# Testing That Retries Do Not Cause a Retry Storm in Spring Framework Mail

A Spring application can send emails asynchronously via `JavaMailSender`, a message broker, or a transactional outbox. When the SMTP relay operates normally, dozens of workers can process messages very quickly. However, if the relay temporarily rejects requests, enforces rate limits, or drops connections, a poorly designed retry mechanism can turn a minor incident into a **retry storm**: workers retry simultaneously, open more connections, grow queues, trigger more timeouts, and keep retrying.

An effective retry test does not merely verify that an email is retried after an error. It must also prove that **every retry is bounded, spread out over time, durably persisted, and does not overload SMTP during failures or right when the relay recovers**. In Spring Framework Mail, this is a coordination problem across SMTP error classification, retry scheduling, idempotency, rate limiting, concurrency, queues, state machines, and testing under load.

> Central principle: retries are a real source of email-sending traffic. They must obey the same resource limits and coordination policies as new emails, never bypassing them simply because an attempt is a retry.

## 1. What Is a Retry Storm?

Suppose a system has 2,000 emails to send. The SMTP relay becomes temporarily unavailable. If 100 workers hit an error and immediately call `send()` again, a feedback loop can occur:

1. Many workers send to SMTP concurrently.
2. The relay returns temporary failures or times out.
3. Workers simultaneously retry with no wait or after the exact same wait duration.
4. The relay keeps receiving concurrent requests and struggles even harder to recover.
5. Workers spawn more attempts, consuming threads, connections, memory, and quotas.
6. When the relay recovers, the entire backlog floods in at once, creating a fresh traffic spike.

~~~mermaid
flowchart TD
    A["Many emails to send"] --> B["SMTP failing / throttling"]
    B --> C["Workers retry simultaneously"]
    C --> D["Increased connections, timeouts, queue"]
    D --> E["Relay remains overloaded"]
    E --> C
    E --> F["Prolonged outage"]
~~~

In many systems, retry storms emerge from **synchronizing retry timestamps**, not simply from having many emails. If 10,000 jobs all set `nextAttemptAt` to now plus exactly 60 seconds, a fresh retry wave hits one minute later. Having every job follow a fixed delay does not guarantee traffic dispersion.

### Common Causes

| Cause | Symptom | Consequence |
| --- | --- | --- |
| Immediate retry | Retrying in a loop when `send()` fails | Spikes CPU, connections, and attempt counts |
| Identical fixed delay | Jobs failing together retry together | Thundering herd |
| Multi-layer nested retries | Spring Retry, queue redelivery, and workers all retry | Multiplies sends unexpectedly |
| Unbounded retry count | A permanently failing record never stops | Queue and attempt history grow endlessly |
| Retrying without a rate limiter | When relay recovers, thousands of jobs send at once | Breaches quota, relay rejects again |
| Independent per-replica limiters | Each pod thinks it is under the threshold | Cluster-wide rate exceeds the limit |
| Simultaneous lease expirations | Many in-flight records get reclaimed together | Duplicate sends and extra load |
| Replaying entire dead-letter queue | One operational action creates a huge burst | Overload and loss of control |
| Unclassified errors | Bad addresses and bad passwords get retried | Wastes quota without recovery |
| Missing expiry checks | Expired campaign/OTP emails still get retried | Late sends or invalid content |

### Why Must Recovery Conditions Also Be Tested?

While SMTP is down, many systems only write `RETRY_PENDING`, so traffic looks quiet. Yet the instant SMTP recovers, every due record can be picked up and sent simultaneously. Therefore, tests must simulate **before failure, during failure, and after recovery**. A limiter that only operates while the server is failing is not enough.

## 2. Defining the Invariants to Verify

Before writing tests, define the rules the system must uphold under every condition.

| Invariant | What must be proven |
| --- | --- |
| Bounded attempts | A message never exceeds its configured retry limit |
| Bounded throughput | Total submissions in any window never exceed enforced quotas |
| Bounded concurrency | Active SMTP sends never exceed the slot limit |
| Shared budget | New emails, retries, and replays share the SMTP budget |
| Durable scheduling | `nextAttemptAt` and attempt counts survive process restarts |
| Classified failures | Only eligible errors retry; permanent errors stop |
| Jitter | Retries of simultaneously failing jobs do not align on one instant |
| No hot loop | When permits are unavailable, workers defer instead of spinning |
| No silent loss | Mandatory transactional emails stay in the outbox until a valid terminal state |
| No uncontrolled duplicates | One job is never claimed concurrently by multiple workers |
| Unknown outcome safety | Uncertain SMTP outcomes are not assumed definitely unsent |
| Policy compliance | Consent, expiry, suppression, and priority are re-checked before retrying |
| Auditable outcomes | Every attempt records status, timestamp, and error code for investigation |

**Do not make "zero duplicate emails under all conditions" an absolute promise when using plain SMTP.** If the relay received `DATA` and the connection dropped before the final reply, the application cannot know whether the message was accepted. You can reduce duplicate risk with idempotency and reconciliation, not guarantee end-to-end exactly-once delivery.

## 3. Traffic Amplification From Retries

Separate these terms:

- **First attempts:** the initial send attempt for each notification.
- **Retry attempts:** additional send attempts after a failure.
- **Resend:** a new intentional send requested by a user or operator.
- **Replay:** reprocessing an outbox or dead-letter record after investigation.

Given `N` messages, each tried up to `A` times (including the initial attempt), the theoretical maximum number of submissions is:

\[
T_{\max} = N \times A
\]

For example, 10,000 messages with up to 5 attempts can generate up to 50,000 SMTP attempts during an outage. If each outbox attempt also invokes a library that retries 3 times internally, total transport calls can climb far higher than intended.

A system must manage a **global retry budget** in addition to per-record attempt caps. For example, within any time window, allow retries to consume at most a set share of the budget so critical new emails can still get through. Exact ratios depend on SLAs and real quotas; no single default fits every system.

### Retry Amplification When Multiple Layers Participate

~~~text
Outbox:       max 5 attempts
Spring Retry: max 3 attempts per outbox attempt
Broker:       redelivery may repeat per policy
-----------------------------------------------
Total SMTP calls can exceed the intended 5 attempts
~~~

When testing, establish which layer owns the total attempt budget. If an adapter performs brief retries for transient network hiccups, count those calls in the real budget and verify nested retries never breach quotas.

## 4. Classifying Errors: Retrying the Right Errors Prevents Storms

Retries apply only to recoverable errors. When an error is permanent or data-related, retrying repeatedly only generates wasted load and noise.

| Error | Typical scenario | Strategy |
| --- | --- | --- |
| Connection refused / brief network drop | Relay unreachable | Retry with backoff; circuit breaker optional |
| SMTP `421` | Service temporarily unavailable | Bounded retry; pace sending per context |
| SMTP `450`/`451`/`452` | Distinct temporary errors | Retry after classifying; do not assume rate limiting |
| SMTP `4.7.x` | Often policy/temporary limit depending on provider | Read provider-specific codes and guidance |
| SMTP `5xx` recipient | Address permanently rejected | `FAILED_PERMANENT` / suppress per policy |
| SMTP authentication failure | Wrong credentials, relay permissions revoked | Do not tight-loop retry; alert to fix config |
| Template not found / parse failure | Content or resource packaging bug | Stop blind retries; fix template then replay |
| Invalid MIME / attachment | Invalid file or data | Fix data source; do not retry infinitely |
| `JavaMailSender` hit unknown outcome | Connection lost after `DATA` | `SUBMISSION_UNKNOWN`; reconcile or apply duplicate policy |
| Out of rate-limiter tokens | SMTP not called yet | Defer; do not count as an SMTP failure attempt |
| Cancelled / expired / unsubscribed | Policy disallows sending | `CANCELLED`/`EXPIRED`/`SUPPRESSED` |

### 4xx Does Not Always Mean Throttling

A `4xx` code indicates a temporary error, yet not every `4xx` means the server is overloaded. For example, a temporarily unavailable mailbox may be a local issue that does not warrant slowing down the entire provider. When testing adaptive throttling, use errors **explicitly identified by the app's classifier as throttling**, not arbitrary `4xx` codes.

### SMTP Has No HTTP-Style Retry-After Header

