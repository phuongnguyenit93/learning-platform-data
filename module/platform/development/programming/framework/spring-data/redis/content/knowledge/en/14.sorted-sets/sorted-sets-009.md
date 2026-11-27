# Limitations of Delayed Queues Built with Sorted Sets

## 1. The Problem and the Boundaries of Redis Sorted Sets

A **delayed queue** holds jobs created ahead of time that only become **eligible for processing after a scheduled timestamp**. Examples include sending a payment reminder email after 15 minutes, retrying a webhook after 30 seconds, expiring a reservation after 10 minutes, or triggering a user-scheduled task.

Redis **Sorted Sets** (ZSETs) are often chosen as the foundation because every element (*member*) has a **score**, and Redis maintains ascending order by score. In a delayed queue, you can store the **job ID** as the member and the **earliest eligible execution timestamp** as the score.

~~~text
ZSET: dq:{email}:scheduled

score (Unix milliseconds)    member
--------------------------------------
1800000000000                mail:101
1800000003000                mail:102
1800000030000                mail:103

smaller score → eligible to run earlier
~~~

When **nowMillis = 1800000005000**, jobs **mail:101** and **mail:102** are due, while **mail:103** is not yet due.

The critical takeaway:

> A Sorted Set only provides score-based ordering along with member query/update operations. It does not automatically become a message queue with timers, acknowledgments, visibility timeouts, retries, dead-letter handling, or exactly-once processing.

A reliable delayed queue must decide what happens if two workers pick up the same job, a worker crashes after claiming a job, an external API executes before Redis receives an ack, Redis fails over, or a massive burst of jobs becomes due simultaneously.

## 2. What Operations Does a Redis Sorted Set Actually Support?

| Command | Role in a delayed queue | Limitation |
|---|---|---|
| **ZADD** | Enqueue job ID with scheduled run timestamp score | Does not send notifications when due |
| **ZRANGE ... BYSCORE** | Find jobs with score ≤ current time | Read-only; does not claim |
| **ZRANGEBYSCORE** | Older syntax for querying by score | Does not automatically claim jobs |
| **ZRANGE key 0 0 WITHSCORES** | Peek at the earliest job and its due time | Does not sleep until the exact timestamp |
| **ZREM** | Remove a job from the ZSET | Does not know whether external work succeeded |
| **ZCARD** | Count total jobs currently in the ZSET | Does not distinguish due from future jobs |
| **ZCOUNT key -inf now** | Count jobs whose score is due | Does not represent in-flight jobs |
| **ZSCORE** | Check a specific job's scheduled run time | Does not report execution outcome |
| **ZPOPMIN** | Retrieve and remove the lowest-score member | May pop a job that is not due yet |
| **BZPOPMIN** | Wait while ZSET is empty, then pop lowest-score member | Does not wait until score ≤ now |

Since Redis 6.2, **ZRANGE ... BYSCORE** can replace **ZRANGEBYSCORE** queries. Examples in this lesson use the newer syntax where appropriate.

### 2.1. A Timeline

~~~text
Current time             Job A         Job B        Job C
     |                     |             |            |
     v                     v             v            v
-----+---------------------+-------------+------------+----> time
  09:00                 09:05         09:10        09:30
     |
     +-- Producer writes ZADD A, B, C

  09:04:59 -> no jobs are due yet
  09:05:00 -> A is eligible to be claimed
  09:10:00 -> B is eligible to be claimed
  09:30:00 -> C is eligible to be claimed
~~~

Redis does not spawn callbacks or per-member timers. A worker or scheduler must watch the clock, detect due scores, and claim jobs.

### 2.2. Complexity

**ZADD** takes roughly **O(log N)** per element; bounded score-range queries using **ZRANGE ... BYSCORE LIMIT** typically take **O(log N + M)**, where **M** is the number of returned elements. This is a major advantage when finding a few near-due jobs among millions of members.

Still, if one million jobs become due at the same time, total execution work still scales to one million jobs. Sorted Sets speed up **finding order**, not performing the actual job execution.

## 3. Data Layout and Time Representation

One possible layout:

~~~text
dq:{email}:scheduled     ZSET  jobId -> runAtMillis
dq:{email}:processing    ZSET  jobId -> leaseUntilMillis
dq:{email}:leaseTokens   HASH  jobId -> claimToken

job:mail:101             Job payload and status
job:mail:102             Job payload and status
~~~

The **dq:{email}:...** keys share the **{email}** hash tag so multi-key scripts stay on the same Redis Cluster hash slot. Do not funnel every job in the entire system into a single hash tag if that creates a hot node; at larger scale you may need partitioning.

Store a **unique job ID** as the member and keep the payload in a separately managed data store. Embedding long JSON directly into the member means changing payload fields makes Redis treat it as a new member, complicating cancellation, retries, deduplication, and state reconciliation.

### 3.1. Scores Use Unix Timestamps in Milliseconds

~~~java
import java.time.Duration;
import java.time.Instant;

Instant runAt = Instant.now().plus(Duration.ofMinutes(15));
long runAtMillis = runAt.toEpochMilli();
~~~

Redis stores ZSET scores as 64-bit floating-point numbers; integers within **±2^53** are represented exactly. Current Unix millisecond timestamps fit inside that range. Do not use huge Unix nanoseconds and assume the score preserves single-nanosecond precision.

Standardize on **milliseconds** across producers, Redis, and workers. If one side writes **epoch seconds** while another compares **epoch milliseconds**, jobs can fire way too early or stall for years.

If a user schedules 08:00 local time in a zone with daylight saving time, the application must resolve timezone and DST rules first and convert to an **Instant**. Redis has no awareness of timezones from a numeric score.

### 3.2. Two Jobs with the Same Score Are Not Ordered FIFO

Redis orders members sharing the same score lexicographically by the binary bytes of the member itself:

