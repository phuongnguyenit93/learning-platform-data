# End-to-End Business Deadlines, Backoff, and Avoiding Multi-Layer Retry Amplification

> **Chapter:** Java Retries and Errors  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — understanding distributed Apache Cassandra, partition keys, query-driven table design, read/write consistency, CQL, replication, compaction, repair, error handling, and Java Driver connectivity.

Suppose a Java endpoint `POST /orders` calls two microservices, checks a quota, and writes to Cassandra. The API gateway waits at most 2 seconds. When Cassandra slows down, the gateway retries three times; Service A retries three times; Service B retries three times; and the Java Driver may try another coordinator. The user clicked **once**, yet the cluster receives **dozens of requests**. Right when the backend is overloaded, retries pour extra load onto it and stretch recovery time.

The problem is not simply “how many times should we retry?”. You must answer all of these together:

1. **How much time remains for the entire business operation?** Once the caller's deadline has passed, issuing a new CQL call usually has no value.
2. **Which errors may be retried?** A timeout never proves the mutation did not run; some operations are not idempotent.
3. **Who owns the authority to retry?** Driver, repository, service, HTTP client, gateway, and job queue must not multiply attempts independently.
4. **How long should we wait before retrying?** Exponential backoff with jitter must respect the deadline while relieving backend load.
5. **How do we tell whether retries help or hurt?** Measure CQL executions per business request, deadline misses, retry budgets, p99, and Cassandra overload signals.

**Technical scope:** Java Driver 4.x, specifically the **Apache Java Driver 4.19** docs; Cassandra 4.x–5.x. All configs and timing figures in this lesson are **lab design examples**, not production defaults for every cluster. Choose production settings from measured latency distributions, SLOs, RF/CL, GC/network health, and data requirements.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Define an **end-to-end business deadline** and distinguish it from individual HTTP or CQL request timeouts.
2. Calculate maximum backend attempts when multiple independent layers retry, including speculative executions.
3. Understand `DefaultRetryPolicy`, `basic.request.timeout`, `Statement.setTimeout`, and `setIdempotent` in Java Driver 4.x.
4. Apply **capped exponential backoff + full jitter**, attempt caps, and service-wide retry budgets.
5. Separate permanent config errors, transient failures, overload, ambiguous timeouts, and CAS conflicts.
6. Write Java using a monotonic clock to set timeouts from **remaining** time and never launch new requests past the deadline.
7. Design a single retry owner combined with load shedding, concurrency limits, and circuit breakers.
8. Measure and run fault-injection tests proving retries **preserve data correctness** and **do not amplify load excessively**.

## 2. An End-to-End Business Deadline Is Not a Single CQL Timeout

### 2.1. Timeout, deadline, and budget

| Term | Meaning | Example |
|---|---|---|
| **Step timeout** | Wait limit for one specific operation | One `session.execute()` call capped at 600 ms |
| **End-to-end business deadline** | Hard finish line for the whole request/workflow | HTTP call must finish within 1,500 ms of entering the gateway |
| **Remaining budget** | Time left at each checkpoint | After auth, validation, and cache: 880 ms remaining |
| **Reserve / guard band** | Buffer reserved for response serialization, logging, HTTP flush, or cleanup | Reserve the final 100–150 ms |
| **Retry budget** | Allowed extra attempt capacity, not just a per-request cap | Max 1 retry/request and service-wide retry rate within measured threshold |

For a sequential flow:

\[
T_{\text{business}} =
T_{\text{gateway}}+T_{\text{auth}}+T_{\text{service}}+
\sum T_{\text{CQL attempts}}+\sum T_{\text{backoff}}+
T_{\text{serialize}}.
\]

The **deadline** requires this total not to exceed the approved limit. If every component picks a 2-second timeout and every layer retries, total latency grows far beyond what users will wait for.

### 2.2. Illustrative 1,500 ms budget

| Elapsed since request arrival | Activity | Remaining budget |
|---|---|---:|
| 0 ms | Gateway receives request; total budget 1,500 ms | 1,500 ms |
| 120 ms | Auth and validation complete | 1,380 ms |
| 300 ms | Cache read and secondary call complete | 1,200 ms |
| 300 ms | Reserve 150 ms for response handling | **1,050 ms** for remaining data work |
| 900 ms | CQL stalls or fails after 600 ms | 600 ms total; only 450 ms before reserve |
| 950 ms | If retry owner exists and waited 50 ms backoff | 550 ms total; only 400 ms left for next try |
| 1,350 ms | Downstream work must stop before reserve | 150 ms left |
| 1,500 ms | Business deadline | 0 ms |

You **cannot** grant a 1,500 ms timeout to *every* CQL call starting at `t=900 ms`. That single call could finish at `t=2,400 ms` long after the caller stopped waiting.

General check before sending any downstream request:

~~~text
remaining = business_deadline - now
usable = remaining - response_reserve

if usable <= min_useful_attempt:
    fail_fast / return deadline exceeded
else:
    cql_timeout = min(configured_cql_ceiling, usable)
    send only the permitted request within this budget
~~~

If a retry owner exists, **both backoff and the next attempt** consume `usable`—never add a fresh timeout on top of the original deadline.

### 2.3. Monotonic clock in Java

A deadline **within the same JVM process** should measure elapsed time using `System.nanoTime()`, never wall-clock calls like `LocalDateTime.now()` subtracted: NTP clock steps, timezones, or DST can jump clocks backward or forward.

~~~java
long startedNanos = System.nanoTime();
long budgetNanos = java.time.Duration.ofMillis(1500).toNanos();

// Perform a business step.
long elapsedNanos = System.nanoTime() - startedNanos;
long remainingNanos = budgetNanos - elapsedNanos;
if (remainingNanos <= 0L) {
    throw new IllegalStateException("Business deadline exceeded");
}
~~~

`System.nanoTime()` **is not a UTC timestamp** and must never be sent raw across machines. Within one JVM, it is ideal for elapsed duration. When propagating deadlines over HTTP/gRPC:

- Either send an **absolute UTC deadline** across synchronized clocks while accounting for skew,
- Or send **remaining duration** (decremented by elapsed time) along with start/progress context; each hop starts a monotonic deadline **shorter than** the received budget rather than resetting to 1,500 ms.
- Where the protocol already provides standard deadline/context propagation (e.g., gRPC), prefer the framework mechanism over inventing custom headers.
- A hop must never “inflate” the deadline up to its own default timeout. Caller cancellation **does not mean the server stopped processing an in-flight mutation**.

