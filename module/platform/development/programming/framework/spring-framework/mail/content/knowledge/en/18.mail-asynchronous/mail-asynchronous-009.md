# Rate Limiting to Avoid Overloading the Mail Server in Spring Framework Mail

When an application sends emails asynchronously, moving send calls out of the HTTP request only solves the problem of **not making users wait on SMTP**. It does not automatically protect the mail server from sudden email spikes. A system can generate tens of thousands of notifications from order events, campaigns, data imports, or replay processes; if workers all call `JavaMailSender.send(...)` at full speed, the SMTP relay can become overloaded, build up queues, reject connections, delay messages, or enforce rate restrictions.

Therefore, an asynchronous email-sending architecture needs **rate limiting** (limiting sends over time) combined with **concurrency limiting** (limiting simultaneous in-flight SMTP operations), **backpressure** (throttling when downstream slows down), and **queue management** (managing durable backlogs). The goal is not simply “sending slower”, but **sending at a rate the system and provider can sustain without losing critical emails or letting queues grow without bound**.

In Spring Framework Mail, `JavaMailSender` provides the API to build and send emails. It does not automatically enforce global quotas per provider, domain, tenant, or campaign. Throttling policies must be designed at the application, dispatcher, or shared email service layer.

## 1. What Does “Overloading the Mail Server” Mean?

Mail servers typically accept messages, place them into a spool/queue, and relay them to receiving servers. If incoming volume exceeds processing capacity or granted quotas, several problems can appear:

- Queues at the SMTP relay grow, delaying message delivery.
- The server refuses additional connections or send commands for a period.
- Per-minute, per-hour, or daily message or recipient quotas are exceeded.
- Memory, CPU, disk, or MIME-processing resources are exhausted.
- Too many parallel SMTP connections lead to timeouts.
- The provider temporarily restricts the sender due to anti-spam policies or traffic quality issues.
- Receiving domains may apply their own throttling policies even if the first-hop relay still accepts messages.
- An optional email campaign consumes resources, delaying critical OTP or transactional emails.

Do not think of “full” as only running out of disk space. It also includes **running out of processing capacity, exhausting quotas, or accumulating too many queued messages** in the application, broker, relay, or receiving system.

### Where Queues Exist

~~~mermaid
flowchart LR
    A["Business events"] --> B["App outbox / queue"]
    B --> C["Mail workers"]
    C --> D["Rate & concurrency gates"]
    D --> E["SMTP relay"]
    E --> F["Relay delivery queue"]
    F --> G["Recipient MX"]
    G --> H["Mailbox"]
~~~

Each stage has different throughput and capacity. Even when the SMTP relay replies that it accepted a message, the relay may still have to queue and deliver it in subsequent steps. **A successful `send()` does not mean the recipient sees the email in their inbox.**

## 2. Distinguishing Rate Limits, Concurrency Limits, and Backpressure

Three mechanisms solve different problems:

| Mechanism | What Does It Limit? | Example |
| --- | --- | --- |
| Rate limiting | Number of messages/recipients/bytes over a time window | Maximum 300 emails per minute |
| Concurrency limiting | Number of SMTP operations running simultaneously | Maximum 4 active connections or sends |
| Queue bounding | Number of waiting jobs in memory/broker | Cap of 500 tasks in executor |
| Backpressure | Adjusting pickup/acceptance rate when downstream slows | Worker stops claiming when no permits remain |
| Retry backoff | Spacing between attempts after failure | Retry after 1, 2, 4 minutes per policy |
| Circuit breaking | Temporarily pausing downstream calls on widespread failure | Pause SMTP when relay is unavailable |

**Limiting thread count alone is not equivalent to limiting emails per minute.** A single thread can send very rapidly and exceed quotas. Conversely, a 100 emails/minute limit allowing 100 simultaneous connections can produce bursts that overload the relay. In practice, both rate limits and concurrency limits are usually needed.

### Example: 4 Workers Do Not Guarantee 4 Emails/Second

If each send takes around 100 ms, four workers can complete dozens of sends per second. If the provider allows fewer, capping at 4 workers is insufficient. If each send takes 10 seconds, the same 4 workers reduce throughput drastically. A rate limit sets the **budget over time**, whereas a concurrency limit sets **how many calls are active at once**.

### Queue Capacity Formula

Let:

- `λ` (lambda): arrival rate of messages into the application, in emails/second.
- `μ` (mu): sustained processing/sending rate, in emails/second.
- `Q`: number of waiting emails.

When the system continuously has work, approximate backlog growth rate is:

\[
\frac{dQ}{dt} \approx \lambda - \mu
\]

If `λ > μ` persists, the backlog grows; no finite-capacity queue can hold it forever. If `λ < μ` for long enough, the system can drain the backlog. **Rate limiting protects the mail server, yet must be paired with input controls and long-term throughput capacity so queues do not grow indefinitely.**

## 3. Identify Actual Limits Before Configuring

Limits can come from the SMTP provider, internal relays, receiving domains, and application policies. Before picking numbers, identify the **unit of measure and scope**.

| Limit Type | Example Unit | Question to Confirm |
| --- | --- | --- |
| Messages per second | 5 messages/second | Applies to one account or system-wide? |
| Messages per minute | 300 messages/minute | Is bursting all 300 in the first second allowed? |
| Recipients per minute | 500 recipients/minute | How is an email with multiple To/Cc/Bcc counted? |
| Daily sending quota | 20,000 messages/day | Does the reset cycle follow UTC or provider time? |
| Max concurrent connections | 3 connections | Counted per IP, account, or SMTP credential? |
| Max message size | Per provider | Does the cap include MIME/Base64 and attachments? |
| Per-domain limit | e.g., for gmail.com | Are there separate domain/MX limits? |
| Per-tenant budget | e.g., per enterprise | How much capacity may each tenant consume? |
| Campaign cap | e.g., per campaign | May optional emails consume the entire quota? |

Numbers in the table are **illustrative examples**, not Spring defaults or a specific provider's limits. Obtain granted quotas from provider documentation, contracts, and current operational telemetry.

### Do Not Count Emails Alone