~~~redis
ZADD dq:{demo}:scheduled 1800000000000 job:b
ZADD dq:{demo}:scheduled 1800000000000 job:a
ZRANGE dq:{demo}:scheduled 0 -1
~~~

The order will be **job:a** then **job:b**, even though job:b was added first. If strict FIFO is required for jobs due at the same instant, design an explicit sequence/tie-breaker convention and atomic sequence allocation; timestamps alone do not give enqueue-order FIFO.

A member appears only once in a ZSET. Calling **ZADD** twice with the same job ID and a different score **reschedules the job** rather than creating two copies to run twice. For recurring tasks, assign distinct IDs per occurrence or use an explicit recurrence model.

## 4. How to Build a Minimal Queue

### 4.1. Producer Enqueues Jobs

~~~redis
ZADD dq:{email}:scheduled 1800000000000 mail:101
ZADD dq:{email}:scheduled 1800000003000 mail:102
ZADD dq:{email}:scheduled 1800000030000 mail:103
~~~

Scores can be updated via ZADD—for instance, rescheduling mail:103. In a system with concurrent workers, verify whether a job is already processing before rescheduling; running ZADD on `scheduled` does not recall an already-running job.

### 4.2. Worker Reads Due Jobs

With **nowMillis = 1800000005000**:

~~~redis
ZRANGE dq:{email}:scheduled -inf 1800000005000 BYSCORE LIMIT 0 10
~~~

Or using the older syntax:

~~~redis
ZRANGEBYSCORE dq:{email}:scheduled -inf 1800000005000 LIMIT 0 10
~~~

Redis returns up to ten members whose scores fall in the specified range, ordered by score. However, this command only **reads**; it does not mark them in-progress or grant ownership. Two separate workers can both receive **mail:101** from this read.

To peek at the earliest job for calculating sleep duration:

~~~redis
ZRANGE dq:{email}:scheduled 0 0 WITHSCORES
~~~

If a producer inserts a new job with an earlier score, a sleeping worker is not automatically woken by Redis. This highlights one of the first design limitations.

## 5. Limitation 1: Polling Introduces Latency or Background Load

A worker loop might run:

~~~text
while running:
    now = currentTimeMillis()
    due = ZRANGE scheduled -inf now BYSCORE LIMIT 0 batchSize
    claim and process due
    sleep(pollInterval)
~~~

### 5.1. Poll Interval Partially Determines Scheduling Latency

If polling every **5 seconds**, a job becoming due right after a poll can wait nearly 5 seconds just to be discovered, before counting queue backlog and execution time:

~~~text
09:00:00  worker polls, no jobs due
09:00:01  job A becomes due
09:00:05  worker polls, discovers A
          -> discovery lag of roughly 4 seconds
~~~

Lowering the interval to 100 ms reduces latency under normal conditions, yet increases Redis queries even when idle.

Suppose **50 workers** poll **10 times/second**:

\[
50 \times 10 = 500\ \text{queries/second}
\]

That is 500 checks per second even while the queue is empty. If every business domain has its own queue, total polling traffic grows further.

### 5.2. Adaptive Polling and Wakeup Signals

One implementation pattern:

- While due jobs remain, keep claiming batches within concurrency bounds.
- When no jobs are due, read the smallest score and sleep until near the next due time, capped by a **maximum sleep interval**.
- When a producer adds an earlier-due job, publish a **Pub/Sub notification** or signal hinting workers to wake up.
- Keep fallback polling, because Redis Pub/Sub is not durable delivery; disconnected subscribers can miss signals.

If jobs must start within a few milliseconds of target time, account for clock skew, network latency, JVM scheduling, failovers, and system load. Sorted Sets plus polling do not guarantee hard real-time timing.

## 6. Limitation 2: Two Workers Can See the Same Job

This code is tempting to write:

~~~java
Set<String> due = zsets.rangeByScore(
    queueKey,
    Double.NEGATIVE_INFINITY,
    (double) System.currentTimeMillis(),
    0,
    1
);

if (due != null && !due.isEmpty()) {
    String jobId = due.iterator().next();
    zsets.remove(queueKey, jobId);
    process(jobId);
}
~~~

Yet **rangeByScore → remove → process** consists of separate operations:

| Step | Worker A | Worker B |
|---|---|---|
| 1 | ZRANGE sees mail:101 | |
| 2 | | ZRANGE also sees mail:101 |
| 3 | ZREM mail:101 returns 1 | |
| 4 | | ZREM mail:101 returns 0 |
| 5 | Processes mail:101 | If ZREM result is ignored, may still process it |

Checking **ZREM == 1** avoids duplicate execution in this narrow race, yet reading and removing remain separate round trips requiring contention retries. Worse still, **deleting a job before processing loses the job if the worker crashes**.

### 6.1. Why Are ZPOPMIN and BZPOPMIN Insufficient?

**ZPOPMIN** atomically retrieves and removes the lowest-score member in one command. However, it **does not check whether the score is due yet**:

~~~redis
ZADD dq:{demo}:scheduled 1800000030000 future:job
ZPOPMIN dq:{demo}:scheduled 1
~~~

It will still pop **future:job** immediately even when the ZSET only holds future jobs.

**BZPOPMIN** blocks while the ZSET *has zero members*. The moment the ZSET has a member—even scheduled for tomorrow—it pops it immediately. **Blocking** here does not mean waiting until **score <= now**.

Similarly, other pop-min commands pop the minimum element without understanding a delayed queue's “not before timestamp” semantics.

## 7. Atomic Claiming via Lua Script

A Lua script checks the due score and removes the job within **one server-side execution**:

~~~lua
-- KEYS[1] = scheduled ZSET
-- ARGV[1] = nowMillis
local due = redis.call(
    'ZRANGE', KEYS[1], '-inf', ARGV[1],
    'BYSCORE', 'LIMIT', 0, 1
)

