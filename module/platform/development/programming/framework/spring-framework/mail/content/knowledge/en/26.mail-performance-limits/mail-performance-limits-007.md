# Provider-Aware Rate Limiting

## 1. Why Must an Email-Sending Application Follow Provider Speed Limits?

In **Spring Framework Mail**, applications typically call `JavaMailSender.send(...)` to submit emails to an SMTP server. Java code can generate thousands of send requests in just a few seconds, yet an **email provider's** capacity is not infinite: each account, domain, sender address, IP, service tier, or API key may be limited in message count, recipient count, concurrent connections, and submission rate.

For example, an e-commerce system runs an order-update campaign for 60,000 recipients while also sending OTP emails. If workers immediately open many SMTP connections to process everything at once:

- The SMTP provider may return temporary errors due to quota breaches or throttling.
- Retried tasks pile up, filling queues and tying up threads.
- Critical OTP emails are delayed because they share capacity with less urgent notifications.
- Sender reputation can degrade when the system produces abnormal traffic spikes.
- A single tenant or campaign can exhaust the entire organization's shared quota.
- Without careful SMTP outcome management, retries can cause duplicate or lost emails.

**Provider-aware rate limiting** is the mechanism of pacing outbound mail submitted to each provider within its actual limits, rather than waiting for the server to reject requests first.

~~~text
Email sources
  order / security / campaign / batch
                  |
                  v
        Mail outbox / queue
                  |
                  v
       Provider-aware dispatcher
                  |
         +--------+--------+
         |                 |
         v                 v
  Policy Provider A   Policy Provider B
    rate + quota        rate + quota
    concurrency         concurrency
         |                 |
         v                 v
    SMTP/API A          SMTP/API B
~~~

The goal is not merely avoiding `421` or `429` errors. A sound system also knows **when sending can resume**, **how many jobs are waiting**, **how to prioritize critical email types**, **how to distribute quotas across replicas/tenants**, and **what happens if a provider becomes temporarily unavailable**.

## 2. Distinguishing Rate Limits, Concurrency Limits, and Quotas

Three concepts are frequently confused:

| Limit Type | Question Answered | Illustrative Example |
|---|---|---|
| **Rate limit** | At most how many events per time window? | 10 messages/second |
| **Concurrency limit** | At most how many operations running simultaneously? | 5 active SMTP submissions |
| **Quota/budget** | Total consumption allowed in a cycle? | 20,000 recipients/day |
| **Connection limit** | How many concurrent SMTP connections opened? | 4 connections/account |
| **Per-message limit** | How many RCPTs or bytes in one message? | 50 recipients/message, separate size limit |
| **Reputation/policy throttle** | Slower allowed rate based on trust or prior errors? | Provider temporarily throttles after high bounce spikes |

**Numbers in this table are hypothetical to explain algorithms**, not quotas of Gmail, Microsoft 365, Amazon SES, or any specific service.

A provider may simultaneously enforce:

~~~text
Per SMTP credential:
  <= 8 messages/second

Per provider account:
  <= 30,000 recipients/24h

Per sender identity:
  <= 3 concurrent submissions

Per message:
  <= 100 recipients

Per SMTP connection:
  provider-specific lifecycle/limits
~~~

If you only cap at 8 messages/second without counting recipients inside each message, the application can still breach recipient quotas. If you only limit worker threads, the application can exceed rates whenever SMTP calls finish very fast.

### Rate Does Not Equal Thread Count

`ThreadPoolTaskExecutor(maxPoolSize=8)` only bounds active running tasks to 8, not 8 emails/second. One thread can execute many SMTP calls in a second if the provider responds quickly.

Conversely, if one SMTP call takes 10 seconds, an 8-thread cap yields an ideal maximum rate of only ~0.8 calls/second even if policy permits 8 calls/second. Achieving adequate throughput requires balancing **both rate and concurrency**.

### Quotas Are Not a Sleep Delay Between Two Emails

Putting `Thread.sleep(1000)` between sends seems to pace one worker at 1 email/second; yet with 10 workers across 4 replicas, total rate can reach dozens of emails/second. Sleeping also ties up workers without doing useful work.

A rate limiter should decide **whether permission to submit is granted right now**; when denied, the job should wait in a queue/outbox until the right time.

## 3. "Provider-Aware" Means Limiting at the Exact Quota Scope

There is no single global "SMTP rate" across all systems. Identify at which level quotas are actually enforced:

| Scope | Example Limit Key | Architectural Consequence |
|---|---|---|
| Provider | `provider=A` | All senders using the same provider share a budget |
| Provider account/tenant | `account=prod-tenant-1` | Multiple applications may share one quota |
| SMTP credential / API key | `credential=orders-key` | Separate credentials may or may not separate quotas |
| Verified domain | `domain=example.com` | Multiple `From` addresses on the same domain still share related quotas |
| Sender identity | `sender=security@example.com` | Dedicated policies for approved `From` addresses |
| Egress IP | `ip-group=nat-cluster-A` | Multiple pods sharing an IP can affect one another |
| Recipient domain | `recipientDomain=gmail.com` | Per-domain pacing may be needed to reduce deferrals |
| Customer tenant | `tenant=customer-A` | In-app fair-share needed even if provider caps only per account |
| Mail category | `lane=SECURITY` | Critical emails must be protected from campaigns |

One account may face **multiple overlapping limits**. For example, each notification may have to pass simultaneously:

~~~text
Global provider/account quota
          AND
Per-credential rate
          AND
Per-sender policy
          AND
Application tenant fairness
          AND
Concurrency slot
~~~

A job may send only when **every required condition is met**. Never create just one bucket per SMTP host when the provider enforces quotas across an entire account or API key; likewise, never assume splitting credentials across multiple accounts automatically raises quotas if the provider aggregates by organization/domain.

### One Sender Can Use Multiple Providers

An application may have a primary provider and a fallback provider. However, switching routes must never be used to **evade anti-spam policies, quotas, or contractual limits**. Failover must comply with each provider's policies while satisfying SPF/DKIM/DMARC, sender verification, and organizational sending rules.

When switching to another provider, never assume numbers from provider A apply to provider B. Define a separate policy and identify the new sending path's quota keys.

## 4. Data to Gather Before Setting Limits

Before choosing `messagesPerSecond` in `application.yml`, determine:

1. **Contract or service plan:** are limits stated per message, recipient, request, day, hour, connection, or IP?
2. **Quota counting scope:** account, tenant, domain, API key, sender, or shared pool?
3. **Reset cycle:** UTC hour, provider timezone, rolling 24h, monthly, or sliding window?
4. **Burst allowance:** are short bursts permitted, or must the rate stay smooth?
5. **Actual traffic:** average, p95/p99, and spikes during campaigns/cron jobs.
6. **Per-submission latency:** connection setup, SMTP wait, and file transfer times.
7. **Recipients per email:** one or multiple To/Cc/Bcc per message?
8. **Error responses:** which SMTP/HTTP codes indicate throttling, and do they include retry timing?
9. **Connection parameters:** timeouts, connection reuse, concurrency limits, and attachment restrictions.
10. **Replica count and other apps:** do other services share the same account/provider?

If the provider exposes a quota dashboard or stats API, use it as a **source of quota state** while accounting for telemetry lag. In-app counters alone cannot reflect messages sent outside the application using the same credentials.

Never invent quotas from random Internet snippets or other accounts' configs. Major providers adjust quotas by account type, tier, reputation, region, or usage history. Check official documentation and the account console when configuring production.

## 5. Counting by Message or by Recipient?

One SMTP message can have multiple envelope recipients:

~~~text
MAIL FROM:<orders@example.com>
RCPT TO:<a@example.net>
RCPT TO:<b@example.net>
RCPT TO:<c@example.net>
DATA
...
~~~

In a single `mailSender.send(message)` call, what occurs can be:

- **1 message submission**;
- **3 SMTP recipients**;
- multiple quota units depending on the provider;
- partial acceptance where some recipients are rejected while others are still accepted by the server per protocol and sending behavior.

When quotas are counted per recipient, never use a **message-only** counter.

### Unit Cost Rules

A policy might specify:

~~~text
Message rate cost    = 1 per message
Recipient rate cost  = actual envelope recipient count
Daily recipient cost = recipients counted per provider policy
Attachment budget    = total raw MIME bytes when size limits apply
~~~

The application should construct a `SendPlan` before submitting:

~~~java
public record SendPlan(
        String providerId,
        String credentialId,
        String senderProfileId,
        String notificationType,
        int messageCount,
        int recipientCount) {
}
~~~

`SendPlan` is an illustrative domain DTO. Never use `email address` as a metric tag or log key. When one message has multiple recipients, count recipients from the **SMTP envelope** the sender actually uses, not solely `getRecipients(Message.RecipientType.TO)` when Cc/Bcc exist.

### Why Can Multiple Recipients Be Hard to Count?

If the provider rejects a subset of recipients before or after `DATA`, how quota is deducted depends on provider policy. Use a conservative accounting rule: **reserve capacity before submission based on expected recipients**, then reconcile with outcomes and provider reports. Never automatically "refund quota" after an exception unless you are certain the provider did not count that attempt.

## 6. Estimating Required Rate from Backlog and Deadline

Suppose 12,000 subscription emails must finish within 60 minutes. Assuming one recipient per email, the minimum average rate is:

\[
r_{\mathrm{required}} = \frac{12\,000}{60\times60}
  \approx 3.33\ \mathrm{messages/second}
\]

If the provider allows a safe operational rate of 5 messages/second, the campaign can finish in roughly:

\[
t_{\mathrm{ideal}} = \frac{12\,000}{5}
  = 2\,400\ \mathrm{s}\approx 40\ \mathrm{minutes}
\]

This is an **ideal estimate** assuming zero retries, network drops, daily quotas, message construction/close overhead, large attachments, or concurrency limits. Leave margin in practice.

