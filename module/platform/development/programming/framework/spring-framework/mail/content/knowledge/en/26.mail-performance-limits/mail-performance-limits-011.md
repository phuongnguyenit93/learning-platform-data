# Backpressure in Mail Sending Queues

In a **Spring Framework Mail** application, offloading email sending to a queue prevents HTTP requests from blocking on `JavaMailSender.send(...)`. However, adding a queue does not automatically solve performance problems. If the application generates emails faster than the SMTP provider can accept them, pending jobs grow continuously. Once memory, storage, or provider limits are exceeded, the system can stall, delay critical emails, trigger retry storms, and eventually degrade unrelated business operations.

**Backpressure** is the mechanism for signaling or enforcing limits when consumers cannot keep up with producers. In a mail pipeline, the goal is keeping unprocessed work within manageable bounds, protecting the SMTP provider, protecting application resources, and maintaining predictable behavior under overload.

An important principle:

> **A queue absorbs temporary load spikes; backpressure decides what the system does when the mismatch persists.**

This lesson covers bottleneck sources, calculating sending capacity, bounded queues and admission control, configuring `ThreadPoolTaskExecutor` for `@Async`, controlling workers with a durable queue/outbox, per-SMTP-route rate limiting, retries with backoff, fairness across tenants/email types, metrics observability, and testing under overload.

## 1. What does backpressure mean in an email-sending system?

An email can pass through this chain:

```text
HTTP / Business event / Scheduler
              |
              v
      Create mail request
              |
              v
       Queue / Outbox
              |
              v
           Workers
              |
              v
       Render + MIME build
              |
              v
     JavaMailSender.send(...)
              |
              v
       SMTP provider
              |
              v
      Downstream delivery
```

The producer generates send demand. The consumer is the worker processing jobs and submitting to SMTP. **Backpressure** arises when consumers or the provider cannot process as fast as producers enqueue jobs.

Examples:

- A campaign generates 20,000 emails in a few minutes.
- The SMTP provider accepts only a fixed number of submissions per second.
- Inline images and large attachments make each send take longer.
- Network trouble raises SMTP connection times from hundreds of milliseconds to several seconds.
- The provider responds temporarily with 4xx codes or applies throttling.
- Workers restart or fail to claim jobs from the database.
- One tenant sends excessive volume, slowing down another tenant's emails.

Without backpressure, upstream layers can keep producing jobs even after backlog exceeds capacity.

### Backpressure is not just retry

**Retry** reattempts a failed job. **Backpressure** limits the rate of creating, accepting, or executing work so the system does not overload. Uncontrolled retries can *worsen congestion* because failed jobs keep re-entering the queue.

### Backpressure does not always mean rejecting email

Depending on architecture, responses to overload can include:

1. **Slowing producers** safely within bounds.
2. **Deferring acceptance** and returning overload feedback.
3. **Persisting durably for later processing** while storage capacity remains.
4. **Capping workers/SMTP connections** so quotas are not exceeded.
5. **Prioritizing or lane-isolating** urgent emails.
6. **Rejecting new work** under an explainable policy.
7. **Pausing non-critical send groups** until backlog shrinks.

Never assume "we have a queue so we can accept unlimited load." An unbounded queue merely shifts the failure point to memory, the database, the broker, or the provider.

## 2. Distinguishing limits at each layer

A mail pipeline has several finite resources:

| Layer | Common limits | Consequence if exceeded |
|---|---|---|
| HTTP ingress | Request threads, connection pool, rate limits | Delayed or rejected requests |
| Template rendering | CPU, heap, caches, input data | Slow rendering, heap pressure |
| MIME/attachments | Memory, file descriptors, I/O | OOM, slow file reads, failed attachments |
| In-memory executor | Threads, queue capacity | `TaskRejectedException`, lost work on process crash |
| Database outbox | Disk, write throughput, indexes, locking | Slow transactions, full storage |
| Message broker | Queue depth, disk, unacked messages | Overloaded broker, consumer lag |
| SMTP transport | Connections, network, TLS handshakes | Timeouts, socket exhaustion |
| SMTP provider | Messages/s, recipients/s, hourly/daily quota | 4xx throttling, blocks, or suspension |
| Receiving systems | Recipient/domain rates, reputation | Deferrals/bounces, delayed delivery |

Backpressure must target the **real bottleneck**, not merely thread counts. If the SMTP provider limits throughput to 10 messages/s, raising workers from 5 to 100 does not remove that limit. It can open more connections, trigger throttling, and inflate retries and queues.

### A key design question

When the API says "accepted email send request", what did the system actually do?

- Merely added a `Runnable` to an in-memory queue?
- Committed an outbox row?
- Broker confirmed a durable publish?
- Worker started an attempt?
- SMTP accepted the message?

Each milestone offers a different reliability guarantee. Backpressure must keep the **request-acceptance contract** clear when queues fill up or providers fail.

## 3. Calculating arrival rate vs. processing capacity

Use two quantities:

- \(\lambda\): mail job arrival rate, in messages/second.
- \(\mu\): mail job processing capacity, in messages/second.

If the system is stable and on average \(\lambda < \mu\), backlog can drain after bursts. If \(\lambda > \mu\) persistently, backlog grows roughly with the difference between the two rates.

\[
\Delta Q \approx (\lambda-\mu)\cdot \Delta t
\]

where \(Q\) is the number of waiting jobs and the formula is an estimate when rates are relatively steady.

### Insufficient capacity example

Suppose:

- The system generates an average of **30 emails/second**.
- Each worker processes **2 emails/second**.
- There are **10 workers**.

Before other constraints, nominal capacity is:

\[
\mu = 10 \times 2 = 20\ \text{emails/second}
\]

Backlog grows by roughly **10 emails/second**. After 10 minutes:

\[
Q \approx 10 \times 600 = 6000\ \text{emails}
\]

Without slowing producers or expanding real capacity, the queue keeps growing.

However, if the provider only allows **15 emails/second**, even adding workers caps usable capacity at 15 emails/second. You must consider workers, network, and provider quotas together.

### Little's Law and queue latency

In steady state, Little's Law states:

\[
L = \lambda \times W
\]

where \(L\) is the average number of items in the system, \(\lambda\) is actual throughput, and \(W\) is average time in the system.

For instance, if a system steadily handles 10 emails/second and each job takes 5 seconds on average from entry to completion, roughly 50 jobs reside in the system at any time.

**Never use Little's Law to claim an unboundedly growing queue has stable wait times.** When producers outpace consumers persistently, latency grows with backlog.

### Measure instead of guessing

Metrics to measure in real environments:

- Arrival rate by notification type.
- SMTP attempts per second and accepted rate.
- P50/p95/p99 duration of an attempt.
- Queue wait latency and oldest waiting job age.
- Concurrent SMTP connections.
- Provider throttling/4xx rate.
- Average message size and attachment size distribution.

Choose queue and concurrency limits from these measurements, not CPU core counts alone.