if #due == 0 then
    return nil
end

local jobId = due[1]
if redis.call('ZREM', KEYS[1], jobId) ~= 1 then
    return nil
end

return jobId
~~~

While the script runs, other workers' commands cannot interleave between locating the job and ZREM. When called via Spring Data Redis, **null** means no due jobs; a String return is the claimed job ID removed from `scheduled`.

**Yet this is still not a reliable queue.** The script only makes claiming atomic. A failure after claiming still drops the job:

~~~text
ZSET scheduled
    |
    | atomic claim, ZREM
    v
Worker A receives job ID in RAM
    |
    +-- succeeds -------------> done
    |
    +-- worker crashes -------> job already removed from scheduled
                                no state left to reschedule it
~~~

Such an **at-most-once attempt** design may be acceptable for non-critical tasks; for payments, data sync, or must-not-drop workflows, you need a processing state and recovery mechanism.

## 8. Limitation 3: You Need Processing State, Leases, and Acknowledgments

A stronger model keeps two Sorted Sets:

~~~text
scheduled:  jobId -> runAtMillis
processing: jobId -> leaseUntilMillis
~~~

A **lease** is the ownership expiration time of a single claim. The worker moves the job from `scheduled` to `processing`; upon finishing, it must **ack**. If the worker crashes and the lease expires, another process detects the stalled job and reschedules it for retry.

### 8.1. Atomic State-Transition Claim

Illustrative script:

~~~lua
-- KEYS[1] = dq:{email}:scheduled
-- KEYS[2] = dq:{email}:processing
-- KEYS[3] = dq:{email}:leaseTokens
-- ARGV[1] = nowMillis
-- ARGV[2] = leaseUntilMillis
-- ARGV[3] = unique token for this claim attempt

local due = redis.call(
    'ZRANGE', KEYS[1], '-inf', ARGV[1],
    'BYSCORE', 'LIMIT', 0, 1
)

if #due == 0 then
    return nil
end

local jobId = due[1]
redis.call('ZREM', KEYS[1], jobId)
redis.call('ZADD', KEYS[2], ARGV[2], jobId)
redis.call('HSET', KEYS[3], jobId, ARGV[3])
return jobId
~~~

This script assumes all keys reside on the same instance/hash slot and that only components obeying the state machine mutate state. This is still **only one piece of the queue**: it lacks heartbeats, acks, reclaimers, retries, cancellation, and payload synchronization.

~~~text
scheduled --[claim]--> processing (leaseUntil)
                           |
                     worker executes
                           |
                +----------+-----------+
                |                      |
             succeeds               fails/crashes
                |                      |
            ack(token)             lease expires
                |                      |
        remove processing          reclaimer
                                       |
                                 retry / DLQ
~~~

### 8.2. Acks Must Verify the Current Owner

Suppose worker A claims a job and takes longer than its lease. A reclaimer assigns the same job to B. If A finishes late and blindly calls **ZREM processing jobId**, it can delete B's active processing state.

A unique **per-claim** token rejects stale acks:

~~~lua
-- KEYS[1] = processing ZSET
-- KEYS[2] = leaseTokens HASH
-- ARGV[1] = jobId
-- ARGV[2] = claimToken

local token = redis.call('HGET', KEYS[2], ARGV[1])
if token ~= ARGV[2] then
    return 0
end

redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('HDEL', KEYS[2], ARGV[1])
return 1
~~~

Checking the token and deleting in one Lua script closes the gap between owner verification and state removal. Still, the token **only protects Redis state**; worker A might have already called an external API after losing its lease. Protecting external side effects requires idempotency or fencing/version checks enforced by the **target system**.

### 8.3. Choosing Lease Duration

Too short a lease causes healthy, unfinished work to be reclaimed and executed twice. Too long a lease forces crashed jobs to wait too long before recovery.

Useful techniques:

- Base leases on p95/p99 processing time and business SLAs.
- **Heartbeat/renew lease** conditionally while the current token remains valid for long jobs.
- Enforce explicit execution timeouts; workers must not hold jobs indefinitely.
- Bound attempts, configure retry delays, and send to dead-letter storage after max failures.

All lease-renewal operations must ensure only the current owner can extend the lease.

## 9. Reclaimers and State Machines: Rescuing Unfinished Jobs

A **reclaimer** scans jobs in **processing** where **leaseUntilMillis <= nowMillis**:

~~~redis
ZRANGE dq:{email}:processing -inf 1800000005000 BYSCORE LIMIT 0 100
~~~

This is only the **discovery** step. A complete reclaimer must atomically:

1. Verify the lease is still expired at reclaim time, avoiding overwriting a worker that just renewed.
2. Confirm the job is still in a retryable state, not already cancelled or completed.
3. Increment attempt count per rules and compute the retry timestamp.
4. Clear old owner/token information.
5. Move the job from processing back to scheduled, or to **dead-letter** storage if retry limits are exceeded.
6. Record failure status/reason for observability and investigation.

If two reclaimers run **ZRANGE → ZREM → ZADD** across multiple commands, they race with each other. A worker renewing its lease right as a reclaimer reads must also be handled cleanly. State transitions must verify conditions **atomically with the write**, typically via Lua/Redis Functions or an equivalent mechanism.

### 9.1. State Machine Model

~~~text
CREATED
   |
   v
SCHEDULED ----[cancel]-------------------------> CANCELLED
   |
   | runAt <= now, claim
   v
PROCESSING ----[success + ack]-----------------> COMPLETED
   |
   +----[retryable error]-------> SCHEDULED
   |
   +----[lease expired]---------> SCHEDULED
   |
   +----[max retries exceeded]--> DEAD_LETTER
~~~

