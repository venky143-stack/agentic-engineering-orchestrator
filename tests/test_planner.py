
from aeo.planner import DependencyPlanner


def _successful_handlers(planner):
    return {
        task_id: (lambda tid=task_id: {"task": tid})
        for task_id in planner.tasks
    }


def test_dag_runs_all_tasks_and_records_trace():
    planner = DependencyPlanner(max_retries=1)

    results, trace = planner.execute(_successful_handlers(planner))

    assert set(results) == set(planner.tasks)
    assert all(
        task.status == "success"
        for task in planner.tasks.values()
    )
    assert any(event["event"] == "success" for event in trace)


def test_retries_transient_failure_and_records_retry_event():
    planner = DependencyPlanner(max_retries=1)
    calls = {"requirements": 0}

    def flaky():
        calls["requirements"] += 1

        if calls["requirements"] == 1:
            raise RuntimeError("temporary")

        return "ok"

    handlers = _successful_handlers(planner)
    handlers["requirements"] = flaky

    results, trace = planner.execute(handlers)

    assert results["requirements"] == "ok"
    assert calls["requirements"] == 2

    task = planner.tasks["requirements"]
    assert task.attempts == 2
    assert task.status == "success"
    assert task.error is None

    retry_events = [
        event for event in trace
        if event["event"] == "retry"
        and event["task"] == "requirements"
    ]
    assert len(retry_events) == 1
    assert retry_events[0]["attempt"] == 1
    assert retry_events[0]["next_attempt"] == 2
    assert "temporary" in retry_events[0]["error"]

    assert any(
        event["event"] == "success"
        and event["task"] == "requirements"
        and event["attempt"] == 2
        for event in trace
    )


def test_exhausted_retries_mark_task_failed():
    planner = DependencyPlanner(max_retries=2)
    calls = {"requirements": 0}

    def always_fails():
        calls["requirements"] += 1
        raise RuntimeError("persistent failure")

    handlers = _successful_handlers(planner)
    handlers["requirements"] = always_fails

    results, trace = planner.execute(handlers)

    task = planner.tasks["requirements"]
    assert calls["requirements"] == 3
    assert task.attempts == 3
    assert task.status == "failed"
    assert "persistent failure" in task.error

    retry_events = [
        event for event in trace
        if event["event"] == "retry"
        and event["task"] == "requirements"
    ]
    assert len(retry_events) == 2

    assert any(
        event["event"] == "failure"
        and event["task"] == "requirements"
        and event["attempt"] == 3
        for event in trace
    )


def test_failed_dependency_blocks_downstream_tasks():
    planner = DependencyPlanner(max_retries=1)

    def fail_requirements():
        raise RuntimeError("requirements analysis failed")

    handlers = _successful_handlers(planner)
    handlers["requirements"] = fail_requirements

    results, trace = planner.execute(handlers)

    # Initial attempt plus one retry.
    requirements = planner.tasks["requirements"]
    assert requirements.status == "failed"
    assert requirements.attempts == 2
    assert "requirements analysis failed" in requirements.error

    # Direct and transitive dependents must not execute.
    for task_id in (
        "architecture",
        "api_contract",
        "docs",
        "implementation",
        "tests",
        "validation",
    ):
        assert planner.tasks[task_id].status == "blocked"
        assert task_id not in results

    # An independent branch should still complete.
    assert planner.tasks["repository"].status == "success"
    assert "repository" in results

    assert any(
        event["event"] == "failure"
        and event["task"] == "requirements"
        for event in trace
    )
    assert any(
        event["event"] == "blocked"
        and event["task"] == "architecture"
        for event in trace
    )


def test_independent_tasks_succeed_when_another_branch_fails():
    planner = DependencyPlanner(max_retries=0)

    handlers = _successful_handlers(planner)

    def fail_requirements():
        raise RuntimeError("requirements unavailable")

    handlers["requirements"] = fail_requirements

    results, trace = planner.execute(handlers)

    # Repository analysis has no dependency on requirements.
    assert planner.tasks["repository"].status == "success"
    assert "repository" in results

    # Requirements-dependent tasks must not run.
    assert planner.tasks["architecture"].status == "blocked"
    assert planner.tasks["api_contract"].status == "blocked"

    # Failure must be visible in the trace.
    assert any(
        event["event"] == "failure"
        and event["task"] == "requirements"
        for event in trace
    )


