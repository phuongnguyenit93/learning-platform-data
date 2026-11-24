# Managing Queues, Concurrency Limits, and Errors in Spring Boot Background Tasks

**Scope:** Spring Boot Application Runtime → Threads and Tasks. This lesson focuses on three requirements that must be solved **together** when an application accepts work not executed directly on HTTP request threads: **bounded queues**, **concurrent execution limits**, and **error intake/recording/recovery**. Content covers `ThreadPoolTaskExecutor` mechanics, rejection policies, `@Async` and `CompletableFuture`, backpressure, restart durability, and shutdown. The complete example uses **Java 17+**, **Spring Boot 3.5.x**, and **Spring MVC**.

All commands and responses in the lab section follow a local application; timings, UUIDs, and thread counts in a snapshot may vary by machine. **Complete Maven-buildable code** is kept separate from **advanced design snippets** so a code fragment is not mistaken for a standalone application.

## 1. Learning objectives

After this lesson, learners will be able to:

1. Distinguish `request thread`, worker thread, thread pool, task queue, scheduler, and a job persisted in a database.
2. Explain `corePoolSize`, `maxPoolSize`, `queueCapacity`, `keepAliveSeconds`, `activeCount`, and `poolSize`.
3. Predict when the pool spawns additional threads, enqueues work, and rejects requests on saturation.
4. Design intake bounds rather than using unbounded queues to mask overload.
5. Handle **submission failures (rejection)** differently from **in-worker exceptions**, cancellation, and timeouts.
6. Use `ThreadPoolTaskExecutor.execute(...)` and `TaskRejectedException` to build an HTTP API returning `202 Accepted` or an appropriate overload response.
7. Use `@Async("...")` with `CompletableFuture` when asynchronous interaction via a Spring proxy is needed; state the limits of `void @Async`.
8. Measure pool/queue/accepted/rejected/succeeded/failed instead of relying solely on "started" logs.
9. Understand why a 202 response does not mean the job succeeded and why an in-RAM queue is not a durable queue.
10. Propose shutdown, retry, idempotency, fairness, and backpressure designs for multi-replica applications.

**Key message:** A reliable background task system must have **finite capacity**, **explicit rejection rules**, **observable job state**, **failure recovery mechanisms**, and **shutdown lifecycle handling**. Using `@Async` or `new Thread(...)` alone does not provide these properties.

## 2. Separating three resources: workers, queues, and work sources

For an HTTP API accepting tasks:

~~~text
HTTP client
    |
    | POST /lab/jobs
    v
Controller (Tomcat request thread)
    |
    | validate + submit
    v
ThreadPoolTaskExecutor
    |
    +--- worker running task         <= maxPoolSize
    |
    +--- BlockingQueue waiting turn  <= queueCapacity
    |
    +--- rejection when no space left
    |
    v
Result/state: DONE, FAILED, INTERRUPTED ...
~~~

**Worker threads** are where task code actually executes. The **queue** is where tasks wait when no worker is free. **Work sources** may be HTTP, events, schedulers, Kafka/RabbitMQ consumers, or database jobs. If the source feeds work faster than completion over a sustained period, a backlog must grow somewhere; moving from a JVM queue to a message broker only shifts where the backlog sits without increasing processing capacity.

Suppose a pool has at most **4** threads and a queue of **2** tasks. When all workers are busy and both queue slots are full, a new submission must be rejected, delayed upstream, or trigger valid backpressure. Never let the process accept unbounded requests and hold every `Runnable` in RAM: latency climbs, the heap swells, and GC pressure or `OutOfMemoryError` can follow.

### 2.1. Defining "concurrency" at the right scope

- `maxPoolSize=4` only caps **this specific executor's worker threads** at 4 once the pool has scaled to that point.
- It does **not** cap Tomcat's total concurrent requests, total tasks across all executors, database requests, or all instances in a cluster.
- One job may spawn extra threads or perform multiple async I/O operations; 4 workers therefore does not necessarily mean at most 4 outbound connections to an external service.
- With 3 replicas each running a pool of max 4 threads, the whole cluster can have roughly 12 concurrent workers active if load distributes across all three.
- To limit **concurrency against a single resource** (such as allowing at most 2 concurrent requests to a quota-limited API), you may need a dedicated `Semaphore`/bulkhead around that resource rather than only tuning a general executor.

## 3. ThreadPoolTaskExecutor mechanics and four essential parameters

Spring Framework provides `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`, a configuration wrapper closely aligned with Java's `ThreadPoolExecutor`, implementing `TaskExecutor`, integrating with Spring's lifecycle, and exposing pool-level metrics.

### 3.1. Task acceptance rules

With a pool using a **bounded queue**:

1. If the current worker count is below `corePoolSize`, the executor typically creates a worker to run the new task.
2. Once core workers are busy, a new task is **placed into the queue** if capacity remains.
3. When the queue is full, the executor can create additional workers from core up to `maxPoolSize`.
4. When workers reach max **and** the queue is full, new tasks are **rejected** per the configured handler.
5. Non-core workers can shrink after idling past `keepAliveSeconds`, subject to core timeout settings.

**Common mistake:** thinking `maxPoolSize=32` means the pool immediately expands to 32 once 8 core threads are busy. With a **sufficiently large queue**, the pool continues enqueueing tasks and only increases workers once the queue fills. This is standard `ThreadPoolExecutor` behavior with normal queues.

### 3.2. Parameters

| Parameter | Function | Trade-off |
|---|---|---|
| `corePoolSize` | Core pool size | High core boosts concurrency at the cost of threads/resources |
| `maxPoolSize` | Upper cap on executor workers | Should not exceed CPU, DB pool, or upstream capacity |
| `queueCapacity` | Number of tasks allowed to wait in queue | Overly long queues cause latency and retain heap objects |
| `keepAliveSeconds` | Idle time before non-core workers shrink | Affects thread creation churn under fluctuating load |
| `threadNamePrefix` | Worker name prefix | Helps read thread dumps/logs and attribution |
| `RejectedExecutionHandler` | Behavior when full or shutting down | Mandatory backpressure policy to decide explicitly |
| `waitForTasksToCompleteOnShutdown` | Whether to keep queued tasks on shutdown | Tied to shutdown budget and task durability |
| `awaitTerminationSeconds` | Wait time for executor termination on shutdown | Must align with process-wide termination grace period |