## 4. The system needs a backlog budget

Queues can absorb brief bursts. However, the system must define upfront its **maximum backlog** and **maximum acceptable latency**.

Example:

| Email category | Illustrative operational target | Policy direction |
|---|---|---|
| OTP / login | Very latency-sensitive; expiring tokens | Priority lane, dedicated quota, disallow long waits |
| Password reset | High priority, needs abuse protection | Per-account/IP admission and rate limits, explicit expiry |
| Order confirmation | Can tolerate short wait, needs reliability | Durable outbox, bounded retries |
| Scheduled reports | Can wait minutes or longer | Batched queue, concurrency/rate limits |
| Marketing / newsletter | High volume, must not starve transactional | Dedicated queue/budget, scheduling, suppression |

Real timings must come from SLAs, security requirements, and provider capacity; the table only shows classification.

A job with a business TTL must not be sent after losing relevance. For example, an OTP expiring in a few minutes sits in the queue for tens of minutes: sending it causes confusion. Workers should enforce an **expire/cancel** policy and record proper state instead of blindly sending every queued job.

### Bounded backlog and admission

When queue depth exceeds a threshold, throttle or reject low-priority emails. For critical transactional mail, prefer capacity reservation or approved alternate routes before dropping jobs.

Never silently "drop" an important email while returning API success. If a request is rejected, return a clear status/exception; if persisted durably, return an ID for status lookup and retries.

## 5. In-memory queues differ from durable queues

Two common designs:

### 5.1. `@Async` with `ThreadPoolTaskExecutor`

```text
Caller -> executor queue (RAM) -> worker -> SMTP
```

Advantages:

- Simple to configure.
- No broker needed.
- Suitable for low-importance emails, low load, and cases where losing in-flight tasks on process death is acceptable.

Limitations:

- The queue vanishes on unexpected process exit.
- Callers may only know the task entered RAM.
- Once full, the executor must reject or run a rejection policy.
- Scaling replicas creates separate queues and concurrency, complicating global SMTP quota control.

### 5.2. Database outbox or durable broker

```text
Business transaction -> outbox/broker -> workers -> SMTP
```

Advantages:

- Send intents survive restarts if committed/published durably.
- Provides status, retry schedules, and auditability.
- Workers can pace throughput independently from API traffic.
- Enables backlog monitoring and crash recovery.

Limitations:

- Databases and brokers also have finite capacity.
- Requires claiming, acking, retries, leases, and deduplication.
- A durably stored job can still wait too long if capacity is insufficient.
- Risk of timeout after SMTP acceptance before status commit.

**A durable queue does not mean an infinite queue.** Enforce admission limits, retention, capacity management, and storage failure handling.

## 6. Bounded ThreadPoolTaskExecutor in Spring

`ThreadPoolTaskExecutor` is often paired with `@Async`. Example:

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class MailExecutorConfiguration {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("mail-");

        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(25);

        return executor;
    }
}
```

These values are illustrative. Key settings:

| Setting | Meaning |
|---|---|
| `corePoolSize` | Core workers maintained by the pool |
| `maxPoolSize` | Maximum workers when the pool scales up |
| `queueCapacity` | Maximum queued tasks in the executor |
| `RejectedExecutionHandler` | Rule when a task cannot be accepted |
| `threadNamePrefix` | Aids observability and debugging |
| `waitForTasksToCompleteOnShutdown` | Shutdown task-drain policy |
| `awaitTerminationSeconds` | Wait timeout on executor shutdown |

### Common pitfall: `maxPoolSize` is not used first

With positive-capacity queues typically used in `ThreadPoolTaskExecutor`, the pool:

1. Creates workers up to `corePoolSize`.
2. Places subsequent tasks into the queue.
3. Expands workers up to `maxPoolSize` only once the queue is full.
4. Rejects further tasks when no capacity remains.

Thus `corePoolSize=4, maxPoolSize=8, queueCapacity=10000` does not mean the system routinely runs 8 workers. It can stay at 4 workers while piling tasks into a massive queue, inflating wait times.

**Choosing queue capacity is a latency and backpressure decision**, not solely a memory decision.

## 7. Rejection policies are part of the API contract

When full, `ThreadPoolTaskExecutor` can throw `TaskRejectedException`. The application must define what that means for callers.

Common Java policies:

| Policy | General behavior | Risk for mail |
|---|---|---|
| `AbortPolicy` | Rejects with an exception | Must be handled and surfaced clearly, never swallowed |
| `CallerRunsPolicy` | Runs task on the calling thread if pool is busy and not shut down | Can turn HTTP requests into synchronous SMTP sends, cascading delays |
| `DiscardPolicy` | Drops task silently without error | Can lose emails silently |
| `DiscardOldestPolicy` | Drops oldest queued task to enqueue newest | Can drop critical emails and reorder work |
| Custom rejection handler | Application-defined rule | Must guarantee acknowledged work is never lost |

### Why does `CallerRunsPolicy` require special care?

`CallerRunsPolicy` creates backpressure by slowing the producer: when full, the submitting thread runs the task. This sometimes fits internal compute pipelines.

However, if the submitting thread is an HTTP request thread and the task calls `JavaMailSender.send`, the HTTP request suddenly waits on SMTP. Under concurrent load, this exhausts request threads, defeating the non-blocking goal of `@Async`.

Furthermore, once the executor shuts down, `CallerRunsPolicy` may **not execute the task**. Therefore, it cannot serve as the sole guarantee that an email send request was preserved.

### Why is `DiscardPolicy` especially dangerous?

An API might return `202 Accepted` after submitting to the executor even though the task was dropped. The caller assumes acceptance while no durable job exists to retry.

For important emails, prefer **explicit rejection** or **persisting to an outbox first followed by best-effort dispatch**, rather than silent drops.

## 8. Handling TaskRejectedException without lying to callers

Example service submitting directly to an executor:

```java
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class InMemoryMailSubmissionService {

    private final ThreadPoolTaskExecutor mailExecutor;
    private final MailWorker worker;

    public InMemoryMailSubmissionService(
            ThreadPoolTaskExecutor mailExecutor,
            MailWorker worker
    ) {
        this.mailExecutor = mailExecutor;
        this.worker = worker;
    }

    public void submit(MailCommand command) {
        try {
            mailExecutor.execute(() -> worker.send(command));
        } catch (TaskRejectedException exception) {
            throw new MailCapacityExceededException(
                    "Mail executor is full",
                    exception
            );
        }
    }
}
```

`MailCommand`, `MailWorker`, and `MailCapacityExceededException` are application-defined types.

If the caller is an HTTP endpoint, map overload errors to an appropriate status such as `429 Too Many Requests` or `503 Service Unavailable` per API contract, with retry guidance when appropriate. Never claim "sent" or "queued" if the executor rejected the task.

### Two issues still remain

1. The executor accepts the task, then the process dies before execution: the in-memory task is lost.
2. The request accepts the task, then SMTP fails after the HTTP response: the caller does not learn the outcome automatically.

Hence this pattern only suits low-durability emails. For transactional mail requiring intent guarantees, persist to an outbox first.

## 9. Outbox as a durable acceptance boundary

A sound model for business-critical flows:

```text
HTTP request / domain event
             |
             v
    Database transaction
       ├── Save business data
       └── Insert mail outbox(PENDING)
             |
             v
           Commit
             |
             v
       Return receipt
             |
             v
   Background poller / worker
             |
             v
       SMTP submission
