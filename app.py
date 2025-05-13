from flask import Flask, request, jsonify
from openai import OpenAI
import os
import hmac
import hashlib
import requests
from bs4 import BeautifulSoup

# Proxy configuration for residential access
PROXY_USER = os.getenv("PROXY_USER")
PROXY_PASS = os.getenv("PROXY_PASS")
PROXY_HOST = "rp.scrapegw.com:6060"

proxies = {
    "http": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}",
    "https": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}",
}


app = Flask(__name__)
client = OpenAI()
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

def verify_slack_request(req):
    timestamp = req.headers.get('X-Slack-Request-Timestamp')
    sig_basestring = f"v0:{timestamp}:{req.get_data(as_text=True)}"
    my_signature = 'v0=' + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    slack_signature = req.headers.get('X-Slack-Signature')
    return hmac.compare_digest(my_signature, slack_signature)

@app.route("/summarize", methods=["POST"])
def summarize():
    # Optional: Uncomment in production
    # if not verify_slack_request(request):
    #     return "Unauthorized", 403

    user_input = request.form.get("text", "").strip()

    if not user_input:
        return jsonify({
            "response_type": "ephemeral",
            "text": "Please provide text to summarize."
        })

    # If it's a URL, fetch and extract text
    if user_input.startswith("http"):
        try:
            page = requests.get(user_input, proxies=proxies, timeout=30)
            soup = BeautifulSoup(page.text, "html.parser")
            title = soup.title.string.strip() if soup.title else "Untitled"
            paragraphs = soup.find_all("p")
            content = " ".join(p.get_text() for p in paragraphs[:10])
            content_to_summarize = f"Title: {title}\n\n{content}"
        except Exception as e:
            return jsonify({
                "response_type": "ephemeral",
                "text": f"Failed to fetch URL: {str(e)}"
            })
    else:
        content_to_summarize = user_input

    prompt = f"""
    Write a draft news story for publication on https://circuit.news. Your response should include:

    - A clear, engaging headline
    - A 2-5 paragraph article written in a professional, informative tone
    - Relevant context and important details for readers interested in business developments in the Middle East, sovereign wealth funds (SWFs), regional investments, and financial diplomacy

    Base the article on the following source content:
    {content_to_summarize}
    """


    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400
        )
        story = response.choices[0].message.content.strip()
    except Exception as e:
        return jsonify({
            "response_type": "ephemeral",
            "text": f"Something went wrong: {str(e)}"
        })

    return jsonify({
        "response_type": "in_channel",
        "text": f"*Summary by GPT-3.5-turbo:*\n{story}"
    })

@app.route("/", methods=["GET"])
def health_check():
    return "Summarize bot is running!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