When using an email provider over an HTTP API, a `429` response may carry `Retry-After`. SMTP has no standard HTTP-like `Retry-After` header in the protocol. A provider might include retry hints in enhanced status codes or custom reply text, yet code must not blindly expect an HTTP header on an SMTP exception.

### Classifying via an Adapter

In Spring, `JavaMailSender` can throw `MailException` or subclasses wrapping Jakarta Mail errors. Reading SMTP status must rely on the concrete exception/cause of the transport in use. Normalize into a model such as:

~~~java
public enum FailureKind {
    TEMPORARY,
    THROTTLED,
    PERMANENT,
    CONTENT_ERROR,
    SUBMISSION_UNKNOWN
}

public record MailFailure(
        FailureKind kind,
        String code,
        boolean retryable
) {
}
~~~

These are internal model types. Mapping exceptions to `MailFailure` must be tested with unit/integration tests against the real adapter, not just regex matching on message strings.

## 5. Exponential Backoff and Jitter

**Exponential backoff** widens the interval between attempts. **Jitter** adds dispersion so many jobs do not retry at the exact same instant.

A bounded backoff formula:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1})
\]

Where:

- `n` is the number of completed failures (starting at 1).
- `d_0` is the base delay, e.g., 1 second.
- `d_max` is the maximum delay, e.g., 2 minutes.

With **full jitter**, delay is picked randomly between `0` and `d_n`. However, in some systems, a 0 ms delay can cause overly rapid retries. You can set a small minimum floor and pick randomly in `[minimum, d_n]` to prevent hot loops—a practical variant rather than pure full jitter.

### Comparison Example

| Job | Fixed 60-second backoff | Backoff with jitter |
| --- | --- | --- |
| A | 10:01:00 | 10:00:24 |
| B | 10:01:00 | 10:00:41 |
| C | 10:01:00 | 10:00:57 |
| D | 10:01:00 | 10:00:36 |

Jittered times are illustrative only. The goal is not "maximum randomness," but reducing simultaneous retries piling onto the same instant.

### A Testable Java Implementation

The example below accepts a random source as a function, letting tests verify bounds without real sleeping:

~~~java
package com.example.mail;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.LongUnaryOperator;

public final class RetryDelay {

    private final long initialMillis;
    private final long maxMillis;
    private final long minimumMillis;
    private final LongUnaryOperator randomBelow;

    public RetryDelay(
            Duration initial,
            Duration maximum,
            Duration minimum,
            LongUnaryOperator randomBelow) {

        this.initialMillis = initial.toMillis();
        this.maxMillis = maximum.toMillis();
        this.minimumMillis = minimum.toMillis();
        this.randomBelow = Objects.requireNonNull(randomBelow);

        if (minimumMillis < 0
                || initialMillis < 1
                || minimumMillis > initialMillis
                || initialMillis > maxMillis
                || maxMillis == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid retry delays");
        }
    }

    public Duration afterFailures(int failureCount) {
        if (failureCount < 1) {
            throw new IllegalArgumentException(
                    "At least one failure is required");
        }

        long upperBound = initialMillis;
        for (int n = 1; n < failureCount; n++) {
            if (upperBound >= maxMillis) {
                break;
            }
            // Double without causing overflow.
            upperBound = upperBound > maxMillis / 2
                    ? maxMillis
                    : Math.min(maxMillis, upperBound * 2);
        }

        long span = upperBound - minimumMillis + 1;
        long offset = randomBelow.applyAsLong(span);
        if (offset < 0 || offset >= span) {
            throw new IllegalStateException(
                    "Random source produced an invalid offset");
        }
        return Duration.ofMillis(minimumMillis + offset);
    }

    public static RetryDelay production() {
        return new RetryDelay(
                Duration.ofSeconds(1),
                Duration.ofMinutes(2),
                Duration.ofMillis(250),
                bound -> ThreadLocalRandom.current().nextLong(bound));
    }
}
~~~

Key properties:

- The first failure has an upper bound equal to `initial`.
- Subsequent failures grow the upper bound exponentially up to `maximum`.
- The random source selects an offset within the valid span.
- Delays are always non-negative and at least `minimum`.
- Never uses `System.currentTimeMillis` for delay computation.
- Tests can pass functions always returning `0` or `bound - 1` to check boundaries.

This class only computes delays; it does not send emails, persist outbox rows, or enforce cluster-wide rate limits. Jitter is **one protective layer**; when 100,000 jobs come due, you still need a global rate limiter.

## 6. Capping Attempts and Notification Age

Do not rely on backoff alone to let a message retry forever. Every notification needs:

- `maxAttempts`: maximum SMTP attempts, including the initial send.
- `maxAge` or `expiresAt`: maximum lifetime of the notification.
- `firstAttemptAt`, `lastAttemptAt`, and `nextAttemptAt`.
- Failure kind, normalized error code, and terminal state.

Policy example:

~~~java
public record MailRetryPolicy(
        int maxAttempts,
        Duration maxAge,
        RetryDelay retryDelay
) {
    public MailRetryPolicy {
        if (maxAttempts < 1 || maxAge.isNegative()
                || maxAge.isZero()) {
            throw new IllegalArgumentException(
                    "Invalid retry policy");
        }
    }
}
~~~

When a send fails, a next retry is scheduled only if:

1. The failure is classified as retryable.
2. Current attempts have not reached `maxAttempts`.
3. The notification has not been cancelled or suppressed.
4. The next retry time does not exceed `expiresAt`.
5. The provider/account is not disabled by policy.

### Timeline Example

~~~text
Created:          10:00:00
Attempt 1:        10:00:01  -> SMTP temporary failure
Attempt 2:        10:00:02  -> SMTP temporary failure
Attempt 3:        10:00:04  -> SMTP temporary failure
Attempt 4:        10:00:08  -> SMTP accepted
Status:           SUBMITTED
~~~

This timeline is illustrative; jitter shifts actual timestamps. If an OTP email expires at 10:03, the worker must never send it at 10:05 even if attempts remain.

### Counting Attempts Consistently

An attempt should represent **an invocation where the app actually began submitting to SMTP**, not a scheduler poll inspecting a record. Lacking tokens, lacking slots, or being blocked by a circuit breaker before calling transport is typically a **deferral**, not an SMTP failure. If an adapter has internal retries, those transport calls must count toward the total budget or be explicitly reflected in telemetry.

## 7. Persisting nextAttemptAt in the Transactional Outbox

Do not use `Thread.sleep()` or thousands of in-memory scheduled futures as a durable retry mechanism. If the process restarts, in-memory retry schedules vanish. An outbox record can contain:

~~~java
public enum OutboxStatus {
    PENDING,
    PROCESSING,
    RETRY_PENDING,
    SUBMITTED,
    SUBMISSION_UNKNOWN,
    FAILED_PERMANENT,
    DEAD_LETTER,
    SUPPRESSED,
    EXPIRED
}

public record MailOutboxSnapshot(
        java.util.UUID id,
        String notificationType,
        OutboxStatus status,
        int attempts,
        java.time.Instant createdAt,
        java.time.Instant nextAttemptAt,
        java.time.Instant expiresAt,
        String lastErrorCode
) {
}
~~~

A failed temporary attempt can transition:

~~~text
PROCESSING
  -> record attempt failure
  -> calculate nextAttemptAt
  -> RETRY_PENDING
  -> commit transaction
~~~

Workers only claim records whose `nextAttemptAt` is at or before the current time. Never hold SMTP connections or database transactions open while waiting.

### States That Must Never Auto-Retry

| State | Should the scheduler claim it? |
| --- | --- |
| `PENDING`, due | Yes |
| `RETRY_PENDING`, due | Yes |
| `PROCESSING` with active lease | No |
| `SUBMITTED` | No |
| `FAILED_PERMANENT` | No |
| `DEAD_LETTER` | Only after an explicit replay decision |
| `SUBMISSION_UNKNOWN` | No blind retries |
| `SUPPRESSED` | No |
| `EXPIRED` | No |

If an outbox record is already `SUBMITTED` and the user asks to resend the invoice, that is generally a **new resend request**, not resetting the old record back to `PENDING`.

## 8. Rate Limiting: An Indispensable Protective Layer

