# Decoupling Request Acceptance Time from Work Completion Time

> **Module:** Spring Framework - concurrency · **Knowledge Group:** Overview  
> **Focus:** Understand the difference between when a system accepts a request, when processing starts, and when the work actually finishes; choose the right way to organize asynchronous tasks in a Spring application.

## 1. The Problem and Mental Model

An HTTP request may arrive in a few milliseconds while the work behind it takes several seconds or minutes: generating reports, exporting files, sending emails, indexing, processing images, or pushing data to another service. If the controller performs all the work before replying, HTTP response latency is tightly coupled to business processing duration.

There are **three timestamps** to distinguish:

1. **Accept:** authentication, authorization, input validation, deciding whether to accept the job, creating a tracking ID, or persisting the request.
2. **Execute:** the job is pulled from a queue or handed to a worker to run; it may start immediately, start later, or be rejected when the system is overloaded.
3. **Complete:** the final success/failure outcome is produced; this state may arrive long after the client received the acceptance response.

Timeline example:

```text
t0   Client sends POST /jobs
t1   Server validates and records job J42
t2   Server returns HTTP 202 + address GET /jobs/J42
t3   Worker starts processing J42
t4   Worker finishes, saves SUCCEEDED (or FAILED)
t5   Client queries GET /jobs/J42 to get the status
```

Timestamp `t2` **does not need to wait** for `t4`. This is the core meaning of decoupling request acceptance time from work completion time. Decoupling timestamps **does not mean** you automatically get infinite parallelism, non-blocking threads, or fault tolerance; each property must be designed separately.

### Why Decouple?

- **Response latency:** the user can immediately receive a job ID and continue interacting.
- **System capacity:** HTTP processing threads do not sit waiting through an entire long task; workers have their own resource limits.
- **Load regulation:** queues, concurrency limits, and rejection policies help prevent cascading overload.
- **Observability and recovery:** job status, errors, and retries are tracked independently of the HTTP connection lifecycle.

Not every request should be decoupled. If the client needs the result immediately to make the next decision, the work is very short, or a business error must be returned directly before ending the HTTP call, synchronous processing can be simpler and more appropriate.

## 2. Distinguishing Easily Confused Mechanisms in Spring

| Mechanism | When Does HTTP Return? | Initial HTTP Thread | Does Work Survive After HTTP Returns? | Best Fit |
| --- | --- | --- | --- | --- |
| Synchronous controller | After processing finishes | Usually held throughout | Not a decoupled model | Fast tasks where the result is needed immediately |
| Spring MVC `Callable`, `WebAsyncTask`, `DeferredResult` | When the async result is ready or times out | Released while waiting; response remains open | Typically **does not** decouple result lifecycle from HTTP | Optimizing waits within a single HTTP response |
| `@Async` + returning `202 Accepted` | Immediately after accepting/submitting succeeds | Returns early; work runs on executor | Possible, within the same JVM process | Simple background tasks where losing jobs on process death is acceptable |
| Durable job record + broker/queue + worker | After the job is safely persisted | Returns early | Yes, if storage/retry is designed properly | Critical, long-running work requiring fault tolerance and scaling |

**Two non-interchangeable kinds of "async":**

- **Async HTTP response:** `Callable` or `DeferredResult` lets Spring MVC step off the initial Servlet thread, then continue processing to return **the same** HTTP response. The client connection still waits for the result.
- **Async business job:** the controller returns `202` and a job ID; a worker completes it later. The result can be retrieved via polling, notifications, or webhooks. This is what truly decouples response time from business completion time.

`CompletableFuture`, `@Async`, WebFlux, or `Mono` are only asynchronous programming tools. Returning a future or using non-blocking I/O does not automatically create a durable job with retries and a status-tracking API.

## 3. Designing the HTTP Contract for Background Work

A common contract:

```http
POST /jobs
HTTP/1.1 202 Accepted
Location: /jobs/7c5c...

{
  "jobId": "7c5c...",
  "statusUrl": "/jobs/7c5c..."
}
```

```http
GET /jobs/7c5c...
HTTP/1.1 200 OK

{
  "jobId": "7c5c...",
  "status": "RUNNING"
}
```

Status codes/meanings must be clear:

- `202 Accepted`: the system **has accepted the request for processing**, not confirming processing succeeded; the task can still fail or not execute.
- `200 OK` from the lookup endpoint: the **status lookup** succeeded; the `status` field indicates whether the job is running or finished.
- `400`/`422` (depending on contract): invalid input, cannot accept the job. `401`/`403`: unauthenticated or unauthorized.
- `429 Too Many Requests` or `503 Service Unavailable`: overloaded/temporarily not accepting more work, with a retry policy if applicable.
- `404 Not Found`: job ID not found or caller lacks access; do not infer that the job failed.