## 3. Retry Amplification: Why Retrying at Every Layer Is Dangerous

### 3.1. Attempts multiply, they do not add

Suppose one business request crosses three layers, each allowing **3 total attempts** (including the initial attempt):

~~~text
HTTP Client:           3 attempts
    Service A:         3 attempts / client attempt
        Service B:     3 attempts / service A attempt
            Cassandra request

Worst case: 3 × 3 × 3 = 27 calls to B/Cassandra
~~~

If the Java Driver adds 2 executions on eligible errors, the theoretical bound reaches **54 CQL executions**, before counting speculative executions or background flows. Specific error types stop early, so this is a **design upper bound on attempts**, not a claim that `DefaultRetryPolicy` always retries every request.

A classic distributed-systems example: **5 layers, 3 attempts each ⇒ \(3^5 = 243\)** calls hitting the bottom layer for one user action. **Watch the wording:** “3 attempts” means *1 initial + 2 retries*. If someone writes “3 retries” meaning *3 retries after the first try*, each layer has 4 attempts.

\[
A_{\text{deepest}}^{\max} = \prod_{i=1}^{n} A_i,
\]

where `A_i` is the total attempts allowed at layer `i`, including the first attempt. With speculative execution, each driver call can fire **multiple parallel executions**, each with its own retry paths, pushing amplification higher still.

### 3.2. Sample amplification table for one request

| Retry configuration | Max deepest-layer attempts | Observation |
|---|---:|---|
| Gateway 1, service 1, Driver 1 | 1 | Zero amplification |
| Gateway 2, service 1, Driver 2 | 4 | Top layer and Driver both retry |
| Gateway 3, service 3, Driver 2 | 18 | High risk of severe load amplification |
| Four layers at 3 attempts each | 81 | Retry storm under correlated errors |
| Five layers at 3 attempts each | 243 | Never design as a default |

**Multiplying requests does not multiply total wall time linearly** due to parallelism and early timeouts, yet the backend still pays in pool slots, coordinator work, replica reads/writes, CPU, network, and tombstone/compaction pressure.

### 3.3. Negative feedback loop when the backend is overloaded

~~~mermaid
flowchart TD
    A["Cassandra slow / replica fault"] --> B["Timeouts and 5xx climb"]
    B --> C["Gateway + service + driver all retry"]
    C --> D["CQL attempts/s and in-flight requests surge"]
    D --> E["CPU / network / queues / GC / compaction climb"]
    E --> A
    C --> F["Client gives up, yet in-flight server work continues"]
    F --> D
~~~

**Backoff only delays retries**—it does not eliminate the multiplicative factor. Designate **one authoritative owner of retry counts** and enforce an end-to-end time and traffic budget.

## 4. Who Should Own Retries?

### 4.1. Pick one primary decision point

| Layer | Allowed to retry? | Design recommendation |
|---|---|---|
| UI / mobile / browser | May retry a safe read after transient error | Never auto-retry state-changing `POST` without an idempotency key and explicit contract |
| API gateway / ingress | May handle pre-upstream connection failures | Never blindly retry all 5xx or extend the total deadline |
| Orchestrating service | Understands business rules, deadlines, and idempotency | Usually the best place to **own workflow-level retries** |
| Downstream microservice | Very bounded retries only if invariants hold | Honor caller deadlines; never pick high attempt counts unilaterally |
| Cassandra Java Driver | Very bounded retries when policy deems safe | Keep default or use a planned custom policy; **never assume zero retries** |
| Cassandra coordinator / replicas | Performs internal work per CL/replication/Paxos | Not controlled directly by app retry loops |
| Job / queue consumer | Broker may redeliver; DLQ/long backoff | Redelivery is also a retry layer; requires dedup/idempotency |

Two manageable strategies:

**Strategy A — Driver-owned retries:** Gateway, service, and repository **do not** manually retry CQL. The Java Driver uses `DefaultRetryPolicy` with a request timeout capped below the **remaining business budget**. This fits many request-response reads. Note that the driver still performs bounded internal retries and hard-coded re-prepares; measure them.

**Strategy B — Service-owned retries:** A single application layer runs backoff based on outcomes and idempotency. The driver policy is configured so **no unexpected policy-level retries stack on top** (e.g., a reviewed custom `RetryPolicy`; pre-send hard-coded recovery still applies). The gateway does not retry the same operation; the service enforces attempt caps, deadlines, and a global retry token budget.

**Never assume `DefaultRetryPolicy` means the driver always sends just one request.** It can perform bounded retries alongside pre-send failovers, transparent re-prepares, and bootstrapping skips. If the service also calls `execute` in a loop, account for both layers.

### 4.2. Retrying too high or too low both carry costs

Retrying at the gateway replays **the entire workflow**—auth, inventory checks, payment calls, and multi-table reads/writes—costing far more than retrying one small query. Retrying too low in the Driver lacks domain context: it has no idea whether a state transition triggers an email.

Selection rule: **assign retry ownership to the layer that knows both idempotency and deadlines while able to bound total load**. Other layers should return meaningful outcomes or perform strictly budgeted minimal retries.

### 4.3. Retry policies never replace load shedding

When Cassandra is genuinely saturated, “smarter retries” still add work. You need:

- **Admission control:** reject or bound queues right at the ingress edge.
- **Concurrency limits / bulkheads:** cap concurrent CQL requests.
- **Retry token budgets:** allow only a tiny fraction of extra attempts while healthy.
- **Controlled circuit breakers:** shed traffic to failing targets to let them recover, avoiding synchronized half-open probes without jitter.
- **Backpressure:** refuse new work if queue wait already prevents finishing before the deadline.

If queue delay approaches the deadline, **stop enqueueing**. A request timing out inside a driver throttling queue still wastes resources and delays business errors.

## 5. Actual Behavior of Java Driver 4.x

### 5.1. Driver 4.x request timeouts

Driver 4.19 documentation confirms:

- `basic.request.timeout` or `Statement.setTimeout(Duration)` caps the **total duration of one `session.execute` call**, including driver retries and speculative executions.
- When request throttling is enabled, **time spent waiting in the throttling queue counts toward this timeout**.
- This timeout **is not the full HTTP deadline** and does not include auth, serialization, or HTTP transport.
- If a workflow executes multiple CQL calls, each `execute` has its own timeout. With paging, fetching later pages issues additional requests; enforce a business-layer deadline across the entire consumption loop.

