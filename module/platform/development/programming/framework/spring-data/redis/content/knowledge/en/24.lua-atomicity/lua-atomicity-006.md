# Evaluating Script Runtime Because Scripts Can Block Other Commands in Spring Data Redis

Lua scripting lets Redis perform multiple reads, conditional checks, and writes **as an execution-level atomic unit**. That is a major advantage when building features like conditional stock deduction, rate limiting, lock ownership checks, or updating related data structures.

However, the very mechanism guaranteeing that atomicity introduces an important constraint: **while Redis executes a Lua script, other ordinary commands on the same Redis server cannot interleave mid-script**. A script with a long loop, excessive element scans, or expensive commands can raise latency across a wave of other Redis requests, even simple `GET`s.

Therefore, when using Spring Data Redis to invoke `EVAL`/`EVALSHA` via `RedisTemplate.execute(...)`, you must evaluate **execution duration, work volume, and latency impact on other requests**, in addition to verifying functional correctness.

This lesson focuses on the relationship between **atomicity**, **how long a script holds the Redis server**, observability tools, and designing Lua scripts with strictly bounded work.

## 1. Why Do Atomic Scripts Risk Causing Contention?

Redis processes data-structure operations through serialized command execution. Even in versions/configurations that use I/O threads for networking, executing standard data operations still means a Lua script occupies Redis's command execution thread while it runs.

For example, two clients sharing one Redis server:

```text
Client A                             Redis server                         Client B
--------                             ------------                         --------
EVAL long-script ------------------> [ script starts ]
                                     [ reads keys    ]
GET user:42 --------------------X    [ large loop    ] <---------------- GET user:42
                                     [ writes keys   ]
                                     [ script ends   ]
                                                                        <--- GET reply
```

Here, Client B's `GET` cannot interleave between the script's steps to observe half-written state. This property gives the script atomicity, yet at the same time makes **Client B's latency depend on the remaining runtime of Script A**.

Possible consequences:

- A script running for several hundred milliseconds spikes latency for many ordinary requests.
- Multiple heavy scripts in a row build a command queue and cause sharp p95/p99 latency spikes.
- A slow script can cause clients to time out before the server finishes processing.
- Operators see the Redis process still alive while other commands stall for a long time or fail with script-busy errors.
- Even a read-only script that writes nothing can cause blocking, because preventing interleaving applies regardless of whether the script performs writes.

Key takeaway: **a script does not need to throw an error to slow the entire system down**. Occupying the command execution path long enough affects every application sharing that Redis server.

## 2. What Does Lua Script Atomicity Actually Guarantee?

Consider a stock deduction operation:

```text
Read stock
    |
Check stock >= quantity
    |
Subtract quantity
    |
Return result
```

If Java sends `GET` and then `DECRBY` as two independent commands, another client can modify stock in between. Putting both check and update inside one Lua script ensures Redis executes them back-to-back without other clients' operations interleaving.

Example:

```lua
local current = tonumber(redis.call('GET', KEYS[1]))
local requested = tonumber(ARGV[1])

if not current or not requested or requested <= 0 then
    return -1
end

if current < requested then
    return 0
end

return redis.call('DECRBY', KEYS[1], requested)
```

With key `stock:sku-42` and requested quantity `2`, the script reads stock, checks it, and subtracts on the Redis server.

Guarantees to understand accurately:

| Aspect | Property |
|---|---|
| No interleaving | Other clients' commands cannot interleave between commands in the script on the executing Redis server |
| Check then update | Condition and mutation reside in the same script |
| Client outcome | Client receives its reply after the script completes or errors |
| Rollback on runtime error | **No** general rollback mechanism for writes performed before an error inside the script |
| Crash durability | Depends on Redis persistence/replication configuration |
| Transactions with PostgreSQL or other services | **Not** provided merely because a Redis script is atomic |
| Execution time bound | Must be designed deliberately; atomicity imposes no safe work cap on its own |

If a script writes some data and then errors, Redis does not automatically restore earlier writes to their pre-script state. Hence, logic should **validate all preconditions and potential error cases before starting writes**. Meanwhile, a functionally correct script can still degrade the system if it runs too long.

## 3. How Does Script Runtime Relate to System-Wide Latency?

Suppose one Redis server serves requests from three services:

```text
Service A: session verification       -> GET session:...
Service B: product cache lookup       -> MGET cache:...
Service C: large statistics update    -> EVAL lua-script
```

If Service C runs a script taking 200 ms, commands arriving at Redis during that window must wait for the script to finish before executing. For systems targeting single-digit millisecond responses, 200 ms far exceeds the latency budget.

Qualitative timeline:

```text
Time
0 ms              50 ms             100 ms             200 ms
|------------------|------------------|------------------|
[                 EVAL running                           ]
   [GET arrives].........................................[GET processed]
                       [INCR arrives]....................[INCR processed]
```

The longer a script holds Redis, the wider the waiting window becomes for unrelated requests.

### 3.1. Do Not Look Only at Average Runtime

A script averaging 2 ms may look fast, yet if it occasionally processes a massive list in 300 ms, p99 system latency can still suffer severely.

Monitor at minimum:

- **Average latency:** gives the overall picture.
- **p95 and p99:** catch rare slow runs, often critical for user-facing requests.
- **Max execution duration:** useful for catching anomalous inputs.
- **Script invocations per second:** a short script called incessantly still consumes significant server capacity.
- **Latency of other commands while scripts run:** reveals blast-radius impact.
- **Timeouts, `BUSY` errors, and queued connections:** signs of saturation or runaway scripts.

Evaluation must tie back to **application latency budgets**, concurrency levels, data sizes, and real traffic. There is no single universal duration threshold suitable for all Redis deployments.

### 3.2. Application-Side Duration Differs from Redis Server Runtime

When Java executes:

```java
redisTemplate.execute(script, keys, args);
```

time measured in Java spans several components:

```text
Client-side duration
  = waiting for connection / pool (if any)
  + serializing keys and arguments
  + sending request over network
  + waiting for server availability
  + Redis executing the Lua script
  + sending response back to client
  + deserializing result
  + application overhead
```

Thus, measuring `System.nanoTime()` around `execute(...)` shows **end-user perceived latency**, but **does not isolate how long Lua actually occupied the server**.

Conversely, `SLOWLOG` primarily records the time Redis spent **executing the command**, excluding network transit time. Observing both sides together distinguishes:

- The script itself is doing heavy work on the server.
- Redis was queued behind other expensive commands.
- Connection pools or networking caused delays.
- The client spent time parsing an oversized reply.

## 4. Why Can a Lua Script Be Slow Even Though It Sends Only One `EVAL`?

From the client's perspective, `EVAL` is one Redis command. Inside, however, it can run numerous loops and `redis.call(...)` invocations.

Example solely illustrating **an anti-pattern to avoid**:

```lua
-- Do not deploy this script on unbounded datasets.
local processed = 0

for i = 1, #KEYS do
    local members = redis.call('SMEMBERS', KEYS[i])

    for _, member in ipairs(members) do
        -- Assume multiple processing steps per member.
        processed = processed + 1
    end
end

return processed
```

Externally there is just **one `EVAL`**, yet internal work includes:

1. Iterating over every key in `KEYS`.
2. Reading all Set elements for each key with `SMEMBERS`.
3. Iterating across every Set element inside Lua.
4. Holding execution control throughout all those loops.

If inputs include thousands of keys and large Sets, runtime grows dramatically.

### 4.1. Complexity Contributes Directly to Blocking Time

| Operation pattern inside script | Risk |
|---|---|
| Read/write a single small Redis String | Usually clearly bounded work |
| Calling `HGET` on a few fixed fields | Usually small if command count is bounded |
| Looping over unbounded client-supplied `KEYS` | Scales with input key count |
| Calling `SMEMBERS`/`LRANGE 0 -1` on large collections | Reads all elements, builds Lua tables, consumes memory |
| `HGETALL` on a large hash | Work scales with field count |
| Nested loops across multiple datasets | Can explode rapidly with input size |
| Many write commands in a long loop | Extends the time the server cannot serve other requests |
| Running `KEYS pattern` inside a script on a large keyspace | Scans wide keyspace ranges, causing stalls |
| Running multiple `SCAN` iterations inside one script | Even though each SCAN step is small, the whole script holds Redis until done |

A common mistake is replacing `KEYS` with `SCAN` **inside a single script** and looping until the cursor returns to `0`. `SCAN` splits work at the command level, yet running all those steps inside **a single `EVAL`** still prevents Redis from serving other ordinary commands between Lua loop iterations.

When keyspace-wide atomicity is not needed, the right solution is **splitting work into multiple small calls**, allowing each call to finish so Redis can serve other traffic.

## 5. Does Redis Automatically Stop Long-Running Scripts?

Redis has a `lua-time-limit` setting, typically defaulting to **5,000 milliseconds**. You can inspect it on your instance:

```redis
CONFIG GET lua-time-limit
```

Illustrative output:

```text
lua-time-limit = 5000
```

Understand this setting accurately:

**`lua-time-limit` does not automatically roll back or forcibly kill every script at exactly 5 seconds.**

Once a script exceeds the threshold, Redis logs a warning about a slow script and permits a narrow set of administrative commands while busy. Other normal Redis commands receive errors like:

```text
BUSY Redis is busy running a script
```

The script may keep running until it finishes on its own or an operator intervenes via supported mechanisms. Never set `lua-time-limit = 5000` and assume the system can never block for more than 5 seconds.

### 5.1. What Are the Limits of `SCRIPT KILL`?

Redis supports:

```redis
SCRIPT KILL
```

This command can stop a slow-running script **only if the script has not yet performed any write operations**. This restriction prevents halting a script midway after it has already mutated Redis state.

Once a script has written data, Redis refuses `SCRIPT KILL` as a safe abort. In severe emergencies, Redis offers drastic administrative measures like stopping without saving (`SHUTDOWN NOSAVE`), which carries **data loss risk** and belongs in strict emergency runbooks—not everyday application timeout handling.

Things to keep in mind:

- Never write scripts assuming `SCRIPT KILL` can rescue every situation.
- Never use kill as a business timeout strategy.
- Never treat a client timeout as proof the script stopped on the server.
- When a script is busy, distinguish Redis `BUSY` errors from client-side timeouts.
- If using Redis Functions, management commands have their own names and conditions, such as `FUNCTION KILL` where applicable.

### 5.2. Client Timeouts Do Not Cancel Scripts on Redis

Suppose a Java client sets a 2-second timeout:

```text
t = 0s    Java sends EVAL
t = 2s    Java stops waiting and throws Redis command timeout
t = 5s    Script on Redis may still be running
t = 7s    Script finally finishes or errors
```

An application timeout only specifies **how long the client is willing to wait**. It never guarantees Redis cancelled the previously submitted work.

If a request fails and the application automatically retries a write script, it can inadvertently **apply the same mutation twice**. For critical operations, use a request identifier and server-side atomic idempotency tracking.

## 6. Designing Scripts with Bounded Steps and Bounded Input Data

A script suited for low-latency workloads typically has these traits:

- **Small, explicitly bounded** number of Redis commands inside.
- Never scans the entire Redis keyspace.
- Never reads full large Sets/Lists/Hashes when only a subset is needed.
- Validates inputs before executing write operations.
- Enforces loop bounds directly on the server, rather than trusting callers alone.
- Returns compact replies, avoiding returning huge datasets when a status code suffices.
- Contains no heavy CPU math or unbounded loops.
- Does not rely on manual intervention to kill runaway scripts.

### 6.1. Example: O(1)-Scoped Stock Script

A script operating on **a single key** is much easier to bound than one scanning multiple keys.

```lua
-- KEYS[1]: stock:sku-42
-- ARGV[1]: quantity to deduct, positive integer within business limit

if #KEYS ~= 1 or #ARGV ~= 1 then
    return redis.error_reply('invalid arguments')
end

local quantity = tonumber(ARGV[1])

if not quantity
   or quantity % 1 ~= 0
   or quantity < 1
   or quantity > 1000 then
    return redis.error_reply('invalid quantity')
end

local rawStock = redis.call('GET', KEYS[1])

if not rawStock then
    return -1 -- Stock does not exist
end

local currentStock = tonumber(rawStock)

if not currentStock then
    return redis.error_reply('invalid stock value')
end

if currentStock < quantity then
    return 0 -- Insufficient stock
end

-- All conditions checked before the write step.
return redis.call('DECRBY', KEYS[1], quantity)
```

Core flow:

```text
GET one key
  |
Parse and validate integer
  |
If insufficient -> return 0
If sufficient   -> DECRBY one key
```

Atomicity prevents race conditions between checking and subtracting stock. The limit `quantity <= 1000` is an **illustrative business rule** to reject bad inputs; not every script must use that exact cap.

Beyond quantity limits, ensure values stored in the key remain valid Redis integers within supported ranges. When operating on multiple keys, enforce similar caps on key counts, data sizes, and processing steps.

### 6.2. A Short Script Can Still Hit Large Data

Do not judge performance merely by counting lines of Lua. For instance:

```lua
return redis.call('HGETALL', KEYS[1])
```

is **one line**, yet a huge Redis Hash can make it slow and produce a massive response.

Similarly:

```lua
return redis.call('LRANGE', KEYS[1], 0, -1)
```

can read an entire List. When pagination or bounding is needed, enforce explicit ranges driven by business requirements and benchmark against maximum expected data sizes.

## 7. Splitting Large Work into Smaller Steps

Suppose an application needs to update hundreds of thousands of Redis records. Running one Lua script to find all keys and process them in a single `EVAL` would block Redis for a long time.

Instead, if all records do not strictly need to change state atomically together, you can:

1. Use an application worker to discover keys incrementally, e.g., using cursor/`SCAN` appropriately.
2. Form small batches with a capped key count.
3. Call a script that processes **one batch** or one specific data unit.
4. Let each script finish so Redis can serve other requests.
5. Monitor latency and handle failures/reprocessing if the worker is interrupted.

```text
Instead of:

EVAL [ process 100,000 keys at once ]
      |----------------------------------- long blocking time ----------------------------------|

Bounded design:

EVAL [batch 1] -> return result
            Redis can serve other commands
EVAL [batch 2] -> return result
            Redis can serve other commands
EVAL [batch 3] -> return result
...
```

Crucial trade-off: **batching gives up atomicity across the entire dataset**. If the business truly requires every record to transition together, revisit the storage model, use version flags, swap pointers to a new dataset, or use storage with appropriate transactions. You cannot demand a single script over huge datasets and expect zero blocking on Redis.

### 7.1. Enforce Key Limits Inside Lua Too

Even if clients batch requests, the script itself should reject oversized inputs:

```lua
local MAX_KEYS = 50

if #KEYS < 1 or #KEYS > MAX_KEYS then
    return redis.error_reply('too many keys')
end

for i = 1, #KEYS do
    redis.call('DEL', KEYS[i])
end

return #KEYS
```

This example only works safely when deleting each key has acceptable cost. `DEL` on a huge data structure can still take noticeable time freeing memory; capping at **50 keys** does not guarantee fast execution in every circumstance. For deleting large values, consider `UNLINK`, required atomicity scope, and memory reclamation behavior.

Input limits must account for **work hidden inside Redis commands**, not just the number of keys passed.

## 8. Measuring Script Call Duration in Spring Data Redis

Spring Data Redis executes scripts via `RedisTemplate.execute(RedisScript<T>, List<K>, Object...)`. With `DefaultRedisScript`, applications can load Lua from the classpath or provide inline script text.

Java example using `StringRedisTemplate` and measuring latency with `System.nanoTime()`:

```java
package com.example.redis;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class StockReservationService {

    private static final String DECREASE_STOCK_LUA = """
        if #KEYS ~= 1 or #ARGV ~= 1 then
            return redis.error_reply('invalid arguments')
        end

        local quantity = tonumber(ARGV[1])
        if not quantity
            or quantity % 1 ~= 0
            or quantity < 1
            or quantity > 1000 then
            return redis.error_reply('invalid quantity')
        end

        local current = redis.call('GET', KEYS[1])
        if not current then
            return -1
        end

        local stock = tonumber(current)
        if not stock then
            return redis.error_reply('invalid stock value')
        end

        if stock < quantity then
            return 0
        end

        return redis.call('DECRBY', KEYS[1], quantity)
        """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> decreaseScript;

    public StockReservationService(StringRedisTemplate redis) {
        this.redis = redis;
        this.decreaseScript =
                new DefaultRedisScript<>(DECREASE_STOCK_LUA, Long.class);
    }

    public long reserve(String sku, int quantity) {
        String key = "stock:" + sku;
        long startNanos = System.nanoTime();

        try {
            Long result = redis.execute(
                    decreaseScript,
                    List.of(key),
                    Integer.toString(quantity)
            );

            if (result == null) {
                throw new IllegalStateException(
                        "Redis script returned no result"
                );
            }

            return result;
        } finally {
            long elapsedNanos = System.nanoTime() - startNanos;
            long elapsedMillis =
                    TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

            // Simple illustration. In production, record histograms
            // with Micrometer/observability rather than logging every request.
            System.out.println(
                    "decrease_stock script call took "
                    + elapsedMillis + " ms"
            );
        }
    }
}
```

In this example:

- `DefaultRedisScript<Long>` sets the desired return type; Redis integer replies map accordingly.
- `StringRedisTemplate` handles key/argument serialization per template conventions.
- `execute(...)` runs the script on Redis; `EVALSHA`/reload fallback is handled by Spring Data Redis according to framework and driver capabilities.
- Timing in `finally` records duration on both success and exceptions.
- The measured time is **end-to-end call duration**, including network and client overhead, not Lua CPU time alone.
- Never attach metric tags for `sku`, session ID, or unbounded values; keep label cardinality low.

In production, record a Micrometer `Timer` with a stable script name such as `decrease_stock`, low-cardinality tags like `result=success|rejected|error`, and monitor p95/p99 and call rates. If a request timed out, account for uncertain execution outcomes before automatically retrying.

### 8.1. Separating Total Duration from Lua Execution Time

Sample observations from a test environment:

```text
App duration p99 of execute(...):   45 ms
Redis SLOWLOG command EVALSHA:       4 ms
```

One possibility is that most latency comes from connection-pool waits, networking, client processing, or queuing behind other commands. Inspect pool metrics, Redis load, and concurrent commands before drawing conclusions.

