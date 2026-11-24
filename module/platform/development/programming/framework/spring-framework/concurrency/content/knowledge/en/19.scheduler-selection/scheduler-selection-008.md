# Separating the Scheduler from the Worker Pool to Control Two Workload Types

## 1. Two Different Workloads, Two Different Policies

A scheduled callback often only needs to fire at the right time, whereas the
actual work may need to query a database, make HTTP calls, render reports, or
run a long batch. To keep slow callbacks from occupying scheduling resources,
you can separate them:

```text
@Scheduled / TaskScheduler       ThreadPoolTaskExecutor
  [trigger pool]                       [worker pool]
        |                                   |
        +--- limits trigger cadence ------> +--- business task
               schedule lag                    queue / running / timeout
```

In Spring Framework, `ThreadPoolTaskScheduler` handles scheduling;
`ThreadPoolTaskExecutor` is an option for executing background work.
The two beans can have different pool sizes, queues, deadlines, metrics, and
shutdown policies.

## 2. Bounded Configuration Example

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableScheduling
class JobsConfiguration {
    @Bean("timeScheduler")
    ThreadPoolTaskScheduler timeScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("time-");
        return scheduler;
    }

    @Bean("jobWorkers")
    ThreadPoolTaskExecutor jobWorkers() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-");
        return executor;
    }
}
```

Here the scheduler has its own pool; the executor has at most four workers and
a bounded queue. These numbers are illustrative only, **not** a general
recommendation. You must size them based on CPU time, wait time, DB/HTTP
connection counts, and SLAs.

## 3. Handoff Requires a Clear Contract

```java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
class ScheduledReport {
    private final ThreadPoolTaskExecutor workers;
    private final AtomicBoolean inFlight = new AtomicBoolean();

    ScheduledReport(ThreadPoolTaskExecutor workers) {
        this.workers = workers;
    }

    @Scheduled(scheduler = "timeScheduler", fixedRate = 10_000)
    public void trigger() {
        // Prevents overlap within a single instance; not a distributed lock.
        if (!inFlight.compareAndSet(false, true)) {
            return;
        }
        try {
            workers.execute(() -> {
                try {
                    doReport();
                } finally {
                    inFlight.set(false);
                }
            });
        } catch (TaskRejectedException ex) {
            inFlight.set(false);
            // Record metric and make an intentional retry/dead-letter decision.
        }
    }

    private void doReport() {
        // Business logic with its own timeout and transaction boundary.
    }
}
```

**Important:** `inFlight` only protects within *a single JVM*. Applications
deployed across multiple replicas need a lease, distributed lock, or conditional
database mechanism matching business invariants. If the executor's policy
silently discards tasks, no exception is thrown from `execute` to release the
flag; therefore, choose a rejection policy aligned with your admission contract.
This example assumes a policy that throws an exception on rejection.

## 4. Completion Layers and Risks

| Signal | Practical meaning |
| --- | --- |
| Trigger fired | The scheduler reached the trigger timestamp |
| Handoff accepted | The executor accepted the execution request; it may still be queued |
| Worker started | The task actually began running on a worker |
| Worker completed | The task finished; success and failure must still be distinguished |
| Business committed | The business invariant has been confirmed via transaction/DB |

The `trigger()` callback returning quickly **does not prove** the report is
done. If submissions arrive faster than worker capacity, the queue will grow,
causing delays or rejections. Monitor queue depth, active workers, rejections,
start lag, duration, failures, and business completion.

## 5. Verification Exercises

1. Use a `CountDownLatch` to hold the first job on a worker; observe that the
   scheduler still fires while `inFlight` prevents additional submissions.
2. Disable single-flight, build a bounded backlog, and measure the time from
   trigger to worker start; test the queue-full case.
3. Verify whether exceptions in the worker are reported to monitoring or
   ignored; add metrics and logs with a correlation id.
4. Test stop/shutdown: determine whether running workers are awaited and
   whether queued jobs are lost.

## 6. Conclusion

Separating the scheduler from workers helps control the two workloads independently,
but it introduces an async boundary: trigger success differs from job success.
Design acceptance, backpressure, idempotency, and completion according to your
system's contract.

**References:** [Spring Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html);
[Spring Boot Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html).