**Lab** HOCON example:

~~~hocon
datastax-java-driver {
  basic.request.timeout = 700 milliseconds
  basic.request.default-idempotence = false

  advanced.retry-policy.class = DefaultRetryPolicy
  advanced.speculative-execution-policy.class = NoSpeculativeExecutionPolicy

  profiles {
    short-read {
      basic.request.timeout = 400 milliseconds
      basic.request.consistency = LOCAL_QUORUM
    }
  }
}
~~~

These are **illustrative values for learning budget limits**, not release defaults. `DefaultRetryPolicy` and `NoSpeculativeExecutionPolicy` are already the defaults; declaring them explicitly clarifies where retries or parallel executions can occur. Size timeouts from real workloads: 400 ms may be too tight for a slow cluster, while 700 ms may exceed a tight endpoint budget.

### 5.2. `DefaultRetryPolicy` never retries unconditionally

| Response / error | Default behavior per Driver 4.19 docs | Key takeaway |
|---|---|---|
| `UnavailableException` | At most **one** try on the next coordinator when eligible | First coordinator may hold stale node-liveness info |
| `ReadTimeoutException` | At most once on the **same coordinator** when enough replicas responded without full data | Never retries all read timeouts |
| `WriteTimeoutException` | Very limited conditional retry, e.g., `BATCH_LOG`; other types usually rethrow | Write may already have applied on some replicas |
| Connection closed after sending without response | Policy may try another coordinator if statement is **idempotent** | Unknown whether the prior request applied |
| `OverloadedException`, certain server errors | If idempotent, may try another coordinator | Widespread overload is **not** cured by more attempts |
| `QueryValidationException`, `ProtocolError`, non-retryable errors | Rethrown via hard-coded rules | Fix CQL, schema, or driver—never retry |
| No connection before sending, `UNPREPARED`, bootstrapping node | Driver handles certain cases **outside `RetryPolicy`** | Monitor request-level metrics rather than assuming the policy governs everything |

**Warning:** this table describes **`DefaultRetryPolicy`** and not every custom policy or fork. `RetryPolicy` is invoked only in eligible scenarios and generally **retries writes/aborts/server errors only when marked idempotent**—never advertise “the driver always retries once” for all errors.

### 5.3. Never use `ConsistencyDowngradingRetryPolicy` to fix timeouts

This policy can drop CL in specific cases (e.g., `QUORUM → ONE`) or ignore write timeouts once any replica ACKed, weakening application consistency guarantees. Under a **write-at-QUORUM / read-at-QUORUM** contract, silent downgrading breaks invariants. **Never enable it just to make error charts look prettier.** Require business sign-off and failure-mode tests before altering CL.

### 5.4. Speculative execution is not a retry after failure

Speculative execution dispatches an extra attempt **before** the first attempt returns if it runs slow. It can lower p99 during single-node GC pauses, yet adds cluster load.

~~~hocon
# Illustrative config syntax only; NEVER enable blindly in production:
datastax-java-driver {
  advanced.speculative-execution-policy {
    class = ConstantSpeculativeExecutionPolicy
    max-executions = 2
    delay = 100 milliseconds
  }
}
~~~

In Driver 4.x, speculative execution is **off** by default and schedules only for **idempotent** requests. Each execution can also undergo retries independently. When one execution “wins”, the other's response is ignored, yet **Cassandra provides no guaranteed server-side cancellation of dispatched mutations**.

Never enable speculation for counter increments, non-idempotent list prepends, side-effecting CAS, or operations that can create external duplicates. Monitor `speculative-executions`, `pool.orphaned-streams`, `pool.in-flight`, and before/after latency—never look solely at client p99.

## 6. Classify Errors Before Retrying

### 6.1. Outcome interpretation matrix

| Error / outcome | Proves non-execution? | Recommended retry posture |
|---|---|---|
| CQL syntax / invalid query, permission denied, schema mismatch | Normally a permanent defect on this request | **Never retry**; fix config, CQL, or schema |
| Authentication / TLS / hostname validation error | Secure connection failed | Never retry blindly; fix credentials, truststores, or certs |
| `UnavailableException` | Coordinator saw too few replicas for CL at that instant | Very bounded next-node try via Driver default; if widespread, fail fast |
| `ReadTimeoutException` | Read lacked CL response; not a write commit | Depends on `dataPresent`/`received` and idempotency; let policy decide |
| `WriteTimeoutException` / `WriteFailureException` | **Does not** prove mutation did not apply | For non-idempotent writes: **`UNKNOWN`**, reconcile before retrying |
| `DriverTimeoutException` | Driver deadline expired without response | **`UNKNOWN` for mutations**; never treat as rollback |
| `OverloadedException` | Cluster is protecting resources | Shed load, back off, throttle—never pile on requests |
| `RequestThrottlingException` | Throttler rejected or timed out queueing request | Admission/backpressure; CQL may not have been sent, yet **not** a license for infinite retries |
| `BusyConnectionException` (may sit inside `AllNodesFailedException`) | Pool / stream IDs exhausted | Investigate concurrency, pool sizing, backpressure; more retries worsen it |
| LWT `wasApplied() == false` | **CAS precondition failed** | Not a transient fault; report conflict or re-evaluate |
| LWT timeout / lost ACK | Outcome ambiguous even if mutation applied | Reconcile via idempotency marker; never coerce to CAS `false` |

**Never classify errors by searching for `"timeout"` in exception messages.** Inspect exact classes and causes per Driver version, coordinator metadata, CL, received/required counts, and metrics. In async flows, unwrap `CompletionException`/`ExecutionException`.

### 6.2. Server timeouts vs. driver timeouts

~~~text
ReadTimeoutException:
  Coordinator accepted query but lacked sufficient responses/data
  before Cassandra's server-side read timeout.

WriteTimeoutException:
  Coordinator accepted mutation but lacked sufficient ACKs within
  server timeout. Some replicas may already have persisted it.

DriverTimeoutException:
  Client-side request deadline expired before driver received a result.
  Can stem from queues, network, coordinator, retries, or speculation.

BusinessDeadlineExceeded:
  The end-to-end workflow exhausted its budget, regardless of whether
  an individual CQL call just succeeded or is still running.
~~~

Never crank `read_request_timeout_in_ms` or server write timeouts **arbitrarily 10x higher** just to silence client errors. Tune client/server timeouts together with RF/CL, network RTT, and backpressure using targeted measurements.