Another case:

```text
App duration p99 of execute(...):  250 ms
Redis SLOWLOG command EVALSHA:     238 ms
```

When server-side time accounts for nearly all latency, the Lua logic or Redis commands inside the script are prime candidates for optimization first.

These figures are purely illustrative; they are not mandatory thresholds in Spring Data Redis.

## 9. Using `SLOWLOG` to Spot Slow Scripts

Redis includes a **slow query log** recording commands whose server-side execution time exceeds a configured threshold.

Check configuration:

```redis
CONFIG GET slowlog-log-slower-than
CONFIG GET slowlog-max-len
```

`slowlog-log-slower-than` is measured in **microseconds**. For instance, `10000` means 10 ms—not 10,000 ms.

View recent entries:

```redis
SLOWLOG GET 20
```

View total logged entries:

```redis
SLOWLOG LEN
```

In a test environment where configuration changes are permitted, you can lower the threshold to log commands taking more than 2 ms:

```redis
CONFIG SET slowlog-log-slower-than 2000
```

`2000` equals 2,000 microseconds. **This is an illustrative test configuration**; never lower thresholds in production without assessing log volume and permission restrictions of your Redis service.

### 9.1. How to Read SLOWLOG Output?

A SLOWLOG entry typically shows:

- Entry ID.
- Timestamp recorded.
- Command execution duration in microseconds.
- Command info and arguments (displayed/truncated per Redis log rules).
- Client metadata on supported Redis versions.

If a script ran via `EVALSHA`, the SLOWLOG entry lists `EVALSHA` along with its script SHA/arguments. You will not necessarily see the full Lua source when invoked by SHA.

**SLOWLOG records commands that have already completed and exceeded the threshold**, so a script still running/stuck may not appear in the log yet. When debugging a live incident, combine SLOWLOG with `BUSY` symptoms, latency metrics, and Redis operational status.

`SLOWLOG` answers "How long did one `EVAL`/`EVALSHA` occupy the server?", not which specific Lua loop caused the delay. To pinpoint expensive sections, analyze the algorithm and input sizes, and benchmark safe variations in a test environment.

## 10. Measuring Redis-Wide Latency with `LATENCY` and Other Tools

Redis provides **latency monitoring** to capture latency spikes once enabled.

Check threshold:

```redis
CONFIG GET latency-monitor-threshold
```

In a test environment, enable an illustrative 10 ms threshold:

```redis
CONFIG SET latency-monitor-threshold 10
```

Inspection commands:

```redis
LATENCY LATEST
LATENCY HISTORY command
LATENCY DOCTOR
```

Note that event names in `LATENCY HISTORY` depend on events Redis actually recorded; `command` is one event type that may appear. `LATENCY DOCTOR` summarizes diagnostics from recorded events and does not replace SLOWLOG or end-to-end application timing.

Other useful commands and metrics:

```redis
INFO commandstats
INFO stats
INFO cpu
INFO memory
```

`redis-cli` utilities in operational environments:

```bash
redis-cli --latency
redis-cli --latency-history
```

`INFO commandstats` reports total calls and time aggregates per command type, helpful for checking whether `eval`/`evalsha` consume significant processing share. However, these are per-command-type aggregates, not per-script p99s.

### 10.1. Combining Multiple Measurement Sources

| Source | What it observes | Limits to remember |
|---|---|---|
| `System.nanoTime()` around `redis.execute(...)` | End-to-end duration perceived by the app | Includes network, pool, serialization, and Redis queuing |
| Micrometer Timer/histogram | Call counts, p95/p99, errors by script name | Requires careful tag and metric-count management |
| Redis `SLOWLOG` | Server-side execution duration of slow commands | Records only completed commands above threshold |
| Redis `LATENCY` | Redis latency spike events if enabled | Depends on threshold and event types |
| `INFO commandstats` | Call counts/total time per command type | Cannot distinguish individual scripts sharing `EVALSHA` |
| `redis-cli --latency` | Latency observed from a Redis client | Affected by network and test environment |
| Error/timeout/BUSY metrics | Impact on availability | Does not directly pinpoint root cause or Lua step count |

A script that feels fast on a developer laptop can become slow under real data volumes and high concurrency. Measure both Redis server metrics **and** application requests under large inputs and concurrent traffic.

## 11. Setting a Time Budget for Lua Scripts

There is no universal rule like "every Lua script must take under 5 ms." A sound budget depends on:

- User-facing API p95/p99 requirements.
- Redis server load from other applications.
- Script invocation frequency.
- Processing time of other commands.
- Expected future growth in data sizes.
- Differences across Redis standalone, replication, and cluster.
- Client timeout and connection-pool settings.