```

With an outbox, callers receive a **notification ID** after commit while workers handle sending later. If workers are temporarily saturated, notifications stay `PENDING` instead of disappearing.

### Bounded admission at the outbox layer

The outbox can reject new requests when the system hits limits:

- Total `PENDING` rows globally.
- `PENDING` rows per mail type or tenant.
- Total payload/attachment storage size.
- Backlog age exceeding SLO.
- Database disk/latency above operational thresholds.
- Provider quota unable to meet business deadlines.

Admission checks must not rely on naive `SELECT COUNT(*)` followed by `INSERT` if you need **hard concurrency limits**, because two transactions can see remaining room simultaneously and both insert. Hard limits require atomic quota/slot reservations or appropriate transactions/locking.

In practice, use soft thresholds for early alerts and an admission guard tight enough to avoid exhausting maximum resources.

## 10. Best-effort dispatch after outbox commit

A design can use the executor as an "early-processing" nudge while keeping the **outbox as the source of truth**.

```java
public MailReceipt requestMail(MailCommand command) {
    // This method must commit the notification record
    // before returning.
    MailJob job = outboxService.createPending(command);

    try {
        mailExecutor.execute(
                () -> mailWorker.processById(job.id())
        );
    } catch (TaskRejectedException rejected) {
        // Do not delete the job and do not assume it was sent.
        // The periodic poller can still pick up PENDING jobs.
        log.info(
                "Mail dispatch saturated; outbox job remains pending"
        );
    }

    return new MailReceipt(job.id(), "QUEUED");
}
```

These types and methods are illustrative. In production, ensure:

- `createPending` actually commits before dispatch; calling inside a larger transaction can dispatch too early.
- `processById` claims with locking or concurrency guards against duplicate execution.
- Periodic polling recovers jobs missed by the executor.
- `QUEUED` means the outbox committed, **not that SMTP accepted the message**.
- Do not increment `mail.message.created` again when the same job retries.

### When the executor is full, do not try to "rescue" with recursion

Avoid writing:

```java
try {
    mailExecutor.execute(task);
} catch (TaskRejectedException rejected) {
    // Avoid: immediately calling again infinitely on the same request.
    submitAgain(task);
}
```

This can wedge CPU or threads without creating any extra capacity. If the job is already persisted durably, let pollers/workers handle it when capacity returns. If not durable, reject explicitly instead of looping endlessly.

## 11. Never claim more jobs than workers can process

With a database outbox, workers typically poll in batches. A common mistake is claiming 10,000 jobs, marking them `PROCESSING`, and then pushing them into an executor with a 100-task queue.

When the executor fills up:

- Many jobs are claimed yet sit unstarted.
- Leases can expire before SMTP even starts.
- Other workers may reclaim them and send duplicates.
- Jobs appear in-flight while actually sitting in yet another RAM queue.

A principle:

> **Claimed, unfinished jobs should match available worker slots, a small buffer queue, and lease policy.**

An implementation can:

1. Compute free worker slots.
2. Claim only that matching batch size.
3. Stop claiming when slots are full or the provider is out of quota.
4. Hold leases only while the job is actively progressing.
5. Persist outcomes before releasing slots.
6. During shutdown, stop claiming before draining in-flight tasks.

### Claiming with locking

Where the database supports it, workers can use row-locking techniques such as `SELECT ... FOR UPDATE SKIP LOCKED`, combining claiming and state updates in a transaction.

Syntax, isolation, and performance vary by database engine. Never treat a bare `SELECT` alone as sufficient ownership protection unless transactions and updates are designed consistently.

Include a `claimToken` or fencing/version check in case leases can expire while an older worker is still running.

## 12. Semaphore limiting concurrent in-flight attempts

Beyond a bounded queue, you can use a `Semaphore` to cap concurrent SMTP sends per **instance**.

Example:

```java
import java.util.concurrent.Semaphore;
import org.springframework.mail.javamail.JavaMailSender;

public final class LimitedSmtpGateway {

    private final JavaMailSender sender;
    private final Semaphore permits = new Semaphore(4);

    public LimitedSmtpGateway(JavaMailSender sender) {
        this.sender = sender;
    }

    public boolean trySend(MimeMessage message) {
        if (!permits.tryAcquire()) {
            // Caller must keep the job PENDING or reschedule later.
            return false;
        }

        try {
            sender.send(message);
            return true;
        } finally {
            permits.release();
        }
    }
}
```

In this example, `false` means **failed to acquire a slot to start**, not that SMTP rejected the message. In production, avoid conflating accepted, failed, and not-admitted into one boolean; separate admission result from `send` outcome.

### Semaphores do not replace rate limits

Capping at 4 concurrent connections does not mean sending only 4 emails/second. If each email finishes in 100 ms, four slots can drive many attempts per second.

Therefore distinguish:

- **Concurrency limit:** simultaneous in-flight attempts.
- **Rate limit:** attempts permitted to start per unit of time.
- **Quota limit:** total emails/recipients/bytes allowed per hour or day.
- **Backlog limit:** waiting jobs accepted into the queue.

Many systems need all four together.

## 13. Rate limiting per SMTP provider and route

SMTP providers enforce limits. If every replica sends at maximum speed, aggregate traffic can exceed the shared quota.

Example:

```text
Provider allows 20 submissions/second

Replica A  -> 15/s
Replica B  -> 15/s
Replica C  -> 15/s
---------------------
Total      -> 45/s (over quota)
```

An in-RAM limiter per instance does not enforce **system-wide** quotas.

### Token bucket

A common mechanism is a **token bucket**:

- The bucket holds up to a maximum number of tokens.
- Tokens refill at the allowed rate.
- Each submission spends tokens per policy.
- When empty, jobs wait or are rescheduled later.
- Short bursts are absorbed up to bucket capacity.

```text
Provider budget
    |
    v
Token bucket
    |
    +-- token available --> worker may submit
    |
    +-- no token --------> keep job pending / reschedule
