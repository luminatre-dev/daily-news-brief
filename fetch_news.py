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
weekday = now.weekday()  # 0=월, 5=토, 6=일
is_weekend = weekday >= 5

# 기존 news_data.json 로드 (중복 제거용)
existing_urls = set()
try:
    with open("news_data.json", "r", encoding="utf-8") as f:
        existing = json.load(f)
        for n in existing.get("commodity_news", []):
            if n.get("url"):
                existing_urls.add(n["url"])
except:
    pass

# FT RSS 피드에서 뉴스 가져오기
def fetch_ft_news(max_items=3):
    ft_feeds = [
        ("https://www.ft.com/rss/home", "FT"),
        ("https://www.ft.com/markets?format=rss", "FT Markets"),
    ]
    items = []
    for url, source in ft_feeds:
        try:
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:max_items]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                desc = item.findtext("description", "").strip()
                if title and link:
                    items.append({
                        "title": title,
                        "summary": desc[:100] + "..." if len(desc) > 100 else desc,
                        "source": source,
                        "url": link,
                        "category": "global",
                        "categoryLabel": "글로벌",
                        "time": "FT"
                    })
            if items:
                break
        except Exception as e:
            print(f"FT RSS 오류: {e}")
    return items[:max_items]

# 평일 뉴스 수집
def fetch_weekday_news():
    # 기존 수집된 URL 로드 (중복 제거용)
existing_news_urls = set()
try:
    with open("news_data.json", "r", encoding="utf-8") as f:
        existing = json.load(f)
        for n in existing.get("news", []):
            if n.get("url"):
                existing_news_urls.add(n["url"])
except:
    pass


        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system="""You are a news aggregator. Return ONLY a JSON array with exactly 6 news items.
Each item: { title, summary (1 sentence in Korean, max 30 words), source, url, category (sg|global|alt), categoryLabel (싱가포르|글로벌|대체투자), time }
Find:
- 1 Singapore local news
- 2 Global news
- 3 Korean alternative investment & PE/VC related news covering: 대체투자, 사모펀드(PEF), 바이아웃, 스타트업 투자, VC 딜, PE 딜, M&A, 인수합병, 업계동향, 정부/금융당국 정책, 펀드 결성, LP/GP 동향 etc. Search broadly across dealsite.co.kr, etnews.com, investchosun.com, hankyung.com, mk.co.kr, sedaily.com, bloter.net, thevc.kr, platum.kr, venturesquare.net or any other relevant Korean news sites
Exclude these already collected URLs: {list(existing_news_urls)[:30]}
Return ONLY valid JSON array. No markdown, no explanation.""",
        messages=[{"role": "user", "content": f"{today} 최신 뉴스 6개를 JSON 배열로 반환해주세요."}]
    )
    text = next((b.text for b in response.content if b.type == "text"), "[]")
    text = text.strip().replace("```json", "").replace("```", "").strip()
    start, end = text.find('['), text.rfind(']')
    news_list = json.loads(text[start:end+1]) if start != -1 else []
    ft_news = fetch_ft_news(max_items=3)
    return news_list + ft_news

# 주말 커머디티 뉴스 수집
def fetch_commodity_news():
    # 이번 주 월요일 00:00 SGT ~ 현재 시점
    days_since_monday = now.weekday() if now.weekday() < 5 else (5 if now.weekday() == 5 else 6)
    monday = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    date_range = f"{monday.strftime('%Y-%m-%d')} 00:00 SGT ~ {now.strftime('%Y-%m-%d %H:%M')} SGT"

    response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1500,
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=f"""You are a commodity market news aggregator. Return ONLY a JSON array.
Each item: {{ title, summary (1 sentence in English, max 30 words), source, url, commodity (one of: Gold/Silver/Platinum, Copper, Crude Oil, Corn, Wheat, Soybean, Coffee), price_impact (up/down/mixed), time }}
Find news from {date_range} (Mon-Fri this week) that significantly impacted prices in global commodity markets for:
- Precious Metals (Gold, Silver, Platinum)
- Copper
- Crude Oil
- Corn
- Wheat
- Soybean
- Coffee
Focus only on news that actually moved or could move prices. Exclude already known URLs: {list(existing_urls)[:20]}
Return ONLY valid JSON array. No markdown, no explanation.""",
        messages=[{"role": "user", "content": f"Find this week's ({date_range}) key commodity market-moving news. Return as JSON array."}]
    )
    text = next((b.text for b in response.content if b.type == "text"), "[]")
    text = text.strip().replace("```json", "").replace("```", "").strip()
    start, end = text.find('['), text.rfind(']')
    items = json.loads(text[start:end+1]) if start != -1 else []

    # 중복 URL 제거
    new_items = [i for i in items if i.get("url") not in existing_urls]
    for i in new_items:
        existing_urls.add(i.get("url", ""))
    return new_items

# 메인 실행
if is_weekend:
    print("📦 주말 모드: 커머디티 뉴스 수집 중...")
    commodity_news = fetch_commodity_news()

    # 기존 데이터 유지하면서 커머디티 뉴스 누적
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
    print("📰 평일 모드: 일반 뉴스 수집 중...")
    news_list = fetch_weekday_news()
    output = {
        "updated_at": now.isoformat(),
        "updated_at_display": now.strftime('%Y-%m-%d %H:%M SGT'),
        "news": news_list
    }
    print(f"✅ 뉴스 {len(news_list)}개 저장 완료")

with open("news_data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
