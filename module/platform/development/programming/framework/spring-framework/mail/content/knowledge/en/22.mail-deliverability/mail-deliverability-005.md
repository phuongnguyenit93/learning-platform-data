# Provider Rate Limits and Quotas

A Spring Framework Mail application may send emails very quickly in a test environment yet run into trouble in real deployment: the SMTP relay temporarily defers messages, a newsletter campaign slows down password-reset emails, queues spike suddenly, or the provider reports exceeding the daily sending threshold. Not all of these situations are `JavaMailSender` configuration bugs. Many providers enforce **rate limits**, **quotas**, **concurrent connection limits**, and sending-reputation protection policies to prevent resource abuse.

**Successful SMTP AUTH does not mean the account can send without limits.** Providers can limit by account, organization, IP, sender domain, recipient, time window, or multiple levels simultaneously. Exact numbers and quota accounting vary by provider and service plan. Spring Framework Mail does not provide a built-in throttle that knows all those limits upfront; the application must design an appropriate sending coordination mechanism.

This lesson distinguishes the types of limits, analyzes SMTP and HTTP email API responses, describes designing an outbox, rate limiters, concurrency guards, retries with backoff and jitter, priority-based quota allocation, operational monitoring, and testing under throttling. The goal is **controlled sending without losing pending work and without turning a retry wave into a new request storm**.

## 1. How Do Rate Limit, Quota, Concurrency, and Deliverability Differ?

| Concept | Definition | Illustrative Example |
| --- | --- | --- |
| Rate limit | Maximum operations within a time window | 60 messages/minute |
| Quota | Total volume permitted within a cycle/budget | 10,000 recipients/day |
| Concurrency limit | Number of active operations or connections at once | 5 simultaneous SMTP sessions |
| Deliverability | Likelihood that messages are accepted and delivered as intended | Messages are not bounced or filtered as spam |

The numbers in the table are **hypothetical examples**, not universal SMTP limits.

An account may not have exhausted 10,000 recipients/day yet still be throttled for sending 500 messages within a few seconds. Conversely, sending slowly yet steadily over many hours can push total recipient count over the daily quota.

Deliverability is a broader goal: respecting quotas helps avoid temporary deferrals by the provider, yet does not guarantee emails land in the inbox. Sender reputation, SPF, DKIM, DMARC, recipient lists, bounces, complaints, and message content also matter.

### Example of Three Limits Applying Simultaneously

A hypothetical provider specifies:

~~~text
Max 100 messages/minute
Max 15,000 recipients per 24 hours
Max 4 concurrent SMTP connections
~~~

A message sent to 1 recipient may consume one message and one recipient unit. A message sent to 50 recipients may still be one submission yet consume 50 recipient units, depending on provider rules. Even without exceeding 100 messages/minute, the application can still fail by opening 10 concurrent SMTP connections.

**Do not merely count `JavaMailSender.send(...)` calls to conclude how much quota was used.**

## 2. Types of Limits Providers Commonly Enforce

### 2.1. Message Throughput

Providers can cap message count per second, minute, or hour. This is a limit on **submission** rate. Using multiple threads or `@Async` does not make the limit disappear; it only creates more parallel send tasks.

### 2.2. Recipient Quota

A provider may count quota by total accepted recipients. For instance, a message with `To`, `Cc`, and `Bcc` may consume multiple recipient units. How rejected addresses, failed submissions, or retries are counted depends on the provider's contract.

### 2.3. Recipients per Message

There may be a cap on the number of addresses in a single message. Thus packing 1,000 recipients into one MIME message to "save quota" can be rejected while also increasing the risk of leaking addresses in To/Cc.

### 2.4. Concurrent SMTP Connections

Providers can cap simultaneous connections/sessions. A `ThreadPoolTaskExecutor` with 50 workers will not necessarily achieve higher throughput than a pool of 5 workers; it may trigger authentication failures, throttling, or connection rejections.

### 2.5. Message Size and Attachments

Another limit is total MIME size. Attachments may be base64-encoded and grow on the wire. A message exceeding the size limit will fail even if message/recipient counts are still within quota.

### 2.6. Sender Account, Domain, IP, and Tenant

Limits can exist at:

- SMTP username or API key.
- Provider account/subaccount.
- Organization or tenant.
- Sender domain, subdomain, or IP pool.
- Recipient domain.
- A specific recipient.
- A connection or service tier.

If three SMTP users share one provider organization, quota may still be aggregated at the organization level. **Multiple credentials do not automatically mean completely independent quotas.**

## 3. Limit Windows: Fixed, Sliding, and Token Bucket

A "100 emails/minute" rule can be implemented with several algorithms:

| Algorithm | Characteristics | Misunderstanding Risk |
| --- | --- | --- |
| Fixed window | Counter resets on time boundaries | Can burst at the boundary between two windows |
| Sliding window | Limit over a rolling time window | Smoother rate control |
| Token bucket | Tokens replenish over time, allowing bounded bursts | Large capacity can create overly strong bursts |
| Leaky bucket | Output is paced at a steady cadence | Tasks must wait |
| Rolling daily quota | Caps total volume over the trailing 24 hours | Does not reset cleanly at 00:00 local time |

Do not assume a "daily" quota resets at midnight in the application's time zone. A provider may use UTC, account time zone, or a rolling 24-hour window.

### Burst Rate vs. Sustained Rate