### 6.3. LWT `false` and request timeouts are two distinct outcomes

Given:

~~~sql
UPDATE retry_lab.jobs_by_id
SET status = 'RUNNING', version = 2
WHERE job_id = 11111111-1111-4111-8111-111111111111
IF version = 1;
~~~

If `ResultSet.wasApplied() == false`, you know the precondition was not met when Paxos evaluated it. If the request timed out, the mutation **may already have bumped version to 2** before the response dropped. An identical retry returns `false` precisely because the first try succeeded. Always separate a ***true conflict*** from an ***unknown outcome***—never lump both into “retryable error”.

## 7. Idempotency: Mandatory Prerequisite Before Retrying Writes

### 7.1. Accurate definition

An operation is **idempotent** if running it multiple times yields **the exact same final data state** as running it once under its domain assumptions. It **does not** mean “the request adds zero load”, “it always returns the same HTTP code”, or “Cassandra rolls back on timeout”.

| CQL / operation | Initial assessment | What must be verified |
|---|---|---|
| Side-effect-free `SELECT` | Usually idempotent | Paging, CL, and time-varying snapshots can still return different rows |
| `UPDATE ... SET status='DONE'` | Usually value-idempotent | Timestamps/TTLs, triggers/outboxes, and concurrent writes can alter final state |
| `INSERT` with fixed PK and values | Potentially row-value idempotent | Timestamps/TTLs, last-write-wins, and duplicate downstream effects |
| `UPDATE counter = counter + 1` | **Not idempotent** | Retry can double-increment |
| `UPDATE list_col = ['x'] + list_col` | **Not idempotent** | Retry can prepend twice |
| `INSERT ... IF NOT EXISTS` | Result semantics differ | First returns `true`, replay returns `false` for same business request |
| `UPDATE ... IF version = n` | Needs dedicated idempotency/reconcile | `false` on retry may reflect an already-committed first attempt |
| External email / payment after write | Not naturally idempotent | Needs operation ID, outbox/dedup on external systems |

Java Driver 4.x sets `basic.request.default-idempotence = false` by default. For a prepared `SELECT`:

~~~java
PreparedStatement ps = session.prepare(
    "SELECT status FROM retry_lab.jobs_by_id WHERE job_id = ?");

BoundStatement read = ps.bind(jobId)
    .setIdempotent(true); // Valid only because this query is pure read-only.
~~~

**Mark idempotence per statement**—never flip `default-idempotence = true` session-wide when the application contains counters, LWTs, batches, or non-idempotent writes. `PreparedStatement` does not automatically make any mutation idempotent.

### 7.2. TTLs and timestamps make retries subtler

An `INSERT ... USING TTL 60` replayed 30 seconds later with `TTL=60` **extends the expiration** relative to the original intent. Same column value, different expiration deadline—so it is **not idempotent with respect to retention deadlines**.

To preserve deadlines:

- Store a business `expires_at_utc`, compute **remaining** TTL before each send instead of reusing the original TTL.
- Define a timestamp/conflict strategy for concurrent writes.
- If already expired, **never pass `USING TTL 0`**, because `TTL 0` means no expiration.
- For auth/session lifetimes requiring exact expiration, enforce deadlines in domain logic rather than waiting solely for Cassandra compaction.

Even an `UPDATE` assigning a fixed value gets a fresh write timestamp on retry and can overwrite a concurrent update. Evaluate **idempotency via invariants and concurrency**, not just identical CQL literals.

### 7.3. Operation IDs for resource-creation APIs

Pattern:

~~~text
POST /jobs
  Idempotency-Key = "request-uuid-123" (example; never use a secret)

Service:
  1. Validate request ID and payload hash within caller's scope.
  2. Persist operation marker in a dedicated partition/registry.
  3. Execute transition only if not already completed.
  4. On timeout, read marker + state before attempting again.
  5. Return an outcome consistent with the first attempt without duplicating side effects.
~~~

**Note:** simply adding an `Idempotency-Key` header does not guarantee deduplication. You need **durable state**, key scoping, retention, concurrency control (possibly LWT), and recovery when marker writes and side effects are non-atomic. Never expose another user's key or log raw keys if they contain sensitive tokens.

## 8. Capped Exponential Backoff and Jitter

### 8.1. Why isn't fixed delay enough?

If 10,000 clients time out together and each sleeps a fixed 100 ms, they retry **in lockstep** at `t+100 ms`, creating another load spike. Exponential backoff widens the wait after consecutive failures; **jitter** spreads retry times so clients desynchronize.

**Full jitter** formula:

\[
cap_k=\min(maxDelay,\ baseDelay \times 2^{k-1}),\quad
sleep_k\sim Uniform(0,\ cap_k).
\]

where `k` is the **upcoming retry index**, starting at `k=1`. Example with `baseDelay=50 ms`, `maxDelay=400 ms`:

| Retry `k` | Delay cap | Random sampling range |
|---|---:|---|
| 1 | 50 ms | 0–50 ms |
| 2 | 100 ms | 0–100 ms |
| 3 | 200 ms | 0–200 ms |
| 4 | 400 ms | 0–400 ms |
| 5+ | 400 ms | 0–400 ms |

Do not misread this table as sleeping **exactly** 50/100/200/400 ms. Full jitter samples uniformly within the window. Also never sleep past the **remaining deadline**; once insufficient time remains for both backoff **and** a meaningful attempt, stop.

### 8.2. Java function for full jitter

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

static Duration fullJitterDelay(
        int retryIndex, long baseMs, long maxMs) {
    if (retryIndex < 1 || baseMs < 1 || maxMs < baseMs
            || maxMs == Long.MAX_VALUE) {
        throw new IllegalArgumentException("Invalid backoff config");
    }

    long capMs = baseMs;
    for (int i = 1; i < retryIndex; i++) {
        capMs = capMs >= maxMs / 2
                ? maxMs
                : Math.min(maxMs, capMs * 2);
    }

    long sampledMs = ThreadLocalRandom.current().nextLong(capMs + 1);
    return Duration.ofMillis(sampledMs);
}
~~~

This function **only computes the delay**; it does not sleep or retry. For async execution:

~~~java
// Pseudocode: scheduler runs once after backoff; never sleep
// inside a Netty/driver callback.
//
// Duration delay = fullJitterDelay(retryIndex, 50, 400);
// if (delay.plus(minUsefulAttempt).compareTo(deadline.remaining()) >= 0)
//     completeDeadlineExceeded();
// else
//     scheduler.schedule(() -> attemptAgainIfStillAllowed(),
//                        delay.toMillis(), TimeUnit.MILLISECONDS);
~~~

