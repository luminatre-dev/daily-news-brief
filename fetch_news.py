import json
import os
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timedelta
import pytz
from google import genai
from google.genai import types

# Google Gemini 클라이언트 설정
client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

sgt = pytz.timezone('Asia/Singapore')
now = datetime.now(sgt)
today = now.strftime('%Y년 %m월 %d일')
week_ago = (now - timedelta(days=7)).strftime('%Y년 %m월 %d일')
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

# FT RSS
def fetch_ft_news(max_items=3):
    try:
        res = requests.get("https://www.ft.com/rss/home", timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(res.content)
        items = []
        for item in root.findall(".//item")[:max_items * 2]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()
            if title and link and link not in existing_news_urls:
                items.append({
                    "title": title,
                    "summary": desc[:100] + "..." if len(desc) > 100 else desc,
                    "source": "FT",
                    "url": link,
                    "category": "global",
                    "categoryLabel": "글로벌",
                    "time": "FT"
                })
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"FT RSS 오류: {e}")
        return []

# Gemini 호출
def call_gemini(system_prompt, user_prompt):
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=1500,
            temperature=0.1,
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
        contents=user_prompt
    )
    return response.text if response.text else ""

# 평일 뉴스 수집
def fetch_weekday_news():
    exclude_urls = list(existing_news_urls)[:20]

    system_prompt = f"""You are a news aggregator. Search and return ONLY a JSON array with exactly 5 news items.
Search date range: {week_ago} ~ {today} (last 7 days only).
Find:
- 3 Korean alternative investment news covering: 바이아웃, VC투자, Growth투자, 스타트업투자, M&A, 인수합병, 인사동향, GP/LP, 사모펀드, 운용사 동향. Search across: dealsite.co.kr, investchosun.com, thevc.kr, hankyung.com, mk.co.kr, etnews.com, platum.kr and any relevant Korean financial news sites → category: "alt", categoryLabel: "대체투자"
- 2 Global economy news (major international economic developments) → category: "global", categoryLabel: "글로벌"
Exclude these already collected URLs: {exclude_urls}
Each item: {{ title, summary (1 sentence in Korean, max 30 words), source, url, category, categoryLabel, time }}
Return ONLY valid JSON array. No markdown. No explanation."""

    user_prompt = f"{week_ago}부터 {today}까지 최신 뉴스 5개를 JSON 배열로 반환해주세요."

    text = call_gemini(system_prompt, user_prompt)

    if not text.strip():
        print("⚠️ Gemini 응답 없음")
        return []
    text = text.strip().replace("```json", "").replace("```", "").strip()
    s, e = text.find('['), text.rfind(']')
    try:
        news_list = json.loads(text[s:e+1]) if s != -1 else []
    except Exception as ex:
        print(f"⚠️ JSON 파싱 오류: {ex}")
        news_list = []

    ft_news = fetch_ft_news(max_items=3)
    return news_list + ft_news

# 주말 커머디티 뉴스 수집
def fetch_commodity_news():
    days_since_monday = weekday if weekday < 5 else (5 if weekday == 5 else 6)
    monday = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    date_range = f"{monday.strftime('%Y-%m-%d')} 00:00 SGT ~ {now.strftime('%Y-%m-%d %H:%M')} SGT"
    exclude_urls = list(existing_commodity_urls)[:20]

    system_prompt = f"""You are a commodity market news aggregator. Return ONLY a JSON array.
Each item: {{ title, summary (1 sentence in English, max 30 words), source, url, commodity (Gold/Silver/Platinum|Copper|Crude Oil|Corn|Wheat|Soybean|Coffee), price_impact (up/down/mixed), time }}
Find news from {date_range} that moved prices in: Precious Metals, Copper, Crude Oil, Corn, Wheat, Soybean, Coffee.
Exclude URLs: {exclude_urls}
Return ONLY valid JSON array. No markdown."""

    user_prompt = f"This week's ({date_range}) commodity market-moving news. JSON array only."

    text = call_gemini(system_prompt, user_prompt)

    if not text.strip():
        return []
    text = text.strip().replace("```json", "").replace("```", "").strip()
    s, e = text.find('['), text.rfind(']')
    try:
        items = json.loads(text[s:e+1]) if s != -1 else []
    except:
        items = []
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