Exponential backoff and jitter spread out retry timestamps, yet do not guarantee total traffic stays below provider quotas. A **cluster-wide token bucket or sliding-window limiter** must gate submissions whenever budget runs out.

Limits that commonly combine:

| Limit | Goal |
| --- | --- |
| Global messages/second | Stay within an SMTP credential/provider quota |
| Global recipients/minute | Accurately count recipient quotas |
| Max in-flight SMTP sends | Prevent opening too many concurrent connections/sends |
| Per-domain rate | Reduce bursts toward one recipient domain |
| Per-tenant budget | Stop one heavy tenant from starving others |
| Retry budget | Prevent retries from starving new emails |
| Category reservation | Protect capacity for OTPs and transactional emails |
| Daily quota | Stay within daily sending caps |

**Per-JVM limiters are insufficient** when running multiple replicas. `N` replicas each allowing 20 emails/second can emit roughly `N × 20` emails/second. Use a distributed limiter or centralized dispatch gate sharing the overall budget.

### Every Sending Path Must Pass Through the Same Gate

~~~mermaid
flowchart LR
    A["New email"] --> D["Shared dispatch gate"]
    B["Scheduled retry"] --> D
    C["Replay / resend"] --> D
    D --> E["Rate + concurrency + policy"]
    E --> F["JavaMailSender"]
    F --> G["SMTP relay"]
~~~

Do not enforce limits solely inside the email-creation REST API. Retries and replays run in the background and bypass that API. Likewise, never create a special dead-letter replay worker that skips the limiter.

### When No Permit Is Available

- Do not call `JavaMailSender`.
- Do not increment `attempts` if SMTP was never tried.
- Keep or return the record to a waiting state.
- Set a reasonable next check time to avoid hot polling.
- Do not hold thousands of records in `PROCESSING` merely waiting for tokens.

If the limiter service is unavailable, the safe default is **defer dispatch and alert**, keeping records in the outbox. Never bypass the limiter entirely and send unboundedly.

## 9. Concurrency Limits and Queue Pressure

Rate limits cap average throughput; concurrency limits cap active simultaneous send calls. Both mechanisms must be tested separately.

Semaphore guard example:

~~~java
import java.util.concurrent.Semaphore;

public final class SmtpConcurrencyGate {
    private final Semaphore permits;

    public SmtpConcurrencyGate(int maxInflight) {
        if (maxInflight < 1) {
            throw new IllegalArgumentException("Invalid concurrency");
        }
        this.permits = new Semaphore(maxInflight);
    }

    public boolean tryEnter() {
        return permits.tryAcquire();
    }

    public void leave() {
        permits.release();
    }
}
~~~

Call `leave` only after `tryEnter` returns `true`; use a `finally` block once a slot is acquired. If a send throws an exception without releasing the slot, throughput can steadily drop to zero.

### Do Not Queue Retries Into an Unbounded Executor

For Spring's `ThreadPoolTaskExecutor`, configure explicit bounds:

~~~java
@Configuration
@EnableAsync
public class MailExecutorConfig {

    @Bean("mailExecutor")
    ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}
~~~

These numbers are illustrative, not Spring defaults. When the executor rejects a task, keep the notification in the outbox and reschedule—never treat a rejected task as sent. `@Async` is not a durable queue: process shutdown loses in-memory tasks. Workers should claim small batches matching available slots/permits.

## 10. Claiming Records With Leases: Avoiding Multi-Worker Duplicate Retries

In a multi-worker system, two instances can spot the same due record. If both call `send()` before the database records `PROCESSING`, duplicates occur even with zero SMTP errors.

Workers should use an **atomic claim**:

1. Select due `PENDING` or `RETRY_PENDING` records.
2. Assign `PROCESSING`, `leaseOwner`, and `leaseUntil` in a transaction.
3. Commit the claim transaction.
4. Call SMTP outside the transaction.
5. Record the outcome in a separate transaction verifying `leaseOwner`/generation.

In PostgreSQL, use `FOR UPDATE SKIP LOCKED` for a batch:

~~~sql
SELECT id
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_PENDING')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, created_at
LIMIT 20
FOR UPDATE SKIP LOCKED;
~~~

This snippet shows only the `SELECT` portion; the application must `UPDATE` the claimed records within the same transaction before committing. Exact syntax depends on the database. On other engines, use conditional compare-and-set `UPDATE` statements, optimistic locking, or a queue broker with proper claim/ack semantics.

### What Happens When a Worker Dies?

If a worker is killed after claiming, its lease expires. The system must recover the record to continue processing. Yet **lease expiration does not prove the email was never sent**:

- Worker died before calling SMTP: safe to retry in the unsent sense.
- Worker died after SMTP accepted but before writing `SUBMITTED`: outcome is unknown.
- Worker paused long enough for another worker to reclaim, then woke up: duplicate risk.

Test all three cases. Systems requiring ultra-low duplicate risk can use submission ledgers, provider ID reconciliation, or `SUBMISSION_UNKNOWN` workflows rather than retrying every expired lease immediately.

### Fencing Tokens or Generations

When claiming, increment `deliveryGeneration` or `leaseVersion`. A worker may update state only if the database version still matches the version it received.

~~~sql
UPDATE mail_outbox
SET status = 'SUBMITTED',
    updated_at = CURRENT_TIMESTAMP
WHERE id = :messageId
  AND status = 'PROCESSING'
  AND lease_owner = :workerId
  AND lease_version = :claimedVersion;
~~~

If the updated row count is 0, the worker lost write authority and must handle it per policy. Fencing stops a stale worker from overwriting a newer worker's state, **yet cannot recall an email that already left the application**. It does not solve exactly-once SMTP on its own.

## 11. A Storm-Safe Dispatcher Flow

A dispatcher can coordinate state, classifier, and dispatch gate like this:

~~~text
pollDueRecords():
    if circuit breaker is OPEN:
        do not claim more
        record deferred metric
        return

    capacity = min(freeConcurrencySlots, smallBatchLimit)
    if capacity == 0:
        return

    records = claimDueWithLease(capacity)

    for each record:
        if expired, cancelled, or suppressed:
            write terminal state; continue

        if no rate-limit quota remains:
            release lease, keep record, and set a new nextAttemptAt
            DO NOT increment SMTP attempts
            continue

        if concurrency slot unavailable:
            defer record; continue

        try:
            render MIME, check content
            record started-attempt
            transport.submit()
            mark SUBMITTED
        catch classified temporary error:
            if attempts/expiry exhausted: mark DEAD_LETTER
            else: schedule retry with backoff + jitter
        catch permanent/content error:
            mark FAILED_PERMANENT
        catch ambiguous SMTP error:
            mark SUBMISSION_UNKNOWN
        finally:
            release concurrency slot
~~~

Never wrap the entire send loop in one long database transaction. In a multi-message batch, one message failing must not roll back status updates for already-submitted messages in a way that causes mass duplicates.

### Do Not Retry Immediately Inside Catch

The snippet below risks a retry storm:

~~~java
// Do not write code like this:
while (true) {
    try {
        mailSender.send(message);
        break;
    } catch (MailException failure) {
        // Tight immediate loop; no backoff, no limit.
    }
}
~~~

Even with a fixed `Thread.sleep`, workers failing together wake up together. Persist `nextAttemptAt` and let the scheduler dispatch under shared quotas.

### A Coordination Example With Clear Component Responsibilities

~~~java
public interface SmtpTransport {
    void submit(MimeMessage message);
}

public interface RetryScheduler {
    void schedule(UUID notificationId, Instant when, String code);
    void permanentFailure(UUID notificationId, String code);
    void submissionUnknown(UUID notificationId, String code);
    void submitted(UUID notificationId);
}

public interface DispatchBudget {
    boolean tryAcquire(int recipientCount);
}
~~~

These interfaces are application adapters, not built-in Spring Mail APIs. The `SmtpTransport` adapter can wrap `JavaMailSender`; `RetryScheduler` updates the outbox transactionally; `DispatchBudget` enforces shared quotas.

A well-designed worker can be tested without real SMTP by replacing `SmtpTransport` with a fault-injecting fake and replacing `Clock` with a controllable clock.

## 12. Building a Pre-Deployment Test Matrix

A test suite must verify **correctness**, **load resilience**, and **recovery**.

