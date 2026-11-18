"""Small CPU-only local E5 adapter. No Hugging Face client or runtime downloads."""
from __future__ import annotations

import hashlib
import json
import threading
from functools import lru_cache

from .catalog import PROJECT


class LocalEmbeddings:
    def __init__(self):
        self.lock = json.loads((PROJECT / "app/data/embedding_model.json").read_text(encoding="utf-8"))
        self.model = None
        self.error = None
        self._guard = threading.RLock()
        self._attempted = False

    def _load(self):
        if self._attempted:
            return
        self._attempted = True
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            folder = PROJECT / "app/.local/embeddings" / self.lock["revision"]
            for name, expected in self.lock["files"].items():
                path = folder / name.split("/")[-1]
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError("Embedding checksum mismatch")
            self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
            self.tokenizer.enable_truncation(max_length=128)
            self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            self.model = ort.InferenceSession(str(folder / "model_qint8_avx512_vnni.onnx"),
                                             sess_options=options, providers=["CPUExecutionProvider"])
        except (ImportError, OSError, ValueError, RuntimeError):
            self.error = "Local embedding files/runtime unavailable or invalid; lexical suggestions only. Run prepare_embeddings.py during setup."

    @lru_cache(maxsize=512)
    def vector(self, text: str, role: str) -> tuple[float, ...] | None:
        with self._guard:
            self._load()
            if self.model is None:
                return None
            import numpy as np

            try:
                encoded = self.tokenizer.encode(f"{role}: {text}")
                features = {"input_ids": np.array([encoded.ids], dtype=np.int64),
                            "attention_mask": np.array([encoded.attention_mask], dtype=np.int64),
                            "token_type_ids": np.array([encoded.type_ids], dtype=np.int64)}
                inputs = {item.name: features[item.name] for item in self.model.get_inputs()}
                hidden = self.model.run(None, inputs)[0]
                mask = features["attention_mask"][..., None]
                pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1)
                vector = pooled[0] / max(float(np.linalg.norm(pooled[0])), 1e-12)
                return tuple(float(x) for x in vector)
            except Exception:
                # A failed local encoder must not disable cached Jev or merchant review.
                self.error = "Local embedding inference failed; lexical suggestions only."
                return None

    def status(self) -> dict:
        return {"model": self.lock["model"], "revision": self.lock["revision"],
                "dimensions": self.lock["dimensions"], "available": self.model is not None and self.error is None,
                "error": self.error, "network_access": False}


embeddings = LocalEmbeddings()