A single MIME message sent to 30 addresses may be counted by the provider as 30 recipients, even though the application only called `send()` once. Many providers cap recipients per message or per time window. Therefore separate:

- **Message budget:** number of submitted messages.
- **Recipient budget:** total recipients across To/Cc/Bcc.
- **Byte budget:** volume of MIME data or attachments.
- **Connection budget:** number of active SMTP sessions.

For personalized notifications, it is usually best to send separately per recipient to protect privacy and support per-recipient tracking. Never stuff hundreds of recipients into Bcc just to trick quotas; provider policies may still count every recipient.

### Internal Limits Must Leave a Safety Margin

If a provider allows a maximum rate, the application should usually start below it because of:

- Retries and emails originating from multiple services.
- Quotas shared with other systems.
- Network/relay instability.
- Peak-hour campaigns.
- Sender- or domain-specific policies.

Never treat one configuration value as permanently correct. Monitor responses, latency, and error rates to tune it.

## 4. Where to Place Limits in an Asynchronous Architecture?

A durable architecture typically includes producers, an outbox/queue, and workers:

~~~text
HTTP / business transaction
       |
       v
Save domain event + mail outbox
       |
       v
      COMMIT
       |
       v
Due-message scheduler
       |
       v
Claim work with lease
       |
       v
Render and validate content
       |
       v
Concurrency permit + rate permit
       |
       v
JavaMailSender.send(...)
       |
       v
Update SUBMITTED / RETRY_PENDING / FAILED
~~~

**The critical enforcement point is right before SMTP submission.** Do not rate-limit only the notification-creation API, because a day later a worker replay could push thousands of messages to SMTP without passing through that API. Nor should you limit only one executor in a single instance if the application runs across multiple replicas.

### Two Levels of Throttling

1. **Admission control:** limits how many requests may be created or sit in the queue, depending on notification type. Optional emails can be deferred, rejected, or suppressed when overloaded.
2. **Dispatch control:** limits how many messages are submitted to SMTP. Mandatory emails are stored durably and processed by priority when capacity is available.

Never silently delete or drop mandatory emails just because permits are currently unavailable. Keep them in `PENDING`/`RETRY_PENDING`, set a next attempt time, and alert if backlogs breach SLAs.

## 5. Common Rate Limiting Algorithms

### 5.1. Fixed Window Counter

Counts sends within a fixed interval, such as each minute:

~~~text
Window 10:00-10:01: 0 ... 300 messages
Window 10:01-10:02: counter reset
~~~

Pros: simple, easy to store in Redis or a database. Cons: bursts can happen at window boundaries, such as sending many messages at the end of one minute and immediately sending many more at the start of the next.

### 5.2. Sliding Window

Counts sends over a recent rolling window, such as 60 seconds backward from the current moment. It reduces boundary bursts, though requires storing timestamps or using approximation mechanisms. Fits when providers enforce sliding-window quotas.

### 5.3. Leaky Bucket

Places work into a queue drained at a steady rate. Useful when a smooth sending stream without large bursts is needed. However, the bucket/queue must have bounded capacity and an explicit full-queue policy.

### 5.4. Token Bucket

A bucket holds permits. Permits refill at a steady rate; each send consumes some number of permits. The bucket has a maximum capacity to bound bursts.

Example:

- Refill rate: 5 tokens/second.
- Capacity: 10 tokens.
- Each email consumes 1 token.

After an idle period, the application can send a burst of up to 10 messages; afterward it must wait for tokens to refill. If strict burst suppression is required, shrink capacity or combine with pacing/leaky bucket.

~~~mermaid
flowchart LR
    A["Pending email"] --> B{"Token available?"}
    B -- "Yes" --> C["Consume permit"]
    C --> D["SMTP send"]
    B -- "No" --> E["Keep pending / schedule later"]
    E --> B
~~~

Token buckets are popular because they support both an average rate and controlled bursts. However, understand which unit the provider limits: messages, recipients, connections, or bytes.

## 6. Simple Token Bucket Implementation in One JVM

The example below illustrates a limiter based on `System.nanoTime()`. This is an **in-memory single-process limiter** and does not cap the aggregate rate across multiple replicas.

~~~java
package com.example.mail;

public final class InMemoryTokenBucket {

    private final double capacity;
    private final double refillPerSecond;

    private double availableTokens;
    private long lastRefillNanos;

    public InMemoryTokenBucket(
            double capacity,
            double refillPerSecond) {

        if (capacity < 1 || refillPerSecond <= 0) {
            throw new IllegalArgumentException(
                    "Capacity and refill rate must be positive");
        }
        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
        this.availableTokens = capacity;
        this.lastRefillNanos = System.nanoTime();
    }

    public synchronized boolean tryAcquire(int permits) {
        if (permits <= 0 || permits > capacity) {
            throw new IllegalArgumentException(
                    "Invalid permit count");
        }

        long now = System.nanoTime();
        double elapsedSeconds =
                Math.max(0L, now - lastRefillNanos)
                        / 1_000_000_000.0;

        availableTokens = Math.min(
                capacity,
                availableTokens + elapsedSeconds * refillPerSecond);
        lastRefillNanos = now;

        if (availableTokens < permits) {
            return false;
        }

        availableTokens -= permits;
        return true;
    }
}
~~~

Characteristics of this example:

- `synchronized` prevents threads in the same JVM from concurrently consuming beyond available tokens.
- `System.nanoTime()` is a monotonic time source suited for measuring elapsed intervals in-process.
- Tokens refill at the configured rate without exceeding capacity.
- `tryAcquire` returns `false` immediately when tokens are lacking; it does not sleep the thread.
- A send targeting multiple recipients may require multiple permits per policy.

### Bean Configuration Example

~~~java
@Configuration
public class MailRateConfiguration {

    @Bean
    public InMemoryTokenBucket mailTokenBucket() {
        // Average max 4 messages/second, burst 8 messages.
        return new InMemoryTokenBucket(8, 4);
    }
}
~~~

This is not a standard SMTP limit; values must come from real quotas. If running three replicas, each using its own 4 tokens/second limiter can generate around 12 messages/second total. **When cluster-wide limits are required, use a distributed limiter or a centralized sending gateway.**