| ID | Scenario | What must be proven |
| --- | --- | --- |
| T01 | Single temporary SMTP failure | One retry scheduled; not resent immediately |
| T02 | Repeated temporary SMTP failures | Delay grows boundedly; never exceeds `maxAttempts` |
| T03 | 1,000 jobs fail together | `nextAttemptAt` values are dispersed, not stacked on one timestamp |
| T04 | Permanent SMTP failure | No retry; record moves to terminal state |
| T05 | Template/MIME error | No blind resend; requires data/template fix |
| T06 | No rate tokens | Deferred; SMTP not called and `attempts` not incremented |
| T07 | Concurrency full | In-flight limit respected; no jobs dropped |
| T08 | Multiple replicas | Combined rate stays within shared quota |
| T09 | Worker dies while `PROCESSING` | Controlled lease recovery |
| T10 | Relay recovers after outage | Backlog drains at paced rate; no surge |
| T11 | Retries and new emails together | Combined throughput stays within budget |
| T12 | Retries alongside manual replay | Never bypasses limiter or duplicates scheduling |
| T13 | Provider returns throttling | Slows down and retries with backoff/jitter |
| T14 | Email expires before retry | Marked `EXPIRED`; not sent |
| T15 | Recipient unsubscribes | `SUPPRESSED`; SMTP not called |
| T16 | Unknown SMTP outcome | Not assumed definitively unsent and blindly retried |
| T17 | Outbox restart | `nextAttemptAt`, `attempts`, and status preserved |
| T18 | Multi-layer retries | Actual transport calls stay within intended budget |
| T19 | Overloaded queue | No unbounded threads, tasks, or `PROCESSING` rows |
| T20 | SMTP recovers briefly then fails again | Circuit breaker/rate limiter keeps attempts bounded |

Every test needs **measurable assertions**: submission counts, attempt timestamps, outbox states, max in-flight, granted tokens, backlog age, and error rates. Checking only that "after a while the email was sent" is insufficient.

## 13. Unit-Testing Backoff Without Thread.sleep

Random delays make tests flaky when relying on `Thread.sleep` and wall-clock timing. Inject a random source or clock instead.

### Testing Jitter Bounds

Using the `RetryDelay` class above:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class RetryDelayTest {

    @Test
    void delayRemainsWithinConfiguredBounds() {
        RetryDelay lowest = new RetryDelay(
                Duration.ofSeconds(1),
                Duration.ofSeconds(8),
                Duration.ofMillis(250),
                bound -> 0L);

        RetryDelay highest = new RetryDelay(
                Duration.ofSeconds(1),
                Duration.ofSeconds(8),
                Duration.ofMillis(250),
                bound -> bound - 1);

        assertEquals(Duration.ofMillis(250),
                lowest.afterFailures(1));
        assertEquals(Duration.ofSeconds(1),
                highest.afterFailures(1));
        assertEquals(Duration.ofSeconds(2),
                highest.afterFailures(2));
        assertEquals(Duration.ofSeconds(8),
                highest.afterFailures(20));
    }

    @Test
    void requiresAtLeastOneFailure() {
        RetryDelay retry = RetryDelay.production();
        assertThrows(IllegalArgumentException.class,
                () -> retry.afterFailures(0));
    }
}
~~~

These tests verify **algorithmic bounds** using a deterministic random source. They do not prove real-world jitter spreads evenly across 10,000 notifications; that requires a scheduler- or load-level test.

### Verifying Many Jobs Do Not Share One Timestamp

A scheduler test can:

1. Fail 1,000 notifications at the exact same instant.
2. Supply a seeded random source or known offset sequence.
3. Compute `nextAttemptAt` for each record.
4. Bucket records into small time intervals.
5. Assert the scheduler does not dump everything into one bucket and the global limiter still guards throughput.

Avoid overly tight probabilistic assertions on an arbitrary seed. Use deterministic inputs for algorithm tests; for distribution tests, run multiple seeds or apply proper statistical tolerances.

## 14. Using a Fake Clock to Test Retry Schedules

A controllable clock lets tests "advance time" in milliseconds of execution rather than waiting minutes or hours.

Example adjustable `Clock`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableClock(Instant initial, ZoneId zone) {
        this.current = new AtomicReference<>(initial);
        this.zone = zone;
    }

    public void advance(Duration amount) {
        if (amount.isNegative()) {
            throw new IllegalArgumentException("Cannot go backward");
        }
        current.updateAndGet(now -> now.plus(amount));
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new Clock() {
            @Override public Instant instant() {
                return MutableClock.this.instant();
            }
            @Override public ZoneId getZone() {
                return newZone;
            }
            @Override public Clock withZone(ZoneId z) {
                return MutableClock.this.withZone(z);
            }
        };
    }
}
~~~

This illustrative class shares one mutable instant across zones. In production, use `Clock.systemUTC()` or an appropriate time source; in tests, use `MutableClock`.

### Virtual-Time Test Flow

~~~text
now = 10:00:00
outbox message is PENDING

worker.dispatch() -> SMTP 421
assert status == RETRY_PENDING
assert nextAttemptAt > 10:00:00
assert submitCount == 1

worker.dispatch() at 10:00:00
assert submitCount == 1     // Not due yet

clock.advance(nextAttemptAt - now)
worker.dispatch() -> SMTP accepted
assert status == SUBMITTED
assert submitCount == 2
~~~

If the scheduler calls `Instant.now()` directly in many places, tests cannot control time and instances may lack a shared clock standard. Inject `Clock` into components computing `nextAttemptAt` and comparing timestamps, or consistently use database time for claims.

### Beware of Clock Skew Across Workers

In distributed systems, instance clocks can drift apart. Do not rely solely on local clock comparisons for lease claims if the database uses a different clock. Compute leases and due checks using database time or reliable time synchronization, and test cases where instances run a few seconds fast or slow. Clock skew must not reclaim records prematurely or leave them stuck past SLA.

## 15. Testing Transport Call Counts and Multi-Layer Retries

Suppose the outbox allows up to three attempts while the transport layer also carries a retry annotation. A test looking only at outbox attempts in the database might see 3 while SMTP was actually called 9 times.

A test must count **actual transport invocations**:

~~~java
@Test
void doesNotMultiplyTransportRetriesUnexpectedly() {
    when(transport.submit(any()))
            .thenThrow(new TemporarySmtpException("421"));

    // Assume dispatcher runs with policy maxAttempts = 3.
    simulateAllDueAttemptsThroughDispatcher();

    verify(transport, times(3)).submit(any());
    assertEquals(3, outboxRecord.getAttempts());
}
~~~

These classes and `simulate...` helper illustrate test structure. What must be measured is the number of SMTP calls for the same notification, not merely how many times the scheduler inspected the row.

If the adapter has internal retries, adjust expectations to match policy, ensuring the maximum total calls are **explicit and bounded**. If a broker automatically redelivers messages when a worker throws an exception, coordinate `ack`, `nack`, backoff, and outbox state so two independent retry schedulers do not arise.

### Testing Broker Redelivery

Deliver the same message ID to the consumer twice, with both attempting to process it. Expected results:

- The first claims or completes it.
- The second sees the record is no longer eligible or holds an invalid lease.
- No duplicate notification record is created.
- Two workers never send concurrently where claims control execution.

Never use a local boolean to deduplicate when multiple replicas exist; persist state/idempotency durably.

## 16. Testing Concurrency With Latches Instead of Sleep

To prove concurrent sends never exceed the cap, use a fake transport that pauses calls at a synchronization point with `CountDownLatch`.

Idea:

~~~java
AtomicInteger inFlight = new AtomicInteger();
AtomicInteger maxObserved = new AtomicInteger();

void simulatedSmtpSend() {
    int now = inFlight.incrementAndGet();
    maxObserved.accumulateAndGet(now, Math::max);
    try {
        releaseLatch.await();
    } finally {
        inFlight.decrementAndGet();
    }
}
~~~

In the test, launch many tasks trying to call send simultaneously, allowing only tasks that acquired a concurrency slot into `simulatedSmtpSend`. While tasks wait on the latch, assert `maxObserved` does not exceed the configured limit.

Details to handle in the test:

- Use timeouts on latches so tests never hang forever on failure.
- Release the latch in the test's `finally` block.
- Launch enough tasks to create real contention.
- Verify slots are released after exceptions.
- Assert tasks lacking slots defer rather than spinning in a hot loop.

Measuring total completion time alone does not prove concurrency bounds. Measure **max observed in-flight**.

## 17. Testing Rate Limits Over Time Windows

For a provider allowing at most `R` submissions in a window `W`, tests should verify:

\[
\text{submitCount}(t-W,\ t] \le R
\]

In the test harness, record each call alongside its simulated clock timestamp. Then scan sliding windows to ensure `R` is never breached. If the limiter is a token bucket permitting bursts, assertions must reflect **both refill rate and burst capacity**; do not apply a strict sliding-window check and falsely fail a token bucket configured to allow bursts.

### Example Acceptance Criteria for a Load Test

Suppose test configuration is:

- Global bucket refill: 10 tokens/second.
- Burst capacity: 20 tokens.
- Max concurrent submits: 4.
- Each message consumes 1 token.

Starting with a full bucket, a burst of messages can submit immediately. Over an interval of `T` seconds, maximum granted permits under the token-bucket model follow roughly:

\[
\text{granted}(T) \le 20 + 10T
\]

This is a **test-model bound**, not a default SMTP provider quota. When testing around window boundaries, mind rounding and timestamp resolution; you can also inspect the limiter's token-grant log directly. Concurrent in-flight sends must never exceed 4.

With five replicas, they **must still share** the single 20/10 bucket rather than each replica keeping its own bucket.

### Testing Distributed Limiters

An integration test using Redis or a real limiter store can:

1. Run `N` workers concurrently, each acquiring permits.
2. Share one key representing the SMTP credential.
3. Count total granted permits per window.
4. Verify the configured rate is not exceeded.
5. Simulate stopping and restarting one worker.
6. Verify the limiter does not reset its quota on JVM restart.

Do not mock Redis alone and claim atomicity of a Lua script or real transaction is verified. Test against an actual store when atomicity matters.

## 18. Fault Injection: Mass SMTP Failures Followed by Recovery

This is the key experiment for catching retry storms. Use a fake/test SMTP relay or transport adapter whose behavior can change over time. Never run overload experiments against production SMTP.

### Scenario A: Full Outage

Assume a test environment with:

- 5,000 `PENDING` notifications in the outbox.
- 4 worker replicas.
- Global budget of 10 messages/second, burst capacity 20.
- Max in-flight sends: 4.
- Fake SMTP returning temporary errors for 3 minutes.
- Retry policy: max 5 attempts, backoff with jitter.

Sequence:

1. Start workers with fake SMTP returning `TEMPORARY`.
2. Measure submit counts over time, per-record attempt counts, and `RETRY_PENDING` count.
3. Advance the clock through retry timestamps.
4. Observe whether workers honor the limiter during retries.
5. After 3 simulated minutes, switch fake SMTP to `ACCEPT`.
6. Keep running until the backlog drains or records reach terminal states.

Expected outcomes:

- Cluster-wide total submissions never exceed the limiter budget.
- Max in-flight never exceeds 4.
- During the outage, attempts do not climb unboundedly.
- No 0-delay retry loops occur outside policy.
- After recovery, the backlog drains smoothly instead of bursting unboundedly.
- Records exhausting attempts may move to `DEAD_LETTER`; not all 5,000 are guaranteed `SUBMITTED` because policy capped attempts.
- Attempt history and terminal states remain consistent.

Do not expect all 5,000 emails to finish sending merely because the relay recovered. Records that hit `maxAttempts` before recovery require an operator-reviewed replay workflow.

### Scenario B: High Failure Rate, Not 100%

Configure the fake SMTP to reply in a deterministic sequence:

~~~text
10 attempts:
  2 ACCEPT
  7 TEMPORARY_FAILURE
  1 PERMANENT_FAILURE
~~~

The test must verify:

- `ACCEPT` messages move to `SUBMITTED`.
- Temporary failures retry per policy without aligning on one timestamp.
- Permanent failures stop.
- The limiter counts failed attempts that actually hit the relay.
- Retries and first attempts compete for quota in a controlled way.
- Notification count does not grow due to retries.

Use a scripted reply sequence or fixed seed for reproducibility. An unseeded random generator can make load tests flaky.

### Scenario C: Relay Recovers With Lower Quota

An outage might be resolved by failing over to a provider with a lower quota. If the system immediately runs at the old rate, the backup provider can also get rate-limited.

Test:

1. Relay A fails.
2. Route shifts to relay B with a lower limit.
3. A large backlog and due retries exist.
4. Verify total submissions to B stay within B's quota.
5. Once A recovers, verify rerouting does not send the same record twice outside policy.

Never treat failover as an excuse to bypass limiters. Each provider/account needs its own budget while workers continue respecting outbox state.

## 19. Testing Circuit Breakers and Preventing Post-Reopen Storms

A circuit breaker stops calling SMTP during a widespread provider outage. Conceptually it has three states:

~~~text
CLOSED -- widespread errors exceed threshold --> OPEN
OPEN   -- pause duration elapsed --------> HALF_OPEN
HALF_OPEN -- probe succeeds --------------> CLOSED
HALF_OPEN -- errors continue -------------> OPEN
~~~

While `OPEN`, workers keep jobs in the outbox without calling SMTP. While `HALF_OPEN`, only a limited number of probes are allowed. Once `CLOSED` again, **the rate limiter must remain active**, because the post-outage backlog can be huge.

### Essential Tests

| Scenario | Expectation |
| --- | --- |
| Continuous provider timeouts | Breaker opens at threshold |
| Breaker `OPEN` | Zero new submits; jobs remain durable |
| `HALF_OPEN` | Only limited probes permitted |
| Probe fails | Breaker returns to `OPEN` |
| Probe succeeds | Breaker closes per policy |
| Breaker closes with huge backlog | Drain still passes through rate limiter/concurrency gate |
| One recipient returns `550` | Does not trip provider-wide breaker for an isolated recipient error |

A circuit breaker is not the only tool for throttling; rate-limit responses sometimes call for **slowing down** rather than tripping the breaker completely. The error-classification layer must define which signals reduce rate, open the breaker, or mark permanent failure.

## 20. Retry Budgets to Avoid Starving New Emails

Suppose SMTP recovers with 10,000 retries waiting. If retries consume 100% of the quota, brand-new OTP emails can be delayed until the entire backlog drains.

One strategy is partitioning the budget:

- Global provider limit: never exceed total quota.
- Reserved capacity: protect new security/transactional emails.
- Retry budget: cap the fraction of permits spent on retries.
- Optional campaign budget: stop marketing from consuming all capacity.
- Per-tenant fairness: prevent one tenant from monopolizing throughput.

~~~text
                 Global SMTP budget
                         |
            +------------+------------+
            |            |            |
         New urgent    New normal     Retry pool
            |            |            |
            +------------+------------+
                         |
                  Shared concurrency
                         |
                    SMTP relay
~~~

All branches must still stay within the global cap. Never allocate independent per-branch quotas whose sum exceeds the provider's budget.

### Testing Priority Under Backlog

1. Enqueue 20,000 marketing emails in `RETRY_PENDING`.
2. Create 10 `PENDING` OTP emails while the backlog is huge.
3. Switch fake SMTP to `ACCEPT`.
4. Run workers under the global limiter.
5. Measure elapsed time from OTP creation to `SUBMITTED`.
6. Assert OTP latency stays within the test environment's SLO.
7. Assert marketing emails are not silently dropped; they wait or expire per policy.

Do not verify priority solely by checking row-fetch order in one batch. Measure **end-to-end queue latency**, since multiple workers and queues interact.

### Avoiding Starvation

Strict priority carries a risk too: if urgent emails arrive continuously at high volume, normal transactional emails could starve. Use weighted fair scheduling or reserved capacity with borrowing. Tests must confirm lower-priority tiers still make progress within committed timeframes when capacity permits.

## 21. Testing Uncertain SMTP Outcomes and Idempotency

A retry-storm test suite is incomplete if it ignores the case where SMTP accepted the message yet the client never received confirmation.

### Post-DATA Uncertainty Window