Minimal state machine:

```text
QUEUED ---> RUNNING ---> SUCCEEDED
                 |
                 +------> FAILED
```

In a real system, you can add `CANCELLED`, `RETRY_WAIT`, `EXPIRED`, attempt count, failure reason, `createdAt`, `startedAt`, `finishedAt`, and result location. Clearly define terminal states and job retention duration.

**Rule:** before returning `202`, be certain the system has *accepted* the work according to its guarantees. If submitting to the executor/queue is rejected, return an appropriate error. If critical work must not be lost on application restart, "acceptance" must include a durable record/message rather than just an object in RAM.

## 4. Runnable Example: Spring Boot MVC + `@Async` + Status Lookup

The following example uses **Java 17+, Spring Boot 3.5.7 (Spring Framework 6.x)** and Maven. It shows the controller returning `202` quickly while the worker sleeps for 3 seconds to simulate processing. For easy observation, state is stored only in an **in-memory** `ConcurrentHashMap`; this is a demo, not a fault-tolerant production deployment.

Project structure:

```text
async-jobs-demo/
├── pom.xml
└── src/main/java/com/example/asyncjobs/
    ├── JobDemoApplication.java
    ├── JobStore.java
    ├── JobWorker.java
    └── JobController.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>async-jobs-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/asyncjobs/JobDemoApplication.java`**

```java
package com.example.asyncjobs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class JobDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JobDemoApplication.class, args);
    }

    @Bean("jobExecutor")
    public ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-");
        return executor;
    }
}
```

`@EnableAsync` activates `@Async` processing. The `jobExecutor` bean is a **bounded** thread pool: at most 4 workers and a queue bounded at 16 items. When the queue is full and the thread limit is reached, the executor rejects tasks; the example handles that situation in the controller. This executor runs **inside the JVM**.

**`src/main/java/com/example/asyncjobs/JobStore.java`**

```java
package com.example.asyncjobs;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class JobStore {
    private final ConcurrentHashMap<UUID, String> states = new ConcurrentHashMap<>();

    public void create(UUID id) {
        states.put(id, "QUEUED");
    }

    public void update(UUID id, String state) {
        states.put(id, state);
    }

    public String find(UUID id) {
        return states.get(id);
    }

    public void remove(UUID id) {
        states.remove(id);
    }
}
```

`ConcurrentHashMap` allows request threads and workers to safely perform individual operations on the map. It **does not** make jobs durable across restarts and does not replace a database.

**`src/main/java/com/example/asyncjobs/JobWorker.java`**

```java
package com.example.asyncjobs;

import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class JobWorker {
    private final JobStore store;

    public JobWorker(JobStore store) {
        this.store = store;
    }

    @Async("jobExecutor")
    public void start(UUID id) {
        store.update(id, "RUNNING");
        try {
            // Simulates 3 seconds of processing; only the worker waits.
            TimeUnit.SECONDS.sleep(3);
            store.update(id, "SUCCEEDED");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            store.update(id, "FAILED");
        } catch (RuntimeException ex) {
            // In practice, log the error, error code, and diagnostic information.
            store.update(id, "FAILED");
        }
    }
}
```

The call `worker.start(id)` goes through the **Spring proxy**, so the method runs on a `jobExecutor` thread. `TimeUnit.SECONDS.sleep(3)` merely illustrates a long task and does **not** run on the HTTP thread. Failures update the state to `FAILED`; with an `@Async void` method, exceptions do not automatically go back to the already-sent HTTP response.

**`src/main/java/com/example/asyncjobs/JobController.java`**

```java
package com.example.asyncjobs;

import java.net.URI;
import java.util.Map;
import java.util.UUID;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/jobs")
public class JobController {
    private final JobStore store;
    private final JobWorker worker;

    public JobController(JobStore store, JobWorker worker) {
        this.store = store;
        this.worker = worker;
    }

    @PostMapping
    public ResponseEntity<Map<String, String>> submit() {
        UUID id = UUID.randomUUID();
        store.create(id);

        try {
            worker.start(id); // Submits work to the executor via the Spring proxy.
        } catch (TaskRejectedException ex) {
            store.remove(id);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("error", "Executor is full"));
        }

        String path = "/jobs/" + id;
        return ResponseEntity.accepted()
                .location(URI.create(path))
                .body(Map.of("jobId", id.toString(), "statusUrl", path));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Map<String, String>> status(@PathVariable UUID id) {
        String state = store.find(id);
        if (state == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(Map.of(
                "jobId", id.toString(),
                "status", state
        ));
    }
}
```

