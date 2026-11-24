# Account and Tenant Rate Limiters

## 1. The production problem: who gets how much sending capacity?

In a **Spring Framework Mail** application, `JavaMailSender.send(...)` can be called concurrently from HTTP requests, schedulers, event consumers, or outbox workers. When a single user tests sending a few emails, rate limits seem unimportant. Yet in a SaaS service serving hundreds of **tenants** or a system using multiple **mail-sending accounts**, one customer running a large campaign can consume all SMTP resources and delay other customers' transactional emails.

Suppose an application has:

- Tenant A sending 20,000 marketing emails in one hour.
- Tenant B needing only a few dozen invoice emails.
- Tenant C with account-verification emails that must go out within seconds.
- All sharing one SMTP provider account with a single aggregate limit.

If workers pull jobs FIFO and add threads to clear the backlog, the following can happen:

1. The provider temporarily rejects sends due to exceeding rate limits.
2. Tenant A burns through the shared quota before B or C get processed.
3. A's retries add extra load, causing a **retry storm**.
4. An account gets suspended or loses reputation due to an abnormal spike.
5. Workers get tied up waiting on quotas; critical emails sit in the queue.
6. Autoscaling adds pods, pushing SMTP request rates up faster than expected.
7. Jobs get duplicated when claims expire while the provider already accepted the email.

An **account or tenant rate limiter** is an admission-control component: it decides whether a job may begin SMTP submission right now or must wait, based on quotas for the **provider account**, **tenant**, **sender identity**, and sometimes **notification type**.

~~~text
HTTP / Business events / Batch
              |
              v
       Durable Mail Outbox
              |
              v
         Dispatcher
              |
       Tenant authorization
              |
              v
      Hierarchical rate gate
       /       |         \
      v        v          v
 Global     Account     Tenant
 budget     bucket      bucket
      \        |         /
       +-------+--------+
               |
               v
    SMTP concurrency control
               |
               v
        JavaMailSender
               |
               v
         SMTP provider
~~~

In this lesson, a "rate limiter" is presented as a **production design pattern**, not merely a `sleep(1000)` helper. It must behave correctly across multiple instances, accounts, tenants, and error states without losing emails.

## 2. Distinguishing accounts, tenants, senders, and quota scopes

Do not use these concepts interchangeably:

| Entity | Role | Illustrative example |
|---|---|---|
| **Tenant** | SaaS customer organization | `tenant-42` |
| **Provider** | Service supplying SMTP/API mail delivery | `PRIMARY_SMTP` |
| **Provider account** | Provider account/organization/sending pool | `primary-prod-account` |
| **Credential** | Username/password, OAuth token, or API key for auth | `orders-key-v3` |
| **Sender identity** | Permitted `From` domain or address | `orders@example.test` |
| **Quota scope** | Scope where the provider or app actually enforces limits | `provider-account:primary-prod` |
| **Notification lane** | Traffic class with distinct priority needs | `SECURITY`, `TRANSACTIONAL`, `BULK` |

Example of one account with two credentials:

~~~text
SMTP Provider A
  |
  +-- Organization/account PROD
         |
         +-- credential "orders"  -> tenant A
         +-- credential "support" -> tenant B
         |
         +-- shared account quota
~~~

If the provider meters quotas per organization, creating two completely independent token buckets per credential can **breach the shared limit**. Conversely, if Tenant A and Tenant B use two independent accounts, a single global counter lets A accidentally starve B's capacity.

### One job can face multiple limits simultaneously

Suppose:

~~~text
Provider account limit:  20 recipient/second
Tenant A policy:          6 recipient/second
Tenant B policy:          4 recipient/second
Transactional lane:      reserved capacity when needed
SMTP concurrent sends:    5 operations
Daily account quota:   50,000 recipients/day
~~~

These numbers are **for explaining the design only**, not official limits of any provider.

A Tenant A job can submit only when:

~~~text
Provider account rate permit
  AND tenant A rate permit
  AND account daily quota available
  AND SMTP concurrency slot available
  AND sender/tenant permission valid
~~~

Crucially, tenant quotas cannot create extra provider quota; they only **partition** and protect available sending capacity.

## 3. Rate, burst, concurrency, and daily quota are separate axes

| Limit | Common units | Question |
|---|---|---|
| Rate | messages/s, recipients/s, requests/min | How many units per time interval? |
| Burst | tokens or instantaneous events | How fast can sends cluster over a short window? |
| Concurrency | in-flight SMTP submissions or connections | How many network operations are active at once? |
| Daily quota | recipients/day, messages/rolling 24h | How much total volume remains in the cycle? |
| Per-message cap | `RCPT TO`/message, MIME bytes | How many recipients or bytes can one message carry? |
| Application tenant budget | units/tenant/window | How much is a tenant permitted to consume? |

**Thread limits are not rate limits.** For example:

~~~java
executor.setMaxPoolSize(8);
~~~

only caps concurrent tasks inside the executor; if SMTP replies very quickly, eight threads can still fire hundreds of requests per second. Conversely, if each call takes several seconds, the rate gate may still have permits while concurrency is maxed out.

A continuously refilling token bucket also **does not replace daily quotas**: it can obey every per-second check while still exceeding the allowed recipients in 24 hours.

### Rate by message or by recipient?

One `send(MimeMessage)` call can carry multiple envelope recipients:

~~~text
MAIL FROM:<orders@example.test>
RCPT TO:<a@example.test>
RCPT TO:<b@example.test>
RCPT TO:<c@example.test>
DATA
...
~~~

That can be **1 message yet 3 recipients**. When the provider meters by recipient, the cost is 3; when by message, cost is 1; when both apply, use two buckets/limiters with distinct units. Bcc addresses also appear in the SMTP envelope even though they do not appear in headers seen by other recipients.

Never automatically refund reserved quota on every `MailException`: the provider may have accounted for or partially accepted the submission, especially if the connection dropped after DATA.

## 4. Setting goals: protect providers and ensure tenant fairness

Two related yet distinct requirements:

**Provider protection:** total submissions through an account stay within the provider's safe quota.

**Tenant fairness:** a tenant sending massive batches cannot monopolize capacity and cause *starvation* for other tenants.

Suppose an account has safe throughput of 12 recipients/second across 3 tenants:

~~~text
Account bucket = 12 recipients/second
                |
                +-- Tenant A: soft cap 5/s
                +-- Tenant B: soft cap 5/s
                +-- Tenant C: soft cap 5/s
~~~

The sum of soft caps is 15/s, while the account allows only 12/s. That is **not wrong if tenant budgets are upper caps and account admission still enforces the 12/s total**. It becomes wrong if the dispatcher grants each tenant its full cap independently while ignoring the account bucket.

Operational goals:

- Never exceed provider contractual quotas/limits.
- Never let one tenant clog the entire outbox.
- Give security/transactional emails appropriate priority.
- Bound active SMTP connections and outbound tasks.
- Never drop emails when permits are unavailable.
- Prevent retries from causing request storms.
- Observe denial reasons by account and tenant.
- Scale replicas up or down without breaking aggregate limits.

### Fairness does not always mean equal shares

Some tenants have higher contracted throughput. You can use *weighted fair scheduling* so higher-tier tenants receive larger shares than basic tenants. Even so, shared quotas and critical-email SLAs remain top constraints. Never rely on a single FIFO queue assuming "first come, first served" is always fair.

## 5. Choosing quota keys by permitted scope

A key design:

~~~text
mail:rate:provider-account:primary-prod
mail:rate:tenant:tenant-42
mail:rate:sender:orders-profile
mail:daily:provider-account:primary-prod
mail:concurrency:primary-prod
~~~

All keys are **normalized internal IDs**, never raw SMTP passwords, recipient addresses, or arbitrary strings passed by API clients.

Each job maps to a quota tuple:

~~~text
jobId             = opaque UUID
tenantId          = tenant-42
senderProfileId   = ORDERS
providerId        = PRIMARY
providerAccountId = primary-prod
notificationType  = ORDER_RECEIPT
quotaCost         = 1 recipient
~~~

**The server must derive `tenantId` from the authentication/authorization context**, never trusting a `tenantId` field in a request body that would let a caller spend another tenant's budget.

### Key by scope, not secret version

If credentials rotate from `key-v3` to `key-v4` on the same provider account, the account quota usually does not reset. Keying quotas by credential version easily opens a fresh full bucket after rotation. Quota keys must stay stable with contractual scope.

### Should you limit by recipient domain?

Sometimes yes: providers or receiving domains may defer spikes aimed at one domain. However, per-email-address buckets create unnecessary PII/high cardinality. If enforcing recipient-domain policies, use controlled configured domains/groups and recognize that domains can still reveal traffic patterns.

## 6. Recommended architecture: durable outbox first, rate gate right before SMTP

~~~mermaid
flowchart TD
    A[Business transaction] --> B[Write mail intent to outbox]
    B --> C[Commit]
    C --> D[Scheduled dispatcher]
    D --> E[Claim due jobs with lease]
    E --> F[Check tenant and sender eligibility]
    F --> G{Hierarchical quota available?}
    G -- No --> H[Defer via next_attempt_at]
    H --> D
    G -- Yes --> I{SMTP concurrency slot?}
    I -- No --> H
    I -- Yes --> J[Create attempt and submit]
    J --> K{Submission outcome}
    K -- Accepted --> L[SUBMITTED]
    K -- Temporary rejection --> M[RETRY with backoff]
    K -- Permanent rejection --> N[FAILED]
    K -- Unknown --> O[UNKNOWN and reconcile]
    M --> D
~~~

Why store emails in an outbox?

- When the limiter denies, the job stays durably persisted.
- On service restarts, schedulers pick up due jobs again.
- Jobs can be canceled, rescheduled, or expired per policy.
- Workers do not tie up thousands of threads sleeping on quotas.
- Tenant fairness policy is decoupled from SMTP execution.
- Backlogs can be measured by tenant, account, and email type.

Still, **an outbox does not guarantee exactly-once SMTP delivery**. A worker can crash after server acceptance yet before writing `SUBMITTED`; unconditionally retrying when the lease expires creates duplicates. Pair it with `UNKNOWN`/reconciliation and business idempotency.

## 7. Token buckets: keeping average rates and bursts bounded

A token bucket fits well when a provider permits bounded **short-term bursts**:

1. Bucket holds at most `capacity` tokens.
2. Tokens refill at `refillTokensPerSecond`.
3. A job requests tokens equal to the submission cost.
4. If enough tokens exist, deduct them and grant the permit.
5. If insufficient, do not submit; return a suggested wait time so the worker defers.

Example:

~~~text
capacity = 8 tokens
refill   = 2 tokens/s
cost     = 1 token/message

t=0: 8 tokens available -> can burst up to 8 messages
t=0: after 8 submits -> 0 tokens
t=0.5s: +1 token
t=1.0s: +2 tokens total if unused
~~~

Long-term average rate is capped by refill, while peak burst depends on capacity. **Do not configure a large capacity if the provider forbids bursts**, because even with a valid average, clustered sends still trigger throttling.

### Cost larger than capacity

When metering by recipient, a message with 20 recipients hits a bucket with capacity 8:

~~~text
cost = 20
capacity = 8
~~~

The job will **never acquire enough tokens** if code simply waits. You must:

- Reject or split valid messages into smaller jobs/recipient groups per policy.
- Or size capacity to accommodate max valid cost while still respecting real burst policies.
- Distinguish message rate buckets (cost 1) from recipient rate buckets (cost 20).

### Do token buckets fit rolling-day quotas?

Not completely. Token buckets bound long-term average rate, yet do not accurately meter a hard cap like 50,000 recipients in a **rolling 24-hour** window. Add dedicated daily/rolling-window budget accounting.

## 8. Single-JVM Java token bucket: illustrating the algorithm

This example is **for a single JVM** and cannot enforce cluster-wide limits when multiple Spring Boot replicas share an account quota.

~~~java
import java.time.Duration;
import java.util.function.LongSupplier;

public record RateDecision(
        boolean allowed,
        Duration retryAfter) {
    public static RateDecision granted() {
        return new RateDecision(true, Duration.ZERO);
    }
    public static RateDecision denied(Duration wait) {
        return new RateDecision(false, wait);
    }
}

public final class LocalTokenBucket {
    private final int capacity;
    private final double refillPerSecond;
    private final LongSupplier ticker;
    private double tokens;
    private long updatedAtNanos;

    public LocalTokenBucket(
            int capacity, double refillPerSecond,
            LongSupplier ticker) {
        if (capacity <= 0
                || !Double.isFinite(refillPerSecond)
                || refillPerSecond <= 0) {
            throw new IllegalArgumentException(
                    "Invalid token bucket policy");
        }
        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
        this.ticker = java.util.Objects.requireNonNull(ticker);
        this.tokens = capacity;
        this.updatedAtNanos = ticker.getAsLong();
    }

    public synchronized RateDecision tryAcquire(int cost) {
        if (cost <= 0 || cost > capacity) {
            throw new IllegalArgumentException(
                    "Invalid token cost");
        }

        long now = ticker.getAsLong();
        long elapsedNanos = Math.max(0, now - updatedAtNanos);
        updatedAtNanos = now;

        tokens = Math.min(
                capacity,
                tokens + (elapsedNanos / 1_000_000_000d)
                        * refillPerSecond);

        if (tokens >= cost) {
            tokens -= cost;
            return RateDecision.granted();
        }

        double missing = cost - tokens;
        long waitNanos = (long) Math.ceil(
                missing / refillPerSecond * 1_000_000_000d);
        return RateDecision.denied(
                Duration.ofNanos(waitNanos));
    }
}
~~~

Usage example:

~~~java
LocalTokenBucket tenantBucket = new LocalTokenBucket(
        10, 3.0, System::nanoTime);

RateDecision rate = tenantBucket.tryAcquire(1);
if (rate.allowed()) {
    // Only one of several conditions is satisfied.
    // Still need to check account quota and concurrency.
} else {
    // Persist next_attempt_at in the database.
    Duration delay = rate.retryAfter();
}
~~~

Characteristics:

- `synchronized` prevents two threads in the **same process** from double-spending a token.
- `System.nanoTime()` measures elapsed time reliably without wall-clock jumps.
- Non-blocking for workers: callers receive `retryAfter` and defer the job.
- After restart, buckets refill to full capacity, potentially creating bursts unless guarded by policy.
- Each replica keeps separate state, unable to enforce aggregate account rates.
- Lacks daily quotas, per-provider costs, and multi-bucket atomic admission.

Therefore **never present a local bucket as a multi-replica production solution**. It is useful for explaining the algorithm or single-instance apps under controlled deployment assumptions.

## 9. Hierarchical limiters: grant all conditions or none

A Tenant A job must pass both the account bucket and tenant bucket. If you write:

~~~java
if (accountBucket.tryAcquire(1).allowed()
        && tenantBucket.tryAcquire(1).allowed()) {
    sender.send(message);
}
~~~

then when the account bucket allows yet the tenant bucket denies, **the account lost a token without sending**. Under heavy load, repeated partial grants leak internal budgets and cause starvation.

This does not necessarily breach provider quotas, yet prevents using granted capacity. Worse, if token-refund logic is buggy or racy, the system can exceed quotas.

A sound design for buckets in the same store:

~~~text
ATOMIC reserve(account, tenant, costs):
  refill account bucket
  refill tenant bucket
  check account has enough
  check tenant has enough
  if either fails:
      grant none
      return denied + next eligible time
  else:
      subtract from both
      return granted
~~~

Extend the same principle across multiple levels (account, tenant, sender, lane). Never update separate keys using non-atomic Redis `GET`/`SET`.

### When account quota counts recipients and tenant quota counts messages

Costs must match each dimension:

~~~text
Account recipient bucket: cost = 5
Tenant message bucket:    cost = 1
Sender concurrency:       cost = 1 in-flight slot
~~~

**A single scalar cost does not fit every quota.** Model it explicitly:

~~~java
public record MailQuotaCost(
        int messages,
        int recipients,
        long mimeBytes) {
    public MailQuotaCost {
        if (messages <= 0 || recipients <= 0 || mimeBytes < 0) {
            throw new IllegalArgumentException(
                    "Invalid mail quota cost");
        }
    }
}
~~~

Compute costs from **actual SMTP envelope recipients** and provider policies, not merely API call counts or `To` headers.

## 10. Why multi-replica deployments require shared admission control

Suppose a provider account allows 10 messages/second:

~~~text
             Shared provider account 10/s
                         ^
                         |
       +-----------+-----+-----------+
       |           |                 |
    Pod A        Pod B             Pod C
  local 10/s   local 10/s        local 10/s

Potential aggregate = 30/s, not 10/s.
~~~

Options:

| Design | Best suited when | Trade-offs |
|---|---|---|
| Single dispatcher per account | Moderate throughput, simplicity desired | Needs HA and avoiding single points of failure |
| Redis atomic buckets | Many replicas, fast rate admission | Shared store, TTL/failover/consistency |
| PostgreSQL quota reservations | DB available and moderate throughput | Contention on counter rows |
| Provider-native throttling | Provider acts as last line of defense | Harder to predict backlogs, retries, and SLAs |
| Static per-pod partitioning | Fixed replica count, predictable load | Breaks during autoscaling, rolling deploys, uneven load |

Merely using Redis as shared memory does not make grants race-free. Doing `GET`, computing in Java, and calling `SET` still races across pods; atomic operations are required.

### Rolling deployments

Even a service normally running 2 replicas can temporarily run 3–4 replicas during a deploy. Static per-pod quota splits can exceed limits whenever instance counts spike temporarily.

### Other applications sharing the same SMTP account

If a legacy service or marketing tool also sends through that account, the Spring app's limiter **cannot see total usage**. Coordinate account-wide where possible, or reserve headroom and reconcile against provider dashboards/usage APIs. Never assume all submissions flow through your dispatcher.

## 11. Redis distributed limiters: data and atomicity

In Redis, store each token bucket's state as:

~~~text
key: mail:rate:{primary-prod}:account
  tokens = 7.0
  updated_at = 1794480000.123

key: mail:rate:{primary-prod}:tenant:tenant-42
  tokens = 2.0
  updated_at = 1794480000.123
~~~

`{primary-prod}` is a Redis Cluster **hash tag**, placing keys with the same tag in the same hash slot; this is required for a Lua script accessing multiple keys in Redis Cluster. It is a logical account ID, not a real username/password.

An atomic reservation must:

1. Read time from a shared source (e.g., Redis server time).
2. Load each bucket's state.
3. Refill based on elapsed time.
4. Check whether **all** buckets have sufficient tokens.
5. If any bucket is short, **deduct none**.
6. If all suffice, deduct and persist state for all.
7. Return `granted` or a suggested delay.

### TTL must not be shorter than full refill time

Suppose a bucket has capacity 100 and refills at 1/s. Once drained, it takes 100 seconds to refill completely. If the Redis key expires after 10 seconds and re-initializes with 100 tokens, the application allows bursts prematurely. Set TTL to **longest full-refill time + safety margin** (or avoid expiration policies that dangerously forget active state).

### Never fail open indefinitely when Redis disconnects

If the limiter fails due to timeouts or a Redis outage, never treat that as an automatic permit. Especially with many replicas, a 5/s local fallback across 100 pods still hits 500/s cluster-wide. Choose fail-closed or a pre-approved emergency mode with a **cluster-wide** budget.

## 12. Lua example: atomically reserving account and tenant buckets

Below is an **illustrative implementation** for Redis (account + tenant token buckets). It assumes both keys share a hash slot, a two-tier policy, and pre-computed costs. Production requires policy versioning, TTLs, Redis failover handling, and additional quota dimensions.

Inputs:

~~~text
KEYS[1] = account bucket key
KEYS[2] = tenant bucket key

ARGV[1] = account capacity
ARGV[2] = account refill tokens/s
ARGV[3] = account cost
ARGV[4] = tenant capacity
ARGV[5] = tenant refill tokens/s
ARGV[6] = tenant cost
ARGV[7] = TTL milliseconds (long enough for full refill)
~~~

~~~lua
-- Atomic reservation for two token buckets.
-- Return [1, 0] if granted.
-- Return [0, waitMillis] if denied.
-- Return [-1, 0] for invalid cost/capacity/rate.

local capA    = tonumber(ARGV[1])
local rateA   = tonumber(ARGV[2])
local costA   = tonumber(ARGV[3])
local capT    = tonumber(ARGV[4])
local rateT   = tonumber(ARGV[5])
local costT   = tonumber(ARGV[6])
local ttlMs   = tonumber(ARGV[7])

if not capA or not rateA or not costA
   or not capT or not rateT or not costT or not ttlMs
   or capA <= 0 or capT <= 0
   or rateA <= 0 or rateT <= 0
   or costA <= 0 or costT <= 0
   or costA > capA or costT > capT
   or ttlMs <= 0 then
    return {-1, 0}
end

local redisTime = redis.call("TIME")
local now = tonumber(redisTime[1])
          + tonumber(redisTime[2]) / 1000000

local function currentState(key, capacity, refill)
    local fields = redis.call("HMGET",
            key, "tokens", "updated_at")
    local tokens = tonumber(fields[1])
    local previous = tonumber(fields[2])

    if not tokens or not previous then
        return capacity
    end

    local elapsed = math.max(0, now - previous)
    return math.min(capacity, tokens + elapsed * refill)
end

local tokensA = currentState(KEYS[1], capA, rateA)
local tokensT = currentState(KEYS[2], capT, rateT)

local accountWait = math.max(0, costA - tokensA) / rateA
local tenantWait  = math.max(0, costT - tokensT) / rateT

if accountWait > 0 or tenantWait > 0 then
    -- Read-only deny: no bucket is consumed.
    -- The next request can recalculate refill from saved state.
    return {0, math.ceil(
            math.max(accountWait, tenantWait) * 1000)}
end

redis.call("HSET", KEYS[1],
        "tokens", tokensA - costA,
        "updated_at", now)
redis.call("PEXPIRE", KEYS[1], ttlMs)

redis.call("HSET", KEYS[2],
        "tokens", tokensT - costT,
        "updated_at", now)
redis.call("PEXPIRE", KEYS[2], ttlMs)

return {1, 0}
~~~

### Key details explained

