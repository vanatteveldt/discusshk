import re, csv, sys, logging, math
from operator import mul
from functools import reduce
from amcatclient import AmcatAPI
from collections import Counter

# see https://en.wikipedia.org/wiki/CJK_Symbols_and_Punctuation

logging.basicConfig(level=logging.DEBUG,
                    format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("amcatclient").setLevel(logging.INFO)
    
amcat = AmcatAPI("https://amcat.nl")

onegrams, bigrams, trigrams = Counter(), Counter(), Counter()

logging.info("Getting text from articles")
for i,art in enumerate(amcat.get_articles(project=1325, articleset=33743, columns=['text'])):
    if not i % 1000:
        logging.debug("... {i}".format(**locals()))
    text = art['text']
    text2 = re.sub("[^\u4e00-\u9fff]", " ", text)
    #text = re.sub(":\w+:", " ", text, re.A)
    #text = re.sub("[A-Za-z0-9_]", " ", text, re.A)
    #text = re.sub("\W", " ", text, re.U)
    text2 = re.sub("\s+", " ", text2)
    #print(repr(text), text2.split())
    for word in text2.split():
        onegrams.update(word)
        if len(word) >= 3:
            trigrams.update("".join(x) for x in zip(word[:-2], word[1:-1], word[2:]))
        if len(word) >= 2:
            bigrams.update("".join(x) for x in zip(word[:-1], word[1:]))

w =csv.writer(sys.stdout)
w.writerow(["gram", "n", "freq"])
for grams, n in [(onegrams, 1), (bigrams, 2), (trigrams, 3)]:
    logging.info("Outputting {} {}-grams".format(len(grams), n))
    for ngram, freq in grams.most_common():
        if freq > 10:
            w.writerow([ngram, n, freq])