~~~text
Mail worker                SMTP relay
    |                          |
    |----- MAIL/RCPT/DATA ---->|
    |                          | Accept message
    |<---- final response -----X  Network drops
    |
    | Unknown whether relay received it
~~~

If the worker flips the record to `RETRY_PENDING` and immediately resends, the recipient can get two emails. Handle it by:

- Separating errors proven pre-submit from uncertain-outcome errors.
- Using the `SUBMISSION_UNKNOWN` state where appropriate.
- Recording notification ID, attempt ID, and provider message ID if available.
- Reconciling with provider events/APIs if the platform supports them.
- Retrying only after applying the business duplicate policy.

### Testing This Scenario

The fake transport should support:

1. Recording that the relay received the message.
2. Throwing an exception simulating a lost final response.
3. Dispatcher receiving an unknown-outcome exception.
4. Asserting the record moves to `SUBMISSION_UNKNOWN` rather than jumping back to `PENDING`.
5. Checking another worker does not automatically claim `SUBMISSION_UNKNOWN`.

If the provider's idempotency API supports stable keys, test that retries reuse the same key; with direct SMTP, never assume the `Message-ID` header guarantees absolute deduplication.

### Database Idempotency Keys

A business key might look like:

~~~text
ORDER_CONFIRMED:order-184:recipient-42
~~~

A unique constraint ensures two consumers receiving the same event do not create two notification records for the same target. However, the unique constraint **does not guarantee** the relay will not accept two submissions of the same record if the client times out in an uncertain window.

### Testing Enqueue Race Conditions

Have two threads create a notification with the same idempotency key concurrently. One transaction wins; the other must receive the existing record or handle the unique constraint violation cleanly. Two parallel send records must never be created.

### Retrying OTPs and Reset Tokens

If an email contains an OTP or reset link, retrying the same notification must generally reuse the still-valid challenge/token per policy. Never mint a fresh token on every SMTP call. Once a token expires, the record must become `EXPIRED` or be replaced by a new request; never resend useless content merely because attempts remain.

## 22. Checking Expiry, Consent, and Suppression Right Before Retry

A message may be eligible when enqueued yet no longer allowed to send at retry time.

Example:

~~~text
10:00  User subscribes to newsletter
10:01  Newsletter is enqueued
10:02  SMTP outage, job RETRY_PENDING
10:05  User unsubscribes
10:10  SMTP recovers, job is due
10:10  Worker re-checks preference -> SUPPRESSED
~~~

The right outcome is **do not send the marketing email**. The worker must not rely solely on the consent snapshot from enqueue time if policy requires honoring the latest unsubscribe state.

Pre-dispatch checks:

- Notification is still within its expiration deadline.
- Recipient is still valid and eligible.
- Current consent/preferences allow optional emails.
- Not on the suppression list.
- Attachments or resources are approved and match the right version.
- Sensitive tokens or links are still valid.
- Template/payload matches policy version.

### Test Not Incrementing Attempts for Suppression

If a worker discovers the recipient unsubscribed before calling SMTP, that is a business decision, not a failed send attempt. The record moves to `SUPPRESSED`, transport is not called, and actual `attempts` does not increment.

### Do Not Send Expired Promotional Emails

Once a campaign ends, its retry backlog must not flush out en masse. Mark `EXPIRED` and stop. That prevents sending poorly timed content and reduces pressure on SMTP.

## 23. Testing Application Restarts and Multi-Version Deployments

Retry schedules must survive restarts and deployments. If a worker relies on `ScheduledFuture` or an in-memory delay queue, stopping the process loses the retry plan. If the app restarts and treats every `FAILED` row as `PENDING`, it can trigger a storm.

### Restart Scenario

1. Have fake SMTP return temporary errors.
2. Worker writes `RETRY_PENDING`, `attempts = 1`, and a future `nextAttemptAt`.
3. Stop the worker/process.
4. Start a fresh worker pointing at the same database.
5. Before `nextAttemptAt`, verify SMTP is not called.
6. At/after `nextAttemptAt`, verify the worker claims the record through the rate limiter.
7. Verify attempt history was not reset.

### Rolling Deployment Scenario

During a rolling update, old and new pods run side by side. Test that:

- They share the same global limiter.
- Record claims do not duplicate across versions.
- The outbox schema stays compatible during rollout.
- Deployments do not reset `nextAttemptAt`.
- No migration accidentally turns thousands of `RETRY_PENDING` rows into `PENDING` simultaneously.
- Stale worker leases are handled per policy when pods terminate.

### Testing Clock Skew

If each instance computes leases or `nextAttemptAt` from its own clock, a faster pod can claim records early. Use database time or consistent time synchronization, and test with worker clocks skewed within your defined risk bounds.

## 24. Integrating SMTP Test Servers and Chaos Testing

Unit tests verify backoff, policies, and states. To catch bugs at the Spring Mail / Jakarta Mail boundary, add integration tests with a test SMTP server capable of returning scripted responses.

### Test Environments Should Be Isolated

- Never use real user mailboxes.
- Never use production SMTP credentials.
- Never send stress traffic to real providers without an authorized test environment/account.
- Use fake transports, SMTP capture servers, or explicitly configured test services.
- Isolate test databases, queues, Redis, and metrics from production.

You can use an SMTP test library or a custom fake server for specialized responses. An SMTP capture server that only accepts mail successfully is not enough to test `421`/`451`, dropping connections between `DATA` and the final reply, or erratic delays; you need a server or fault injector able to control those phases.

### A Fault-Injection Matrix

| Fault point | Test | Expectation |
| --- | --- | --- |
| Before connect | Connection refused | Retry with backoff, finite attempts |
| During TLS handshake | Timeout or cert error | Classify properly; never blindly retry cert config errors |
| After connect, before `DATA` | Server returns `421` | Retryable, no burst |
| At `RCPT TO` | One recipient permanently rejected | Never infinitely retry that recipient |
| After server receives `DATA` | Cut connection before final reply | `SUBMISSION_UNKNOWN` |
| Writing outbox state | Temporary DB failure | Must not turn into thousands of uncontrolled resends |
| Limiter out of tokens | Token unavailable | Defer, do not call SMTP |
| Redis limiter outage | Shared gate unavailable | Do not bypass cluster-wide quota |
| Worker killed | `PROCESSING` interrupted | Controlled lease/state recovery |
| Relay just recovered | Large backlog | Drains at paced rate, no spike |

### Network Latency and Message Size

Beyond exceptions, simulate slow SMTP. A send with a large attachment takes much longer than a plain-text email. Without a concurrency gate, memory and connections can surge. Test combinations of:

- Large and small messages.
- Short and long response times.
- Varying worker counts.
- Recipient and message quotas.
- Aged backlogs coming due simultaneously.

A stable pipeline must maintain its in-flight cap and never flood the executor with unbounded tasks even when SMTP slows to a crawl.

## 25. Measuring Operations to Detect Retry Storms

To tell whether retries are generating excessive load, separate first attempts, retry attempts, suppressions, and provider failures.

| Suggested metric | Usage |
| --- | --- |
| `mail_first_attempts_total` | Count of initial attempts |
| `mail_retry_attempts_total` | Retry traffic |
| `mail_smtp_submissions_total` | Total SMTP calls executed |
| `mail_smtp_temporary_failures_total` | Retryable failures |
| `mail_smtp_permanent_failures_total` | Permanent failures |
| `mail_smtp_unknown_total` | Unknown submission outcomes |
| `mail_rate_limited_total` | Deferrals due to missing tokens |
| `mail_inflight_sends` | Active submissions |
| `mail_outbox_pending` | Messages awaiting initial send |
| `mail_outbox_oldest_age_seconds` | Age of oldest waiting message |
| `mail_retry_pending` | Jobs awaiting retry |
| `mail_dead_letter_total` | Jobs moved to dead-letter |
| `mail_retry_schedule_lag_seconds` | Difference between `nextAttemptAt` and actual worker pickup |
| `mail_limiter_available_tokens` | Remaining permits, if exposed by exporter |
| `mail_circuit_breaker_state` | Breaker state |
| `mail_dispatch_latency_seconds` | Submission latency |

Metric names are application-defined; implement with Micrometer and Spring Boot Actuator. Never put full email addresses, notification IDs, or SMTP transcripts into metric labels, as that leaks data and causes extreme cardinality.