Suppose a provider allows 60 messages/minute, yet forbids more than 2 messages/second. If the application sends all 60 in the first second, the per-minute total is valid yet the instantaneous rate is violated.

Permits must be granted across **multiple limit tiers** when the provider publishes multiple thresholds, such as a per-second bucket and a daily quota.

## 4. How Are Spring Mail Applications Affected?

The call:

~~~java
MimeMessage message = mailSender.createMimeMessage();
// Set From, To, Subject, and body.
mailSender.send(message);
~~~

can **block** during TCP connect, TLS, SMTP AUTH, data transfer, and waiting for the response. When a provider temporarily defers:

- Processing time can increase.
- `JavaMailSender.send` may throw `MailException`.
- Sending threads stay occupied until timeout.
- Outbox or executor queues can grow.
- HTTP latency spikes if sending directly inside a request.
- Unbounded retries can cause the provider to block harder.

`@Async` only offloads work to an executor thread. It **does not** automatically regulate messages/second, recipients/day, or concurrent connections.

### More Threads Do Not Guarantee More Throughput

For example, a provider accepts 20 messages/second. If one worker averages 10 messages/second, increasing workers from one to four can push total demand past the limit. The system may receive more errors while actual accepted message count does not increase.

Control both **rate** and **concurrency**, while setting SMTP timeouts and backlog bounds.

## 5. SMTP Responses When Throttled

SMTP uses three-digit reply codes. Some servers add enhanced status codes and explanatory text.

| Class | General Meaning | Handling Approach |
| --- | --- | --- |
| `2xx` | Positive completion | Continue command/session per protocol |
| `4xx` | Transient negative completion | Evaluate delayed retry |
| `5xx` | Permanent negative completion | Do not retry blindly |

Codes you may encounter:

- `421`: Service unavailable or closing session; some providers use it for too many connections.
- `450`: Mailbox temporarily unavailable or temporarily rejected.
- `451`: Temporary server-side error; may be used for policy/throttling.
- `452`: Insufficient resources or temporary limit, potentially related to recipients/quota.
- `454`: Temporary error related to authentication/TLS depending on context.
- `550` / `553`: May be a recipient, relay, or policy rejection.
- `552`: May relate to storage or message size depending on context.

**Not every `421`, `451`, or `452` is quota throttling.** Inspect the reply text and provider documentation.

Illustrative response example:

~~~text
451 4.7.0 Temporarily deferred due to sending rate
~~~

The code `4.7.0` is an enhanced status in the policy/security category. The text states the throttling reason in this example, yet another provider may phrase or code it differently. Do not parse exceptions simply by searching for the word "quota."

### Temporary Failure Does Not Mean Retry Immediately

A `4xx` response indicates conditions may change after some time. If the application retries immediately, it can create a loop attacking its own provider.

Use backoff, jitter, attempt caps, and stopping policies.

## 6. Provider HTTP APIs Differ from SMTP

A system can send via:

1. SMTP using `JavaMailSender`.
2. The provider's HTTP REST API via WebClient/HTTP client.

With an HTTP API, the provider may return:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
~~~

`429` and `Retry-After` belong to the HTTP protocol. There is no reason to expect `JavaMailSender` to receive this HTTP status or header when using SMTP.

| Transport | Signals | Notes |
| --- | --- | --- |
| SMTP | Reply code, enhanced code, Jakarta Mail exception | Needs provider-specific error classifier |
| HTTP API | HTTP status, Retry-After, JSON error | Honor the HTTP API contract |
| Provider dashboard/admin API | Quota, usage, bounces, complaints | Data may not be strictly real-time |

If switching from SMTP to an HTTP API, application commands and the outbox can remain intact, while the transport/error classifier/quota integration layer must be adapted.

## 7. Message Quota and Recipient Quota Must Be Counted Separately

Consider a message with multiple recipients:

~~~java
helper.setTo("buyer@example.org");
helper.setCc("accounting@example.org");
helper.setBcc("audit@example.org");
~~~

There is one send-message command yet three intended recipients. Depending on the provider, it may consume one submission and three recipient units.

Metrics should be separated:

~~~text
message_attempt_total
message_submitted_total
recipient_attempt_total
recipient_accepted_total
recipient_rejected_total
local_quota_denied_total
provider_quota_remaining
~~~

Clearly define whether accepted means the application saw the send command succeed or the provider confirmed each recipient. Do not record "delivered" merely because SMTP send returned normally.

### Partial Acceptance

An SMTP session can encounter cases where some recipients are accepted and some are rejected, depending on the server and Jakarta Mail configuration. Retrying the **entire message** when one recipient fails can cause already-accepted recipients to receive duplicate emails.

For personalized emails and systems requiring accurate retry/audit, it is usually easier to manage when each logical recipient has **its own outbox job and its own message**.

## 8. Outbox and Rate-Controlled Worker Architecture

A suitable sending flow for applications requiring reliability:

~~~mermaid
flowchart TD
    A["HTTP request / Business event"] --> B["Application service"]
    B --> C["Authorization + recipient policy"]
    C --> D["Persist business state + outbox"]
    D --> E["Worker claim PENDING job"]
    E --> F["Global / account / tenant quota gate"]
    F --> G{"Permit granted?"}
    G -->|"No"| H["Defer to nextAttemptAt"]
    H --> E
    G -->|"Yes"| I["Concurrency gate"]
    I --> J["JavaMailSender.send"]
    J --> K["SMTP relay"]
    K --> L["Record result / retry"]