- A Lua script executes **atomically** in Redis for valid keys within the same execution context; two workers cannot read the same token and both spend it.
- If the tenant lacks tokens, the account bucket **is not partially deducted**.
- If either bucket is short, return the maximum wait across both, since **both** must have enough.
- The returned delay is an estimate at execution time; before SMTP submission, **acquire a fresh permit** rather than assuming expiry of the delay grants permission.
- `cost > capacity` returns a config/parameter error rather than waiting forever.
- On denial, existing state stays intact; subsequent requests compute refills from saved `updated_at`.
- TTL must exceed the full-refill time under idle conditions plus a safety margin; never let keys vanish while budgets still need protection.

### Scope of the illustrative script

This script **does not solve** daily quotas, atomic policy reloads, abrupt dynamic capacity reductions, per-recipient-domain buckets, global tenant quotas spanning multiple accounts, global concurrency slots, or Redis failover durability.

If one tenant uses **multiple provider accounts** under one tenant-wide quota, the global tenant key and account keys may land in **different Redis Cluster hash slots**. Never assume a script can atomically update arbitrary hash slots. Options:

1. Colocate keys in the same slot (if scale permits).
2. Use a coordination service or transactional database with atomic boundaries.
3. Split quotas into bounded reservations/allocations.
4. Accept conservative accounting paired with pre-designed reconciliation.

Never run multiple independent scripts and assume they form a distributed transaction.

## 13. Calling RedisScript from Spring Data Redis

A Spring Data Redis example showing how the adapter invokes the script and maps results to application types.

~~~java
import java.time.Duration;

public record QuotaPermit(
        boolean granted,
        Duration retryAfter) {

    public static QuotaPermit allow() {
        return new QuotaPermit(true, Duration.ZERO);
    }

    public static QuotaPermit defer(Duration delay) {
        return new QuotaPermit(false, delay);
    }
}

public interface AccountTenantRateGate {
    QuotaPermit reserve(
            String providerAccountId,
            String tenantId,
            int accountCost,
            int tenantCost);
}
~~~

Conceptual Redis adapter class:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

public final class RedisAccountTenantRateGate
        implements AccountTenantRateGate {

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<List> script;
    private final MailQuotaPolicyRegistry policies;

    public RedisAccountTenantRateGate(
            StringRedisTemplate redis,
            DefaultRedisScript<List> script,
            MailQuotaPolicyRegistry policies) {
        this.redis = redis;
        this.script = script;
        this.policies = policies;
    }

    @Override
    public QuotaPermit reserve(
            String accountId, String tenantId,
            int accountCost, int tenantCost) {

        var p = policies.forAccountAndTenant(
                accountId, tenantId);

        // Same Redis Cluster hash tag for these two keys.
        String tag = "{" + p.accountScopeId() + "}";
        String accountKey = "mail:rate:" + tag + ":account";
        String tenantKey = "mail:rate:" + tag
                + ":tenant:" + p.tenantScopeId();

        List<?> result = redis.execute(
                script,
                List.of(accountKey, tenantKey),
                Integer.toString(p.accountBurstCapacity()),
                Double.toString(p.accountRefillPerSecond()),
                Integer.toString(accountCost),
                Integer.toString(p.tenantBurstCapacity()),
                Double.toString(p.tenantRefillPerSecond()),
                Integer.toString(tenantCost),
                Long.toString(p.ttl().toMillis()));

        if (result == null || result.size() != 2) {
            throw new IllegalStateException(
                    "Rate gate returned an invalid response");
        }

        long code = ((Number) result.get(0)).longValue();
        long waitMs = ((Number) result.get(1)).longValue();
        if (code == 1) {
            return QuotaPermit.allow();
        }
        if (code == 0 && waitMs >= 0) {
            return QuotaPermit.defer(
                    Duration.ofMillis(waitMs));
        }

        throw new IllegalStateException(
                "Invalid rate gate policy or script error");
    }
}
~~~

`MailQuotaPolicyRegistry` and policy fields are **application-built** abstractions. To use this class, create a `DefaultRedisScript<List>` with the Lua script above, call `setResultType(List.class)`, and choose appropriate Redis serializers. Verify result deserialization with your Spring Data Redis/Jedis/Lettuce version; never copy a fragment lacking bean registration and treat it as a complete app.

### Never trust arbitrary external accountId/tenantId strings

`policies.forAccountAndTenant(...)` must validate the tenant → account mapping and return **normalized IDs**, never concatenating raw request inputs into Redis keys (risking key-space injection and high cardinality). Redis keys should contain only logical IDs issued by identity/policy stores.

### Returning rate-gate errors differs from returning DENIED

If Redis times out, the script errors, or the result is invalid, never return `QuotaPermit.defer(Duration.ZERO)` or `allow()`. That is a **quota-system failure** and must fail closed (or enter an approved fallback), retain the job, and alert. `DENIED` is a normal out-of-quota response, distinct from `ERROR`.

## 14. Daily quotas: separate cycle counters

If a provider enforces both:

~~~text
10 messages/second
20,000 recipients/rolling 24h
~~~

you need **at least two mechanisms**:

1. Token bucket or sliding window for messages/second.
2. Accurate rolling-24h budget accounting for recipients.

A fixed calendar-day counter does not replace a rolling window:

~~~text
23:59 -> sends nearly entire quota
00:01 -> app counter resets to 0
~~~

If the provider uses a rolling 24h window, the 23:59 sends still count inside the window, causing 00:01 sends to breach the quota.

For providers using a **calendar window**, you can use a DB table:

~~~sql
CREATE TABLE mail_quota_window (
    quota_scope_key VARCHAR(140) NOT NULL,
    quota_unit VARCHAR(32) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    capacity BIGINT NOT NULL CHECK (capacity > 0),
    reserved BIGINT NOT NULL DEFAULT 0
        CHECK (reserved >= 0),
    PRIMARY KEY (
        quota_scope_key, quota_unit, window_start
    ),
    CHECK (window_end > window_start)
);
~~~

Reserve via DB transaction:

~~~sql
UPDATE mail_quota_window
SET reserved = reserved + :cost
WHERE quota_scope_key = :scope
  AND quota_unit = :unit
  AND window_start = :window_start
  AND reserved + :cost <= capacity
RETURNING reserved;
~~~

In PostgreSQL, updates on the same row serialize via row locks. When no row returns, **never assume quota was sufficient**: the row may be missing, the window wrong, or quota exhausted.

### When both account and tenant daily budgets exist

Reserve both in **one transaction**, or use a coordinated reservation mechanism:

~~~text
BEGIN
  Lock account window row
  Lock tenant window row (in consistent order)
  Validate both capacities
  Increment both counters
COMMIT
~~~

If either counter lacks room, the transaction **rolls back completely**, avoiding partial deductions. Lock rows in deterministic order to minimize deadlocks. If the provider uses a rolling 24h window, the calendar table above does not apply directly; use event/window accounting or provider-supplied quota APIs.

### Why never hold the transaction across SMTP?

A network call can hang for seconds. Never hold quota row locks and DB transactions open across `JavaMailSender.send(...)`. Reserve and commit quickly, then submit SMTP outside the transaction. If a worker dies after reserving yet before submitting, some virtual capacity is lost; that is safer for quotas than blindly refunding permits when the provider may have accepted. Reconciliation must rely on evidence and reservation semantics.

## 15. Concurrency limiters: separating slots from rate tokens

Even with valid average throughput, opening too many simultaneous SMTP connections can trigger rejections or hang workers.

~~~java
import java.util.concurrent.Semaphore;

public final class LocalSmtpConcurrencyGate {
    private final Semaphore slots;

    public LocalSmtpConcurrencyGate(int maximum) {
        if (maximum <= 0) {
            throw new IllegalArgumentException(
                    "maximum must be positive");
        }
        this.slots = new Semaphore(maximum);
    }

    public boolean tryAcquire() {
        return slots.tryAcquire();
    }

    public void release() {
        slots.release();
    }
}
~~~

Usage:

~~~java
if (!slots.tryAcquire()) {
    deferJobForCapacity(jobId);
    return;
}

try {
    // Reserve rate permit right before submission.
    // Then call JavaMailSender.send(...).
    sender.send(message);
} finally {
    slots.release();
}
~~~

**Only release when slot acquisition succeeded.** A local semaphore bounds operations within one JVM; with 4 replicas of 5 slots each, the cluster can still run 20 concurrent SMTP calls.

For hard concurrency caps per provider account, use a global slot allocator / distributed semaphore or a centralized worker pool. When using **leases for distributed slots**, account for worker pauses, network drops, and lease expirations: a slot can expire while an old SMTP call is still active, breaching the hard limit. Apply timeouts, renewal/fencing, and cautious policies; never assume TTL-based distributed semaphores are absolute guarantees against every failure.

### Acquire slot first or token first?

- Acquiring a token first and then finding no SMTP slot can waste the token.
- Holding a slot while waiting minutes for a token locks concurrency capacity needlessly.
- Check slot availability quickly, atomically reserve the rate permit **close to submission time**, and immediately release the slot if the permit is denied.
- Across multiple distributed dimensions, document reservation ordering and compensation rules for proven pre-submission denials.

Never hold a database transaction while waiting for slots or quotas.

## 16. Fair scheduling: tenant quotas alone do not prevent starvation

A FIFO queue containing:

~~~text
A1, A2, A3, ..., A100000, B1, C1
~~~

Even if Tenant A is capped at 5/s, workers can repeatedly claim hundreds of A-jobs, get denied by the limiter, and defer them—keeping B and C from being picked on time.

Therefore **rate limiters** should pair with a **fair scheduler**:

~~~text
Ready queues by tenant/lane
        |
        v
Weighted round robin / Deficit round robin
        |
        v
Hierarchical rate admission
        |
        v
SMTP worker pool
~~~

Approaches:

| Policy | Pros | Cons |
|---|---|---|
| Round robin across tenants | Simple, stops one tenant taking every turn | Ignores multi-recipient cost |
| Weighted fair queueing | Prioritizes service tiers by weight | Requires configuring/tuning weights |
| Deficit round robin | Handles varying job costs, unit-fair | Must track deficits/quanta |
| Priority lanes | Security/transactional emails go first | Strict priority can starve bulk |
| Reserved slots/rate | Protects capacity for critical emails | May sit idle when lane load is low |

### Why must fairness account for cost?

If Tenant A sends one message to 20 recipients while Tenant B sends one message to 1 recipient, round robin by **message count** still lets A consume 20x the recipient quota. When providers meter by recipient, fair-share algorithms must weight by that cost.

### Avoid reverse starvation

Do not let the security lane consume 100% of capacity indefinitely unless SLA/policy requires it. Combine reserved capacity, weighted scheduling, and job-age escalation. Marketing emails with valid consent and deadlines also deserve progress within available provider capacity.

## 17. Configuring account/tenant policies in Spring Boot

An application-defined namespace:

~~~yaml
app:
  mail:
    rate-limits:
      accounts:
        primary-prod:
          unit: recipients
          refill-tokens-per-second: 10.0
          burst-capacity: 20
          max-concurrent-submissions: 5
          safe-daily-recipient-budget: 20000
      tenant-defaults:
        unit: recipients
        refill-tokens-per-second: 2.0
        burst-capacity: 5
      tenant-overrides:
        tenant-gold:
          refill-tokens-per-second: 5.0
          burst-capacity: 10
      fallback:
        on-limiter-unavailable: fail-closed
~~~

**Numbers are illustrative only, not real provider quotas.** `app.mail.rate-limits.*` is not enforced automatically by Spring Mail; the application must read, validate, and wire it into rate gates and scheduler policies.

