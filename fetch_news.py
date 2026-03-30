import anthropic
import json
from datetime import datetime
import pytz

client = anthropic.Anthropic()
sgt = pytz.timezone('Asia/Singapore')
today = datetime.now(sgt).strftime('%Y년 %m월 %d일')

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2000,
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
    system="""You are a news aggregator. Search for today's latest news and return ONLY a JSON array.
Each item: { title, summary (2 sentences in Korean), source, url, category (sg|global|alt), categoryLabel (싱가포르|글로벌|대체투자), time }
Find:
- 3 Singapore local news (straitstimes.com, channelnewsasia.com 등)
- 3 Global international news
- 4 Korean alternative investment news: M&A, buyout, private equity
  from dealsite.co.kr, etnews.com, investchosun.com
Return ONLY valid JSON array. No markdown, no explanation.""",
    messages=[{"role": "user", "content": f"{today} 최신 뉴스 JSON 배열로 반환해주세요."}]
)

# 텍스트 블록 추출
text = next((b.text for b in response.content if b.type == "text"), "[]")
text = text.strip().replace("```json", "").replace("```", "").strip()
start, end = text.find('['), text.rfind(']')
news_list = json.loads(text[start:end+1]) if start != -1 else []

output = {
    "updated_at": datetime.now(sgt).isoformat(),
    "updated_at_display": datetime.now(sgt).strftime('%Y-%m-%d %H:%M SGT'),
    "news": news_list
}

with open("news_data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ {len(news_list)}개 뉴스 저장 완료")