A state machine is a **business convention**, not something Redis Sorted Sets enforce automatically. When producers, workers, reclaimers, and cancel/reschedule APIs coexist, every component must honor the same states, versions, and update permissions.

### 9.2. Recovery Does Not Mean the Job Never Ran

A worker can complete external side effects successfully yet fail to ack Redis in time. The reclaimer only sees an expired lease, unaware of whether external side effects succeeded. Retrying can execute the job twice. This leads directly to the next limitation.

## 10. Limitation 4: No End-to-End Exactly-Once Guarantee

| Guarantee | Meaning | With a DIY ZSET queue |
|---|---|---|
| **At-most-once** | Jobs can be lost after claim; low risk of intentional replay | Remove from scheduled before processing; drops jobs on crash |
| **At-least-once** | Avoids dropping jobs; accepts duplicate execution | Requires processing state, leases, acks, retries, and recovery |
| **Exactly-once effect** | Business side effect at target occurs strictly once | Cannot be achieved by Redis commands alone |

Example:

~~~text
Worker A claims job:payment:42
      |
      v
Calls payment gateway -> succeeds
      |
      v
Worker dies before acking Redis
      |
      v
Lease expires; reclaimer moves job back to scheduled
      |
      v
Worker B claims job and calls payment gateway again
~~~

From Redis's perspective, the job was never acked and deserves a retry. From the payment gateway's perspective, the charge already happened. **Redis has no atomic transaction spanning an external HTTP API**, and a Redis claim token alone cannot prevent double charges.

Common mechanisms to combine:

- Business-stable **idempotency keys**, e.g., **payment:order-42**, enforced by the target system to reject duplicates.
- Database tables recording job outcomes with unique constraints and proper transactions.
- **Outbox/inbox patterns** when syncing domain writes with event dispatch.
- **Fencing tokens/versions** checked by the target resource to reject stale-lease workers.
- Compensation or reconciliation workflows when external targets cannot provide exactly-once effects.

A practical rule of thumb is **at-least-once processing + idempotent handlers**. Define “success” at the business layer: ack Redis only after recording proof that the side effect succeeded, while still preparing for ack failures.

## 11. Limitation 5: Time, Clocks, and Key TTLs

### 11.1. Clock Skew Between Producers and Workers

A producer schedules due time via:

~~~java
long runAtMillis = Instant.now()
    .plusSeconds(30)
    .toEpochMilli();
~~~

A worker passes **System.currentTimeMillis()** into the Lua claim script. If the worker host's clock runs 15 seconds ahead of the producer's, the job can be claimed early relative to the scheduling clock.

Standardize on one time convention, keep instance clocks synchronized (UTC/Unix milliseconds). Designs can also read **TIME** from the Redis server when comparing against a single data-side clock, provided it matches the Redis server/driver and script contract.

### 11.2. “Due” Differs from “Started” and “Completed”

**runAtMillis = T** only denotes the *earliest eligible start time*. It does not guarantee a worker is alive at T, CPU is free at T, or side effects finish at T.

~~~text
runAt       actualStart            actualFinish
  |              |                       |
  v              v                       v
--+--------------+-----------------------+----> time
      queue lag       execution time
~~~

A delayed queue must define SLAs around **start lag**, **completion lag**, or actual business deadlines. Storing a score alone does not measure these lags.

### 11.3. Never Use ZSET EXPIRE as a Per-Job Timer

~~~redis
EXPIRE dq:{email}:scheduled 3600
~~~

This deletes the **entire Redis key** after one hour, wiping out jobs scheduled for tomorrow too. **A member's score is not a TTL**, and Redis does not pop members when their scores pass.

Similarly, if a job's separate payload key has a 30-minute TTL while runAt is two hours away, the worker can claim a job ID whose payload already vanished. Payload retention must cover **scheduled delay, retries, lease duration, DLQ, and investigation needs**.

### 11.4. Slow Tasks and Daylight Saving Time

A job scheduled for “8:00 AM tomorrow” depends on the **user's timezone** and can encounter non-existent or repeated local times across DST transitions. Resolve calendar rules in the application, store a concrete **Instant** as the score, and persist the timezone/schedule definition separately to compute future recurrences.

Never compute daily recurring schedules by blindly adding **24 hours** when the business rule is “8:00 AM local time daily” in DST regions.

## 12. Limitation 6: Backlogs, Fairness, and Starvation

### 12.1. Due Jobs Can Wait a Long Time

Suppose a worker pool handles at most **50 jobs/second**, and **10,000 jobs** all become due at 10:00.

\[
\frac{10000}{50} = 200\ \text{seconds}
\]

Even with zero overhead, clearing that burst takes at least ~200 seconds. Redis orders scores accurately, yet does not create extra worker capacity.

Measure **scheduling lag**:

\[
\text{lagMillis} = \text{actualStartMillis} - \text{runAtMillis}
\]

and track p50/p95/p99 lag per job type. Monitoring only Redis command latency hides multi-minute queue backlogs even while Redis responds in milliseconds.

### 12.2. One Shared Queue Can Lack Fairness

~~~text
scheduled queue:
  5,000 due webhooks
  20 due payment reminder emails
  100 due scheduled reports
~~~

If workers always pick the earliest score and webhooks fill all slots, emails can suffer severe delays. Sorted Sets do not manage fairness across tenants, priorities, job types, or execution costs.

Consider:

- Separate queues/partitions for workloads with distinct SLAs.
- Dedicated worker pools and concurrency limits for heavy vs. lightweight jobs.
- Per-tenant or per-destination rate limits.
- Weighted priority scheduling across multiple queues.
- Capping batch claims so one worker does not hoard jobs.

Creating too many queues increases polling load and operational complexity. Partition based on real load and fairness requirements rather than splitting mechanically.

### 12.3. Score Order Alone Is Not Enough for Strict Priority

