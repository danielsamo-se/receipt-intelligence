from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi import WebSocket

from .service import ReceiptService

REPLAY_LINES = ["pilot:01","pilot:02","pilot:03","pilot:08","pilot:24","pilot:29"]


class EventBroker:
    def __init__(self):
        self.clients: dict[str,set[WebSocket]] = {}

    async def connect(self, merchant_id: str, socket: WebSocket):
        await socket.accept()
        self.clients.setdefault(merchant_id,set()).add(socket)
        await socket.send_json({"type":"connected","merchant_id":merchant_id})

    def disconnect(self, merchant_id: str, socket: WebSocket):
        self.clients.get(merchant_id,set()).discard(socket)

    async def publish(self, merchant_id: str, event: dict):
        for socket in tuple(self.clients.get(merchant_id,set())):
            try:
                await socket.send_json(event)
            except Exception:
                self.disconnect(merchant_id,socket)


class ReplayManager:
    def __init__(self, service: ReceiptService, broker: EventBroker, interval: float):
        self.service,self.broker,self.interval = service,broker,interval
        self.tasks: dict[str,asyncio.Task] = {}

    def launch(self, session: dict):
        task = asyncio.create_task(self.run(session))
        self.tasks[session["id"]] = task
        def completed(finished):
            if self.tasks.get(session["id"]) is finished:
                self.tasks.pop(session["id"],None)
        task.add_done_callback(completed)

    async def start(self, merchant_id: str, policy: str) -> dict:
        self.service.merchant(merchant_id)
        session = self.service.store.create_replay(merchant_id,policy,REPLAY_LINES)
        self.launch(session)
        return session

    async def cancel_task(self, session_id: str):
        task = self.tasks.pop(session_id,None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def reset(self, session_id: str, merchant_id: str, policy: str) -> dict:
        self.service.merchant(merchant_id)
        self.service.store.replay(session_id,merchant_id)
        await self.cancel_task(session_id)
        session = self.service.store.reset_replay(session_id,merchant_id,policy)
        self.launch(session)
        return session

    async def stop(self, session_id: str, merchant_id: str) -> dict:
        self.service.merchant(merchant_id)
        session = self.service.store.replay(session_id,merchant_id)
        await self.cancel_task(session_id)
        if session["status"] == "running":
            self.service.store.replay_status(session_id,merchant_id,session["generation"],"stopped")
        return self.service.store.replay(session_id,merchant_id)

    async def run(self, session: dict):
        store = self.service.store
        await self.broker.publish(session["merchant_id"],{"type":"replay.started","session_id":session["id"],"generation":session["generation"]})
        try:
            for line_id in session["sequence"]:
                await asyncio.sleep(self.interval)
                decision = self.service.decision(line_id,session["merchant_id"],session["policy"])
                if not store.add_replay_member(session["id"],session["merchant_id"],line_id,session["generation"]):
                    continue
                current = store.replay(session["id"],session["merchant_id"])
                await self.broker.publish(session["merchant_id"],{
                    "type":"receipt.processed","session_id":session["id"],"generation":session["generation"],
                    "line_id":line_id,"processed_count":current["processed_count"],"total_count":current["total_count"],
                    "decision":decision.model_dump(),
                })
            store.replay_status(session["id"],session["merchant_id"],session["generation"],"complete")
            await self.broker.publish(session["merchant_id"],{"type":"replay.completed","session_id":session["id"],"generation":session["generation"]})
        except asyncio.CancelledError:
            raise
        except Exception:
            store.replay_status(session["id"],session["merchant_id"],session["generation"],"interrupted")
            await self.broker.publish(session["merchant_id"],{"type":"replay.interrupted","session_id":session["id"],"generation":session["generation"]})

    async def close(self):
        for session_id in list(self.tasks):
            await self.cancel_task(session_id)
        self.service.store.interrupt_replays()