### When No Permits Are Available

Avoid:

~~~java
while (!bucket.tryAcquire(1)) {
    // Busy spin: burns CPU while waiting.
}
~~~

Nor should you dump thousands of tasks into an executor just to have them `Thread.sleep(...)` waiting for quota. Better practice is keeping jobs in the outbox/queue and scheduling the next dispatch time. When volume is low and latency permits, a scheduler can check permits periodically; at high volume, the limiter should return an approximate ready time so workers can schedule efficiently.

## 7. Limiting Concurrent Connections and In-Flight Sends

Even with a token bucket, you still need to prevent too many SMTP calls from running simultaneously. A simple approach within one JVM is `Semaphore`:

~~~java
import java.util.concurrent.Semaphore;

public final class SmtpConcurrencyGate {

    private final Semaphore slots;

    public SmtpConcurrencyGate(int maxConcurrentSends) {
        if (maxConcurrentSends < 1) {
            throw new IllegalArgumentException(
                    "maxConcurrentSends must be positive");
        }
        this.slots = new Semaphore(maxConcurrentSends);
    }

    public boolean tryEnter() {
        return slots.tryAcquire();
    }

    public void leave() {
        slots.release();
    }
}
~~~

With this code, only invocations where `tryEnter()` returned `true` may call `leave()`. Never call `leave()` without having acquired a permit, or you will inflate phantom slots.

### Combining Rate and Concurrency

~~~java
public DispatchResult trySubmit(PreparedMail prepared) {
    if (!smtpGate.tryEnter()) {
        return DispatchResult.DEFERRED_CONCURRENCY;
    }

    try {
        if (!tokenBucket.tryAcquire(1)) {
            return DispatchResult.DEFERRED_RATE;
        }

        mailSender.send(prepared.message());
        return DispatchResult.SUBMITTED;
    } finally {
        smtpGate.leave();
    }
}
~~~

`PreparedMail` and `DispatchResult` are application-defined types. This method acquires a concurrency slot first, then acquires a rate token and submits; if no token is available, it returns a deferred result so the worker keeps the job waiting rather than marking `FAILED`. If SMTP throws an exception, the calling layer must classify it and update outbox status.

Consumed tokens are normally not refunded after an SMTP attempt, because the provider may have received part or all of the request and quotas typically count attempts. This is a policy choice: if certain SMTP was never called, the application may have a permit-refund rule; never arbitrarily refund after an ambiguous outcome.

### Concurrency Limit Is Not a Connection Pool

A limit of 3 concurrent sends does not mean the application always keeps 3 open SMTP connections. Reusing or opening connections depends on the transport/Jakarta Mail and implementation. If using session/connection pooling, still cap active connections to provider quotas.

## 8. Bounded Executor When Using @Async

A common mistake is using `@Async` to “send fast” without bounding how many tasks enter the executor:

~~~java
@Async
public void sendEmail(MimeMessage message) {
    mailSender.send(message);
}
~~~

If thousands of requests call the method concurrently, tasks can pile up in the executor or run in parallel beyond SMTP capacity. `@Async` does not automatically enforce emails/second quotas and does not turn work into a durable queue.

### Configuring a Bounded ThreadPoolTaskExecutor

~~~java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mail-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}
~~~

Usage:

~~~java
@Async("mailExecutor")
public CompletableFuture<Void> sendInBackground(
        PreparedMail message) {
    mailDispatcher.submit(message);
    return CompletableFuture.completedFuture(null);
}
~~~

These limits are illustrative only. When the queue is full and no more workers can be created, `AbortPolicy` rejects tasks rather than building an unbounded backlog on the heap. Callers must catch/record rejections and retain the pending record in the outbox. Never silently drop mandatory emails.

### Notes on Executors

- `corePoolSize` is the core thread count.
- `maxPoolSize` is the maximum thread count.
- `queueCapacity` is the number of tasks allowed to wait.
- When the queue is full and threads hit the limit, the rejection policy determines how to react.
- `@Async` via Spring proxies does not work automatically when a method is called directly from another method in the same bean (self-invocation).
- Tasks in an in-memory executor can be lost if the process stops; it does not replace a durable outbox/queue.
- With `void @Async`, exceptions do not return to the HTTP caller; separate error handling and status recording are required.

`CallerRunsPolicy` can apply backpressure by running tasks on the caller's thread, yet for emails triggered from HTTP requests it can unexpectedly force requests to wait on SMTP. Pick the rejection policy by context rather than treating `CallerRunsPolicy` as a universal fix.

## 9. Do Not Let Queues Grow Unboundedly

Rate limiting can make sending slower than notification creation. If producers keep generating more work than workers can process, the backlog grows. Therefore, **bounded queues and admission policies** are required.

### Prioritizing Work Under Overload

| Email Type | When Backlog Is High |
| --- | --- |
| OTP, authentication | Prioritize fast processing, rate-limit requests, and alert on SLA breaches |
| Receipts, order confirmations | Persist durably, retry, and monitor backlog age |
| Essential status updates | Persist durably, can batch-dispatch by priority |
| Newsletters | Defer, verify consent and expiration |
| Promotions | Can suppress/cancel if campaign expired or overloaded |
| Non-urgent periodic reports | Can consolidate, reduce frequency, or schedule off-peak |

**Do not prioritize marketing emails ahead of OTPs simply because marketing entered the queue first.** A single FIFO queue can suffer head-of-line blocking: thousands of optional emails at the front of the queue delay later security emails.

### In-Memory Queues vs. Durable Outboxes

A queue in `ThreadPoolTaskExecutor` caps waiting tasks in a single process. It is insufficient to guarantee send requests survive restarts. A durable outbox or broker persists requests; workers pull only an amount of work matching permits and concurrency.

Separate:

- **Persistent backlog:** outbox, broker, or job store.
- **In-flight batch:** jobs claimed with a lease.
- **Executor queue:** tasks waiting in-process.
- **SMTP connection capacity:** active connections/sends.