When two jobs have the same score, Redis uses binary member lexicographical order, not enqueue-time FIFO. If you need **priority first, then timestamp**, design composite scores/members or separate structures, and guard against starvation when high-priority work arrives continuously.

## 13. Limitation 7: Data Durability and Failover

### 13.1. A Successful ZADD Does Not Automatically Mean Durable Storage

A command succeeding on a Redis primary does not guarantee every replica received it or that it survives every crash. Check **AOF/RDB**, fsync policies, replication, failover behavior, backups, and recovery time.

When a failover occurs near **schedule/claim/ack**, the application can observe state inconsistent with what it believed finished earlier. Recovery and idempotency must account for these failure windows.

### 13.2. Eviction Can Wipe Out Queues

If Redis is configured as a cache with a **maxmemory eviction** policy, queue keys can be evicted under memory pressure. Critical jobs should not rely on a ZSET surviving forever in an eviction-enabled cache without strict retention, noeviction/dedicated instances, and recovery mechanisms.

For high-durability workloads, a database can act as the job source of truth while Redis Sorted Set serves as a **rebuildable schedule index**. If Redis loses data, run reconciliation/rebuild from durable storage.

### 13.3. Metadata Inconsistency

Example:

~~~text
dq:{email}:scheduled   contains mail:101
job:mail:101            email payload already expired or deleted
~~~

A worker claims the ID yet cannot process it. This is a data-modeling bug, not a ZRANGE bug. Align payload and state lifecycles with **runAt**, retries, and completion, avoiding deleting payloads before jobs finish or are investigated.

## 14. Limitation 8: Syncing Payloads, Job Status, and Schedules

Suppose a producer writes a job to PostgreSQL and then schedules it in Redis:

~~~text
INSERT job in PostgreSQL
           |
           v
ZADD scheduled in Redis
~~~

If the process crashes between steps, SQL has the job while Redis has no schedule. Reversing the order leaves Redis holding an ID whose SQL payload does not exist yet.

**Redis transactions/Lua cannot span an external database**, making this a classic **dual-write** problem.

### 14.1. Outbox and Reconciliation

When a database is the primary source of truth, one approach:

1. Persist both the **job** and an **outbox record** in one database transaction.
2. A dispatcher reads the outbox and schedules in Redis using a stable job ID.
3. The dispatcher marks the outbox entry sent after confirmation, retrying on errors.
4. Apply deduplication/schedule-version rules to prevent unintended extra runs.
5. Run **reconciliation** to fix missing Redis schedules, cancelled jobs, or post-failover drift.

This pattern still needs policies for jobs rescheduled before the outbox dispatches, or completed before a dispatcher retry.

### 14.2. Rescheduling with ZADD Can Recreate a Scheduled Entry While Processing

~~~redis
ZADD dq:{email}:scheduled 1800000600000 mail:101
~~~

If **mail:101** was already claimed into `processing`, this command creates `mail:101` again in `scheduled` while the active worker is still running—creating two concurrent executions for the same job ID.

Likewise:

~~~redis
ZREM dq:{email}:scheduled mail:101
~~~

only removes the job if it is still in `scheduled`; it **does not recall** side effects from a worker already executing. Cancellation and rescheduling must be governed by the state machine, versions/attempts, and coordinated against claim, heartbeat, and ack races.

## 15. Limitation 9: Retries, Backoff, and Dead-Letter Handling Must Be Built Yourself

| Failure type | Typical handling |
|---|---|
| Transient network drop | Bounded retries, backoff, and jitter |
| External API returns HTTP 429 | Honor Retry-After / rate limits if provided |
| Malformed payload or missing fields | Permanent failure; do not retry infinitely |
| Worker crash | Reclaim upon lease expiration |
| External API succeeded but Redis ack failed | May retry; handler must be idempotent |
| Repeated code failure on the same job | Dead-letter and investigate |

### 15.1. Exponential Backoff

Example schedule:

~~~text
attempt 1 -> wait ~1 second
attempt 2 -> wait ~2 seconds
attempt 3 -> wait ~4 seconds
attempt 4 -> wait ~8 seconds
...
~~~

Retry score calculation:

\[
\text{nextRunAt} = \text{now} +
\min(\text{baseDelay} \times 2^{\text{attempt}-1},\ \text{maxDelay})
+ \text{jitter}
\]

**Jitter** stops thousands of jobs from waking up together after an outage. Cap retry attempts, total lifetime, and define behavior when business deadlines pass.

### 15.2. Dead-Letter Storage

ZSETs do not provide dead-letter queues, attempt histories, exception tracking, or inspection dashboards. Your application must decide how to record:

- Last error and failure timestamp.
- Attempt count, worker/trace ID, job version.
- Payload reference (avoiding logging unnecessary secrets).
- How to replay or discard after investigation.
- Error data retention and access permissions.

When these capabilities are core requirements, a dedicated queue or workflow engine dramatically reduces custom infrastructure code.

## 16. Spring Data Redis: Scheduling and Inspecting with ZSetOperations

With Spring Boot using Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Local Redis configuration example:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

For string job IDs, **StringRedisTemplate** keeps serialization consistent and easy to inspect in redis-cli. A repository solely responsible for **scheduling, peeking due jobs, and metrics**:

~~~java
package com.example.jobs;

import java.time.Instant;
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Repository;

@Repository
public class RedisDelayedSchedule {

    private static final String SCHEDULED_KEY =
        "dq:{email}:scheduled";

    private final ZSetOperations<String, String> zsets;

    public RedisDelayedSchedule(StringRedisTemplate redis) {
        this.zsets = redis.opsForZSet();
    }

    public boolean schedule(String jobId, Instant runAt) {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("jobId is required");
        }
        if (runAt == null) {
            throw new IllegalArgumentException("runAt is required");
        }

