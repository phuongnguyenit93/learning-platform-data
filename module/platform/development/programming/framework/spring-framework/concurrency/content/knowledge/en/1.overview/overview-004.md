# The Relationship Between TaskExecutor, @Async, TaskScheduler, and @Scheduled in Spring Framework

## 1. The Big Picture: Task Execution vs. Deciding When to Run

Spring Framework provides two groups of capabilities that are often used together but answer **two different questions**:

- **Execution:** once a piece of work is requested to run, where does it run, on which thread, is there a queue, and how many tasks are processed concurrently? This is the role of **TaskExecutor**; **@Async** is the declarative way for Spring to route a method call to an executor.
- **Scheduling:** when should a piece of work be triggered: once in the future, after each pause, at a regular cadence, or on a cron schedule? This is the role of **TaskScheduler**; **@Scheduled** declares the trigger schedule for a method.

These two groups are **independent**: an application that only needs asynchronous processing can use @Async without enabling @Scheduled; an application that only needs periodic jobs can use @Scheduled without enabling @Async. They combine when you want *to trigger a task on schedule, then hand off the heavy processing to another executor*.

| Component | Nature | Primary Function | When Does It Operate? |
| --- | --- | --- | --- |
| **TaskExecutor** | Interface, extending java.util.concurrent.Executor | Accepts a Runnable and executes it according to the executor's policy | When code submits a task via execute or Spring dispatches an @Async call |
| **@Async** | Annotation on a method/type | Marks a call via Spring proxy so the method body is dispatched to an executor | When another object calls the method through the Spring proxy |
| **TaskScheduler** | Interface | Registers a Runnable to run once or repeatedly according to time/Trigger | When code registers a task or Spring registers @Scheduled |
| **@Scheduled** | Annotation on a method | Declares fixedDelay, fixedRate, cron, initialDelay | Spring registers the schedule when the bean is initialized; the scheduler triggers it afterward |

Visualize the two control flows:

~~~text
HTTP/event/service caller
    └── calls bean.method() via Spring proxy
            └── @Async ──> TaskExecutor ──> worker thread ──> method

Clock / schedule trigger
    └── TaskScheduler ──> @Scheduled method on bean
                               ├── processes directly on scheduler thread
                               └── calls another bean via @Async proxy
                                        └── TaskExecutor ──> worker thread
~~~

**Key takeaway:** @Async does not create a schedule on its own; @Scheduled does not inherently move all work to an @Async pool. When a task is triggered by a schedule and where the work executes are two separate decisions.

## 2. How Are TaskExecutor and @Async Related?

**TaskExecutor** accepts a task as a Runnable via the execute(Runnable) method. Spring provides several implementations; the name "executor" does not guarantee there is a thread pool: for example, SyncTaskExecutor runs immediately on the calling thread, SimpleAsyncTaskExecutor creates a thread per task (and can be configured to use virtual threads on a suitable JDK), while ThreadPoolTaskExecutor manages a thread pool and queue.

Direct usage:

~~~java
// Example method inside a Spring bean with an injected TaskExecutor.
public void submit(TaskExecutor executor) {
    executor.execute(() ->
            System.out.println(Thread.currentThread().getName()));
}
~~~

With **@Async**, the developer does not manually wrap a Runnable. Spring uses an AOP/proxy mechanism (by default) to intercept valid calls, submit the work to an executor, and return control to the caller without waiting for the method body to finish. This does not mean every method annotated with @Async runs in the background: the conditions for proxy activation are critical.

To enable the annotation in Spring configuration, use **@EnableAsync**. An @Async method is typically declared to return **void**, **Future<T>**, or **CompletableFuture<T>**. A void method fits fire-and-forget cases with a dedicated error-handling mechanism; CompletableFuture lets the caller receive results, chain steps, or handle failures without blocking. Avoid calling get()/join() immediately if the goal is not to block the calling thread.

Short example of separating beans:

