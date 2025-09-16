import asyncio, httpx

class ReplicateClient:
    def __init__(self, api_token: str):
        self.headers = {"Authorization": f"Token {api_token}", "Content-Type": "application/json"}

    async def generate(self, model_version: str, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.replicate.com/v1/predictions",
                                  json={"version": model_version, "input": {"prompt": prompt}},
                                  headers=self.headers)
            r.raise_for_status()
            pred = r.json()
            url = pred["urls"]["get"]
            while True:
                rr = await client.get(url, headers=self.headers)
                d = rr.json()
                if d["status"] == "succeeded":
                    out = d.get("output")
                    return out[0] if isinstance(out, list) else out
                if d["status"] in {"failed", "canceled"}:
                    raise RuntimeError(d)
                await asyncio.sleep(2)