~~~

Roles:

- Application service decides when an email exists and who is allowed to receive it.
- Outbox persists the sending intent durably alongside the business transaction if needed.
- Worker claims jobs with a lease/token so multiple instances do not process the same job concurrently.
- Quota gate decides when the account may be used.
- Concurrency gate limits active connections/tasks.
- Mail gateway sends over SMTP without containing business policy.
- State service updates `SENT`, `RETRY`, or `DEAD` in a short transaction.

When quota is insufficient, the worker **does not call SMTP**. The job is deferred under control, not turned into an SMTP failure and not deleted from the outbox.

### Is an Outbox Mandatory?

No. For non-critical emails with low volume where losing tasks on process death is acceptable, a bounded executor may suffice. However, for invoices, transaction confirmations, or emails requiring audit/retry, an outbox is advantageous because work survives restarts.

## 9. Multi-Scope Rate Limiters

Suppose a provider account has a global limit of 100 messages/second. Two tenants have their own internal allowances:

~~~text
Provider account: 100 messages/second

Tenant A: 30 messages/second
Tenant B: 20 messages/second
Other tenants: share the remainder

Security: reserve a portion of priority capacity
Marketing: can queue longer
~~~

The numbers are illustrative. A job may send only if **all relevant scopes allow it**:

~~~text
provider-account
  → tenant
  → mail-purpose
  → recipient-domain (if required by policy)
~~~

A per-tenant limiter does not replace a global limiter. A global limiter does not protect fairness between tenants. Similarly, a per-message quota does not replace a per-recipient quota.

### When the Quota Service Is Unavailable

If Redis/database issuing permits fails, letting all workers send without limits can trigger provider throttling. Have a fail-safe policy:

- Defer bulk mail.
- Keep jobs in the outbox.
- Use conservative configured bounds if justified.
- Trigger alerts.
- For security emails, use an approved fallback rather than arbitrarily dropping quotas.

**Do not open all limiters wide just because the throttling system encountered an error.**

## 10. Token Bucket: Refill Rate and Burst

Token bucket is an intuitive way to throttle:

- The bucket has maximum capacity `C`.
- Tokens refill at rate `r` units/second.
- Each message requires one or more tokens.
- When tokens are sufficient, deduct tokens and allow.
- When tokens are insufficient, schedule sending later.

Example bucket with capacity 20 tokens, refill 5 tokens/second:

~~~text
Initially: 20 tokens
Send 8 messages: 12 tokens left
After one idle second: add up to 5 tokens
Insufficient tokens: SMTP must not be called
~~~

Formula:

\[
T_{\mathrm{new}} = \min(C,\; T + r \times \Delta t)
\]

If job cost is `c` and `T_new ≥ c`, grant the permit and subtract `c`. If insufficient, return `DENIED` along with the retry timestamp.

### Burst Capacity Must Not Be Too Wide

A bucket refilling at 1 token/second yet having a capacity of 1,000 tokens can allow a burst of 1,000 messages the moment the bucket is full. If the provider enforces a per-second limit, this setup can still cause throttling.

Base design on the provider contract, using multiple limiters when both a burst cap and a long-term quota are needed.

## 11. Single-JVM Sliding-Window Limiter Example

A gate can be illustrated in standard Java:

~~~java
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.Deque;

public final class LocalMailRateGate {

    private final int maxMessages;
    private final long windowNanos;
    private final Deque<Long> acceptedAt =
            new ArrayDeque<>();

    public LocalMailRateGate(
            int maxMessages,
            Duration window) {

        if (maxMessages <= 0
                || window == null
                || window.isZero()
                || window.isNegative()) {
            throw new IllegalArgumentException(
                    "Invalid rate window"
            );
        }

        this.maxMessages = maxMessages;
        this.windowNanos = window.toNanos();
    }

    public synchronized boolean tryAcquire() {
        long now = System.nanoTime();

        while (!acceptedAt.isEmpty()
                && now - acceptedAt.peekFirst()
                        >= windowNanos) {
            acceptedAt.removeFirst();
        }

        if (acceptedAt.size() >= maxMessages) {
            return false;
        }

        acceptedAt.addLast(now);
        return true;
    }
}
~~~

Usage example:

~~~java
LocalMailRateGate gate = new LocalMailRateGate(
        60,
        Duration.ofMinutes(1)
);

if (gate.tryAcquire()) {
    mailGateway.send(mail);
} else {
    // Record nextAttemptAt and return job to waiting state.
    // Do not sleep on the SMTP worker thread.
}
~~~

This is an **algorithm illustration**, not a complete production solution:

- Counters exist only within a single process.
- Does not share permits across instances.
- Does not calculate cost per recipient.
- Does not know the provider's daily quota.
- Does not preserve counters across restarts.
- Does not guarantee fairness or multiple quota windows.
- Does not by itself resolve permits granted when SMTP has not started yet.

With multiple instances, a shared permit system or explicit capacity partitioning is required.

## 12. Distributed Limiters and Atomic Updates

If three worker instances each allow 60 messages/minute, the total can reach 180/minute even though the provider only allows 60/minute.

Solutions can include:

- Redis + Lua atomic script/token bucket.
- Database counter with transactions/conditional updates.
- A centralized dispatcher.
- Broker/queue with defined worker count and throughput.
- A distributed rate-limiting system suited to the infrastructure.

The core requirement is **check-and-consume must be atomic**. Do not do:

~~~text
count = GET(account_key)
if count < limit:
    SET(account_key, count + 1)
    return ALLOWED
~~~

Two workers can both read that count still has room and both increment.

Instead, the quota authority must execute:

~~~text
tryAcquire(account, tenant, purpose, cost):
  atomically:
    update window/tokens
    check relevant limits
    if sufficient:
      consume permit
      return ALLOWED
    if insufficient:
      do not consume
      return DENIED + retryAt
~~~

When a job spans multiple scopes, design permit acquisition so it does not consume quota in one scope and then fail in another unintentionally. With Redis, handle clocks, TTLs, key cardinality, and availability. If the quota authority loses connectivity, workers must follow the fail-safe policy.

### Local Quota Is an Estimate; the Provider Is the True Limit Source

Application counters may not accurately reflect provider usage if there are:

- Other applications sharing the same credentials.
- Manual sends by admins.
- Provider counting recipients and submissions differently than expected.
- Retries or partial acceptance.
- Provider changing quota/plan.

If the provider offers an API reporting remaining/reset quota, it can be used to calibrate the limiter, while accounting for update lag, account scope, and metric semantics.

## 13. Which Step of the Outbox Worker Holds the Rate Gate?

Two common patterns:

**Claim first, then request permit.** The worker claims a job in a short transaction. If the limiter denies, record waiting status and `nextAttemptAt`, then release the lease. Do not hold transactions open and do not increment the SMTP attempt count if send was not called.

**Request permit first, then claim.** The dispatcher grants capacity first, then claims a matching number of jobs. Must handle permits granted when no job exists or when a worker crashes before using the permit.

Both have trade-offs. What matters is:

- Do not hold DB row locks while waiting for quota.
- Do not keep many worker threads `sleep`ing for hours.
- Do not hot-retry.
- Do not record "SMTP failed" when SMTP was never called.
- Do not turn quota denials into deleted jobs.
- Do not grant a permit for account A and then send through account B.

### Distinguishing Quota Wait State from Send Failure

You can use a state machine:

~~~text
PENDING
WAITING_RATE_LIMIT
SENDING
RETRY
SENT
DEAD
~~~

`WAITING_RATE_LIMIT` indicates the job has not called the provider due to lacking a permit. `RETRY` can indicate a failed send attempt or unknown outcome. If you prefer not to add statuses, you can use `PENDING + nextAttemptAt + reasonCode`; you still must distinguish an **actual attempt** from an **internal deferral**.

## 14. Worker Pseudocode Combining Quota and Concurrency

~~~java
public void process(ClaimedMailJob job) {

    SenderAccount account =
            routingPolicy.resolve(
                    job.tenantId(),
                    job.mailPurpose()
            );

    QuotaCost cost = new QuotaCost(
            1,                      // Message submission.
            job.recipientCount()    // Recipient units.
    );

    PermitDecision permit =
            quotaService.tryAcquire(
                    account.id(),
                    job.tenantId(),
                    job.mailPurpose(),
                    cost
            );

    if (!permit.allowed()) {
        stateService.scheduleForQuota(
                job.id(),
                job.claimToken(),
                permit.retryAt()
        );
        return;
    }

    try {
        concurrencyGate.withPermit(
                account.id(),
                () -> mailGateway.send(
                        account,
                        renderer.render(job)
                )
        );

        stateService.markSent(
                job.id(),
                job.claimToken()
        );

    } catch (MailException transportError) {
        stateService.recordTransportFailure(
                job.id(),
                job.claimToken(),
                transportError
        );
    }
}
~~~

This is **Java architectural pseudocode**. `ClaimedMailJob`, `QuotaCost`, `PermitDecision`, `StateService`, and gateway classes are application-defined abstractions. Production code must separate renderer, send, status-update errors, and lost-lease cases. Never wrap the entire SMTP call in a long-running DB transaction.

### What If a Permit Was Granted but Not Sent?

The provider may count quota by actual submissions, while the local limiter consumes tokens beforehand. If a worker crashes right after acquiring a token, the local count may exceed actual usage. This is generally more **conservative** than reissuing tokens loosely and risking quota exhaustion. To refund permits, you must be certain no external side effect occurred and the limiter contract supports it.

Do not automatically refund tokens on timeout without knowing whether the SMTP relay accepted the message.

## 15. Limiting Concurrent Connections with Semaphore

A rate limiter does not replace concurrency limits. If a send takes 10 seconds, even a submission rate of 30 messages/minute can hold many active connections open simultaneously.

A local example:

~~~java
import java.util.concurrent.Semaphore;

public final class LocalConnectionGate {

    private final Semaphore permits =
            new Semaphore(5, true);

    public void runWithPermit(Runnable operation)
            throws InterruptedException {

        permits.acquire();

        try {
            operation.run();
        } finally {
            permits.release();
        }
    }
}
~~~

The number 5 is only an example. Bound permit wait time, handle interruption, and handle shutdown. A `Runnable` does not throw checked exceptions; in applications, a custom functional interface can be used.

**A Semaphore in one JVM does not protect the provider's aggregate limit across multiple JVMs.** Use a distributed limiter or assign fixed capacity per worker group so the sum does not exceed the cap.

## 16. @Async and ThreadPoolTaskExecutor Are Not Quota Managers

~~~java
@Async("mailExecutor")
public CompletableFuture<Void> sendAsync(MailCommand command) {
    mailGateway.send(command);
    return CompletableFuture.completedFuture(null);
}
~~~

