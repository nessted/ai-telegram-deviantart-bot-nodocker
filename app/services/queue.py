import asyncio
from aiolimiter import AsyncLimiter

job_queue: asyncio.Queue = asyncio.Queue()
lim_openai = AsyncLimiter(60, 60)       # 60 req/min
lim_tensorart = AsyncLimiter(30, 60)
lim_replicate = AsyncLimiter(30, 60)

_workers: list[asyncio.Task] = []

async def worker():
    while True:
        job = await job_queue.get()
        try:
            provider = job.get("provider")
            func = job["func"]
            args = job.get("args", [])
            kwargs = job.get("kwargs", {})
            if provider == "openai":
                async with lim_openai:
                    await func(*args, **kwargs)
            elif provider == "tensorart":
                async with lim_tensorart:
                    await func(*args, **kwargs)
            elif provider == "replicate":
                async with lim_replicate:
                    await func(*args, **kwargs)
            else:
                await func(*args, **kwargs)
        finally:
            job_queue.task_done()

def start_workers(n=3):
    global _workers
    if _workers:
        return
    for _ in range(n):
        _workers.append(asyncio.create_task(worker()))

async def submit_job(provider: str, func, *args, **kwargs):
    await job_queue.put({"provider": provider, "func": func, "args": args, "kwargs": kwargs})
