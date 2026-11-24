# Backoff, Jitter, and Maximum Attempts in Spring Framework Mail

Sending email via `JavaMailSender` is a network operation, so a send can fail when the SMTP server is busy, the connection drops, or the provider temporarily throttles traffic. Yet not every error is solved by resending. If retries happen continuously without wait intervals and limits, the application can trigger a **retry storm**, exhaust workers, overload the SMTP relay, and even send duplicate emails.

A reliable retry policy must answer three questions: **which errors should be retried**, **how long to wait before the next attempt**, and **when to stop**. Backoff determines the wait interval, jitter randomizes the retry time, and `maxAttempts` caps the total number of sends. For critical emails, you also need a business deadline, durable retry state persistence, and a mechanism to handle ambiguous SMTP outcomes.

In Spring Framework Mail, `JavaMailSender` is responsible for executing a single send. Retry logic should generally live in the application/worker layer rather than being mixed into `MimeMessage` construction. Spring Retry can support short in-process retries; a transactional outbox is suitable when send requests must survive restarts.

## 1. Why Are Immediate Retries Usually Harmful?

Suppose an SMTP provider reports it is busy. If 1,000 mail-sending tasks fail at once and retry immediately, they can all keep hitting the already overloaded server together.

~~~text
1,000 email sends
        |
        v
SMTP temporarily rejects
        |
        v
1,000 immediate retries
        |
        v
SMTP rejects again
        |
        v
Repeats, creating higher load
~~~

When all workers use the exact same wait schedule, they can create load spikes at the exact same moments. This phenomenon is commonly called a *thundering herd* or *retry storm*.

A sound policy should:

- Separate transient errors from permanent errors.
- Spread out retry intervals as failures accumulate.
- Add jitter so workers do not all retry at the same instant.
- Enforce a maximum number of attempts and a deadline.
- Respect provider quotas and concurrency limits.
- Avoid holding database transactions or HTTP request threads during long waits.
- Record attempts, next attempt time, and outcomes for operations.

Retries improve the odds of overcoming **recoverable** errors—they are not a cure-all for every failure.

## 2. Distinguishing Attempt, Retry, and maxAttempts

A common design mistake is confusing total send attempts with retry count.

- **Attempt**: one actual invocation of the mail-sending system.
- **Initial attempt**: the first send attempt.
- **Retry**: an additional attempt after a previous failure.
- **maxAttempts**: in this lesson, the total number of allowed attempts, **including the initial one**.

Example with `maxAttempts = 5`:

| Execution | Attempt type | Attempts used |
| --- | --- | ---: |
| 1 | Initial send | 1 |
| 2 | Retry #1 | 2 |
| 3 | Retry #2 | 3 |
| 4 | Retry #3 | 4 |
| 5 | Retry #4 | 5 |
| 6 | Not allowed | Limit exceeded |

Thus `maxAttempts = 5` corresponds to **one initial attempt and up to four retries**.

Some libraries or applications use a `maxRetries` field to count only the additional resend attempts. If you choose that convention, name it explicitly. Never let one part of the codebase interpret `5` as five total sends while another interprets it as five retries.

### When Should an Attempt Be Counted?

When a worker reads a record from the outbox and attempts to call SMTP, keep a consistent rule:

1. Claim the record.
2. When actually starting a send, record the corresponding attempt.
3. Send via the adapter.
4. Update to `SUBMITTED` or `RETRY_WAIT`/`FAILED`.

If an executor rejects a task before the worker sends it, decide whether to count that as a send attempt or solely as a **dispatch attempt**. Never increment the attempt count in multiple places for the same execution.

## 3. When Should You Retry?

Do not catch every `MailException` and resend. Classify failures by root cause and, when possible, the stage of the SMTP conversation.

| Error group | Examples | Typical appropriate policy |
| --- | --- | --- |
| Transient (`TRANSIENT`) | Busy SMTP server, network drop, pre-submission timeout, temporary throttling | Retry with backoff and jitter |
| Permanent (`PERMANENT`) | Invalid recipient, MIME exceeds size limit, blocked file type | Do not retry the same message |
| Configuration (`CONFIGURATION`) | Wrong credentials, TLS/certificate issue, invalid host | Alert/fix configuration, do not tight-loop |
| Ambiguous (`AMBIGUOUS`) | Timeout after DATA was sent and server may have accepted it | Needs reconciliation/idempotency policy before retrying |
| Post-submission delivery failure | Bounce due to mailbox or downstream policy | Handle events/suppression separately |

### SMTP 4xx and 5xx

SMTP replies starting with `4` generally indicate transient errors; `5` generally indicates permanent errors. For example:

- `421`: SMTP service unavailable or closing connection; usually temporary.
- `450`, `451`, `452`: many cases of temporarily unavailable mailbox, processing, or resources.
- `550`: often mailbox does not exist or request rejected by policy.
- `552`: may relate to quota/storage limits; inspect message text and provider policy.

These are classification hints, not absolute mappings. Enhanced status codes, provider messages, SMTP stage, and specific policies can alter handling. Retrying the exact same oversized message will rarely bypass a size limit.

### Extracting Failure Info From Spring Mail