For example, if an API requires p99 latency under 100 ms while DB/Redis/network steps share that budget, an 80 ms Lua script already consumes most of the allowance. If called frequently, it also delays unrelated requests.

Illustrative budget breakdown:

```text
Total API p99 budget:             100 ms

- Network/application overhead:    25 ms
- Other system queries:            40 ms
- Redis calls and wait time:       20 ms
- Headroom:                        15 ms
```

In this example, a single script should not consume the entire 20 ms without leaving room for Redis queuing or network transit. Aim well below that allowance and validate with load testing.

### 11.1. Frequency Matters as Much as Single-Run Duration

A script taking 10 ms once an hour has a very different average impact than a 10 ms script running dozens of times per second.

Consider both together:

```text
Single-script cost x Script calls per second
      -> pressure on Redis command execution thread
```

This rough estimate helps gauge capacity utilization; it cannot predict exact p99 latency since arrival distributions, command mix, I/O, and runtime factors also matter.

## 12. Benchmarking Across Input Sizes, Not Just One Tiny Sample

When evaluating a script, test across **growing input sizes** along any dimension that affects complexity:

| Scenario | Data | Observation goal |
|---|---|---|
| Small | One String key, one check | Baseline minimum script cost |
| Medium | Tens of keys or hundreds of elements if required | How duration scales with work |
| Large within supported cap | Batch at the enforced input cap | p95/p99 and impact on other commands |
| High contention | Many clients calling same script/key | Queuing, throughput, and retries |
| Large data structures | Hash/Set/List near maximum expected size | Hidden costs in `HGETALL`, `SMEMBERS`, etc. |
| Error cases | Missing key, wrong type, invalid data | Script rejects fast without partial writes |
| Redis Cluster | Keys distributed across real hash slots | Routing bounds and per-node timing |

### 12.1. Never Benchmark Lua Only on an Idle Server

A script taking 1 ms on an idle Redis instance can cause noticeable disruption when hundreds of concurrent requests are queued.

A meaningful benchmark typically includes:

1. Populating data at realistic sizes.
2. Generating representative background `GET`/`SET` traffic.
3. Calling the script at expected request rates.
4. Measuring script timing on both client and Redis, alongside background p95/p99 latency.
5. Testing inputs near maximum limits and under high concurrency.
6. Reducing scope if the script inflates tail latency for background traffic.

The goal is not forcing every script to run in identical time, but establishing **safe workload bounds** and understanding behavior as data and call rates grow.

## 13. Strategies to Reduce How Long Scripts Hold the Redis Server

### 13.1. Prefer Native Redis Commands When They Suffice

To increment a counter, use:

```redis
INCR metrics:views:42
```

Do not write Lua just to do:

```lua
local value = tonumber(redis.call('GET', KEYS[1]) or '0')
redis.call('SET', KEYS[1], value + 1)
return value + 1
```

`INCR` already reads, adds, and writes atomically with less code. Besides performance, native commands eliminate type-conversion bugs and concurrency mistakes.

Likewise, consider `SET ... NX EX`, `HINCRBY`, `SADD`, `GETDEL`, and other built-in Redis commands whenever they express the operation directly.

### 13.2. Keep Simple Checks on the Server, Heavy Processing in the Application

Lua fits small logic like:

```text
Read 1-2 values
  |
Check condition
  |
Write 1-2 values
  |
Return status
```

Avoid pushing complex domain processing, large data joins, report calculations, or full keyspace scans into Lua just to save round trips.

Whenever possible, process large data outside Redis in the application and let Lua handle only the final atomic check and update.

### 13.3. Bound Counts and Data Sizes

Enforce bounds on:

- Number of keys in `KEYS`.
- Number of elements read from collections.
- Loop iteration counts.
- Payload and response sizes.
- Numeric ranges in `ARGV`.
- Number of write operations a script can issue.

Check these bounds **at the very top of the script**, before running expensive commands.

### 13.4. Design Data Structures to Avoid Full Scans

If you frequently need "find the highest-scoring item," prefer a Sorted Set and rank/score lookup commands rather than scanning all Set members inside Lua.

If you frequently need "check whether an email already exists," use a dedicated lookup key or appropriate structure instead of fetching an entire user list and looping.

If you frequently need to remove expired keys, rely on native TTLs instead of periodic Lua scripts scanning all keys.

**Adjusting the data model** is usually far more effective than micro-optimizing Lua syntax over a broad scan.

### 13.5. Split into Batches and Scope Transactions Per Unit

When global atomicity across the whole dataset is not required, split work into small scripts to minimize server blocking per call. Use cursors/progress markers and idempotency so workers can resume after failures.