If no tokens are available, workers should not claim thousands more records and hold them in `PROCESSING`. Doing so causes leases to expire, triggers re-claiming, and harms observability.

## 10. Backpressure from Dispatcher to Producer

Backpressure is the ability to react when downstream lacks sufficient capacity. It does not mean returning HTTP 500 for every request on error.

### On the Producer Side

- Cap optional notifications created per user/tenant/campaign.
- Rate-limit APIs that can spawn emails, such as OTP request endpoints.
- Cancel or coalesce duplicate/non-essential notifications.
- When queues reach thresholds, defer large campaigns.
- Never drop mandatory transactional requests without an alternative business plan.

### On the Worker Side

- Claim only as many records as available slots and permits allow.
- Pause claiming when limiters run out of quota.
- Lower concurrency when SMTP timeouts or throttling increase.
- Pause workers or open a circuit breaker during widespread provider outages.
- Reschedule instead of sleeping inside transactions.

### Why Not Drain the Queue by Adding Threads?

If the downstream SMTP relay is the bottleneck, adding threads only increases waiting calls, open connections, and timeout rates. Once the provider enforces quotas, adding threads does not increase quota. Adjust **the rate at which work enters the relay**, not just the application's CPU consumption capacity.

## 11. Prioritizing Critical Emails and Fairness Across Sources

Systems often send several email categories:

- Security/OTP.
- Transactional.
- Product notifications.
- Marketing/campaigns.

Sharing one bucket and queue lets a marketing campaign drain all permits right before an OTP arrives. A solid design can:

1. Enforce an unbreakable **global provider limit**.
2. Partition budgets by priority group.
3. Reserve a portion of capacity for security/transactional traffic.
4. Set per-tenant/campaign limits.
5. Enforce fairness so one tenant cannot consume the entire quota.

~~~text
                   GLOBAL SMTP BUDGET
                           |
          +----------------+----------------+
          |                |                |
      Security         Transactional     Optional
       priority          priority          budget
          |                |                |
      User limits       Tenant limits   Campaign limits
          +----------------+----------------+
                           |
                        SMTP relay
~~~

This partitioning must keep the sum within the global limit. Do not create four independent limiters whose combined quota exceeds what the provider allows.

### Reserved Capacity and Starvation

Reserving capacity for OTPs avoids delaying security alerts. However, absolute priority all the time can starve normal emails when security traffic stays high. Use weighted fair scheduling, per-group min/max bounds, or quota-borrowing rules when high-priority groups are idle.

Exact rules depend on SLAs. If an OTP expires in a few minutes, its acceptable latency must be much lower than a newsletter's. If a campaign has expired, stop sending instead of spending quota on stale backlogs.

## 12. Limiting by Provider, Domain, and Tenant

An application may use multiple SMTP providers or accounts. Conversely, multiple services may share one SMTP account. Therefore, identify **the right rate-limit keys**.

| Key | Conceptual Example | Reason |
| --- | --- | --- |
| Provider/account | `smtp-account:transactional` | Stay within credential quota |
| Sender/domain | `sender:mail.example.com` | Comply with sender policies |
| Recipient domain | `recipient-domain:example.net` | Reduce bursts to receiving domains |
| Tenant | `tenant:tenant-42` | Prevent one tenant from monopolizing capacity |
| Campaign | `campaign:campaign-184` | Throttle optional blasts |
| Notification category | `category:security` | Prioritize essential emails |

A single message may need permits at **multiple tiers**: global provider, tenant, category, and recipient domain. Submission occurs only when all checks pass.

### Do Not Non-Atomically Acquire Multiple Tokens and Abandon Them

Suppose the application consumes a global token but fails to acquire a domain token. Retrying repeatedly can drain the global bucket without sending any messages. A multi-quota implementation needs to:

- Check budgets in order or via an atomic transaction in the same limiter store.
- Have a permit release/refund policy if certain SMTP was never called.
- Avoid deadlocks when concurrently acquiring permits across multiple keys.
- Set wait times and reschedule when any tier lacks capacity.
- Separate **rate quotas** from **concurrency slots** if their release semantics differ.

In distributed systems, a centralized admission/limiter service or a library supporting atomic multi-key operations is usually preferable. Do not assume calling several independent limiters always yields accurate budgets.

### Recipient Domain Does Not Equal Destination SMTP Server

An address `customer@example.net` has domain `example.net`, yet mail may actually route to an MX hosted by another provider. Recipient-domain rate limiting is a useful application-level grouping, not an exact model of connections to every receiving server.

When grouping, use domains from parsed/validated addresses rather than splitting untrusted strings arbitrarily. Pay attention to internationalized addresses, case sensitivity, and system-wide normalization rules.

## 13. Rate Limiting in Multi-Replica Applications

An in-JVM limiter **does not enforce cluster-wide limits**. Suppose an application runs 5 pods, each allowing 10 messages/second. Total throughput can reach around 50 messages/second, exceeding a provider limit of 10 messages/second.

### Common Organizational Patterns

| Approach | Pros | Limitations |
| --- | --- | --- |
| Single centralized mail dispatcher | Easy to enforce global rate and concurrency limits | Needs high availability and avoiding single point of failure |
| Redis-backed rate limiter | Replicas consume from a shared budget | Needs atomic operations, Redis outage handling, and adds latency |
| Broker with bounded consumers | Easy to control consumer count, prefetch, and pacing | Consumer count alone does not guarantee message rate |
| Database-based limiter | Reuses existing DB infrastructure | Prone to contention and latency under high traffic |
| Email provider API with quota enforcement | Provider blocks when threshold exceeded | App must still avoid flooding with rejected requests |

With Redis, a fixed-window counter can use atomic commands or a Lua script; distributed token buckets must update tokens and timestamps **atomically**. Reading values, computing in the JVM, and writing back with multiple unlocked commands introduces race conditions.

### Example Lua Fixed-Window Limiter for One Key

~~~lua
-- KEYS[1]: rate-limit key
-- ARGV[1]: maximum count within the window
-- ARGV[2]: window duration in milliseconds
local limit = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])
local current = tonumber(redis.call('GET', KEYS[1]) or '0')

if current >= limit then
    return 0
end