`@Async` only executes the method via an executor if the call passes through a suitable Spring proxy. It has no awareness of provider quotas. If 10,000 events are pushed into the executor:

- In-memory queues can grow huge.
- Many threads may call SMTP simultaneously.
- A full queue can trigger task rejection.
- `CallerRunsPolicy` can push tasks back onto request threads.
- When the JVM dies, tasks still in RAM can be lost.

An outbox with rate-controlled workers is often better suited for important notifications. `@Async` can assist concurrency inside workers, provided there is a bounded executor, rate gate, and monitoring.

## 17. Classifying Errors from JavaMailSender

`JavaMailSender.send` can throw exceptions from the `org.springframework.mail` layer such as `MailSendException`, with deeper causes from Jakarta Mail or the SMTP provider.

An error taxonomy can be built:

~~~java
public enum MailFailureCategory {
    PROVIDER_THROTTLED,
    QUOTA_EXHAUSTED,
    TEMPORARY_TRANSPORT,
    PERMANENT_RECIPIENT,
    MESSAGE_TOO_LARGE,
    AUTHENTICATION_FAILED,
    TLS_CONFIGURATION,
    UNKNOWN_OUTCOME
}
~~~

~~~java
public interface MailErrorClassifier {
    MailFailureCategory classify(
            Throwable error,
            SenderAccount account);
}
~~~

Implementations must inspect the exception chain, extractable SMTP status/enhanced status codes, provider documentation, command context, and session state. When there are multiple recipients, check per-address accept/reject details exposed by the library.

Wrong:

~~~java
if (error.getMessage().contains("limit")) {
    retryImmediately();
}
~~~

Message strings can change, are unstructured, may contain PII, or may refer to a limit unrelated to rate. Include an `UNKNOWN_OUTCOME` branch and record structured reason codes.

### 4xx Can Be Retried, Yet Needs a Schedule

A temporary error does not mean try right away. Use backoff/jitter, quota reset hints when available, max attempts, and priority policies.

## 18. Exponential Backoff and Jitter

A common formula:

\[
d_n = \min(d_{\max}, d_{\mathrm{base}} \cdot 2^{n-1}) + J_n
\]

Where `n` is the nth attempt, `d_base` is the initial wait, `d_max` is the cap, and `J_n` is jitter.

Example with 30-second base, 30-minute cap:

| Retry | Base Delay Before Jitter |
| --- | --- |
| 1 | 30 seconds |
| 2 | 60 seconds |
| 3 | 120 seconds |
| 4 | 240 seconds |
| 5 | 480 seconds |
| 6 | 960 seconds |

Numbers are illustrative only. Do not compute unbounded exponents on integers causing overflow. If the provider HTTP API returns `Retry-After` or a dashboard exposes reset times, use documented signals to adjust schedules.

### Retry Storm

Do not do:

~~~java
while (true) {
    try {
        mailSender.send(message);
        break;
    } catch (MailException ex) {
        // Retry immediately, no sleep/backoff.
    }
}
~~~

This loop has no attempt cap, no error classification, can spam the provider, and causes duplicates on ambiguous timeouts.

Instead, the worker writes `RETRY` with `nextAttemptAt`, releases the thread, and the scheduler only claims jobs once due. Internal quota denials can use their own schedule and need not count as SMTP attempts.

## 19. Exhausted Daily Quota Differs from Per-Second Limits

The provider reports no daily quota remaining at 13:00. Retrying after 5 seconds will not help if quota resets hours later.

A decision object:

~~~java
public record PermitDecision(
        boolean allowed,
        Instant retryAt,
        String reasonCode) {
}
~~~

Example internal reason codes:

~~~text
RATE_PER_SECOND
RATE_PER_MINUTE
DAILY_QUOTA
ACCOUNT_SUSPENDED
CONCURRENCY_FULL
PROVIDER_BACKOFF
~~~

Do not treat `ACCOUNT_SUSPENDED` as normal throttling; operational intervention may be needed. Quota reset timing must come from the contract/provider or an observed conservative estimate, not assumed to be midnight.

### Protecting a Portion of Capacity

If security and marketing share an account quota, a bulk campaign can exhaust the budget before customers needing password resets. You can:

- Separate accounts/subaccounts if the provider offers separate quotas.
- Reserve capacity for security/transactional mail.
- Defer marketing when remaining quota is low.
- Use priority queues and per-purpose limits.
- Set a global cap covering all accounts sharing an organization/IP.

Never allow marketing requests to change their purpose to security to bypass quotas.

## 20. Idempotency During Retries

Two forms of duplication:

1. **Duplicate enqueue:** One event creates two outbox jobs.
2. **Duplicate external submission:** The same job is sent twice after a retry/crash.

A unique idempotency key per event/purpose/recipient reduces duplicate enqueues. Yet it does not create an atomic transaction between the database and SMTP.

~~~text
Worker sends mail
SMTP relay accepts message
Network drops before worker receives response
Worker sees timeout
Worker retries
SMTP may accept the message a second time
~~~

`Message-ID` is a message identifier header for tracing/threading; it does not force an SMTP relay to deduplicate. If a provider HTTP API truly supports an idempotency key, follow the provider's contract using the same key across retries.

**Do not claim exactly-once delivery merely because you use an outbox and `JavaMailSender`.**

## 21. Fairness Across Tenants and Email Types