def test_missing_handler_fails_clearly():
    planner = DependencyPlanner()
    handlers = _successful_handlers(planner)
    del handlers["requirements"]

    try:
        planner.execute(handlers)
    except ValueError as exc:
        assert "requirements" in str(exc)
    else:
        raise AssertionError("Expected missing handler to raise ValueError")


def test_negative_retry_count_is_rejected():
    try:
        DependencyPlanner(max_retries=-1)
    except ValueError as exc:
        assert "max_retries" in str(exc)
    else:
        raise AssertionError("Expected negative retries to raise ValueError")


def test_dependency_cycle_is_rejected_before_handlers_run():
    planner = DependencyPlanner()
    planner.tasks["requirements"].dependencies = ["architecture"]

    calls = []
    handlers = {
        task_id: (lambda tid=task_id: calls.append(tid))
        for task_id in planner.tasks
    }

    try:
        planner.execute(handlers)
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("Expected dependency cycle to be rejected")

    assert calls == []


def test_unknown_dependency_is_rejected_before_handlers_run():
    planner = DependencyPlanner()
    planner.tasks["architecture"].dependencies = ["missing_task"]

    calls = []
    handlers = {
        task_id: (lambda tid=task_id: calls.append(tid))
        for task_id in planner.tasks
    }

    try:
        planner.execute(handlers)
    except ValueError as exc:
        assert "missing_task" in str(exc)
    else:
        raise AssertionError("Expected unknown dependency to be rejected")

    assert calls == []


def test_self_dependency_is_rejected_before_handlers_run():
    planner = DependencyPlanner()
    planner.tasks["requirements"].dependencies = ["requirements"]

    calls = []
    handlers = {
        task_id: (lambda tid=task_id: calls.append(tid))
        for task_id in planner.tasks
    }

    try:
        planner.execute(handlers)
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("Expected self-dependency to be rejected")

    assert calls == []

def test_execute_can_be_reused_for_a_fresh_run():
    planner = DependencyPlanner()
    calls = []

    handlers = {
        task_id: (lambda tid=task_id: calls.append(tid) or tid)
        for task_id in planner.tasks
    }

    first_results, first_trace = planner.execute(handlers)

    assert set(first_results) == set(planner.tasks)
    assert len(calls) == len(planner.tasks)
    assert {
        event["task"]
        for event in first_trace
        if event["event"] == "success"
    } == set(planner.tasks)

    second_results, second_trace = planner.execute(handlers)

    assert set(second_results) == set(planner.tasks)
    assert len(calls) == 2 * len(planner.tasks)
    assert {
        event["task"]
        for event in second_trace
        if event["event"] == "success"
    } == set(planner.tasks)

def test_execute_recovers_after_failed_run():
    planner = DependencyPlanner()
    attempts = {}
    fail_requirements = True

    handlers = {}

    for task_id in planner.tasks:
        def handler(tid=task_id):
            attempts[tid] = attempts.get(tid, 0) + 1

            if tid == "requirements" and fail_requirements:
                raise RuntimeError("simulated first-run failure")

            return tid

        handlers[task_id] = handler

    first_results, first_trace = planner.execute(handlers)

    assert "requirements" not in first_results
    assert planner.tasks["requirements"].status == "failed"
    assert any(
        event["event"] == "blocked"
        for event in first_trace
    )

    fail_requirements = False

    second_results, second_trace = planner.execute(handlers)

    assert set(second_results) == set(planner.tasks)
    assert {
        event["task"]
        for event in second_trace
        if event["event"] == "success"
    } == set(planner.tasks)

    assert all(
        task.status == "success"
        for task in planner.tasks.values()
    )


def test_zero_retries_runs_failed_task_once_without_retry_event():
    planner = DependencyPlanner(max_retries=0)
    calls = {"requirements": 0}

    def always_fails():
        calls["requirements"] += 1
        raise RuntimeError("failure with retries disabled")

    handlers = _successful_handlers(planner)
    handlers["requirements"] = always_fails

    results, trace = planner.execute(handlers)

    task = planner.tasks["requirements"]

    assert "requirements" not in results
    assert calls["requirements"] == 1
    assert task.attempts == 1
    assert task.status == "failed"
    assert "failure with retries disabled" in task.error

    assert not any(
        event["event"] == "retry"
        and event["task"] == "requirements"
        for event in trace
    )

    assert any(
        event["event"] == "failure"
        and event["task"] == "requirements"
        and event["attempt"] == 1
        for event in trace
    )