~~~java
@Service
class EmailWorker {
    @Async("appTaskExecutor")
    public CompletableFuture<String> send(String address) {
        // Method body runs on the designated executor.
        return CompletableFuture.completedFuture("sent to " + address);
    }
}

@Service
class CheckoutService {
    private final EmailWorker worker;

    CheckoutService(EmailWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> checkout(String address) {
        // Call through another bean so Spring's proxy can intercept it.
        return worker.send(address);
    }
}
~~~

The snippet above only illustrates the relationship between beans; imports, executor configuration, and a standalone runnable application are in the complete example below.

**Self-invocation trap:** if the same object calls this.send() or just calls send() internally, the call does not pass through the proxy so @Async may have no effect. In the default proxy mode, avoid placing async work on private/final methods that cannot be properly intercepted by the proxy; prefer public methods on a Spring bean called from another bean. @Async should not be used as a way to directly initialize async work on a @PostConstruct method.

## 3. How Are TaskScheduler and @Scheduled Related?

**TaskScheduler** represents scheduling capability. It has APIs such as schedule(Runnable, Instant), schedule(Runnable, Trigger), scheduleAtFixedRate(Runnable, Duration), and scheduleWithFixedDelay(Runnable, Duration). These methods return a ScheduledFuture in appropriate cases, allowing the schedule to be canceled via cancel(...).

**@Scheduled** is the declarative layer on top of that functionality: Spring finds annotated methods on beans and registers triggers with the scheduler; you do not have to call scheduler.schedule(...) manually for each method. Enable this feature with **@EnableScheduling**.

Example declarations:

~~~java
@Scheduled(initialDelay = 1000, fixedDelay = 5000)
public void refreshCache() {
    // First trigger after about 1 second;
    // each subsequent run waits 5 seconds after the previous one finishes.
}

@Scheduled(fixedRate = 5000)
public void updateHeartbeat() {
    // Target cadence is 5 seconds between start times.
}

@Scheduled(cron = "0 0 9 * * MON-FRI", zone = "Asia/Ho_Chi_Minh")
public void weekdayReport() {
    // 09:00 AM Monday through Friday in the selected time zone.
}
~~~

By default, numeric values in the example above are in **milliseconds**; you can use the timeUnit attribute of @Scheduled. Standard Spring cron expressions have **six fields**: second, minute, hour, day of month, month, day of week; do not take a five-field Unix cron expression and apply it directly. For standard synchronous Java @Scheduled methods, declare **no parameters and a void return type**; normal return values are unused. Spring Framework 6.1+ also provides dedicated support for certain Publisher/reactive types and Kotlin suspend functions with different rules, which should not be extrapolated from synchronous Java examples.

Distinguishing the three scheduling modes:

| Configuration | Where Is the Interval Measured From? | Key Things to Remember |
| --- | --- | --- |
| **fixedDelay** | Waits the delay duration *after* a **scheduled method invocation** finishes | Suitable when you want a pause between runs; if the method only submits an async task and returns, it does not wait for the async task to finish |
| **fixedRate** | Targets a period measured from the scheduled start times | Tasks can be delayed if the scheduler is busy; do not assume all runs of a registration definitely overlap |
| **cron** | Calendar times matching the expression, optionally with a zone | Used for time-of-day/day-of-week schedules; account for time zones and daylight saving time shifts in DST zones |

Spring has **ThreadPoolTaskScheduler**, which typically executes callbacks directly on the scheduler threads it manages. Therefore, a long-running @Scheduled callback can occupy a slot and delay other schedules if the scheduler is too small. Spring 6.1 introduces **SimpleAsyncTaskScheduler** with different execution behavior (in particular, fixedDelay still executes on a single scheduler thread); do not equate every TaskScheduler with the exact same thread model.

If no scheduler is explicitly specified, Spring has a mechanism to look up a suitable scheduler or create a local fallback; in Spring Boot there is also auto-configuration depending on the application's beans and properties. Therefore, **do not assume the scheduler and async executor are the same pool**. When multiple options exist, declaring beans or explicit configuration makes things easier to control.

## 4. Runnable Example: Scheduler Triggers, Executor Processes

This example set uses **Java 17+ and Spring Boot 3.3.x (Spring Framework 6.1)**. Create a Gradle project with this structure:

~~~text
schedule-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/concurrency/
    ├── DemoApplication.java
    ├── TaskConfiguration.java
    ├── ReportWorker.java
    └── ReportSchedule.java
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'schedule-demo'
~~~

File **build.gradle** (versions are stable examples, not necessarily the latest):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

**DemoApplication.java**:

~~~java
package demo.concurrency;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**TaskConfiguration.java** creates **two separate pools**. The name appTaskExecutor is explicitly selected by @Async; the name taskScheduler allows Spring to recognize the scheduler for @Scheduled methods.

~~~java
package demo.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class TaskConfiguration {
    @Bean(name = "appTaskExecutor")
    public ThreadPoolTaskExecutor appTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("async-");
        return executor;
    }