`JavaMailSender` can throw subclasses of `MailException`. `MailSendException` can contain underlying causes from Jakarta Mail/SMTP transport. The adapter should preserve the original exception as the cause, extract the reply code when available, and map to a meaningful application error:

~~~java
public enum MailFailureCategory {
    TRANSIENT,
    PERMANENT,
    CONFIGURATION,
    AMBIGUOUS
}
~~~

Unknown errors require their own policy. Never treat every timeout as unsent. Also, avoid classifying solely by matching substrings in free-form error messages if the provider API supplies official response codes or exception types.

## 4. Fixed Backoff

Fixed backoff uses a constant wait interval:

~~~text
Attempt 1: send immediately
Attempt 2: wait 10 seconds
Attempt 3: wait 10 seconds
Attempt 4: wait 10 seconds
Attempt 5: wait 10 seconds
~~~

Pros: simple, predictable, and suitable for certain short-lived errors. Cons: many requests failing together may continue retrying in lockstep, and attempts do not space out further during prolonged provider outages.

Fixed backoff can be used for very short internal retries or low-volume workloads. For larger email volumes, exponential backoff combined with jitter is usually better suited.

## 5. Exponential Backoff

Exponential backoff increases the wait interval with the number of failures:

~~~text
unclampedDelay(k) = initialDelay * multiplier^(k - 1)

cappedDelay(k) = min(maxDelay, unclampedDelay(k))
~~~

Where:

- `k` is the upcoming retry index, starting at 1.
- `initialDelay` is the wait before the first retry.
- `multiplier` is the growth factor, e.g., 2.
- `maxDelay` is the ceiling for each wait interval.

Example: `initialDelay = 2 seconds`, `multiplier = 2`, `maxDelay = 30 seconds`.

| Attempt | Type | Delay before attempt |
| --- | --- | ---: |
| 1 | Initial send | 0 |
| 2 | Retry 1 | 2 seconds |
| 3 | Retry 2 | 4 seconds |
| 4 | Retry 3 | 8 seconds |
| 5 | Retry 4 | 16 seconds |
| 6 | Retry 5 | 30 seconds |
| 7 | Retry 6 | 30 seconds |

From retry 5 onward, the delay hits the 30-second cap. This table assumes all attempts are permitted; in practice, if `maxAttempts = 5`, attempts 6 and 7 are not executed.

### Why Is maxDelay Needed?

Without a cap, exponential growth climbs rapidly. After enough failures, the delay can become so long that the email is no longer relevant, or integer arithmetic can overflow.

`maxDelay` bounds the algorithmic wait time. It is not a license to ignore a longer wait requested by the provider; if the provider asks to wait one hour, the application should not try earlier just because its internal cap is two minutes.

## 6. Jitter Prevents Workers From Retrying Together

Plain exponential backoff can still keep requests synchronized.

~~~text
Without jitter:
  10:00:00 - 500 tasks fail
  10:00:02 - 500 tasks retry at the same time
  10:00:06 - 500 tasks retry at the same time
  10:00:14 - 500 tasks retry at the same time

With jitter:
  10:00:00 - 500 tasks fail
  10:00:00–10:00:02 - retries are spread out
  Subsequent rounds continue spreading send times
~~~

Jitter is a random component added to the delay to:

- Reduce SMTP connection spikes after an outage.
- Smooth load on the provider.
- Prevent application instances from sharing identical retry schedules.
- Help rate limiters and worker pools coordinate smoothly.

Jitter does not replace a rate limiter. If a provider only accepts a certain number of emails per second, the system still needs to throttle overall throughput.

## 7. Full Jitter, Equal Jitter, and Decorrelated Jitter

Let `cap` be the exponential delay after clamping by `maxDelay`.

### Full Jitter

~~~text
delay = random(0, cap)
~~~

Each retry picks a random value between 0 and `cap`. Pros: strong dispersion; cons: it can choose a delay very close to 0. If the provider is overloaded, combine with a floor delay or rate limiting to avoid hot retries.

### Equal Jitter

~~~text
delay = cap / 2 + random(0, cap / 2)
~~~

Retains at least half of `cap`, with the rest randomized. If `cap` is 8 seconds, the delay is roughly 4–8 seconds. This strategy prevents overly immediate retries while still spreading tasks out.

### Decorrelated Jitter

A common variant:

~~~text
delay = min(maxDelay, random(baseDelay, previousDelay * 3))
~~~

The new delay depends on the previous delay rather than strictly following a fixed power curve. You must persist `previousDelay` per email if rescheduling in an outbox.

### Comparison

| Strategy | Characteristic | Note |
| --- | --- | --- |
| No jitter | Delay equals exact cap | Simple but prone to synchronization |
| Full jitter | Random from 0 to cap | Strong spread, may retry very early |
| Equal jitter | Random from cap/2 to cap | Fewer premature retries |
| Decorrelated jitter | Based on previous delay | Requires extra persisted state |

There is no single best strategy for every provider. Absent specific requirements, bounded exponential backoff with equal or full jitter and a clear deadline is a sensible starting point for testing.

## 8. MaxAttempts Does Not Replace a Deadline

An email can lose its value even before exhausting its attempt limit. Examples:

- An OTP expires after a few minutes.
- A password reset token has been revoked.
- An event invitation email is no longer useful after the event starts.
- A newsletter must not be resent after the user unsubscribes.