A global FIFO queue can let 100,000 marketing emails from tenant A block new transactional emails from tenant B.

Ways to mitigate this:

- Separate priority queues or lanes by purpose.
- Cap jobs claimed per tenant per batch.
- Weighted fair scheduling.
- Rate caps per tenant, provider account, and purpose.
- Reserved capacity for security.
- Dedicated rate limits for bulk/campaigns.
- Monitor queue age by mail type, not just total backlog.

Priority does not mean bypassing provider quotas. When quota is genuinely exhausted, the application must defer or use a fallback route **approved for the same purpose**, never automatically route marketing through the security account.

## 22. Separating SMTP Accounts for Load Isolation

Applications can use:

~~~text
securityMailSender
transactionalMailSender
marketingMailSender
~~~

Each `JavaMailSenderImpl` has its own host/credentials/sender identity, routed by `MailPurpose`.

~~~java
public enum MailPurpose {
    SECURITY,
    TRANSACTIONAL,
    MARKETING
}
~~~

~~~java
public interface MailRoutingPolicy {
    SenderAccount resolve(
            MailPurpose purpose,
            UUID tenantId);
}
~~~

**Do not let HTTP clients choose the SMTP account arbitrarily.** Application services determine purpose from authorized use cases.

Remember too: multiple usernames under the same provider organization may still share quotas, reputation, or IP pools. Isolation intended to reduce blast radius must be verified at the provider level.

## 23. Estimating Capacity by Throughput

Suppose 12,000 transactional emails must be sent within 2 hours. Each message has one recipient; the provider has hypothetical limits of 150 messages/minute and 20,000 recipients/day.

Required average rate:

\[
r = \frac{12\,000}{120} = 100\ \text{messages/minute}
\]

Arithmetically, 100/minute is below 150/minute and 12,000 recipients is below 20,000/day. Yet the system must also account for:

- Traffic from other features sharing the same quota.
- Per-second and concurrency limits.
- SMTP latency, timeouts, attachment sizes.
- Retries increasing total attempts.
- Quota reset times and domain-specific deferrals.
- Capacity needing to be reserved for security.
- Peak load at specific moments rather than averages alone.

If the provider cap is lower than demand, **adding threads does not solve the problem**. Extend the sending schedule, reduce bursts, allocate capacity, or upgrade plans/providers per policy.

### Estimating Concurrency with Little's Law

If target throughput is `λ` messages/second and one send averages `W` seconds, average concurrency is roughly:

\[
L \approx \lambda W
\]

For example, needing 2 messages/second with average SMTP latency of 1.5 seconds implies a theoretical minimum concurrency around 3. This is only an estimate; p95/p99 latency, connection reuse, and provider caps may require tuning. Do not use this formula to ignore hard concurrency limits.

## 24. Configuring SMTP Timeouts in Spring Boot

~~~yaml
spring:
  mail:
    host: smtp.provider.example
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

Host, port, and timeouts are illustrative values. JavaMail timeouts are in milliseconds. They prevent threads from hanging indefinitely, **they are not rate limiters**. A timed-out send can still have an indeterminate outcome.

STARTTLS/implicit TLS and certificate verification protect the connection; they do not govern quotas. SPF/DKIM/DMARC authenticate the sender domain; they likewise do not increase throughput. Do not disable TLS or switch domains just to evade throttling.

## 25. Deliverability and Post-SMTP Feedback

`JavaMailSender.send` returning normally does not mean the email reached the inbox. The relay may still:

- Temporarily defer at the receiving server.
- Bounce because the mailbox does not exist.
- Route into the spam folder.
- Reject later based on policy/domain.
- Receive spam complaints or unsubscribes.

Improving deliverability requires:

1. Valid, authorized recipients checked per purpose.
2. Handling hard bounces, unsubscribes, and complaints.
3. Properly authenticated sender domains with SPF/DKIM/DMARC.
4. High-quality content, cadence, and sending lists.
5. Warm-up and rate ramping when sender domains/IPs are new.
6. Avoiding duplicates from non-idempotent retries.
7. Measuring provider feedback, not just local send success.

**Submitted, SMTP accepted, delivered, and opened are distinct states.** Do not collapse them into a single "email succeeded" flag.

## 26. Warm-Up, Ramp-Up, and Recipient Domains

A new sender domain or IP can be flagged as anomalous if volume jumps suddenly from dozens to tens of thousands of messages. Even if technical quota allows it, deliverability can still suffer.

Strategy:

- Start with appropriate volume and valid recipients.
- Increase according to acceptance/bounce/complaint signals.
- Avoid huge bursts right after deploy.
- Throttle down if deferrals or complaints rise.
- Do not use unconsented lists to "warm up."

There is no single safe ramp schedule across all providers. Concrete thresholds should be guided by provider documentation and live observation.

A receiving server may temporarily defer multiple messages to the same domain even while the sending provider still has quota. When consistent, grounded signals appear, you can set a per-recipient-domain rate limit. Yet do not treat every error for that domain as throttling without analysis.

## 27. Quota Monitoring and Alerting

Useful metrics:

| Metric | Meaning |
| --- | --- |
| `mail_send_attempt_total` | Number of send attempts |
| `mail_smtp_accepted_total` | Number of sends successful per API |
| `mail_provider_throttle_total` | Number of errors classified as throttling |
| `mail_quota_denied_total` | Number of jobs deferred by local gates |
| `mail_queue_depth` | Number of waiting jobs |
| `mail_oldest_pending_age_seconds` | Longest wait duration |
| `mail_retry_total` | Number of retries |
| `mail_send_duration_seconds` | SMTP latency |
| `mail_active_send_count` | Concurrent active sends |
| `mail_provider_remaining_quota` | Remaining quota reported by provider |
| `mail_dead_job_total` | Number of jobs requiring intervention |