    @Bean(name = "taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("schedule-");
        return scheduler;
    }
}
~~~

**ReportWorker.java** runs heavy work on the executor; CompletableFuture records success or failure. Preserve the interrupt flag if sleep is interrupted.

~~~java
package demo.concurrency;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("appTaskExecutor")
    public CompletableFuture<String> buildReport(int sequence) {
        System.out.printf("WORK start #%d thread=%s%n",
                sequence, Thread.currentThread().getName());

        try {
            TimeUnit.SECONDS.sleep(2);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(ex);
        }

        System.out.printf("WORK end   #%d thread=%s%n",
                sequence, Thread.currentThread().getName());
        return CompletableFuture.completedFuture("report-" + sequence);
    }
}
~~~

**ReportSchedule.java** only receives the schedule tick and delegates through **another bean** so the Spring proxy handles @Async; it does not wait for the two-second work.

~~~java
package demo.concurrency;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReportSchedule {
    private final AtomicInteger counter = new AtomicInteger();
    private final ReportWorker worker;

    public ReportSchedule(ReportWorker worker) {
        this.worker = worker;
    }

    @Scheduled(initialDelay = 1000, fixedDelay = 4000)
    public void onTick() {
        int sequence = counter.incrementAndGet();

        System.out.printf("TICK       #%d thread=%s%n",
                sequence, Thread.currentThread().getName());

        worker.buildReport(sequence).whenComplete((result, error) -> {
            if (error != null) {
                System.err.printf("FAIL       #%d cause=%s%n",
                        sequence, error);
            } else {
                System.out.printf("DONE       #%d result=%s%n",
                        sequence, result);
            }
        });
    }
}
~~~

Use **Gradle 8.5+ and JDK 17+** installed on your machine; run from the schedule-demo directory:

~~~bash
gradle bootRun
~~~

If the project has the Gradle Wrapper, use **./gradlew bootRun** on Linux/macOS or **gradlew.bat bootRun** on Windows. Stop with Ctrl+C to close the application context.

A run *might* print the following lines (startup logs omitted):

~~~text
TICK       #1 thread=schedule-1
WORK start #1 thread=async-1
WORK end   #1 thread=async-1
DONE       #1 result=report-1
TICK       #2 thread=schedule-1
WORK start #2 thread=async-2
WORK end   #2 thread=async-2
DONE       #2 result=report-2
~~~

Actual thread names/numbers, timing, and line ordering depend on the runtime; **do not treat the transcript above as a single or immutable stdout**. What to observe is that TICK lines run on **schedule-**, WORK lines run on **async-**, and the next trigger is not forced to wait for the previous run's worker.

### Why Does the Example Need Both Beans?