**Never call `Thread.sleep` inside Java Driver `RetryPolicy`**: policy callbacks run on I/O threads, and blocking them stalls unrelated requests. Implement delayed retries via scheduling in the **service layer** that owns retries, never sleeping inside policy callbacks.

### 8.3. Backoff must be paired with caps

A sound retry gate checks all conditions together:

~~~text
retry_allowed =
    operation_is_safe_to_repeat
    AND error_is_transient_and_retryable
    AND attempts_used < max_attempts
    AND retry_token_budget_has_capacity
    AND now + jitter_delay + min_useful_attempt + reserve < deadline
    AND downstream_not_overloaded_beyond_safe_threshold
~~~

If any gate closes, stop. **Capped backoff never means retrying forever at `maxDelay`**: enforce `maxAttempts`, deadlines, and a retry token budget.

### 8.4. `Retry-After`, circuit breakers, and overload

An overloaded HTTP service may return `Retry-After`. Honor it **when** it fits inside the remaining deadline and the caller permits retries—never ignore it to fire early. However, Cassandra CQL has no universal `Retry-After` header across all errors. On Cassandra overload, you normally need to **cut admission rate, queue depth, and concurrency**, rather than merely sleeping briefly and retrying anyway.

Circuit breakers need **bounded half-open probes**, or thousands of service instances will reopen simultaneously and trigger a fresh spike. Size retry budgets (e.g., a few percent of successful traffic over a sliding window) from telemetry rather than fixed guesses.

## 9. Java Driver: Setting Timeouts from Remaining Budget

### 9.1. A `Deadline` class using a monotonic clock

Standard-library-only example reusable within a single JVM:

~~~java
import java.time.Duration;

public final class Deadline {
    private final long startedNanos;
    private final long budgetNanos;

    private Deadline(Duration budget) {
        if (budget.isZero() || budget.isNegative()) {
            throw new IllegalArgumentException("Budget must be positive");
        }
        this.startedNanos = System.nanoTime();
        this.budgetNanos = budget.toNanos();
    }

    public static Deadline start(Duration budget) {
        return new Deadline(budget);
    }

    public Duration remaining() {
        long elapsed = System.nanoTime() - startedNanos;
        long left = budgetNanos - elapsed;
        return Duration.ofNanos(Math.max(0L, left));
    }

    public boolean expired() {
        return remaining().isZero();
    }

    public Duration usable(Duration reserve) {
        Duration result = remaining().minus(reserve);
        return result.isNegative() ? Duration.ZERO : result;
    }
}
~~~

This snippet assumes budgets fit comfortably within `Duration.toNanos()` and stay in one process. Production implementations may also handle overflow, tracing context, cancellation, and framework deadline propagation; **never send `startedNanos` across hosts**.

### 9.2. Sending a `SELECT` with a budget-shrinking timeout

Service example **without an extra service-layer CQL retry loop**. The driver keeps bounded `DefaultRetryPolicy` and speculative execution disabled as in Section 5.1; the whole operation is guarded by one `Deadline`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.util.Optional;
import java.util.UUID;

static Optional<String> readJobStatus(
        CqlSession session, PreparedStatement prepared,
        UUID jobId, Deadline deadline) {

    // Prepare/cache PreparedStatement at startup, not per HTTP request.
    Duration usable = deadline.usable(Duration.ofMillis(100));
    Duration configuredCeiling = Duration.ofMillis(700);
    Duration timeout = usable.compareTo(configuredCeiling) < 0
            ? usable : configuredCeiling;

    if (timeout.compareTo(Duration.ofMillis(50)) < 0) {
        throw new IllegalStateException("Insufficient business budget");
    }

    BoundStatement statement = prepared.bind(jobId)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setIdempotent(true)   // Pure SELECT with no side effects.
        .setTimeout(timeout); // Caps this execute call, including Driver retries.

    ResultSet rs = session.execute(statement);

    // Once the caller's deadline expired, do not treat a late response
    // as a valid success for the waiting HTTP request.
    if (deadline.expired()) {
        throw new IllegalStateException("Business deadline exceeded");
    }

    Row row = rs.one();
    return row == null
        ? Optional.empty()
        : Optional.ofNullable(row.getString("status"));
}
~~~

Prepare the statement at startup:

~~~java
PreparedStatement readById = session.prepare(
    "SELECT status FROM retry_lab.jobs_by_id WHERE job_id = ?");
~~~

**Example limits:** `IllegalStateException` is a placeholder for a domain `DeadlineExceeded` exception; production code maps to HTTP/gRPC status codes, logs/traces, and cleanup. Callers must pass **the same `Deadline` instance** across auth, cache, CQL, and serialization—never create a fresh 1,500 ms `Deadline` inside every repository method.

On timeouts or cancellation, Cassandra may still be executing an already-sent mutation. Checking `deadline.expired()` after receiving a response protects the **response contract**, not a data rollback.

### 9.3. Execution profiles and immutable statements

Driver 4.x statement setters **return a new instance**:

~~~java
BoundStatement base = readById.bind(jobId);
BoundStatement timed = base
    .setIdempotent(true)
    .setTimeout(Duration.ofMillis(250))
    .setExecutionProfileName("short-read");

// Must execute "timed", not "base" expecting in-place mutation.
session.execute(timed);
~~~

When using profile `short-read` with a 400 ms default timeout, `setTimeout(250 ms)` on the statement overrides it. Forgetting to capture the returned statement silently leaves old timeouts and retry behavior active.

### 9.4. Synchronous vs. asynchronous execution and cancellation

`session.executeAsync` returns a `CompletionStage`; frameworks can attach timeouts and propagate cancellation. However:

- Cancelling a Java future **does not guarantee Cassandra cancels in-flight coordinator/replica work**.
- Once the caller gives up, **never enqueue fresh retries** or fetch remaining pages nobody will read.
- Never block event-loop/Netty callbacks with sleep backoff, synchronous I/O, or heavy CPU work.
- When managing deadlines across **multiple CQL calls** in a saga, the outer orchestrator must own the end-to-end deadline; driver timeouts govern individual calls.

## 10. When the Service Truly Owns Retries: Backoff at Exactly One Layer

### 10.1. Controlled loop structure