Attach account/purpose/tenant labels as operationally viable while avoiding excessive metric cardinality. Provider quota metrics may update with lag; do not assume local estimates match provider numbers exactly.

### Alerts Worth Watching

- Security emails waiting longer than SLA.
- Remaining quota below projected sending demand.
- Unusual spikes in SMTP throttling.
- Retry rate rising while accepted throughput does not increase.
- Connection timeouts or latency increasing.
- Queue age rising continuously.
- Workers still retrying too quickly after daily quota is exhausted.
- Traffic originating from an unexpected SMTP account.
- `DEAD` jobs increasing under a given reason code.

A hundred password-reset emails waiting 15 minutes can be more severe than tens of thousands of marketing emails sending on schedule. Monitor **queue age and purpose**, not just counts.

## 28. Safe Auditing

A send record may contain:

~~~text
mail_job_id: job-412
business_event_id: evt-981
tenant_id: tenant-42
purpose: TRANSACTIONAL
sender_profile: tx-primary
recipient_contact_id: contact-77
attempt: 3
failure_category: PROVIDER_THROTTLED
next_attempt_at: 2026-11-12T12:30:00Z
provider_reply_class: 4xx
~~~

Do not log SMTP passwords, reset tokens, email bodies, attachments, or full recipient addresses unless necessary and properly protected. Prefer correlation IDs, contact IDs, masking, and structured reason codes.

Audits should answer: which job, which event, which account, why it was deferred, how much quota remained, when it retries, the provider outcome, and who triggered any manual replay.

## 29. Testing Rate Limits and Throttling

### 29.1. Local Limiter

- Grants up to the exact maximum permits.
- Subsequent permit is denied.
- New permit available after the window elapses.
- Concurrent calls from two threads do not exceed the cap.
- Time math does not overflow or reset incorrectly.

### 29.2. Multi-Instance Distributed

- Two or more workers simultaneously request permits from shared quota.
- Total permits do not exceed the simulated global cap.
- Tenant A does not exceed the tenant cap.
- When the quota authority is unavailable, the system follows fail-safe policy.

### 29.3. SMTP Test Server Simulating Throttling

- Server returns `4xx` errors with illustrative text.
- Classifier recognizes documented provider errors properly.
- Job transitions to `RETRY` with `nextAttemptAt`.
- No hot-retrying.
- Enforces max attempts and classifies as `DEAD` when appropriate.

### 29.4. Daily Quota Exhaustion

- Local gate denies and reschedules the job.
- Does not keep threads sleeping for hours.
- Quota and queue-age alerts fire.
- Priority/security policies are honored without exceeding provider caps.

### 29.5. Concurrency

- With 50 jobs and cap 5, no more than 5 sends run concurrently within the guarded scope.
- Permits are released when errors occur.
- Test cluster-wide when the provider limits account-wide, not just single-JVM.

### 29.6. Partial Recipient Success

- Some RCPTs are accepted, some are rejected.
- Does not retry all recipients without checking statuses already accepted by the relay.
- Has appropriate per-recipient retry/audit mechanisms.

### 29.7. Ambiguous Timeout

- Fake transport simulates relay accepting message while caller times out.
- Worker does not assert "not sent" with certainty.
- Retry/reconciliation policy and duplicate-risk alerts are tested.

### 29.8. Restart

- Pending outbox jobs are not lost.
- Expired leases allow reclaiming.
- `SENT` jobs are not reclaimed normally.
- Rate-limit denials are not counted as SMTP attempts.

Never use production SMTP credentials in automated tests; use fake mail senders, SMTP test servers, or appropriate provider sandboxes.

## 30. Common Mistakes

### 30.1. Thinking Successful SMTP AUTH Means Unlimited Sending

Authentication only proves the account is authenticated. Rates, quotas, and policies still apply.

### 30.2. Only Increasing the Thread Pool

Concurrency does not equal valid throughput; it can hit connection limits faster.

### 30.3. Using @Async as a Rate Limiter

`@Async` does not manage provider quotas.

### 30.4. Local Limiters When Deploying Multiple JVMs

The sum of limiters can exceed the global cap. A distributed quota authority is needed.

### 30.5. Treating Every SMTP 4xx as a Quota Error

SMTP 4xx has many causes. Classify by provider reply and context.

### 30.6. Retrying Immediately Without Backoff/Jitter

Causes retry storms, degrades recovery, and can send duplicates.

### 30.7. Confusing HTTP 429 with SMTP Replies

`429`/`Retry-After` belong to HTTP APIs. SMTP has its own response codes.

### 30.8. Not Counting Recipients

`To`, `Cc`, and `Bcc` can consume multiple recipient units depending on the provider.

### 30.9. Holding SMTP Threads Waiting for Quota Reset

Exhausts threads and resources. Save `nextAttemptAt` and return the job to the queue.

### 30.10. Not Allocating Fairness

One campaign can consume all quota, delaying security emails.

### 30.11. Marketing Automatically Switching to the Security Account

Violates sender policy, breaks quota isolation, and can harm reputation.

### 30.12. Not Setting SMTP Timeouts

