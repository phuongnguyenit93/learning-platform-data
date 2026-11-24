# Choosing Between Returning Errors, Admission Control, or Durable Job Persistence

**Module:** Spring Framework - concurrency  
**Group:** Overload and Rejection  
**Objective:** When a system cannot immediately process every incoming request, know how to choose and combine three strategies: **returning errors early**, **controlling the rate/number of accepted tasks**, or **persisting work durably for later processing**. Understand exact HTTP contracts, guarantee boundaries, Spring executor limits, failure recovery, and how to measure overload.

## 1. The Problem: More Requests Arrive Than Processing Capacity Allows

Suppose a report-generation API is called **100 times/second**, yet the service can only complete **40 reports/second** over a sustained period. If every call is placed into an unbounded queue, the backlog grows by roughly 60 jobs per second. After 10 minutes, the theoretical backlog alone is around 36,000, not counting failed tasks and retries.

Increasing `queueCapacity` or `maxPoolSize` does not magically create extra CPU, DB connections, or external service capacity. When arrival rate exceeds completion rate long enough, **any finite queue will fill up**; an unbounded queue merely converts errors into huge delays and out-of-memory risk.

Distinguish three concepts:

- **HTTP request received:** the server saw the request on the network connection. This does not mean it accepted business responsibility for processing it.
- **Work accepted:** the server accepted the job under a specific contract: either merely handed off in memory, or persisted to durable storage.
- **Completed:** business logic produced a final outcome, whether success or failure.

Therefore, when the backend is busy, which response is correct depends on **the level of guarantee**:

```text
Client sends request
        |
        v
Authenticate + validate payload + permissions + quota
        |
        v
Can serve immediately / within deadline?
        |
       Yes ---------------------> Process synchronously -> 2xx/4xx/5xx per result
        |
       No
        |
        +-- Cannot / should not accept --> intentional 429 or 503
        |
        +-- Allow at most N concurrent tasks -> admission control/bulkhead
        |                                       |
        |                                       +-- Space left -> accept/process
        |                                       +-- Full -> reject early
        |
        +-- Later processing acceptable & durable storage available?
                                           |
                                           +-- Persisted successfully -> 202 + jobId
                                           +-- Failed to persist -> return error, do not promise acceptance
```

These three strategies **can be combined**. For instance, an API caps each customer at 20 jobs/minute, saves jobs to the DB while quota remains and returns `202`, and returns `503` once the backlog reaches a safety threshold even while the DB still has disk space. Having a queue does not mean you must accept every request.

## 2. Decision Table: Reject, Limit Admission, or Persist Durably?

| Question/condition | Return error early | Limit further admission | Persist work durably |
| --- | --- | --- | --- |
| Can the client retry without duplicate side effects? | Reasonable if retry metadata is given | Reasonable for controlling bursts | Still needs idempotency on retries |
| Very short job needing a result in the same HTTP response? | Reject when overloaded | **Prefer** concurrency limits and a very small queue | Usually not worth the overhead of a durable job |
| Long job that can run later without immediate client result? | If admission capacity is exhausted | Used to protect queue insertion rate | **Suitable** with job + status tracking |
| Must requests survive a restart without loss? | Client retains retry responsibility | Only sufficient if admission itself is durable | **Requires** durable DB/queue + recovery |
| Downstream DB or external API is bottlenecked? | Return error early to break cascading failure | Bulkhead/rate limit per downstream | Only queue when deadlines, retries, and backlog are controlled |
| Different quotas per user/tenant? | `429` per quota | Token bucket + per-tenant quota | Combine quota with queued-job cap per tenant |
| System itself is overloaded or temporarily under maintenance? | Usually `503` | Reduce admission, load shedding | May keep persisting if job store and quota remain healthy |

**Practical reasoning order:**

1. Define the client **SLO/deadline**: by when is a result needed?
2. Define **business invariants**: is duplicate processing allowed, is task loss acceptable?
3. Identify the **bottleneck resource**: CPU, threads, queue, DB connections, remote quota, RAM, disk, or broker.
4. Define **safe admission capacity**: how many running, how many waiting, max backlog, and TTL?
5. Choose responses and guarantees matching reality; then enforce limits, add metrics, and test failure paths.

## 3. Returning Errors Early: Keeping the Server and Downstream Operational

When there is no way to finish within deadline and jobs cannot be accepted safely, **explicit rejection** is better than hanging requests until they time out. Two commonly used HTTP statuses:

### `429 Too Many Requests`: Client/Tenant Hit Quota or Rate Limit

Per RFC 6585, `429` indicates **too many requests against a rate limit**. For example, a customer exhausts 60 report exports/minute:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 30