current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('PEXPIRE', KEYS[1], windowMs)
end
return 1
~~~

This script illustrates an atomic fixed-window limiter for one key, not a complete production solution. You must handle argument validation, TTLs, key namespacing, daily quotas, access control, and Redis unavailability. Fixed windows still permit boundary bursts; if providers enforce sliding windows or strict burst caps, choose a more suitable algorithm.

### What If the Limiter Store Fails?

If Redis or the limiter service is unavailable, letting every worker send without limits can instantly overload SMTP. A safe policy is typically:

- **Do not exceed quotas when throttling state is unavailable.**
- Pause or defer dispatching while keeping mandatory emails in the outbox.
- Emit infrastructure errors and alerts.
- Use a very low fallback rate only if the design proves it cannot breach total quota during failures.

Do not confuse *failing closed on immediate sending* with *deleting send requests*. Emails can still wait to recover.

## 14. SMTP Throttling and Transient Error Responses

Rate limits should proactively prevent overload, yet the system must still handle responses from the SMTP server. Common responses:

| SMTP Code | Typical Meaning | Handling Approach |
| --- | --- | --- |
| `421` | Service temporarily unavailable / closing channel | Slow down, close connection, retry with backoff |
| `450` | Mailbox temporarily unavailable | Retry per policy, not necessarily a quota issue |
| `451` | Local error in processing | Retry with backoff and monitor |
| `452` | Insufficient system storage/resources | Avoid piling on load, retry later |
| `4.7.x` enhanced status | Often policy, security, or throttling depending on provider | Inspect provider response/documentation |
| `5xx` | Permanent error for the current request | Do not retry blindly; address root cause |

**Not every SMTP 4xx is a rate-limit error.** For instance, a temporarily unavailable mailbox differs from provider throttling. Store SMTP codes and enhanced status codes when available; combine them with provider docs to decide whether to lower throughput, retry, or handle a specific recipient.

### SMTP Differs from HTTP 429

With HTTP email APIs, servers can return `429 Too Many Requests` with `Retry-After`. SMTP has no standard HTTP `Retry-After` header in send responses. An SMTP provider may put recommended retry timings in response text or custom docs; follow the provider's conventions rather than assuming a standard retry header exists.

### Avoiding Retry Storms

If many workers hit throttling simultaneously and all retry after exactly 60 seconds, the system can trigger a new burst. Use:

- Exponential backoff and jitter.
- Lowering global rate when widespread throttling is detected.
- Capping pending retries and open connections.
- Preventing retries from consuming the entire budget for urgent new emails.
- Cluster-wide rate control.

## 15. Retries Must Also Pass Through the Rate Limiter

A common bug is rate-limiting only new emails while retries run through a separate worker without a limiter. When SMTP recovers, old retries can stampede and immediately overload the server again.

**Every path to SMTP must go through the same dispatch policy:** new emails, automatic retries, manual replays, resends, and batch campaigns.

~~~mermaid
flowchart TD
    A["New outbox records"] --> D["Shared dispatch gate"]
    B["Scheduled retries"] --> D
    C["Manual replay / resend"] --> D
    D --> E["Global + tenant + domain budget"]
    E --> F["Concurrency gate"]
    F --> G["JavaMailSender"]
~~~

If the application uses multiple providers, maintain per-provider budgets and a coordinator routing by policy. Avoid dumping the entire backlog onto a fallback provider in an uncontrolled surge.

### Transient Retries vs. Permanent Replays

- Transient errors: schedule `nextAttemptAt` and retry automatically.
- Permanent recipient or configuration errors: stop, record `FAILED`/`DEAD_LETTER`, and wait for root cause resolution.
- Ambiguous SMTP outcome: carries duplicate risk; reconcile before retrying per policy.
- Already `SUBMITTED` emails: do not auto-resend since `send()` does not mean delivered.

Rate limiters regulate speed, yet do not replace idempotency logic, outbox states, or error classification.

## 16. Designing the Worker from Outbox to SMTP

A mail worker should not claim thousands of records and queue them into an in-memory executor. It should claim a small batch matching actual capacity and defer records that cannot yet be sent.

### Usable Statuses

| Status | Meaning |
| --- | --- |
| `PENDING` | Persisted, waiting to be sent |
| `PROCESSING` | Claimed by a worker with a lease |
| `DEFERRED_RATE` | Paused because quota is unavailable |
| `DEFERRED_CAPACITY` | Paused because concurrency slots are full |
| `RETRY_PENDING` | Transient SMTP error, retry scheduled |
| `SUBMITTED` | SMTP relay accepted per application-observed response |
| `SUBMISSION_UNKNOWN` | Uncertain whether relay received the message |
| `FAILED_PERMANENT` | Error that should not be retried blindly |
| `SUPPRESSED / EXPIRED` | Not sent per consent or expiration policy |

`DEFERRED_RATE`/`DEFERRED_CAPACITY` can be distinct statuses or simply `PENDING` with a next attempt timestamp, depending on the model. **Do not increment failure attempts when only lacking tokens without having called SMTP**, if attempts represent actual send tries.

### Dispatcher Pseudocode

~~~text
dispatchDueMessages():
    if globalGate.isUnavailable():
        record operational alert
        return

    budget = estimateCapacityForSmallBatch()
    if budget <= 0:
        return

    jobs = outbox.claimDueWithLease(budget)
    for job in jobs:
        if job.expired or job.suppressed:
            update terminal state
            continue

        try:
            mime = renderAndValidate(job)
        catch permanentContentError:
            mark FAILED_PERMANENT
            continue

        if not concurrencyGate.tryEnter():
            releaseClaimAndDefer(job)
            continue

        try:
            if not rateGate.tryAcquire(job.recipientCount):
                releaseClaimAndDefer(job)
                continue

            try:
                smtp.send(mime)
                mark SUBMITTED
            catch temporarySmtpError:
                scheduleRetryWithBackoff(job)
            catch permanentSmtpError:
                mark FAILED_PERMANENT
            catch uncertainSmtpOutcome:
                mark SUBMISSION_UNKNOWN
        finally:
            concurrencyGate.leave()
