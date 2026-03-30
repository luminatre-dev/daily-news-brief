import anthropic
import json
import os
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timedelta
import pytz

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

sgt = pytz.timezone('Asia/Singapore')
now = datetime.now(sgt)
today = now.strftime('%Y년 %m월 %d일')
weekday = now.weekday()
is_weekend = weekday >= 5

# 기존 수집된 URL 로드
existing_news_urls = set()
existing_commodity_urls = set()
try:
    with open("news_data.json", "r", encoding="utf-8") as f:
        existing = json.load(f)
        for n in existing.get("news", []):
            if n.get("url"): existing_news_urls.add(n["url"])
        for n in existing.get("commodity_news", []):
            if n.get("url"): existing_commodity_urls.add(n["url"])
except:
    pass

# RSS 피드 목록
RSS_FEEDS = {
    "sg": [
        ("https://www.straitstimes.com/news/singapore/rss.xml", "Straits Times"),
        ("https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=10416", "CNA"),
        ("https://www.businesstimes.com.sg/rss/all", "Business Times"),
    ],
    "global_econ": [
        ("https://www.ft.com/rss/home", "FT"),
        ("https://feeds.reuters.com/reuters/businessNews", "Reuters Business"),
        ("https://feeds.bloomberg.com/economics/news.rss", "Bloomberg Economics"),
    ],
    "us_politics": [
        ("https://feeds.reuters.com/Reuters/PoliticsNews", "Reuters Politics"),
        ("https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml", "NYT Politics"),
        ("https://www.politico.com/rss/politicopicks.xml", "Politico"),
    ],
    "kr_econ": [
        ("https://www.hankyung.com/feed/finance", "한국경제"),
        ("https://www.mk.co.kr/rss/30100041/", "매일경제"),
        ("https://www.sedaily.com/RSS/Rss.xml", "서울경제"),
        ("https://platum.kr/feed", "플래텀"),
        ("https://www.bloter.net/feed", "블로터"),
        ("https://www.etoday.co.kr/news/rss/finance.xml", "이투데이"),
    ],
}

def fetch_rss(url, source, max_items=5):
    try:
        res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(res.content)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()
            if title and link and link not in existing_news_urls:
                items.append({"title": title, "desc": desc[:150], "url": link, "source": source})
        return items
    except Exception as e:
        print(f"RSS 오류 ({source}): {e}")
        return []

def collect_rss_candidates():
    candidates = {}
    for category, feeds in RSS_FEEDS.items():
        candidates[category] = []
        for url, source in feeds:
            candidates[category] += fetch_rss(url, source, 5)
    return candidates

def curate_with_claude(candidates):
    """Claude가 RSS 후보에서 선별 + 요약 (웹검색 없이)"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=f"""You are a news curator. Select and summarize from candidate news items.
Return a JSON array with exactly these selections:
- 3 Singapore news (politics, economy, society focused) → category: "sg", categoryLabel: "싱가포르"
- 3 Global economy news (major economic news from FT/Reuters/Bloomberg) → category: "global", categoryLabel: "글로벌경제"
- 3 US politics news → category: "us", categoryLabel: "미국정치"
- 6 Korean economy/finance news most relevant to: 대체투자, 인수합병, 스타트업투자, VC, PE, 사모펀드, 운용사, GP/LP 동향, 인력이동, 주요인사 → category: "alt", categoryLabel: "한국경제"
Each item: {{ title (original language), summary (1 sentence in Korean, max 30 words), source, url, category, categoryLabel, time: "오늘" }}
Return ONLY valid JSON array. No markdown. No explanation.""",
        messages=[{"role": "user", "content": f"Today: {today}\nCandidates:\n{json.dumps(candidates, ensure_ascii=False)}"}]
    )
    text = next((b.text for b in response.content if b.type == "text"), "[]")
    text = text.strip().replace("```json", "").replace("```", "").strip()
    s, e = text.find('['), text.rfind(']')
    return json.loads(text[s:e+1]) if s != -1 else []

def fetch_kr_deal_news():
    """딜사이트, 투자조선, thevc 웹검색으로 각 1개"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system="""Search for latest news from dealsite.co.kr, investchosun.com, thevc.kr.