{
  "type": "https://example.invalid/problems/rate-limit",
  "title": "Rate limit exceeded",
  "status": 429,
  "detail": "Quota for this client is exhausted."
}
```

This is an **HTTP contract example**, not a real response from a running server. `Retry-After` can be a number of seconds or an HTTP date; include a value only when the service has a real basis to estimate it. Do not return the same hardcoded number of seconds for every case without quota-reset logic.

### `503 Service Unavailable`: Service Temporarily Lacks Capacity

Per RFC 9110, `503` fits temporary overload or maintenance:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 5

{
  "type": "https://example.invalid/problems/overloaded",
  "title": "Service temporarily overloaded",
  "status": 503,
  "detail": "No execution capacity is available."
}
```

A full executor, an exhausted DB connection pool, or an unavailable broker can lead to `503` depending on the contract. Not every DB error is overload: data errors, configuration errors, or programming bugs must be classified separately.

**`429` or `503`?** A limit placed on **a caller's request volume** is usually expressed with `429`; **shared server capacity** temporarily unable to cope is usually `503`. In practice both causes can happen at once; design stable business error codes so clients know the reason and how to retry. Never assume a full thread pool is always the client's fault.

### Client-Side Retry Policy

- Only retry operations when **idempotent** or protected by an `Idempotency-Key`/deduplication.
- Use exponential backoff + jitter; respect `Retry-After` when present. Never let thousands of clients retry at the exact same instant.
- Enforce a **retry budget**, overall deadline, and circuit breaker/bulkhead if downstream keeps failing.
- Limit retries across all layers: API gateway, SDK, internal services, and workers; ad-hoc retries at multiple layers multiply traffic exponentially.
- Return useful metadata: error code, status, correlation ID, retry hint; never expose internal stack traces, SQL, or sensitive tokens.

A request rejected **before execution** differs from a request that partially executed and then timed out. In the second case, the client may not know whether side effects occurred. That makes idempotency and status-lookup APIs even more vital.

## 4. Limiting Further Admission: Controlling *Rate*, *Concurrency*, and *Backlog*

**Admission control** decides *whether to admit a new job into the system* based on real budgets. It is a defense layer in front of or right next to the executor/downstream, not just catching exceptions after overload.

Three distinct kinds of limits:

| Limit | What is constrained? | Example | What is NOT guaranteed? |
| --- | --- | --- | --- |
| **Rate limit** (token bucket, sliding window) | Number of calls within a time window | Max 100 POSTs/min/tenant | Does not cap in-flight concurrency if tasks run very long |
| **Concurrency limit** (semaphore/bulkhead) | Number of operations active simultaneously | Max 8 concurrent queries to database | Does not cap total requests/min when each operation is fast |
| **Queue/backlog limit** | Number of waiting jobs, plus maximum age | Max 200 jobs in `QUEUED` | Does not guarantee throughput if workers are too slow |

You may need all three: a rate limit stops a tenant from flooding; a semaphore caps DB calls; a bounded queue caps latency and RAM.

### Semaphore / Bulkhead

`Semaphore` is a simple way to cap **concurrent** operations inside one JVM:

```java
private final java.util.concurrent.Semaphore dbSlots =
        new java.util.concurrent.Semaphore(8);

public Result queryWithLimit(Request request) {
    if (!dbSlots.tryAcquire()) {
        throw new BackendBusyException();
    }
    try {
        return queryDatabase(request);
    } finally {
        dbSlots.release();
    }
}
```

This is an **illustrative member snippet** requiring `Result`, `Request`, `BackendBusyException`, and `queryDatabase` to be defined in the application. Acquire a permit before touching downstream, and **always** release in `finally`. `tryAcquire()` does not wait, enabling fail-fast; `tryAcquire(timeout, unit)` fits only if the request's wait budget allows it.

Notes:

- If a service has 5 replicas, each with an 8-permit semaphore, the theoretical **cluster-wide limit can reach 40**, not 8. For a cluster-wide quota, you need shared coordination or per-replica budget allocation.
- If a connection pool already caps connections at 8, an extra semaphore can still help reject early instead of letting dozens of workers wait for a connection, though it must be sized sensibly against real connections and other workloads.
- Do not hold a permit across unrelated steps like waiting for a client download, long sleeps, or after handing a job off to another queue; permits must guard the exact constrained resource.

### Why Not Just Grow the Queue?

Suppose an executor finishes 25 jobs/sec and you give it a 1,000-job queue. A job at the tail can wait roughly **40 seconds** if the pool runs steadily without priorities. If the client deadline is 2 seconds, that queue produces results far too late. Queue sizing must be based on **acceptable wait time**, burst size, and actual throughput, not just free RAM.

Little's Law, when a system is relatively steady:

\[
L = \lambda \times T
\]

`L` is the number of tasks in the system, `λ` is throughput, and `T` is the average residence time (including queue wait if measuring the whole system). The formula does not make overload vanish; it reminds us that backlog and latency are directly coupled.

### Fairness and Workload Isolation

One tenant sending bursts of jobs can fill the queue for every other tenant. Consider per-tenant quotas, weighted fair queues, or separate pools/queues by task class. Urgent jobs and long-running batch jobs should usually not share a single unprioritized queue. Resource separation must reflect SLOs and load forecasts; too many tiny pools add thread and monitoring overhead.

## 5. When Does Spring `ThreadPoolTaskExecutor` Reject?

`ThreadPoolTaskExecutor` wraps JDK `ThreadPoolExecutor` underneath and exposes Spring's `TaskExecutor` contract. Core parameters:

```java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(16);
executor.setRejectedExecutionHandler(
        new java.util.concurrent.ThreadPoolExecutor.AbortPolicy());
```

This is just an illustrative configuration snippet. Normal admission order of `ThreadPoolExecutor`:

1. While current worker count is below `corePoolSize`, create a worker for the new task.
2. Once core is reached, **put the task in the queue if space remains**.
3. When the queue accepts no more, create workers beyond core up to `maxPoolSize`.
4. When no worker can be created and the queue is full, apply `RejectedExecutionHandler`.

Therefore `maxPoolSize=8` **does not mean** the executor immediately uses 8 threads while the queue still has room. With an unbounded queue, the pool may run almost exclusively on core workers while the backlog keeps ballooning. A **finite queue bound** is an essential part of overload design.

### Rejection Policies

- **`AbortPolicy`** (JDK): throws `RejectedExecutionException`; `ThreadPoolTaskExecutor` surfaces rejection per Spring's `TaskRejectedException` contract.
- **`CallerRunsPolicy`**: if the executor has not shut down and cannot accept the task, the submitting thread may **run the task itself**. On a Servlet request thread, that can block for a long time; unsuitable when fast, predictable error responses are needed.
- **`DiscardPolicy`/`DiscardOldestPolicy`**: dangerous for business logic because tasks can be dropped without the caller knowing the outcome, especially if acceptance was already promised.
- You can write a custom policy, provided it clearly defines when work is accepted, when errors are reported, and who owns retries.

By default, `ThreadPoolTaskExecutor` is not a durable queue. A task already inside the in-JVM queue can be **lost if the process dies**. Rejecting when full is one layer of defense, not a final execution guarantee.

### Spring Bean Example With Explicit Bounds

These are configuration files for a Spring Boot 3.x/Java 17+ application with `spring-boot-starter-web` (or equivalent Spring Context).

**`src/main/java/com/example/overload/ExecutorConfig.java`**:

```java
package com.example.overload;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ExecutorConfig {

    @Bean("shortTaskExecutor")
    public ThreadPoolTaskExecutor shortTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("short-task-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

**`src/main/java/com/example/overload/AdmissionService.java`**:

```java
package com.example.overload;