State the business trade-off explicitly: Batch 1 may finish while Batch 2 has not yet run. If intermediate states are unacceptable, adopt a versioned-data pattern or a more suitable transactional store.

### 13.6. `EVALSHA` Helps Script Delivery, Not Algorithmic Speed

Spring Data Redis can load scripts and invoke them by SHA when supported by the driver and framework. This avoids resending the full script text on every call and can cut transmission/compilation overhead in some cases.

Yet:

```text
EVALSHA <sha> 1 key arg
```

**still runs every loop and `redis.call(...)` inside the script**. If the algorithm iterates over a million items, switching from `EVAL` to `EVALSHA` does not make it fast or non-blocking.

## 14. When Redis Is Blocked by a Long Script: Reading Symptoms Properly

Common symptoms:

- Latency spikes across `GET`, `SET`, `PING`, and other requests.
- Clients hit command timeouts even though network connectivity remains intact.
- Redis logs warnings about a script exceeding its time limit.
- Normal commands receive `BUSY Redis is busy running a script`.
- `SLOWLOG` shows very slow `EVAL`/`EVALSHA` entries after the script completes (if above threshold).
- CPU spikes on the Redis node (still distinguish from other CPU-heavy work).

A sound operational response sequence:

1. **Determine blast radius:** which Redis nodes, services, and command types show latency spikes.
2. **Inspect application and Redis metrics:** latency, `BUSY` errors, timeouts, and Redis SLOWLOG/LATENCY where available.
3. **Identify the invoked script:** business name, SHA/script ID, call frequency, key count, and input sizes.
4. **Check whether the script is still running or finished:** SLOWLOG usually reports only completed commands.
5. **If the script is stuck running:** follow your Redis runbook and `SCRIPT KILL` if no writes occurred; never assume safe termination after writes.
6. **Fix the root cause:** cap batch sizes, remove full scans, use native commands, add metrics and input limits.
7. **Audit retries and idempotency:** timed-out requests may already have executed; do not blindly replay writes.

With managed Redis services, commands like `CONFIG`, `SCRIPT KILL`, or certain admin tools may be restricted. Rely on supported metrics, logs, and provider operational controls in those environments.

## 15. Does Redis Cluster Avoid All Script-Blocking Issues?

Redis Cluster distributes keys across hash slots and nodes. A Lua script executes on the node serving its accessed keys; **command blocking occurs on that node**, without automatically blocking other cluster nodes.

Example:

```text
Redis Cluster

Node A: cache + slot group A stock
   |
   +--- Long EVAL on Node A
   |       -> other commands served by Node A may slow down
   |
Node B: keys in slot group B
   |
   +--- continues serving Node B's own commands
```

However:

- Script-accessed keys must obey cluster routing and hash-slot rules.
- If workload concentrates on one node/hot slot, a slow script can still severely degrade the application.
- Adding nodes does not automatically make a script scanning huge data safe.
- Atomic multi-key operations cannot arbitrarily span independent shards.
- If one application request awaits keys from multiple nodes, one blocked node still slows the entire request.

Keeping scripts short with clearly bounded work therefore remains vital in Redis Cluster.

## 16. Lua Scripts vs. `MULTI/EXEC` Regarding Blocking Time

Both Lua and Redis transactions prevent other commands from interleaving **while the atomic unit executes**. They differ in how logic is defined:

| Criterion | Lua `EVAL`/`EVALSHA` | `MULTI`/`EXEC` |
|---|---|---|
| Conditional logic | Supports `if`, loops, and branching on intermediate command results directly on the server | Commands are queued; the application does not have `GET` results to branch before `EXEC` |
| Execution lock duration | Throughout the entire script execution | During the phase where Redis executes the queued commands at `EXEC` |
| Risk of long execution | Loops, large datasets, expensive commands | Large queues of commands or heavy commands |
| Rollback on runtime error | No general rollback | No general rollback |
| Transactions with external DBs | No | No |
| Conflict handling tools | Conditions written inside script | Can use `WATCH` before `MULTI` |

If heavy work is queued into `MULTI/EXEC`, Redis can still become busy executing that batch. Moving the exact same workload from Lua into `MULTI` does not guarantee fixing latency.

The goal is **shortening how long Redis executes continuously without yielding to other commands**, through small operations and bounded workloads.

## 17. Misconceptions About Lua Runtime

**"A Lua script is a single Redis command, so it must be very fast."** False. One `EVAL` can invoke tens of thousands of Redis commands internally and scan massive datasets.

**"Atomicity only concerns data correctness, not latency."** False. Preventing interleaving simultaneously prevents other ordinary commands from running while the script executes.

**"Setting `lua-time-limit = 5000` makes scripts auto-stop after 5 seconds."** False. That threshold primarily detects slow scripts and enters busy-handling state; it performs no automatic rollback or hard stop at that mark.

