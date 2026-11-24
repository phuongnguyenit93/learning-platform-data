# Choosing How to Track Completion Based on Each Scheduler's Contract

## 1. Do Not Confuse Distinct Meanings of Completion

An API named `schedule(...)` returning a `ScheduledFuture` does not mean the
system has completed the business task. Separate the following stages:

1. **Schedule registered / trigger fired:** the scheduler knows when to invoke.
2. **Work handed off:** the runnable was submitted to a thread/executor.
3. **Work finished running:** the callback or actual job ended, possibly with an error.
4. **Business action committed:** the intended data/operation has been durably recorded.

In particular, the `SimpleAsyncTaskScheduler` Javadoc states explicitly that
`ScheduledFuture` may represent the **handoff to the execution thread**, not the
completion of the dispatched callback. Therefore, `get()`/`isDone()` must be
interpreted according to the implementation, not merely the return type name.

## 2. One-Shot and Periodic Tasks Differ

With `ThreadPoolTaskScheduler` backed by `ScheduledExecutorService`, a one-shot
`ScheduledFuture` typically lets you observe when the callback has finished
according to the underlying executor's semantics. Conversely:

- With a **periodic task**, the future represents a series of triggers; it can
  remain incomplete as long as ticks keep running. `isDone() == false` does
  not mean "no tick has run yet."
- With **`SimpleAsyncTaskScheduler`**, the future may only reflect the handoff,
  without waiting for the worker to finish the real work.
- With a scheduler that only **triggers and offloads**, the future attached to
  the trigger likewise does not prove the executor-side task succeeded.
- `cancel(...)` generally helps stop the schedule or attempt to interrupt the
  task according to the corresponding semantics; it does not automatically roll
  back transactions, recall sent messages, or undo external side effects.

## 3. Tracking a One-Shot Task with ScheduledFuture

```java
import java.time.Instant;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.TaskScheduler;

class OneShotProbe {
    private final TaskScheduler scheduler;

    OneShotProbe(TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    void scheduleOneShot() throws Exception {
        ScheduledFuture<?> handle = scheduler.schedule(
            () -> System.out.println("callback finished"),
            Instant.now().plusSeconds(1)
        );
        if (handle == null) {
            throw new IllegalStateException("No remaining trigger time");
        }
        handle.get(5, TimeUnit.SECONDS);
        // Only draw conclusions according to the actual scheduler implementation's contract.
    }
}
```

This example is for analyzing a scheduler's contract. With
`SimpleAsyncTaskScheduler`, even after `handle.get(...)` returns, the handed-off
callback may not have finished yet. Furthermore, an expired `get(timeout)`
**does not** automatically stop the callback.

## 4. When Business Completion Matters: Own the State Yourself

For background jobs that matter to users or have side effects, track a dedicated
`jobId`:

```text
PLANNED -> ACCEPTED -> RUNNING -> SUCCEEDED
                     \\-> FAILED
          \\-> REJECTED
RUNNING   \\-> CANCEL_REQUESTED -> CANCELLED / FAILED / SUCCEEDED
```

The worker is where the final state is updated after actual processing.
If the system has multiple instances or must recover across restarts, store
job state in a durable store with conditional state updates (DB/queue/job store).
Do not keep job state solely in a `ConcurrentHashMap` if SLAs require data to
survive restarts or coordinate across multiple instances.

A separate `CompletableFuture` completed by the worker is also useful within a
single JVM, but it is **not** a durable job store. When coordinating via a
database or message broker, distinguish the `ACCEPTED` state from the handler
having committed the data, and handle timeouts, retries, and idempotency.

## 5. Matrix for Choosing What to Observe

| Need | What to observe |
| --- | --- |
| Cancel future runs | ScheduledFuture / scheduler API |
| Know the trigger fired | Trigger log/timestamp, schedule lag metric |
| Know the worker actually finished | Future/CompletionStage completed by the worker, or result event |
| Know the business transaction succeeded | Durably persisted job state, DB outcome, post-commit event |
| Run periodically across multiple replicas | Lock/lease, ownership, idempotency mechanism, and audit |

## 6. Self-Verification Exercises

1. For a one-shot task, block the callback with a latch and inspect `isDone()`
   on `ThreadPoolTaskScheduler` and `SimpleAsyncTaskScheduler`.
2. For a periodic task, record the callback run count, `isDone()`, and state
   after `cancel`; verify whether any new ticks fire.
3. Split trigger and worker into two executors; demonstrate that the trigger's
   future does not reflect worker completion.
4. Have the worker update state to `SUCCEEDED` **after** transaction commit,
   distinguishing it from merely accepting the job.

## 7. Conclusion

The completion contract must be chosen based on the scheduler and workload type:
`ScheduledFuture` primarily serves schedule management, whereas business
outcomes must be tracked at the appropriate worker/transaction boundary.

**References:** [Spring TaskScheduler Reference](https://docs.spring.io/spring-framework/reference/integration/scheduling.html);
[SimpleAsyncTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html).