In `ThreadPoolTaskExecutor`, `queueCapacity > 0` creates a `LinkedBlockingQueue` with that capacity; `queueCapacity <= 0` creates a `SynchronousQueue` that stores no waiting tasks. Using `queueCapacity=0` can cause threads to scale eagerly to max; enforce a sensible ceiling. Standalone `ThreadPoolTaskExecutor` defaults to core 1, very large max, and very large queue; do not confuse this class's defaults with those auto-configured by Spring Boot for the application executor. In particular, an unbounded queue can prevent `maxPoolSize` from ever taking effect.

### 3.3. Illustrative decision table

With `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=2`, and **the first six tasks intentionally blocked**:

| Submission | Typical handling | Total accepted tasks |
|---|---|---:|
| Task 1 | Runs on 1st core worker | 1 |
| Task 2 | Runs on 2nd core worker | 2 |
| Task 3 | Enters queue | 3 |
| Task 4 | Enters queue | 4 |
| Task 5 | Queue full, spawns 3rd worker | 5 |
| Task 6 | Spawns 4th worker | 6 |
| Task 7 | Max workers + queue full → rejection | 6 |

This example is engineered so tasks **do not complete before all seven are submitted**. In production, because jobs continuously finish and workers pull from the queue, queued/active counts are fluctuating snapshots. Do not hardcode this table as a rule for all workloads and timings.

## 4. Rejection is a load-control mechanism, not just an exception

`java.util.concurrent.ThreadPoolExecutor` provides notable rejection strategies:

| Policy | When out of space | Risk |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException`; Spring `ThreadPoolTaskExecutor` surfaces `TaskRejectedException` per TaskExecutor contract | Caller must handle it to avoid an opaque 500 |
| `CallerRunsPolicy` | Runs the task on the submitting thread if the executor is still active | HTTP request threads can be held for long durations, starving the request pool |
| `DiscardPolicy` | Drops the task without executing | Silent work loss; very dangerous for business logic |
| `DiscardOldestPolicy` | Drops the oldest queued task and retries | Loses older tasks, breaks ordering, hard to audit |

For an intake API where silent loss is unacceptable, the lab chooses **AbortPolicy** and maps rejection to HTTP **429 Too Many Requests** with a clear message and client retry policy. In real systems, if the executor is shutting down, HTTP **503 Service Unavailable** and readiness state may fit better than 429. Do not conflate these two rejection causes if gateways/clients decide retries by status code.

**Do not default to CallerRunsPolicy just to "never reject".** When a task performs long I/O, it can run directly on a Tomcat thread, turning async HTTP submission into synchronous execution and exhausting request threads; it is a form of backpressure, but only safe when deliberately chosen, measured, and timeout-bounded.

## 5. Sample application with bounded queue, status tracking, and saturation test

### 5.1. Create the project

Create the project with Spring Initializr:

- Build: **Maven**, Language: **Java**, Java: **17+**.
- Spring Boot: **3.5.x**, packaging **Jar**.
- Group: `com.example`, Artifact: `bounded-worker-lab`.
- Package: `com.example.boundedworker`.
- Dependency: **Spring Web** (Actuator is optional for the basic lab).

Keep the `pom.xml` and Maven Wrapper generated by Initializr. Files:

~~~text
bounded-worker-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/boundedworker/
    BoundedWorkerApplication.java
    WorkerExecutorConfiguration.java
    JobService.java
    JobController.java
  src/main/resources/application.properties
~~~

Place public classes in matching filenames and the correct package. The Maven classpath is needed to compile because `ThreadPoolTaskExecutor` and Spring MVC are external dependencies outside the JDK. A bare `javac` command on one file is insufficient; use `./mvnw spring-boot:run` or build the JAR.

### 5.2. Main class

File `BoundedWorkerApplication.java`:

~~~java
package com.example.boundedworker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundedWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundedWorkerApplication.class, args);
    }
}
~~~

`@EnableAsync` is not needed because the main lab **submits directly** to the executor via `execute(...)`. `@EnableAsync` is only needed when choosing the `@Async` mechanism in the extension section.

### 5.3. Declaring ThreadPoolTaskExecutor with explicit bounds

File `WorkerExecutorConfiguration.java`:

~~~java
package com.example.boundedworker;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class WorkerExecutorConfiguration {

    @Bean("boundedWorkerExecutor")
    public ThreadPoolTaskExecutor boundedWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(2);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("lab-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        // When Spring manages @Bean, it invokes the init lifecycle.
        // No need to call executor.initialize() manually here.
        executor.setWaitForTasksToCompleteOnShutdown(false);
        executor.setAwaitTerminationSeconds(10);

        return executor;
    }
}
~~~

**Explanation:**

- Four workers is the concurrency cap **specifically for bean** `boundedWorkerExecutor`.
- The queue holds at most two waiting `Runnable` tasks.
- `AbortPolicy` lets the API detect when the executor cannot accept tasks.
- `setWaitForTasksToCompleteOnShutdown(false)` does not promise keeping all queued tasks on shutdown; unfinished tasks may be interrupted/canceled. `setAwaitTerminationSeconds(10)` is the executor shutdown wait timeout, **not** data durability.
- `ThreadPoolTaskExecutor` is a Spring bean with an initialization/shutdown lifecycle; **do not call `initialize()` manually inside `@Bean` and let Spring initialize it again**, as that can yield unintended executor state.
- Spring Boot may alter task executor auto-configuration when an application defines its own `Executor` bean. This lesson always injects the exact `boundedWorkerExecutor` bean via `@Qualifier`, making no assumption about whether it replaces `applicationTaskExecutor` used by Spring MVC.
- Do not blindly use this single pool for all application work; name and separate work classes with different resource profiles.

### 5.4. JobService: distinguishing QUEUED, RUNNING, DONE, FAILED, and REJECTED

File `JobService.java`:

~~~java
package com.example.boundedworker;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class JobService {

    private final ThreadPoolTaskExecutor executor;
    private final ConcurrentMap<String, JobView> jobs =
            new ConcurrentHashMap<>();
    private final CountDownLatch releaseGate =
            new CountDownLatch(1);

    private final AtomicInteger accepted = new AtomicInteger();
    private final AtomicInteger rejected = new AtomicInteger();
    private final AtomicInteger succeeded = new AtomicInteger();
    private final AtomicInteger failed = new AtomicInteger();
    private final AtomicInteger interrupted = new AtomicInteger();

    public JobService(
            @Qualifier("boundedWorkerExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public Submission submit(String kind) {
        String id = UUID.randomUUID().toString();
        jobs.put(id, new JobView(id, kind, "QUEUED", "waiting"));

        try {
            executor.execute(() -> runJob(id, kind));
            accepted.incrementAndGet();
            System.out.println("LAB_SUBMITTED id=" + id
                    + " kind=" + kind);
            return new Submission(id, "ACCEPTED");
        } catch (TaskRejectedException ex) {
            rejected.incrementAndGet();
            jobs.put(id, new JobView(
                    id, kind, "REJECTED",
                    "executor saturated or shutting down"));
            System.out.println("LAB_REJECTED id=" + id);
            return new Submission(id, "REJECTED");
        }
    }

    private void runJob(String id, String kind) {
        String thread = Thread.currentThread().getName();
        jobs.put(id, new JobView(id, kind, "RUNNING", thread));
        System.out.println("LAB_RUNNING id=" + id
                + " thread=" + thread);

        try {
            switch (kind) {
                case "block" -> {
                    if (!releaseGate.await(120, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "LAB_BLOCK_WAIT_TIMEOUT");
                    }
                }
                case "fail" -> throw new IllegalStateException(
                        "LAB_INTENTIONAL_WORKER_FAILURE");
                default -> Thread.sleep(300);
            }

            succeeded.incrementAndGet();
            jobs.put(id, new JobView(id, kind, "DONE", thread));
            System.out.println("LAB_DONE id=" + id);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            interrupted.incrementAndGet();
            jobs.put(id, new JobView(
                    id, kind, "INTERRUPTED", thread));
            System.out.println("LAB_INTERRUPTED id=" + id);
        } catch (Exception ex) {
            failed.incrementAndGet();
            jobs.put(id, new JobView(
                    id, kind, "FAILED", ex.getMessage()));
            System.out.println("LAB_FAILED id=" + id
                    + " cause=" + ex.getMessage());
        }
    }

    public void releaseBlockedJobs() {
        releaseGate.countDown();
    }

    public JobView find(String id) {
        return jobs.get(id);
    }

    public Stats stats() {
        ThreadPoolExecutor pool = executor.getThreadPoolExecutor();
        return new Stats(
                executor.getPoolSize(),
                executor.getActiveCount(),
                pool.getQueue().size(),
                pool.getQueue().remainingCapacity(),
                accepted.get(),
                rejected.get(),
                succeeded.get(),
                failed.get(),
                interrupted.get());
    }

    public record Submission(String id, String state) {
    }

    public record JobView(
            String id, String kind, String state, String detail) {
    }

    public record Stats(
            int poolSize,
            int active,
            int queued,
            int queueRemaining,
            int accepted,
            int rejected,
            int succeeded,
            int failed,
            int interrupted) {
    }
}
~~~

**Design decisions in the lab:**

1. `executor.execute(...)` submits the task without **waiting** for completion. If accepted, the API returns `ACCEPTED`; if the queue and workers are full, `TaskRejectedException` is caught immediately on the **submitting thread**.
2. `JobView` is stored in `ConcurrentHashMap` with states `QUEUED` → `RUNNING` → `DONE`/`FAILED`/`INTERRUPTED`. Rejection produces `REJECTED` and the task does not run.
3. `"block"` uses `CountDownLatch.await(120, TimeUnit.SECONDS)` to hold workers in the lab; the release endpoint lets them finish. This is a **controlled load-testing tool**, not a business queue pattern.
4. `"fail"` throws `IllegalStateException` inside the worker. `runJob` catches it and records `FAILED`, so the HTTP response at submit time can still be `202 Accepted`. **Never** equate accepted with succeeded.
5. `InterruptedException` has dedicated handling, restoring the interrupt flag via `Thread.currentThread().interrupt()` and recording `INTERRUPTED`; never use a catch-all to swallow shutdown signals.
6. `getPoolSize()`, `getActiveCount()`, and `getThreadPoolExecutor().getQueue().size()` are snapshot metrics; they can change between reads and do not form an atomic transaction.
7. Counters for accepted/rejected/succeeded/failed/interrupted are strictly observational. When workers run very fast, `succeeded` can increment before the submitting thread increments `accepted`, producing momentary snapshot skew; never treat that delta as an instant invariant.
8. `ConcurrentHashMap` stores all submitted jobs **with no size limit or TTL in the lab**. Production must define retention, cleanup, persistent job stores, memory/size bounds, and restart recovery. A bounded pool does **not** automatically make the job registry bounded.

### 5.5. Controller receiving work and reporting backpressure via HTTP

File `JobController.java`:

~~~java
package com.example.boundedworker;

import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class JobController {

    private static final Set<String> VALID_KINDS =
            Set.of("quick", "block", "fail");

    private final JobService service;

    public JobController(JobService service) {
        this.service = service;
    }

    @PostMapping("/lab/jobs")
    public ResponseEntity<?> submit(
            @RequestParam(defaultValue = "quick") String kind) {

        if (!VALID_KINDS.contains(kind)) {
            return ResponseEntity.badRequest().body(
                    Map.of("error",
                            "kind must be quick, block, or fail"));
        }

        JobService.Submission submission = service.submit(kind);

        if (submission.state().equals("REJECTED")) {
            return ResponseEntity.status(
                    HttpStatus.TOO_MANY_REQUESTS).body(submission);
        }
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(submission);
    }

    @GetMapping("/lab/jobs/{id}")
    public ResponseEntity<?> find(@PathVariable String id) {
        JobService.JobView job = service.find(id);

        if (job == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("error", "unknown job id"));
        }
        return ResponseEntity.ok(job);
    }

    @GetMapping("/lab/stats")
    public JobService.Stats stats() {
        return service.stats();
    }

    @PostMapping("/lab/release")
    public Map<String, Boolean> release() {
        service.releaseBlockedJobs();
        return Map.of("released", true);
    }
}
~~~

With the application running and controllers unrestricted by security:

- `POST /lab/jobs?kind=quick` → HTTP 202 if the executor accepts the task.
- `POST /lab/jobs?kind=block` → HTTP 202 if space exists; the task waits on the latch.
- `POST /lab/jobs?kind=fail` → HTTP 202 when accepted, then transitions to `FAILED`.
- When the pool is full: HTTP **429** with JSON `state=REJECTED`. In production you can add `Retry-After` based on grounded recovery capacity rather than guessing arbitrarily.
- `GET /lab/jobs/{id}` → specific job status.
- `GET /lab/stats` → executor metrics and counters.
- `POST /lab/release` → opens the latch **once** for blocked jobs; afterward the latch cannot be reset. Restart the app to repeat the saturation test.

**Security:** This is a test API with no auth/rate limiting. `POST /lab/release` and job kinds that intentionally fail/block must **not exist** on a production public API. Enforce body/size/tenant/token limits on real APIs.

### 5.6. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=bounded-worker-lab
server.address=127.0.0.1
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

`server.address=127.0.0.1` keeps the lab on loopback. In Pods/containers, configure proper network binding; do not copy localhost settings verbatim to Kubernetes when kubelet or ingress must connect from another network interface.

## 6. Running the application and verifying job completion

### 6.1. Maven Wrapper

Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

Maven compiles classes and starts Tomcat. If port 8080 is occupied, stop the existing service or change the port and curl URLs accordingly. Once Spring Boot finishes starting, test in a second terminal:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=quick"
curl -i "http://127.0.0.1:8080/lab/stats"
~~~

Typical submit response:

~~~json
{"id":"<actual-UUID>","state":"ACCEPTED"}
~~~

`<actual-UUID>` is a **placeholder denoting a varying value in the description**, not a literal ID returned by the API; the real response contains a concrete UUID v4. Copy the returned ID, such as `b2e2c77c-6ef3-4554-9221-69831a9c1141` if your logs show that ID. This is only a **format example**, not a measured run output.

Continue:

~~~bash
curl -i "http://127.0.0.1:8080/lab/jobs/<actual-UUID>"
~~~

Replace the `<...>` part with the actual ID **before running the command**; do not pass raw placeholder symbols through the shell. The job may be `QUEUED` or `RUNNING` if queried right away; a few hundred milliseconds later it will reach `state=DONE` under normal machine conditions. `HTTP 202` only confirms **acceptance into the executor**, not job completion.

### 6.2. Markers in logs

Concise logs for a job show markers like:

~~~text
LAB_SUBMITTED id=<id> kind=quick
LAB_RUNNING id=<id> thread=lab-worker-1
LAB_DONE id=<id>
~~~

**Do not assume a strict ordering** between `LAB_SUBMITTED` and `LAB_RUNNING`: the worker can start running before the request thread finishes logging "submitted" because those are two independent threads. What must hold is that a job never reaches `DONE`/`FAILED` unless the executor accepted and ran it.

Worker name `lab-worker-1` is also illustrative; in practice it may be `lab-worker-2`, `lab-worker-3`, etc. depending on thread allocation.

## 7. Saturation test: 6 accepted, 7th request rejected

In a **freshly started JVM**, before calling `/lab/release`, submit seven `block` jobs consecutively. They wait on the latch for up to 120 seconds; run these steps within that window to preserve test conditions.

On Linux/macOS:

~~~bash
for i in 1 2 3 4 5 6 7; do
  curl -s -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=block"
done
curl -s "http://127.0.0.1:8080/lab/stats"
~~~

On Windows PowerShell:

~~~powershell
1..7 | ForEach-Object {
    curl.exe -s -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=block"
}
curl.exe -s "http://127.0.0.1:8080/lab/stats"
~~~

While the jobs have neither timed out nor been released, expect:

- Six HTTP **202 Accepted** responses with distinct UUIDs.
- The seventh response as HTTP **429 Too Many Requests**, body containing `state=REJECTED`.
- `poolSize` likely **4**, `active` **4**, `queued` **2**, `queueRemaining` **0**.
- `accepted` around **6**, `rejected` **1**, `succeeded` **0** for the blocked jobs.
- Four `LAB_RUNNING` lines from worker threads, and two jobs still in `QUEUED`.
- `LAB_REJECTED` logging the rejected job's ID; that job is not executed.

This experiment deliberately blocks tasks. If tasks finish, time out, or the environment stalls too long between commands, snapshot numbers may differ. Restart the JVM to reset the latch and counters if you need to reproduce the exact table.

### 7.1. Opening the latch and observing queue drain

In the second terminal:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/release"
curl -i "http://127.0.0.1:8080/lab/stats"
~~~

Right after release, the four blocked workers proceed to `DONE`; the two queued tasks are dequeued in turn and complete. Call `/lab/stats` again once logs show six `LAB_DONE` markers to see `queued=0`, `active=0`, and `succeeded=6` across the seven submissions. The pool may keep `poolSize=4` for a while due to keep-alive; do not confuse "thread still alive in pool" with "thread actively running a task".

The rejected job's `JobView` stays `REJECTED`. Once the pool frees up, it **does not automatically catch up** without explicit retry/re-enqueue logic. In production, clients must be notified of rejection and apply retry with backoff or submit into a durable system.

### 7.2. Notable properties

The peak in-flight load held by the executor in the example may be **4 running tasks + 2 queued tasks**, yet `ConcurrentHashMap jobs` and request payloads still consume additional memory. Thus capping concurrency does not mean total memory footprint is bounded; you must also bound payload sizes, retained job records, request rates, and users/tenants.

When a job blocks on I/O or holds a connection, it still occupies a worker even while idle on CPU. That is why capacity planning differs between I/O-bound and CPU-bound tasks.

## 8. Two kinds of errors must be handled at two boundaries

### 8.1. First error: unable to submit

In `JobService.submit(...)`:

~~~java
try {
    executor.execute(() -> runJob(id, kind));
    return new Submission(id, "ACCEPTED");
} catch (TaskRejectedException ex) {
    return new Submission(id, "REJECTED");
}
~~~

This snippet is an abridged version; the runnable class in section 5 contains full counters and state transitions. When the pool is full or shutting down under AbortPolicy, the executor reports rejection **synchronously to the submitting thread**. At the HTTP boundary, return 429 or 503 per policy and let the client handle the outcome.

Never retry infinitely inside a controller with `while(true)`: when a pool is full, immediate retries burn CPU and add latency without adding capacity. Use backoff/jitter and deadlines. If critical work cannot be rejected, route it through a durable queue/DB transaction with clear capacity and operations rather than dropping silently.

### 8.2. Second error: task ran and failed

Submit an intentionally failing job when the pool is idle:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=fail"
~~~

The response is still typically **202 Accepted** with an ID. Afterward:

~~~bash
curl -i "http://127.0.0.1:8080/lab/jobs/<actual-ID>"
~~~

Substitute the actual ID in the curl command. Once the worker runs, the body has `state="FAILED"` and `detail="LAB_INTENTIONAL_WORKER_FAILURE"`. Console output shows:

~~~text
LAB_FAILED id=<id> cause=LAB_INTENTIONAL_WORKER_FAILURE
~~~

The failure happens **after** the executor accepted the task, so the submission HTTP handler cannot catch it with a `catch` around `execute(...)` as if it were synchronous. `JobService.runJob(...)` must catch it and record state; an alternative is `submit(Callable)` returning a `Future` so an observer thread reads `ExecutionException` from `Future.get()`.

**Distinction:** `202 Accepted` is not `200 completed`. A well-designed API returns `jobId` and offers status queries, bounded polling, or reliable callbacks/webhooks; never return fake success results while a job has not run.

### 8.3. Third error: cancellation / interrupt / timeout

When a worker waits on `CountDownLatch.await(...)` and the context shuts down or the task is canceled with interruption, `InterruptedException` signals an interrupt request. The sample code:

- Calls `Thread.currentThread().interrupt()` to restore the interrupt flag.
- Records `INTERRUPTED` status separately from business errors.
- Does not continue working as if nothing happened.
- Does not hold locks or skip cleanup when resources must stop.

Timing out the latch wait after 120 seconds marks the job `FAILED` with marker `LAB_BLOCK_WAIT_TIMEOUT`. This is a **task-controlled timeout**, distinct from Tomcat's request timeout and `awaitTerminationSeconds` at shutdown. A long-running task is not automatically killed by the executor merely because the queue capacity is small.

In production, establish **end-to-end deadlines** for jobs, timeouts on DB/HTTP/broker calls, circuit breakers/bulkheads, cancellation policies, and `finally` cleanup.

## 9. @Async and CompletableFuture: different mechanism, same bounding problem

Spring supports calling `@Async` methods through an AOP proxy to offload work to a `TaskExecutor`. This syntax is concise, yet **does not eliminate** the need for bounded pools, rejection handling, exception handling, and context propagation.

### 9.1. Optional extension you can add to the project

Add `@EnableAsync` on the main class:

~~~java
@SpringBootApplication
@EnableAsync
public class BoundedWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundedWorkerApplication.class, args);
    }
}
~~~

This is a **replacement snippet for the main class** in the same package as section 5; add `import org.springframework.scheduling.annotation.EnableAsync;`. Do not keep two duplicate `BoundedWorkerApplication` classes in the project.

Create a new bean:

~~~java
package com.example.boundedworker;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncReportService {

    @Async("boundedWorkerExecutor")
    public CompletableFuture<String> generate(String id) {
        if ("fail".equals(id)) {
            throw new IllegalStateException("LAB_ASYNC_FAILURE");
        }
        return CompletableFuture.completedFuture("report-" + id);
    }
}
~~~

The snippet above is a **complete Java file once `@EnableAsync` is enabled** and placed in the right package/classpath. `@Async("boundedWorkerExecutor")` explicitly selects the executor without relying on default bean names or Spring Boot auto-configuring `applicationTaskExecutor`.

**Another** bean calling `asyncReportService.generate("x")` receives a `CompletableFuture`. If the method throws in the worker, the future completes exceptionally; calling code can use `whenComplete(...)`, `exceptionally(...)`, `handle(...)`, or `join()` to observe and handle it. When `join()` encounters an error, it typically throws `CompletionException` wrapping the cause.

**Critical warnings:**

- Calling `this.generate("x")` from the **same bean** normally bypasses the Spring proxy, so `@Async` is not applied in default proxy mode.
- `private` methods or instances created manually with `new` are not guaranteed to be AOP-intercepted.
- `@Async` on a `void` method returns no future to the caller; exceptions cannot propagate via a future and may only be logged by `AsyncUncaughtExceptionHandler`. If auditing/retries are needed, **prefer returning a future or having the service persist job state**.
- `@Async` submissions can also be rejected by the executor right at proxy dispatch; callers must handle the rejection path separately, not only `future.exceptionally(...)`.
- If a future is returned directly from an HTTP controller without designing a proper async API, do not assume the JSON response represents the job result. Choose a 202 + ID contract or an appropriate Spring MVC async response.
- Do not share an overly small executor across both HTTP async handling and heavy background jobs if they can starve each other.

### 9.2. Why does void @Async easily lose errors?

Snippet example:

~~~java
@Async("boundedWorkerExecutor")
public void sendNotification() {
    throw new IllegalStateException("notification failed");
}
~~~

Without a `Future`, the caller cannot `join/get` to retrieve this exception; Spring uses an uncaught exception handler for `void @Async`, which by default typically logs it. For stricter policies, configure `AsyncConfigurer.getAsyncUncaughtExceptionHandler()` along with metrics/alerts. Still, a logged error **does not** mean the job was retried, sent to a DLQ, or marked failed in a durable store.

### 9.3. Spring Boot auto-configured executor and properties

Spring Boot 3.5 includes task execution auto-configuration. Without a custom `Executor` bean, Boot may supply `AsyncTaskExecutor`; with platform threads, this is typically `ThreadPoolTaskExecutor`. On Java 21+ with virtual threads enabled, executor choice and the effect of pool properties change. Because the lab names its own executor and injects it explicitly with `@Qualifier`, it does not rely on that default selection.

The following properties **target the Boot auto-configured executor**, and do not automatically alter the manually created `boundedWorkerExecutor` bean from section 5:

~~~properties
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=100
spring.task.execution.pool.keep-alive=30s
~~~

Do not add them to the lab's `application.properties` thinking they override `setCorePoolSize(2)` in code. To configure a custom bean from properties, use `@ConfigurationProperties` or `@Value`/builders bound to that exact instance, with validation constraints.

In Spring Boot 3.5, registering a custom `Executor` can cause auto-configuration to back off; Spring MVC/WebFlux/GraphQL async integrations have specific expectations for the `applicationTaskExecutor` bean. If you need both an isolated business pool and the default framework executor, investigate `@Bean(defaultCandidate=false)` (corresponding Boot 3.5/Spring Framework 6.2), `spring.task.execution.mode=force`, or declaring the appropriate executor. Never alter application-wide mechanics solely to serve one business queue.

## 10. Background tasks are a load-throttling system, not just an Executor

### 10.1. Estimating capacity

A rough estimation rule using **Little's Law**:

\[
L = \lambda \times W
\]

Where `L` is the average number of items in the system, `\lambda` is the arrival rate per second, and `W` is the average wait + processing time. At 10 jobs/s and 0.8 s average time in the system, roughly 8 jobs are outstanding on average in steady state. This is an **estimate**, not a direct formula for choosing queue capacity or thread ceilings. You must measure tail latency, burstiness, memory per job, retries, and downstream pool limits.

For CPU-bound work, too many workers cause context switching; for blocking I/O, worker counts can exceed core counts while still respecting database connection pools, API rate limits, and timeouts. Use load tests reflecting real workloads to choose `core/max/queue` and SLOs.

### 10.2. Semaphore to cap resources narrower than the pool

Suppose an executor has 4 threads yet a partner allows at most 2 concurrent requests. You can guard partner calls with `Semaphore(2)`:

~~~java
private final Semaphore gatewayPermits = new Semaphore(2);

public void callGateway() throws InterruptedException {
    if (!gatewayPermits.tryAcquire(2, TimeUnit.SECONDS)) {
        throw new IllegalStateException("gateway overloaded");
    }
    try {
        invokeExternalGatewayWithTimeout();
    } finally {
        gatewayPermits.release();
    }
}
~~~

**This is a design snippet**, requiring imports for `Semaphore`/`TimeUnit`, a definition of `invokeExternalGatewayWithTimeout()`, and appropriate bean/scope setup. A semaphore caps **how many threads enter a critical section in one instance**; it does not enforce a cluster-wide quota. Use `tryAcquire` with a deadline rather than blocking every worker indefinitely; otherwise the semaphore itself becomes a hidden queue exhausting the pool.

### 10.3. Rate limit vs. concurrency limit

- **Rate limit** caps requests/jobs **per unit of time**, e.g. 100/s.
- **Concurrency limit** caps work **at the same instant**, e.g. 4.
- **Queue capacity** caps work **accepted and still waiting**.
- **Timeout** caps how long a single wait or execution may take.
- **Backpressure** signals sources to slow down, retry with control, or reject.

A system handling 10,000 ultra-fast tasks per second may not violate concurrency=4 yet still overwhelm DB networking. Conversely, 4 requests hanging for 10 minutes can occupy the entire pool despite low throughput. Combine limits rather than applying one knob to every problem.

## 11. Retry, DLQ, and idempotency

When a job fails, you cannot simply write `catch (Exception e) { executor.execute(task); }` and retry forever:

1. Permanent errors (bad data, business rule violations) will keep failing.
2. Immediate retries trigger a "retry storm", filling queues and starving new jobs.
3. If a side effect partially succeeded before failing to record state, retrying can send duplicate emails, double-charge, or double-write.
4. On JVM restart, in-RAM queues and the example registry vanish; `ThreadPoolTaskExecutor` is not a durable broker.
5. Exceptions from shutdown/interruption need different handling than transient connection errors.

A production design should specify:

- A stable **idempotency key** for the same business job, e.g. `(tenantId, orderId, operationType)` or a stable event ID.
- **Retry taxonomy:** transient, permanent, canceled, timeout; bound attempt counts.
- **Delay:** exponential backoff with jitter; avoid long `Thread.sleep` directly on scarce workers when a delayed queue/scheduler fits better.
- **Visibility timeout/ack:** when using a broker, define when acks happen, when redelivery triggers, and who owns state.
- **DLQ/quarantine:** jobs exceeding retry thresholds are retained for investigation rather than dropped.
- **Outbox/inbox:** handle atomically with the database when persisting state and publishing related events.
- **Compensation:** if external side effects cannot share a transaction, define recovery/compensation and use the provider's idempotency contract.

For critical job-submission APIs, **never return 202 before durable persistence** if the business requirement is "accepted and must not be lost on crash". In the lab, `202` only means the executor accepted into RAM. When production contracts demand durability, write the job to a database/queue with durable confirmation **before** returning 202, then let workers consume it.

## 12. Shutdown and background task lifecycle

When Spring Boot receives a normal shutdown, the context closes and managed executors are handled per lifecycle. Two common choices:

| Policy | Meaning | When to use |
|---|---|---|
| Wait for queue and tasks (`waitForTasksToCompleteOnShutdown=true`) | Gives accepted tasks a chance to finish, though may prolong shutdown | Bounded tasks, clear timeouts, sufficient termination budget |
| Do not wait for all queued tasks (`false`) | Allows interrupting/canceling per shutdown mechanics | Jobs live in a durable source and can be redelivered |
| `awaitTerminationSeconds` | How long the framework waits for executor termination | Must align with shutdown phases and platform grace period |
| Graceful HTTP shutdown | Stops new requests, drains in-flight requests per server | Ensures intake stops before workers are disposed |

**Important:** `server.shutdown=graceful` applies to the web server; it does not make RAM queues durable. `spring.lifecycle.timeout-per-shutdown-phase` bounds a shutdown phase, distinct from an executor's `awaitTerminationSeconds` and Kubernetes `terminationGracePeriodSeconds`. If tasks block on I/O without timeouts or ignore interrupts, shutdown can still time out.

In the lab, `CountDownLatch.await(...)` is timeout-bounded and responds to interrupts; if blocked jobs remain at shutdown, their state may become `INTERRUPTED` before the JVM exits. Because the registry lives in RAM, never claim those states remain queryable after process death.

**Recommended operational flow:**

1. Stop new submission intake via readiness/gateway or contract admission control.
2. Stop consuming new messages in broker consumers while preserving valid ack/redelivery.
3. Let queued/running jobs finish or cancel by deadline; persist durable state/acks.
4. Close connections/executors in the proper phase, handling cleanup errors.
5. Observe canceled counts, pending retries, and lost work before spinning up replacement instances.

Avoid `kill -9` to "test graceful": SIGKILL does not guarantee shutdown hooks or callbacks run.

## 13. Logging, metrics, and alerting

Checking `poolSize=4` alone is not enough to assess system health. Observe over time:

| Metric/signal | Meaning | Alert when |
|---|---|---|
| `activeCount` | Threads actively running tasks | Sustained near max |
| `poolSize` | Current worker thread count | Oscillating abnormally or unexpectedly low |
| `queue.size` | Tasks waiting | Growing steadily or frequently full |
| `queue.remainingCapacity` | Free queue slots | Near 0 across multiple intervals |
| Rejection count/rate | Work not accepted | Exceeding budget or spiking |
| Queue waiting time | Submit → start duration | p95/p99 exceeds SLA |
| Execution duration | Worker runtime | p95/p99 climbing, tasks hanging |
| Success/fail/interrupt/cancel | Actual job outcomes | High failure rate or missing recovery |
| Retry attempts / DLQ size | Repeatedly failing workload | Backlog growing out of control |
| Memory/GC, DB pool, external latency | Indirectly constrained resources | Pool/queue looks small yet dependencies bottleneck |

`ThreadPoolTaskExecutor` exposes `getActiveCount()` and `getPoolSize()`, sufficient for the lab. In production, use Spring Boot Actuator/Micrometer to instrument executor/job metrics; whether a specific metric is recorded **depends on instrumentation configuration**, so never assume every custom executor appears in dashboards without verifying.

An event log should record job ID, kind, submit time, start time, finish time, status, duration, attempt number, thread name, idempotency key, and correlation ID. Avoid logging full payloads containing secrets/PII. Never retain references to `HttpServletRequest` or request-scoped beans inside a `Runnable` after the request finishes.

### 13.1. Context propagation and thread-locals

Threads in a pool can be **reused** across different jobs. Therefore:

- MDC/trace context, locale, tenant, transactions, and Spring Security context do not automatically follow across thread hops.
- Never assume an HTTP caller's `@Transactional` "wraps" work on a worker thread. Define an independent transaction on the worker-executed method if needed.
- When copying context, use a `TaskDecorator` or framework-supported context propagation scoped accurately; **clear ThreadLocals in `finally`** to avoid cross-request leaks.
- Never copy passwords/tokens or broader SecurityContexts than necessary; prefer passing validated business identifiers and enforcing authorization at boundaries.
- When jobs must retry after restart, persist trace/tenant/user identity meaningfully in durable job metadata rather than relying on transient ThreadLocals.

## 14. Scheduled tasks and other executor types

`@Scheduled` can be driven by `TaskScheduler`; `spring.task.scheduling.*` properties are not the same as `spring.task.execution.*`. If a scheduled job continuously spawns background tasks, throttle its submission rate; a single-threaded scheduler does not stop an underlying executor's queue from saturating.

Java's `Executors.newFixedThreadPool(n)` uses an unbounded backing queue by default; a fixed thread count does not mean memory backlog is bounded. `newCachedThreadPool()` can spawn excessive threads when requests block concurrently, so bounds are still required.

With **Java 21+ virtual threads**, virtual thread count is not a quota for databases, networks, or CPU. Virtual threads reduce thread-per-task overhead in many blocking cases, yet **do not replace** concurrency limits to external resources, backpressure, request budgets, and durable job handling.

If choosing a broker instead of an in-RAM thread pool, still configure consumer concurrency, prefetch/in-flight limits, ack policies, retries, DLQs, and quotas. A broker does not automatically make a redelivered non-idempotent task safe.

## 15. Quick diagnosis of common failures

| Symptom | Hypothesis | How to inspect |
|---|---|---|
| Set max=32 yet active stays around core=2 | Queue not full or overly large | Check `queueCapacity`, `queue.size`, and saturation timing |
| App OOMs despite only 2 workers | Queue or job registry retaining too many objects | Heap histogram, queue size, payload size, retention |
| Submit returns 500 when pool saturates | Rejection not mapped to an HTTP response | Catch `TaskRejectedException` at submission boundary |
| HTTP 202 yet job hasn't run | Task is waiting in queue | Query `QUEUED` state and queue metrics |
| HTTP 202 then job fails | Exception inside worker | Record FAILED state, error category, retry policy |
| `@Async` method still runs synchronously | Self-invocation in same bean, bypassed proxy, missing `@EnableAsync` | Verify proxy invocation and Spring-managed bean |
| `void @Async` fails unseen by caller | No Future/observability | Async exception handler or return CompletableFuture |
| `CallerRunsPolicy` causes sudden HTTP slowdowns | Runnable executing on request thread | Check thread names and pool rejection policy |
| Job processed twice after retry | Missing idempotency key/dedupe | Check business ID, durable inbox, provider idempotency |
| Shutdown loses queued work | RAM queue and policy neither waits nor persists | Use durable store or accept explicit at-most-once |
| Job never stops | Blocking I/O without timeouts or ignoring interrupts | Thread dump, deadlines, graceful shutdown budget |
| Queue metrics low yet requests slow | Workers/DB pool/upstream bottlenecked | Measure end-to-end latency, DB pool, external quotas |
| Multiple replicas exceed upstream quota | Limit is per-JVM only | Total concurrency and distributed bulkhead |
| Job stuck RUNNING after process crash | In-memory state or missing lease expiry | Durable job lease/heartbeat, redelivery protocol |
| Empty queue yet executor rejects | Executor shutting down or broken pool lifecycle | Lifecycle logs, shutdown state, exception type |
| Calling `Future.get()` in HTTP request times out | Turned async into blocking wait | Use 202 + status, or MVC async response with valid timeout |

## 16. Hands-on exercises and acceptance criteria

### Exercise A — Normal job

Run the lab, POST `kind=quick`, note the actual ID, and GET status until `DONE`. Verify `accepted` increments on submission and `succeeded` increments when the task finishes. Distinguish 202 Accepted from DONE state.

### Exercise B — Executor saturation

Restart the app so the latch is unreleased. Send 7 rapid `kind=block` POSTs within 120 seconds. Confirm 6 accepted and 1 rejected matching `core=2, max=4, queue=2` and the active/queued snapshot. Call `/lab/release` and wait for queue drain. Do not guess outcomes if jobs already timed out before submissions finished.

### Exercise C — Worker exception

When the pool is idle, POST `kind=fail`. Observe HTTP 202 first and `FAILED` status afterward, with marker `LAB_INTENTIONAL_WORKER_FAILURE`. Explain why a `catch` around `execute(...)` does not catch exceptions inside the worker unless tasks handle them or futures receive exceptions.

### Exercise D — Rejection policy

In a copy of the lab, compare `AbortPolicy` against `CallerRunsPolicy` on the same blocking workload. Observe response latency and executing thread names when submissions overload the pool. **Never** use policies that silently drop real jobs. Restore AbortPolicy after the experiment.

### Exercise E — Resource control

Suppose an upstream permits only 2 concurrent connections while the pool max is 4. Propose `Semaphore(2)`, acquire deadlines, reject/timeout metrics, and retry policy. Compute total concurrency across 3 replicas; describe protecting the upstream if the quota is cluster-wide.

### Exercise F — Crash durability

Evaluate: after the HTTP API returns 202 while the job still sits in the RAM queue, the JVM is forcibly killed. Is the job recovered? In the lab, **there is no guarantee**. Design a DB table or broker with ack + retry + idempotency key, returning 202 only after durable persistence per business contract.

### Verification table

| Experiment | Evidence to keep | Conclusion |
|---|---|---|
| Quick task | 202, UUID, eventually DONE | Submit differs from completion |
| Saturation | 6 accepted, 1 rejected, full queue | Bounded capacity and rejection |
| Release | Queue drops, succeeded rises | Workers keep draining tasks from queue |
| Intentional fail | 202 then FAILED | In-worker errors differ from submission errors |
| Shutdown | Interrupt/stop logs depending on timing | RAM queues do not survive process death |
| Async proxy | Caller receives Future and sees exception | `@Async` exception path |
| Retry/durability design | Idempotency key, ack/inbox/outbox | Ready for at-least-once delivery |

### Final checklist

- [ ] Correctly interpret `corePoolSize`, `maxPoolSize`, and `queueCapacity`.
- [ ] Explain why large queues prevent pools from scaling early to max.
- [ ] Know where to catch `TaskRejectedException`.
- [ ] Distinguish QUEUED/RUNNING/DONE/FAILED/REJECTED/INTERRUPTED.
- [ ] Run the Java 17/Spring Boot 3.5.x Maven project.
- [ ] Verify HTTP 202 does not mean job success.
- [ ] Reproduce saturation with 7 `kind=block` POSTs.
- [ ] Inspect queue/active/pool and know snapshots are fluctuating values.
- [ ] Prove worker exceptions are not caught by the submission handler.
- [ ] Understand `@Async` proxies and catching exceptions via CompletableFuture.
- [ ] Point out differences between RAM queues and durable job stores.
- [ ] Configure concurrency limits, timeouts, and retries with idempotency.
- [ ] Describe clean shutdown and why interruption/cleanup are needed.
- [ ] Have metrics and alerts for rejections, backlog, failures, and latency.

## 17. Official documentation

1. Spring Framework 6.2 — Task Execution and Scheduling, `@Async`, and exception management: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
2. Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc, queue capacity, and metrics: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
3. Spring Framework — `TaskRejectedException`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskRejectedException.html
4. Spring Boot 3.5 — Task Execution and Scheduling auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
5. Java SE 17 — `ThreadPoolExecutor` and rejection handlers: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
6. Java SE 17 — `CountDownLatch` and `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html

**Conclusion:** For background tasks, "having an executor" is only the starting point. **Bound workers and queues**, embrace intentional rejection, track job state and errors, apply retries/idempotency per contract, and protect shutdown/restart. An HTTP 202 should strictly mean the application **accepted the work under its published guarantees**, never turning into an implicit promise that the job will definitely complete.