Find 1 article from each site (total 3) about: 대체투자, M&A, 바이아웃, VC투자, PE딜, 스타트업투자, 인력이동, GP/LP.
Return ONLY a JSON array. Each item: { title, summary (1 sentence in Korean, max 30 words), source, url, category: "alt", categoryLabel: "한국딜", time }
No markdown.""",
        messages=[{"role": "user", "content": f"{today} dealsite.co.kr investchosun.com thevc.kr 최신 딜/투자 뉴스 각 1개씩"}]
    )
    text = next((b.text for b in response.content if b.type == "text"), "[]")
    text = text.strip().replace("```json", "").replace("```", "").strip()
    s, e = text.find('['), text.rfind(']')
    items = json.loads(text[s:e+1]) if s != -1 else []
    return [i for i in items if i.get("url") not in existing_news_urls]

def fetch_weekday_news():
    print("📡 RSS 수집 중...")
    candidates = collect_rss_candidates()

    print("🤖 Claude 선별 중...")
    curated = curate_with_claude(candidates)

    print("🔍 딜사이트/투자조선/thevc 검색 중...")
    deal_news = fetch_kr_deal_news()

    return curated + deal_news

# 주말 커머디티 뉴스 수집
def fetch_commodity_news():
    days_since_monday = weekday if weekday < 5 else (5 if weekday == 5 else 6)
    monday = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    date_range = f"{monday.strftime('%Y-%m-%d')} 00:00 SGT ~ {now.strftime('%Y-%m-%d %H:%M')} SGT"
    exclude_urls = list(existing_commodity_urls)[:20]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=f"""You are a commodity market news aggregator. Return ONLY a JSON array.
Each item: {{ title, summary (1 sentence in English, max 30 words), source, url, commodity (Gold/Silver/Platinum|Copper|Crude Oil|Corn|Wheat|Soybean|Coffee), price_impact (up/down/mixed), time }}
Find news from {date_range} that moved prices in: Precious Metals, Copper, Crude Oil, Corn, Wheat, Soybean, Coffee.
Exclude URLs: {exclude_urls}
Return ONLY valid JSON array. No markdown.""",
        messages=[{"role": "user", "content": f"This week's ({date_range}) commodity market-moving news. JSON array only."}]
    )
    text = next((b.text for b in response.content if b.type == "text"), "[]")
    text = text.strip().replace("```json", "").replace("```", "").strip()
    s, e = text.find('['), text.rfind(']')
    items = json.loads(text[s:e+1]) if s != -1 else []
    return [i for i in items if i.get("url") not in existing_commodity_urls]

# 메인 실행
if is_weekend:
    print("📦 주말 모드: 커머디티 뉴스 수집 중...")
    commodity_news = fetch_commodity_news()
    try:
        with open("news_data.json", "r", encoding="utf-8") as f:
            output = json.load(f)
    except:
        output = {"news": []}
    output["commodity_news"] = output.get("commodity_news", []) + commodity_news
    output["commodity_updated_at"] = now.isoformat()
    output["commodity_updated_display"] = now.strftime('%Y-%m-%d %H:%M SGT')
    print(f"✅ 커머디티 뉴스 {len(commodity_news)}개 추가 (누적 {len(output['commodity_news'])}개)")
else:
    print("📰 평일 모드: 뉴스 수집 중...")
    news_list = fetch_weekday_news()
    output = {
        "updated_at": now.isoformat(),
        "updated_at_display": now.strftime('%Y-%m-%d %H:%M SGT'),
        "news": news_list
    }
    print(f"✅ 총 {len(news_list)}개 뉴스 저장 완료")

with open("news_data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