```

Service-level logic example:

```java
public void processOne(MailJob job) {
    if (!quotaLimiter.tryAcquire(job.smtpRoute())) {
        outboxRepository.deferUntil(
                job.id(),
                quotaLimiter.nextAvailableTime(job.smtpRoute())
        );
        return;
    }

    smtpGateway.send(job);
}
```

`quotaLimiter` and `outboxRepository` are illustrative components. In production, handle **atomic quota allocation**, claim ownership, deadlines, and cases where a token was acquired yet the attempt never started.

### Distributed quotas

When multiple instances share one provider limit, options include:

- A dedicated worker pool managing that route.
- Token buckets backed by shared storage/coordination.
- Broker partitions or consumer groups with bounded concurrency.
- A dedicated mail-gateway service responsible for rate limiting.
- Static per-replica quota partitioning when replica counts are stable with headroom.

Never assume "20/s per instance" works if the provider only allows 20/s total. When autoscaling, adjust per-instance limits or use coordinated quotas.

## 14. Provider throttling is external backpressure

When an SMTP server returns temporary responses such as 4xx codes, that can signal provider overload or rate/policy throttling.

Responses like `421`, `451`, or `4.7.x` may relate to temporary unavailability or throttling, though exact meanings depend on the server and enhanced status codes.

Avoid reacting with:

```text
4xx -> retry immediately -> 4xx -> retry immediately -> ...
```

Instead:

1. Classify errors from the SMTP response and cause chain.
2. If the provider advertises a retry window, honor that guidance where appropriate.
3. Slow down the corresponding route.
4. Use exponential backoff with jitter and an attempt cap.
5. Keep notifications in durable storage.
6. Monitor accepted rate, 4xx rate, queue age, and provider quota.
7. Ramp speed back up gradually as the provider stabilizes.

**Do not treat every 4xx code as throttling.** It could be a recipient-level or transient network issue. Accurate classification prevents slowing an entire route due to one isolated failure.

## 15. Retry storms and their impact on backlog

A common queueing failure mode:

```text
Producer generates 100 jobs/s
          |
          v
Provider slows down
          |
          v
Workers fail 80 jobs/s
          |
          v
Immediate retry adds 80 jobs/s
          |
          v
Total effective demand = original + retries
          |
          v
Queue and provider overloaded further
```

When retries spike rapidly, **attempt** generation rate can far outstrip **logical notification** creation rate. Dashboards show high send traffic while newly delivered notifications stagnate.

### Per-attempt backoff

An illustrative schedule:

```text
Attempt 1 fails -> wait about 30 seconds
Attempt 2 fails -> wait about 60 seconds
Attempt 3 fails -> wait about 120 seconds
Attempt 4 fails -> stop or escalate by policy
```

These values are not Spring Mail defaults. Add jitter so workers do not all retry at the exact same instant when the provider recovers.

Example formula:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

where \(d_n\) is the base backoff delay and \(d_{\max}\) is the cap. Apply jitter afterward according to policy.

### Retries need business deadlines

Some emails lose all value if delivered late:

- Expired OTPs.
- Revoked password-reset links.
- Reminders for past events.
- Reports already superseded by newer versions.

Workers must check `expiresAt` or business conditions before retrying. Once expired, move the job to `EXPIRED` or `CANCELLED_BY_POLICY` instead of retrying endlessly.

### Dead-letter queues are not an automatic trash bin

Jobs exceeding retry limits can move to a DLQ or manual-intervention state. Still preserve:

- Failure reason and category.
- Notification ID and attempt history.
- Reprocessing permissions and workflow.
- Rate limits during replay.
- Retention and deletion policies for sensitive data.

If operators replay thousands of DLQ jobs at once without backpressure, the DLQ itself triggers a fresh overload.

## 16. Unknown outcomes and duplicate risk during retries

SMTP has a tricky failure case: the server may have accepted the message, yet the client loses the connection before receiving the final response after `DATA`.

```text
Worker                          SMTP server
  |---- MIME DATA ----------------->|
  |                                  |
  |                            Message accepted
  |                                  |
  X<--- connection lost ------------|
  |
  v