        return Boolean.TRUE.equals(zsets.add(
            SCHEDULED_KEY,
            jobId,
            (double) runAt.toEpochMilli()
        ));
    }

    public Set<String> peekDue(Instant now, long batchSize) {
        if (now == null || batchSize <= 0) {
            throw new IllegalArgumentException("Invalid arguments");
        }

        return zsets.rangeByScore(
            SCHEDULED_KEY,
            Double.NEGATIVE_INFINITY,
            (double) now.toEpochMilli(),
            0,
            batchSize
        );
    }

    public Long scheduledCount() {
        return zsets.size(SCHEDULED_KEY);
    }

    public Long dueCount(Instant now) {
        return zsets.count(
            SCHEDULED_KEY,
            Double.NEGATIVE_INFINITY,
            (double) now.toEpochMilli()
        );
    }
}
~~~

Explanation:

- **opsForZSet().add(...)** maps to ZADD. Its Boolean indicates whether a **new** member was added; if the member already existed and only **changed score**, it returns **false** even though rescheduling succeeded. Do not use that Boolean alone to conclude a write failed.
- **rangeByScore(...)** fetches **due** jobs **without claiming ownership**. The name **peekDue** reflects this intent.
- **size(...)** maps to ZCARD, including jobs not yet due.
- **count(...)** maps to ZCOUNT over the score interval, useful for measuring due backlogs.

This sample code targets normal synchronous calls. Some Spring Data Redis APIs return **null** when queued inside a pipeline/transaction; do not assume the behavior above applies unchanged to every execution context.

**Never call process(jobId) directly after peekDue()** when multiple workers run. Jobs must be claimed via an atomic conditional mechanism and managed through the full lifecycle.

## 17. Spring Data Redis: Claiming Jobs via Lua Script

An adapter claiming jobs using the **scheduled → processing** model described earlier:

~~~java
package com.example.jobs;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Repository;

@Repository
public class RedisJobClaimer {

    private static final String SCHEDULED =
        "dq:{email}:scheduled";
    private static final String PROCESSING =
        "dq:{email}:processing";
    private static final String TOKENS =
        "dq:{email}:leaseTokens";

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<String> claimScript;

    public RedisJobClaimer(StringRedisTemplate redis) {
        this.redis = redis;
        this.claimScript = new DefaultRedisScript<>();
        this.claimScript.setResultType(String.class);
        this.claimScript.setScriptText("""
            local due = redis.call(
                'ZRANGE', KEYS[1], '-inf', ARGV[1],
                'BYSCORE', 'LIMIT', 0, 1
            )
            if #due == 0 then
                return nil
            end
            local jobId = due[1]
            redis.call('ZREM', KEYS[1], jobId)
            redis.call('ZADD', KEYS[2], ARGV[2], jobId)
            redis.call('HSET', KEYS[3], jobId, ARGV[3])
            return jobId
            """);
    }

    public Optional<ClaimedJob> claim(
            Instant now,
            Duration leaseDuration) {

        if (now == null || leaseDuration == null ||
                leaseDuration.isZero() || leaseDuration.isNegative()) {
            throw new IllegalArgumentException("Invalid claim arguments");
        }

        String token = UUID.randomUUID().toString();
        long nowMs = now.toEpochMilli();
        long leaseUntilMs = now.plus(leaseDuration).toEpochMilli();

        String jobId = redis.execute(
            claimScript,
            List.of(SCHEDULED, PROCESSING, TOKENS),
            Long.toString(nowMs),
            Long.toString(leaseUntilMs),
            token
        );

        return Optional.ofNullable(jobId)
            .map(id -> new ClaimedJob(id, token));
    }

    public record ClaimedJob(String jobId, String leaseToken) {}
}
~~~

Each piece has a clear role:

1. **DefaultRedisScript** holds the Lua script for Spring Data Redis to run on Redis; the adapter creates and reuses it once.
2. **KEYS[1]** is the scheduled ZSET; the script finds one member with score ≤ nowMillis.
3. **KEYS[2]** is the processing ZSET; the script sets the lease expiration time.
4. **KEYS[3]** stores the unique claim token for this attempt.
5. **Optional.empty()** means no due jobs exist on this claim pass.

Because all three Redis keys share the **{email}** hash slot, the script satisfies Redis Cluster multi-key slot constraints when supported by topology and client. Any payload/metadata keys also touched by the script must be passed in **KEYS** and obey the same rule.

**Limitations of this example:** this adapter only shows claiming. The full system still needs ack, heartbeat, reclaimer, cancel/reschedule, attempt limits, DLQ, outbox, and idempotent handlers. Furthermore, clocks are passed from Java, requiring clock-skew control across workers.

### 17.1. Why Isn't @Transactional Enough?

Putting **@Transactional** on a service does not turn Redis, PostgreSQL, and HTTP API calls into an atomic distributed transaction. Even Redis transactions require specific configuration and connection semantics.

Even with **MULTI/EXEC**, a queued read command cannot be inspected in Java before EXEC to decide what to write in the same transaction. For **selecting a due job and transitioning its state**, Lua or Redis Functions keep the condition and write inside one server-side execution boundary.

Lua also provides no automatic rollback for writes committed before a runtime error inside the script. Therefore, validate inputs clearly and keep script logic brief.

## 18. Reactive Redis Does Not Add Queue Semantics Either

In a WebFlux application, **ReactiveRedisTemplate** or **ReactiveStringRedisTemplate** operates on Redis via **Mono/Flux**, reducing thread blocking while awaiting network I/O.

However:

- Chaining **rangeByScore → remove** via **flatMap** still sends two separate Redis commands unless wrapped in an atomic mechanism.
- **Non-blocking** does not mean **exactly-once**, does not create visibility timeouts, and does not stop duplicate worker claims.
- **Flux** and backpressure do not handle retries, leases, or lost payloads.
- Calling **block()** on a WebFlux event loop defeats reactive benefits and causes blocking errors.