1. **taskScheduler** manages the triggers of onTick() according to fixedDelay. It does not take responsibility for running the heavy report itself.
2. **ReportSchedule** runs briefly, hands off the task, and returns. Therefore, the four-second fixedDelay is measured from when onTick() finishes, not when ReportWorker finishes.
3. **@Async("appTaskExecutor")** is where the buildReport() call is dispatched to the executor pool. The annotation will not behave as expected if worker.buildReport(...) is replaced with an internal call on the same object.
4. **appTaskExecutor** controls how many workers can execute or wait. If report duration exceeds the trigger period and the arrival rate exceeds the processing rate, the queue can build up and eventually lead to task rejections.
5. **whenComplete** observes the error or value of the CompletableFuture. The callback may run on the thread completing the future or the thread attaching the callback, depending on timing; do not assume it is the scheduler thread or a separate pool.

With the executor configuration above, corePoolSize=2, maxPoolSize=4, and queueCapacity=20. ThreadPoolExecutor typically prioritizes creating up to the core pool, then placing tasks into the queue, and only scaling above core when the queue is full; **maxPoolSize=4 does not mean four workers are always running from the start**. Setting the queue too large can increase latency and memory usage.

## 5. Valid Combinations and Choosing a Design

| Need | What to Use? | Explanation |
| --- | --- | --- |
| Process a user request without blocking the caller | **@Async** + TaskExecutor | The caller initiates the request; the executor decides execution |
| Manually submit a Runnable to a pool | **TaskExecutor.execute(...)** | No annotation needed if you want to submit tasks directly |
| Run periodic, fast, non-blocking cleanup | **@Scheduled** + TaskScheduler | The scheduler wakes the method automatically on schedule |
| Run a periodic job where heavy work should use a separate pool | **@Scheduled** in bean A calling **@Async** in bean B | Separates timing policy from processing capacity |
| Register flexible schedules dynamically and cancel them | **TaskScheduler.schedule(...)**, keeping ScheduledFuture | Suitable when schedules are created/canceled dynamically at runtime |

An application can also use TaskScheduler directly without writing @Scheduled:

~~~java
// Snippet inside a Spring bean with an injected TaskScheduler.
ScheduledFuture<?> handle = taskScheduler.scheduleAtFixedRate(
        () -> System.out.println("heartbeat"),
        java.time.Duration.ofSeconds(5)
);

// When no longer needed:
handle.cancel(false);
~~~

At the implementation level, TaskScheduler can be backed by ScheduledExecutorService, while TaskExecutor can use ThreadPoolExecutor. Although they belong to the same java.util.concurrent family, Spring's APIs still represent two distinct roles. The fact that a scheduler can execute a Runnable does not automatically make it the executor for every @Async call.

### Should @Scheduled and @Async Be Placed on the Same Method?

Some configurations can make them work together, but **overlap limits and lifecycle become harder to predict**: when the method is called on schedule, the async call may return before the work finishes; fixedDelay therefore no longer represents the pause between two actual work runs. For a problem requiring clear operations, separate a **short trigger bean** (@Scheduled) and a **background processing bean** (@Async), as in the example above.

If the requirement is "must run only once at a time," @Scheduled + @Async alone does not satisfy that guarantee. You need a mechanism to prevent overlap (locks, semaphores, job state, bounded queues, or an appropriate orchestration solution). In a multi-instance system, each instance can register the same schedule independently; @Scheduled by itself does not provide **cluster-wide single-execution** coordination.

## 6. Common Errors and Important Constraints

**@Async does not seem to work:** check @EnableAsync, whether the bean is Spring-managed, whether the call goes through the proxy, whether the method is suitable for proxy interception, and whether the executor exists under the qualifier. Printing Thread.currentThread().getName() in both caller and worker is a quick diagnostic.

**@Scheduled does not trigger:** check @EnableScheduling, whether the bean is created in the ApplicationContext, whether the cron/fixedDelay attributes are valid, and whether the scheduler is blocked. A normal method annotated with @Scheduled can still be called directly in Java; that is a regular call, not a schedule-generated trigger.

