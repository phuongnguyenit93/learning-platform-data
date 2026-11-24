# Do Not Equate an Accepted Task with a Completed Business Operation

A Spring application receives a request to generate a report, send an email, or process an order, then calls `executor.execute(task)` or an `@Async` method. The submission call returns without throwing an error. **Can you immediately return "processed successfully" to the customer?** No. At that point, the system usually only knows **the executor accepted the task**, not whether a worker has run it, finished processing, persisted data successfully, or reached the final business state.

This is a critical boundary of asynchronous processing in **Spring Framework – concurrency**, belonging to **Task Submission and Retrieval**. This lesson distinguishes four layers of information: **acceptance**, **execution**, **technical result**, and **verifiable business outcome**. From there, you can design APIs, job states, error handling, retries, and recovery to match reality.

## 1. A Task Passes Through Many States, Not Just "Success / Failure"

Consider an HTTP request asking to export a report:

```text
Client                    Spring API              Executor            Worker / DB / Storage
  |                           |                       |                       |
  | POST /reports             |                       |                       |
  |-------------------------->|                       |                       |
  |                           | submit(task)          |                       |
  |                           |---------------------->|                       |
  |                           |<--- accepted ---------|                       |
  |<--- 202 Accepted + jobId--|                       |                       |
  |                           |                       |-- queue / start ----->|
  |                           |                       |                       | processing...
  |                           |                       |                       | write file / DB
  | GET /jobs/{id}            |                       |                       |
  |-------------------------->| read status           |                       |
  |<--- RUNNING / SUCCEEDED --|<----------------------------------------------|
```

**202 Accepted** in the diagram is an example for a background-job API protocol. It **does not mean the task has completed**. With results held only in RAM, 202 also **does not automatically guarantee survival across crashes**.

A common state model:

| State | Meaning | Business operation completed? |
| --- | --- | --- |
| `NEW` / `VALIDATING` | Checking data, permissions, and quotas before accepting | Not yet |
| `ACCEPTED` | System confirms the request was accepted under the published contract | Not yet |
| `QUEUED` | Task has entered the executor/queue backlog | Not yet |
| `RUNNING` | Worker is executing | Not yet |
| `RETRYING` | An attempt failed, preparing to retry | Not yet |
| `SUCCEEDED` | Business success criteria are satisfied with appropriate evidence | Yes, per business contract |
| `FAILED` | Failed to meet success criteria under the current policy | No |
| `CANCELLED` | Successfully cancelled per the application's definition | Does not necessarily "undo" already-occurred effects |
| `EXPIRED` | Exceeded the allowed processing/waiting deadline | External effects may still have occurred |

Every system does not need all of these states. More importantly, **each state must have an explicit definition and transition condition**. For instance, a job should transition to `SUCCEEDED` only when saving the report has actually finished and is retrievable, not immediately after the caller submits the task.

### Four Questions to Distinguish

1. **Was the request accepted?** Did the API/executor admit the work into the system, or reject it immediately?
2. **Has execution started?** Has a worker pulled the task from the queue yet?
3. **Has execution finished?** Did `run`/`call` finish normally, throw an error, or get cancelled?
4. **Did the business operation succeed?** Have the required effects—such as updating order status, saving documents, delivering the email, or confirming payment—fulfilled business guarantees and become verifiable?

These four questions can have four different answers at the exact same moment.

## 2. What Does `execute` or `submit` Returning Actually Tell You?

With a standard thread pool:

```java
executor.execute(() -> generateReport(reportId));
```

When `execute` returns normally under a configuration that throws on rejection, it tells you the task was accepted per the executor's rules, **not that `generateReport` has run or succeeded**. The task may be sitting in the queue. Under `CallerRunsPolicy`, the task may run directly on the caller when the pool is saturated; so do not assume "`execute` always returns immediately" either. With `DiscardPolicy`, a dropped task may throw no exception at all, so you must know **the specific rejection policy** rather than treating "did not throw" as a universal acceptance guarantee.

Similarly:

```java
Future<String> future = executorService.submit(() -> generateReport());
```

`submit` typically returns a `Future` representing a *forthcoming* result. It does not automatically wait for the worker to finish. To know the outcome, the caller must inspect `get()`, `isDone()`, and exception/cancellation states.

**Comparison table:**

