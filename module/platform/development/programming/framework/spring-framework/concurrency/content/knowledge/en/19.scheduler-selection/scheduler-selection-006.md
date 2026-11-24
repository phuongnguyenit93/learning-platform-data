# SimpleAsyncTaskScheduler Separates Triggering from Task Execution

## 1. The Problem

A scheduler must solve **two distinct responsibilities**: knowing *when*
to trigger work and deciding *where* the work actually runs. If a
callback blocks on I/O for several seconds, conflating these two responsibilities
leads to misdiagnosis: a schedule was triggered on time, yet the work has not
finished, or one callback delays the schedule of another.

Since Spring Framework **6.1**, `SimpleAsyncTaskScheduler` is a
`TaskScheduler` implementation that uses **a single scheduler thread** to manage
triggers. For fixed-rate and cron, it can dispatch each run to a separate thread;
on **JDK 21+**, virtual threads can be enabled. This is not a
`ThreadPoolTaskScheduler` with a fixed number of workers. In particular,
**fixed-delay is an important exception**, which will be analyzed in lesson 7.

## 2. Visualizing the Execution Flow

```text
Clock / Trigger / @Scheduled
          |
          v
  Single scheduler thread
          |    calculates and marks trigger times
          |----> task A -> execution thread A
          |----> task B -> execution thread B
          |----> task C -> execution thread C
          |
          +----> fixed-delay: exception, runs on scheduler thread
```

With thread-per-task, there is no traditional pool reusing threads. Virtual
threads can make waiting on I/O lighter than platform threads, but they
**do not** increase the number of CPU cores, database connections, or downstream
API limits. A system still needs timeouts, concurrency limits, and backpressure.

## 3. Configuration in Spring

Java 21 and Spring Framework 6.1+ example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.SimpleAsyncTaskScheduler;
import org.springframework.stereotype.Component;

@Configuration
@EnableScheduling
class SchedulingConfiguration {
    @Bean("reportScheduler")
    SimpleAsyncTaskScheduler reportScheduler() {
        SimpleAsyncTaskScheduler scheduler = new SimpleAsyncTaskScheduler();
        scheduler.setThreadNamePrefix("report-schedule-");
        scheduler.setVirtualThreads(true); // Only use with Java 21+
        scheduler.setConcurrencyLimit(16); // Concurrency limit, not DB pool size
        return scheduler;
    }
}

@Component
class ReportJobs {
    @Scheduled(scheduler = "reportScheduler", fixedRate = 10_000)
    public void refresh() {
        // Call an injected service with appropriate timeout and idempotency.
        System.out.println("Executing on " + Thread.currentThread());
    }
}
```

The scheduler name in `@Scheduled` is used to select the bean; avoid having
multiple scheduler beans that cause ambiguity. Setting `setVirtualThreads(true)`
requires a Java 21+ environment. If the project runs on an older Java version,
do not enable this option.

## 4. When to Use a Dedicated Target Executor?

`SimpleAsyncTaskScheduler.setTargetTaskExecutor(Executor)` lets you offload
the **execution** of triggered tasks to another `Executor`, such as an
application-owned `ThreadPoolTaskExecutor`. In that setup, the scheduler still
primarily handles trigger timing; the target executor controls workers and the queue.

```java
@Bean("reportScheduler")
SimpleAsyncTaskScheduler reportScheduler(ThreadPoolTaskExecutor reportWorkers) {
    SimpleAsyncTaskScheduler scheduler = new SimpleAsyncTaskScheduler();
    scheduler.setTargetTaskExecutor(reportWorkers);
    return scheduler;
}
```

The example above only illustrates the delegation mechanism; you must declare
the `reportWorkers` bean with explicit pool/queue bounds and a rejection policy.
**Do not treat** `SimpleAsyncTaskScheduler` + target executor as
`ThreadPoolTaskScheduler`: scheduling paths and completion semantics differ.

## 5. Self-Verification

1. Record the timestamp before a task starts, the thread name, `isVirtual()`,
   and the task completion timestamp; run two independent fixed-rate callbacks.
2. Have one callback wait on a `CountDownLatch`; check whether another callback
   can start on a different thread.
3. Apply increasing load levels and observe the number of active tasks, DB
   connections, and rejections on the target executor. Do not use `Thread.sleep()`
   to *prove* schedule correctness.
4. Try cancelling a schedule while a callback has already been handed off to a
   worker; distinguish between **stopping future triggers** and **stopping a running task**.

## 6. Conclusion

Choose `SimpleAsyncTaskScheduler` when you need a lean scheduling path capable
of dispatching each run to a separate thread, especially well suited for
I/O workloads on Java 21. Do not treat that characteristic as automatic proof of
concurrent fixed-delay execution, resource bounding, durability, or completion.

**References:** [Spring Scheduling Reference](https://docs.spring.io/spring-framework/reference/integration/scheduling.html);
[SimpleAsyncTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html).