### Retry Ratio

A useful metric:

\[
\text{retryRatio} =
\frac{\text{retryAttempts}}{\text{firstAttempts}+\text{retryAttempts}}
\]

If `retryRatio` spikes sharply, there may be a transport/provider incident or systemic bug. However, never diagnose a "retry storm" from ratio alone: a low-traffic system can show 50% with tiny absolute attempt counts. Always inspect **total attempts/second, backlog, throttling, and in-flight count**.

### Retry Storm Alerts

An alert can combine:

- Total attempt throughput nearing or hitting control thresholds.
- Retry attempt rate surging compared to baseline.
- Rising SMTP `4xx`/throttling responses.
- Growing backlog age.
- Many retry-queue items coming due at once.
- Circuit breaker flapping open/closed.

Alert thresholds depend on SLAs and provider capacity. Never use one threshold for both OTPs and marketing emails.

## 26. Per-Attempt Logging and Auditing

An attempt log entry should include:

~~~json
{
  "notificationId": "notification-184",
  "attemptNumber": 3,
  "kind": "RETRY",
  "outcome": "SMTP_TEMPORARY_FAILURE",
  "smtpCode": "421",
  "scheduledFor": "2026-11-12T09:00:40Z",
  "startedAt": "2026-11-12T09:00:41Z",
  "nextAttemptAt": "2026-11-12T09:02:17Z",
  "providerKey": "transactional-primary"
}
~~~

This is an illustrative log schema, not Spring's default output. Log data should suffice to trace and reconstruct retry schedules without storing SMTP passwords, OTPs, reset tokens, bodies, or attachment bytes. If an SMTP response contains recipient info, sanitize or restrict access.

### Why Is Attempt History Necessary?

If you only store `status = RETRY_PENDING` and `lastError = timeout`, it is hard to tell whether a record retried twice or 200 times, when attempts clustered, or whether two replicas sent simultaneously. Attempt history and correlation IDs pinpoint where a storm originated.

### Do Not Log Every Poll as a Retry

If a scheduler inspects 1,000 not-yet-due records without calling SMTP, never increment `retry_attempts_total`. Distinguish:

- Poll/claim/defer.
- Permit granted/denied.
- SMTP submit started.
- SMTP submit completed/failed.

This distinction is essential for accurately measuring real load placed on the relay.

## 27. A Reproducible End-to-End Test Scenario

To prove the system does not generate retry storms, build a simulation test:

### Input Data

~~~text
Notifications: 10,000
Notification categories:
  - 1,000 transactional
  - 9,000 optional

Workers: 4 replicas
Shared token bucket:
  - 20 permits/second
  - burst capacity 40
SMTP concurrency: 6
Retry:
  - max attempts 4
  - bounded exponential backoff + jitter

SMTP fake:
  - first minute: temporary failure
  - second minute: 50% temporary failure
  - afterward: accept
~~~

These numbers are for test environments only, not recommended production settings.

### Sequence and Observation Points

**Phase 1 — Enqueue**

- Create 10,000 notifications with distinct idempotency keys.
- Verify no duplicate records are created.
- Insert all into the outbox as `PENDING`.

**Phase 2 — Provider outage**

- Enable fake SMTP temporary failures.
- Run workers for one simulated minute.
- Count total attempts, max in-flight, deferrals, and `nextAttemptAt` values.
- Verify retries do not exceed `maxAttempts`.

**Phase 3 — Partial recovery**

- Fake SMTP accepts half of requests.
- Run workers for another interval.
- Verify successful records move to `SUBMITTED`.
- Temporary errors continue spacing out retries.

**Phase 4 — Full recovery**

- Fake SMTP accepts all requests.
- Run the dispatcher against the remaining backlog.
- Verify the limiter still enforces throughput and in-flight caps.
- Verify critical new emails still process using reserved capacity.

**Phase 5 — Restart and replay**

- Stop one worker and restart it.
- Replay a subset of eligible `DEAD_LETTER` records.
- Verify retries/replays share the same limiter and preserve history.
- Verify `SUBMITTED` records are not replayed in a way that sends duplicates.

### Passing Criteria

| Criterion | Measurement |
| --- | --- |
| No traffic storm | Total permits/submits match token bucket over time |
| No connection storm | Max observed in-flight never exceeds 6 |
| No infinite retries | No record exceeds 4 SMTP attempts per policy |
| No lost mandatory emails | Records persist and remain in trackable/terminal states |
| No expired optional sends | Expired records transition to `EXPIRED`/`SUPPRESSED` |
| No misreported statuses | `SUBMITTED` set only on reliable transport acceptance |
| No concurrent-claim duplicates | Only one valid lease owner processes each record |
| No post-recovery storm | Backlog drains within limits without bursting past budget |
| Diagnosable | Attempt history and metrics reflect errors and tries |

An integration test does not need to wait real minutes: use a fake clock for outbox scheduling, pace sends in the test harness, and use a fake transport. For real network benchmarks, measure wall-clock time in an isolated environment.

## 28. Special Test Cases: Queue and Rate Limiter Out of Sync

A real-world problem occurs when components have unsynchronized state. For instance, the outbox claims 100 messages while the rate limiter has only 5 tokens left. If the worker pushes all 100 into an in-memory executor to wait for tokens, leases can expire before they ever send.

### Testing Permit Exhaustion Right After Claim

1. Claim a small batch.
2. Have the shared limiter return no available tokens.
3. Verify the worker does not call SMTP.
4. Verify the record returns to a waiting state or receives a reasonable `nextAttemptAt`.
5. Verify `attempts` does not increment.
6. Verify the lease is properly released/adjusted and the row does not stay stuck `PROCESSING`.

### Testing Race Losses Between Check and Token Acquisition

Two workers may both see the limiter "has 1 token left," yet only one may consume it. Checking balance first and updating non-atomically afterward can let both send.

Test two workers competing for the last permit:

- Only one request receives the permit.
- The other request receives a deferral outcome.
- No negative counters or quota overruns occur.
- If using Redis/Lua, verify against real Redis or an equivalent integration setup.

### Testing Queue Saturation

With a bounded executor:

- Once threads and queue capacity fill, new tasks are intentionally rejected.
- Mandatory emails remain safely in the outbox without being dropped.
- Operators see `rejected`/`deferred` metrics.
- Workers never catch `RejectedExecutionException` and mark `SUBMITTED`.

If using `CallerRunsPolicy`, test that HTTP requests do not unexpectedly block waiting on SMTP in latency-sensitive flows. Rejection policies must fit the architecture rather than hiding exceptions.

## 29. Design Mistakes That Easily Lead to Retry Storms

### 29.1. Infinite Retry in a While Loop

A `while(true)` loop can generate thousands of calls when SMTP rejects immediately. Enforce attempt caps and backoff.

### 29.2. Identical Fixed Delay for Every Message

Messages failing together wake up together, causing a thundering herd. Use jitter and global limits.

### 29.3. Testing Only a Single Notification

One notification retrying properly does not prove 10,000 retrying together will not spike. Run concurrent load tests.

### 29.4. Counting Only Records, Not Real SMTP Calls

Nested retries inside an adapter can invoke transport far more times than outbox attempts show. Count physical submits.

### 29.5. Skipping the Rate Limiter for Retries/Replays

New emails may obey quotas while retries and replays create a storm. Every send source must traverse the same dispatch gate.

### 29.6. One Independent Limiter per Replica

Total rate scales with pod count. Use a shared budget or centralized dispatcher.

### 29.7. Capping Threads Without Capping Rate

A few fast threads can still exceed per-second or per-minute quotas. Enforce both rate and concurrency.

### 29.8. Calling Thread.sleep Inside a Transaction

Holds connections/locks across wait periods, starving the database. Persist `nextAttemptAt`, commit, and let workers return when due.

### 29.9. Setting maxAttempts Without Checking Expiry

Expired OTPs or ended campaign emails can still send late. Check expiration before retrying.

### 29.10. Treating Missing Rate Tokens as an SMTP Error

If transport was never called, do not increment SMTP attempt count or enter the failure retry chain. It is a deferred dispatch.

### 29.11. Opening a Provider-Wide Circuit Breaker on One Recipient Error