Timeout or MailException
```

At this point, it is uncertain whether submission succeeded. If backpressure increases timeouts and workers retry aggressively, recipients may receive multiple duplicates.

Distinguish outcomes:

| Outcome | Meaning | Handling |
|---|---|---|
| `SMTP_ACCEPTED` | Transport confirmation of success | Do not retry merely because no delivery event arrived yet |
| `KNOWN_REJECTED` | Evidence that the message was not accepted | Retry depending on error class |
| `UNKNOWN` | Uncertain whether SMTP accepted it | Reconcile if possible; controlled retry with duplicate risk |
| `EXPIRED` | Job lost business validity | Do not send per policy |

`MailException` is a broad exception hierarchy, not absolute proof that the email never left the application. Classify based on root cause, SMTP stage, and provider response where available.

### Scoped idempotency

An `idempotencyKey` prevents creating two logical notifications for the same business event. A `notificationId` should stay stable across retries; `attemptId` changes per attempt.

However, **outbox idempotency does not guarantee exactly-once delivery** between SMTP and the database. Do not expect keeping the same MIME `Message-ID` to make every mail server deduplicate duplicates.

## 17. Broker backpressure: RabbitMQ and consumer prefetch

When using RabbitMQ as a mail queue, pay attention to **prefetch** — how many messages the broker may deliver to a consumer before acknowledgment, depending on configured semantics.

If prefetch is too large:

- Consumers hold too many unacknowledged messages.
- Messages sit in consumer memory without worker slots.
- If a consumer crashes, large batches must be requeued.
- One consumer can hoard backlog, skewing work distribution.
- Unacked counts obscure true in-flight SMTP attempts.

A practical approach:

1. Bound consumer count and concurrency.
2. Set prefetch close to real processing capacity with a small measured buffer.
3. ACK only after completing the stage defined by contract.
4. On transient errors, schedule delayed retries or delay queues instead of immediate requeue.
5. Monitor ready messages, unacked messages, consumer count, and delivery rate.

### ACK as a reliability boundary

If the broker is the sole store for jobs:

- ACKing **before** durable SMTP attempt handling risks losing jobs on process crash.
- ACKing **after** SMTP acceptance allows broker redelivery if the worker dies before ACKing, causing duplicates.

This stems from having no distributed transaction between SMTP and the broker. Pair it with idempotency, attempt records, and clear retry policies.

If the broker only carries a wake-up signal ("new outbox row ready") while the database stores durable job state, ACK semantics can reflect signal receipt rather than email delivery. Be explicit about which store is the source of truth.

## 18. Kafka: consumer lag and processing throttling

With Kafka, distinguish carefully between:

- Producer successfully appending a record.
- Consumer fetching records.
- Worker submitting over SMTP.
- Committing offsets.

A consumer may poll batches while SMTP slows down. Blocking too long or failing heartbeat/poll intervals triggers consumer group rebalances. Uncommitted records can then be reprocessed, creating duplicate risk.

Options:

- Bound polled records per batch and queued jobs entering worker pools.
- Pause/resume partitions when worker capacity runs out.
- Keep calling `poll`/heartbeats appropriately while paused per the Kafka client contract.
- Manage offset commits cleanly alongside processing outcomes and partition ordering.
- Back retries with durable storage/idempotency rather than blocking partitions arbitrarily.
- Monitor consumer lag per partition and consumer group.

**Never commit offsets merely because a task was submitted to an in-memory RAM executor** if Kafka is the sole durable record of the mail request and crash recovery is required.

### Scaling consumers cannot outrun useful partitions

If a consumer group has few partitions, adding instances does not increase parallel consumption. Meanwhile, SMTP quotas remain the hard cap. Scale based on partition assignment, worker capacity, and provider limits.

## 19. Fairness: never let one tenant dominate the queue

A multi-tenant system can encounter:

```text
Tenant A: 50,000 campaign emails
Tenant B: 12 password resets
Tenant C: 200 order confirmations
```

With one shared FIFO queue dominated by A's backlog, emails from B and C wait behind tens of thousands of jobs despite being tiny and urgent.

Mitigations against starvation:

- Separate queues or topics by priority tier: transactional vs. bulk.
- Reserved worker/concurrency capacity for urgent traffic.
- Per-tenant enqueue quotas and dispatch quotas.
- Weighted fair scheduling or round-robin across tenants.
- Burst limits on large tenants.
- Deadline/expiry prioritization within lanes where suitable.

### Priority is more than an integer field

If every email tags itself `priority=HIGH`, prioritization collapses. Maintain a backend-owned priority catalog rather than trusting arbitrary client-sent priority flags.

Example:

| Tier | Examples | Rules |
|---|---|---|
| Critical transactional | OTP, password reset | Reserved capacity, short TTL, abuse protection |
| Normal transactional | Order confirmation, receipt | Reliable queue, bounded retries |
| Bulk / non-urgent | Reports, newsletters | Lower rate limit, scheduled, pausable |

Never let bulk campaigns consume slots reserved for security-critical mail. Conversely, protect OTP endpoints from spam and enumeration, because a priority lane does not mean accepting unbounded requests.

### Prevent indefinite starvation

Strict priority can starve bulk jobs indefinitely if critical traffic stays saturated. Maintain baseline fairness, quotas, or expiry policies, and monitor job age across every tier.

## 20. Send ordering and handling stale emails

Emails can have business ordering relationships:

- "Order Created" before "Order Cancelled".
- "New OTP Code" after "Old OTP Code".
- Reminder #1 before Reminder #2.

Backpressure and retries can invert order. An older failed job retried later may arrive after a newer one.

Decide upfront:

- Which emails tolerate out-of-order arrival?
- Is per-aggregate ordering (`orderId`/`accountId`) required?
- Can superseded older jobs be cancelled instead of sent?
- Should sequence/version numbers be checked right before sending?
- May notifications for the same recipient run concurrently?

Do not enforce global system-wide FIFO across all business flows; that severely hurts throughput and breaks across multiple brokers/replicas.

A practical pattern is storing `businessVersion` or `expiresAt` on the job and rechecking current state before sending emails that can become obsolete.

## 21. Attachments and MIME size affect backpressure

Not all emails cost the same.

A 2 KB plain-text email sends far faster than a 15 MB PDF email. Limiting only messages/s lets a handful of large files tie up workers and SMTP connections for too long.

Account for:

- MIME bytes after encoding.
- Template rendering cost.
- File/object-storage read cost.
- Number of attachments and data sources.
- Time to upload payloads over SMTP.
- Memory holding byte arrays.
- Provider quotas based on message size or recipient count.

Binary attachments are typically Base64-encoded, enlarging transmitted bytes relative to raw file bytes. Thus a 10 MB file limit does not mean the SMTP payload is 10 MB.

### Cost-aware scheduling

You can split lanes:

- Small transactional.
- Attachment-heavy.
- Bulk send.

Or apply a dedicated concurrency cap to large messages. Never let 8 workers all stall on huge attachments while tiny OTP emails wait behind them.

If bytes-in-flight bounds are needed, use weighted permits based on estimated size, though avoid over-engineering before measuring. Separate concurrency caps per email class are usually an easy first step.

## 22. Memory management: what belongs in the queue?

An anti-pattern:

```java
byte[] attachment = Files.readAllBytes(path);

mailExecutor.execute(() -> {
    sendMail(attachment);
});
```

When many tasks queue up, each `Runnable` retains a large byte array on the heap. A 100-task queue with 10 MB attachments holds huge heap memory before accounting for overhead.

A safer approach:

```text
Queue job:
  notificationId
  tenantRef
  templateVersion
  approvedAttachmentId
  storageKey/version

Worker when ready:
  -> load approved data
  -> build MIME
  -> send
  -> release resources
```

Keep **small metadata** in the queue; store attachments in durable storage with explicit access controls, versioning/retention, and read-size bounds. This also lets workers on any replica process the job.

However, do not put short-lived signed URLs in the queue and expect workers to fetch them hours later. Store internal storage keys/versions and resolve credentials when needed under policy.

## 23. Timeouts must align with concurrency

When SMTP slows down, every worker holds its slot longer. With fixed worker counts, throughput falls and backlog grows. Therefore, timeouts are part of backpressure.

Example configuration:

```yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "mail.smtp.auth": true
      "mail.smtp.starttls.enable": true
      "mail.smtp.starttls.required": true
      "mail.smtp.connectiontimeout": 5000
      "mail.smtp.timeout": 5000
      "mail.smtp.writetimeout": 5000
```

These millisecond values are illustrative. The three timeouts do not form a single overall attempt deadline; sending involves multiple read/write phases.

### Is adding more workers the answer?

When per-attempt latency rises, increasing concurrency can utilize I/O wait time, but it also:

- Increases open connections.
- Increases CPU/TLS/heap pressure.
- May breach provider concurrency quotas.
- Increases timeouts if the provider becomes overloaded.
- Raises the risk of retry storms.

Test with bounded concurrency steps while watching accepted throughput, p95/p99 latency, 4xx rates, and bytes-in-flight. Stop scaling up once throughput plateaus or error rates begin degrading.

## 24. Bulkheads and circuit breakers for SMTP routes

A system may use two SMTP providers: a transactional primary and a bulk provider. If the bulk provider slows down, it must not exhaust worker slots for the transactional route.

**Bulkheads** isolate resources:

```text
Mail dispatcher
    |
    +--> Transactional pool (reserved capacity)
    |       +--> SMTP route A
    |
    +--> Bulk pool (bounded)
            +--> SMTP route B
```

**Circuit breakers** temporarily pause calls to a route when failure rates exceed policy thresholds. Opening a circuit must be paired with proper job handling:

- Do not drop jobs.
- Keep them `PENDING`/`DEFERRED` or fail over to an authorized route.
- Schedule bounded probes/retries.
- Avoid all workers probing simultaneously in `HALF_OPEN`.
- Never use a circuit breaker to mask a permanent `SMTP AUTH` misconfiguration.

Failing over to another route must account for sender authorization, SPF/DKIM/DMARC, quotas, content policies, and consistency of provider IDs/webhooks. Never switch routes casually just because primary is slow.

## 25. API backpressure: what to return to producers?

When a caller hits the notification creation endpoint, the HTTP status must match the **admission contract**.

### Case A: outbox committed

You can return:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "notificationId": "notif-503",
  "status": "QUEUED"
}
```

