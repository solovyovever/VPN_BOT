import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    WG_API_URL = os.getenv('WG_API_URL')
    WG_API_KEY = os.getenv('WG_API_KEY')
    WG_ENDPOINT_DE = os.getenv('WG_ENDPOINT_DE')
    WG_ENDPOINT_EN = os.getenv('WG_ENDPOINT_EN')
    WG_ENDPOINT_NL = os.getenv('WG_ENDPOINT_NL')
    WG_DNS = os.getenv('WG_DNS', '9.9.9.9')
    TRIAL_DAYS = int(os.getenv('TRIAL_DAYS', 5))
    WG_MTU = int(os.getenv('WG_MTU', 1420))
    WG_KEEPALIVE = int(os.getenv('WG_KEEPALIVE', 25))