| Call / signal | What is known | What cannot be inferred |
| --- | --- | --- |
| `execute(task)` without throwing, AbortPolicy | Task was accepted by the executor or ran via the configured mechanism | Business effects are completed |
| `submit(callable)` returns `Future` | You have a handle to observe processing | Task finished successfully |
| `future.isDone() == true` | Future reached a terminal state (may be completion, failure, or cancellation) | Business success |
| `future.get()` returns normally | Callable returned normally; appropriate memory-consistency guarantees hold | DB transactions, external APIs, or side effects are durable if code did not ensure it |
| `future.get()` throws `ExecutionException` | Task ended with the wrapped exception | External side effects definitely did not happen |
| `CompletableFuture.isCompletedExceptionally()` | Future completed exceptionally or via cancellation depending on case | Business effects were rolled back |
| HTTP 202 from a job API | Request was accepted **per the API contract** | Work finished or is guaranteed to run exactly once |

Notably, a task can finish performing a side effect and then **fail while recording the final status**, leaving the system reporting `FAILED` even though the side effect actually occurred. Conversely, code can return normally without **verifying** that an external service actually executed the request.

## 3. Three Distinct Layers of "Completion"

### 3.1. Executor-Layer Completion

A worker finishes `Runnable.run()` or `Callable.call()`. The `Future` moves to a terminal state. This is the **technical state of the task**.

```java
CompletableFuture<String> task =
        CompletableFuture.supplyAsync(() -> "done", executor);
```

Here `"done"` is merely the value returned by the lambda. The executor has no idea whether `"done"` means **the report was saved successfully**.

### 3.2. Application-Layer Completion

The application checks concrete steps: creating the file, writing to storage, updating the DB, receiving a downstream response, recording task history, and so on. If each step reports back, the application can evaluate the outcome per its policy.

However, "HTTP request to email provider succeeded" may only mean **the provider accepted the request**. It does not prove the email landed in the recipient's inbox. Each external system has different acknowledgment semantics.

### 3.3. Business-Layer Completion

A report generation request may only be considered complete when:

- The file physically exists in the intended storage location.
- Metadata / file ID linked to the job has been committed/persisted durably.
- Authorized users can download/look up the file per contract.
- The job status is updated according to these success criteria.

For payments, "payment request sent" differs completely from "bank/PSP confirmed transaction settled". For emails, "enqueued at email provider" differs from "delivered"; separate states like `SUBMITTED_TO_PROVIDER`, `DELIVERED`, and `BOUNCED` may be needed.

**Principle:** define `SUCCEEDED` via **verifiable business evidence** rather than `executor.execute` returning.

## 4. Standalone Java 17+ Example: accepted ≠ done, done ≠ success

The following example uses JDK 17+ to clearly demonstrate both distinctions. One task is `submit`ted successfully yet held waiting for controlled release; another task **has finished, yet finished by throwing an exception**.

Save the contents as **AcceptedVsCompletedDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

public class AcceptedVsCompletedDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean businessStepFinished = new AtomicBoolean(false);

        try {
            Future<?> accepted = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                businessStepFinished.set(true);
            });

            started.await();
            System.out.println("accepted=true, done="
                    + accepted.isDone()
                    + ", businessStepFinished="
                    + businessStepFinished.get());

            release.countDown();
            accepted.get();
            System.out.println("accepted=true, done="
                    + accepted.isDone()
                    + ", businessStepFinished="
                    + businessStepFinished.get());

            Future<?> failed = pool.submit(() -> {
                throw new IllegalStateException("simulated failure");
            });
            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("failedFutureDone="
                        + failed.isDone()
                        + ", taskSucceeded=false");
            }
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```bash
javac AcceptedVsCompletedDemo.java
java AcceptedVsCompletedDemo
```

**Deterministic stdout on a normal run:**

```text
accepted=true, done=false, businessStepFinished=false
accepted=true, done=true, businessStepFinished=true
failedFutureDone=true, taskSucceeded=false
```

**Why is the result reliable?**

1. `pool.submit(...)` returns a `Future`. `started.await()` guarantees the worker started the task, yet remains held at `release.await()`.
2. While the latch is closed, the task cannot reach the line setting `businessStepFinished=true`; `Future.isDone()` is `false`. Having accepted the task **does not equal** completion.
3. After `release.countDown()`, `Future.get()` waits for the task to finish and lets the caller observe the write to `AtomicBoolean`. Only then are both `done` and the simulated flag `true`.
4. The second task intentionally throws `IllegalStateException`. `failed.get()` throws `ExecutionException`; the Future is `done=true`, yet **not a success**.
5. `CountDownLatch` eliminates luck when observing states. It avoids `Thread.sleep(100)` to guess how far the worker got.