~~~

This pseudocode clearly separates missing permits from SMTP errors. In a real application, claiming and state updates must run in short transactions while SMTP sending runs outside transactions. Every completion must update by matching record ID and lease owner so an old worker cannot overwrite a newer worker's state after lease expiration.

### Bounding Claim Batches

If a worker supports at most 4 concurrent sends, it should not claim 5,000 records without lease renewal or appropriate work streaming. You can:

- Claim at most free slots plus a small buffer.
- Check limiter budgets before claiming, while still confirming tokens atomically right before sending.
- When tokens are unavailable, return the record to `PENDING` with `nextAttemptAt` to avoid hot polling.
- Keep leases long enough for expected send duration and support renewal when needed.

Never wrap an entire email send inside one `@Transactional` method. External mail servers do not participate in ACID database transactions; holding locks during network waits wastes resources and still cannot guarantee exactly-once delivery.

## 17. Adaptive Throttling When the Mail Server Slows Down

Static limits are a starting point, yet relay capacity can fluctuate. When provider queues grow or throttling error rates spike, reduce send rate. Once stable over time, gradually increase again within granted limits.

An **AIMD (Additive Increase, Multiplicative Decrease)** style idea:

~~~text
If throttling is detected with high confidence:
    newRate = max(minRate, currentRate * 0.5)

If stable across multiple monitoring windows:
    newRate = min(configuredMaxRate, currentRate + smallStep)
~~~

These factors are illustrative only, not fixed recommendations. Ensure:

- Never exceed confirmed provider quotas.
- Use long enough observation windows to avoid rapid oscillation.
- Distinguish throttling errors from recipient-specific errors.
- Require thresholds and stabilization periods before ramping back up.
- Track per provider/account and relevant recipient groups.
- Never scale up indefinitely merely because errors are temporarily absent.

### Useful Signals

| Signal | What It May Suggest |
| --- | --- |
| Rising throttling-related SMTP 421/4.7.x | Provider is asking you to back off |
| Rising submission latency | Relay or network showing slowdown |
| Rising connection timeouts | Network/capacity issue |
| Falling remaining quota | Approaching limit |
| Rising relay spool/queue | Downstream delivery cannot keep up |
| Rising outbox backlog age | Dispatch capacity lagging behind producers |
| Rising bounce/spam complaint rate | Traffic quality issue; review sending policies |

Never infer rate limiting from a single metric alone. For example, SMTP 450 may relate to one mailbox rather than the whole provider. Lowering global rates because of one recipient's error would needlessly slow unrelated emails.

### Warm-Up and Sender Reputation

When a new account/domain/IP begins sending, jumping suddenly from a handful of emails to hundreds of thousands can hurt deliverability. Many systems use warm-up: ramping up gradually while watching delivery quality, bounces, complaints, and provider feedback. This is a **sender reputation** issue alongside technical server capacity, and cannot be solved simply by adding threads.

## 18. Daily Quotas, Windows, and Reserves for Essential Emails

Providers may enforce daily quotas in addition to per-second/per-minute caps. A messages/second token bucket cannot prevent exceeding a daily message total.

### Multi-Tier Management

~~~text
1. Daily remaining budget?
2. Hourly/minute budget?
3. Per-domain or per-tenant budget?
4. Burst/token budget?
5. SMTP concurrency slot?
6. Submit message
~~~

Units must stay consistent. If daily quotas count recipients, do not use message counts as a proxy. If the provider shares quotas across multiple accounts or services, aggregate the corresponding telemetry.

### Reset Windows

A “per day” limit may reset at UTC midnight, the account's timezone, or on a rolling 24-hour window. Never assume resets happen at 00:00 in the application's local time. When implementing daily Redis keys, match the provider's exact window definition or use a more conservative bound.

### Capacity Reserves

If the system sends both transactional and marketing emails, reserve a portion of daily quota for transactional traffic. When nearing exhaustion:

- Stop creating new marketing campaigns.
- Pause newsletters.
- Preserve remaining budget for OTPs and essential transactional emails.
- Alert to raise provider quotas or adjust capacity.

Do not treat reserved capacity as permission to exceed the global cap. Total messages/recipients must still stay within quota.

## 19. Size and Total Byte Limits When Sending

A message with large attachments consumes far more bandwidth and SMTP time than a plain text email. If a rate limiter charges one token per message regardless of size, the system can still put heavy pressure on network and storage.

For flows with attachments, consider:

- Maximum size per attachment.
- Maximum total MIME message size.
- Maximum attachment count.
- Total bytes sent over a time window if required by the provider.
- Lower concurrency for large messages.
- Separating large report batches from small transactional emails.

When MIME encodes binary attachments in Base64, transfer size typically grows by roughly one-third, plus headers, boundaries, and line wrapping. Leave headroom below the provider's message size limit.

### Weighted Permits

A policy can compute permits from recipient count or size:

~~~java
int messagePermits = 1;
int recipientPermits = message.recipientCount();
long byteBudget = estimatedEncodedSize(message);
~~~

These values belong to **separate budgets** and do not necessarily sum into a single token count. If the provider meters messages and recipients independently, apply a corresponding limiter per quota type. When exact size is unknown prior to serialization, use a conservative estimate and verify before submission.

## 20. Circuit Breakers When SMTP Becomes Unavailable

If the SMTP provider suffers a widespread outage, continuing to call `send()` at full speed only produces timeouts and wastes workers. A circuit breaker can open when reliable error signals exceed a threshold, pausing new requests before allowing controlled probes.

~~~text
CLOSED: submit normally within quota
   |
   | widespread errors exceed threshold
   v
OPEN: do not call SMTP; retain outbox and defer
   |
   | after cooldown interval
   v
HALF_OPEN: a few probe requests
   |
   +-- steady success --> CLOSED
   |
   +-- continued errors -> OPEN
~~~

Circuit breakers do not replace rate limiters. Once the breaker closes again, the backlog may be huge; the rate limiter must still throttle drain speed so it does not trigger another flood.

### Distinguishing Outages from Recipient Errors