This means the request was accepted into the processing system under contract, **not that SMTP accepted it or the user read it**.

### Case B: admission rejected due to overload

You can return:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 30
Content-Type: application/json

{
  "errorCode": "MAIL_QUEUE_OVER_CAPACITY",
  "message": "Mail submission is temporarily unavailable"
}
```

Or `429 Too Many Requests` when enforcing a per-caller/tenant limit, depending on contract. Include `Retry-After` only with an appropriate retry policy that does not leak internal information.

**Never return 202 before persisting the job to storage durable enough for your contract.**

### Email as a side effect of another business flow

If an endpoint creates an order and writes to the outbox in the same transaction:

- When SMTP is down, the order can still succeed while the outbox holds the notification.
- If the outbox itself is overloaded, decide whether the whole transaction fails or an approved degraded policy applies.
- Never silently create an order while falsely reporting that the email was sent.
- Never retry order creation solely because email sending failed, to avoid duplicate orders.

Deciding whether email is mandatory for the primary operation belongs to business design, not just queue configuration.

## 26. Ensuring atomic admission under heavy load

Suppose the pending quota per tenant is 1,000 jobs.

Two concurrent requests:

```text
Request A reads pending=999
Request B reads pending=999

A inserts job -> 1000
B inserts job -> 1001
```

Checking `COUNT(*) < 1000` before `INSERT` does not enforce a hard limit under concurrency.

Techniques depending on storage:

- Transaction acquiring/releasing a quota slot on a locked/versioned row.
- Unique constraints and reservation records.
- Conditionally updated atomic quota counters.
- Broker quotas or ingress rate limits paired with primary backpressure.
- Soft warning thresholds plus hard storage-layer capacity protection.

With distributed counters, implement a **reconciliation** policy when a process dies before releasing a quota slot. A permanently leaked slot could lock a tenant out of sending forever.

Never enforce global quotas using a static variable inside one replica if multiple instances run.

## 27. Shutdown and backpressure are two sides of the same coin

Upon receiving `SIGTERM` or context close, workers should:

1. Stop accepting new tasks into the shutting-down executor.
2. Stop polling/claiming new jobs from the outbox/broker.
3. Let in-flight attempts finish within the deadline.
4. Persist outcomes and release leases/slots per policy.
5. Leave unfinished jobs for other workers or the next startup.

Continuing to claim jobs during shutdown inflates in-flight backlog and breaches the termination grace period.

With `ThreadPoolTaskExecutor`, setting:

```java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(25);
```

waits cleanly for tasks during executor shutdown. It **does not preserve in-RAM tasks across `SIGKILL`, power loss, or process crashes**. Reliable email delivery requires durable storage alongside proper retries and leases.

### Uncertain SMTP outcomes after a force kill

If a worker already transmitted data and died before saving `SMTP_ACCEPTED`, the job may be resent. Backpressure must work alongside idempotency and controlled retries, not worker counts alone.

## 28. Difference between backpressure and autoscaling

Autoscaling adds workers when backlog rises, but it does not replace backpressure.

Example:

- Queue grows because the SMTP provider caps throughput at 15 messages/s.
- The autoscaler scales from 5 to 50 workers.
- All workers compete for the same 15 messages/s quota.
- The provider returns even more 4xx errors.
- Retries swell the backlog further.

Autoscaling helps only when the bottleneck is **scalable processing capacity**, such as CPU rendering or too few workers within provider limits.

A sound scaling policy inspects:

- Queue depth and oldest age.
- In-flight worker counts and CPU/memory.
- SMTP accepted throughput.
- Provider quotas and rate-limit/error signals.
- Available partitions/consumers that can run in parallel.
- Startup cost and warm-up latency of new workers.

**Scaling workers up toward provider quotas is not an unbounded solution.** You may need to scale down or pause while the provider rejects traffic to curb retry storms.

## 29. Observing backpressure with Micrometer

In Spring Boot, Micrometer can record counters, timers, and gauges.

Useful meters:

| Suggested metric | Type | Meaning |
|---|---|---|
| `mail.notification.created` | Counter | New logical notifications |
| `mail.queue.admission.rejected` | Counter | Requests rejected due to capacity |
| `mail.send.attempt` | Counter | SMTP attempts started |
| `mail.send.accepted` | Counter | Attempts accepted by SMTP |
| `mail.send.failed` | Counter | Attempts with known failures |
| `mail.send.unknown` | Counter | Attempts with unknown outcomes |
| `mail.smtp.throttled` | Counter | Provider responses classified as throttling |
| `mail.outbox.pending` | Gauge | Waiting jobs |
| `mail.outbox.oldest.age` | Gauge | Age of oldest waiting job (seconds) |
| `mail.worker.inflight` | Gauge | Busy worker slots |
| `mail.executor.queue.depth` | Gauge | Tasks sitting in RAM queue |
| `mail.queue.wait.duration` | Timer | Time from enqueue to processing |
| `mail.smtp.attempt.duration` | Timer | Latency of SMTP send calls |

These names are illustrative conventions, not metrics automatically emitted by Spring Mail.

### Which metrics reveal true congestion?

A telltale pattern:

```text
created/s          = 50
smtp accepted/s    = 15
outbox pending     = increasing
oldest pending age = increasing
provider 4xx       = increasing
```

This signals the system is falling behind. Watching `smtp accepted/s` alone can mislead you into thinking throughput is healthy; compare arrival rate against departure rate.

### Queue age matters more than queue depth alone

A 500-job backlog may be harmless after a brief burst. Yet 20 jobs waiting over 30 minutes is critical if those emails carry short deadlines.

Monitor all of:

- `pending_count`.
- `oldest_pending_age_seconds`.
- Queue wait distribution.
- Expired or SLO-breaching jobs.
- Backlog per priority tier and route.

## 30. Keep tag cardinality low

Metrics are stored per tag combination. Attaching `notificationId` or recipient emails as tags can explode into hundreds of thousands of time series.

Appropriate tags:

```text
type=transactional|bulk|security
route=primary|backup|marketing
result=accepted|failed|unknown
reason=capacity|rate_limit|shutdown
error=authentication|connection|tls|throttling|unclassified
```

Avoid using:

- `correlationId`, `notificationId`, `attemptId`.
- Recipient email addresses.
- Raw SMTP exception messages.
- Unbounded order IDs, user IDs, or tenant IDs.
- Full URLs, filenames, or tokens.

Keep IDs for lookup in logs and outbox records rather than metric labels. For per-tenant quotas, store quota accounting in storage and emit aggregate metrics by bounded tenant tiers/groups.

## 31. Prometheus and dashboards during queue congestion

Suppose you export these series:

```text
mail_notification_created_total
mail_send_attempt_total
mail_send_accepted_total
mail_queue_admission_rejected_total
mail_outbox_pending
mail_outbox_oldest_age_seconds
```

Exact exported names depend on the Micrometer registry and unit conventions. Always inspect the real `/actuator/prometheus` endpoint before copying PromQL queries.

### Notification creation rate

```promql
sum(rate(mail_notification_created_total[5m]))
```

### SMTP accepted rate

```promql
sum(rate(mail_send_accepted_total[5m]))
```

### Demand vs. throughput gap

```promql
sum(rate(mail_notification_created_total[5m]))
-
sum(rate(mail_send_accepted_total[5m]))
```

The final expression is a **rough trend indicator**, not an exact queue-growth formula, because `created` and `accepted` can come from different cohorts, retries, expirations, and multi-recipient messages. The `mail_outbox_pending` gauge directly reflects point-in-time backlog.

### Admission rejection count

```promql
sum(increase(mail_queue_admission_rejected_total[15m]))
```

### Backlog by route

```promql
sum by (route) (mail_outbox_pending)
```

If multiple instances export the same shared DB backlog, summing across replicas **double-counts**. Use a clean export mechanism (such as one collector, leader election, or partitioned queries) before aggregating.

### Throttling ratio

If tracking a dedicated counter:

```promql
sum(rate(mail_smtp_throttled_total[5m]))
/
sum(rate(mail_send_attempt_total[5m]))
```

When the denominator is 0, never arbitrarily treat the ratio as 0% or 100%. Alerts should require minimum traffic thresholds and an evaluation window.

## 32. Alerts for mail queue congestion

A dashboard alone is insufficient without actionable alerts.

### Alert on queue age

Example policy: alert when the oldest `PENDING` job age exceeds that email category's threshold for long enough to filter transient noise.

Avoid one shared threshold for OTPs and weekly reports; their SLOs differ.

### Alert on admission rejections

If `mail.queue.admission.rejected` keeps climbing, producers are experiencing backpressure. While this may show the safeguard is working, investigate why capacity is insufficient.

### Alert on worker stalls

```text
mail_outbox_pending > 0
AND
mail_send_attempt rate ~= 0
```

If jobs exist yet no attempts happen over a sustained period, workers/schedulers/consumers may be down or paused by circuit/rate limits.

### Alert on provider throttling

If 4xx throttling climbs while accepted throughput drops and queue age grows, slow down the route instead of blindly adding workers.

### Alert on storage resources

If disk, the outbox table, or broker queues approach full capacity, trigger protective measures early. Never let the database fill up and crash core business transactions.

### Do not alert solely on large queue depth

A planned batch can spike queue depth briefly. Combine oldest age, drain trend, and SLO adherence to avoid noisy false alarms on every campaign.

## 33. Runbook when backlog surges rapidly

### Step 1: identify which backlog is growing

- In-RAM executor queue?
- Database outbox?
- RabbitMQ ready/unacked messages?
- Kafka consumer lag?
- Provider queues/deferred events?

Each queue requires a different mitigation. Never apply a blanket "clear queue" action everywhere.

### Step 2: locate the bottleneck

Check:

- Creation rate.
- SMTP accepted rate.
- 4xx/throttling and timeouts.
- Worker in-flight counts.
- CPU/heap/GC.
- Database/broker latency.
- Attachment sizes and affected routes.

### Step 3: throttle non-critical traffic sources

Pause bulk/campaign sends, shrink batch sizes, throttle producers, and enforce per-tenant quotas. Never block OTPs or security emails automatically unless a proper fallback policy exists.

### Step 4: curb retry storms

Check retry schedules, jitter, attempt counts, and permanent AUTH errors. For bad credentials, pause retries on that route until fixed rather than burning quota.

### Step 5: recover within real capacity

Once the provider recovers, ramp concurrency and rate gradually within limits. Keep the backlog durable and avoid replaying the entire DLQ at once.

### Step 6: inspect expired jobs

OTPs and reminders past deadlines may need `EXPIRED` transitions instead of confusing late deliveries. Emails with retention obligations need separate handling.

### Step 7: monitor post-recovery

Confirm:

- Backlog and oldest age are falling.
- SMTP accepted rate is steady.
- 4xx/timeouts are dropping.
- In-flight counts and bounded queues remain within limits.
- No abnormal duplicate rates appear.
- No API-acknowledged jobs were lost.

## 34. Unit test: a full executor must reject explicitly

A concrete test configures an executor with one worker and a tiny queue, holds the first task on the worker with a latch, queues the second task, and expects rejection on the third.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void rejectsWhenWorkerAndQueueAreFull() throws Exception {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(1);
    executor.setQueueCapacity(1);
    executor.initialize();

    CountDownLatch started = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);

    try {
        executor.execute(() -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });

        // Ensure the first task is actively occupying the worker.
        org.assertj.core.api.Assertions.assertThat(
                started.await(5, TimeUnit.SECONDS)
        ).isTrue();

        executor.execute(() -> {
            // Second task sits in the queue.
        });

        assertThatThrownBy(() ->
                executor.execute(() -> {})
        ).isInstanceOf(TaskRejectedException.class);
    } finally {
        release.countDown();
        executor.shutdown();
    }
}
```