**Confusing fixedDelay with async job completion time:** if an @Scheduled method calls async and returns immediately, the next trigger is measured from when that short method finishes. If you want a delay starting from when the entire processing completes, design the scheduled callback to intentionally wait/coordinate on completion; weigh the impact on scheduler threads, timeouts, and throughput. Do not fix it by blindly adding Thread.sleep().

**Task storms or resource exhaustion:** increasing the scheduler pool only pushes more callbacks and does not solve a slow worker pool; increasing the worker pool indefinitely also does not create more system resources. Measure processing time, backlog, rejected tasks, CPU/I/O, queue limits, and use backpressure/drop or coalescing policies where appropriate.

**Swallowed errors:** with @Async returning void, exceptions cannot automatically propagate back to the caller like a synchronous call; configure AsyncUncaughtExceptionHandler or add proper logging/monitoring. With Future/CompletableFuture, handle complete exceptionally, whenComplete, exceptionally, or get() at an intentional boundary. With synchronous @Scheduled, errors belong to the scheduler thread and the corresponding ErrorHandler mechanism; do not assume the error-handling behavior of the two annotations is identical.

**Thread context does not propagate automatically:** transactions, ThreadLocal, MDC logging, SecurityContext, or request context are not guaranteed to be present on an async worker. In particular, @Transactional on the caller does not mean the worker uses the same transaction/connection. If needed, pass data explicitly, start transactions at the worker boundary, or configure a TaskDecorator/controlled context-propagation mechanism. Do not share EntityManager or non-thread-safe objects across tasks.

**Application shutdown:** during shutdown, consider the policy for waiting on in-flight tasks, canceling scheduled triggers, and handling interrupts. Do not assume the program stops immediately or will always finish every queued task; that depends on executor/scheduler configuration and the Spring lifecycle.

**Multiple schedules on one method:** @Scheduled is repeatable; each declaration has its own trigger and can produce closely spaced or overlapping runs. Do not rely on a small pool as a business locking mechanism.

## 7. Self-Check Questions

1. A REST endpoint calls an `@Async` method, but the code calls `this.method()`: why is the thread still the HTTP request thread? **Because internal calls bypass the proxy in default mode.**
2. `@Scheduled(fixedDelay = 5000)` calls `@Async` and returns after 10 ms while the worker takes 30 seconds: does the next trigger wait for the worker to finish? **No; fixedDelay is tied to the scheduled invocation finishing, and does not automatically observe future completion.**
3. You have `@EnableScheduling` without `@EnableAsync`, and an `@Scheduled` method calls another `@Async` method: what is certain? **The schedule still triggers, but `@Async` has not been enabled through this annotation configuration, so you cannot assume the call is asynchronous.**
4. A `ThreadPoolTaskExecutor` is created with 2 core threads, 4 max threads, and queue 20: when the third task arrives, is a third thread always created? **No; tasks are normally queued before growing beyond the core size.**
5. Three replicas of the application are deployed, each with `@Scheduled` cron 09:00: how many invocations can occur? **Normally each instance triggers once on its own; external coordination is required if business logic demands exactly once across the whole system.**

## 8. Key Takeaways and Official Documentation

- **TaskExecutor / @Async** answers "which resources run the work and how to avoid keeping the caller waiting."
- **TaskScheduler / @Scheduled** answers "when Spring triggers the work."
- The two groups only coordinate when we design them to coordinate; if one scheduled tick can spawn multiple background tasks, you must control queues, errors, overlap, context, and shutdown.
- Start by identifying the goal: event-driven tasks, periodic tasks, or both; then choose separate pools and monitoring policies for each role.

Official documentation: [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html). Details on default executors/schedulers can vary by Spring Framework version, Spring Boot version, and application configuration; the example above explicitly defines both beans to avoid relying on those defaults.
