pip install -r requirements.txt

sqlite3 websites.db

INSERT INTO websites (url, content) VALUES ('https://example.com', '');
INSERT INTO websites (url, content) VALUES ('https://another-example.com', '');

.exit

SELECT * FROM websites;

tail -f monitor.log