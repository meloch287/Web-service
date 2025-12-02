import uvicorn
from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    print("=" * 50)
    print("RECEIVER - Protected Target Service")
    print("=" * 50)
    print(f"Host: {settings.receiver_host}:{settings.receiver_port}")
    print("Protection: Nemesida WAF + pfSense simulation")
    print("=" * 50)
    uvicorn.run("app.receiver:app", host=settings.receiver_host, port=settings.receiver_port, reload=True, access_log=False)