Retries must check both the attempt count and the business deadline:

~~~text
Allowed to retry?
  error is a retryable type
  AND attempts < maxAttempts
  AND now < expiresAt
  AND content is still valid for business rules
  AND does not violate cooldown/provider policy
~~~

If the next scheduled retry falls after `expiresAt`, stop rather than sending an expired email.

### Types of Limits

| Limit | Purpose |
| --- | --- |
| `maxAttempts` | Prevent infinite SMTP calls |
| `maxDelay` | Prevent excessive exponential wait times |
| `maxAge`/`expiresAt` | Stop when the email is no longer meaningful |
| `rateLimit` | Cap overall sending rate |
| `maxConcurrentSends` | Cap concurrent connections/tasks |
| `maxQueueAge` | Prevent backlog delays from breaching SLAs |

Do not conflate these concepts into a single parameter.

## 9. Modeling a Retry Policy in Java

Keep the retry policy independent of Spring Mail for easy testing.

~~~java
import java.time.Duration;

public record MailRetrySettings(
    int maxAttempts,
    Duration initialDelay,
    Duration maxDelay,
    Duration maxAge
) {
    public MailRetrySettings {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                "maxAttempts must be positive");
        }
        if (initialDelay.isZero()
                || initialDelay.isNegative()
                || maxDelay.compareTo(initialDelay) < 0
                || maxAge.isNegative()
                || maxAge.isZero()) {
            throw new IllegalArgumentException(
                "Invalid retry durations");
        }
    }
}
~~~

These values are business configuration, not defaults of Spring Framework Mail.

An outcome can be standardized as:

~~~java
public record RetryDecision(
    boolean retry,
    Instant nextAttemptAt,
    String reason
) {}
~~~

Error classification belongs to the adapter/provider integration; delay calculation belongs to the retry policy; persisting `nextAttemptAt` belongs to worker/outbox orchestration. Separating these responsibilities lets you modify one part without impacting the others.

## 10. Implementing Exponential Backoff With Equal Jitter

Java 17+ example using `RandomGenerator` so a deterministic random source can be injected in tests.

~~~java
package example.mail.retry;

import java.time.Duration;
import java.util.random.RandomGenerator;

public final class MailBackoffPolicy {

    private final long initialMillis;
    private final long maxMillis;

    public MailBackoffPolicy(Duration initial, Duration max) {
        if (initial.isZero() || initial.isNegative()
                || max.isZero() || max.isNegative()) {
            throw new IllegalArgumentException(
                "Delays must be positive");
        }

        this.initialMillis = initial.toMillis();
        this.maxMillis = max.toMillis();

        if (initialMillis <= 0
                || maxMillis < initialMillis
                || maxMillis == Long.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Invalid delay range");
        }
    }

    /**
     * failedAttempt=1: just failed the initial send.
     * failedAttempt=2: just failed the first retry.
     */
    public Duration delayAfterFailure(
            int failedAttempt,
            RandomGenerator random) {

        if (failedAttempt < 1) {
            throw new IllegalArgumentException(
                "failedAttempt must be >= 1");
        }

        long cap = initialMillis;

        // Double with cap, avoiding overflow.
        for (int i = 1; i < failedAttempt; i++) {
            if (cap >= maxMillis / 2) {
                cap = maxMillis;
            } else {
                cap = Math.min(maxMillis, cap * 2);
            }
        }

        long minimum = cap / 2;
        long additionalRange = cap - minimum;

        long jitter = random.nextLong(additionalRange + 1);
        return Duration.ofMillis(minimum + jitter);
    }
}
~~~

Usage example:

~~~java
MailBackoffPolicy policy = new MailBackoffPolicy(
    Duration.ofSeconds(2),
    Duration.ofMinutes(2)
);

Duration delay = policy.delayAfterFailure(
    3,
    ThreadLocalRandom.current()
);
~~~

With `failedAttempt = 3`, `cap` is 8 seconds and equal jitter produces a delay around 4–8 seconds. `failedAttempt` represents the number of sends already attempted and failed, not the number of remaining retries.

### Calculation Notes

- Use `long` and clamp at `cap` to prevent overflow.
- Do not call `Math.pow` on unbounded attempt counts and cast directly to `long`.
- Keep initial and max delays within realistic ranges rather than near numeric type limits.
- Compute jitter individually per record/send attempt.
- In tests, inject the RNG/`Clock` so results are reproducible.
- This function only calculates delay; it does **not** itself know whether the error is retryable.

## 11. Deciding Retries by Error, Attempts, and Deadline

Standalone policy example:

~~~java
public RetryDecision decide(
        MailFailureCategory failure,
        int attemptsSoFar,
        int maxAttempts,
        Instant now,
        Instant expiresAt,
        Duration delay) {

    if (failure != MailFailureCategory.TRANSIENT) {
        return new RetryDecision(
            false, null, "Failure is not safely retryable");
    }

    if (attemptsSoFar >= maxAttempts) {
        return new RetryDecision(
            false, null, "Max attempts reached");
    }

    if (!now.isBefore(expiresAt)) {
        return new RetryDecision(
            false, null, "Business deadline expired");
    }

    Instant nextAttemptAt = now.plus(delay);

    if (!nextAttemptAt.isBefore(expiresAt)) {
        return new RetryDecision(
            false, null, "Next retry is beyond deadline");
    }

    return new RetryDecision(
        true, nextAttemptAt, "Transient failure");
}
~~~