### Binding and validating policies

Example with Spring Boot configuration properties:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties
        .ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.rate-limits")
public record MailRateLimitsProperties(
        Map<String, AccountLimit> accounts,
        TenantLimit tenantDefaults,
        Map<String, TenantLimit> tenantOverrides) {

    public record AccountLimit(
            String unit,
            double refillTokensPerSecond,
            int burstCapacity,
            int maxConcurrentSubmissions,
            long safeDailyRecipientBudget) {
    }

    public record TenantLimit(
            String unit,
            double refillTokensPerSecond,
            int burstCapacity) {
    }
}
~~~

Registration:

~~~java
import org.springframework.boot.context.properties
        .EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(
        MailRateLimitsProperties.class)
public class MailRateLimitConfiguration {
}
~~~

In production add **validation**: values must be positive (unless disabled is explicitly modeled), `Double.isFinite`, burst capacity sufficient for valid costs, valid tenant mappings, quota units matching the provider, and TTL exceeding full-refill time. Never silently treat missing account policies as unlimited.

### Changing policies at runtime

Lowering a limit from 10/s to 3/s across replicas needs a shared **policy version**. If some pods run old configs and others run new ones, aggregate behavior drifts. Redis buckets holding tokens under the old capacity must also be handled when lowering caps; the sample script clamps tokens to capacity, yet does not solve pods running mixed policy versions.

Only authorized roles may change quotas, with audit logs and orderly rollouts; never let tenants pass `limit=1000000` in an arbitrary HTTP request.

## 18. Tenant authorization and provider account selection

A rate limiter is not an authorization mechanism. Before granting permits, the system must know which tenant owns the job and which sender/provider accounts that tenant is **permitted** to use.

~~~text
Authenticated caller
        |
        v
Resolve trusted tenant from security context
        |
        v
Validate notification type + sender profile
        |
        v
Select approved provider account
        |
        v
Lookup quota policy for account and tenant
        |
        v
Rate gate
~~~

A mail API must never accept directly:

~~~json
{
  "tenantId": "tenant-of-another-customer",
  "providerAccountId": "admin-smtp-account",
  "smtpPassword": "any-value",
  "rateLimit": 999999
}
~~~

and trust those fields for quota decisions. Callers could "borrow" another customer's budget or turn the backend into an open relay.

Instead, use a business API:

~~~java
public record SendInvoiceCommand(
        String invoiceId,
        String locale) {
}
~~~

The application service verifies the invoice belongs to the authenticated tenant, resolves recipients from trusted records, chooses an approved sender profile, and creates the mail job. `tenantId` and `providerAccountId` are server-derived and durably persisted for auditing and quotas.

### Tenant quotas can change with contracts

A tenant upgrading plans may go from 2 recipients/s to 5 recipients/s. Waiting jobs should generally use the active policy per product rules rather than snapshotting old quotas into every job. Even so, raising a tenant budget never raises the provider account's quota.

## 19. Outbox schema with tenant, account, status, and schedule time

Illustrative PostgreSQL table:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    provider_account_id VARCHAR(100) NOT NULL,
    sender_profile_id VARCHAR(80) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    lane VARCHAR(24) NOT NULL,

    recipient_ref VARCHAR(160) NOT NULL,
    payload_ref VARCHAR(255) NOT NULL,
    recipient_count INT NOT NULL
        CHECK (recipient_count > 0),
    business_event_key VARCHAR(180) NOT NULL,

    status VARCHAR(24) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    attempt_count INT NOT NULL DEFAULT 0,
    last_error_code VARCHAR(80),

    claim_token UUID,
    lease_until TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT chk_outbox_status CHECK (
        status IN (
            'PENDING', 'CLAIMED', 'PROCESSING',
            'RETRY', 'SUBMITTED',
            'FAILED', 'CANCELLED', 'EXPIRED', 'UNKNOWN'
        )
    ),
    CONSTRAINT uq_outbox_business_event UNIQUE (
        tenant_id, business_event_key
    )
);

CREATE INDEX idx_mail_outbox_ready
    ON mail_outbox (
        provider_account_id,
        available_at,
        id
    )
    WHERE status IN ('PENDING', 'RETRY');
~~~

`business_event_key` supports idempotent mail-intent creation per business action. It does not guarantee exactly-once SMTP on retries. `recipient_ref`/`payload_ref` should point to storage with proper access controls, encryption, and retention; never snapshot SMTP credentials in jobs.

### Store lane to support fairness

`lane` can be `SECURITY`, `TRANSACTIONAL`, or `BULK`. It is an application-approved classification, not an arbitrary parameter tenants pick to grab priority quota.

### Do not count rate denials as SMTP attempts

When the rate gate returns `DENIED`, the worker **never called SMTP**. Update `available_at` without incrementing `attempt_count`. Track `rate_limit_deferral_total` separately.

## 20. Creating mail intents in the same business transaction

Invoice issuance and email enqueue use case:

~~~text
BEGIN TRANSACTION
  INSERT/UPDATE invoice data
  INSERT mail_outbox (
    tenant_id,
    provider_account_id,
    status=PENDING,
    scheduled_at,
    available_at,
    ...
  )
COMMIT

Only after commit may the dispatcher submit via SMTP.
~~~

If business data commits yet enqueue fails, the email request is lost; if the email sends before the business transaction commits, the recipient receives info about a rolled-back transaction.

Spring:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {
    private final InvoiceRepository invoices;
    private final MailOutboxRepository outbox;
    private final TenantMailPolicy tenantPolicy;

    public InvoiceService(
            InvoiceRepository invoices,
            MailOutboxRepository outbox,
            TenantMailPolicy tenantPolicy) {
        this.invoices = invoices;
        this.outbox = outbox;
        this.tenantPolicy = tenantPolicy;
    }

    @Transactional
    public void issueInvoice(IssueInvoiceCommand command) {
        Invoice invoice = invoices.issue(command);
        TenantMailRoute route = tenantPolicy
                .approvedRoute(invoice.tenantId(), "INVOICE");

        outbox.insertIfAbsent(
                MailIntent.forInvoice(invoice, route));
    }
}
~~~

`InvoiceRepository`, `MailOutboxRepository`, `TenantMailPolicy`, and `MailIntent` are illustrative application abstractions. `insertIfAbsent` needs a unique constraint or atomic UPSERT on the business key; separate check-then-insert races when two requests arrive together.

**Never place `JavaMailSender.send(...)` inside the invoice-creation transaction.** SMTP does not roll back with the database.

## 21. Claiming small batches with SKIP LOCKED

With multiple workers, querying `SELECT ... WHERE status='PENDING'` and sending immediately can let two instances process the same mail job.

In PostgreSQL:

~~~sql
WITH ready AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND provider_account_id = :account_id
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND available_at <= CURRENT_TIMESTAMP
      AND (expires_at IS NULL
           OR expires_at > CURRENT_TIMESTAMP)
    ORDER BY available_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS job
SET status = 'CLAIMED',
    claim_token = :claim_token,
    lease_until = CURRENT_TIMESTAMP
        + INTERVAL '120 seconds',
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
FROM ready
WHERE job.id = ready.id
RETURNING job.id, job.tenant_id,
    job.provider_account_id, job.recipient_count,
    job.claim_token;
~~~

This is a **short transaction**: claim and commit, with no SMTP inside it. `SKIP LOCKED` avoids waiting on rows locked by another transaction, yet **does not guarantee strict FIFO** or inter-tenant fairness; `ORDER BY available_at` can still pull many Tenant A jobs ahead of B.

### Why not claim 100,000 jobs at once?

If an account can only send 5 recipients/s, hundreds of claimed jobs sit idle in RAM/executor queues. Leases expire before their turn comes; other workers reclaim them, causing duplicate work and hurting cancel/reschedule capability.

Size batches to actual throughput, bounded executor queues, and active claims. A fair selector can pick a few jobs per tenant/lane before claiming. When running fair scheduling across multiple workers, persist/recover fairness state too rather than keeping round-robin state only in one pod's memory.

## 22. When the limiter returns DENIED: defer without calling SMTP

Example job:

~~~text
id               = job-123
tenant_id        = tenant-42
status           = CLAIMED
scheduled_at     = 09:00
available_at     = 09:00
attempt_count    = 0
~~~

Account has permits, yet the tenant bucket is empty. The rate gate **deducts neither bucket** and returns a 3-second delay:

~~~text
new status       = PENDING
new available_at = 09:00:03
attempt_count    = 0
defer reason     = TENANT_RATE_LIMIT
~~~

Conditional update SQL:

~~~sql
UPDATE mail_outbox
SET status = 'PENDING',
    available_at = :next_available_at,
    claim_token = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND status = 'CLAIMED'
  AND claim_token = :claim_token
RETURNING id;
~~~

If 0 rows update, the worker lost its claim or state changed. Never update unconditionally and accidentally resurrect a canceled job.

### available_at must consider multiple constraints

If:

~~~text
account bucket next permit: 09:01
tenant bucket next permit:  09:00:03
daily quota recheck:       10:00
business quiet hours:      10:30
~~~

you may need to defer to a time **no earlier than all known constraints**. When provider quotas are unclear or usage data lags, use conservative recheck intervals without claiming certainty that a permit will be ready then.

**Never skip re-acquiring a permit just because the delay elapsed**; the rate gate may have issued that token to another job. Always request fresh admission right before submitting.

## 23. Interface pattern decoupling limiters from Spring Mail

Instead of embedding quota logic inside every controller/handler, dispatchers should use a shared interface:

~~~java
import java.time.Duration;
import java.util.UUID;

public record MailDispatchContext(
        UUID jobId,
        String tenantId,
        String providerAccountId,
        String senderProfileId,
        String notificationType,
        int messageCost,
        int recipientCost) {
}

public interface MailAdmissionPolicy {
    QuotaPermit reserve(MailDispatchContext context);
}

public interface SmtpSubmission {
    void submit(ClaimedMailJob job);
}
~~~

`MailAdmissionPolicy` can combine:

1. Provider account rate.
2. Tenant rate.
3. Daily quota.
4. Sender/account concurrency.
5. Lane reservations and explicit business restrictions.

**Note:** shared quotas must be reserved atomically/coordinated by design; a single-method interface does not automatically turn separate Redis/DB/slot backends into one distributed transaction.

`SmtpSubmission` hides `JavaMailSender` details so dispatchers can be unit-tested with fake senders. Each attempt must use a `providerAccountId` from approved config, never arbitrary hosts/passwords from tenant inputs.

### Distinguishing RateDecision, QuotaPermit, and system errors

Separate three outcomes:

~~~text
GRANTED
  -> capacity reserved; proceed to submission

DENIED
  -> provider/tenant budget insufficient; includes retryAfter

ERROR
  -> limiter DB/Redis unavailable or invalid policy
~~~

Never collapse config errors or Redis outages into `allowed=false` and silently retry every millisecond. Quota infrastructure failures need alerts and a `WAITING_LIMITER` status or separate deferral rather than looking like a tenant exhausted its budget.

## 24. Spring @Scheduled only wakes the dispatcher