Network I/O can block workers longer than expected.

### 30.13. Treating Error-Free Send as Delivered

The SMTP relay may accept the message yet bounce or spam-filter it later.

### 30.14. Retrying All Recipients When Only One RCPT Was Rejected

Can send extra copies to recipients already accepted.

### 30.15. Not Recording Uncertain Outcomes

A timeout after SMTP DATA does not prove the message was not sent.

### 30.16. Limiting Only Per Day and Ignoring Per-Second Bursts

You can still get throttled despite remaining daily quota.

### 30.17. Failing Open When Redis Quota Errors

Can push all workers into the provider at once. A fail-safe policy is required.

### 30.18. Increasing Quota While Ignoring Deliverability

Higher quotas do not fix bounces, complaints, missing SPF/DKIM/DMARC, or list quality.

## 31. Practice Questions

**Question 1.** A provider allows 10,000 recipients/day, and each message has 5 recipients. If 2,000 messages are fully accepted, how many recipient units are consumed under a one-unit-per-recipient rule?

10,000 recipient units. However, verify the provider's actual quota accounting.

**Question 2.** Three instances each allow 100 messages/minute, while the provider allows 100/minute account-wide. Is this safe?

No. Theoretical total can reach 300/minute. Use a shared limiter or formal capacity allocation.

**Question 3.** Does `@Async("mailExecutor")` with 50 threads automatically prevent throttling?

No. It only dispatches threads.

**Question 4.** SMTP returns `451 4.7.0`. Can we conclude the daily quota is exhausted?

No. Check reply text, provider contract, and context.

**Question 5.** An HTTP API returns `429 Retry-After: 120`. Does `JavaMailSender` read it automatically?

No. `JavaMailSender` is an SMTP sender; HTTP API is a different transport.

**Question 6.** The relay accepted the message, but the worker timed out before seeing the response. Can a retry cause duplicates?

Yes. The outcome is uncertain and requires a dedicated policy.

**Question 7.** Daily quota is exhausted and resets in 10 hours. Should the worker `Thread.sleep` for 10 hours?

No. Save `nextAttemptAt` and release the thread.

**Question 8.** How can 100,000 marketing jobs be prevented from blocking password resets?

Use routing/purpose, priority lanes, reserved capacity, and fairness under a global quota cap.

**Question 9.** Is a 100/minute token bucket enough if the provider limits to 4 concurrent connections?

Not yet. A concurrency gate is also needed.

**Question 10.** Do two SMTP users under the same provider account have independent quotas by default?

No. Verify the provider's quota scope.

**Question 11.** SMTP has not been called yet because the local gate denied the job. Should the SMTP attempt count be incremented?

Normally no; distinguish local deferral from an actual attempt.

**Question 12.** Does `JavaMailSender.send` succeeding prove the email reached the inbox?

No. Track delivery/bounces separately if required by the business.

## 32. Mental Model

~~~mermaid
flowchart TD
    A["Email command / Business event"] --> B["Authorization + recipient policy"]
    B --> C["Durable outbox"]
    C --> D["Worker claim"]
    D --> E["Account/global quota"]
    E --> F["Tenant/purpose quota"]
    F --> G{"Permit granted?"}
    G -->|"No"| H["Reschedule / backpressure"]
    H --> D
    G -->|"Yes"| I["Concurrency guard"]
    I --> J["JavaMailSender"]
    J --> K["SMTP provider"]
    K --> L{"Outcome"}
    L -->|"Accepted"| M["Mark submitted/sent"]
    L -->|"Temporary throttle"| N["Backoff + jitter"]
    L -->|"Permanent"| O["Dead + audit"]
    L -->|"Unknown"| P["Reconcile or controlled retry"]
    N --> D
~~~

Key takeaways:

1. **Rate limit, quota, concurrency, and deliverability are distinct concepts.**
2. **A single provider may limit across multiple scopes at once**: messages, recipients, accounts, domains, IPs, tenants, and time windows.
3. **There is no universal SMTP quota across providers**; inspect contracts and actual signals.
4. **`@Async`/thread pools are not rate limiters**; SMTP still blocks on workers.
5. **Use an outbox/queue and backpressure** so jobs are not lost while waiting for quota.
6. **Grant permits atomically cluster-wide** when multiple instances share an account.
7. **Control both sending rate and concurrent connections.**
8. **SMTP 4xx can be temporary, yet not every 4xx is throttling**; classify errors per provider.
9. **HTTP 429/Retry-After belong to HTTP APIs**, and do not appear automatically in SMTP.
10. **Retry with backoff, jitter, and max attempts**, not busy loops.
11. **Idempotency and unknown outcomes** must be designed to limit duplicates on retries/crashes.
12. **Separate security/transactional from bulk marketing**, while still respecting global provider caps.
13. **Monitor quotas, queue age, throttling, bounces, and complaints**, not just successful `send` counts.
14. **SMTP accepted does not guarantee delivered**, and available quota does not mean emails reach the inbox.

In Spring Framework Mail, `JavaMailSender` is responsible for sending MIME over the configured transport. **The application is responsible for pacing sends within provider limits**, persisting work durably when needed, allocating capacity fairly across email types, and handling failures with accurate state tracking. When rate limiters, outboxes, retries, and operational observability are combined properly, critical transactional emails are far less likely to be disrupted by bulk sending waves, throttling drops, and the system gains a solid foundation for long-term deliverability improvements.
