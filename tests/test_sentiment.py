"""Tests for the no-API-key lexicon sentiment analyzer."""

from harken.analyze.sentiment import LexiconSentiment
from harken.models import Sentiment


def make():
    return LexiconSentiment()


def test_clearly_positive():
    a = make()
    r = a.score("This tool is absolutely fantastic, I love it!")
    assert r.label is Sentiment.POSITIVE
    assert r.score > 0.2


def test_clearly_negative():
    a = make()
    r = a.score("Honestly terrible experience, buggy and frustrating. I hate it.")
    assert r.label is Sentiment.NEGATIVE
    assert r.score < -0.2


def test_neutral_factual():
    a = make()
    r = a.score("The release ships on Tuesday and supports SQLite.")
    assert r.label is Sentiment.NEUTRAL


def test_negation_flips_positive():
    a = make()
    pos = a.score("This is good.")
    neg = a.score("This is not good.")
    assert pos.score > 0
    assert neg.score < pos.score  # negation pulls it down / negative


def test_intensifier_amplifies():
    a = make()
    plain = a.score("good")
    strong = a.score("very good")
    assert strong.score > plain.score


def test_empty_is_neutral():
    a = make()
    r = a.score("")
    assert r.label is Sentiment.NEUTRAL
    assert r.score == 0.0


def test_emoji_positive():
    a = make()
    r = a.score("shipped it 🎉🚀")
    assert r.score > 0


def test_typographic_apostrophe_negates_like_ascii():
    a = make()
    ascii_quote = a.score("I don't like it")
    curly_quote = a.score("I don’t like it")
    assert ascii_quote.label is Sentiment.NEGATIVE
    assert curly_quote.label is Sentiment.NEGATIVE
    assert curly_quote.score == ascii_quote.score


def test_but_contrast_favors_the_second_clause():
    a = make()
    r = a.score("Quill is fine but overhyped. The sync is bad, the price is worse.")
    assert r.label is Sentiment.NEGATIVE


def test_churn_language_reads_negative():
    a = make()
    r = a.score("We switched off Acme after the third outage. Support never replied.")
    assert r.label is Sentiment.NEGATIVE


def test_price_hike_with_no_notice_reads_negative():
    a = make()
    r = a.score("Acme just raised prices 40% with no notice.")
    assert r.label is Sentiment.NEGATIVE


def test_less_negative_language_reads_positive():
    r = make().score("The UI is cleaner and way less bloated.")
    assert r.label is Sentiment.POSITIVE


def test_common_product_complaints_read_negative():
    samples = [
        "The price went up again and is too much for me.",
        "It keeps crashing and performance is rough.",
        "The lack of reliable sync is a non-starter.",
        "I don't trust it; that is a dealbreaker.",
    ]
    assert all(make().score(text).label is Sentiment.NEGATIVE for text in samples)


def test_no_complaints_reads_positive():
    assert make().score("No complaints from our team.").label is Sentiment.POSITIVE


def test_fixed_bug_reads_positive():
    assert (
        make().score("The bug was fixed and now everything works perfectly.").label
        is Sentiment.POSITIVE
    )


def test_explicitly_split_opinions_read_neutral():
    assert make().score("Some users like it and others hate it.").label is Sentiment.NEUTRAL


def test_stock_mild_phrases_stay_neutral():
    assert make().score("It works as described.").label is Sentiment.NEUTRAL
    assert make().score("It is fine, nothing special.").label is Sentiment.NEUTRAL