Another metric:

\[
\text{required concurrency}
\approx \text{target rate}\times\text{mean SMTP service time}
\]

To achieve 5 submissions/second when each submission holds a worker for 0.8 seconds on average:

\[
C \approx 5\times 0.8=4
\]

Roughly 4 concurrent SMTP operations is a starting point to measure, **not a configuration guaranteeing throughput**. Variable latency, connection overhead, server throttling, and concurrency limits can alter real results.

### Why Configure Below the Maximum Quota?

When a provider publishes a limit, configuring right at the threshold causes errors when:

- The provider uses a sliding window or burst policy differing from the app's model.
- Multiple replicas are not strictly synchronized.
- Other services share the same credentials.
- Clocks or telemetry lag.
- Multi-recipient messages are billed differently than expected.

You usually need **operational headroom**, such as picking a fraction of the quota and tuning upward based on measurements. The exact headroom ratio is not fixed; base it on policy and operational telemetry.

## 7. Common Rate Limiting Algorithms

An email-sending system may combine multiple algorithms. No single algorithm fits every provider.

| Algorithm | How It Works | Best For | Limitations |
|---|---|---|---|
| Fixed window counter | Counts sends in a fixed interval | Simple per-minute/daily quotas | Bursts across window boundaries |
| Sliding window log/counter | Inspects events over a rolling interval | Matching rolling windows closely | Higher memory/query cost |
| Token bucket | Tokens refill at a fixed rate, allowing bounded bursts | Average rate with permitted bursts | Burst capacity must match provider |
| Leaky bucket / paced queue | Releases work at a steady pace | SMTP providers sensitive to spikes | Can add latency to bursts |
| Concurrency semaphore | Limits active in-flight sends | Bounding concurrent connections/SMTP | Does not cap messages/second |
| Daily budget counter | Tracks total consumption per cycle | Recipients/day or messages/day | Requires accurate reset/window handling |

In practice, systems often combine them:

~~~text
Daily quota counter
        AND
Token bucket per provider/account
        AND
Semaphore per SMTP identity
        AND
Per-tenant fair share
~~~

If a provider **forbids bursts**, a token bucket with large capacity is unsuitable even when the average rate is right. Use a small capacity or a smooth pacing mechanism.

## 8. Token Bucket: Average Rate and Bursts

A token bucket works as follows:

1. The bucket holds at most `capacity` tokens.
2. Tokens refill at `refillRate` tokens/second.
3. Sending a message requires acquiring tokens equal to its cost.
4. If enough tokens exist, grant immediately.
5. If tokens are short, do not send; compute when to retry.

Example:

~~~text
capacity = 10 tokens
refill   = 4 tokens/second
cost     = 1 token/message

Time 0s:       10 tokens, allows burst up to 10 messages
After burst:    0 tokens
Time +0.25s:    1 token, allows one message
Time +1.00s:    4 tokens if unconsumed
~~~

The bucket permits an initial burst while **bounding the long-term rate** to roughly 4 tokens/second. If the provider requires steady pacing, lower capacity or add a pacer.

### Per-Recipient Cost

If a provider counts quota per recipient, one message with 5 recipients may consume 5 tokens:

~~~java
int cost = sendPlan.recipientCount();
RateDecision decision = recipientRateGate.tryAcquire(cost);
~~~

Here `capacity` must be large enough for the highest valid cost, or the application must split messages per policy. If cost exceeds capacity, waiting will **never** accumulate enough tokens; that is a design/admission bug to catch early rather than retrying endlessly.

### Token Buckets Do Not Manage Daily Quotas

A continuously refilling bucket can allow cumulative volume past a 24-hour quota. If a provider enforces both `5 messages/second` and `20,000 recipients/day`, use a separate daily budget counter aligned with the provider's cycle instead of relying on bucket refill.

## 9. Java Example: An In-Memory Token Bucket

This example requires **no external libraries** and illustrates permit issuance inside a **single JVM**. It intentionally **does not sleep** when tokens run out, allowing callers to leave jobs waiting in an outbox.

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.function.LongSupplier;

public record RateDecision(
        boolean allowed,
        Duration retryAfter) {

    public static RateDecision granted() {
        return new RateDecision(true, Duration.ZERO);
    }

    public static RateDecision denied(Duration retryAfter) {
        return new RateDecision(false, retryAfter);
    }
}

public final class LocalTokenBucket {
    private final double capacity;
    private final double refillTokensPerSecond;
    private final LongSupplier ticker;

    private double tokens;
    private long lastNanos;

    public LocalTokenBucket(
            int capacity,
            double refillTokensPerSecond,
            LongSupplier ticker) {

        if (capacity <= 0 || !Double.isFinite(
                refillTokensPerSecond)
                || refillTokensPerSecond <= 0) {
            throw new IllegalArgumentException(
                    "Capacity and refill rate must be positive");
        }

        this.capacity = capacity;
        this.refillTokensPerSecond = refillTokensPerSecond;
        this.ticker = Objects.requireNonNull(ticker);
        this.tokens = capacity;
        this.lastNanos = ticker.getAsLong();
    }

    public synchronized RateDecision tryAcquire(int cost) {
        if (cost <= 0 || cost > capacity) {
            throw new IllegalArgumentException(
                    "Cost must fit within bucket capacity");
        }

        refill();
        if (tokens >= cost) {
            tokens -= cost;
            return RateDecision.granted();
        }

        double missing = cost - tokens;
        double waitNanos = Math.ceil(
                missing * 1_000_000_000d
                        / refillTokensPerSecond);

        long clampedNanos = (long) Math.min(
                waitNanos, (double) Long.MAX_VALUE);
        return RateDecision.denied(
                Duration.ofNanos(clampedNanos));
    }

    private void refill() {
        long now = ticker.getAsLong();
        long elapsedNanos = Math.max(0L, now - lastNanos);
        lastNanos = now;

        double added = (elapsedNanos / 1_000_000_000d)
                * refillTokensPerSecond;
        tokens = Math.min(capacity, tokens + added);
    }
}
~~~

Usage:

~~~java
LocalTokenBucket limiter = new LocalTokenBucket(
        10, 4.0, System::nanoTime);

RateDecision decision = limiter.tryAcquire(1);
if (decision.allowed()) {
    // Job is allowed to start SMTP submission.
} else {
    // Not submitted yet. Schedule retry later instead of sleeping and holding the thread.
    Duration delay = decision.retryAfter();
}
~~~

### Characteristics and Limitations of the Example

- `synchronized` ensures reading/refilling/deducting tokens does not race across threads inside the **same JVM**.
- `System.nanoTime()` measures elapsed time rather than wall-clock time that NTP can adjust.
- `tryAcquire` returns `retryAfter` so the caller handles scheduling; **never blocks inside the method**.
- Once tokens are deducted, this example does not refund them. If SMTP fails to start right after granting, the system may lose a little capacity—this conservative accounting is safer than wrongly refunding on ambiguous outcomes.
- No persistence. Process restarts create a fresh full bucket, which can cause unintended bursts.
- State is not shared across replicas.
- Does not yet account for daily quotas, multi-dimensional limits, or SMTP concurrency.

Therefore, **do not use a local bucket across multiple replicas to claim cluster-wide provider quota compliance**. It is an illustrative component suited for unit tests and simple single-process needs.

### Why Not Sleep Inside tryAcquire?

~~~java
// Undesirable design when there are thousands of jobs:
while (!limiter.tryAcquire(1).allowed()) {
    Thread.sleep(250);
}
~~~

This loop ties up the mail-sending thread even when not allowed to submit, reducing capacity and slowing shutdowns. Workers should reschedule the job via `available_at`/`next_attempt_at` and handle other work or wait for the event scheduler.

## 10. Unit Testing the Token Bucket with a Fake Clock

Testing rate limiters with `Thread.sleep(...)` easily creates flaky tests, especially on busy CI runners. With `LongSupplier ticker`, you can simulate time deterministically.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;
import org.junit.jupiter.api.Test;

final class FakeTicker implements LongSupplier {
    private long nanos;

    @Override
    public long getAsLong() {
        return nanos;
    }

    void advanceMillis(long millis) {
        nanos += TimeUnit.MILLISECONDS.toNanos(millis);
    }
}

class LocalTokenBucketTest {
    @Test
    void grantsBurstThenWaitsForRefill() {
        FakeTicker ticker = new FakeTicker();
        LocalTokenBucket bucket =
                new LocalTokenBucket(2, 1.0, ticker);

        assertThat(bucket.tryAcquire(1).allowed()).isTrue();
        assertThat(bucket.tryAcquire(1).allowed()).isTrue();

        RateDecision denied = bucket.tryAcquire(1);
        assertThat(denied.allowed()).isFalse();
        assertThat(denied.retryAfter().toMillis())
                .isEqualTo(1000);

        ticker.advanceMillis(500);
        assertThat(bucket.tryAcquire(1).allowed()).isFalse();

        ticker.advanceMillis(500);
        assertThat(bucket.tryAcquire(1).allowed()).isTrue();
    }