The controller **does not call** `get()`, `join()`, or wait for the worker's result. After the executor accepts the task, the controller returns HTTP `202 Accepted` along with `Location` for the client to query. If the executor is full, the controller returns `503`, avoiding reporting acceptance when work could not be submitted. In a real system, authentication, authorization, and input validation must happen before acceptance; payload is intentionally omitted here to focus on timestamps.

Run the project (with JDK 17+ and Maven installed):

```bash
mvn spring-boot:run

# In another terminal:
curl -i -X POST http://localhost:8080/jobs
# Copy jobId from the response:
curl -i http://localhost:8080/jobs/<jobId>
```

**Illustrative** output (the UUID changes on every call):

```http
HTTP/1.1 202
Location: /jobs/<jobId>

{"jobId":"<jobId>","statusUrl":"/jobs/<jobId>"}
```

Right after POST, GET may show `QUEUED` or `RUNNING`; about 3 seconds after the worker starts, it will typically show `SUCCEEDED`. If the worker is scheduled/runs fast, the state may change before the client's first GET; do **not** rely on assumed timing order. There is no fixed stdout because processing time and UUIDs depend on each run.

**Points to observe:** POST can complete in under 3 seconds; the GET endpoint returns the state at the moment it is queried; a `job-*` thread handles the work instead of the HTTP thread; work can be lost if the JVM stops.

## 5. When You Only Want to Release the HTTP Thread, Still Returning the Result in the Same Response

Spring MVC has a Servlet async mechanism for cases where **the client still needs the data in the same open HTTP response**. Example of an added method in a `@RestController`:

```java
@GetMapping("/preview")
public java.util.concurrent.Callable<String> preview() {
    return () -> {
        java.util.concurrent.TimeUnit.SECONDS.sleep(2);
        return "PREVIEW_READY";
    };
}
```

This is an **illustrative method snippet** to place in a controller with an active `@GetMapping`; it is not a standalone Java program. Spring MVC receives the `Callable`, starts Servlet async processing, releases the initial Servlet thread, and runs the callable on an `AsyncTaskExecutor`. After the callable finishes, Spring dispatches again to return the `PREVIEW_READY` body. The client still has to wait around 2 seconds to receive this response.

`DeferredResult<T>` is used when the result is provided by **an external event** or callback rather than directly running a `Callable`. The application holds the `DeferredResult` object and another thread calls `setResult` or `setErrorResult`. Timeouts and completion must be handled so requests do not hang indefinitely. `WebAsyncTask` provides a way to set a custom timeout/executor for a `Callable`.

Do not use `Callable`/`DeferredResult` and conclude "work has been moved to the background": the HTTP connection remains tied to waiting for the result. Conversely, a `202` endpoint does not keep the response open, but must provide a way to observe the result later.

## 6. Production Design: Reliable Acceptance, Controlled Execution

The example above teaches the **mechanism**, not durability. For large reports, critical emails, or tasks that can run for minutes, split into components:

```text
Client
  |
  | POST /jobs (+ Idempotency-Key if needed)
  v
HTTP API --validate/auth--> DB: INSERT job(status=QUEUED)
  |                                |
  | HTTP 202 + jobId               | Worker/broker picks up task
  v                                v
Client --GET /jobs/{id}--> DB <-- Worker updates RUNNING/SUCCEEDED/FAILED
```

There are two common implementations:

1. **DB as job queue:** a transaction saves the `QUEUED` job, and workers query/claim jobs with a lock or lease and update status. Expired claims, job distribution across multiple instances, retries, and crashes must be handled.
2. **DB + message broker:** the API records the intent to work and publishes a message to RabbitMQ/Kafka or equivalent; workers consume it. If you must guarantee no job is lost between DB commit and message publish, use a **transactional outbox** (write job + outbox in the same transaction, and a publisher emits the message after commit). Consumers must handle possible duplicate deliveries.

Minimum decisions to specify:

- **Acceptance boundary:** authenticate, authorize, validate input, check quota, and persist the job/queue entry successfully before returning `202`. If writing fails, return an error instead of issuing a "phantom" job ID.
- **Backpressure:** bounded executors/queues; reject or defer accepting jobs when overloaded rather than spawning unbounded threads. Separate **HTTP latency** metrics from **queue wait time** and **job execution time**.
- **Idempotency:** clients may resend POST due to timeouts; if the business action must not run twice, support an idempotency key and map that key to a single job. Workers also need to be idempotent on retry/redelivery.
- **Retries and errors:** distinguish transient errors from permanent errors, use backoff, limit attempts, store the failure reason, and move exhausted retries to `FAILED`/dead-letter per contract.
- **Results and permissions:** store output or a download URL upon completion; check job ownership on every GET/cancel/download, never allowing anyone who knows a UUID to view the data.
- **Timeouts and cancellation:** an HTTP timeout does not automatically cancel a job; cancellation requires dedicated state, worker signaling, and resource cleanup policies.
- **Observability:** include correlation/job IDs in logs and traces; measure queued job count, oldest job age, running worker count, failure/retry rate, and time from acceptance to completion.
- **Recoverability:** after a restart, detect abandoned `RUNNING` jobs, use leases/heartbeats and valid rerun mechanisms; do not rely on RAM.

**Note on transactions and context:** `@Async` switches threads. A request's transaction does not automatically propagate to the worker thread; `SecurityContext`, request attributes, and `ThreadLocal`-based MDC also do not inherently follow. Workers should receive required data as explicit values/IDs and open their own transactions when needed. If you require "start only after DB commit," use an appropriate post-commit trigger; if it must be *durable* across crashes, use an outbox/queue instead of only `@TransactionalEventListener` + `@Async`.

## 7. Common Mistakes and Self-Check

| Misconception/Wrong Practice | Consequence | How to Handle |
| --- | --- | --- |
| Returning `200 OK` or "completed" right after submitting work | Client thinks the business action has already succeeded | Return `202`, job ID, and status endpoint |
| Calling `future.get()`, `join()`, or waiting for the worker in the controller | HTTP still waits for the long work | Only submit the work and return; read status in a separate call |
| Calling an `@Async` method via `this.start()` inside the same bean | Self-invocation bypasses the proxy; work may run synchronously | Call through another Spring bean or use an explicit scheduling mechanism |
| Assuming `@Async` inherently has a durable queue | Restarts/crashes lose jobs and RAM state | DB/broker, retries, recovery |
| Using an unbounded thread pool/queue or `CallerRunsPolicy` carelessly | Resource exhaustion; `CallerRunsPolicy` can run the job directly on the HTTP thread | Set bounds, monitor queue depth, reject intentionally |
| Not handling exceptions in `@Async void` tasks | HTTP has already returned; errors are never sent back to the client | Catch errors, update status, log and alert |
| Using `DeferredResult` and forgetting timeouts/cleanup | Hanging HTTP requests holding resources | Timeout callback, error result, clean up listeners |
| Relying on the calling thread's transaction/context | Reading uncommitted data, missing principal/trace | Pass explicit IDs, use dedicated transactions/context |
| Unconditional retries on operations with side effects | Sending emails/charging money/writing data twice | Idempotency, deduplication, and retry policies |

**Self-check questions:**

1. If POST returns after 20 ms while the worker takes 15 seconds, which HTTP status is appropriate and where does the client learn the result?
2. `Callable` in Spring MVC releases the initial HTTP thread; why must the client still wait for the response?
3. What happens to jobs stored in `ConcurrentHashMap` and the executor when the JVM process stops?
4. Why can calling `@Async` within the same bean run synchronously?
5. When the queue is full or the broker fails to accept the message, should the API still return `202`?

Guiding answers: (1) `202` + job ID/status endpoint; (2) the HTTP response remains open until the result is ready; (3) in-RAM jobs/state are not durable; (4) it does not pass through the Spring proxy; (5) no, unless a durable record already exists guaranteeing the job will be processed later.

## 8. Takeaway

**Decoupling acceptance from completion** is a decision about **business lifecycle and the client contract**. Spring supports several asynchronous execution mechanisms, but you must choose the right one based on what the user is waiting for:

- Need **the result in the same HTTP response**: consider Spring MVC `Callable`/`DeferredResult` with appropriate timeouts and executors.
- Need **fast acceptance and learning the result later**: use `202 Accepted`, a job ID, and a lookup mechanism; `@Async` is sufficient for demos or background tasks where in-JVM loss is acceptable.
- Need **no lost work, retries, and multi-instance scaling**: persist jobs durably, use a queue/outbox/workers, idempotency, and operational observability.

**Official documentation:** [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) · [Spring Framework – Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html) · [HTTP Semantics RFC 9110, §15.3.3 – 202 Accepted](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3)