Real tests may structure executor lifecycle differently and add cleanup on assertion failure. No real emails need to be sent: this verifies full-capacity behavior.

### Testing that the API never reports false success

When the executor rejects:

- If jobs live only in RAM, the service must never report successful queueing.
- If the job already committed to the outbox, the service may return `QUEUED` even when best-effort dispatch rejects.
- Never increment `mail.send.accepted` before calling SMTP.

This is an application-service contract test independent of the SMTP provider.

## 35. Testing worker concurrency caps

With a `Semaphore` or bounded worker pool, verify:

1. Submit more jobs than the cap.
2. Use a fake SMTP sender with a latch to hold in-flight attempts.
3. Measure peak concurrent active attempts.
4. Assert concurrency never exceeds available permits.
5. Release latches and verify permits return in `finally`.
6. Trigger exceptions and verify no permits leak.
7. Confirm unclaimed jobs stay `PENDING` in the outbox.

Never rely on arbitrary `Thread.sleep(...)` to prove concurrency behavior because tests become flaky. `CountDownLatch` or `Phaser` gives deterministic coordination.

### Across multiple replicas

An in-memory test only proves single-instance limits. To verify global provider quotas, run multi-worker/replica integration tests or test the distributed quota mechanism directly rather than extrapolating from a single `Semaphore(4)`.

## 36. Testing backoff retries without inflating notifications

Example scenario:

```text
Create notification N -> created +1
Attempt A1 -> known 4xx, schedule retry
Before nextAttemptAt -> worker must not claim N
After nextAttemptAt -> attempt A2
A2 -> SMTP accepted
Notification N -> final submission state accepted
```