import java.util.concurrent.Semaphore;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class AdmissionService {
    // Caps total accepted and unfinished tasks on this instance.
    private final Semaphore capacity = new Semaphore(24);
    private final ThreadPoolTaskExecutor executor;

    public AdmissionService(
            @Qualifier("shortTaskExecutor") ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public boolean trySubmit(Runnable action) {
        if (!capacity.tryAcquire()) {
            return false;
        }
        try {
            executor.execute(() -> {
                try {
                    action.run();
                } finally {
                    capacity.release();
                }
            });
            return true;
        } catch (TaskRejectedException rejected) {
            capacity.release();
            return false;
        }
    }
}
```

In this example, concurrency admission effectively caps **total accepted work (running + queued)** at 24 per instance, matching the 8-worker plus 16-queue ceiling under full load. This is an **in-memory guard**, not a job store.

- A controller can call `trySubmit` and return `503` on `false` for general overload, or `429` when rejected by a caller-specific quota. Ensure the success contract matches the job type and the application's tracking model.
- Do **not** return `202` claiming a durable guarantee simply because `trySubmit()` returned `true`: the task lives in the JVM and can vanish on a crash.
- If `action.run()` fails, the permit is still released, yet the business error must be logged/recorded by a separate mechanism. There is no job-status store in this minimal example.
- `Semaphore` is scoped to one bean instance. Multiple replicas require alignment with real resource limits or a cluster-wide limit.
- Do not wrap an `@Async` task in a semaphore and hold the permit on the **request thread** across an indeterminate lifecycle. Choose exact acquire/release boundaries carefully to avoid leaking permits on rejection, cancellation, or timeout.

### Spring Exception → Intentional HTTP Mapping

If submission is rejected, a controller or `@RestControllerAdvice` can map `TaskRejectedException` to `503` for general overload; however, do **not** blindly map every `IllegalStateException` or `Exception` to `503`. Pair this with a justified `Retry-After`, logs/metrics, and stable error codes. Tasks already accepted that fail later **cannot** rewrite an HTTP response that was already sent.

## 6. When Must Work Be Persisted Durably?

Choose a durable job when **the work is valuable and must survive the request/JVM lifecycle**, such as long report exports, reconciliation, on-demand document generation, batch processing, contract generation, or multi-step workflows. When clients can poll for results later, the API can return `202 Accepted` with a job ID.

Contract sample:

```http
POST /reports
Idempotency-Key: request-2026-0001
Content-Type: application/json

{"period":"2026-09"}
```

```http
HTTP/1.1 202 Accepted
Location: /jobs/8b4f
Content-Type: application/json

{
  "jobId": "8b4f",
  "status": "QUEUED",
  "statusUrl": "/jobs/8b4f"
}
```

```http
GET /jobs/8b4f

HTTP/1.1 200 OK
Content-Type: application/json

{
  "jobId": "8b4f",
  "status": "RUNNING",
  "attempts": 1
}
```

The IDs and payloads above are **illustrative**, not responses from a demo server. `202 Accepted` per RFC 9110 means accepted for processing **without yet being completed**, and the eventual outcome may succeed or fail. Provide a status resource for clients to poll; `200` on `GET` only proves **reading the status** succeeded, not that the job `SUCCEEDED`.

### Where Is the "Accepted" Boundary?

Four situations must be kept separate:

1. **Placed into an in-memory `ThreadPoolTaskExecutor`:** only guarantees temporary acceptance by the delegate at call time; unsafe across crashes.
2. **Written a job record to the DB and committed:** the job is durably stored per the database's commit guarantee and can be recovered/claimed after a restart.
3. **Broker confirmed the message is stored under real durable settings:** can be consumed later; distinguish a successful confirmed publish from merely calling send. Durability depends on broker/quorum/replication/ack policies.
4. **Business side effects completed:** actual business completion; retries and duplicate processing can occur unless designed to be idempotent.

If the contract prohibits losing jobs, **return `202` only after durable persistence succeeds**. If the DB commit fails or the broker has not acknowledged the message under required guarantees, report an appropriate failure or indeterminate status; never generate an in-memory `jobId` and promise guaranteed processing.

### Simple Job Persistence Flow

```text
Client -> API (auth/validate/quota)
              |
              | BEGIN TRANSACTION
              v
       jobs(status=QUEUED) ----+----> outbox(event=PROCESS_JOB)
              |               |
              +--- COMMIT -----+
                       |
                       +----> HTTP 202 + jobId
                       |
               Outbox publisher
                       |
                       v
                  Message broker
                       |
                       v
              Worker (claim/dedupe)
                       |
                       v
            jobs: RUNNING -> SUCCEEDED/FAILED
                       |
                       v
                GET /jobs/{jobId}
```

A worker can use the DB directly as a queue at an appropriate scale, using **claim/lease** mechanics and orphan-job recovery. A broker decouples producers/consumers and smooths distribution, yet does not eliminate the need for backlog control, idempotency, and status tracking.

## 7. Transactional Outbox to Avoid Losing Work Between DB and Broker

A common bug:

```text
1. INSERT job into DB and COMMIT.
2. Publish message to broker.
3. Return HTTP 202.
```

If the process dies between steps 1 and 2, the DB has a `QUEUED` job that the broker never knows to run. Reversing the order—publishing before commit—is also dangerous: a worker might execute for a transaction that subsequently rolls back.

**Transactional outbox** writes the job and the event to publish **in the same DB transaction**:

```sql
-- PostgreSQL: illustrative schema, simplified to focus on invariants.
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_job_idem UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE job_outbox (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id),
    event_type VARCHAR(40) NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Inside one transaction, upon receiving a new request:

```sql
BEGIN;

WITH inserted AS (
    INSERT INTO jobs (
        id, tenant_id, idempotency_key, request_hash, status
    )
    VALUES (
        :job_id, :tenant_id, :idempotency_key, :request_hash, 'QUEUED'
    )
    ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
    RETURNING id
)
INSERT INTO job_outbox (job_id, event_type, payload)
SELECT id, 'PROCESS_JOB', jsonb_build_object('jobId', id)
FROM inserted;

COMMIT;
```

This is a **PostgreSQL SQL sample using named parameters** (`:job_id`, ...) bound by a framework/JDBC client; it will not run verbatim in `psql` without parameter substitution/binding. Request-handling logic must distinguish a **new insert** from a **duplicate idempotency key**:

- On a new insert, the outbox is written in the same transaction; only after `COMMIT` is `202` + job ID returned.
- On conflict on `(tenant_id, idempotency_key)`, look up the existing job **for the same tenant** and compare request hashes. If payloads match, return the same job ID; if different, return `409 Conflict` or a contract error for reusing a key with different content.
- Ensure rechecks handle transaction races while preserving authorization and tenant scoping; do not merely see `affectedRows=0` and create another job.
- Workers/publishers must tolerate duplicate events caused by retries/crashes. Outbox prevents **message loss from the DB-then-publish gap**, yet does not deliver exactly-once side effects.

A typical publisher reads unpublished outbox rows, claims them via lock/lease, publishes with broker confirmation, and marks `published_at` after confirmation. If publishing succeeds but the publisher crashes before writing `published_at`, the event may be **republished**. That is why consumers must be idempotent.

**Do not equate "has a DB row" with "the job is guaranteed to finish"**. The DB can still fail or fill up; workers may hit permanent failures; payloads may become stale/invalid. "Durable" refers to persisting and recovering responsibility for accepted work, not guaranteeing business logic always succeeds.

## 8. Workers, Retries, Idempotency, and Crash Recovery

A job typically transitions through states:

```text
QUEUED -> RUNNING -> SUCCEEDED
              |
              +-> RETRY_WAIT -> QUEUED
              |
              +-> FAILED
              |
              +-> CANCELLED (if business supports cancellation)
```

When reliable processing is needed:

- **Single claim at a time:** one worker atomically moves an eligible job from `QUEUED` to `RUNNING` (or uses a queue consumer ack contract). DB implementations can use row locking/leases; prevent two workers from claiming the same job normally.
- **Lease/heartbeat:** if a worker dies while a job is `RUNNING`, the job can be reassigned after the lease expires; a revived old worker needs fencing/version checks if late writes are possible.
- **Ack at the right time:** never ack a broker message before business effects and status are persisted per contract, since crashing in between loses processing responsibility. Acking after commit means messages may be redelivered, which consumers must tolerate.
- **Classified retries:** transient failures (network timeouts, downstream overload) can retry with exponential backoff + jitter; permanent failures (invalid payload, missing permissions, missing data) must end in `FAILED` with an explanation.
- **Retry caps:** `maxAttempts`, retry deadline, dead-letter queue, or `FAILED` state; jobs must never loop infinitely and clog the queue.
- **Idempotent side effects:** perform versioned state transitions; use unique business keys, dedupe tables, or downstream-supported request IDs. Sending emails, charging cards, or firing webhooks can duplicate if failure happens right after the side effect and before ack.
- **Out-of-order & cancellation:** on late status updates, enforce valid transition conditions and versions. `CANCELLED` must never be overwritten to `SUCCEEDED` by a stale worker.
- **Result retention:** define how long `GET /jobs/{id}` remains valid, where result files live, tenant data protection, download expiration, and controlled cleanup.

### There Is No Free "Exactly Once"

Suppose a worker calls a partner to charge a payment; the partner charges successfully, yet the response is lost to a network timeout. Not knowing the charge succeeded, a retry may charge a second time. The fix is an **idempotency key at the side-effect boundary**, or partner reconciliation; putting messages in a durable queue alone does not solve this problem.

The same applies to sending emails, money transfers, data writes, and webhooks. Distinguish:

- **At-most-once attempt:** can lose work, fewer duplicates.
- **At-least-once delivery:** reduces loss via retries/acks, yet events can repeat.
- **Exactly-once business effect:** requires idempotency/transactions/fencing or appropriate business design across all involved systems; never assume it just because a broker advertises a delivery feature.

## 9. Standalone Java 17: Two Quick Defensive Patterns

To observe **rejection when an executor is full** and **capping concurrent executions**, this example uses only the JDK, without Spring. It does not simulate durable storage: durability must be proven with a real DB/broker and crash/restart tests, not by renaming an in-memory `List` to "durable queue."

Save the full program to **`OverloadDecisionDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class OverloadDecisionDemo {

    static boolean rejectWhenExecutorFull() throws Exception {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);

        try {
            Future<?> running = executor.submit(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!workerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker was not started");
            }

            // Sole worker is waiting; this task takes the 1 queue slot.
            Future<?> queued = executor.submit(() -> { });

            boolean rejected = false;
            try {
                executor.execute(() -> { });
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            releaseWorker.countDown();
            running.get();
            queued.get();
            return rejected;
        } finally {
            releaseWorker.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    static void limitConcurrentAdmissions() {
        Semaphore gate = new Semaphore(2);

        boolean first = gate.tryAcquire();
        boolean second = gate.tryAcquire();
        boolean third = gate.tryAcquire();

        System.out.println(
                "admit=" + first + "," + second + "," + third);

        if (first) {
            gate.release();
        }
        boolean retry = gate.tryAcquire();
        System.out.println("admitAfterRelease=" + retry);

        if (second) {
            gate.release();
        }
        if (retry) {
            gate.release();
        }
        System.out.println("availablePermits=" + gate.availablePermits());
    }

    public static void main(String[] args) throws Exception {
        System.out.println(
                "executorRejected=" + rejectWhenExecutorFull());
        limitConcurrentAdmissions();
    }
}
```

Run with JDK 17+:

```bash
javac OverloadDecisionDemo.java
java OverloadDecisionDemo
```

**Deterministic stdout when the program finishes normally:**

```text
executorRejected=true
admit=true,true,false
admitAfterRelease=true
availablePermits=2
```

Explanation:

1. The sole worker is held on a latch and the sole queue slot is occupied. The third task is refused, so `AbortPolicy` throws `RejectedExecutionException`: `executorRejected=true`. In Spring's `ThreadPoolTaskExecutor`, the corresponding Spring-contract exception is typically `TaskRejectedException`.
2. The Semaphore has 2 permits; the first two calls succeed, while the third is rejected immediately: `true,true,false`.
3. After releasing one permit, a new attempt succeeds; finally all acquired permits are released so `availablePermits=2`.
4. Ordering is controlled by latches so results **do not depend** on thread scheduling during normal execution; do not use sleep durations to guess outcomes.

**Do not take throughput numbers from this tiny program** to size production pools: it is an admission/rejection property demonstration. For real load tests, include request traffic, downstream calls, wait times, queue age, timeouts, and crash scenarios.

## 10. Choosing the HTTP Response for Each Situation

A handy design reference:

| Situation | Usually appropriate response | Has the work been accepted? |
| --- | --- | --- |
| Tenant exceeded 100 requests/min quota, no job created | `429` + quota code; optionally `Retry-After` | No |
| CPU/worker pool saturated, deadline cannot be met | `503`; optionally `Retry-After` | No |
| DB-protecting semaphore out of permits | `503` for shared capacity limit, or `429` for caller-specific limit | No |
| Submitted to in-memory executor, API promises only best-effort | Can be `202` if contract clearly documents guarantees and tracking | Accepted in **RAM**, may be lost on crash |
| DB job + outbox committed, work will run later on workers | `202 Accepted` + `Location`/job ID | **Durably** accepted, not yet completed |
| DB commit failed before confirming job acceptance | Appropriate `5xx`, must not claim durable `202` | Possibly unaccepted; handle uncertain responses |
| Client retries with same idempotency key and same payload | Return same existing job and state per contract | No duplicate job created |
| Client reuses same key with different payload | `409 Conflict` or contract error | No new job accepted |
| Job finished processing with a business failure | `GET /jobs/{id}` returns `200` with `FAILED`, or dedicated status API | Previously accepted, now has failed outcome |

**Note on uncertain failures:** sometimes the DB **already committed** yet the connection between DB and API failed before the API saw the result, or the `202` response was sent yet the client timed out. In that case you cannot conclude with certainty "not accepted." You need **idempotency keys + status lookup** so clients can retry safely without creating duplicate jobs.

## 11. Strategy Selection Scenarios

### Scenario A — Product Recommendation API Must Respond Within 200 ms

If CPU computation or downstream calls take longer than the deadline, a long queue renders responses useless. Choose **in-flight request concurrency limits**, a very short queue or no queue, and reject under overload. Clients can use cached/fallback responses per contract; there is no need for durable jobs if a result is worthless a minute later.

### Scenario B — Accounting Report Export Taking 5 Minutes

Users should not hold an HTTP connection open for 5 minutes; losing requests on a restart is unacceptable. Choose **DB job persistence + outbox/worker**, returning `202` + status. Still enforce per-tenant quotas and backlog limits; when the DB cannot store jobs or backlog exceeds committed bounds, return `429`/`503`.

### Scenario C — High-Volume Marketing Notifications

Tasks can run later, yet the email provider's rate limit is very low. Choose a durable queue, rate-limited workers (token bucket/concurrency cap), retries, and idempotency. If the provider has an outage, do not grow workers/queues indefinitely; use a circuit breaker, back off retries, and enforce campaign TTLs.

### Scenario D — Placing an Order With Only One Item Remaining in Stock

If overload causes two concurrent requests to place orders successfully, a queue alone does not protect inventory invariants. You need **DB transactions/conditional updates** and idempotency on order creation; choose synchronous or durable jobs depending on transaction contract. Never promise success when merely recording a job: `202` only means accepted, not confirmed stock allocation.

### Scenario E — Multi-Tenant System With One Bursting Customer

Choose per-tenant rate limits (`429`), bulkheads protecting shared resources, and queue fairness/priority if using durable jobs. Local `Semaphore` limits across 10 replicas must be reasoned about as **aggregate admission**; if you need a 200 jobs/minute system-wide quota, use a shared counter and distributed rate-limiting algorithm.

## 12. Operations: Where to Read Overload Signals?

Measure both **ingress rate** and **completion capability** simultaneously:

- **Request ingress:** rate per endpoint/tenant, `429`/`503`/`202` statuses, API p95/p99, timeouts, and retry rate.
- **Executor:** `activeCount`, pool size, queue depth, **oldest job age**, rejection count, pre-execution wait time, runtime by task type.
- **Downstream:** connection pool active/pending, p95 latency, timeouts, rate limits, circuit breaker open counts.
- **Durable jobs:** counts in `QUEUED`, `RUNNING`, `RETRY_WAIT`, `SUCCEEDED`/`FAILED` ratio, attempt counts, backlog age, dead-letters, lost heartbeats, outbox lag, time from `202` to completion.
- **Infrastructure:** CPU throttling, memory, GC pauses, file descriptor/socket exhaustion, disk, and DB storage.
- **Fairness:** backlog and rejections per tenant/priority, preventing one group from starving others.

Some signals and responses:

| Observation | Possible cause | Action to consider |
| --- | --- | --- |
| High active threads, queue climbing steadily | Arrival > completion or slow downstream | Admission/rate limits, reduce work, genuinely scale capacity |
| Spare CPU, most workers waiting on JDBC connections | DB pool or query bottleneck | Cap concurrency, optimize queries, align pool with DB |
| `503` drops yet p99 spikes after growing the queue | Shifted pressure into wait time | Shrink queue to match deadlines, report overload early |
| Outbox growing, broker/workers not consuming | Publisher error, broker unavailable | Recover publisher, monitor lag, stop admitting past quota |
| `FAILED`/retries spike after an outage | Retry storm or downstream still fragile | Backoff + jitter, retry caps, circuit breaker |
| Queue nearly empty yet CPU saturated | Workers doing CPU-heavy work | Cap CPU concurrency, profile code, avoid oversubscription |

**SLOs also differ by strategy:**

- Early error return: intentional rejection probability, rejection response latency, keeping the server from collapsing.
- Admission control: accepted/rejected ratio, permit wait time, and isolation between workload groups.
- Durable jobs: percentage of accepted jobs surviving restarts, end-to-end completion latency, outbox publish lag, retries, and stuck jobs.

Do not optimize solely for "high HTTP 2xx rate." An API returning thousands of `202` responses while jobs never run can be worse than rejecting early at the right time.

## 13. Common Mistakes

| Misconception / bad implementation | Consequence | Fix |
| --- | --- | --- |
| "The longer the queue, the better" | OOM, timed-out requests, multi-minute latency | Bound it based on deadlines and throughput |
| Very large `maxPoolSize`, but unbounded queue | Pool does not scale as expected, backlog still grows | Understand queue-before-grow; align core/max/queue |
| Returning `202` right after `executor.execute()` and calling it *durable* | Crashes lose jobs promised for processing | Commit job/outbox or durable broker before `202` |
| Returning `429` for every backend error | Clients blamed even when server/DB is saturated | Separate caller quotas from server overload |
| `CallerRunsPolicy` for CPU-heavy requests | Request threads run tasks, sudden latency spikes | Pick policy by SLO, consider `AbortPolicy` + rejection |
| Catching every exception and returning `503` | Hides programming/permanent bugs | Map only genuine capacity/overload errors |
| Infinite retries, no jitter | Retry storm, amplifies outages | Retry budgets, backoff, deadlines, dead-lettering |
| Token bucket alone without capping in-flight work | Few requests running very long still exhaust workers | Combine concurrency limits and timeouts |
| Per-instance semaphore only when quota is cluster-wide | Total admitted exceeds intended quota | Budget allocation or shared rate-limiting mechanism |
| Publishing message outside transaction after DB commit | Crash in between leaves unconsumed jobs | Transactional outbox / DB queue |
| Treating a message broker as automatically exactly-once | Duplicate side effects on redelivery | Idempotent consumers, deduplication, transactions/fencing |
| Acking before updating status/processing | Crash loses processing responsibility | Ack per contract after durable persistence |
| No mechanism to reclaim `RUNNING` after worker crash | Jobs stuck forever | Leases/heartbeats/reconciliation |
| No authorization checks on `GET /jobs/{id}` | Leaks results/metadata of other tenants | Enforce authz and tenant scoping on every operation |
| Using sleep-based tests for production sizing | Misestimates CPU/DB/network limits | Load test with real traffic and dependencies |

## 14. Pre-Deployment Design Checklist

1. **Document the contract:** does the client need the result in the current response or can it take a `jobId`? When is `202` emitted? Are job losses across restarts allowed?
2. **Establish budgets:** real throughput, latency SLOs, queue wait, RAM, CPU, DB connections, broker throughput, and partner limits.
3. **Classify overload:** per-caller quota → `429`; shared temporary capacity exhaustion → `503`; `202` only when work is genuinely accepted.
4. **Set rate/concurrency/queue caps:** enforce limits where resources are consumed; control totals across instances.
5. **Configure executor policies:** core, max, queue, rejection handler, timeouts; check whether `CallerRunsPolicy` could block request threads.
6. **If durable:** persist job and outbox atomically, return the same job on retries with the same idempotency key, publish with confirmation, ensure idempotent consumers.
7. **Handle crash windows:** after commit before response, after publish before ack, after side effect before `SUCCEEDED`, worker death while `RUNNING`.
8. **Configure TTL, retries, and cancellation:** keep diagnosable failure states, dead-lettering, result access control, and old-data cleanup.
9. **Measure and test:** traffic past capacity, bursts, DB/broker downtime, restarts, multiple replicas, client retries, downstream latency, and per-tenant quotas.
10. **Security review:** authentication, authorization, payload limits, quota fairness, personal data in jobs/outbox, secret handling.

## 15. Self-Check Questions

**1.** An API receives 200 requests/second yet processes only 80 requests/second for hours. Should you just raise the queue to 1 million?  
**Answer:** No. The backlog accumulates and wait time rises continuously. You must increase real capacity, reduce work, or limit/reject admissions.

**2.** A tenant exceeds 20 POST/minute while the server remains healthy. Which status code should be returned?  
**Answer:** Usually `429 Too Many Requests` with a quota code, optionally `Retry-After` if the reset window is known.

**3.** The worker pool is full due to downstream timeouts and can no longer accept tasks. Which status code should be returned?  
**Answer:** Usually `503 Service Unavailable` for temporary overload; ensure rejected requests were never recorded as accepted.

**4.** Why does a `Semaphore(10)` in each replica of a 6-replica cluster not guarantee at most 10 concurrent tasks overall?  
**Answer:** Each replica has 10 independent permits; theoretically the cluster can reach 60.

**5.** Will `ThreadPoolTaskExecutor(core=4,max=12,queue=200)` scale up to 12 workers before the queue fills?  
**Answer:** Normally no. Once core is reached, the queue is used first; workers scale past core only when the queue cannot accept more.

**6.** An API returns `202` right after putting work into an in-memory queue, then the JVM dies. Does this satisfy "jobs must not be lost"?  
**Answer:** No. You need a durable store or broker with proper acknowledgment before accepting responsibility.

**7.** The DB saves a job successfully, yet broker publishing fails between the two steps. How do you prevent "forgotten jobs"?  
**Answer:** Save job + outbox in a single DB transaction, use a republishing relay and idempotent consumers; or use a durable DB queue/alternative design with explicit recovery.

**8.** A broker delivers the same message twice due to a crash after a side effect and before ack. Can duplicate side effects be prevented by queue configuration alone?  
**Answer:** Not enough; use idempotency keys, deduplication, and/or transactions/fencing at the side-effect boundary.

**9.** Should you send `Retry-After: 5` when you have no idea whether the service will recover in 5 seconds?  
**Answer:** Only publish it when justified; if unknown, do not fabricate a recovery time. Clients still need backoff/jitter per policy.

**10.** A job has been `RUNNING` since yesterday and its worker died. What is missing?  
**Answer:** Leases/heartbeats and a reclaim/reconciliation process. Durable jobs do not self-recover if state remains stuck.

## 16. Key Takeaways and References

The three options answer three different questions:

- **Return errors early:** the system **did not accept** this work; the client learns when/under what conditions it may retry. Use `429` for caller quotas/rate limits and `503` for temporary service overload per contract.
- **Limit further admission:** the system only admits within **rate, concurrency, queue, and downstream** budgets it can serve; once budgets are spent, it rejects explicitly.
- **Persist work durably:** the system **accepts responsibility for later processing** after safe persistence; returns `202` and a job ID, with state tracking, retries, dedupe, and recovery. It does not promise the business task has already completed.

Official sources:

- [RFC 9110 — 202 Accepted](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3), [503 Service Unavailable](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.6.4), and [Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).
- [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).
- [Spring Framework — `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html).
- [Java SE 17 — `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).
- [Java SE 17 — `Semaphore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html).