Example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class MailDispatcherSchedulingConfig {
}
~~~

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class MailOutboxPoller {
    private final AccountAwareMailDispatcher dispatcher;

    public MailOutboxPoller(
            AccountAwareMailDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(
            fixedDelayString =
                    "${app.mail.dispatch.poll-delay-ms:1000}")
    public void dispatchReadyMail() {
        dispatcher.processReadyBatch();
    }
}
~~~

`AccountAwareMailDispatcher` is an application service, not built into Spring Mail. Using `@Scheduled` alone without an outbox loses quota-waiting state on restart.

### Never use Thread.sleep when permits run out

~~~java
// Avoid:
while (!rateLimiter.tryAcquire(1)) {
    Thread.sleep(1000);
}
~~~

With thousands of jobs, this ties up worker/executor slots just waiting, fills queues, and slows shutdowns. A `DENIED` response should end job processing, update `available_at`, and release the claim/slot.

### One pod or many pods?

In Kubernetes, every pod runs its own `@Scheduled`. Never assume only one instance runs the scheduler. Use atomic claims/leases or an appropriate per-account/queue leader. `@Scheduled` does not provide cluster-wide leadership.

## 25. Example dispatcher integrating quota gate and SMTP adapter

This skeleton shows **where** to acquire permits and update states; repositories, classifiers, and worker leases are application abstractions:

~~~java
import java.time.Clock;
import org.springframework.stereotype.Service;

@Service
public final class AccountAwareMailDispatcher {
    private final MailOutboxRepository jobs;
    private final MailAdmissionPolicy admission;
    private final SmtpSubmission submission;
    private final MailSubmissionErrorPolicy errors;
    private final Clock clock;

    public AccountAwareMailDispatcher(
            MailOutboxRepository jobs,
            MailAdmissionPolicy admission,
            SmtpSubmission submission,
            MailSubmissionErrorPolicy errors,
            Clock clock) {
        this.jobs = jobs;
        this.admission = admission;
        this.submission = submission;
        this.errors = errors;
        this.clock = clock;
    }

    public void processReadyBatch() {
        for (ClaimedMailJob job :
                jobs.claimReadyBatch(clock.instant(), 20)) {
            dispatchOne(job);
        }
    }

    private void dispatchOne(ClaimedMailJob job) {
        if (!jobs.isStillEligible(job)) {
            jobs.releaseOrExpire(job);
            return;
        }

        final QuotaPermit permit;
        try {
            permit = admission.reserve(job.dispatchContext());
        } catch (RuntimeException limiterFailure) {
            jobs.deferForLimiterOutage(
                    job, clock.instant().plusSeconds(30));
            reportRateGateFailure(job, limiterFailure);
            return;
        }

        if (!permit.granted()) {
            jobs.deferWithoutAttempt(
                    job,
                    clock.instant().plus(permit.retryAfter()));
            return;
        }

        if (!jobs.beginSubmission(job)) {
            // Claim changed or job was canceled.
            // Permit may be conservatively consumed;
            // never send without owning the job.
            return;
        }

        try {
            submission.submit(job);
            boolean persisted = jobs.markSubmitted(
                    job, clock.instant());
            if (!persisted) {
                reportOutcomeConflict(job);
            }
        } catch (Exception ex) {
            // Policy must distinguish phase/SMTP outcome.
            var outcome = errors.classify(ex);
            jobs.persistClassifiedOutcome(
                    job, outcome, clock.instant());
        }
    }

    private void reportRateGateFailure(
            ClaimedMailJob job, Exception error) {
        // Log jobId, account, and safe error code.
        // Never dump raw exceptions containing recipients/tokens.
    }

    private void reportOutcomeConflict(ClaimedMailJob job) {
        // Needs reconciliation; never auto-retry SMTP.
    }
}
~~~

`ClaimedMailJob`, `MailOutboxRepository`, `MailSubmissionErrorPolicy`, and invoked methods are **illustrative abstractions**, not built-in APIs. The example clarifies the ordering:

~~~text
Claim -> Validate -> Rate admission
       -> Begin attempt -> SMTP
       -> Persist classified outcome
~~~

### Production additions required

- Enforce account/tenant authorization and quota-scope mapping in the dispatcher.
- Re-check business eligibility: expired, unsubscribed, or canceled emails must not send.
- Acquire and release SMTP concurrency slots; never hold slots during deferrals.
- Coordinate daily budgets + rate tokens + slots with explicit reservation semantics.
- `beginSubmission` must check claim token/lease/status in a short transaction.
- Separate **compose**, **SMTP submit**, and **DB persistence** exceptions by phase; one `catch(Exception)` in the skeleton is insufficient to decide what is safe to retry.
- If SMTP accepts yet `markSubmitted` fails, reconcile as `UNKNOWN` instead of immediately resending.
- When a batch holds multiple messages/recipients, outcomes can be partial; track per-message/recipient states if providers return partial acceptance.
- Never log raw exceptions since providers may echo recipient addresses or MIME.
- Never span a single DB transaction across SMTP I/O.

### Exact placement for quota checks

Acquire permits **close to when network submission actually starts**. Reserving thousands of permits and queuing jobs in an executor for minutes breaks the rate limiter's accuracy against outgoing traffic. Use bounded worker pools and limit in-flight reservations.

## 26. When the rate gate fails: fail closed, bounded fallback, or fail open?

| Policy | Behavior | When to consider |
|---|---|---|
| **Fail closed** | Do not call SMTP; defer job durably | Safe default for bulk/marketing |
| **Fail open** | Submit without quota control | Risks breaching quotas; only under exceptional pre-accepted risk |
| **Bounded emergency fallback** | Send tiny volume under cluster-wide budget | Critical security emails with explicit approval and backup quota |
| **Provider failover** | Route to approved backup provider | Requires sender verification, separate quota, safe prior outcomes |

**Never default to fail-open to "avoid losing emails."** With an outbox, fail-closed **never loses mail intents**; it delays sending until permits resume. What remains is SLA and deadline monitoring.

### Bounded fallbacks must have cluster-wide caps

A 1/s local emergency limiter across 50 pods still emits 50/s, breaching account quotas. If using a fallback, enforce:

- A shared admission source or pre-designated coordinator.
- Explicit allowed accounts and lanes.
- Budget, TTL, fallback window, and auditing.
- Automatic shutoff when the shared limiter recovers.
- Operational alerts.

Never quietly switch to an "admin" SMTP credential with higher privileges just to bypass quotas.

## 27. Retry throttling differs from rate limiter DENIED

Two distinct cases:

**Application self-DENIES before calling SMTP:**

~~~text
job.status        = PENDING
job.available_at  = now + retryAfter
job.attempt_count = unchanged
reason            = TENANT_RATE_LIMIT
~~~

**Provider received submission and returned temporary rejection:**

~~~text
job.status        = RETRY
job.available_at  = now + backoff
job.attempt_count = incremented for the SMTP attempt
reason            = PROVIDER_TEMPORARY_THROTTLE
~~~

`RETRY` status is only for errors where policy permits retrying. A job deferred by the rate gate **is not an SMTP failure**.

### SMTP throttling differs from HTTP 429

SMTP uses reply codes like `421`, `450`, `451`, `452`, and provider-specific enhanced statuses; not all `4xx` replies are throttling. **HTTP email APIs** can return HTTP `429` and a `Retry-After` header. Never treat "SMTP 429" as a standard code.

An SMTP reply can echo recipients:

~~~text
451 4.7.0 Temporarily deferred <someone@example.test>
~~~

Never log raw exception messages or SMTP transcripts. Log internal codes, provider account IDs, and opaque `jobId`s.

## 28. Retries with backoff, jitter, and just-in-time quota checks

A retry policy:

\[
d_n = \min(d_{\max},d_0\times 2^{n-1})
\]

With *full jitter*:

\[
d_{\text{retry}} \sim U(0,d_n)
\]

If a provider specifies a minimum wait or daily quota reset time, `available_at` must not precede it.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

public final class MailRetryBackoff {
    private final long baseMillis;
    private final long maximumMillis;

    public MailRetryBackoff(
            Duration base, Duration maximum) {
        this.baseMillis = base.toMillis();
        this.maximumMillis = maximum.toMillis();
        if (baseMillis <= 0
                || maximumMillis < baseMillis) {
            throw new IllegalArgumentException(
                    "Invalid retry delays");
        }
    }

    public Instant nextAttempt(
            Instant now, int failedAttemptCount) {
        if (failedAttemptCount < 1) {
            throw new IllegalArgumentException(
                    "failedAttemptCount must be positive");
        }

        long cap = baseMillis;
        for (int i = 1; i < failedAttemptCount; i++) {
            cap = cap > maximumMillis / 2
                    ? maximumMillis
                    : Math.min(maximumMillis, cap * 2);
        }
        long wait = ThreadLocalRandom.current()
                .nextLong(cap + 1);
        return now.plusMillis(wait);
    }
}
~~~

This is an illustrative helper. Production needs a minimum retry delay if near-zero delays are undesirable, max attempts, job expiry, error classification, and provider-specified cooldowns. Never retry authentication or permanent sender-permission failures like temporary throttling.

**Backoff does not replace the rate gate.** When a job reaches `available_at`, it must still request a tenant/provider-account permit because other jobs may have consumed quota while it waited.

## 29. SMTP UNKNOWN outcomes and their effect on quota accounting

The hardest aspect of combining a DB outbox, Redis limiter, and SMTP is that the three systems **share no transaction**:

~~~text
Worker reserves account + tenant rate tokens
          |
          v
Worker writes PROCESSING / attemptStarted
          |
          v
JavaMailSender.send(message)
          |
          +-- Server accepts DATA
          |
          +-- Network drops before client receives result
          |
          v
App sees exception; DB still PROCESSING
~~~

If the app automatically does:

~~~text
refund all rate tokens
mark job RETRY
resend through provider B immediately
~~~

both accounting and delivery break: Provider A already metered and accepted the message, and resending via B duplicates it.

A cautious policy:

1. Classify outcomes by SMTP phase and evidence.
2. When acceptance is uncertain, mark `UNKNOWN` or a reconciliation state.
3. Never refund quota reservations merely because an exception occurred.
4. Use provider message tracing or idempotency features **only when genuinely supported**.
5. Retry or fail over only per the business workflow's duplicate-risk rules.
6. Record attempt history with provider/account, timestamps, and safe status codes.

**Rate limiters do not provide exactly-once delivery.** They only bound how many operations may start within a time window.

### Lease expiry does not prove SMTP did not send

If a worker starts submitting and gets killed, its lease expires. The next worker cannot infer the server never accepted the job. Separate pre-network `CLAIMED` from attempt-started `PROCESSING`, verify claim tokens/fencing, and route ambiguous states to reconciliation rather than blind replay.

## 30. Provider failover requires independent quotas and permissions

A system with primary Provider A and backup B:

~~~text
Tenant A job
   |
   v
Routing policy
   |
   +-- Provider A account
   |       +-- Account A quota
   |       +-- Tenant A share on account A
   |
   +-- Provider B account
           +-- Account B quota
           +-- Tenant A share on account B
~~~

When failing over:

- Jobs may use Provider B only if sender identity/domain are verified and permitted by policy.
- Provider B has its own quota scopes; **never reuse A's bucket** when accounts are independent.
- If A and B sit under one shared organization quota, both must respect that global scope together.
- Never fail over immediately while A's outcome is `UNKNOWN`.
- Never use multiple providers to evade anti-abuse restrictions or mail contracts.

Provider failover is not mutating `spring.mail.host` on a shared multi-threaded `JavaMailSenderImpl` singleton. Create distinct senders/adapters per route with independent credentials and sender permissions.

## 31. Per-tenant quotas when one tenant uses multiple products

A tenant may send emails from several modules:

~~~text
Tenant A
   |
   +-- Billing service
   +-- Account security service
   +-- Campaign service
   |
   +-- Tenant-level policy
   |
   +-- Provider-account-level policy
~~~

If each module has an independent 5/s limiter, the tenant's aggregate rate reaches 15/s. If the tenant quota applies **product-wide**, all modules must draw from a shared tenant-level budget. If policy is per product/lane, keys and limits must express that exact scope.

### Cross-account tenant quotas

One tenant might use:

~~~text
tenant-42 → provider account A (transactional)
tenant-42 → provider account B (subscription)
~~~

If the tenant's contract allows at most 100,000 recipients/day **across all providers**, the tenant quota must span both. A two-bucket Lua script in **one Redis Cluster slot** is not automatically atomic if Account A/B and global-tenant keys live in different slots.

Options:

- Shared database transaction for global daily budgets.
- Quota allocator issuing bounded sub-budgets to each provider route.
- Central coordinator managing account and tenant quotas together.
- Colocating keys in one Redis hash slot when scale/policy allows.

Never hand each provider account the full tenant quota assuming the sum stays valid.

## 32. Periodic quotas, schedules, and time-of-day rules

A tenant may have a **monthly quota** or paid tier while the provider has a **rolling 24h quota**. A customer near their monthly cap may still fit under the provider's remaining quota, yet **application tenant policy must block them**.

Example:

~~~text
Tenant contractual budget: 60,000 recipients/month
  remaining = 0

Provider sending account:
  remaining today = 8,000

Result:
  Tenant email is not admitted despite provider capacity.
~~~

Conversely, if the tenant still has budget while the provider is exhausted, the job must still defer.

### Quiet hours and marketing schedules

Rate limiters only govern count/speed; they do not replace rules on *when sending is allowed*. A job may wait because:

- The user set a future `scheduled_at`.
- The tenant restricts sends to business hours.
- Consent/suppression policies apply.
- Account quota is not ready yet.
- The provider is degraded.

`available_at` in the outbox should reflect the earliest computed eligible time, yet **every critical eligibility check must re-run right before SMTP submission**. A job created last week may no longer have consent today.

## 33. Monitoring: rate limiter metrics need three dimensions

Observe:

1. **Demand:** how many jobs are created and waiting?
2. **Admission:** how many permits are granted/denied and why?
3. **Supply:** how many submissions did the SMTP provider actually accept?

| Metric | Meaning |
|---|---|
| `mail_outbox_ready_jobs` | Due jobs awaiting dispatch |
| `mail_outbox_oldest_ready_age_seconds` | Age of oldest due job |
| `mail_rate_permit_total` | Permits granted by account/lane |
| `mail_rate_denied_total` | Denials due to quota |
| `mail_rate_denied_duration_seconds` | Suggested deferral delay when denied |
| `mail_rate_gate_errors_total` | Redis/DB/shared limiter errors |
| `mail_rate_gate_latency_seconds` | Latency to reserve permits |
| `mail_account_daily_quota_remaining` | Remaining account budget if known |
| `mail_tenant_budget_remaining` | Per-tenant budget if appropriately tracked |
| `mail_smtp_inflight` | Active in-flight SMTP operations |
| `mail_provider_throttle_total` | Throttling responses from providers |
| `mail_submitted_total` | Accepted submissions |
| `mail_attempt_unknown_total` | Attempts with uncertain outcomes |
| `mail_expired_total` | Jobs expired before submission |
| `mail_fair_scheduler_wait_seconds` | Wait time for turn by lane/tier |

### Distinguish future scheduled backlogs from genuinely delayed backlogs

A job with `scheduled_at` next week is `PENDING`, not overdue. A good dashboard separates:

~~~text
scheduled_future:
  scheduled_at > now

ready_now:
  scheduled_at <= now
  available_at <= now
  status in PENDING/RETRY

waiting_quota:
  scheduled_at <= now
  available_at > now
  deferReason in QUOTA/TENANT_LIMIT
~~~

Counting total `PENDING` triggers false alarms when tenants schedule future campaigns. Counting only `ready_now` hides backlogs deferred for hours due to exhausted daily budgets. You need both.

### Metric labels: avoid high cardinality and personal data

Labels should come from small, controlled sets:

~~~text
provider=PRIMARY
account_tier=PRODUCTION
lane=TRANSACTIONAL
decision=DENIED
reason=TENANT_RATE
~~~

Never use `recipient`, raw email addresses, mail job UUIDs, subjects, or unbounded tenant IDs as default Prometheus tags. With tens of thousands of tenants, a `tenant_id` label on every metric causes high cardinality and high cost; aggregate by plan/tier and use dedicated job/audit stores for per-tenant lookups.

## 34. Micrometer example: recording permits and denials

Spring Boot apps typically use Micrometer to export metrics:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public final class MailQuotaMetrics {
    private final MeterRegistry metrics;

    public MailQuotaMetrics(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    public void recordDecision(
            String providerGroup,
            String lane,
            String reason,
            boolean permitted) {
        metrics.counter(
                "mail_quota_admission_decisions",
                "provider_group", providerGroup,
                "lane", lane,
                "reason", reason,
                "decision", permitted ? "granted" : "denied")
                .increment();
    }
}
~~~

`providerGroup`, `lane`, and `reason` must come from **enums/allowlists**, never raw tenant inputs or email addresses. To display per-tenant breakdowns in an admin table, query the database with access control and pagination rather than pushing hundreds of thousands of tenant IDs into metric labels.

### Should you expose a gauge for remaining tokens?

Remaining tokens in Redis are instantaneous state. Polling gauges frequently across thousands of tenant buckets loads Redis just for monitoring. Usually it is better to track permits/denials, latency, backlogs, and policy caps; sample remaining quota only for critical scopes or bounded diagnostics.

## 35. Alerting on SLAs rather than only SMTP error rates

A system can show:

~~~text
SMTP 4xx error rate = 0
Outbox backlog      = 200,000 jobs
Oldest OTP pending  = 7 minutes
~~~

If the limiter blocked all SMTP calls due to exhausted quotas, the provider reports zero errors while the system breaches OTP SLAs. Tie alerts to:

- Ready job age exceeding per-lane thresholds.
- Prolonged tenant rate denials alongside growing backlogs.
- Rising provider throttles despite active account limiters.
- Rising limiter p95/p99 latency.
- Redis/DB quota store unavailability.
- Outbox schedulers failing to claim despite ready backlogs.
- Daily budgets exhausting too early in the cycle.
- OTPs starved by bulk lanes.
- Accepted submission throughput lagging demand for too long.
- Abnormal spikes in `UNKNOWN` outcomes.

### Evaluate capacity with real numbers

Example:

~~~text
Demand: 8 recipients/s
Provider safe supply: 5 recipients/s
Net backlog growth: ~3 recipients/s
~~~

Without changing policy, adding workers cannot shrink the backlog sustainably; it only increases deferred requests. Throttle mail producers, stagger campaign schedules, route via approved quotas/providers, or negotiate higher limits.

Rough backlog drain estimate:

\[
t_{\mathrm{drain}} \approx
\frac{\text{backlog cost}}
{\text{accepted capacity} - \text{new demand}}
\]

Valid only when accepted capacity exceeds new demand and all values share **the same unit**. Daily quota resets, retries, multiple lanes, and varying job costs complicate real-world drains.

## 36. Unit testing token buckets with a fake ticker

Never test a rate limiter with `Thread.sleep(1000)` hoping CI timing cooperates. With `LongSupplier ticker`, control virtual time deterministically:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;

public final class FakeTicker implements LongSupplier {
    private long nanos;

    @Override
    public long getAsLong() {
        return nanos;
    }

    public void advanceMillis(long milliseconds) {
        nanos += TimeUnit.MILLISECONDS.toNanos(milliseconds);
    }
}
~~~

JUnit 5 + AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.junit.jupiter.api.Test;

class LocalTokenBucketTest {

    @Test
    void grantsBurstButNotBeyondCapacity() {
        FakeTicker ticker = new FakeTicker();
        LocalTokenBucket bucket = new LocalTokenBucket(
                2, 1.0, ticker);

        assertThat(bucket.tryAcquire(1).allowed()).isTrue();
        assertThat(bucket.tryAcquire(1).allowed()).isTrue();

        RateDecision denied = bucket.tryAcquire(1);
        assertThat(denied.allowed()).isFalse();
        assertThat(denied.retryAfter().toMillis())
                .isEqualTo(1000);
    }

    @Test
    void replenishesTokensWithElapsedTime() {
        FakeTicker ticker = new FakeTicker();
        LocalTokenBucket bucket = new LocalTokenBucket(
                1, 2.0, ticker);

        assertThat(bucket.tryAcquire(1).allowed()).isTrue();
        assertThat(bucket.tryAcquire(1).allowed()).isFalse();

        ticker.advanceMillis(500);
        assertThat(bucket.tryAcquire(1).allowed()).isTrue();
    }

    @Test
    void rejectsCostThatCanNeverFit() {
        FakeTicker ticker = new FakeTicker();
        LocalTokenBucket bucket = new LocalTokenBucket(
                2, 1.0, ticker);

        assertThatThrownBy(() -> bucket.tryAcquire(3))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

These tests only verify the **local algorithm**. They do not prove a 10-pod Kubernetes cluster preserves aggregate rates. For Redis/shared stores, run real concurrent integration tests.

## 37. Redis integration tests: multiple workers never exceed shared quota

A key test:

~~~text
Account bucket:
  capacity = 10
  refill = disabled for test observation interval

Tenant A bucket:
  capacity = 10

100 concurrent workers each reserve cost 1

Expected in the controlled window:
  Granted = 10
  Denied  = 90
  Total consumed = 10
~~~

In the lesson's Lua script, refill is always positive; in integration tests, use a tiny refill, a short test window, or a controlled clock/test implementation. **Do not pass `refill=0` to the current script**, as it rejects invalid policies. Tests must control timing and races so tokens refilling mid-run do not skew assertions.

### Verifying two buckets never partially deduct

~~~text
Account tokens = 1
Tenant A tokens = 0
Tenant B tokens = 1

Request Tenant A -> DENIED
Request Tenant B -> GRANTED

If Tenant A had consumed the shared token first,
Tenant B would have failed incorrectly.
~~~

Tests must inspect Redis state afterward to verify a `DENIED` request **did not deduct the account bucket**. If using multi-key scripts, run tests against real Redis Cluster or matching config to catch `CROSSSLOT` errors when hash tags diverge.

### Scenarios to cover

| ID | Scenario | Expectation |
|---|---|---|
| RD-01 | Multiple threads reserve same account key | Total grants never exceed bucket in window |
| RD-02 | Tenant A empty, account has tokens | A denied, account not deducted |
| RD-03 | Account empty, Tenant B has tokens | B denied, Tenant B not deducted |
| RD-04 | Varying recipient costs | Deducts exact policy units |
| RD-05 | Cost exceeds capacity | Invalid cost error, never waits forever |
| RD-06 | Redis script timeout | `ERROR`/fail closed, never grants falsely |
| RD-07 | Redis restart/failover | Handled per policy and headroom |
| RD-08 | Key TTL expiry | Never replenishes tokens too early |
| RD-09 | Account policy changes | Replicas do not mix two uncontrolled versions |
| RD-10 | Cluster keys in different hash slots | Error caught, no unbounded fallback |
| RD-11 | Tenant quota shared across providers | Global budget stays protected |
| RD-12 | Credential rotation | Does not reset provider-account bucket |
| RD-13 | Retry of timed-out reserve request | Conservative accounting or idempotent reservation if supported |
| RD-14 | Both buckets have permits | Single joint atomic grant |

### Avoiding a misconception about retrying reservations

If a client calls the Lua script, Redis grants a permit, and the reply drops on the network, retrying **consumes a second token**. That does not exceed quota, though it can reduce effective throughput. Where tighter precision is needed, add a **reservation ID** with TTL-bound idempotent accounting—noting this adds state and race handling. Never refund tokens without knowing whether SMTP submission occurred.

## 38. Load testing database outbox and SMTP sink together

To validate the production design, test from **job ingestion** through the **SMTP adapter**, not just the bucket in isolation:

~~~text
Test producer
      |
      v
PostgreSQL outbox
      |
      v
N Spring worker replicas
      |
      v
Shared Redis limiter
      |
      v
SMTP sink / mock server
      |
      v
Record accepted submissions
~~~

Example scenarios:

| Test | Goal |
|---|---|
| 1 tenant, burst of 10,000 jobs | Never exceeds safe account rate |
| 50 active tenants | No tenant suffers unjustified starvation |
| 1 huge-volume tenant + 1 OTP tenant | OTP latency stays within SLA |
| Autoscale from 2 to 10 pods | Aggregate throughput stays capped |
| Rolling deploy with 2 config versions | Transition does not over-grant permits |
| Provider slow (10 s per response) | Concurrency slots bound in-flight calls |
| Temporary Redis outage | Jobs are not lost and provider is not flooded |
| Worker crash after claim | Lease recovers without losing jobs |
| Worker crash after SMTP accepted | `UNKNOWN`/reconciliation, no blind resend |
| Daily account quota exhausted | Jobs defer until valid window/recheck |
| Simultaneous campaigns across tenants | Fair scheduler balances by weights/cost |
| Multi-recipient messages | Meters recipient costs accurately, not just messages |

Use an SMTP sink or test double like Mailpit/GreenMail depending on your stack, paired with programmable response/latency injection. Sinks usually lack real quotas; to test provider throttling, simulate reply codes or use an **approved sandbox account**.

### Never test against production accounts or real recipients

You do not need thousands of real emails to prove a limiter works. Load tests should use sandbox SMTP, synthetic data, and non-sensitive content; measure rates, concurrency, loss/retries, and DB state rather than "whether it landed in real Gmail."

### Metrics to collect

- Requests accepted by the SMTP sink per window.
- Account/tenant granted vs denied permits.
- Retry/queue backlog age and expired job count.
- Rate-gate p95 latency and Redis CPU/network.
- DB claim latency and row contention.
- Executor active threads and queue length.
- Fairness across tenant tiers and lanes.
- Email duplicate rate across crash windows.

High throughput that causes duplicates, dropped jobs, or quota breaches **is not a success**.

## 39. Runbook: a tenant is throttled for too long

Suppose Tenant B reports order confirmation emails are delayed 20 minutes:

~~~text
tenant B:
  due jobs = 2,100
  submitted last 15 min = 0
  rate denied = high
  SMTP errors = 0
~~~

Never conclude the provider is healthy just because SMTP errors are zero. The limiter may be blocking all submissions before the provider ever sees a request.

### Step 1: distinguish the quota cause

1. Check jobs still in `PENDING`/`RETRY`, `available_at`, and defer reasons.
2. Identify the active account/tenant quota keys.
3. Check the tenant contract/tier, policy version, and quota window.
4. Check remaining provider account budget.
5. Check whether external tools are sharing the account unknown to the dispatcher.
6. Check Redis script errors, TTLs, and suggested delays.
7. Compare granted permits against SMTP-accepted counts.

### Step 2: inspect fairness and job selection

If the account still has quota while B gets skipped:

- Is another tenant hogging the head of a FIFO queue?
- Does the scheduler partition selection by tenant/lane?
- Is `batchSize` claiming too many jobs from one tenant?
- Does B actually have permission/eligibility errors misreported as quota denials?
- Does Tenant B's message cost exceed burst capacity so it can never be granted?
- Is a rate limiter key mis-scoped or holding a stale policy?

### Step 3: remediation steps

- Temporarily pause non-urgent batches to protect critical emails.
- Lower burst capacity of the spiking source rather than just adding workers.
- Fix quota key/policy mappings if misconfigured.
- Reconcile account usage against provider dashboards.
- Tune fair-scheduler weights within contractual and provider limits.
- Keep jobs durable; never mass-delete emails just because the backlog is big.

### Step 4: post-fix verification

- Tenant B begins receiving permits and SMTP acceptances.
- Aggregate account throughput stays within safe caps.
- Backlog age declines.
- No retry storms or duplicate spikes emerge.
- No other tenant starves due to policy edits.

## 40. Runbook: provider keeps throttling despite the limiter

A provider may still return SMTP 4xx throttling even when internal limiters look mathematically sound:

1. **Wrong scope:** provider meters per organization while the app limits per credential.
2. **Multiple senders:** legacy apps, marketing tools, or scripts share the account.
3. **Different rolling window:** app uses fixed windows while provider uses sliding windows.
4. **Burst too high:** average refill matches, yet short bursts exceed provider tolerance.
5. **Wrong unit:** app counts messages while provider counts recipients.
6. **Replica scaling:** some pods run local limiters or stale configs.
7. **TTL/failover reset:** Redis keys reset to full tokens prematurely.
8. **Reputation throttling:** provider temporarily slows traffic below published quotas.
9. **Connection caps:** too many concurrent SMTP operations despite low message rates.
10. **Clock/policy drift:** scheduler uses wrong timestamps or wait logic.

### Mitigation workflow

~~~text
Provider begins throttling
        |
        v
Pause or reduce noncritical bulk lane
        |
        v
Verify provider account and quota unit
        |
        v
Inspect aggregate sends across all workers/apps
        |
        v
Lower rate/burst and apply safe backoff
        |
        v
Keep jobs in outbox until permits available
        |
        v
Restore gradually based on observed acceptance
~~~

Never "fix" this by raising `ThreadPoolTaskExecutor.maxPoolSize` or creating extra SMTP credentials under the same quota account. Adding concurrency during throttling usually worsens error rates.

### Adaptive throttling

When providers throttle dynamically by reputation, use **additive increase, multiplicative decrease (AIMD)**:

\[
r_{t+1} =
\begin{cases}
\max(r_{\min}, \beta r_t), & \text{significant throttling}\\
\min(r_{\max}, r_t+\alpha), & \text{stable with remaining demand}
\end{cases}
\]

where `0 < β < 1`, `α > 0`. The upper cap `r_max` must still obey provider contracts and safe caps; when traffic is idle, never raise the rate endlessly just because no errors appeared.

## 41. Security and privacy in quota state

Redis keys, metrics, logs, and traces can also expose customer data. Principles:

| Asset | Risk | Control |
|---|---|---|
| Redis quota keys | Contain sensitive emails/usernames/tenants | Use stable opaque IDs only; ACLs/TTLs |
| Quota policies | Tenant alters another customer's limits | Server-side authorization and audits |
| Mail job/outbox | Contains recipients and payloads | DB encryption/RBAC/retention |
| SMTP exceptions | Provider echoes addresses | Normalized error codes, no raw transcripts |
| Metric labels | High-cardinality tenants/recipients | Aggregate by tier/lane/provider |
| Support UI | Exposes another tenant's send states | Row-level tenant authorization |
| Audit trails | Reveal organizational patterns | Access controls and retention |
| Config secrets | SMTP passwords and API tokens | Secret manager, rotation, least privilege |

### Never use recipient email as a default rate limiter key

~~~text
mail:rate:recipient:customer@example.test
~~~

This places personal data inside Redis keys that can show up in monitoring snapshots, logs, or backups. If per-recipient abuse prevention is required, design scoped/opaque tokens with access controls, retention, and privacy review rather than defaulting to raw emails.

### Do not treat tenant ID as a secret

While internal tenant IDs may not identify individuals directly, combining them with timestamps, mail types, and send volumes reveals business activity. Restrict public detail and audit access, especially on cross-tenant dashboards.

### Rate limiters do not replace consent/suppression

A tenant with remaining quota still cannot spam or email unsubscribed users. Before SMTP submission, check business authorization, consent/suppression, and notification type. Rate limiting protects resources; it never validates send legitimacy.

## 42. Anti-patterns in multi-tenant systems

### 42.1. Only calling Thread.sleep between sends

Multiple workers/replicas exceed aggregate limits while sleeping ties up threads. Use distributed gates and durable deferrals.

### 42.2. Setting maxPoolSize to "limit emails/second"

Pool size controls concurrency, not rate or daily quotas.

### 42.3. One local bucket per replica

Scaling from 2 to 10 pods multiplies aggregate throughput 5x. Use shared admission or controlled budget partitioning.

### 42.4. Keying by credential version instead of provider account

Rotating passwords resets buckets while the provider still enforces one account quota. Scope keys to the provider contract.

### 42.5. Having tenant limiters without an account limiter

Each tenant stays under its own limit while their combined traffic breaches the provider account quota.

### 42.6. Having an account limiter without tenant fairness

One large-batch customer consumes all shared capacity, starving other tenants.

### 42.7. Deducting account tokens then finding the tenant bucket empty

Leaks capacity on partial grants. Use atomic hierarchical reservations or coordinated admission.

### 42.8. Using non-atomic Redis GET/SET

Two workers read the same token count and both send, breaching budgets. Use atomic scripts or transactions.

### 42.9. Overly short Redis TTLs or resetting buckets full on restart

State vanishes before full refill, enabling unauthorized bursts. Size TTLs, Redis persistence/failover, and headroom.

### 42.10. Confusing calendar days with rolling 24 hours

Midnight counter resets can breach rolling quotas right after midnight.

### 42.11. Treating one message as one recipient

Messages with To/Cc/Bcc consume quota per envelope recipient. Use matching cost units.

### 42.12. Refunding permits on every SMTP exception

The provider may have accepted or metered part of the request despite client timeouts. Never refund blindly on unclear outcomes.

### 42.13. Retrying immediately on provider throttles

Retry storms worsen 4xx rates; use backoff/jitter, quota re-checks, and max attempts.

### 42.14. Spinning up extra SMTP accounts/keys to evade anti-abuse

Violates provider policies and harms deliverability/reputation. Failover is for approved routes, not bypassing restrictions.

### 42.15. Letting tenants choose another tenant's quota scope or account

Risks budget theft and sender spoofing. Enforce mappings server-side.

### 42.16. Claiming too many jobs before capacity exists

Leases expire in executor queues, causing duplicate work. Claim small batches with backpressure and reserve right before sending.

### 42.17. Calling SMTP inside quota/outbox locking transactions

Slow network I/O causes DB contention; commit reservations/claims quickly and send outside transactions.

### 42.18. Failing open indefinitely during Redis outages

Losing shared control across replicas floods providers instantly. Fail closed or use a cluster-wide emergency budget.

### 42.19. Not monitoring backlog age

Zero SMTP errors do not mean due emails are moving; jobs may be stuck on quota denials for hours.

### 42.20. Logging raw exceptions, recipients, or tenant quota details unnecessarily

Increases data-leak risk and cardinality. Use structured logs, opaque IDs, reason codes, access controls, and retention.

## 43. Phased production rollout checklist

A rollout path that avoids flipping full traffic onto a brand-new token bucket:

### Phase 1: inventory and policy

1. List all provider accounts, SMTP credentials, and applications sharing them.
2. Identify true quota scopes by provider/organization/account/credential/sender.
3. Identify units: messages, recipients, API requests, connections, byte sizes.
4. Identify windows: per-second, sliding minute, rolling 24h, or calendar day.
5. Define burst allowances and concurrency caps.
6. List tenant tiers, email types, and SLAs.
7. Design tenant access policies for sender/provider accounts.
8. Pick safe budgets below hard provider limits for headroom.

### Phase 2: durable job persistence

1. Create outbox entries in the same transaction as business events.
2. Add idempotency keys for send intents.
3. Persist `scheduled_at`, `available_at`, `status`, and `attempt_count`.
4. Add claim tokens, leases, and conditional status transitions.
5. Forbid SMTP sends before job-creation transactions commit.
6. Define handling for expired, canceled, or unsubscribed jobs.

### Phase 3: admission control

1. Define account and tenant policies with matching cost units.
2. Implement atomic multi-bucket reservations.
3. Choose DB/Redis/shared stores matching required scale and consistency.
4. Define TTLs, policy versions, clocks, and limiter failover behavior.
5. Add daily/rolling-window quotas and SMTP concurrency caps.
6. Reserve right before submission rather than pre-reserving thousands of jobs.
7. On denial, reschedule in the outbox without incrementing SMTP attempts.
8. On limiter outages, fail closed or apply audited bounded fallbacks.

### Phase 4: fairness and SLAs

1. Separate `SECURITY`/`TRANSACTIONAL`/`BULK` lanes.
2. Pick fair schedulers (round robin, weighted, or deficit).
3. Prevent one tenant's batch from filling all worker claims.
4. Monitor job age per tenant tier/lane, not just aggregate backlogs.
5. Reserve quota for latency-sensitive mail per policy.
6. Enforce deadlines; never send expired OTPs.

### Phase 5: testing and operations

1. Unit-test refills, bursts, and costs.
2. Integration-test concurrent workers reserving the same account key.
3. Test cross-tenant permissions and quota isolation.
4. Test Redis timeouts, failovers, TTLs, and policy reloads.
5. Test DB claims/leases and crash windows.
6. Test temporary SMTP throttles and unknown outcomes with sinks/test doubles.
7. Load-test multiple replicas and fairness under single-tenant bursts.
8. Add alerts for permit denials, backlog age, remaining quotas, and limiter errors.
9. Roll out via sandbox or a slice of eligible traffic first.
10. Measure provider-accepted throughput and tune safe caps from data.

### Acceptance criteria

| Requirement | Evidence needed |
|---|---|
| Never exceed account quota | Multi-replica rate tests and provider telemetry |
| Tenants cannot "borrow" unauthorized quota | Authorization tests and mapping policies |
| One tenant cannot starve others | Fairness/load tests by lane/tier |
| No lost emails on `DENIED` | Outbox persistence + recovery tests |
| No SMTP attempts without permits | Attempt counts and adapter mocks |
| No duplicates from simple claim races | DB concurrency/claim-token tests |
| Post-SMTP crashes never blindly retry | `UNKNOWN`/reconciliation tests |
| Redis outages never flood providers | Fail-closed tests |
| Daily quotas reset properly | Calendar/rolling-window tests matching provider policy |
| No recipient/credential leaks | Logging/security tests |
| Delayed jobs trigger alerts | Dashboards and alert drills |

## 44. Frequently asked questions

**How do per-tenant rate limiters differ from provider-account limiters?** Provider-account limiters protect shared vendor quotas, while tenant limiters partition capacity and enforce product tiers. On shared accounts, each job must pass both.

**If each tenant gets 5/s and the provider account allows 10/s, can we host 100 tenants?** Yes, provided **total submissions** stay capped at 10/s by the account gate with fair scheduling. Tenant caps are individual ceilings, not guarantees every tenant gets 5/s simultaneously.

**Do rate limiters automatically guarantee tenant fairness?** No. Limiters block overruns; job selection order and capacity sharing require fair schedulers or queue policies.

**Can `@Async` with `ThreadPoolTaskExecutor` enforce rate limits?** Not sufficiently. It provides async execution and local concurrency limits, not cluster-wide provider-account or tenant rate accounting.

**Does Spring Mail include a per-tenant rate limiter?** `JavaMailSender` handles SMTP submission only, with no awareness of tenants or provider quotas. You need an admission layer in the app/dispatcher or a dedicated service.

**Can `spring.mail.*` properties alone cap emails/second?** No. SMTP properties do not create token buckets, daily quota counters, or fair schedulers.

**If a tenant message has 20 recipients, how many tokens does it cost?** Depends on policy: an account recipient bucket may deduct 20, a tenant message bucket deducts 1, and a concurrency gate takes 1 slot. Define every unit explicitly.

**Why compute costs before SMTP?** The limiter must know how much capacity to reserve. With multi-recipient messages, counting `send` calls undercounts actual quota consumption.

**Should we split a message when cost exceeds burst capacity?** Only if business rules and providers allow; protect recipient privacy, Bcc semantics, and accurate per-group metering. Otherwise reject the invalid job/config.

**Does using Redis automatically make limiting distributed-safe?** No. You still need atomic reservations, properly scoped keys, TTL/failover policies, timeout handling, and consistent policy versions.

**Why must two Redis keys share a hash tag?** Redis Cluster allows atomic multi-key Lua execution only when keys map to the same hash slot. Hash tags colocate keys per account scope.

**What if a tenant has an org-wide quota across multiple provider accounts?** Coordinate a global tenant quota alongside account quotas; never assume scripts touching keys in separate cluster slots are atomic.

**Can each replica keep its own local rate limiter?** Only when total limits are safely partitioned and replica counts stay controlled. On shared accounts, independent local buckets exceed quotas during autoscaling.

**Does adding extra SMTP credentials increase quotas?** Not necessarily. Multiple credentials often share one account/organization limit. Scope quota keys to the vendor's published boundary.

**Do token buckets enforce daily sending limits automatically?** No. Add dedicated window-based budget counters, especially when providers use rolling 24-hour limits.

**Why not refund tokens whenever `MailSendException` is thrown?** The provider may have accepted or partially metered the send despite client errors. Refunding without proof breaks quota accounting.

**When the rate gate errors, should we keep sending to avoid losing mail?** With a durable outbox, jobs stay safe without sending. Failing closed is usually safer; emergency fallbacks need explicit cluster-wide budgets.

**Should `DENIED` increment `attempt_count`?** No, if SMTP was never called. Use a separate deferral counter so `attempt_count` reflects actual submission tries.

**Does SMTP `421` always mean rate limiting?** No. `421` can indicate service unavailability or connection closure. Classify using provider responses, protocol phase, and vendor docs.

**Does HTTP `429` apply to SMTP?** HTTP `429` belongs to HTTP APIs. SMTP has its own reply/status codes; never treat "SMTP 429" as a universal code.

**How do we stop retry storms when providers throttle?** Persist `available_at`, apply exponential backoff/jitter, enforce max retries, and re-acquire quota permits on later attempts. Never spin in a `while` loop.

**What if an email was accepted yet the DB crashed before updating?** The outcome may be `UNKNOWN`. Never resend blindly; reconcile via provider traces, idempotency where supported, and duplicate-risk policies.

**Can `Message-ID` guarantee exactly-once delivery?** No. `Message-ID` aids correlation, yet SMTP servers/receivers do not guarantee deduplication by that header.

**Do rate limiters automatically make OTP emails fast?** Not on their own. Combine reserved capacity/priority, fair scheduling, expiry checks, and suitable provider SLAs.

**Is a growing backlog with zero SMTP errors a problem?** Possibly. The limiter may be blocking accurately while demand exceeds quota; you still need capacity planning and job-age alerts.

**Should tenants adjust rate limits through a public API?** Only as an authorized feature bounded by contractual caps and server-side validation. Tenants must never modify other accounts or bypass hard limits.

**Can we put tenant IDs in Prometheus labels?** Only for small, fixed tenant counts; high cardinality drives up cost and operational pain. Aggregate by tier/lane and query authorized stores for tenant specifics.

**How do we test rate limits without sending real spam?** Use fake clocks in unit tests, Redis/PostgreSQL integration tests, and SMTP sinks/fake adapters to count submissions and simulate errors.

**What must happen when changing quotas at runtime?** Version policies, sync across replicas, adjust existing bucket tokens/capacities, and ensure transitions never breach safe provider quotas.

**Does failing over to another provider need separate rate limiting?** Yes. Provider B has different sender permissions, quota scopes, and limits—or may share an organization budget. Never switch routes while A's outcome is `UNKNOWN`.

## 45. Summary

In **Spring Framework Mail**, "account or tenant rate limiters" form a **multi-layered design pattern**, not just a library throttling `JavaMailSender.send(...)` calls.

Cooperating layers:

~~~text
Authorized business intent
         |
         v
Durable mail outbox
         |
         v
Fair dispatcher by tenant/lane
         |
         v
Resolve provider account + tenant policy
         |
         v
Atomic hierarchical rate admission
  +-- provider account rate
  +-- tenant or tenant-tier budget
  +-- daily quota when applicable
         |
         v
SMTP concurrency control
         |
         v
JavaMailSender.submit
         |
         v
Classified submission outcome
  +-- SUBMITTED
  +-- RETRY with backoff
  +-- FAILED
  +-- UNKNOWN for reconciliation
         |
         v
Audit, metrics, alerts, recovery
~~~

**Key principles:**

1. **Provider account limits are the overall ceiling**; tenant budgets allocate and cap shares underneath—neither replaces the other.
2. **Match scopes and units:** separate credentials do not mean separate quotas; recipients differ from messages; rate differs from concurrency and daily quotas.
3. **Atomic admission:** when a job needs both account and tenant tokens, never deduct partially across buckets.
4. **Distribute properly:** multiple pods must share quota state with managed TTLs, failovers, clocks, and policy versions.
5. **Never drop send intents:** `DENIED` simply defers jobs in the outbox without sleeping threads or discarding work.
6. **Fairness is a scheduling concern:** use round-robin, weighted, or deficit scheduling so large tenants cannot starve workers.
7. **SMTP retries are neither free nor side-effect safe:** manage backoff/jitter, permanent errors, and `UNKNOWN` outcomes to curb duplicates.
8. **Observe all three dimensions:** demand/backlogs, admission/denials, and provider-accepted throughput, alerting on SLAs.
9. **Protect tenant and recipient data:** derive quota keys from server-side identity, keeping emails and credentials out of logs and metrics.

Implemented consistently, the system serves many tenants across one or more mail accounts while protecting quotas, keeping critical emails timely, recovering from outages, and allocating capacity fairly. Success is measured not only in emails per second, but in **enforcing quota boundaries, fairness, durability, and explainability for why each job ran or waited**.
