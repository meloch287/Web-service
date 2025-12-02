import uvicorn
from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    print("=" * 50)
    print("SENDER - Attack Traffic Generator")
    print("=" * 50)
    print(f"Host: {settings.sender_host}:{settings.sender_port}")
    print(f"Target: {settings.receiver_url}")
    print("=" * 50)
    uvicorn.run("app.sender:app", host=settings.sender_host, port=settings.sender_port, reload=True, access_log=False)