**Intentional limitation of the demo:** `businessStepFinished` is an **in-memory** flag that only simulates completion. It does not prove a database committed or an email reached the recipient. In real applications, business status must be backed by corresponding verifiable operations.

## 5. Spring's `@Async` and the Meaning of Future Outcomes

Spring supports asynchronous method execution via `@EnableAsync` and `@Async`:

```java
@Service
class ReportService {
    @Async("reportExecutor")
    public CompletableFuture<String> generateReport(String reportId) {
        String url = calculateAndStoreReport(reportId);
        return CompletableFuture.completedFuture(url);
    }

    private String calculateAndStoreReport(String reportId) {
        // Fragment: requires actual business logic and storage implementation.
        return "/reports/" + reportId;
    }
}
```

This is an **illustrative fragment**, not a complete program: imports and the executor bean are assumed to exist; `calculateAndStoreReport` here only returns a string and **does not save a real file**. It illustrates how Spring's proxy creates an async invocation and returns a result when the method finishes.

When another bean calls `reportService.generateReport(id)` through the Spring proxy, a task is handed to `reportExecutor`. The caller receives a `CompletableFuture` to observe; that **does not automatically make the report real**. When the method returns normally, the future represents completion of Spring's execution path, yet **business semantics** still depend on what the code actually did and on external transactions/resources.

**Common pitfalls:**

- Under default proxy configuration, `this.generateReport(id)` called from inside the same bean typically **does not pass through the `@Async` proxy**. Do not rely on self-invocation to infer whether an executor accepted a task.
- `@Async void` gives no Future to the caller, so it is unsuitable if the caller needs the outcome. Exceptions on `void` return types require `AsyncUncaughtExceptionHandler` and proper logging/monitoring.
- When returning `CompletableFuture<T>`, observe `whenComplete`, `handle`, `exceptionally`, or `join/get` at an appropriate place; if unchecked, failed tasks can slip into logs while users still see "success".
- `@Async` using another worker does not make blocking JDBC/HTTP calls non-blocking. Workers still stay occupied waiting on I/O, and the executor can saturate.
- If `CallerRunsPolicy` is used for overload, tasks may execute on the calling thread when the pool is full; with `AbortPolicy`, submission can fail immediately with `TaskRejectedException`.
- An in-JVM Future is not durable job state across restarts and does not automatically reflect status across other replicas.

### 5.1. The Future Completed, but Did the Transaction Commit?

Do not equate "method returned" with "data committed" when transactions and proxies/side effects are not verified together. For example, a transactional method writes to the database and then **emits a `SUCCEEDED` signal externally right inside the method**, before the transaction actually commits. If the transaction rolls back at the end, the emitted signal is false.

Safer approaches depending on design:

1. **Job status and business outcome in the same DB transaction:** once committed, data becomes visible to readers. If rolled back, both roll back together.
2. **With operations outside the DB:** mark success only after confirming the operation per the provider's contract; anticipate uncertain outcomes on timeouts.
3. **Events emitted only after commit:** `@TransactionalEventListener(phase = AFTER_COMMIT)` can be used for in-process events when suitable, though in-memory listeners can lose events on crash. For durability, use a transactional outbox/broker.
4. **When completion is verified externally:** transition to `SUCCEEDED` only with strong evidence, such as confirming the report exists in object storage and metadata is consistent.

No Spring annotation automatically turns a sequence of DB + HTTP + broker calls into an atomic transaction across all systems.

## 6. HTTP 202 Accepted and Job APIs: Report Exactly What Was Done

When an API accepts work for background processing, it may use:

```http
POST /jobs HTTP/1.1
Content-Type: application/json

{"reportType":"monthly"}
```

If the API accepted the request **per contract** and provides a tracking path, a typical response is:

```http
HTTP/1.1 202 Accepted
Location: /jobs/8f2a

{"jobId":"8f2a","statusUrl":"/jobs/8f2a"}
```

The client then polls:

```http
GET /jobs/8f2a HTTP/1.1
```

It might receive:

```json
{"jobId":"8f2a","state":"RUNNING","message":"Generating report"}
```

And later:

```json
{"jobId":"8f2a","state":"SUCCEEDED","message":"Report stored"}
```

**This is an illustrative protocol**, not logs from a running server. Status naming, payloads, and paths should be designed per the actual contract.

### Do Not Interchange 200, 201, and 202 Arbitrarily