Do not open a provider-wide circuit breaker over one recipient returning 550. Use connection failures, widespread service errors, provider throttling, and matching signals. A bad recipient must be handled at the notification level without halting all emails.

### Behavior While the Breaker Is Open

- Mandatory emails: keep in outbox, update retry schedules, and alert.
- Optional emails: defer, expire, or suppress per policy.
- HTTP requests: if the feature genuinely needs immediate SMTP, return an appropriate notice; otherwise confirm the job was queued.

Never accumulate unbounded in-memory tasks just waiting for the breaker to close.

## 21. Monitoring Capacity and Backlogs

Without observability, rate limiters are easily misconfigured too low or too high without anyone noticing. Monitor **production rate**, **send rate**, **wait time**, and **provider health**.

| Metric | Meaning |
| --- | --- |
| `mail_outbox_pending` | Number of messages waiting to be sent |
| `mail_outbox_oldest_age_seconds` | Age of the oldest waiting message |
| `mail_dispatch_attempts_total` | Submission attempt count |
| `mail_submitted_total` | Count accepted by SMTP per response |
| `mail_rate_limited_total` | Count deferred due to missing quota before send |
| `mail_concurrency_deferred_total` | Count deferred due to exhausted slots |
| `mail_smtp_temp_failures_total` | Retryable SMTP failures |
| `mail_smtp_perm_failures_total` | Permanent SMTP failures |
| `mail_smtp_latency_seconds` | Submission latency |
| `mail_inflight_sends` | Active in-flight send calls |
| `mail_retry_pending` | Records waiting for retry |
| `mail_dead_letter_total` | Records moved to dead-letter state |
| `mail_rate_configured` | Current configured rate per provider/category |

Metric names are examples only; implement using Micrometer/Actuator or existing telemetry. Keep metric labels low-cardinality such as provider ID, category, and error group.

### Never Put Recipient Data in Metric Labels

Do not use full recipient email addresses, notification UUIDs, or subjects as time-series labels. Those create extreme cardinality and risk leaking personal data. Use correlation-ID logs or access-controlled tracing systems to inspect individual cases.

### Useful Alerts

- Transactional backlog age exceeding SLA.
- Unusually high rate-limited counts.
- SMTP temporary failures exceeding threshold.
- Daily quota nearing exhaustion.
- Circuit breaker stuck in `OPEN` state.
- Rapidly growing dead-letter count.
- In-memory queue hitting capacity.
- OTP latency exceeding acceptable threshold.

Alerts should account for email type. A marketing backlog of a few hours may be acceptable, whereas an OTP delayed by minutes may already be useless.

## 22. Testing Limiters and Asynchronous Throttling

Tests must prove limits actually take effect, not merely that `JavaMailSender` gets called when a job exists.

### Testing the Token Bucket in One JVM

With a bucket that does not refill noticeably during the test:

~~~java
@Test
void rejectsWhenBurstCapacityIsConsumed() {
    InMemoryTokenBucket bucket =
            new InMemoryTokenBucket(2, 0.0001);

    assertTrue(bucket.tryAcquire(1));
    assertTrue(bucket.tryAcquire(1));
    assertFalse(bucket.tryAcquire(1));
}
~~~

In production tests, inject a fake clock/ticker to test refills and time boundaries deterministically rather than relying on `Thread.sleep(...)` or CI runner speed. The test above only illustrates one burst-capacity case.

### Testing Concurrency with Synchronization Primitives

Use `CountDownLatch` and a mock sender to hold multiple tasks at the send point, then verify no more than N tasks ever run simultaneously. Tests should also cover exception branches to confirm slots are `release()`d in `finally`.

### Multi-Replica Testing

In-memory limiters are insufficient for cluster-wide caps. Write integration tests against Redis or the real limiter store:

1. Run multiple workers concurrently acquiring permits.
2. Verify total granted permits never exceed the window quota.
3. Test a worker crashing mid-processing.
4. Verify quota resets/TTLs match the algorithm.
5. Test behavior when the limiter store is unavailable.

### Testing Full Queues

With a bounded executor, submit more tasks than total thread/queue capacity and verify rejections are recorded. Mandatory emails must remain in the outbox, never lost. If using a broker, verify prefetch, consumer concurrency, redelivery, and retry behavior.

### Testing SMTP Throttling

Mock the transport or use an SMTP test server capable of returning temporary responses like `421` or `451`. Verify:

- Messages are not marked `SUBMITTED`.
- Retries are scheduled with backoff.
- Rate can be throttled down per policy on widespread throttling.
- No simultaneous replay storm after recovery.
- Permanent errors are not retried endlessly.

### Testing Priority

Create a large marketing backlog, then submit an OTP and verify the OTP still dispatches within SLA thanks to reserved capacity/priority policies. Also test fairness so one tenant cannot consume the entire budget of other tenants.

## 23. Practical Implementation Process

A team can start simple and expand as traffic grows:

1. **Inventory email sources**: OTP, transactional, product notifications, marketing, replays.
2. **Confirm provider quotas**: messages, recipients, connections, daily limits, and message sizes.
3. **Define SLOs/SLAs**: maximum wait times per category.
4. **Build a durable outbox or queue** so you do not rely on an in-memory executor.
5. **Establish a single shared dispatch gate** that all SMTP sends pass through.
6. **Apply rate limiting** and **in-flight concurrency limits**.
7. **Partition budgets by category/tenant** within global quotas.
8. **Bound claim batches and executor queues**; never pull unbounded tasks into RAM.
9. **Classify SMTP errors and retry with backoff**; route permanent errors to separate handling.
10. **Throttle down when providers throttle**, with outage/circuit-breaker policies.
11. **Add metrics, logs, and alerts** for queue age, rates, errors, and remaining quota.
12. **Load-test with ramping traffic**, supporting runtime tuning without redeploying if the system permits.

### Incident Decision Table

