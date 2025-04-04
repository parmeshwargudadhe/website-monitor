import time
import json
import logging
import sqlite3
import requests
import smtplib
import os  # For checking file size
from email.message import EmailMessage
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

# Load configuration
with open("config.json") as f:
    config = json.load(f)

CHECK_INTERVAL = config["check_interval"]
EMAIL_FROM = config["email_from"]
EMAIL_TO = config["email_to"]
EMAIL_PASSWORD = config["email_password"]

# Logging setup with log size management
def setup_logging():
    # Define the log file path
    log_file = "monitor.log"
    
    # Check if the log file exists and exceeds 1 MB (1 * 1024 * 1024 bytes)
    if os.path.exists(log_file) and os.path.getsize(log_file) > 1 * 1024 * 1024:
        # Clear the log file if it's too large
        with open(log_file, "w"):
            pass  # Truncate the file to 0 bytes

    # Set up logging
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

setup_logging()

# Database initialization
def init_db():
    conn = sqlite3.connect("websites.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS websites (
            url TEXT PRIMARY KEY,
            content TEXT
        )
    """)
    conn.commit()
    conn.close()

# Load websites from database
def load_websites():
    init_db()  # Ensure the table exists
    conn = sqlite3.connect("websites.db")
    cursor = conn.cursor()
    cursor.execute("SELECT url, content FROM websites")
    websites = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    logging.debug(f"Loaded websites: {websites}")
    return websites

# Save updated content to database
def save_websites(websites):
    init_db()  # Ensure the table exists
    try:
        conn = sqlite3.connect("websites.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM websites")
        logging.debug(f"Saving websites: {websites}")  # Log the data being saved
        cursor.executemany("INSERT INTO websites (url, content) VALUES (?, ?)", websites.items())
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Database error in save_websites: {e}")
    finally:
        conn.close()

# Fetch webpage content using requests
def get_page_content(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract main content (fallback to <body> if no specific tags are found)
        main_content = soup.find("main") or soup.find("div", class_="content") or soup.find("body")
        content = main_content.get_text(strip=True) if main_content else ""
        logging.debug(f"Fetched content for {url}: {content[:200]}...")
        return content
    except requests.RequestException as e:
        logging.error(f"Error fetching {url}: {e}")
        return None

# Send email notification
def send_email(url, old_content, new_content):
    msg = EmailMessage()
    msg["Subject"] = f"🌐 Website Change Detected: {url}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    msg.set_content(f"""
    🔔 **Website Update Alert**
    -------------------------------
    🖥 **Website:** {url}
    
    🕒 **Detected Change at:** {time.strftime('%Y-%m-%d %H:%M:%S')}
    
    📜 **Old Content (First 500 chars):**
    {old_content[:500]}...
    
    🆕 **New Content (First 500 chars):**
    {new_content[:500]}...
    
    📌 Check the website for full details: {url}
    """)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
        logging.info(f"Email sent for {url}")
    except Exception as e:
        logging.error(f"Failed to send email for {url}: {e}")

# Monitor a single website
def monitor_website(url, old_content):
    new_content = get_page_content(url)
    if new_content is None:
        logging.warning(f"Failed to fetch content for {url}. Skipping.")
        return url, old_content

    # Handle first-time monitoring (no old content)
    if not old_content:
        logging.info(f"First-time monitoring for {url}. Saving initial content.")
        return url, new_content

    # Detect changes
    if new_content != old_content:
        logging.info(f"Change detected on {url}")
        send_email(url, old_content, new_content)
        return url, new_content
    return url, old_content

# Main monitoring loop
def monitor_websites():
    init_db()  # Ensure the database and table are initialized
    try:
        while True:
            logging.info("Starting monitoring loop...")
            websites = load_websites()
            with ThreadPoolExecutor(max_workers=10) as executor:
                results = executor.map(lambda item: monitor_website(item[0], item[1]), websites.items())
            updated_websites = dict(results)
            save_websites(updated_websites)
            logging.info(f"Check completed. Next run in {CHECK_INTERVAL} seconds.")
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt detected! Shutting down gracefully...")
        print("\nMonitoring stopped by user.")
        exit(0)  # Exit cleanly

if __name__ == "__main__":
    monitor_websites()