In this example, `AMBIGUOUS` failures are not automatically retried due to duplicate-send risk. That is a **conservative policy choice**; another application might decide differently when a provider idempotency key exists or the business tolerates duplicates.

In production, add handling for optional `expiresAt`, provider cooldowns, configuration errors, and recipient suppression status. Do not retry a notification once the user has unsubscribed or the content has become invalid.

## 12. Ambiguous SMTP Outcomes and Duplicate Risk

A tricky scenario is a timeout after the SMTP server has already received the body:

~~~text
Application                      SMTP server
    |                                |
    |---------- SMTP DATA ---------->|
    |                                | Receives full message
    |                                | Stores for forwarding
    |<--- lost response / timeout ---|
    |
    +--> Client sees error
~~~

The application does not know whether the server accepted the message. If it retries, the recipient may receive two emails.

Distinguish:

- Error before connecting: usually not submitted.
- Error during the session before sending DATA: generally lower duplicate risk.
- Timeout after data has been transmitted: outcome may be unknown.
- Server returns a success reply: submission was accepted, **not** proof the email landed in the Inbox.

Do not assume every `MailSendException` or timeout can be safely retried. Preserve the error code, cause, and phase if supplied by the transport for classification.

### An Idempotency Key Is Not a Silver Bullet

A unique key in the database prevents creating two outbox records for the same business event, but it does not automatically eliminate an SMTP resend of **the same** record.

If a provider over an HTTP API supports an idempotency key, pass the same key across all retries. With traditional SMTP, there is no universal idempotency mechanism across all servers. The `Message-ID` header is useful for correlation, not a guarantee that the mailbox or provider will deduplicate.

Therefore, explicitly decide how to handle `AMBIGUOUS`: reconcile with the provider if an API exists, move to a review state, or allow retries where duplicates cause minimal harm and mitigations are in place.

## 13. Respecting Provider Retry Guidance

Some email APIs return HTTP `429` or `503` with `Retry-After`. If the provider asks to wait until a given time, do not retry earlier.

In SMTP, `4xx` responses represent various temporary errors, but there is no single universal `Retry-After` header equivalent to HTTP across all servers. Providers may document cooldown windows or quotas in their own documentation.

A coordinated policy:

~~~text
algorithmNotBefore = now + backoffWithJitter
providerNotBefore  = time permitted by provider (if any)

nextAttemptAt = max(algorithmNotBefore, providerNotBefore)

If nextAttemptAt >= businessExpiresAt:
    do not retry further
~~~

The algorithm's `maxDelay` must not be used to violate a longer cooldown requested by the provider. If the provider asks for a 30-minute pause but an OTP only has 5 minutes left, terminate the notification instead of forcing a send after 2 minutes.

### Distinguishing Retries From Rate Limiting

- Retry backoff governs **each individual failed email**.
- A rate limiter governs **total emails** per unit of time.
- A thread pool/concurrency limit governs **how many sends run simultaneously**.

An application with jitter where 100 instances all send too many emails can still breach quotas. Across multiple instances, coordinate quotas per account/provider rather than relying solely on local per-JVM limiters.

## 14. Spring Retry for Short-Lived Retries

Spring Retry enables declarative retries via `@Retryable`. The example below applies when the project uses a Spring Retry version supporting those annotation attributes along with proper AOP proxying.

Enable retry:

~~~java
@Configuration
@EnableRetry
public class RetryConfiguration {
}
~~~

Service:

~~~java
@Service
public class RetryingMailSubmission {

    private final MailDeliveryPort mailDelivery;

    public RetryingMailSubmission(MailDeliveryPort mailDelivery) {
        this.mailDelivery = mailDelivery;
    }

    @Retryable(
        retryFor = TransientMailSubmissionException.class,
        maxAttempts = 4,
        backoff = @Backoff(
            delay = 1000,
            multiplier = 2.0,
            maxDelay = 10_000,
            random = true
        )
    )
    public void submit(OutgoingMail mail) {
        mailDelivery.send(mail);
    }
}
~~~

This requires the `spring-retry` library and appropriate AOP/proxy dependencies; the annotations reside in `org.springframework.retry.annotation`. Here `maxAttempts = 4` includes the initial invocation.

Parameters:

- `delay`: initial wait time in milliseconds.
- `multiplier`: growth factor.
- `maxDelay`: delay cap.
- `random`: enables randomization per Spring Retry's implementation.

Do not assume Spring Retry's `random = true` equals **exact full jitter** from the formula in Section 7. If you need a specific jitter distribution, deadline check, or scheduler, use a custom retry policy or scheduling in an outbox worker.

### Limitations of Synchronous Retries

If a `@Retryable` call waits for backoff on the executing thread, that thread remains occupied throughout the wait. If called inside an HTTP request or a long database transaction, latency and resource usage climb.

In addition:

- Retry context does not survive a process crash.
- Self-invocation bypasses Spring's default proxy.
- It does not provide idempotency on its own.
- It cannot tell whether SMTP received the message on a timeout.
- It does not guarantee delivery to the Inbox.
- It does not recover tasks lost during a process restart.