- **200 OK:** reflects an HTTP request succeeding for the current response; if the body claims "report ready", return it only after actual success criteria have been verified.
- **201 Created:** may state that a **job resource** was created, without implying *the report itself* is finished. Distinguish the "job" resource from the job's output.
- **202 Accepted:** the HTTP standard for a request accepted for processing that **is not yet completed at response time**; it is **noncommittal**, not a promise that the eventual workflow will succeed.
- **400/422:** invalid request per the API requirements.
- **429 Too Many Requests:** the application is enforcing client rate limits/quotas.
- **503 Service Unavailable:** the backend temporarily lacks capacity or cannot accept work; consider `Retry-After` if a retry policy exists.
- **404 Not Found on GET status:** may mean the job does not exist, expired and was purged, or the client hit the wrong replica of an in-memory system. Define exact API semantics.

Never return 202 if **the task was not actually accepted** (executor rejected it or job persistence failed), unless the system placed it into a valid, trackable alternative intake mechanism.

### Client Timeout After the Server Already Accepted

A client sends POST, the server enqueues successfully, and the network drops before the 202 response reaches the client. Thinking "I don't know if it was received", the client retries. If each POST creates a new job, the report or email may be processed **twice**. Use an **idempotency key** or stable request ID so retries return the first attempt's job/outcome.

That is why **receiving the HTTP response** and **server accepting the work** can also diverge when the network fails.

## 7. Spring Boot 3.x: An API Reporting "Accepted" and Allowing Status Queries

The following example uses **Java 17+**, Spring Boot 3.x / Spring Framework 6.x, and the `spring-boot-starter-web` dependency. Its goal is to demonstrate **reporting accepted vs. completed truthfully** with `ThreadPoolTaskExecutor` and job status.

**Note:** the example uses `ConcurrentHashMap` to store status **in RAM only**, so it does not guarantee durability or multi-replica operation. It simulates work with `Thread.sleep`; `SUCCEEDED` only indicates the demo step finished normally, **no real report is saved**. Section 8 explains how to upgrade to a production design.

Place the entire code in **src/main/java/com/example/demo/JobApplication.java**:

```java
package com.example.demo;

import java.net.URI;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JobApplication {
    public static void main(String[] args) {
        SpringApplication.run(JobApplication.class, args);
    }

    @Bean("jobExecutor")
    ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("job-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}

record JobReceipt(String jobId, String statusUrl) {}

record JobStatus(String jobId, String state, String message) {}

@Service
class JobService {
    private final ThreadPoolTaskExecutor executor;
    private final ConcurrentMap<String, JobStatus> jobs =
            new ConcurrentHashMap<>();

    JobService(@Qualifier("jobExecutor") ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    JobReceipt submit() {
        String id = UUID.randomUUID().toString();
        jobs.put(id, new JobStatus(id, "QUEUED", "Waiting for a worker"));

        try {
            executor.execute(() -> perform(id));
        } catch (TaskRejectedException rejected) {
            jobs.remove(id); // Do not report accepted for a rejected task.
            throw rejected;
        }

        return new JobReceipt(id, "/jobs/" + id);
    }

    Optional<JobStatus> find(String id) {
        return Optional.ofNullable(jobs.get(id));
    }

    private void perform(String id) {
        jobs.put(id, new JobStatus(id, "RUNNING", "Demo work started"));
        try {
            Thread.sleep(300); // Simulates processing, saves no real data.
            jobs.put(id, new JobStatus(
                    id, "SUCCEEDED", "Demo step finished"));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            jobs.put(id, new JobStatus(id, "FAILED", "Interrupted"));
        } catch (RuntimeException ex) {
            jobs.put(id, new JobStatus(id, "FAILED", "Processing error"));
        }
    }
}

@RestController
class JobController {
    private final JobService service;

    JobController(JobService service) {
        this.service = service;
    }

    @PostMapping("/jobs")
    public ResponseEntity<?> create() {
        try {
            JobReceipt receipt = service.submit();
            return ResponseEntity.accepted()
                    .location(URI.create(receipt.statusUrl()))
                    .body(receipt);
        } catch (TaskRejectedException rejected) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("error", "executor_unavailable"));
        }
    }

    @GetMapping("/jobs/{id}")
    public ResponseEntity<JobStatus> status(@PathVariable String id) {
        return service.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```

Run using the Spring Boot project's build:

```bash
./gradlew bootRun
curl -i -X POST http://localhost:8080/jobs
```

On Windows you can run `gradlew.bat bootRun`. When the executor accepts the work, the response is **202 Accepted**, with a JSON body containing `jobId` and `statusUrl`, for example:

```json
{"jobId":"b610d4e5-8891-48b1-a63f-632faf38b7cf","statusUrl":"/jobs/b610d4e5-8891-48b1-a63f-632faf38b7cf"}
```

This is an **example ID**, not a fixed constant ID. Use the returned ID to query status:

```bash
curl -i http://localhost:8080/jobs/<jobId>
```

`<jobId>` in the command above is a **placeholder for the real ID**; do not type angle brackets in the shell. The JSON may show `QUEUED`, `RUNNING`, or `SUCCEEDED` depending on timing. Do not predict exact log/thread-scheduling order per request. If the executor rejects right at `execute`, the API returns **503** with `executor_unavailable`.

### Why Does This Example Not "Report Success Early"?

- `submit()` creates a `QUEUED` status entry **before** calling the executor, so even if a worker starts immediately, a corresponding record exists.
- If `execute` throws `TaskRejectedException` under `AbortPolicy`, the record is removed and the controller does not return 202.
- If accepted, the controller returns only **202 + jobId**, never reporting `SUCCEEDED`. The worker transitions to `RUNNING` and `SUCCEEDED` after the demo step finishes.
- Even if the worker finishes before the HTTP 202 response reaches the client, status GET may already read `SUCCEEDED`. That **does not turn 202 into a business completion claim**; the response still only confirms intake per contract.
- `ConcurrentHashMap` protects status reads/writes between the HTTP thread and workers. `JobStatus` instances are immutable records; callers cannot mutate internal entries.
- This is a **best-effort in-memory** example. `jobs` do not persist across restarts and are not shared across servers. `SUCCEEDED` here **is only completion of the simulated step**.

**Limitation to know in real systems:** The controller returns 202 once `execute` admits the task to the in-RAM pool; if the JVM crashes right after, both job and status are lost. To guarantee durable intake, replace intake with a proper transaction/persistent queue before returning 202.

## 8. Upgrading to a Durable Job Protocol

Production solutions usually require a transactional **job store** and a retry-capable worker. A common design:

```text
Client
  |
  | POST /jobs + Idempotency-Key
  v
API: check permissions, payload, quota
  |
  | BEGIN DB transaction
  |   INSERT job(id, status=ACCEPTED, requestHash, ...)
  |   INSERT outbox(jobId, event=JobAccepted, ...)
  | COMMIT
  v
HTTP 202 + jobId
  |
  | outbox publisher (may re-run)
  v
Message broker / durable queue
  |
  | worker receives (may receive duplicates)
  v
Idempotent business processing
  |
  | Save result + terminal state in appropriate transaction
  v
SUCCEEDED / FAILED / RETRYING
  |
  | GET /jobs/{id}
  v
Client observes verifiable state
```

### 8.1. Why Must We Commit Before Returning Accepted?

If you only keep jobs in RAM and return 202, a crash loses the request. If you write to a database yet return 202 **before the transaction commits**, the transaction could roll back after the response. Hence, a "durably accepted" guarantee must only be emitted **after a successful commit**.

Depending on an API's definition, 202 can signify best-effort in-RAM acceptance. That does not violate HTTP semantics, yet it must be transparent; never promise "guaranteed processing" without a durability mechanism.

### 8.2. Why Is a Transactional Outbox Needed?

A classic dual-write failure:

1. The API commits the job record in the database.
2. The API tries to publish a message to the broker, yet crashes between the two steps.

Now the DB has the job, while the broker never got the event. Reversing the order (publish first, commit DB second) also has a failure window: the worker receives the event before the job exists or the transaction rolls back.

A **transactional outbox** writes the job + event record in **the same DB transaction**. A separate publisher reads the outbox and dispatches messages; it may redeliver when acks are uncertain, so **consumers must be idempotent**. An outbox does not magically provide end-to-end exactly-once, yet eliminates the window where "DB has a job with no trail to keep publishing".

### 8.3. Where Does True Completion Happen?

In the worker, `SUCCEEDED` should be written **after or atomically alongside** verifiable success conditions:

- For a single DB update, write the business outcome and job status in the same transaction when feasible.
- For creating files outside the DB, declare success only after upload is confirmed per storage contract and metadata linking to the job is safely persisted. Plan for the case where upload succeeds yet the DB update fails.
- For sending email via a provider, distinguish the provider **accepting the request** from **delivering the email to the recipient**; states may require multiple confirmation tiers.
- For payments, never infer success solely from timeouts or incomplete HTTP responses; reconcile provider transaction IDs/final states, and enforce idempotency for financial operations.