When an operation is safe to repeat and the service must retry a transient error that the default driver policy does not cover, use a **decision structure** like:

~~~text
deadline = businessDeadlineFromCaller()
maxAttempts = 2           # includes initial attempt
retryBudget = sharedTokenBudgetForThisService()

for attemptIndex in 1..maxAttempts:
    if deadline has no useful time:
        return DEADLINE_EXCEEDED

    execute downstream request with timeout <= remaining minus reserve

    if result is success:
        return SUCCESS
    if result is non-retryable:
        return ERROR / BUSINESS_CONFLICT
    if result is UNKNOWN write outcome:
        reconcile or fail UNKNOWN; never blindly repeat
    if attemptIndex == maxAttempts or tokenBudget exhausted:
        return ERROR

    delay = fullJitter(retryIndex=attemptIndex)
    if delay + usefulAttempt + reserve >= remaining:
        return DEADLINE_EXCEEDED
    schedule next attempt after delay
~~~

**Design condition:** when the service owns attempts, **disable or strictly bound Driver policy-level retries and speculative executions** via a tested policy. Even then, the driver still runs internal pre-send skips and re-prepares, so count actual physical attempts via metrics. Also disable or budget external HTTP client, gateway, and queue retries together.

### 10.2. Never sleep inside Driver `RetryPolicy`

Official `RetryPolicy` docs emphasize that callbacks execute on I/O threads; **never call `Thread.sleep`** for backoff. Implement delayed retries in the service layer using a scheduler and centralized attempt counters.

In reactive pipelines, schedule delays using non-blocking schedulers or reactive delay operators rather than spawning unbounded thread-per-retry loops. Drop expired requests from queues immediately.

### 10.3. Service-wide retry budgets

Capping `maxAttempts = 2` per request is not enough: if the backend rejects 100% of requests, traffic still **doubles**. Enforce a **global retry budget relative to total traffic**.

Illustrative policy parameters:

~~~text
incoming requests: 10,000 / minute
retry budget: max 200 extra attempts / minute during steady state
max attempts / request: 2
business deadline: 1,500 ms
overload / circuit open: zero retry tokens, fail fast
~~~

These numbers are **illustrative**. With 10,000 fresh requests/min and a 200/min retry budget, extra load is capped near 2% **if the token budget is enforced consistently** across instances. In multi-instance deployments, clarify whether budgets are per-process or shared so scaling out by \(N\) instances does not accidentally multiply the budget by \(N\).

## 11. Java/CQL Lab: Proving Deadlines and Retries Preserve Data Correctness

### 11.1. Setup

The lab requires Cassandra 4.x/5.x and Java Driver 4.x. On a three-node cluster in real DC `dc1`, use RF=3; on a single-node lab, adjust RF/CL accordingly first.

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

In `cqlsh`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS retry_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS retry_lab.jobs_by_id (
  job_id uuid PRIMARY KEY,
  status text,
  version int,
  updated_at timestamp
);

INSERT INTO retry_lab.jobs_by_id
  (job_id, status, version, updated_at)
VALUES (
  11111111-1111-4111-8111-111111111111,
  'NEW',
  1,
  '2026-11-21T09:00:00Z'
);

SELECT status, version
FROM retry_lab.jobs_by_id
WHERE job_id = 11111111-1111-4111-8111-111111111111;
~~~

`IF NOT EXISTS` does not alter existing schemas. Before measuring, inspect `DESCRIBE KEYSPACE retry_lab`, `DESCRIBE TABLE retry_lab.jobs_by_id`, DC names, and actual RF. Never use real user data in fault-injection labs.

### 11.2. Case A — A `SELECT` with an end-to-end deadline

Run through a lab application endpoint:

1. Create a 1,500 ms `Deadline` at ingress; share it across auth, business logic, and CQL reads.
2. Set driver timeout `min(700 ms, remaining - 100 ms)` before each attempt.
3. Log `business_elapsed_ms`, `driver_call_ms`, `remaining_before_cql_ms`, `attempt_count`, and response status.
4. Inject controlled latency **at a proxy/lab layer** before CQL and verify **fail-fast** when remaining time drops low.
5. Confirm that once the caller deadline expires, no new CQL calls or retries start.

Never test by randomly killing production replicas or deleting SSTables; use approved lab clusters/proxies with clean rollback.

### 11.3. Case B — Timeout after a mutation may have succeeded

In the lab:

~~~sql
UPDATE retry_lab.jobs_by_id
SET status = 'RUNNING', version = 2
WHERE job_id = 11111111-1111-4111-8111-111111111111
IF version = 1;
~~~

Create a controlled test where **coordinator responses are delayed or blackholed after the request may already have executed**. Java sees a timeout. Next read:

~~~sql
SELECT status, version
FROM retry_lab.jobs_by_id
WHERE job_id = 11111111-1111-4111-8111-111111111111;
~~~

If `version` is 2, the mutation committed even though the client timed out. Even if unchanged, never generalize that similar timeouts are safe to retry blindly. Record `UNKNOWN` and reconcile by operation ID, version, and service policy.

### 11.4. Case C — Counters must never retry like `SELECT`s

Separate table **for lab use only**:

~~~sql
CREATE TABLE IF NOT EXISTS retry_lab.request_counter (
  counter_id uuid PRIMARY KEY,
  total counter
);

UPDATE retry_lab.request_counter
SET total = total + 1
WHERE counter_id = 22222222-2222-4222-8222-222222222222;
~~~

If the counter `UPDATE` response drops and the request replays, `total` can jump by 2. **Never** mark counter increments `setIdempotent(true)` merely to gain automatic retries. When business logic needs exact-once counts, aggregate and deduplicate from event IDs instead of assuming counter writes retry safely.

### 11.5. Case D — Three independent retry layers

Set up a proxy/mock test (without modifying production Driver code):

~~~text
Client attempts: 3
Service A attempts: 3
Service B attempts: 3
Driver recoverable attempts: measure empirically (do not force assumptions)

Record HTTP calls and CQL executions per business_request_id.
Measure p99, in-flight, retry budget exhausted, and backend throughput.
Then disable retries in two layers and re-measure under the same fault rate.
~~~

Keep injected fault type, request rate, data, and CL identical across runs. If one layer only retries certain errors, observed counts may stay below the theoretical product. **The goal** is demonstrating retry fan-out via telemetry, not forcing exact numbers like 27 or 54 at all costs.

