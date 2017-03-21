import datetime
import json
import logging
from itertools import count
import re

import requests
from lxml import html
from lxml.html import HtmlElement, HtmlComment


class URL:
    page = "http://news.discuss.com.hk/viewthread.php?tid={tid}&extra=&page={pagenr}"
    forum = "http://news.discuss.com.hk/forumdisplay.php?fid={fid}&page={pagenr}"
    fora = "http://news.discuss.com.hk/index.php?gid={gid}"

NOTICE_DELETED = {"作者被禁止或刪除 內容自動屏蔽", "提示: 作者被禁止或刪除 內容自動屏蔽", "提示: 該帖被管理員或版主屏蔽"}
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
    if notice and any(n in notice[0].text_content() for n in NOTICE_DELETED):
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


    likes = post.cssselect(".like-number")[0].text_content()
    likes = 0 if likes in ("GG", "推") else int(likes)
    dislikes = post.cssselect(".dislike-number")[0].text_content()
    dislikes = 0 if dislikes in ("GG", "推") else int(dislikes)



    quote = []
    body = post.cssselect(".t_msgfont span")[0]
    content = [body.text]
    for e in body:
        if isinstance(e, HtmlComment):
            continue
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

    extra = {"author_uid": author_uid, "likes": likes, "dislikes": dislikes}
    quote = " ".join(c for c in quote if c)
    if quote:
        extra["quote"] = quote

    profilefields = {"帖子": "posts", "金幣": "gold", "註冊時間": "joindate", "積分": "score"}
    profilekeys = post.cssselect("dl.profile dt")
    profilevalues = post.cssselect("dl.profile dd")
    for k,v in zip(profilekeys, profilevalues):
        k = profilefields[k.text_content()]
        v = v.text_content().strip()
        extra[k] = v

    return {"date": date,
           "headline": headline,
           "text": content,
           "medium": "discusshk",
           "url": post_url,
           "extrameta": json.dumps(extra),
           "author": author}


def get_threads(fid):
    for pagenr in count(1):
        if SKIP and pagenr < PAGE: continue
        url = URL.forum.format(**locals())
        page = get_html(url)
        for a in page.cssselect(".tsubject a"):
            yield int(re_search("\?tid=(\d+)", a.get("href")).group(1))
        if not page.cssselect(".pages .next"):
            break

def get_fora(gid):
    url = URL.fora.format(**locals())
    page = get_html(url)
    for a in page.cssselect(".forumdesc h2 a"):
        fid = int(re_search("\?fid=(\d+)", a.get("href")).group(1))
        if SKIP and fid != FORUM: continue
        yield fid, a.text_content()

SKIP=False
SKIP, FORUM, PAGE, THREAD = True, 1136, 48, 26035379

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                        format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("amcatclient").setLevel(logging.INFO)

    from amcatclient import AmcatAPI
    a = AmcatAPI("https://amcat.nl")
    gid, gname = 150, "時事新聞討論區"
    for fid, fname in get_fora(gid):
        fname = " > ".join([gname, fname])
        logging.info("Scraping forum {fid}:{fname}".format(**locals()))
        for thread in get_threads(fid):
            if SKIP and thread != THREAD: continue
            SKIP=False
            articles = list(scrape_thread(fname, thread))
            logging.info("Adding {} articles from thread {thread}".format(len(articles), **locals()))
            a.create_articles(1325, 33743, json_data = articles)