    @Test
    void rejectsCostLargerThanMaximumBurst() {
        FakeTicker ticker = new FakeTicker();
        LocalTokenBucket bucket =
                new LocalTokenBucket(2, 1.0, ticker);

        org.assertj.core.api.Assertions
                .assertThatThrownBy(() -> bucket.tryAcquire(3))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

This test verifies the algorithm inside a single process; it does not prove a multi-replica system stays within quotas. Distributed limiters require concurrent contention integration tests against a shared store.

## 11. Concurrency Limiter: A Semaphore Alongside the Rate Limiter

Even when the mail rate is capped at 4 messages/second, a single SMTP submission can take several seconds. To protect connections and threads, enforce a separate **in-flight** limit:

~~~java
import java.util.concurrent.Semaphore;

public final class LocalSmtpConcurrencyGate {
    private final Semaphore slots;

    public LocalSmtpConcurrencyGate(int maxConcurrent) {
        if (maxConcurrent <= 0) {
            throw new IllegalArgumentException(
                    "maxConcurrent must be positive");
        }
        this.slots = new Semaphore(maxConcurrent);
    }

    public boolean tryEnter() {
        return slots.tryAcquire();
    }

    public void exit() {
        slots.release();
    }
}
~~~

When combined:

~~~java
if (!concurrencyGate.tryEnter()) {
    // Worker/dispatcher has no slot yet; SMTP not called.
    return;
}

try {
    RateDecision rate = tokenBucket.tryAcquire(1);
    if (!rate.allowed()) {
        // Reschedule the job; SMTP not called.
        return;
    }

    mailSender.send(message);
} finally {
    concurrencyGate.exit();
}
~~~

**Only call `exit()` when a slot was genuinely acquired.** In the example, the no-slot branch returns before `try/finally` so it never releases mistakenly. When `mailSender.send` throws an exception, `finally` returns the slot.

### Limitations of a Local Semaphore

With 5 replicas each configured for 4 slots, the whole cluster can have **20 concurrent SMTP calls**. If the provider limits the entire account to 4 connections, local semaphores are insufficient. You need **global concurrency coordination**, or a centralized worker / per-replica quota config with skew safeguards.

In addition, an SMTP submission may reuse connections depending on the library/provider; bounding running tasks does not always match exact TCP connection count. Measure in practice.

## 12. Daily Quota: A Dedicated Limit with a Clear Reset Cycle

Suppose a provider caps usage at 30,000 recipients per 24-hour cycle. The system must track:

- Whether the quota unit is messages or recipients.
- Whether the cycle is a **calendar day** in the provider's timezone or a **rolling 24h** window.
- Whether sends from other apps/credentials share the same quota.
- Whether the provider also counts rejected submissions or retries against quota.
- Whether an API exposes remaining quota or reset timestamps.

A UTC daily counter might look like:

~~~text
quota:provider-A:account-prod:2026-11-12
usedRecipients = 18,420
maxRecipients  = 30,000
remaining      = 11,580
~~~

**Do not assume a UTC calendar day if the provider uses a rolling 24-hour window or another timezone.** A fixed daily counter can permit nearly double the rate within a few minutes around midnight when the provider enforces a rolling 24h limit.

### Actions When Approaching Quota Exhaustion

For critical emails:

1. Throttle or pause non-urgent lanes (marketing/digests).
2. Reserve a portion of the budget for OTPs and transactional emails if policy allows.
3. Reduce rates and increase delays for campaigns.
4. Alert on backlog and estimated completion time.
5. If exceeded, keep unsent jobs in the outbox until the next quota window.

Never retry aggressively every second while the remaining daily quota is zero. When the reset time is known, set `next_attempt_at` accordingly; otherwise, poll conservatively and cross-check the provider dashboard.

## 13. Why Are Local Limits Insufficient Across Multiple Replicas?

Spring Boot is commonly deployed across multiple instances:

~~~text
Provider account shared quota: 12 messages/s

Replica A: local limit 12/s
Replica B: local limit 12/s
Replica C: local limit 12/s
Replica D: local limit 12/s
--------------------------------
Total can reach up to 48/s
~~~

Each replica believes it is obeying the quota, yet **the whole cluster** can send four times faster than the account limit.

Several solutions:

| Design | Pros | Things to Watch |
|---|---|---|
| Single centralized SMTP dispatcher per account quota | Easy to enforce global rate | Needs HA and backlog handling |
| Redis/distributed token bucket | Atomic permits across replicas | Shared store, latency, consistency, failover |
| Database-backed quota reservation | Reuses existing DB, clear transactions | Row contention, throughput, locking |
| Broker with concurrency/rate-capped consumers | Durable job distribution and coordination | Still needs shared quota cap as consumers scale |
| Static quota partitioning across replicas | Simple when replica count is fixed | Autoscaling/skew/wasted quota |
| Provider-native rate control | Provider is the final enforcer | Often lacks optimal latency/retry behavior |

**Redis does not automatically make a distributed rate limiter correct.** You must design atomic token deductions, clocks, TTLs, key scopes, restart behavior, trade-offs when Redis disconnects, and retry handling.

### Never Share One Key Across Independent Quotas

If Provider A and Provider B have separate budgets, do not put both into one bucket. Conversely, if two SMTP credentials actually share one organization quota, creating separate buckets per credential can exceed the shared quota.

Rate-limit keys must match **the exact scope enforced by the provider**, not bean names or hostnames visible in config.

## 14. Distributed Token Bucket: Reservations Must Be Atomic

Suppose two workers read the bucket state concurrently:

~~~text
Bucket has 1 token remaining

Worker A reads = 1
Worker B reads = 1
Worker A sends an email
Worker B sends an email

Result: 2 consumed despite only 1 token left.
~~~

The fix is not simply caching token counts in Redis. You need **atomic read–refill–decrement–write** on the same bucket, e.g., via a Redis Lua script or properly semantic transaction/compare-and-swap.

Pseudo-code:

~~~text
reserve(providerAccountKey, cost, now):
    ATOMIC {
        state = load(key)
        state.tokens = min(
            capacity,
            state.tokens + elapsed(now, state.updatedAt)*refillRate)

        if cost > capacity:
            return INVALID_COST

        if state.tokens < cost:
            persist(refilled state)
            return DENIED_WITH_RETRY_AFTER

        state.tokens -= cost
        state.updatedAt = now
        persist(state, with suitable TTL)
        return GRANTED
    }
~~~

This pseudo-code cannot be implemented as separate `GET`, compute, and `SET` calls across replicas without locks or atomicity guarantees. In practice, pick a proven distributed rate-limiting library or implement a script/transaction and test race conditions thoroughly.

### Factors to Define in a Distributed Implementation

- **Clock:** does time come from clients or the Redis server? Could clock skew across replicas distort token refill?
- **Atomicity:** do token deduction and state persistence happen in one atomic operation?
- **TTL:** when a key expires, does the bucket reinitialize full and allow a policy-breaking burst?
- **Persistence:** on Redis restart or failover, is quota state lost?
- **Network partition:** when permits cannot be acquired, does sending pause or fall back under tight limits?
- **Idempotency:** if a client times out after Redis granted a permit, does retrying the permit request burn extra tokens?
- **Scope:** do key names avoid recipients/PII and match real account/provider quotas?
- **Capacity:** could multi-recipient message costs exceed bucket token capacity?

### Never Store Recipient Addresses in Rate Limiter Keys

Example:

~~~text
mail:limit:provider-A:account-orders
mail:limit:provider-A:sender-security
mail:limit:provider-A:tenant-42
~~~

Provider/account/tenant identifiers should be controlled internal IDs. Never use `mail:limit:user@example.com` without a compelling reason; that also leaks sensitive data into Redis keys, metrics, and logs.

## 15. Simple Case: Static Quota Partitioning Across Replicas

Without a distributed store and with a fixed replica count, a temporary option is splitting the budget:

~~~text
Account safe budget: 12/s
4 replicas
Per replica: 3/s
~~~

This can keep total usage below quota **if there truly are only four replicas, all run identical configs, and no other sender shares the account**. However, issues arise:

- Autoscaling to 6 replicas can push total traffic over the limit.
- An idle replica wastes its share of quota.
- Rolling deployments can temporarily spawn extra replicas.
- Other apps sharing the account remain unaccounted for.
- A provider's rolling window may not align with local limiter boundaries.

Therefore, use this only when assumptions are tightly controlled, paired with monitoring and headroom. For critical multi-replica mail systems, **shared admission control** is generally more reliable.

## 16. Database Quota Reservation: When an Outbox Already Exists

When all mail jobs live in the same database, provider/account quotas can be managed transactionally. PostgreSQL example for a simple **calendar window**:

~~~sql
CREATE TABLE mail_quota_window (
    quota_key VARCHAR(150) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    capacity BIGINT NOT NULL CHECK (capacity > 0),
    reserved BIGINT NOT NULL DEFAULT 0
        CHECK (reserved >= 0),
    PRIMARY KEY (quota_key, window_start),
    CHECK (window_end > window_start)
);
~~~

A worker wants to reserve 3 recipients in the resolved window:

~~~sql
UPDATE mail_quota_window
SET reserved = reserved + :cost
WHERE quota_key = :quota_key
  AND window_start = :window_start
  AND reserved + :cost <= capacity
RETURNING reserved;
~~~

If the statement returns one row, reservation succeeded. If no row returns, either the window's budget is exhausted or the window/key row does not exist. **Never treat "no rows returned" as "quota is still available."**

In PostgreSQL, concurrent updates to the same row serialize via row-level locking so the capacity predicate is re-evaluated across competing transactions. Still, ensure:

- Window rows are created safely without initialization races.
- Windows match the provider's actual reset policy.
- Everything under the same account/organization shares the same `quota_key`.
- Margin exists for quota consumed outside the application.
- The reservation transaction commits quickly without holding locks during SMTP sends.

This is a **fixed-window counter reservation**, not an exact rolling 24h implementation. If the provider uses a rolling window, use a rolling-window structure/mechanism or provider telemetry.

### Why Not Keep Transactions Open During SMTP Calls?

~~~text
BEGIN TRANSACTION
  SELECT ... FOR UPDATE quota row
  JavaMailSender.send(...)  ← may block for several seconds
  UPDATE ...
COMMIT
~~~

This design holds database locks and connections across network I/O; throughput can plummet and create heavy contention. Instead, **reserve quota quickly in a transaction**, commit, and then call SMTP outside the transaction.

If a worker dies after reserving but before sending, a bit of quota is "lost" in the counter. This conservative choice lowers quota-breach risk; reservation leases/reconciliation can reclaim unused slots if maximizing utilization, though never refund quota when the server may have accepted the message.

## 17. Multiple Simultaneous Limits: Avoiding Partial Reservations

Suppose a message must pass two quotas:

- Account has 10 tokens left.
- Sender identity has exhausted its quota.

If the code does:

~~~text
reserve account token  → succeeds
reserve sender token   → fails
~~~

then the account lost tokens even though nothing was sent. If callers retry repeatedly, account budget can drain without sending a single email.

Ways to handle this:

1. **Atomic multi-key reservation:** if keys sit in the same store and support proper transactions/scripts, check and deduct **all or nothing**.
2. **Coordinated reservation:** manage reservation state with transactions/leases and controlled rollbacks only when sending definitely never started.
3. **Conservative accounting:** accept small phantom quota loss to avoid breaching limits; curb overly frequent retries.
4. **Sequential coordinator dispatcher:** at moderate throughput, a single coordinator can be simpler to manage.

In Redis Cluster designs, multi-key Lua scripts may require keys to share a hash slot; never assume arbitrary keys update atomically across a cluster. With multiple DB counter rows, lock in a consistent order to reduce deadlocks and write reservations in one transaction.

**Never string together `tryAcquire()` calls across three buckets and call SMTP without defining what happens when the second or third bucket rejects.**

## 18. Fail Closed or Fail Open When the Limiter Fails?

If Redis/the quota service goes down, the dispatcher has several options:

| Policy | Behavior | Risks / Benefits |
|---|---|---|
| Fail closed | Do not submit mail; keep jobs in outbox | Prevents uncontrolled quota breaches; backlog grows |
| Fail open | Continue sending without permits | Preserves throughput, risks quota breach/account suspension |
| Bounded emergency fallback | Send only critical subset at very low rate | Requires explicit budget and operational runbook |
| Switch to backup provider | Only when route is pre-approved | Needs separate limits, sender auth, and quotas |

For marketing/batch mail, fail closed is usually safer to control. For OTPs or security alerts, consider a **pre-designed fallback path**, yet never bypass all rate limits indefinitely when the limiter store fails.

If falling back, calculate the **cluster-wide** cap rather than setting a 1/s local limiter across 100 replicas and assuming total load is safe. Audit when fallback mode toggles on/off, who approved it, jobs sent, and fallback quota consumed.

### Quota Coordination Systems Also Need Monitoring

A malfunctioning limiter might produce zero immediate SMTP errors while starving jobs from ever sending. Track metrics:

- Permits granted / denied.
- Permit acquisition latency.
- Limiter store connection errors.
- Reservation timeouts.
- Age of jobs delayed due to quotas.
- Remaining token/budget percentage if known.

Never confuse "zero SMTP errors" with "healthy system" while backlog climbs because the limiter stopped granting permits.

## 19. Separating Durable Send Intent from Permission to Send Now

A rate limiter is not a queue. When the bucket runs out of tokens, send requests must **sit in durable storage** if emails cannot be lost.

A Spring-compatible architecture:

~~~mermaid
flowchart TD
    A[Application use case] --> B[Database transaction]
    B --> C[Business state + Mail outbox]
    C --> D[Commit]
    D --> E[Outbox dispatcher]
    E --> F{Provider quota available?}
    F -- No --> G[Reschedule available_at]
    G --> E
    F -- Yes --> H{Concurrency slot available?}
    H -- No --> G
    H -- Yes --> I[SMTP submission]
    I --> J{Outcome}
    J -- Accepted --> K[Mark SUBMITTED]
    J -- Temporary rejection --> L[Backoff + RETRY]
    J -- Permanent rejection --> M[DEAD / review]
    J -- Unknown --> N[UNKNOWN + policy]
    L --> E
~~~

Key points:

- The **Outbox** preserves send intents across restarts when written in the right transaction.
- The **Rate limiter** decides whether a submission may start right now.
- The **Concurrency limiter** caps active in-flight SMTP operations.
- The **Retry policy** handles outcomes rather than retrying blindly forever.
- **Database state** distinguishes jobs waiting on quota, retrying SMTP errors, or already submitted.

These mechanisms solve distinct problems; `@Async` or a huge thread pool does not replace them.

### Job State Pattern

~~~text
PENDING
   |
   +-- quota insufficient --------> WAITING_RATE_LIMIT
   |                                 |
   |                                 v
   |                              PENDING
   |
   +-- claim + permit ----------> PROCESSING
                                     |
                  +------------------+----------------+
                  |                  |                |
                  v                  v                v
              SUBMITTED           RETRY              UNKNOWN
                                     |
                                     v
                                   PENDING
~~~

`WAITING_RATE_LIMIT` is a suggested state name, not a built-in Spring Mail enum. Simple systems may keep `PENDING` with a future `available_at` instead of adding a new state; what matters is that workers do not treat "insufficient tokens" as an attempted SMTP failure.

## 20. Outbox Claiming and Keeping Database Connections Short

An outbox worker typically follows this loop:

1. Identify the provider/account and remaining capacity.
2. Claim a small batch of due jobs with a lease so multiple workers do not claim the same job.
3. Compute cost by message/recipient and applicable policies.
4. Acquire quota permit and concurrency slot.
5. Submit SMTP **outside the DB transaction**.
6. Persist outcome or retry schedule in a short transaction.

PostgreSQL batch-claim SQL example:

~~~sql
WITH ready AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND available_at <= CURRENT_TIMESTAMP
      AND provider_id = :provider_id
    ORDER BY priority DESC, available_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS job
SET status = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP,
    claim_token = :claim_token,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds'
FROM ready
WHERE job.id = ready.id
RETURNING job.id, job.provider_id, job.recipient_count;
~~~

This is an illustrative SQL design assuming the `mail_outbox` table has matching columns. `SKIP LOCKED` keeps multiple workers from blocking on locked rows, though it does not guarantee strict FIFO. `claim_token` must distinguish claim rounds, and post-send state updates must verify the token so stale workers cannot overwrite newer workers.

**Do not claim 50,000 jobs and push all of them into a `ThreadPoolTaskExecutor` queue.** With a real limit of 5 emails/second, holding thousands of claimed jobs in RAM causes lease expirations, duplicate work, and poor backpressure control.

### When the Bucket Denies Permission

Upon `RateDecision.denied(retryAfter)`:

- Return the job to a waiting state or update `available_at`.
- Release the claim/lease in a short transaction.
- Do not increment "SMTP attempt count" since SMTP was not called.
- Optionally increment `rate_limit_deferral_total`.
- Prevent workers from repeatedly re-claiming the same job in the same millisecond.

When a provider enforces both a daily quota and a per-second rate, `available_at` should reflect the earliest time **all conditions are satisfied**, not solely the fastest-refilling bucket.

## 21. Configuring Per-Provider Policies in Spring Boot

Place policies in an application namespace rather than hardcoding them across code:

~~~yaml
app:
  mail:
    limits:
      primary:
        bucket-capacity: 10
        refill-tokens-per-second: 4.0
        max-concurrent: 3
        max-recipients-per-message: 20
        safe-daily-recipient-budget: 15000
      backup:
        bucket-capacity: 4
        refill-tokens-per-second: 1.5
        max-concurrent: 2
        max-recipients-per-message: 10
        safe-daily-recipient-budget: 3000
~~~

These numbers are **purely illustrative**, not official quotas for any specific provider. `app.mail.limits` is an **application-defined** namespace; Spring Boot will not automatically enforce quotas just because YAML contains these fields.

Record binding example:

~~~java
import org.springframework.boot.context.properties
        .ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.limits")
public record MailLimitProperties(
        ProviderLimit primary,
        ProviderLimit backup) {

    public record ProviderLimit(
            int bucketCapacity,
            double refillTokensPerSecond,
            int maxConcurrent,
            int maxRecipientsPerMessage,
            long safeDailyRecipientBudget) {
    }
}
~~~

Register via `@EnableConfigurationProperties`:

~~~java
import org.springframework.boot.context.properties
        .EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MailLimitProperties.class)
public class MailLimitConfiguration {
}
~~~

Illustrative local rate limiters for two providers:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LocalRateGateConfiguration {

    @Bean("primaryRateGate")
    LocalTokenBucket primaryRateGate(
            MailLimitProperties config) {
        var policy = config.primary();
        return new LocalTokenBucket(
                policy.bucketCapacity(),
                policy.refillTokensPerSecond(),
                System::nanoTime);
    }

    @Bean("backupRateGate")
    LocalTokenBucket backupRateGate(
            MailLimitProperties config) {
        var policy = config.backup();
        return new LocalTokenBucket(
                policy.bucketCapacity(),
                policy.refillTokensPerSecond(),
                System::nanoTime);
    }
}
~~~

**Warning:** these two beans are **local JVM limiters** illustrating dependency injection. With multiple replicas sharing one provider account, replace them with a shared rate gate or centralized dispatcher. `safeDailyRecipientBudget` and `maxConcurrent` are not enforced by those beans yet; add matching daily quota counters and concurrency gates.

### Validate Configuration Before Startup

Never start the service with:

- `bucketCapacity <= 0`.
- `refillTokensPerSecond <= 0`.
- `maxConcurrent <= 0`.
- `maxRecipientsPerMessage <= 0`.
- Negative daily budgets, or zero unless intentionally disabling a lane.
- Message costs larger than burst capacity without a job-splitting mechanism.

Use Jakarta Bean Validation (`@Validated`, `@Min`, `@Positive`) along with cross-field checks. Configuration is an **operational safety invariant**; invalid settings should fail fast rather than leaving jobs stuck forever at runtime.

### Changing Policies at Runtime

When an operator lowers the rate from 4 to 2 tokens/second, all replicas must adopt the new config consistently. If a local bucket initializes once at startup, editing YAML will not update beans automatically unless the app has an explicit reload mechanism. Distributed limiters also need a policy version so some workers do not enforce the new capacity while others enforce the old capacity.

Never let public endpoints modify provider limits. Changing quotas requires authorization, auditing, and compliance with provider contracts.

## 22. Using the Rate Gate from a Service/Dispatcher

An abstraction decouples specific algorithms from mail submission:

~~~java
public interface ProviderRateGate {
    RateDecision reserve(
            String providerAccountId, int recipientCost);
}

public interface MailJobStore {
    void deferForQuota(String jobId, java.time.Duration delay);
    void markSubmitted(String jobId);
    void recordFailure(String jobId, MailDispatchFailure failure);
}
~~~

The interfaces and `MailDispatchFailure` are application-defined types. A conceptual coordinator:

~~~java
import org.springframework.mail.javamail.JavaMailSender;

public final class MailDispatchCoordinator {
    private final ProviderRateGate rateGate;
    private final MailJobStore jobStore;
    private final JavaMailSender mailSender;

