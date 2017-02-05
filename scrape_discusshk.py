import datetime
import json
import logging
from itertools import count
import re

import requests
from lxml import html
from lxml.html import HtmlElement


class URL:
    page = "http://news.discuss.com.hk/viewthread.php?tid={tid}&extra=&page={pagenr}"
    forum = "http://news.discuss.com.hk/forumdisplay.php?fid={fid}&page={pagenr}"

NOTICE_DELETED = "作者被禁止或刪除 內容自動屏蔽"

def get_html(url) -> HtmlElement:
    """Request html and return as lxml HtmlElement"""
    logging.info(url)
    res = requests.get(url)
    res.encoding = "big5"
    if res.status_code != 200:
        raise Exception("Error on getting {url}: {res.status_code}\n{res.text}".format(**locals()))
    return html.fromstring(res.text)


def re_search(pattern, string, **kargs):
    """Wrap re.search to raise exception if no match found"""
    m = re.search(pattern, string, **kargs)
    if not m:
        raise Exception("Cannot parse: {string!r}".format(**locals()))
    return m


def scrape_thread(section, tid):
    for pagenr in count(1):
        url = URL.page.format(**locals())
        page = get_html(url)
        yield from scrape_page(section, url, pagenr, page)
        if not page.cssselect(".pages .next"):
            break


def scrape_page(section, url, pagenr, page):
    title = page.cssselect("h1")[0].text_content().strip()
    for i, post in enumerate(page.cssselect(".mainbox.viewthread")):
        try:
            p = scrape_post(url, pagenr, title, post)
        except:
            logging.exception("Error on scraping {url} post {i}".format(**locals()))
            raise
        if p is not None:
            p['section'] = section
            yield p


def scrape_post(url, pagenr, title, post):
    postinfo, = post.cssselect(".postinfo strong")
    id = int(postinfo.get("id").replace("postnum_", ""))
    nr = int(postinfo.text_content().replace("#", ""))
    if nr == 1 and pagenr != 1:
        # first post is repeated on all pages, so skip on later pages
        return

    notice = post.cssselect("div.notice")
    if notice and NOTICE_DELETED in notice[0].text_content():
        return
    elif notice:
        print(notice[0].text_content())

    headline = "{title} #{nr}".format(**locals())
    post_url = "{url}#pid{id}".format(**locals())

    a, = post.cssselect(".postauthor cite a")
    author = a.text_content()
    author_uid = int(a.get("href").split("uid=")[-1])

    info, = post.cssselect(".postinfo")
    datestr = re_search("發表於\s*(\d+-\d+-\d+\s+\d+:\d+\s+(?:AM|PM))", info.text_content())
    date = datetime.datetime.strptime(datestr.group(1), "%Y-%m-%d %I:%M %p")

    quote = []
    body = post.cssselect(".t_msgfont span")[0]
    content = [body.text]
    for e in body:
        content.append(e.text)
        if e.tag == "div" and e.get('class') == "quote":
            quote.append(e.text_content())
        elif e.tag == "img":
            src = e.get("src")
            if "images/smilies/default/" in src:
                smiley = src.split("images/smilies/default/")[1].replace(".gif", "")
                content.append(":"+smiley+":")
        elif e.tag == "br":
            content.append("\n")
        else:
            content.append(e.text_content())
        content.append(e.tail)
    content = " ".join(c for c in content if c)
    if not content: content = "-"

    extra = {"author_uid": author_uid}
    quote = " ".join(c for c in quote if c)
    if quote:
        extra["quote"] = quote

    return {"date": date,
           "headline": headline,
           "text": content,
           "medium": "discusshk",
           "url": post_url,
           "extrameta": json.dumps(extra),
           "author": author}


def get_threads(fid):
    for pagenr in count(1):
        url = URL.forum.format(**locals())
        page = get_html(url)
        for a in page.cssselect(".tsubject a"):
            yield int(re_search("\?tid=(\d+)", a.get("href")).group(1))
        if not page.cssselect(".pages .next"):
            break


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                        format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')
    from amcatclient import AmcatAPI
    a = AmcatAPI("https://amcat.nl")

    fname = "金融財經討論區 > 時事新聞討論區"
    fid = 1175 # news
    for thread in get_threads(fid):
        articles = list(scrape_thread(fname, thread))
        a.create_articles(1325, 33521, json_data = articles)