### 11.6. Case E — Deadlines and paging

Query thousands of rows with a small page size. Across 10 pages, `basic.request.timeout` applies to individual CQL requests—it never guarantees **the entire paging loop** finishes inside 1,500 ms. In multi-page loops, check `deadline.remaining()` **before fetching each next page**, cap pages/rows, and stop consuming once the caller's budget expires.

## 12. Test Matrix

| Scenario | Expected behavior | What must never happen |
|---|---|---|
| Healthy backend | One business request triggers designed CQL executions | Enabling unnecessary retries or speculation |
| One slow replica | `DefaultRetryPolicy` retries only eligible cases | Retrying every error until CL passes |
| Entire local DC lost | Fails fast per locality/DR policy | Silently downgrading CL or failing over to remote DC unapproved |
| `WriteTimeoutException` | Mutation outcome may be `UNKNOWN` | Reporting “not written” and replaying infinitely |
| Transient `ReadTimeoutException` | Bounded retry within budget if read is idempotent | Each microservice independently adding attempts |
| CQL syntax / authorization error | Stops and fixes CQL or roles | Backing off and resending the same broken request |
| Cassandra overload | Sheds admission and cuts retry budget | Flooding more requests to “push through” overload |
| Request past deadline | Sends zero additional CQL or retries | Resetting timeouts inside repositories |
| User `POST` times out | Idempotency check / reconciliation before replay | Creating duplicate orders or side effects |
| Speculative execution enabled | Tracks extra executions and stream IDs | Treating it as free or server-cancellable |
| Long paging | Enforces outer deadline across the whole loop | Granting each page an unbounded fresh timeout |
| LWT `false` | Handled as conflict per business invariants | Classified as a retryable network error |

### 12.1. Empirical measurement sheet

| Metric | Baseline | Fault injection | After retry tuning | Target |
|---|---|---|---|---|
| P95/P99 business latency | _fill_ | _fill_ | _fill_ | Meets SLO |
| HTTP requests / original action | _fill_ | _fill_ | _fill_ | No unbudgeted multiplication |
| CQL executions / business request | _fill_ | _fill_ | _fill_ | Bounded and measured |
| Retry attempts/s | _fill_ | _fill_ | _fill_ | Within retry budget |
| `DriverTimeout` / `ReadTimeout` / `WriteTimeout` | _fill_ | _fill_ | _fill_ | Tracked separately |
| `UNKNOWN` write outcomes | _fill_ | _fill_ | _fill_ | Reconciled |
| Driver pool in-flight / available streams | _fill_ | _fill_ | _fill_ | Never exhausted |
| Throttling queue size / delay | _fill_ | _fill_ | _fill_ | No expired requests queued |
| Cassandra p99 / GC / compaction | _fill_ | _fill_ | _fill_ | No cascading failure |
| Duplicate business effects | _fill_ | _fill_ | _fill_ | 0 when required by domain |

**Count hidden attempts too**: gateway retries, HTTP client retries, service retries, driver retries, speculative executions, and queue redeliveries. In Java Driver 4.x, metrics are **off by default**; enable required metrics per docs and evaluate observability overhead. Never extrapolate full metrics from a single sample request.

## 13. Preventing Cascading Failures Beyond Retries

### 13.1. Concurrency limits and bounded queues

By Little's Law, at steady arrival rate, rising processing times drive in-flight request counts upward. When Cassandra slows down, an unbounded queue accumulates **requests already rendered useless by expired deadlines**.

Sensible bounds:

- Concurrent requests at the HTTP service and per `CqlSession`/workload class.
- Queue depth limits with policies to drop expired jobs.
- Active retries and retry tokens, prioritizing fresh requests with a chance of finishing over waves of stale retries.
- Connection stream limits and throttling queue wait times so pools do not exhaust stream IDs and trigger cascading retries.

Java Driver 4.x provides `ConcurrencyLimitingRequestThrottler` and `RateLimitingRequestThrottler` for session-level throttling, though queueing does not speed up saturated servers. Queue wait counts toward the Driver request timeout; monitor `throttling.delay`, `throttling.queue-size`, and `throttling.errors`.

### 13.2. Fail fast can beat retrying

If the local DC lacks replicas for `LOCAL_QUORUM`, blind retries rarely succeed and worsen overload. Preserve consistency contracts; **never switch `LOCAL_QUORUM → ONE`** just to cut HTTP 5xx rates.

Conversely, when one coordinator holds stale membership state, a single next-node retry under `DefaultRetryPolicy` can help. The right choice is not “ban all retries”, but **retry only recoverable errors under strict cost and deadline bounds**.

### 13.3. Hedging / speculation must count against retry budgets

A read dispatched concurrently to two coordinators may finish faster, yet still consumes **two executions** competing for cluster resources. Near capacity, adding hedging can degrade overall system p99.

Never count only `session.execute` calls from Java: **one `execute` can emit multiple executions** when speculative policies are active. Measure true load with Driver metrics, low-rate tracing, and Cassandra request counters.

## 14. Common Misconceptions

| Misconception | Why it is wrong | Correct approach |
|---|---|---|
| “2-second timeout per layer means 2 seconds total” | Sequential steps and retries add up | End-to-end deadlines and remaining budgets |
| “Three retries per layer only add a few calls” | Attempts **multiply**, not add | Single retry owner; measure fan-out |
| “Driver 4.x always sends one CQL request” | Default policy, pre-send recovery, re-prepare, and speculation | Inspect config/metrics and test |
| “`basic.request.timeout` is the HTTP deadline” | Governs one `execute`, not the whole workflow | Propagate deadlines in the service |
| “Write timeout = mutation was not written” | Some replicas may have written or ACKs dropped | `UNKNOWN` / reconcile / idempotency |
| “`DefaultRetryPolicy` retries all errors” | Retries only specific safe conditions | Inspect error types and idempotence |
| “Driver requests are idempotent by default” | Driver 4 defaults to `false` | Mark per statement by semantics |
| “Setting `setIdempotent(true)` makes it safe” | Counters, list prepends, TTLs, and side effects remain unsafe | Verify domain invariants |
| “LWT `false` can retry like a timeout” | `false` means precondition failed | Handle conflict or re-evaluate CAS |
| “Fixed 100 ms backoff avoids spikes” | Clients synchronize retry waves | Full jitter + cap |
| “Jitter replaces deadlines and `maxAttempts`” | Random delays can still run too long | Enforce budgets and stop conditions |
| “Cancelling a future undoes the Cassandra mutation” | Server may still process it | Stop adding attempts; reconcile if needed |
| “Switch `QUORUM` to `ONE` to stop timeouts” | Breaks consistency guarantees | Keep CL; fix capacity/availability |
| “Retrying on overload helps self-heal” | Retries create positive load feedback | Load shedding, token budgets, circuit breakers |
| “Per-page timeout bounds full paging” | Later pages issue new requests | Check outer deadline on every page |