Use Spring Retry mainly for short retry counts, brief wait times, and scenarios without strict durability requirements. For critical transactional emails, an outbox/worker is usually better suited.

## 15. @Recover and Handling Exhausted Attempts

A Spring Retry service can declare `@Recover` to handle cases when attempts are exhausted:

~~~java
@Service
public class RetryingMailSubmission {

    private final MailDeliveryPort mailDelivery;

    public RetryingMailSubmission(MailDeliveryPort mailDelivery) {
        this.mailDelivery = mailDelivery;
    }

    @Retryable(
        retryFor = TransientMailSubmissionException.class,
        maxAttempts = 3,
        backoff = @Backoff(
            delay = 1000,
            multiplier = 2.0
        )
    )
    public void submit(OutgoingMail mail) {
        mailDelivery.send(mail);
    }

    @Recover
    public void recover(
            TransientMailSubmissionException cause,
            OutgoingMail mail) {

        throw new MailSubmissionExhaustedException(
            "Mail attempts exhausted", cause
        );
    }
}
~~~

`@Recover` can translate the exception or record the failure state. If the email needs tracking and retries across restarts, update the outbox in an appropriate transaction instead of merely logging.

### Avoiding Nested Retry Layers

If an outbox worker allows 5 attempts and each attempt invokes a `@Retryable(maxAttempts=4)` service, the application can hit SMTP up to 20 times instead of 5.

A design should have **a single owner of the retry budget**. If there are transport-level retries for ultra-brief connection hiccups, account for them explicitly in metrics and total send limits.

## 16. Do Not Use Thread.sleep for Long Retries

An easy-to-write yet dangerous loop:

~~~java
for (int attempt = 1; attempt <= 5; attempt++) {
    try {
        mailSender.send(message);
        return;
    } catch (MailException exception) {
        Thread.sleep(30_000);
    }
}
~~~

Problems:

- Sleeps even after the last attempt unless guarded.
- Holds HTTP/worker threads while doing no useful work.
- May hold database transactions and connections open.
- Does not classify errors before retrying.
- Does not handle `AMBIGUOUS` outcomes.
- Does not persist attempt counts or retry schedules.
- When the process crashes, all stack state is lost.

For delays of seconds or minutes, persist `nextAttemptAt` and let a scheduler/worker re-trigger it. While waiting, the thread is returned to the pool to handle other emails.

~~~text
SMTP returns temporary error
          |
          v
Compute backoff + jitter
          |
          v
Persist nextAttemptAt
          |
          v
Return thread to executor
          |
          v
Scheduler runs when due
~~~

## 17. Combining Backoff With a Transactional Outbox

A transactional outbox stores the send request in the same transaction as the business data. After commit, a worker fetches the record, sends the email, and updates the status.

~~~text
PENDING
   |
   v
PROCESSING
   |
   +---- success ----------> SUBMITTED
   |
   +---- temporary error --> RETRY_WAIT
   |                          |
   |                          v
   |                    nextAttemptAt reached
   |                          |
   |                          +---> PROCESSING
   |
   +---- permanent error --> FAILED
   |
   +---- attempts exhausted -> FAILED / DEAD_LETTER
~~~

An outbox record needs:

| Field | Role |
| --- | --- |
| `id` | Send request ID |
| `idempotency_key` | Stable ID for the business event |
| `status` | `PENDING`, `PROCESSING`, `RETRY_WAIT`, `SUBMITTED`, `FAILED` |
| `attempts` | Number of send executions performed |
| `next_attempt_at` | Next scheduled attempt timestamp |
| `created_at` and `expires_at` | Age/deadline control |
| `locked_by` and `locked_until` | Lease to prevent concurrent claims by multiple workers |
| `last_failure_class` | Failure classification |
| `last_error_code` | Normalized error code |
| `provider_message_id` | Provider ID if available |

An outbox enables recovery after a process crash. It cannot guarantee exactly-once delivery for SMTP if the worker dies after the server accepts the email but before writing `SUBMITTED`.

## 18. Example Outbox Schema With Retry Metadata