    public MailDispatchCoordinator(
            ProviderRateGate rateGate,
            MailJobStore jobStore,
            JavaMailSender mailSender) {
        this.rateGate = rateGate;
        this.jobStore = jobStore;
        this.mailSender = mailSender;
    }

    public void dispatch(ClaimedMailJob job) {
        RateDecision permit = rateGate.reserve(
                job.providerAccountId(),
                job.recipientCost());

        if (!permit.allowed()) {
            jobStore.deferForQuota(
                    job.id(), permit.retryAfter());
            return;
        }

        try {
            mailSender.send(job.mimeMessage());
            jobStore.markSubmitted(job.id());
        } catch (org.springframework.mail.MailException ex) {
            // Classify error; do not log raw exception/recipient.
            jobStore.recordFailure(
                    job.id(), MailDispatchFailure.from(ex));
        }
    }
}
~~~

`ClaimedMailJob` and `MailDispatchFailure.from` are illustrative abstractions. The code focuses on **where permits are acquired before SMTP**. A production implementation must add:

- A concurrency gate and provider/account-based `JavaMailSender` selection.
- Ownership/claim-token checks in state transitions.
- Transaction boundaries for job status updates.
- Error handling when the **rate gate or job store** fails.
- Logic for uncertain outcomes; never assume every `MailException` is safely retryable.
- Blocking jobs that unsubscribed or expired by business rules right before sending.
- Keeping state consistent if the process crashes after SMTP acceptance.

### Do Not Do SMTP Work Directly Inside @Scheduled Methods

A scheduler should primarily **wake up the dispatcher**:

~~~java
@Scheduled(fixedDelayString = "${app.mail.poll-delay-ms:1000}")
public void wakeUpDispatcher() {
    dispatcher.dispatchReadyBatch();
}
~~~

If the scheduled method sends thousands of emails synchronously itself, it occupies the scheduler thread and delays other schedules. Workers executing SMTP should use a dedicated executor with bounded queues/concurrency. The scheduler need not claim jobs when the rate gate is already known to deny all traffic for a period.

## 23. Multi-Dimensional Coordination: Rate, Quota, and Concurrency

A send may have to pass through these gates:

~~~text
Mail job
   |
   v
Check business eligibility / suppression
   |
   v
Check per-message recipient and size limits
   |
   v
Reserve provider-account daily budget
   |
   v
Reserve provider-account rate token
   |
   v
Reserve sender-specific rate token
   |
   v
Acquire SMTP concurrency slot
   |
   v
JavaMailSender.send(...)
   |
   v
Save outcome, release concurrency slot
~~~

This is a logical diagram. **Do not blindly implement each step as independent non-rollbackable deductions.** Define a coordinated reservation or atomic admission mechanism matching actual quotas. If account quota was reserved and sender rate then denies, handle the dangling reservation per design or use one atomic operation.

Exact ordering depends on cost:

- Check business/recipient eligibility first so cancelled jobs do not waste quota.
- Check immutable or cheap conditions first.
- With multiple quotas, prefer atomic admission decisions where possible.
- Never hold DB transactions/locks or thread slots across long quota waits.
- Call SMTP only when eligible and holding an execution slot.

### One Call, Multiple Recipients

If a message has 10 recipients, deduct 10 units **from the per-recipient limiter**, yet only 1 unit from the per-message limiter. A single cost model across every quota can be wrong.

~~~text
messagesPerSecond bucket:    cost = 1
recipientsPerSecond bucket:  cost = 10
recipientsPerDay budget:    cost = 10
connectionConcurrency:      cost = 1 slot
~~~

Each quota needs an explicit unit documented in field, config, and metric names. Avoid an ambiguous `limit=100` parameter where nobody knows if it means 100 emails or 100 recipients.

## 24. Fairness: Never Let Campaigns Starve OTP Quotas

One account may serve multiple lanes:

~~~text
HIGH:  security / OTP
MED:   order receipts / account notifications
LOW:   newsletter / marketing digest
~~~

If all jobs enter one FIFO queue, 100,000 newsletters enqueued earlier can stall newly arriving OTPs for a long time even while the provider still allows sends.

Solutions:

| Policy | Benefit | Things to Watch |
|---|---|---|
| Strict priority | Critical emails go first | Low lanes can starve |
| Reserved capacity | Reserves quota slice for security | Wasted if priority lane is idle |
| Weighted fair queueing | Allocates capacity across lanes | More complex than FIFO |
| Separate provider accounts | Strong quota isolation when truly independent | More operational overhead; may still share org limits |
| Time-based campaign throttling | Smooths marketing traffic | Must still meet campaign deadlines |

Illustrative budget example:

~~~text
Safe account rate = 10 messages/s

Security lane   -> reserve 3/s when needed
Transaction     -> target max 5/s
Marketing       -> uses remaining capacity
~~~

Do not treat these numbers as real quotas. When designing reservations, specify whether unused slots can be "borrowed" by other lanes and whether they are reclaimed when priority emails arrive.

### Per-Tenant Fairness

If 50 organization customers share one provider account, one tenant's huge batch can delay other tenants' backlogs. Add soft per-tenant quotas, weighted round-robin, or per-tenant token buckets underneath the account-wide quota.

**Tenant quotas must never exceed the shared account quota.** Per-tenant limiters only divide existing capacity fairly; they do not create extra provider capacity.

## 25. How Does Provider Throttling Show Up Over SMTP?

Unlike HTTP email APIs, SMTP returns reply codes across steps like connection, `MAIL FROM`, `RCPT TO`, and `DATA`. Common codes:

| SMTP Reply | General Meaning | Handling |
|---|---|---|
| `421` | Service temporarily unavailable / closing connection | Usually defer and retry per policy |
| `450` | Mailbox action temporarily unavailable | Check reason, defer reasonably |
| `451` | Temporary local processing error | Retry with backoff if outcome is clear |
| `452` | Insufficient resources / temporary restriction | Slow down or defer |
| `454` | Temporary auth/TLS condition | Inspect specific cause |
| `4.7.x` enhanced status | Often security/policy or rate/deferral depending on provider | Consult provider docs and context |
| `5xx` | Permanent rejection per reply semantics | Usually fix root cause; do not retry blindly |

**Not every `4xx` response means "rate limit exceeded."** Providers may defer for mailbox state, anti-abuse, greylisting, DNS, or internal errors. Conversely, a provider may signal quota/rate limits via a custom error code in the SMTP response.

Classify accurately using:

1. SMTP reply code.
2. Enhanced status code if present.
3. Protocol phase when the response arrived.
4. Rules of the specific provider/account.
5. Certainty regarding message submission outcome.

Do not rely solely on `exception.getMessage().contains("rate limit")`, because messages can change language/format or contain recipient addresses and sensitive data.

### SMTP Throttling and HTTP 429 Are Not Identical

When using an **HTTP email API**, the provider may return:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{"code":"RATE_LIMIT_EXCEEDED"}
~~~

`Retry-After` is an HTTP header that may hold seconds or an HTTP-date per HTTP rules. When using an HTTP API, respect this header per provider documentation.

**There is no universal standard `Retry-After` header in SMTP like in HTTP.** Over SMTP, retry timing is normally derived from reply details/provider limits, backoff policies, and published quota reset windows.

### A Reply After RCPT TO Differs from One After DATA

Before the SMTP client sends the `DATA` body, the server can reject one recipient or the whole transaction. After the server receives the body and before the client receives the final reply, the connection can end in an **ambiguous state where acceptance is unknown**.

Therefore distinguish:

~~~text
RATE_LIMIT_REJECTED_BEFORE_ACCEPTANCE
        -> Evidence of non-acceptance; can schedule retry

SMTP_ACCEPTED
        -> Do not retry as unsent

SMTP_OUTCOME_UNKNOWN
        -> Duplicate risk if re-sent
~~~

Rate limiting does not turn SMTP into exactly-once delivery. Retries and duplicates still require idempotency/correlation per workflow capabilities and explicit risk acceptance.

## 26. Classifying Errors in Spring Mail

Spring Mail provides exceptions such as `MailSendException`, `MailAuthenticationException`, and `MailPreparationException`. An SMTP failure may wrap Jakarta Mail or SMTP transport provider exceptions.

Suggested table:

| Error Type | Is Rate Limiter the Cause? | Response |
|---|---|---|
| Invalid email address | No | Validate; do not retry like throttling |
| MIME preparation failed | No | Fix data/template/resource |
| SMTP authentication rejected | Usually no | Check credentials/OAuth/policy |
| Evident SMTP temporary throttle | Possibly | Defer, lower rate, and retry |
| Network connect timeout before send | Uncertain | Check availability, back off |
| Connection lost after `DATA` | Uncertain outcome | `UNKNOWN` state, duplicate policy |
| Provider daily quota exhausted | Yes | Wait for quota reset or pre-approved backup route |
| HTTP 429 from email API | Possibly | Honor `Retry-After` and quota key |
| SMTP permanent sender not permitted | No | Fix sender permissions; do not retry infinitely |

Because `MailSendException` can represent multiple messages/causes, **never catch that type alone and assume every message was throttled**.

Example classifier emitting internal codes only:

~~~java
public enum SubmissionFailureKind {
    RATE_THROTTLED,
    TEMPORARY_TRANSPORT_FAILURE,
    AUTHENTICATION_FAILURE,
    INVALID_MESSAGE,
    PERMANENT_REJECTION,
    UNKNOWN_OUTCOME
}
~~~

This is an **application-defined enum**. The classifier should use observable cause chains, SMTP statuses, and protocol phases, prioritizing types and codes over raw text containing recipients. Without enough evidence, classify as `UNKNOWN_OUTCOME` or an unclassified code rather than claiming the server did not receive the message.

### Safe Logging When Providers Echo Recipients

An SMTP error might contain:

~~~text
451 4.7.0 Temporarily throttled for <person@example.test>
~~~

Never log raw exception messages or raw SMTP transcripts when they include emails, tokens, subjects, or bodies. Log:

~~~text
event=mail_submission_failed
jobId=mail-job-001
provider=PRIMARY
failureKind=RATE_THROTTLED
smtpStatusClass=4xx
attempt=3
~~~

This lets you monitor rates without turning logs into a shadow copy of recipient data.

## 27. Retries with Exponential Backoff and Jitter

When many workers get rejected for throttling, if all retry exactly 1 second later, they create a new thundering herd:

~~~text
00:00  1000 jobs get throttled
00:01  all 1000 retry simultaneously
00:02  all 1000 retry simultaneously
...
~~~

**Exponential backoff** increases wait times with attempt count:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Where:

- `d0`: base delay.
- `n`: consecutive failure count or retry count per policy.
- `dmax`: maximum delay cap.

Add **jitter** so workers do not wake up simultaneously:

\[
d_{\mathrm{jitter}} \sim U(0, d_n)
\]

This is *full jitter*: picking uniformly between 0 and the capped delay for that attempt. Systems also need a **minimum retry delay** to avoid retrying some jobs almost immediately.

### Java Example Generating Retry Delay

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryBackoff {
    private final long baseMillis;
    private final long maxMillis;

    public RetryBackoff(
            Duration baseDelay,
            Duration maxDelay) {
        this.baseMillis = baseDelay.toMillis();
        this.maxMillis = maxDelay.toMillis();
        if (baseMillis <= 0 || maxMillis < baseMillis) {
            throw new IllegalArgumentException(
                    "Invalid retry delay bounds");
        }
    }

    public Duration forFailureNumber(int failureNumber) {
        if (failureNumber < 1) {
            throw new IllegalArgumentException(
                    "Failure number starts at 1");
        }

        long cap = baseMillis;
        for (int i = 1; i < failureNumber; i++) {
            if (cap >= maxMillis) {
                break;
            }
            cap = cap > maxMillis / 2
                    ? maxMillis
                    : cap * 2;
        }

        long randomized = ThreadLocalRandom.current()
                .nextLong(cap + 1);
        return Duration.ofMillis(randomized);
    }
}
~~~

Production systems may also need:

- A minimum delay to prevent instant same-millisecond retries.
- Honoring `Retry-After` or quota reset times when exposed by an **HTTP API/provider**.
- Max attempts, deadlines, and maximum job age.
- Separating transient errors from permanent errors and `UNKNOWN`.
- Storing `next_attempt_at` in the database to survive restarts.
- Alerting when backlog age rises or jobs enter dead-letter queues.

### Retry Delays and Rate Gates Must Coordinate

When a job becomes due for retry, the worker **must still request a permit** from the current provider gate. Backoff does not replace rate limiting, because other jobs may be consuming quota. Conversely, holding a permit does not prove the earlier outage has cleared.

When the server specifies a reliable minimum retry timestamp (such as HTTP `Retry-After`), retry scheduling should not run earlier than that time. Likewise, never retry while the daily budget is exhausted and unreset.

## 28. Adaptive Rate Control When Providers Throttle Continuously

A static rate limit taken from provider docs can still be too high during sender-reputation dips or provider incidents. Some systems add **adaptive throttling**:

~~~text
If sending is stable over observation window:
    increase rate slowly, never exceeding safe configured cap

If throttle rate increases:
    decrease rate relatively quickly

If provider daily quota is nearly exhausted:
    restrict non-priority lanes
~~~

A simple variant is **AIMD** (*additive increase, multiplicative decrease*):

\[
r_{t+1} =
\begin{cases}
  \max(r_{\min}, \beta r_t),
    & \text{when provider throttles significantly} \\
  \min(r_{\max}, r_t + \alpha),
    & \text{when stable and budget remains}
\end{cases}
\]

Where `0 < β < 1` is the decrease factor and `α > 0` is a small additive step.

**Adaptive controllers must never exceed the provider's hard cap** and must not turn an idle network outage into a post-recovery speedup. Observe over sufficiently long windows to avoid constant oscillation.

### Do Not Raise Rate When the System Has No Load

When queues are empty, seeing zero throttling does not mean the provider can handle faster sending. Adaptive policies must rely on real request samples, success rates, and latency rather than ramping up unboundedly during idle minutes.

### Backpressure and Circuit Breakers Are Different

- **Rate limiter:** bounds usage while the provider is operating normally.
- **Backpressure:** stops accepting/dispatching more work when processing capacity cannot keep up.
- **Circuit breaker:** throttles or blocks new calls when a dependency fails continuously.
- **Retry/backoff:** schedules retries for potentially recoverable errors.

An email provider suffering a major outage may need a circuit breaker and holding jobs in the outbox, not merely lowering rate from 10 to 8 emails/second. Conversely, when a provider works fine with a low quota, a circuit breaker does not replace a token bucket.

## 29. Multi-Provider Routing and Failover

If the organization allows using multiple providers:

~~~text
Outbox
    |
    v
Routing policy
    |
    +-- Primary SMTP
    |      +-- own quota/rate/concurrency
    |
    +-- Backup SMTP
           +-- own quota/rate/concurrency
~~~

However, failover must consider:

1. Are the sender domain and `From` verified with provider B?
2. Do DKIM/SPF/DMARC align with the new route?
3. Is there a separate contracted backup quota?
4. Would it breach an aggregate organization/provider quota?
5. Which system receives bounces, complaints, and feedback?
6. Is the job in SMTP **UNKNOWN** state on provider A?
7. What business impact could duplicate sends from two providers cause?

Never immediately reroute a job that timed out after `DATA` to provider B without determining whether provider A may have accepted it. That is a common cause of unintended duplicate emails.

### Failover Is Not a Way to Bypass Provider Limits

If a provider temporarily blocks traffic for spam-like behavior, rotating across multiple accounts/providers to keep blasting email can worsen the issue and violate terms of service. Routing splits for **availability and legitimate use** must be explicitly designed, approved, and monitored.

## 30. Monitoring: Measure Both Sent Emails and Quota-Blocked Emails

A dashboard showing only `mail_sent_total` is insufficient. When a limiter works well, **SMTP errors may drop** while backlog climbs if demand exceeds provider capacity. Monitor admission, queues, and actual submissions together.

| Metric | Meaning | When Abnormal |
|---|---|---|
| `mail_rate_limit_permit_total` | Permits granted | May be too low or too high vs. expectations |
| `mail_rate_limit_denied_total` | Times deferred by limiter | Sustained rise when backlog is large |
| `mail_provider_throttle_total` | Provider throttling responses | Rising even with internal limiter active |
| `mail_quota_remaining` | Remaining budget per account | Near 0 long before reset time |
| `mail_outbox_pending` | Jobs awaiting send | Climbing steadily, exceeding capacity |
| `mail_outbox_oldest_age_seconds` | Age of oldest pending job | Breaching lane SLA |
| `mail_submission_duration_seconds` | Send latency | Climbing p95/p99 |
| `mail_executor_active_threads` | Busy workers | Constantly hitting ceiling |
| `mail_executor_queue_size` | Jobs queued in RAM | Climbing or hitting capacity |
| `mail_rate_gate_duration_seconds` | Time to acquire permit | Shared limiter/store is slow |
| `mail_rate_gate_errors_total` | Permit acquisition errors | Redis/DB coordinator outage |
| `mail_job_retry_total` | Jobs entering retry | Climbing due to SMTP errors |
| `mail_job_unknown_total` | Uncertain outcomes | Duplicate risk |
| `mail_submission_accepted_total` | Provider accepted | True throughput |

A controlled label scheme:

~~~text
provider_id=PRIMARY
account_id=ORDERS
mail_lane=TRANSACTIONAL
result=PERMIT_DENIED
reason=RATE_WINDOW
~~~

Never include:

~~~text
recipient=user@example.net
subject="Your order #12345"
jobId=mail-unique-per-message
~~~

Email addresses are PII; subjects can reveal customer details; `jobId` has very high cardinality. Those belong in authorized job-lookup systems or policy-compliant secure logs, **not metric labels**.

### Micrometer Example: Counting Rate Limiter Decisions

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class MailLimiterMetrics {
    private final MeterRegistry metrics;

    public MailLimiterMetrics(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    public void decision(
            String providerId,
            String lane,
            boolean allowed) {
        metrics.counter(
                "mail_rate_limit_decisions",
                "provider", providerId,
                "lane", lane,
                "result", allowed ? "granted" : "denied")
                .increment();
    }
}
~~~

`providerId` and `lane` must come from **fixed value sets**. Never let callers pass arbitrary emails, dynamic tokens, or individual campaign names into tags.

## 31. Alerts and Runbook When a Provider Nears Quota Exhaustion

Useful alerts tie directly to real impact:

- **Rate-limit denials climbing** while backlog age exceeds the lane's target.
- **Provider throttling climbing** after a config change or replica scale-up.
- **Daily budget running low** with many hours left until reset.
- **OTP backlog growing** while marketing consumes heavy quota.
- **Rate gate store failing**, halting all workers from acquiring permits.
- **High SMTP latency** saturating concurrency even without rate-limiter denials.
- **Sudden drop to zero submitted jobs** while the outbox keeps receiving new jobs.

### Runbook: Provider Starts Returning Throttling Errors

1. Identify which **provider/account/sender** is affected.
2. Separate error types: rate-related SMTP 4xx, network errors, auth failures, or daily quota.
3. Check actual **cluster-wide** send rate and other services sharing the account.
4. Check remaining quota and reset times in the provider console if available.
5. Inspect limiter config, replica count, recent deployments, and burst capacity.
6. Lower rates or pause low-priority lanes; protect critical emails.
7. Check whether retries/backoff are causing a thundering herd.
8. Keep jobs in the outbox; avoid dropping or repeatedly re-sending.
9. Track backlog age and ETA per lane.
10. Restore rates gradually once the provider stabilizes, and document root cause.

**Do not default to raising thread counts or SMTP connections.** When a provider is throttling, higher concurrency can trigger even more rejections.

### Dashboards Must Show Both Demand and Supply

Place side by side:

~~~text
Demand: incoming jobs/second
Supply: accepted SMTP submissions/second

If Demand > Supply over a sustained period:
    backlog will grow

If Demand < Supply:
    backlog has a chance to drain
~~~

When handling multiple email types, split by low-cardinality lanes so you can see whether priority emails are impacted.

## 32. Estimating Backlog Drain Time

Suppose:

- `B` jobs are waiting.
- Each job consumes an average of `c` quota units.
- Net rate remaining for this queue is `r` units/second.
- No new jobs arrive.

Ideal estimate:

\[
t_{\mathrm{drain}} \approx \frac{B\times c}{r}
\]

Example: `B = 30,000` emails, one recipient each, net rate 5 recipients/second:

\[
t_{\mathrm{drain}} \approx 6\,000\ \mathrm{s}
  \approx 100\ \mathrm{minutes}
\]

If new traffic arrives continuously at rate `a` while processing rate is `r` (assuming `r > a`), the backlog drains roughly at rate `r - a`:

\[
t_{\mathrm{drain}} \approx \frac{B\times c}{r-a}
\]

This formula is only a simplified model. If `r \le a`, the backlog **cannot drain sustainably** under steady conditions.

### Factors That Skew Estimates

- Daily quota exhausts and must wait for reset.
- Rate reserved for higher-priority lanes.
- Retries and SMTP errors consuming capacity.
- Large attachments or latency/connection limits.
- Varying recipient counts per message.
- Provider adjusting limits dynamically based on reputation.
- Multiple replicas and shared limiter policies.

Measure actual **accepted** throughput over a steady window; never use `maxPoolSize` or granted permit counts as actual throughput for ETAs.

### Deadlines for Critical Emails

A 5-minute OTP should not sit in a 30-minute backlog and then be sent. Jobs can store:

~~~text
created_at
available_at
expires_at
priority
notification_type
~~~

If `now > expires_at`, workers should mark the job expired per business rules rather than sending an invalidated code just because quota is free. For subscription emails, campaigns may have a different deadline or send window; not all email types should share one retry policy.

## 33. Testing Provider-Aware Rate Limiting

Test multiple layers, not merely whether `tryAcquire()` returns true or false:

| Test Layer | Scenario | Expected Result |
|---|---|---|
| Unit — token bucket | Burst at capacity | Never grants above capacity |
| Unit — refill | Fake time advances | Tokens refill accurately |
| Unit — cost | Message with 5 recipients | Deducts exactly 5 recipient units |
| Unit — invalid configuration | Rate <= 0, burst <= 0 | Fails fast |
| Unit — concurrency | Workers occupy all slots | Rejects extra in-flight work |
| Unit — multi-policy | One limit exhausted | Does not invoke SMTP |
| Unit — retries | SMTP throttle | Schedules retry with backoff |
| Unit — rejected before submit | Rate gate denies | Does not increment SMTP attempts |
| Unit — unknown outcome | Connection lost after `DATA` | Does not falsely mark safely failed |
| Integration — Redis/DB | N workers reserve same key | Never exceeds token/quota count |
| Integration — crash | Worker dies after claim | Job becomes processable again via lease |
| Integration — multi-replica | Multiple instances share account | Aggregate throughput stays within tested policy |
| Integration — daily quota | Near reset boundary | Accurate window accounting |
| Integration — failover | Provider A fails | Provider B used only per routing/permissions |
| System — backlog | Inbound rate > allowed rate | Jobs queue without loss |
| System — priority | Marketing batch + new OTP | OTP dispatched within SLA |

### Contention Tests on Distributed Stores

A test should simulate multiple workers concurrently requesting permits for the same quota key:

~~~text
capacity = 10
refill disabled for duration of test
100 parallel workers each request 1 token

Expected:
    exactly 10 successful reservations
    90 denied
    total charged <= 10
~~~

When running this test, inspect **state in the shared store**, not just call counts at each replica. If the limiter refills automatically over time, use a controlled clock/test window so execution timing does not skew results.

### Testing Concurrency Without Arbitrary Thread.sleep

Use `CountDownLatch`, test executors, and timeouts to hold simulated SMTP tasks in flight. Then verify configured slot limits are never exceeded and all slots are released when exceptions occur.

### Testing HTTP 429 Is Not Testing SMTP 4xx

If the adapter uses SMTP, simulate SMTP transport replies/thrown exceptions. If the adapter uses an HTTP API, mock HTTP `429` and `Retry-After`. Both protocols report errors differently; tests should never lump everything together as "429 SMTP."

## 34. Integration Testing with an SMTP Sink Simulating Limits

A local message-capturing SMTP sink (such as Mailpit or GreenMail) helps verify:

- The application only submits messages permitted by the gate.
- Queues retain jobs when the limiter denies.
- No more concurrent SMTP sends occur than the concurrency limit.
- Workers update states accurately after accepted/rejected outcomes.
- Messages are not duplicated when multiple workers claim jobs.

However, an SMTP sink may not enforce provider throttling policies by itself. To test quota errors, use an **SMTP test double** or mock server programmed to return scripted SMTP 4xx/5xx codes.

### Controlled Test Scenarios

~~~text
Scenario A: Provider accepts 3 per second
    -> rate gate caps at <= 3/s per test window

Scenario B: Provider replies 451 for transient throttle
    -> record RETRY, backoff, no immediate retry storm

Scenario C: Provider disconnects after DATA
    -> record UNKNOWN, do not claim exactly-once

Scenario D: Shared limiter unavailable
    -> job remains durable; no uncontrolled flood

Scenario E: 4 replicas, one shared provider account
    -> quota reservation aggregate correctly enforced
~~~

Never send real emails to production users to test quota breaches or induce thousands of throttling errors. Run these tests only in approved sandbox environments.

## 35. Common Anti-Patterns

### 35.1. Making Each Thread `sleep(1000)` as a 1/s Quota

Across multiple workers or replicas, total rate is no longer 1/s. Sleeping also ties up threads and slows shutdowns. Use a limiter scoped to the real quota and defer jobs durably.

### 35.2. Bounding Only ThreadPoolTaskExecutor

~~~java
executor.setMaxPoolSize(10);
~~~

This bounds local concurrency, **not** 10 messages/second, and not 10,000 recipients/day. You still need a rate gate and quota budgets.

### 35.3. One Local Token Bucket for the Entire Cluster

Local buckets are instantiated separately inside each JVM. As you scale out, aggregate throughput grows with replica count. For shared provider quotas, use a distributed limiter or a suitable coordinator.

### 35.4. Using Each Credential as a Quota Key When an Account Shares Limits

Two different credentials may still draw from the same organization quota. Learn the true scope and key by provider policy rather than assuming credentials are independent.

### 35.5. Treating Every `send(MimeMessage)` Call as One Recipient

A message with multiple `RCPT TO` addresses may consume multiple recipient quota units. Charge costs in the right unit using envelope recipient details.

### 35.6. Automatically Refunding Permits on Every Exception

If the client disconnects after the provider accepted, refunding the permit and retrying immediately can exceed quotas and cause duplicates. Distinguish pre-submission failures from `UNKNOWN` outcomes; define clear reservation semantics.

### 35.7. Immediately Retrying All SMTP 4xx Errors

~~~java
catch (MailSendException ex) {
    mailSender.send(message); // Immediate retry can cause an error storm.
}
~~~

Failing to classify 4xx, back off, or check quotas triggers thundering herds. Persist the job, classify errors, and schedule retries with jitter.

### 35.8. Treating 429 as an SMTP Code

`429 Too Many Requests` is an HTTP status code; SMTP uses protocol reply codes and optional enhanced status codes. Do not wire HTTP `Retry-After` parsers onto SMTP transport unless specifically supported by a provider.

### 35.9. Optimizing Only Messages/Second and Ignoring Daily Quotas

A continuously refilling bucket can still consume too many recipients over 24 hours. Enforce cycle budgets in the right units.

### 35.10. Using Fixed Calendar Days for Rolling 24h Limits

Two bursts right before and after midnight reset can breach a rolling quota. Pick algorithms matching the provider's real policy.

### 35.11. Claiming the Whole Outbox into RAM When Sending Only a Few Emails/Second

Queues explode, leases expire, other workers reclaim jobs, and tracking which emails actually sent becomes messy. Claim batches matching capacity, keep backlogs durable, and apply backpressure.

### 35.12. Treating `@Async` as a No-Mail-Loss Guarantee

Executor queues live in RAM; restarts lose tasks. Use a transactional outbox or broker when durable delivery intents are required.

### 35.13. Sending SMTP Inside Transactions Holding Quota Row Locks

Holding database locks across slow networks causes contention and deadlock risks. Reserve/update state in short transactions; send outside transactions.

### 35.14. Letting Marketing Burn Security Quotas

A massive campaign can stall OTPs and password resets. Separate lanes, enforce priorities/fairness, and protect budgets where policy allows.

### 35.15. Failing Over to Another Provider on Every Timeout

`UNKNOWN` outcomes can cause duplicates; provider B has different senders/DKIM/quotas; failover must never be used to evade anti-abuse restrictions.

### 35.16. Failing to Monitor Rate Limiter Denials

Zero SMTP errors does not prove the system is healthy. When limiters deny and backlogs grow, alert on job age and SLAs.

### 35.17. Logging Raw SMTP Exceptions or Recipients to Debug

Providers may echo addresses or SMTP content. Log `jobId`, `providerId`, status class, sanitized `errorCode`, and attempt count; protect recipient data.

### 35.18. Setting Huge Token Capacity to "Avoid Queues"

High bursts can trip provider rate windows even when average rates are compliant. Size capacity for allowed burst allowances, not as an excuse to hide queue delays.

### 35.19. Limiting Only from the Spring App When Other Systems Share the Account

If a legacy batch job or provider console also sends via the same account, in-app quota accounting is insufficient. Coordinate at a shared source or reserve headroom, monitor provider usage, and restrict shared credentials.

### 35.20. Ignoring Policy Checks at Send Time

Enqueued jobs can expire, users can revoke consent, or tenants can change sender policies. Before acquiring permits and submitting over SMTP, re-check required business conditions; never waste quota on mail no longer permitted to send.

## 36. Step-by-Step Provider-Aware Rate Limiting Rollout

A practical roadmap:

1. **Inventory providers and identities:** SMTP/API endpoints, accounts, credentials, sender domains, and co-tenant apps.
2. **Collect official quotas:** message/recipient/rate/concurrency/window/reset rules and throttling behavior.
3. **Choose cost units:** per message and per recipient per policy.
4. **Define SLAs:** OTP/transactional/batch deadlines and backlog age per lane.
5. **Pick safe caps:** rate caps below published quotas where headroom is needed.
6. **Design a durable queue:** outbox/broker holding jobs when quotas exhaust or providers fail.
7. **Build provider-aware admission:** daily budgets, rate buckets, and concurrency in matching units and scopes.
8. **Choose distributed state:** Redis atomic limiters, database reservations, or a centralized dispatcher per system scale.
9. **Define deny behavior:** skip SMTP, do not increment SMTP attempts, defer job to eligible time.
10. **Define retries:** separate throttling, temporary, permanent, and `UNKNOWN`; backoff with jitter and deadlines.
11. **Allocate fairness:** protect critical flows without starving other lanes indefinitely.
12. **Add metrics/alerts:** permits, denials, provider throttles, remaining quota, accepted throughput, and backlog age.
13. **Test concurrency:** multiple replicas competing for the same quota, store failovers, and crash windows.
14. **Roll out gradually:** small/sandbox traffic, check error rates and throughput, then scale up.
15. **Write runbooks:** quota exhaustion, provider slowdowns, retry storms, global store outages, and campaign backlogs.
16. **Review periodically:** when changing providers/plans, scaling replicas, adding apps to an account, or changing email types.

### Policy Documentation Template

~~~yaml
# Design documentation example, not official quotas.
provider: PRIMARY
quotaScope: provider-account
rateUnit: recipients_per_second
burstCapacity: 12
refillPerSecond: 4
maxConcurrentSubmissions: 3
dailyQuotaUnit: recipients
dailyBudget: 15000
quotaWindow: provider-defined
priorities:
  - SECURITY
  - TRANSACTIONAL
  - SUBSCRIPTION
onRateDenied: defer_outbox
onLimiterUnavailable: fail_closed
retryPolicy: exponential_backoff_with_jitter
~~~

This is an illustrative policy document, not a Spring Boot auto-configuration schema. Every system must map these fields to its implementation and verify against the real provider.

## 37. Frequently Asked Questions

**Can rate limiting be configured solely via `spring.mail.*`?** Spring Mail properties primarily configure the sender/SMTP session and transport. Provider-aware rate limiting is the job of an integrated dispatcher/rate limiter or coordination service; it does not appear automatically when setting username/password.

**Can I set `maxPoolSize=5` to cap sending at 5 emails/second?** No. Max pool size caps concurrent tasks in an executor, not per-second throughput.

**Is one bucket per Spring Boot instance enough?** Only if quotas apply independently per instance or cluster-wide partitioning is safely enforced. For shared provider-account quotas, cluster-wide coordination is needed.

**Can I limit by SMTP host?** Only when that matches the real quota scope. Multiple credentials/senders sharing a host may have independent or shared quotas depending on the provider.

**Do providers usually limit messages or recipients?** Depends on the service and plan. Both may apply alongside daily/connection quotas. Read your actual account policy rather than assuming one message always equals one recipient.

**Do rate limits and daily quotas replace each other?** No. Rate caps speed; daily quotas cap total consumption within a window.

**Is a larger token bucket capacity always better?** Only when the provider permits large bursts. High capacity can cause spikes that breach policy even with a low refill rate.

**Should workers wait with `Thread.sleep` when tokens run out?** Never tie up mail workers for long stretches. Deferring jobs in a queue/outbox to release resources is far better.

**Does every application need Redis?** No. A single-process app with low volume can use a local limiter. Across multiple replicas, shared quotas, or multiple apps, proper coordination is required; Redis is only one option.

**If Redis fails, should we send without limits?** No. Choose fail closed or an approved bounded fallback, especially when providers enforce strict quotas/anti-abuse rules.

**Does SMTP `421` always mean rate limiting?** No. `421` indicates the service is temporarily unavailable, which can have many causes. Use context, reply details, and provider policies to classify.

**Does SMTP have `Retry-After` like HTTP 429?** SMTP has no universal HTTP-style `Retry-After` header. For HTTP email APIs, follow API/provider guidance; for SMTP, base retry delays on reply codes, state, and policy.

**If one email has 20 recipients, how many tokens are deducted?** Depends on the quota: 1 token if message-based, 20 if recipient-based, or other costs defined by the provider. You may need permits from multiple distinct buckets.

**Should tokens be refunded when an SMTP call throws an exception?** Only with solid proof that quota was not consumed and when the reservation mechanism supports it. On uncertain outcomes, wrongly refunding permits risks quota breaches and duplicates.

**Does rate limiting lose emails?** Not when send intents are persisted durably and workers defer cleanly. Pure RAM queues and fire-and-forget `@Async` lack that guarantee.

**How do I prevent campaigns from slowing down OTPs?** Use priorities/fairness, budget reservations, and separate lanes/accounts if the provider allows, plus deadline alerts.

**Can rate automatically scale up when no throttling appears?** Yes under a bounded adaptive policy, provided you keep headroom, require sufficient load evidence, and never exceed the provider's hard cap.

**Should I switch providers on every timeout?** No. A timeout after `DATA` can be an `UNKNOWN` outcome; immediate retry/failover can duplicate emails. Classify the failure point and apply reconciliation policies.

**When a provider raises our quota, does the app automatically speed up?** Only if there is a safe, consistent policy update mechanism. Local beans built at startup do not reload just because the provider console changed.

**How do I calculate backlog ETA?** Use current backlog and net accepted throughput after subtracting new incoming traffic, retries, and quota reserved for other lanes. Never use thread count as an ETA.

**Does rate limiting improve deliverability?** Smoothing spikes and reducing provider throttling stabilizes operations, yet deliverability still depends on consent, content, authentication, reputation, bounces/complaints, and recipient policies.

## 38. Summary

In **Spring Framework Mail**, provider-aware rate limiting is a problem of **coordinating resources and send states**, not merely adding `Thread.sleep` or shrinking `ThreadPoolTaskExecutor` threads.

A resilient system needs:

1. **Accurate quota understanding:** message vs. recipient units, rate/window, daily budgets, concurrency, and provider/account/domain scope.
2. **Controlled permit issuance:** token buckets/sliding windows and concurrency gates in the exact unit and scope.
3. **Cluster-wide coordination:** a local limiter does not suffice when multiple replicas share an account.
4. **Durable job retention:** when permits are unavailable or providers fail, defer in an outbox/broker rather than losing emails or sleeping workers.
5. **SMTP outcome classification:** throttled, permanent, temporary, accepted, and `UNKNOWN`; retry with backoff/jitter and prevent duplicates.
6. **Protecting critical flows:** prioritize OTP/transactional traffic, fairness, and deadlines.
7. **Observing demand and capacity:** permits denied, remaining quota, provider throttles, accepted throughput, and backlog age.

General architecture diagram:

~~~text
Business events / Requests
           |
           v
  Transactional Mail Outbox
           |
           v
    Mail Dispatcher
           |
           +-- Validate eligibility / expiration
           +-- Choose allowed provider/account
           +-- Reserve shared quota & rate
           +-- Acquire concurrency slot
           |
           v
      JavaMailSender
           |
           v
      SMTP Provider
           |
      +----+-----+
      |          |
   Accepted   Rejected/Unknown
      |          |
      v          v
  SUBMITTED   Retry/DEAD/UNKNOWN
                 |
                 v
            Durable Outbox
~~~

**Final principle:** let provider quotas govern sending pace, let durable queues hold waiting requests, and let the application track outcomes accurately. When these layers are designed consistently, the system sends emails smoothly, avoids unnecessary throttling, protects critical notifications, and scales load with real capacity rather than raw thread counts.