**Never write `SUCCEEDED` before critical side effects**, expecting rollbacks to automatically fix external systems. If a side effect happened and writing status failed, worker retries can duplicate the effect — design idempotency or compensation accordingly.

## 9. Retries, Failures, and Idempotency

An accepted task may be attempted multiple times. Common reasons:

- Worker crashes after calling an external API successfully, yet **before recording completion status**.
- Broker redelivers because it did not receive an ack.
- Timeout leaves the caller unsure whether the external call occurred.
- User resends POST after not receiving the 202 response.
- Job exceeds lease/deadline or workers scale/restart.

**At-least-once delivery** means a task may be dispatched/processed **multiple times**. The right goal is usually **business effects not being duplicated**, rather than claiming the executor runs a callback strictly once system-wide.

### 9.1. Idempotency Keys at Job Intake

The client sends the same `Idempotency-Key` across retries of **the same logical request**. The API stores the key alongside a request hash and job ID in a DB with a unique constraint. If the key exists with a matching payload, return the same job ID/status; if the key matches with a different payload, return a conflict error per contract.

```text
POST /jobs + key=abc, payload=P → job-123, HTTP 202
Network drops before client receives response.
POST /jobs + key=abc, payload=P → job-123 (no second job created)
POST /jobs + key=abc, payload=Q → conflict (do not reuse a job with different content)
```

Do not use only an in-memory `ConcurrentHashMap` as an idempotency store across multiple replicas, because replicas cannot see each other's keys.

### 9.2. Idempotency in the Worker

Even if intake creates only one job, the broker can still redeliver the same message. Workers should use stable keys such as `jobId`/`paymentIntentId` and guard business effects:

- Check status/deduplication inside a transaction.
- Use unique constraints or optimistic locking for operations that must occur once at the DB level.
- Forward idempotency keys to external services when supported by the provider.
- Design retries with exponential backoff, jitter, and a maximum attempt count.
- Route uncompletable jobs to `FAILED` or dead-letter/reconciliation queues with operational tooling.

**Do not treat "exactly-once execution" as a default property of `@Async`, executors, or message brokers.** In practice, enforce it at the **business-effect** level.

## 10. When May You Announce "Success"?

A practical rule: messages must reflect **the strongest fact the system has actually verified**, not what you hope will happen.

| Situation | Accurate message | Misleading message |
| --- | --- | --- |
| `executor.execute` accepts task | "Task accepted for processing" | "Processed successfully" |
| Task placed into durable queue | "Request recorded; track progress via job ID" | "Result is ready" |
| Worker begins generating report | "Processing" | "Report generated" |
| Worker sends request to email provider; provider accepts | "Provider accepted delivery request" | "Recipient read the email" |
| File written, accessible, and status committed | "Report is ready" | No need to delay needlessly |
| `Future.isDone()==true` yet Future failed | "Processing failed" | "Completed successfully" |
| Task accepted, then JVM crashed before processing | "Status requires recovery/reconciliation" | "Success" |
| Worker timed out calling external service | "Outcome uncertain, checking status" | "Definitely failed, retrying immediately" |

Define *what "success" applies to*: success in **accepting the command**, **submitting to a provider**, **provider execution**, or **customer receipt**. A system can have multiple distinct success milestones that cannot be collapsed into one vague boolean.

## 11. Race Conditions and State Consistency

Job tracking designs must handle real concurrency:

### 11.1. Worker Starts Before the API Returns 202

The executor can run a task immediately upon submit. Never insert the job record **after** submitting while assuming the worker has not started yet. In the Spring example, `QUEUED` is saved before `execute`, and then the worker updates to `RUNNING`. Returning 202 still only confirms acceptance, even if state has already progressed to `RUNNING` or `SUCCEEDED` before the response reaches the client.

### 11.2. Status Can Regress

If multiple worker retries and callbacks update the same record concurrently, you can get:

```text
Worker A: writes SUCCEEDED
Stale Worker B: writes RUNNING or FAILED
=> status regresses or overwrites success
```

With a database, use **conditional updates**, versioning/optimistic locking, lease/attempt IDs, and transition rules. For example, allow `RUNNING → SUCCEEDED` only for the worker/attempt holding the active lease, and reject `SUCCEEDED → RUNNING` from stale callbacks.

### 11.3. Terminal Status Does Not Mean Zero Remaining Side Effects

A client requests cancellation while a task is calling an external API. The worker may be interrupted or the Future cancelled, yet the HTTP request already left the system and the provider continues processing. Thus **`CANCELLED` does not automatically guarantee external effects were rolled back**. Define best-effort cancellation and compensation if business rules require it.