Assertions:

- Notification ID stays unchanged.
- Attempt IDs differ.
- Created count does not increment on A2.
- The job receives `nextAttemptAt` per policy.
- No immediate tight-loop retries occur.
- Exceeding max attempts or TTL transitions clearly.
- Two workers cannot claim the same job under a valid lease.
- `UNKNOWN` outcomes are never lumped into known rejections.

Fix test time with `Clock.fixed(...)` or a fake clock rather than relying on wall-clock timing.

## 37. Testing brokers and outbox under failures

Important integration scenarios:

| Failure | Expectation |
|---|---|
| Worker crash before sending | Job remains in queue/outbox and is recoverable |
| Crash after SMTP acceptance before DB commit | Recovery does not claim exactly-once; attempt flagged unknown/needs reconciliation |
| RabbitMQ redelivery | Handler is idempotent per logical notification |
| Kafka rebalance | Never commits offsets as processed before work is durable |
| SMTP provider throttling continuously | Workers slow down, retries back off, no hot-looping backlog |
| Outbox nearing full | Admission protects storage and returns clear status |
| Bulk traffic spike | Critical lane retains reserved capacity |
| Forced shutdown | Stops claiming new work; jobs remain pending/leased |
| Oversized attachment | Never loads huge byte arrays into executor RAM |
| Massive DLQ replay | Subject to the same limiters as normal traffic |

Use an SMTP test server or fake sender rather than production credentials. Queue/outbox tests should assert real persisted state, not just metric counters.

## 38. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Nearly unbounded RAM queues | Heap growth, hidden delays, lost tasks on crash | Bounded queues and explicit overload contracts |
| Raising `maxPoolSize` with huge `queueCapacity` | Pool fails to scale workers as expected | Understand queue/pool order and measure |
| Using `CallerRunsPolicy` on HTTP threads | HTTP requests block on SMTP | Explicit admission or durable outbox |
| Using `DiscardPolicy` | Silent email loss | Reject explicitly or persist |
| Claiming too many outbox jobs | Leases expire before sending, duplicates | Claim strictly by available slots/permits |
| Giving each replica the full provider quota | Aggregate rate exceeds quota | Global limiter or partitioned quotas |
| Retrying immediately on every 4xx | Retry storms | Classify errors, apply backoff/jitter |
| Retrying SMTP timeouts as definitely unsent | Duplicate emails | `UNKNOWN`/reconciliation |
| Counting attempts as messages created | Metrics skew during retries | Track logical notification IDs |
| Watching queue depth alone | Misses stale jobs | Track oldest age and SLOs |
| Scaling workers unboundedly | Worse provider throttling | Scale within real quotas |
| Sharing one FIFO for OTP and bulk | OTPs stall | Separate lanes, fairness, reserved capacity |
| Holding attachment `byte[]` inside queue tasks | OOM under backlog | Small metadata + separate storage |
| Putting tenant/`notificationId` in metric labels | High cardinality | Bounded labels; keep IDs in DB/logs |
| Returning 202 before durable enqueue | Lost jobs despite caller thinking accepted | Wait for commit/publish confirmation |
| No shutdown admission stop | Jobs rejected or lost on redeploy | Stop claiming, drain, retry |
| Sending expired OTP jobs | Useless codes and user confusion | Enforce TTL/expiry policies |

## 39. Design and operations checklist

Before deploying a mail-sending queue to production:

1. **Define the job unit:** one logical notification per recipient or a multi-recipient batch.
2. **Measure arrival rates and SMTP accepted throughput** under realistic load.
3. **Know provider quotas:** messages/s, recipients/s, concurrency, and daily limits where applicable.
4. **Bound RAM queues:** explicit threads, queue capacity, and rejection policies.
5. **Never drop acknowledged jobs** when durability is promised by contract.
6. **Use a durable outbox/broker** for business-critical emails.
7. **Bound admission** by storage headroom and backlog/SLO limits.
8. **Bound claims/in-flight work** to worker slots and leases.
9. **Apply route/provider-wide rate limits** when replicas share quotas.
10. **Retry with backoff, jitter, max attempts, and deadlines** instead of hot retries.
11. **Distinguish SMTP accepted, known failures, and unknown outcomes.**
12. **Enforce priority/fairness** so bulk traffic never blocks urgent mail.
13. **Manage attachments** outside executor RAM queues and cap bytes-in-flight.
14. **Design clean shutdown** to stop claiming, drain within deadlines, and leave unfinished jobs recoverable.
15. **Track queue depth, oldest age, accepted throughput, throttling, and in-flight counts.**
16. **Protect metric cardinality** and keep PII out of labels.
17. **Test overload**, task rejections, crash/retry flows, broker redelivery, and timeouts.
18. **Maintain a runbook** for throttling producers, pausing bulk, fixing SMTP routes, and controlled replay.

Small applications do not need every mechanism on day one. Yet every system needs **finite bounds**, **defined behavior when full**, and **an honest answer about whether a job was accepted**.

## 40. Key takeaways

- Backpressure governs mismatches between email creation speed and worker/SMTP provider sending capacity.
- Queues absorb bursts, but infinite queues never raise processing capacity.
- `ThreadPoolTaskExecutor` needs bounded `corePoolSize`, `maxPoolSize`, `queueCapacity`, and an explicit rejection policy; RAM queues do not survive crashes.
- With positive queue capacity, workers only scale toward `maxPoolSize` after the queue fills.
- `CallerRunsPolicy` can turn async sends into blocking HTTP calls; `DiscardPolicy` and `DiscardOldestPolicy` risk silent mail loss.
- Important emails should be persisted durably in a queue/outbox and assigned a notification ID before returning accepted status.
- Never claim more jobs than you can process; coordinate leases and claim tokens across workers.
- Concurrency limits, rate limits, quotas, and backlog limits are four distinct mechanisms.
- SMTP 4xx/throttling must be classified and handled with backoff/jitter, never unbounded retries.
- Retries can produce duplicates when SMTP outcomes are uncertain; an outbox alone does not guarantee exactly-once delivery.
- Separate lanes, priorities, and quotas so bulk traffic never delays OTPs and critical transactional emails.
- Keep attachments in durable storage rather than stuffing large byte arrays into waiting tasks.
- Monitor created rates, accepted throughput, retries, queue age, in-flight counts, and admission rejections together.
- When the provider caps send rates, unbounded worker autoscaling only worsens overload.
- Graceful shutdown must stop new claims, drain within deadlines, and preserve unfinished jobs for later retries.

**Conclusion:** Mail-queue backpressure is not a single config knob — it is a **throttling contract spanning producers, queues, workers, and SMTP providers**. A resilient system explicitly declares when it has capacity, when work must wait, and when requests must be rejected; stores vital work durably, prevents retry storms, and measures real latency per email class. That allows Spring Framework Mail to operate reliably under load spikes without silently losing messages or dragging down the rest of the application.