Isolated recipient failures do not indicate a provider outage. Classify signals accurately.

### 29.12. Dumping the Whole Backlog When the Circuit Breaker Closes

Once the relay recovers, large backlogs must still pass through the limiter. Ramp throughput gradually per policy.

### 29.13. Replaying Every Dead Letter at Once

Can trigger bursts, send stale content, or violate consent. Replays require filtering, dry runs, rate limits, auditing, and small batches.

### 29.14. Treating Unknown SMTP Outcomes as Definitely Failed

Immediate retries can send duplicates if the relay accepted the message. Use a dedicated state and reconcile per provider capabilities.

### 29.15. Using Message-ID to Claim Exactly-Once

`Message-ID` helps tracing, yet does not force every relay or mailbox to drop duplicates. Never treat it as an idempotency guarantee.

### 29.16. Testing Only With Always-Succeeding SMTP

You cannot catch retry, jitter, timeout, breaker, or redelivery bugs if fake servers only return `ACCEPT`. Use fault injection.

### 29.17. Relying on Thread.sleep in Tests

Tests turn flaky on slow CI or jittered schedulers. Inject `Clock` and random sources for deterministic logic tests.

### 29.18. Failing to Test State-Update Failures

SMTP may accept a message while the DB fails to persist `SUBMITTED`, causing reprocessing. Test post-submit DB errors and enforce unknown/duplicate policies.

### 29.19. Not Prioritizing Essential Notifications

Marketing retries eat up quotas, delaying OTPs or transactional emails. Use reserved budgets or fair scheduling.

### 29.20. Ignoring Backlog Age

Queue count may look small while an OTP has waited past expiry. Monitor oldest age and dispatch latency per category.

## 30. A Workflow for Testing and Operating in Production

Before shipping a new retry mechanism to production, follow this sequence:

1. **Identify real quotas:** messages/sec, recipients/min, connections, daily caps, and size limits; separate per provider/account.
2. **Inventory all sending paths:** initial sends, retries, replays, resends, campaigns, and manual dispatches.
3. **Choose the state model:** appropriate `PENDING`, `PROCESSING`, `RETRY_PENDING`, `SUBMITTED`, `UNKNOWN`, `FAILED`, `EXPIRED`, and `SUPPRESSED` states.
4. **Define retry policy:** error classes, `maxAttempts`, backoff, jitter, `maxAge`, circuit breaker, and unknown-outcome handling.
5. **Define the shared dispatch gate:** global budget, concurrency, per-tenant/domain/category caps, and retry budget.
6. **Define transaction boundaries:** claim, SMTP, and state updates must not sit in one long transaction.
7. **Add idempotency keys and leases:** prevent duplicate enqueues and claims; persist attempt history.
8. **Write clock/random unit tests:** avoid real sleeps for time logic.
9. **Write database/limiter integration tests:** verify atomic claims and shared permits across replicas.
10. **Write fault-injection tests:** timeouts, `421`, `5xx`, post-`DATA` disconnects, limiter outages, and database outages.
11. **Simulate outages and recovery:** large backlogs must drain within rate/concurrency limits.
12. **Check recipient policies:** consent, expiry, suppression, OTP tokens, and template versions.
13. **Verify metrics/alerts:** observe throughput, retry ratio, oldest age, queue depth, and rate-limit state.
14. **Roll out gradually:** scale workers/concurrency incrementally while watching provider replies instead of opening full throttle immediately.
15. **Prepare runbooks:** lower rates, pause marketing, open breakers, investigate DLQs, and replay in small batches.

### Acceptance Verification Table

| Requirement | Proof |
| --- | --- |
| Does not exceed rate limits | Cluster-wide token-bucket / sliding-window test |
| Does not exceed connection caps | Max observed in-flight via latch/test transport |
| Does not synchronize retries | Jitter test and `nextAttemptAt` histogram |
| Does not retry infinitely | `maxAttempts` and terminal-state tests |
| Does not lose mandatory emails | Outbox persistence/restart test |
| Does not duplicate via concurrent claims | Two-worker database integration test |
| Does not auto-retry unknown outcomes | SMTP response-loss test |
| Does not storm after provider recovery | Fault-injection outage → `ACCEPT` |
| Does not send expired/unsubscribed emails | Pre-dispatch policy tests |
| Does not bypass quotas on manual replay | Replay integration test |
| Incidents are diagnosable | Attempt history, metrics, and log correlation |

These criteria are design-test targets, not claims a system satisfies them until backed by real test results.

## 31. Self-Check Questions

**1. How does a retry storm differ from a large email queue?**

A large queue is pending work waiting to be sent. A retry storm happens when retries amplify traffic, synchronize timestamps, or exceed SMTP capacity, potentially prolonging an outage. A large queue can drain safely with a limiter; a tiny queue can still cause a storm if every message retries infinitely.

**2. Why is exponential backoff alone insufficient?**

If many jobs fail together and follow the same delay curve, they still retry at the exact same instants. You need jitter and a shared rate limiter.

**3. Can full jitter return a 0 delay?**

Yes. Therefore some systems set a minimum delay or pick another jitter variant to avoid instant retries, especially when failures return rapidly.

**4. Should maxAttempts count scheduler polls or SMTP submissions?**

Generally count attempts where the app actually began calling transport. Lacking tokens or slots before calling SMTP is a deferral, not an SMTP attempt.

**5. Should SMTP 5xx errors be retried repeatedly?**

No. `5xx` codes typically indicate permanent rejections for the current request; investigate the cause. Never lump all exceptions into retryable.

**6. Why count actual transport calls?**

Because retries can exist in multiple layers. An outbox might show three attempts while Spring Retry or broker redeliveries made far more than three SMTP calls.

**7. With multiple pods each having its own token bucket, is the quota enforced?**

No. Total rate scales with pod count. You need a shared limiter or centralized dispatcher.

**8. What should happen when permits run out after a record was claimed?**

Release or defer the claim, keep the record in the outbox, set a sensible next retry timestamp, and do not increment SMTP attempts when nothing was sent.

**9. Why avoid Thread.sleep when testing backoff?**

It makes tests slow, scheduler-dependent, and flaky. Inject `Clock` and a random source to control time and outcomes deterministically.

**10. What must be tested when SMTP recovers?**

Large backlogs must not flood past quotas, max in-flight must hold, and urgent new emails must not be starved by old retries.

**11. When the SMTP relay accepted DATA and the reply was lost, can we retry immediately?**

Do not retry blindly. The submission outcome may be unknown; apply `SUBMISSION_UNKNOWN` handling, reconciliation, or an explicit business duplicate-risk policy.

**12. Does a unique idempotency key guarantee zero SMTP duplicates?**

No. It stops creating two outbox rows for the same event, yet cannot eliminate duplicates across a network submit step that shares no transaction with the database.

**13. Why re-check consent when retrying marketing emails?**

Users can unsubscribe after enqueueing. When retry time arrives, the system must honor current preferences and suppression lists.

**14. When a circuit breaker closes again, can the entire backlog flush at once?**

No. After recovery, the limiter must still pace traffic; otherwise you risk triggering a second outage.

**15. Which metrics help detect a storm?**

Total SMTP attempts/sec, retry attempts/sec, temporary failure rate, rate-limited count, max in-flight, backlog age, and circuit breaker state are key signals.

**16. Should retry-storm experiments be run against production SMTP?**

No. Use fake SMTP, capture servers, or authorized load-test environments to protect recipients and sending reputation.

## Conclusion

**Testing that retries do not cause a retry storm means testing the entire coordination mechanism during failures and recovery, not just a single successful retry.** With Spring Framework Mail, classify errors before retrying, use exponential backoff with jitter, cap attempts and notification age, persist `nextAttemptAt` in a durable outbox, claim with leases, and maintain clear idempotency keys. Every new send, retry, resend, and replay must traverse the same cluster-wide rate limiter and concurrency gate. Tests should include fake clocks/randomness, fault injection, concurrent workers, lost SMTP responses, restarts, and outage recovery with large backlogs—while observing actual transport calls, max in-flight, retry ratios, and queue age. **A compliant system recovers smoothly within SMTP capacity, never drops critical emails, never sends expired or suppressed messages, and never lets the retry mechanism itself become a new outage.**