### 11.4. Multi-Instance Visibility

If an API has two replicas A and B and job state sits in A's memory, `GET /jobs/{id}` routed to B returns 404 even while the job runs on A. For consistent status across replicas, use a shared DB/cache with explicit TTL, versioning, retention, and access controls.

## 12. "Done" Outcomes Must Be Observable

Beyond `SUCCEEDED` status, the API should provide usable output:

```json
{
  "jobId": "job-123",
  "state": "SUCCEEDED",
  "result": {
    "reportId": "report-456",
    "downloadUrl": "/reports/report-456/download"
  }
}
```

The example above is a **suggested contract**, not the Spring sample's response. Expose `downloadUrl` only when the resource is accessible under the caller's permissions.

For `FAILED`, provide actionable error codes/categories without leaking stack traces or internal secrets:

```json
{
  "jobId": "job-123",
  "state": "FAILED",
  "error": {
    "code": "REPORT_SOURCE_UNAVAILABLE",
    "retryable": true
  }
}
```

Distinguish **retryable** errors (downstream temporarily overloaded) from **permanent** errors (invalid request). Never let clients blindly retry operations that can duplicate effects without idempotency.

## 13. Observability and Operations: "Accepted" Count Is Not Successful Throughput

A dashboard showing only `jobs_submitted_total` can make a system look healthy even while queues fill up and business completions stall.

Metrics to separate:

| Metric | Explanation |
| --- | --- |
| Requests received | How many HTTP requests the API received |
| Jobs accepted | How many jobs were accepted per the API contract |
| Jobs rejected | How many requests were refused due to overload/shutdown/validation |
| Jobs started | How many jobs workers actually started |
| Jobs completed successfully | How many jobs met business success criteria |
| Jobs failed/cancelled/expired | Unsuccessful endings |
| Queue depth/age | How many tasks are waiting, and how long the oldest has waited |
| Queue wait duration | Time from accepted to started |
| Processing duration | Time from started to terminal state |
| End-to-end completion latency | Time from client request submission until usable result |
| Retry count/duplicates | Reprocessing rate and idempotency hit rate |
| "Stuck" jobs | Jobs still `QUEUED` or `RUNNING` past SLA, needing recovery |

Invariants useful for **periodic reconciliation** once counting rules are defined and duplicate retry counting is avoided:

```text
Accepted jobs (unique job IDs)
≈ Active jobs + Terminal jobs + Jobs needing reconciliation

Terminal = SUCCEEDED | FAILED | CANCELLED | EXPIRED (per contract)
```

This is a logical job-level auditing view, **not an exact instantaneous sum** in distributed systems with eventual consistency, retries, job deletion, and intermediate states.

Measure SLA completion rate, oldest queued task age, DB/broker latency, and the percentage of accepted requests that reached a final outcome. A system with 10,000 accepted jobs where 9,000 never completed cannot be described as "successfully processed 10,000 jobs".

## 14. Common Mistakes

**Mistake 1 — Returning "email sent" right after `@Async` submit.** More accurate: "send request accepted"; delivery status requires its own confirmation source.

**Mistake 2 — `Future.isDone()==true` so setting `SUCCEEDED`.** The Future may be cancelled or failed. Check `get()/join()`, exceptions, and business criteria.

**Mistake 3 — Method returned normally so assuming all side effects committed.** Transactions may not have committed yet; providers may only return an initial acknowledgment. Success evidence must match the boundary.

**Mistake 4 — Treating 202 as guaranteed execution.** HTTP 202 only means accepted for processing; crash-survival guarantees depend on architecture.

**Mistake 5 — Assuming an executor accepting a task into a RAM queue makes it durable.** In-RAM queues vanish on process death; critical work needs a DB/broker/outbox.

**Mistake 6 — Client times out and retries a new POST without an idempotency key.** Can spawn two jobs for one logical request and duplicate effects.

**Mistake 7 — Worker retries without protecting side effects.** A task may finish part of its work and crash; a retry could generate another report, charge again, or send a second email.

**Mistake 8 — Updating status to `SUCCEEDED` before writing files / committing DB.** Status can become false if subsequent operations fail or roll back.

**Mistake 9 — Giving clients no way to query status.** An "accepted" response with no job ID or lookup URL leaves no way to learn the final outcome.

**Mistake 10 — Using a single `FAILED` status for all errors.** Loses retryable/permanent/unknown distinctions, blocking proper recovery or automated retries.

**Mistake 11 — In-memory job state across multiple replicas.** Status GETs can land on another instance and return 404; use a shared job store.