~~~sql
CREATE TABLE mail_outbox (
    id                 UUID PRIMARY KEY,
    idempotency_key    VARCHAR(200) NOT NULL UNIQUE,
    event_type         VARCHAR(120) NOT NULL,
    payload            JSONB NOT NULL,
    status             VARCHAR(30) NOT NULL,
    attempts           INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at         TIMESTAMPTZ,
    locked_by          VARCHAR(120),
    locked_until       TIMESTAMPTZ,
    last_failure_class VARCHAR(40),
    last_error_code    VARCHAR(120),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at       TIMESTAMPTZ
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

This is an illustrative PostgreSQL schema. For other databases, adjust JSON types, timestamp types, and index syntax. The `PENDING`/`RETRY_WAIT` index does not cover expired-lease `PROCESSING` records; add an appropriate query/index when implementing dead-worker reclamation.

Avoid storing large attachments as Base64 inside the payload when a durable file reference can be used. Do not store plaintext secrets or OTPs longer than necessary.

### Attempts Must Be Recorded Consistently

One implementation approach: when claiming to actually send, the worker increments `attempts`. If a task is merely submitted to an executor and rejected by the pool before running, you can keep `attempts` unchanged and track `dispatch_failures` separately.

Crucially, check `attempts >= maxAttempts` after `attempts` reflects the true number of sends executed; avoid incrementing twice for a single attempt.

## 19. Worker Coordinating Retries

Workers should split transactions:

1. Claim the outbox record in a short transaction, setting `PROCESSING`/lease.
2. Commit.
3. Send the email via `MailDeliveryPort` outside any transaction.
4. Open another transaction to write `SUBMITTED` or the retry schedule.

Conceptual outcome-handling example:

~~~java
public void process(MailOutboxRecord record) {
    try {
        mailDelivery.send(render(record));

        resultService.markSubmitted(record.id());

    } catch (PermanentMailSubmissionException exception) {
        resultService.markFailed(
            record.id(),
            "PERMANENT"
        );

    } catch (TransientMailSubmissionException exception) {
        RetryDecision decision = retryCoordinator.decide(
            record,
            MailFailureCategory.TRANSIENT
        );

        if (decision.retry()) {
            resultService.scheduleRetry(
                record.id(),
                decision.nextAttemptAt()
            );
        } else {
            resultService.markFailed(
                record.id(),
                decision.reason()
            );
        }

    } catch (AmbiguousMailSubmissionException exception) {
        resultService.markNeedsReconciliation(record.id());
    }
}
~~~

`MailOutboxRecord`, `MailDeliveryPort`, and `resultService` are application abstractions, not built-in Spring Framework Mail APIs. Orchestrating retry logic outside the adapter keeps the SMTP adapter free of scheduler, transaction, and deadline concerns.

### When a Worker Crashes

If a worker crashes in `PROCESSING`, the lease expires so another worker can claim the row. However, if SMTP already accepted the email before the worker died, a retry may cause a duplicate. Idempotency/reconciliation is a separate problem that leases alone do not solve.

## 20. Scheduler Polling Due Records

You can use `@Scheduled` with a database query to pick due records:

~~~java
@Component
public class MailOutboxScheduler {

    private final MailOutboxDispatcher dispatcher;

    public MailOutboxScheduler(MailOutboxDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelayString = "${app.mail.poll-delay-ms:1000}")
    public void tick() {
        dispatcher.dispatchDueBatch();
    }
}
~~~

Enable scheduling with appropriate configuration, such as `@EnableScheduling`. The dispatcher must claim records atomically and enforce a lease strategy.

Example PostgreSQL query inside a transaction:

~~~sql
SELECT id
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, created_at
FOR UPDATE SKIP LOCKED
LIMIT 50;
~~~

`FOR UPDATE SKIP LOCKED` prevents multiple workers from locking on rows currently being claimed by another transaction. After claiming, update status/lease and commit before calling SMTP; never hold database locks across network I/O.

With multiple instances or crashed workers, reclaim `PROCESSING` rows when their leases expire. Do not only poll `PENDING` and leave crashed `PROCESSING` records stuck forever.

## 21. Rate Limiters and Post-Outage Retry Storms

After a long outage, many records may become due around the same time. Jitter helps disperse them, but it does not guarantee the provider will not exceed its quota.

Combine:

- Concurrency-bounded thread pool.
- Rate limiter per SMTP account/provider.
- Claim batches sized to executor capacity.
- Exponential backoff with jitter for transient errors.
- Circuit breaker/cooldown during widespread provider failures.
- Durable queue/outbox to hold send requests.
- Metrics to tune batch sizes and rates.

If a dispatcher claims 1,000 records and pushes them into an internal queue holding only 100 tasks, many records' leases may expire before execution. Claim according to capacity, or start the lease when the task is actually picked up; if submission is rejected, return the record safely to a waiting state.

Do not let a single scheduler tick flood thousands of tasks just because all records reached `nextAttemptAt`.

## 22. Job Idempotency and SMTP Idempotency Differ

A unique constraint prevents creating multiple send requests for the same business event:

~~~sql
INSERT INTO mail_outbox (
    id, idempotency_key, event_type,
    payload, status
)
VALUES (
    :id, :key, :eventType, :payload, 'PENDING'
)
ON CONFLICT (idempotency_key) DO NOTHING;
~~~

Yet a worker can still send **one** record twice:

~~~text
Worker A calls SMTP, server accepts
       |
       v
Worker A crashes before marking SUBMITTED
       |
       v
Lease expires
       |
       v
Worker B retries
       |
       v
Recipient may receive two emails
~~~

Therefore distinguish:

- **Job idempotency**: preventing duplicate enqueues in the database.
- **Transport idempotency**: preventing duplicate send side effects at the provider.

There is no universal transport idempotency mechanism across all SMTP servers. `Message-ID` is useful for tracing, not a deduplication guarantee. If a provider API supports an idempotency key, pass the same key on retries of the same event.

For unknown outcomes, you can choose an `AMBIGUOUS`/`NEEDS_RECONCILIATION` state for further checks instead of auto-retrying immediately.

## 23. Retries by Email Type

Do not apply one policy to all notifications:

| Email type | Timing requirement | Retry approach |
| --- | --- | --- |
| OTP | Must arrive before code TTL | Few attempts, short deadline, never send expired codes |
| Password reset | Token has expiry and may be revoked | Stop if token is no longer valid |
| Order confirmation | Needs durable request and retry | Outbox, exponential + jitter |
| Invoice | Can tolerate longer wait | Retry with immutable snapshot/file reference |
| Newsletter | High volume, has unsubscribe | Separate campaign queue and rate limit |
| Debug email | Non-critical business priority | May omit retries |

Specific values must follow business SLAs and provider policies rather than taking a generic number from an example.

If data might change when retried minutes later, store an appropriate snapshot/version. For instance, if an invoice is updated after the event occurred, the worker must know which version to send rather than blindly reading the latest version if doing so would misrepresent the original event.

## 24. MaxAttempts and Terminal States

Once limits are exhausted, the record must move to an observable state:

~~~text
PENDING
  |
  v
PROCESSING (attempt 1)
  |
  v
RETRY_WAIT
  |
  v
PROCESSING (attempt 2)
  |
  ...
  |
  v
PROCESSING (attempt 5)
  |
  v
FAILED / DEAD_LETTER
~~~

Do not leave records in `RETRY_WAIT` indefinitely when they are no longer eligible for retry. When transitioning to `FAILED`, store a reason such as:

- `MAX_ATTEMPTS_REACHED`.
- `BUSINESS_DEADLINE_EXPIRED`.
- `RECIPIENT_INVALID`.
- `PROVIDER_POLICY_REJECTION`.
- `MANUAL_REVIEW_REQUIRED`.

You can build a manual requeue mechanism after resolving the root cause. Requeuing requires auditing, access control, and re-checking deadlines and idempotency. Never reset `attempts` to 0 automatically on every worker startup, as that defeats `maxAttempts`.

## 25. Metrics and Logs for Retry Policy

Values worth tracking:

- Attempt count by provider and outcome.
- Total scheduled retries by failure category.
- Jobs reaching `maxAttempts`.
- Delay `nextAttemptAt - now`.
- Age of oldest `PENDING`/`RETRY_WAIT` record.
- SMTP timeouts, throttling, and authentication failures.
- Rejected executor tasks.
- `AMBIGUOUS` jobs needing reconciliation.
- Time from `created_at` to `submitted_at`.
- `SUBMITTED` rate by email type.

Log example:

~~~json
{
  "notificationId": "notif-8fe2",
  "category": "ORDER_CONFIRMATION",
  "provider": "primary-smtp",
  "attempt": 3,
  "maxAttempts": 5,
  "failureCategory": "TRANSIENT",
  "smtpCode": "421",
  "retryDelayMs": 7421,
  "nextAttemptAt": "2026-11-12T12:00:07Z",
  "status": "RETRY_WAIT"
}
~~~

Never log raw email bodies, credentials, reset tokens, or full personal details. Prefer internal notification IDs, standardized error codes, and minimal diagnostic metadata.

### Operational Alerts

Watch for:

- Unusual growth in `RETRY_WAIT`.
- Many jobs repeatedly hitting `maxAttempts`.
- Rising provider `4xx`/throttling responses.
- Unsent record ages exceeding SLA.
- Rising expired-lease `PROCESSING` records.
- Rising `AMBIGUOUS` counts, possibly due to network timeouts.
- Sharp drop in submitted mail while new job volume continues growing.

Do not raise `maxAttempts` before identifying the root cause. If credentials are wrong, increasing retries only generates more failures.

## 26. Testing Backoff and Jitter

Retry policies can be unit-tested without an SMTP server.

### Verifying the Exponential Cap

With 1-second initial delay and 8-second max:

~~~text
failedAttempt = 1 => cap 1s
failedAttempt = 2 => cap 2s
failedAttempt = 3 => cap 4s
failedAttempt = 4 => cap 8s
failedAttempt = 5 => cap 8s
~~~

When using jitter, the actual delay does not equal the fixed cap. Tests should assert that the delay falls within the valid bounds.

Equal jitter example:

~~~java
@Test
void equalJitterFallsWithinExpectedRange() {
    MailBackoffPolicy policy = new MailBackoffPolicy(
        Duration.ofSeconds(1),
        Duration.ofSeconds(8)
    );

    RandomGenerator random = new Random(1234L);

    Duration result = policy.delayAfterFailure(3, random);

    assertFalse(result.compareTo(Duration.ofSeconds(2)) < 0);
    assertFalse(result.compareTo(Duration.ofSeconds(4)) > 0);
}
~~~

`failedAttempt = 3` has a 4-second cap, so equal jitter yields 2–4 seconds. A fixed seed makes the test reproducible, though you should avoid asserting a specific random sequence when only range bounds matter.

### Verifying Attempts and Deadlines

Tests should cover:

1. The first send is counted as attempt 1.
2. `maxAttempts = 5` does not allow a sixth attempt.
3. Permanent errors are not rescheduled.
4. Transient errors produce a `nextAttemptAt` after the current time.
5. Expired emails are not sent.
6. Ambiguous errors produce a distinct decision.
7. Provider cooldowns later than backoff are honored.
8. When the deadline is earlier than the next attempt, the policy stops.

### Testing the Worker

With a fake `MailDeliveryPort` and a test database:

- Worker retries after a temporary error.
- Worker marks `SUBMITTED` when the adapter succeeds.
- Expired leases are reclaimed.
- Two workers never claim the same record simultaneously.
- Executor rejection does not drop the request.
- A process crash after submission can produce a duplicate; the system has appropriate state/reconciliation.
- No DB transaction is held during sleeps or SMTP sends.

Inject `Clock` so tests do not wait for real seconds via `Thread.sleep` and do not depend on wall-clock time.

## 27. Common Anti-Patterns

| Anti-pattern | Consequence | Better approach |
| --- | --- | --- |
| Retry every `MailException` | Loops on permanent/config errors | Classify errors |
| Retry immediately without backoff | Retry storm | Bounded backoff |
| No jitter | Multiple workers retry together | Dispersion with jitter |
| No `maxAttempts` | Failing email loops forever | `maxAttempts` + failed state |
| No deadline | Sends expired OTP/email | Business-driven `expiresAt` |
| No delay cap | Excessive waits or overflow | `maxDelay` and safe math |
| Sleeping inside a transaction | Holds DB connections/locks | Persist `nextAttemptAt` and use scheduler |
| Long retries in HTTP request | Ties up thread, causes timeouts | Worker/outbox |
| Nested Worker + Spring Retry | More SMTP calls than intended | One clear retry owner |
| Treating timeouts as always unsent | Duplicate emails | Handle `AMBIGUOUS` |
| Treating `Message-ID` as guaranteed dedup | No guarantee from SMTP | Provider idempotency if supported |
| In-memory `@Async` queue only | Crashes lose jobs | Durable outbox/broker |
| Ignoring provider cooldowns | Continued throttling | Honor `Retry-After`/policy |
| Claiming too many tasks | Stuck records/expired leases | Bounded batches |
| Treating `SUBMITTED` as `DELIVERED` | Misrepresents recipient status | Separate delivery events |
| Logging email contents and secrets | Data leakage | Minimal ID/code/attempt logs |

## 28. Implementation Workflow

A complete retry flow can be built in this order:

1. **Define mail categories and SLAs**: OTP, transactional, invoice, campaign.
2. **Isolate the delivery adapter** so one call corresponds to one send attempt.
3. **Classify errors** into transient, permanent, configuration, and ambiguous.
4. **Configure `maxAttempts`, `initialDelay`, `multiplier`, `maxDelay`, jitter, and deadlines**.
5. **Apply rate limits and concurrency limits** per provider.
6. **For critical emails, persist to an outbox** in the same database transaction as business changes.
7. **Have workers claim records** in short transactions, set a lease, and send outside the transaction.
8. **If `SUBMITTED`**, record the outcome; track delivery events separately if available.
9. **If permanent**, mark `FAILED` without retrying.
10. **If ambiguous**, reconcile or apply the chosen idempotency policy.
11. **If transient**, check attempts/deadline, compute delay with jitter and provider cooldown.
12. **Save `nextAttemptAt`**, return the thread to the pool, and wait for the scheduler.
13. **If exhausted**, mark `FAILED`/`DEAD_LETTER` and alert.
14. **Monitor metrics**, and test overload, process crashes, concurrency, and provider errors.

~~~text
Due outbox record
          |
          v
Claim + check deadline
          |
          v
Send via MailDeliveryPort
          |
          +---- SUCCESS ------> SUBMITTED
          |
          +---- FAILURE
                    |
                    v
             Classify error
                    |
        +-----------+-----------+
        |           |           |
    PERMANENT    AMBIGUOUS   TRANSIENT
        |           |           |
        v           v           v
      FAILED     Reconcile   Check limits
                                |
                           +----+----+
                           |         |
                         Stop      Continue
                           |         |
                           v         v
                         FAILED   Backoff + jitter
                                     |
                                     v
                                nextAttemptAt
                                     |
                                     v
                                 RETRY_WAIT
~~~

## 29. Key Takeaways

- Retries only help for recoverable errors; permanent errors require fixing the root cause.
- An SMTP timeout does not always mean the email was not sent, so duplicate risk exists.
- `maxAttempts` must follow a clear convention; here it **includes the initial send attempt**.
- Exponential backoff increases delay across failures and is bounded by `maxDelay`.
- Jitter spreads out retry timestamps to reduce thundering herds.
- Full, equal, and decorrelated jitter have different properties; do not use one formula for every SLA.
- A business deadline may force stopping before `maxAttempts` is reached.
- Respect provider cooldown guidance and cap overall send throughput.
- Spring Retry fits short in-process retries; it does not replace a durable outbox.
- Avoid long sleeps inside HTTP requests or database transactions.
- Outbox workers should persist `nextAttemptAt`, lease, and attempt count to recover across restarts.
- Database idempotency differs from SMTP idempotency; `Message-ID` does not guarantee deduplication.
- Never nest multiple retry layers that push total sends past the budget.
- Record sufficient metrics/logs to monitor exhausted retries, queue age, and ambiguous outcomes.
- Once attempts or deadlines are exhausted, end the job in an observable, actionable state.

A good retry policy does not try to send forever at all costs. It selects the right errors to retry, paces attempts with backoff and jitter, stops when notifications lose value, and keeps state durable enough to operate safely. In Spring Framework Mail, combining **bounded exponential backoff, jitter, `maxAttempts`, deadlines, and an outbox worker** enables systems to weather transient failures while keeping SMTP load and duplicate risk under control.