If building a reactive delayed queue, you must still uphold the exact same state machine and claim/ack/reclaim invariants. Switching to asynchronous APIs does not remove Sorted Set's fundamental limitations.

## 19. Monitoring: Counting Queue Size Is Not Enough

Measuring only **ZCARD scheduled** is misleading. A queue with 100,000 jobs scheduled for next week may be completely healthy, whereas a queue with only 15 jobs all overdue by 30 minutes is failing.

| Metric | Meaning |
|---|---|
| **scheduled_count** | Total jobs currently in the scheduled ZSET |
| **due_count** | Jobs already due via ZCOUNT |
| **processing_count** | Jobs claimed and awaiting ack |
| **expired_lease_count** | Jobs in processing whose lease has expired |
| **scheduling_lag_ms** | Time from runAt to actualStart |
| **execution_duration_ms** | Worker execution duration |
| **success/failure_rate** | Success vs. failure ratio |
| **retry_count** | Number of job retries |
| **dead_letter_count** | Jobs moved to terminal failure state |
| **claim_errors** | Command, Lua, timeout, key-type, or connection errors |
| **outbox_backlog** | Jobs in durable store not yet scheduled in Redis |

Example peeking at the earliest job:

~~~redis
ZRANGE dq:{email}:scheduled 0 0 WITHSCORES
~~~

Compare the score against current time to see how overdue it is. If `scheduled` is empty while `processing` holds thousands of expired leases, jobs are still stuck. Observe both states.

Track metrics by job type and tenant matching SLAs, while avoiding high-cardinality time-series labels per **job ID**.

To inspect queue keys, never run **KEYS dq:\*** on request paths or polling loops in large Redis databases. Maintain an explicit queue registry or use controlled SCAN for admin tasks.

## 20. Redis Cluster: Same Slot for Claiming, Easy to Hotspot

The Redis keys in our Lua script:

~~~text
dq:{email}:scheduled
dq:{email}:processing
dq:{email}:leaseTokens
~~~

all share the **{email}** hash tag. In Redis Cluster, keys in a multi-key script must map to the same hash slot; Redis does not turn multiple primaries into a cross-cluster atomic transaction.

If all jobs funnel into one huge ZSET on one slot, a single node becomes a hotspot. As load grows, consider partitioning:

~~~text
dq:{email-0}:scheduled / processing / leaseTokens
dq:{email-1}:scheduled / processing / leaseTokens
dq:{email-2}:scheduled / processing / leaseTokens
...
~~~

Each partition's **scheduled/processing/tokens** group keeps local claim atomicity. However, the system must manage partition fairness, worker assignment, retry/cancel routing, and which partition owns each job. You cannot assume a ZRANGE or script on partition 0 sees any job on partition 1.

## 21. When Are Sorted Sets Suitable, and When Do You Need Another Platform?

Sorted Sets can be a sensible choice if:

- Job and worker counts fit your current operational capacity.
- Polling latency is acceptable.
- Jobs can be retried safely or handlers are idempotent.
- The team is ready to own leases, acks, reclaimers, retries, DLQs, metrics, and state machines.
- The system can rebuild schedules/payloads from durable storage when needed.

For critical workflows or strict delivery guarantees, compare against alternatives:

| Approach | Strengths | Notes for delayed queues |
|---|---|---|
| **DIY Redis Sorted Set** | Easy to store runAt as score; fast due-job lookup | Must build most queue semantics yourself |
| **Redis Streams + consumer groups** | Built-in pending/ack/claim consumer groups | Stream messages do not release only at a timestamp; still needs a scheduling layer |
| **Database jobs table** | Can enlist job creation in business data transactions | Requires proper queries/indexes/locking and polling workers |
| **Message broker with delayed delivery** | Some products support delays, acks, retries, DLQs | Delay caps, ordering, and guarantees depend on product/config |
| **Job scheduler/workflow engine** | Manages lifecycles, dependencies, retries, and history | Higher operational footprint, far less custom plumbing |

If Redis is primarily used as a cache while jobs involve payments, order cancellations, or unrecoverable state, think carefully before making a ZSET the sole source of truth.

## 22. Common Misconceptions

### Misconception 1: BZPOPMIN Waits Until the Score Becomes Due

No. **BZPOPMIN** only waits until the ZSET has a member. A member scheduled for tomorrow will still be popped immediately once the queue is non-empty.

### Misconception 2: Atomic Lua Claim Means Jobs Can Never Be Lost

No. If claiming simply runs **ZREM and returns the ID**, a worker crash after claiming drops the job from scheduled. Atomic claiming only resolves worker contention inside Redis.

### Misconception 3: Having Leases Means a Job Never Runs Twice

No. An old worker may finish an external side effect before failing to ack, and the job gets reassigned after lease timeout. You need idempotency at the target system.

### Misconception 4: Equal Scores Mean FIFO

No. Redis orders tied members lexicographically by binary member bytes, not by ZADD insertion order.

### Misconception 5: Setting EXPIRE on the Queue Creates Delayed Messages

No. **EXPIRE** deletes the entire queue key; scores are not per-member TTLs.

### Misconception 6: Retrying Any Timed-Out Command Is Safe

No. The command or side effect may have succeeded while the client missed the response. Unprotected retries can duplicate side effects.

### Misconception 7: A Small ZCARD Means No Backlog

No. Jobs may be stuck in `processing` or a few due jobs may be severely overdue. Measure **due_count**, **expired leases**, and **lag**.

### Misconception 8: Rescheduling with ZADD Recalls an Already-Claimed Job

No. If a worker moved the ID into `processing`, calling ZADD on `scheduled` can create a duplicate schedule entry while the old job keeps running.

