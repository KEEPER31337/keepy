from .academic_calendar import get_academic_calendar
from .cafeteria import get_cafeteria_menu
from .chat_history import search_chat_history
from .crabfit import create_crabfit_event
from .cse_notice import get_cse_notices
from .cse_pbl import search_pbl_rooms
from .dorm import get_dorm_menu
from .hacker_news import get_hacker_news, read_hacker_news
from .message import react_message, send_message
from .security_news import get_security_news
from .web import read_web_page, search_web

TOOLS = [
    send_message, react_message, create_crabfit_event, get_cse_notices, search_pbl_rooms,
    get_security_news, get_hacker_news, read_hacker_news, search_chat_history, get_cafeteria_menu,
    get_dorm_menu, get_academic_calendar, search_web, read_web_page,
]