**Mistake 12 — Unbounded backlogs and unaddressed rejections.** "Accepted" can turn into "queued forever"; return 503/429 when capacity is exhausted.

**Mistake 13 — Failing to capture `@Async` callback errors.** Futures fail after the HTTP response was already sent; ensure error status, logs/metrics, and alerting exist.

**Mistake 14 — Confusing `CANCELLED` with rolling back external effects.** Interrupt/cancel cannot unsend an email or automatically reverse an external transaction.

## 15. Checklist for Designing a Task-Intake API

1. Define **business completion criteria**: what exact conditions allow reporting `SUCCEEDED`.
2. Define the **acceptance contract**: in-RAM intake only or durably persisted? Responses must reflect what actually happened.
3. Provide a **job ID**, states, and lookup path; distinguish queued/running/succeeded/failed.
4. Separate **submit errors** (`TaskRejectedException`, validation) from **execution errors** (worker exceptions) and **business failures** (unmet business conditions).
5. Use `Future`/`CompletableFuture` to observe completion inside the JVM, without treating Futures as a distributed job store.
6. With DB transactions, **never announce success before commit**; with brokers, consider a transactional outbox.
7. Enforce **idempotency** from intake to worker across client retries, broker redeliveries, and task re-runs.
8. Configure clear timeouts, retry/backoff, dead-letter/reconciliation, TTL, and access control on job status.
9. Track **accepted**, **started**, **completed**, **failed**, **rejected** counts and end-to-end latency separately.
10. Test failure windows: crash after accepted, crash after side effect before status write, transaction rollback, client timeout, and concurrent retries.

## 16. Self-Check Questions

**Question 1.** A controller calls `executor.execute(task)` without error. Can it return HTTP 200 with body `{"status":"COMPLETED"}`?

**Answer:** Only if the business operation has genuinely satisfied and verified its completion criteria. Submitting a task without error normally only proves acceptance per policy, insufficient to announce completion.

**Question 2.** `Future.isDone()==true`, yet `future.get()` throws `ExecutionException`. What do you conclude?

**Answer:** The task reached a terminal state, yet execution failed. It must not be treated as business success.

**Question 3.** A client receives HTTP 202 from an API writing tasks to an in-memory executor. If the server crashes immediately afterward, is the task guaranteed to run again?

**Answer:** No. In-RAM queues and in-memory status have no durable recovery. Guarantees require a persistent job store/broker and retries.

**Question 4.** A worker sends a transfer command, hits a network timeout, and does not know whether the provider executed it. Can it immediately mark `FAILED` and retry?

**Answer:** Never assume the transaction definitely did not occur. Query provider status with a stable key, enforce idempotency, and reconcile to avoid double transfers.

**Question 5.** Why is `@Async void` unsuitable when job outcomes need to be tracked?

**Answer:** The caller receives no result Future; errors go to `AsyncUncaughtExceptionHandler`. A durable status mechanism or Future return type is needed when appropriate.

**Question 6.** When a worker flips a job to `SUCCEEDED` before the DB transaction commits, what can go wrong?

**Answer:** If the transaction rolls back, consumers see a false success notification. Ensure status and business effects commit together or emit events only after commit; for high durability, consider an outbox.

**Question 7.** Two POSTs with the same idempotency key and the same payload should create how many jobs?

**Answer:** Under the recommended idempotent protocol, only one logical job; the retry returns the existing job ID/status. A unique constraint and shared key store enforce this across replicas.

**Question 8.** Why does the "accepted" count not reflect the "completed successfully" count?

**Answer:** An accepted task may still be queued, running, failed, cancelled, or lost in a crash. Success counts must rely on terminal states backed by business evidence, not submission counts.

## Summary

**Acceptance is a promise about intake under contract; business completion is an outcome requiring separate proof.** `execute`, `submit`, `@Async`, and HTTP 202 do not by themselves turn a request into a completed business operation.

Sound designs connect **request ID → accepted/queued → running → final outcome**, handle retries and failure windows properly, and announce `SUCCEEDED` only when business criteria are genuinely fulfilled. That prevents premature success claims as well as lost or duplicated asynchronous work.

## References

- Java SE 17 — `ExecutorService`, `Future`, and memory consistency effects: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 — `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Spring Framework Reference — Task Execution and Scheduling, `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Javadoc — `ThreadPoolTaskExecutor` and `TaskRejectedException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- HTTP Semantics (RFC 9110) — 202 Accepted: https://httpwg.org/specs/rfc9110.html#status.202