### Misconception 9: One Lua Script Runs Across Any Redis Cluster Slots

No. Multi-key scripts must obey same-hash-slot constraints. Forcing everything into one slot lets scripts run yet creates hotspots.

### Misconception 10: @Transactional Commits Redis and External APIs Together

No. A local transaction manager does not turn Redis, SQL, and HTTP side effects into an atomic distributed transaction.

## 23. Reasoning Exercises

### Exercise 1 — Two Workers Read the Same Job

Two workers both call **ZRANGE ... BYSCORE LIMIT 0 1** and receive **mail:101**. Why?

**Explanation:** ZRANGE is read-only. To grant exclusive ownership to one worker, use an atomic conditional claim operation and track post-claim state.

### Exercise 2 — Popping an Undue Job

A ZSET holds only a job with score **now + 10 minutes**. A worker calls **BZPOPMIN**. Will it receive the job immediately?

**Explanation:** Yes. Because the ZSET already has a member, BZPOPMIN returns it immediately even though its score is not due yet.

### Exercise 3 — Crash After Claim

A worker uses Lua **ZRANGE then ZREM**, then crashes before sending the email. Will the queue recover the job automatically?

**Explanation:** No. The job was deleted. You need `processing` state, leases, a reclaimer, and retry policies if jobs must not be dropped.

### Exercise 4 — Polling Load

There are **20 workers**, each polling **5 times/second**. When the queue is empty, how many checks per second hit Redis?

**Explanation:** Roughly **100 checks/second**. Load can be reduced with reasonable poll intervals, adaptive polling, and supplementary wakeup signals.

### Exercise 5 — Duplicate IDs

Calling **ZADD** twice with the same member **mail:101**, first with score 1000 and second with score 2000. How many members are in the ZSET?

**Explanation:** One member. The second call updates its score rather than creating a second independent run.

### Exercise 6 — Worker Clock 15 Seconds Fast

The producer uses an accurate clock, while a worker is 15 seconds fast and passes local time into Lua. What is the risk?

**Explanation:** The worker can claim jobs earlier than the intended business time. Standardize on a shared time source and clock synchronization.

### Exercise 7 — Stale Worker Ack

Worker A's lease expires; B reclaims the same job. A sends **ZREM processing** using only the job ID. What is the risk?

**Explanation:** A can delete the active state owned by B. Acks must verify the current claim token/version atomically.

### Exercise 8 — Side Effect Succeeded Before Retry

A worker calls a payment API successfully and dies before acking; the reclaimer returns the job to scheduled. What can happen?

**Explanation:** The payment API can be called a second time. Use idempotency keys or target-side duplicate protection.

### Exercise 9 — Backlog Clearing Time

8,000 jobs become due together, and the system processes 100 jobs/second. What is the minimum time to clear them?

**Explanation:** At least around **80 seconds**, excluding overhead and failures. Becoming due does not mean starting or finishing instantly.

### Exercise 10 — Queue TTL

A queue holds jobs scheduled for tomorrow, yet code calls **EXPIRE scheduled 3600**. What happens?

**Explanation:** After one hour, the whole ZSET can be deleted, losing every job in the key including tomorrow's jobs.

## 24. Decisions to Finalize Before Implementation

1. **Latency:** what maximum scheduling lag is acceptable and what polling interval fits?
2. **Durability:** is Redis the source of truth or backed by a database/outbox for recovery?
3. **Claiming:** can multiple workers compete for jobs; is claiming atomic?
4. **Leases:** how long are leases, are heartbeats needed, and who can renew?
5. **Ack:** what token/version confirms ownership of the current claim?
6. **Recovery:** how are crashed workers or Redis failovers detected and retried?
7. **Idempotency:** if a job runs twice, how does the target protect side effects?
8. **Retry/DLQ:** what are attempt limits, backoff, jitter, and failure investigation workflows?
9. **Cancel/reschedule:** how are jobs handled once already processing?
10. **Backpressure/fairness:** when bursts become due at once, how are workers allocated?
11. **Cluster:** do scripts stay within a single slot; do partitions cause hotspots?
12. **Monitoring:** are due_count, expired leases, and scheduling lag tracked?

If these questions remain unanswered, **ZADD + ZRANGE + ZREM** is only a bare minimum appointment table, not a delayed queue reliable enough for critical business operations.

## 25. References

- [Redis — Sorted Sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/)
- [Redis — ZADD](https://redis.io/docs/latest/commands/zadd/)
- [Redis — ZRANGE](https://redis.io/docs/latest/commands/zrange/)
- [Redis — ZPOPMIN](https://redis.io/docs/latest/commands/zpopmin/)
- [Redis — BZPOPMIN](https://redis.io/docs/latest/commands/bzpopmin/)
- [Redis — Lua scripting](https://redis.io/docs/latest/develop/interact/programmability/eval-intro/)
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Spring Data Redis — ZSetOperations](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/ZSetOperations.html)
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)

## 26. Summary

**Redis Sorted Sets** offer a compact way to store **earliest eligible execution times** as scores, query due jobs, and reschedule tasks. Spring Data Redis's **ZSetOperations** manipulates scores and members, while **RedisScript** can combine due-time checks and claiming into one atomic execution.

The main limitations lie in **job execution lifecycles**: polling adds latency and background load; pop commands do not wait for scores to become due; multiple workers can observe the same job; removing before processing drops jobs on crash; and leases/retries can cause duplicate execution. Sorted Sets also do not provide transactions spanning databases or external APIs, built-in dead-letter queues, or exact execution-time guarantees.

For simple tasks tolerant of minor imperfections, a ZSET is a pragmatic foundation. For critical workloads, design **processing states, leases, token-checked acks, reclaimers, retries, DLQs, monitoring, idempotency, and durable recovery**, or adopt a dedicated queue/workflow platform providing those guarantees out of the box.