| Symptom | Recommended Action |
| --- | --- |
| SMTP returns 421/4.7.x throttling | Lower throughput, increase backoff, and review provider quotas |
| Many connection timeouts | Reduce concurrency, inspect network/relay |
| Outbox growing continuously | Compare inflow vs. outflow, throttle optional producers, raise valid quotas, or scale the real bottleneck |
| Executor queue full | Keep jobs in outbox, reduce claim batch size, handle rejections explicitly |
| Marketing delays OTPs | Enforce priority/reserved budgets; prevent one FIFO queue from monopolizing |
| Huge backlog after outage | Drain with rate limiting; never replay everything at once |
| Many emails to same recipient | Deduplicate/coalesce notifications where business logic allows |
| Daily quota nearly exhausted | Halt optional campaigns, preserve budget for essential notices |
| Limiter store loses connection | Do not bypass quotas globally; defer and alert |
| Send succeeds yet mailboxes are slow | Check relay queues, provider events, and receiving systems; `send()` does not prove delivery |

## 24. Common Mistakes

### 24.1. Thinking @Async Automatically Rate-Limits

`@Async` only moves execution to an executor. If many tasks run concurrently, send rates can still breach quotas. Combine a rate limiter, concurrency gate, and bounded executor queue.

### 24.2. Limiting Only Thread Count

Fewer threads do not mean fewer emails per minute. Set budgets in the provider's exact units.

### 24.3. Separate In-Memory Limiter per Pod

Total rate multiplies by replica count. Use a distributed limiter or centralized dispatcher.

### 24.4. Allowing Overly Large Token Bucket Bursts

Excessive bucket capacity lets hundreds of SMTP calls fire in a brief span. Shrink burst capacity or apply pacing when providers disallow bursts.

### 24.5. Retries Bypassing the Limiter

After an outage, retries can flood SMTP. All sending paths must share the same dispatch gate.

### 24.6. Sleeping Thousands of Threads Waiting for Quota

Threads remain occupied doing nothing and executor heaps fill up. Reschedule in the outbox or let the broker hold the work.

### 24.7. Claiming Too Many Records

Workers lacking permits hold many `PROCESSING` leases. Claim only small batches matched to available capacity.

### 24.8. Deleting Mandatory Emails When Queues Fill

That loses business messages. Retain requests in a durable outbox, alert, and fix capacity.

### 24.9. Failing to Prioritize Transactional Emails

Marketing consumes all quota, delaying OTPs and receipts. Apply category budgets and fairness.

### 24.10. Treating Every 4xx as Throttling

Some 4xx errors stem from recipient or infrastructure issues. Classify by code, enhanced status, and provider docs.

### 24.11. Applying HTTP Retry-After Logic to SMTP

SMTP has no standard HTTP `Retry-After` header. Follow retry guidance only as explicitly documented by the provider.

### 24.12. Replaying Unboundedly After Closing a Circuit Breaker

Once the relay recovers, the backlog can be huge. Keep the rate limiter active and ramp back up gradually.

### 24.13. Not Measuring Backlog Age

Counting waiting messages alone can hide transactional emails stuck past SLA. Monitor oldest age per category.

### 24.14. Using Message Limits When the Provider Meters Recipients

One multi-recipient message can consume many quota units. Count according to granted policies.

### 24.15. Equating Send Success with Delivery

`JavaMailSender.send()` usually only indicates SMTP submission succeeded. Inbox delivery and visibility require additional signals from providers/bounces.

## 25. Self-Check Questions

**1. Why is sending emails with @Async insufficient to protect the mail server?**

Because `@Async` only hands work to an executor. It does not automatically cap messages/second, recipients/minute, or total SMTP connections.

**2. How does rate limiting differ from concurrency limiting?**

Rate limiting caps sends over time; concurrency limiting caps active concurrent send calls. Both usually must be combined.

**3. How does a token bucket allow bursts?**

Permits refill steadily and accumulate up to capacity. When full, the application can send a matching burst before waiting for refills.

**4. Does an in-memory limiter protect a multi-replica cluster?**

No. Each JVM has its own bucket so total rate scales with replica count. A shared limiter or centralized dispatcher is needed.

**5. What should be done if tokens are exhausted for a mandatory email?**

Keep the request in a durable outbox, reschedule it, and monitor SLA; never silently delete the email.

**6. Why avoid Thread.sleep() across thousands of send tasks?**

It ties up threads idle, increases queue/memory pressure, and complicates recovery across restarts. Use `nextAttemptAt` or a scheduler.

**7. Is SMTP 421 always caused by rate limiting?**

No. It indicates service temporarily unavailable/closing channel; inspect context and provider responses.

**8. Can failed email replays bypass the rate limiter?**

No. Replays generate SMTP sends and must share the same budget as new emails.

**9. Why must recipient counts be limited?**

Because providers may meter quotas by recipient rather than by message alone. Multiple recipients on one email can consume multiple quota units.

**10. What problem does backpressure solve?**

It slows down, defers, or rejects non-essential work from producers/dispatchers when downstream lacks capacity, preventing unbounded backlog growth.

**11. Is a rate limiter still needed after a circuit breaker closes again?**

Yes. Post-outage backlogs can be huge; replaying at full speed could overload the provider all over again.

**12. Why monitor pending record age instead of count alone?**

Because even a small queue can hold OTP or transactional emails stuck beyond SLA.

**13. Should all workers send freely if the rate limiter store goes down?**

No. Defer, alert, and keep the outbox, or use a fallback proven incapable of exceeding quotas.

**14. Do daily quotas and per-second quotas substitute for one another?**

No. You must simultaneously satisfy every window and quota unit enforced by the provider.

## Conclusion

**Rate limiting asynchronous email sending protects the entire delivery pipeline, not merely reducing thread counts in the application.** Identify quotas across messages, recipients, sizes, and connections; apply rate limiters alongside concurrency gates right before `JavaMailSender.send(...)`; persist backlogs in a durable outbox/queue; and claim work only according to real capacity. In multi-replica deployments, use a shared budget so aggregate speed does not breach provider limits. Retries, manual replays, and resends must pass through the same limiter, paired with backoff and context-aware SMTP 4xx/5xx classification. When servers face overload, apply backpressure, prioritize essential emails, monitor backlog age, and throttle throughput cleanly. **The ultimate goal is keeping the mail server stable, preventing unbounded queue growth, and delivering critical emails per policy without losing messages.**
