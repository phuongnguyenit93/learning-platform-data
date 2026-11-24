# Fixed-Delay Limitation Running on the Scheduler Thread of SimpleAsyncTaskScheduler

## 1. An Exception That Impacts Architecture

`SimpleAsyncTaskScheduler` (Spring Framework 6.1+) is often introduced as a
scheduler that uses one thread to trigger work and separate threads to run
callbacks. **Do not apply that model mechanically to fixed-delay.**
According to the Spring Javadoc, fixed-delay runs directly on the **single
scheduler thread** to preserve its semantics: the next run only starts after
the previous callback **completes** and the delay interval has elapsed.

For example, suppose a scheduled method performs I/O for 8 seconds and has
`fixedDelay = 2000`. In a normal cycle, the first callback finishes after
8 seconds, and only then waits an additional 2 seconds. With
`SimpleAsyncTaskScheduler`, a long fixed-delay callback can also occupy the
scheduler thread, **forcing other fixed-delay tasks to wait**.

## 2. Comparing the Three Trigger Modes

| Mode | Primary time reference | Key consideration |
| --- | --- | --- |
| Fixed-delay | Interval from callback *completion* to the *start* of the next run | A callback can hold the scheduler thread of SimpleAsyncTaskScheduler |
| Fixed-rate | Targets a periodic trigger cadence | Can dispatch triggers to other threads; overlap must be considered |
| Cron | Timestamps based on schedule expression and time zone | Computing a trigger time does not mean work finishes on time |

Switching fixed-delay to fixed-rate is **not** a harmless optimization:
operational semantics change. Fixed-delay usually expresses the intent "finish,
then rest"; fixed-rate expresses "try to stay on a time cadence." If business
logic cannot allow two data updates to overlap, you must add a **single-flight**
mechanism, lock/lease, or data-level control; do not merely change the annotation.

## 3. Example Reproducing Head-of-Line Blocking

```java
import java.util.concurrent.CountDownLatch;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class FixedDelayExperiments {
    private final CountDownLatch release = new CountDownLatch(1);

    // Uses the same SimpleAsyncTaskScheduler bean configured in the previous lesson.
    @Scheduled(scheduler = "reportScheduler", fixedDelay = 2_000)
    public void slowJob() throws InterruptedException {
        System.out.println("SLOW: " + Thread.currentThread().getName());
        release.await();
    }

    @Scheduled(scheduler = "reportScheduler", fixedDelay = 2_000)
    public void anotherJob() {
        System.out.println("OTHER: " + Thread.currentThread().getName());
    }

    public void releaseExperiment() {
        release.countDown();
    }
}
```

This is an **intentional experiment**, not for production applications:
the `slowJob` callback is held until `releaseExperiment()` is called.
Use a test with a timeout and a `finally` block to release the latch even if
an assertion fails. Observe the thread names and execution counts of both
callbacks, and avoid drawing conclusions from a single trace because initial
ordering also depends on OS thread scheduling.

## 4. Design Options

- If you need to preserve fixed-delay semantics for jobs that may run long,
  consider a `ThreadPoolTaskScheduler` with an appropriate worker count and
  a load-testing plan. Keep in mind that each periodic series still has its own
  ordering/completion behavior and does not automatically prevent system-wide overlap.
- If you need to decouple triggering from long processing, use a short callback
  whose sole job is submitting work to a bounded executor. In that case, **when
  the callback finishes is no longer when the real work finishes**; fixed-delay
  will measure from the short handoff, not from the underlying business task.
- If the job inherently requires durability, retries across restarts, or
  single-node execution across a cluster, an in-memory scheduler is insufficient.
  You need a durable queue/job store or dedicated coordination.

## 5. Pre-Decision Checklist

1. Should the delay be measured from callback completion or from completion of the underlying business work?
2. Are two runs allowed to overlap? If not, what state enforces that invariant?
3. Would a callback blocking the scheduler thread delay other schedules?
4. When a task is cancelled, is interruption handled cooperatively or does the callback continue?
5. Which metrics measure *schedule lag*, *execution duration*, *handoff latency*,
   and *business completion* separately?

## 6. Conclusion

Fixed-delay on `SimpleAsyncTaskScheduler` requires special caution because it
runs on a single scheduler thread. Choose a scheduler based on the semantics
of the workload, not solely on the ability to spawn virtual threads.

**References:** [Spring Scheduling Reference](https://docs.spring.io/spring-framework/reference/integration/scheduling.html);
[SimpleAsyncTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html).