**"`SCRIPT KILL` always works when a script hangs."** False. Redis refuses to kill a script via standard kill once it has written data.

**"A client timeout means the script stopped running."** False. The client can stop waiting while the server keeps executing.

**"Replacing `KEYS` with `SCAN` inside the same script prevents blocking."** False. If the `SCAN` loop runs entirely inside one `EVAL`, the script still holds execution control until it finishes.

**"A script with a single `HGETALL` cannot be slow."** False. A single command reading a huge data structure can still take considerable time.

**"`EVALSHA` makes heavy scripts algorithmically faster."** False. It optimizes script transmission/loading in some scenarios, without changing internal work volume.

**"Splitting a script into batches keeps the whole job atomic."** False. Atomicity then applies only per batch; you must design intermediate states and recovery.

**"No SLOWLOG entries means no slow scripts."** Inconclusive. The threshold may be too high, log entries evicted, a running script not yet finished, or the bottleneck in networking/pooling.

**"Lua rolls back automatically if an exception occurs."** False. Writes already completed inside the script are not automatically reverted if a later step errors.

## 18. Design Checklist for a New Lua Script

Before running a script against real traffic, check:

| Question | Decision guideline |
|---|---|
| Which invariant does the script protect? | State clearly what must be checked/updated atomically |
| Can a single Redis command do this? | If yes, prefer the native command |
| What is the maximum number of keys processed? | Enforce an explicit limit inside the script |
| What is the maximum size of data inside each key? | Evaluate complexity of `HGETALL`, `SMEMBERS`, `LRANGE`, etc. |
| Are there data-dependent loops? | Cap iterations; consider batching |
| Are any expensive Redis commands used? | Choose cheaper data structures/commands when possible |
| Are error conditions validated before writes? | Put validation first to avoid partial updates |
| Can client timeouts occur? | Handle unknown outcomes and idempotency |
| What is the script's latency target? | Base it on p99 budgets and call frequency |
| Have both script and background traffic been measured? | Use client metrics, SLOWLOG/LATENCY, and realistic load tests |
| Will it run on Cluster? | Check hash slots, nodes, and key limits |
| How are slow-script incidents handled? | Maintain a runbook; know `SCRIPT KILL` limits and admin risks |

Runtime evaluation must be part of invariant design, because choosing "update everything in one atomic call" trades off directly against Redis node latency.

## 19. Synthesis Scenario: Replacing a Scanning Script with Short Scripts

Suppose a system tracks learning events. Initially, a periodic script had to:

```text
1. Find all progress:* keys.
2. Read each key.
3. Check for inactive learners.
4. Delete or update status.
5. Return total processed learners.
```

If the script scans the entire keyspace itself, it processes ever-growing key counts and slows down APIs sharing Redis.

An alternative design:

```text
Application-side worker
    |
    +-- SCAN / read IDs in batches outside scripts
    |
    +-- EVAL update_one_progress(key1) ----> finishes
    +-- EVAL update_one_progress(key2) ----> finishes
    +-- EVAL update_one_progress(key3) ----> finishes
    |
    +-- Save checkpoint/progress
    +-- Continue next batch
```

Each single-learner script handles one tiny operation, such as:

```lua
-- Example: mark progress inactive only if currently ACTIVE.
if redis.call('HGET', KEYS[1], 'status') ~= 'ACTIVE' then
    return 0
end

redis.call('HSET', KEYS[1], 'status', 'INACTIVE')
return 1
```

Limiting execution scope lets other commands run between `EVAL` calls. The worker handles retries, checkpoints, and data changing during scanning. If the requirement truly demands "all users change status simultaneously," design around data versioning or a suitable transactional model, since batching cannot deliver global atomicity.

## 20. Conclusion

Lua in Redis is powerful for **atomic server-side checks and updates**, at the cost of **holding command execution control for its entire runtime**. A long script raises latency for small commands from other clients, triggering timeouts or `BUSY` errors.

With Spring Data Redis, do not stop at asking "Is the script logic right?"—also answer:

1. **What is the script's worst-case workload?**
2. **What are Redis execution time and client-perceived latency, especially at p95/p99?**
3. **How does the script affect commands from other apps sharing the server?**
4. **If a timeout or partial failure happens, can the app retry and recover safely?**

Effective practice keeps scripts short, caps keys and input data, prefers native commands when sufficient, batches large jobs when business rules allow, pairs **client latency** with Redis **SLOWLOG/LATENCY**, and avoids treating `lua-time-limit` as an automatic script stopper.

When **runtime** is treated as part of **atomicity design**, applications can leverage Lua to eliminate race conditions without turning Redis into a system-wide bottleneck.