## 15. Scenario Exercises

### Exercise 1 — Calculate maximum attempts

Gateway allows 3 attempts, service allows 2, and Driver can run 2 executions per service call. How many Cassandra executions can one user action generate at most?

**Answer:** `3 × 2 × 2 = 12` executions as a design upper bound. Not `3 + 2 + 2 = 7`; actual runtime counts depend on error types, policies, and stop gates.

### Exercise 2 — Too little budget left

Business deadline is 1,200 ms. After auth and cache, 180 ms remain; 100 ms are reserved for HTTP response, and CQL p99 is 250 ms. Should you grant a 600 ms timeout and retry?

**Answer:** No. Only 80 ms usable remain, below the minimum useful attempt; fail fast, adjust the workflow, or switch to an approved async pattern. Never reset the deadline inside repositories.

### Exercise 3 — Retrying counters

An app runs `UPDATE counter = counter + 1`, hits a timeout, sets `setIdempotent(true)`, and retries. What happens?

**Answer:** The counter may increment twice because the first attempt applied. Use deduplication, event IDs, and reconciliation rather than treating counter mutations as idempotent.

### Exercise 4 — Deadlines and driver timeouts

`basic.request.timeout = 2 seconds`. Gateway gives the endpoint 800 ms max, and the service starts CQL with 200 ms left. Is the request guaranteed to return within 800 ms?

**Answer:** No. The 2-second driver timeout governs one execute call only; compute `remaining - reserve` and pass it via `setTimeout`. If too little time remains, do not send it.

### Exercise 5 — LWT `false` after timeout

A service sends `UPDATE ... IF version=4` and times out; retry receives `wasApplied=false` and sees `version=5`. Is it certain the first attempt failed?

**Answer:** No. The first attempt may have written version 5 before its ACK dropped. Reconcile using operation IDs and state invariants instead of returning an assumed conflict.

### Exercise 6 — Full jitter

`base=40 ms`, `cap=320 ms`. What are the delay windows for retries 1 through 5?

**Answer:** `0–40`, `0–80`, `0–160`, `0–320`, `0–320` ms; sample randomly inside each window rather than sleeping fixed at the upper bound.

### Exercise 7 — Layered retries under overload

When Cassandra overloads and HTTP errors rise, every microservice increases `maxAttempts` from 2 to 5. Why does the system get worse?

**Answer:** Backend load multiplies across layers, extending queues, GC, and timeouts in a feedback loop. Shed load, centralize retry ownership, enforce budgets, and apply backoff/jitter instead of raising attempts.

### Exercise 8 — Cancellation

A user closes their browser; the service cancels the Java Driver `CompletionStage` and declares “Cassandra definitely didn't write”. Correct?

**Answer:** No. Client-side cancellation never guarantees aborting an in-flight mutation on the server. Do not fire further attempts, record `UNKNOWN` when appropriate, and reconcile later.

### Final checklist

- [ ] One end-to-end business deadline exists, measured with a monotonic clock within each JVM.
- [ ] Every downstream timeout is `<= remaining budget - reserve`.
- [ ] Zero new requests or retries start once the deadline has expired.
- [ ] Attempts are counted across gateway, service, repository, Driver, and queue redeliveries.
- [ ] Amplification math is understood: the product of total attempts across layers.
- [ ] **One primary retry-owning layer** is designated, with Driver behavior accounted for in the budget.
- [ ] Team understands `DefaultRetryPolicy`/Driver 4.x does not retry all errors and defaults idempotence to `false`.
- [ ] Team distinguishes `DriverTimeout`, `ReadTimeout`, `WriteTimeout`, `Unavailable`, and overload.
- [ ] Non-idempotent mutations and unknown write outcomes are never retried blindly without reconciliation.
- [ ] Capped exponential backoff + full jitter, `maxAttempts`, and retry token budgets are enforced.
- [ ] No sleeping or blocking occurs inside Driver `RetryPolicy` I/O callbacks.
- [ ] Load shedding, bounded queues, concurrency limits, and safe half-open probes are implemented.
- [ ] Speculative executions are counted in physical attempts and capacity budgets.
- [ ] Tests cover fault injection, p95/p99 latency, timeouts/`UNKNOWN`, duplicate effects, and fan-out.

## 16. References

1. Apache Cassandra Java Driver 4.19 — [Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): `DefaultRetryPolicy`, handling `Unavailable`/`ReadTimeout`/`WriteTimeout`, hard-coded recovery, and bounds.
2. Apache Cassandra Java Driver 4.19 — [Idempotence](https://apache.github.io/cassandra-java-driver/4.19.0/core/idempotence/): per-statement flag, default `false`, retries/speculation only on eligible requests.
3. Apache Cassandra Java Driver 4.19 — [Speculative Execution](https://apache.github.io/cassandra-java-driver/4.19.0/core/speculative_execution/): off by default, parallel executions, stream IDs, and metrics.
4. Apache Cassandra Java Driver 4.19 — [Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): HOCON, `basic.request.timeout`, and execution profiles.
5. Apache Cassandra Java Driver 4.19 — [Statement API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/Statement.html): `setTimeout(Duration)`, `setIdempotent`, immutable statements.
6. Apache Cassandra Java Driver 4.19 — [RetryPolicy API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/retry/RetryPolicy.html): non-blocking I/O threads and implementing custom policies.
7. Apache Cassandra Java Driver 4.19 — [Throttling](https://apache.github.io/cassandra-java-driver/4.19.0/core/throttling/) and [Metrics](https://apache.github.io/cassandra-java-driver/4.19.0/core/metrics/): queueing inside request timeout, concurrency limits, and observability.
8. Google SRE Book — [Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/): retry budgets, randomized backoff, and avoiding multi-layer retry amplification.
9. Amazon Builders' Library — [Timeouts, Retries, and Backoff with Jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/): retry multiplication, deadlines, and jitter.
10. Apache Cassandra Documentation — [CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): CQL semantics, TTLs, counters, and LWTs.
