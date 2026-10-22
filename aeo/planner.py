
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Callable
import threading
import time


@dataclass
class Task:
    task_id: str
    agent: str
    dependencies: list[str]
    status: str = "pending"
    attempts: int = 0
    error: str | None = None
    duration_ms: int | None = None

    def to_dict(self):
        return asdict(self)


class DependencyPlanner:
    """Deterministic DAG scheduler with bounded retries and execution tracing."""

    def __init__(self, max_retries: int = 1):
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        self.max_retries = max_retries
        self.tasks = {
            "requirements": Task(
                "requirements", "requirement_analyst", []
            ),
            "repository": Task(
                "repository", "repository_analyst", []
            ),
            "architecture": Task(
                "architecture", "architecture_agent", ["requirements"]
            ),
            "api_contract": Task(
                "api_contract", "api_contract_agent", ["requirements"]
            ),
            "docs": Task(
                "docs", "docs_agent", ["requirements", "architecture"]
            ),
            "implementation": Task(
                "implementation",
                "implementation_agent",
                ["api_contract", "architecture"],
            ),
            "tests": Task(
                "tests", "test_agent", ["implementation", "api_contract"]
            ),
            "validation": Task(
                "validation",
                "validation_gate",
                ["implementation", "tests", "docs", "repository"],
            ),
        }

    def execute(
        self, handlers: dict[str, Callable[[], object]]
    ) -> tuple[dict[str, object], list[dict]]:
        results: dict[str, object] = {}
        trace: list[dict] = []
        trace_lock = threading.Lock()

        missing_handlers = sorted(set(self.tasks) - set(handlers))
        if missing_handlers:
            raise ValueError(
                f"Missing handlers for tasks: {', '.join(missing_handlers)}"
            )

        while any(
            task.status not in {"success", "failed", "blocked"}
            for task in self.tasks.values()
        ):
            pending = [
                task
                for task in self.tasks.values()
                if task.status == "pending"
            ]

            blocked = [
                task
                for task in pending
                if any(
                    self.tasks[dependency].status in {"failed", "blocked"}
                    for dependency in task.dependencies
                )
            ]

            for task in blocked:
                failed_dependencies = [
                    dependency
                    for dependency in task.dependencies
                    if self.tasks[dependency].status in {"failed", "blocked"}
                ]
                task.status = "blocked"
                task.error = (
                    "Dependency did not succeed: "
                    + ", ".join(failed_dependencies)
                )
                trace.append(
                    {
                        "event": "blocked",
                        "task": task.task_id,
                        "reason": task.error,
                        "at": time.time(),
                    }
                )

            ready = [
                task
                for task in self.tasks.values()
                if task.status == "pending"
                and all(
                    self.tasks[dependency].status == "success"
                    for dependency in task.dependencies
                )
            ]

            if not ready:
                pending_tasks = [
                    task
                    for task in self.tasks.values()
                    if task.status == "pending"
                ]

                # Repeat so blocked status propagates through
                # every downstream dependency level.
                if blocked:
                    continue

                if pending_tasks:
                    raise RuntimeError(
                        "Planner deadlock: unresolved dependency cycle "
                        "or invalid task state"
                    )

                break

            # Tasks in this wave have successful dependencies and
            # can execute concurrently.
            with ThreadPoolExecutor(
                max_workers=min(4, len(ready))
            ) as pool:
                futures = {
                    pool.submit(
                        self._run_one,
                        task,
                        handlers[task.task_id],
                        trace,
                        trace_lock,
                    ): task
                    for task in ready
                }

                for future in as_completed(futures):
                    task = futures[future]

                    try:
                        results[task.task_id] = future.result()
                        task.status = "success"
                        task.error = None

                        trace.append(
                            {
                                "event": "success",
                                "task": task.task_id,
                                "attempt": task.attempts,
                                "duration_ms": task.duration_ms,
                                "at": time.time(),
                            }
                        )

                    except Exception as exc:
                        task.error = f"{type(exc).__name__}: {exc}"
                        task.status = "failed"

                        trace.append(
                            {
                                "event": "failure",
                                "task": task.task_id,
                                "attempt": task.attempts,
                                "error": task.error,
                                "at": time.time(),
                            }
                        )

        return results, trace

    def _run_one(
        self,
        task: Task,
        handler: Callable[[], object],
        trace: list[dict],
        trace_lock: threading.Lock,
    ):
        last_error = None
        started_total = time.perf_counter()

        for attempt in range(1, self.max_retries + 2):
            task.attempts = attempt
            started_attempt = time.perf_counter()

            try:
                result = handler()
                task.duration_ms = round(
                    (time.perf_counter() - started_total) * 1000, 2
                )
                return result

            except Exception as exc:
                last_error = exc

                if attempt <= self.max_retries:
                    event = {
                        "event": "retry",
                        "task": task.task_id,
                        "attempt": attempt,
                        "next_attempt": attempt + 1,
                        "error": f"{type(exc).__name__}: {exc}",
                        "duration_ms": round(
                            (time.perf_counter() - started_attempt) * 1000,
                            2,
                        ),
                        "at": time.time(),
                    }

                    with trace_lock:
                        trace.append(event)

        task.duration_ms = round(
            (time.perf_counter() - started_total) * 1000, 2
        )
        raise last_error  # type: ignore[misc]