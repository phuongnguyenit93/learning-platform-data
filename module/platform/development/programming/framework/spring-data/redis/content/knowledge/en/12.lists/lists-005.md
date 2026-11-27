# Moving Elements Between Lists

In Redis, a **List** is an ordered data structure that allows adding and removing elements at the **head (LEFT)** or **tail (RIGHT)**. With Spring Data Redis, many applications use Lists to store pending jobs, temporary task lists, or steps in a workflow. When moving an element from one List to another, the operation must be designed so that elements are not lost or accidentally picked up by two consumers at the same time.

Redis provides two primary commands for this need:

- **`LMOVE`**: removes an element from one end of a source List and pushes it onto one end of a destination List in **a single atomic command**.
- **`BLMOVE`**: the same operation, except it **waits** when the source List is empty until data arrives or a timeout expires.

Spring Data Redis exposes corresponding operations in `ListOperations`, notably `move(...)`. You may also encounter `rightPopAndLeftPush(...)`, an API tied to the legacy Redis commands `RPOPLPUSH`/`BRPOPLPUSH`.

This lesson focuses on **the semantics of moving elements**, source/destination direction choices, atomicity, blocking moves, the `pending → processing` queue pattern, job recovery limitations, and proper usage in a Spring Boot application.

## 1. Why Move Elements Between Two Redis Lists?

Suppose an application has pending jobs waiting to be processed:

~~~text
jobs:pending
LEFT                         RIGHT
[job-101, job-102, job-103]
~~~

A worker wants to take `job-101` for processing. The simple approach is:

~~~text
LPOP jobs:pending
-> job-101
~~~

After this command, `job-101` is no longer in the source List. If the worker crashes right after receiving the job but before finishing it, Redis has no explicit record in any list showing that the job was claimed.

A **second List** can be used:

~~~text
jobs:pending                   jobs:processing

[job-101, job-102, job-103]   []
             |
             | LMOVE source destination LEFT RIGHT
             v

[job-102, job-103]             [job-101]
~~~

One Redis operation both removes `job-101` from `pending` and places it in `processing`. If the worker stops after the move, the job remains in `processing` so the system has a chance to detect and reprocess it.

This is useful when an application must track jobs that have been **claimed but not yet acknowledged**. However, **a second List by itself does not form a complete reliable queue**; failure handling, timeouts, acknowledgement, and recovery require additional mechanisms.

## 2. A Redis List Has Two Ends: LEFT and RIGHT

A List can be visualized as follows:

~~~text
Key: queue:pending

LEFT                                RIGHT
[A, B, C, D]
 ^                                    ^
 first element                      last element
~~~

Basic operations:

| Redis Command | Effect | Result on `[A, B, C, D]` |
|---|---|---|
| `LPUSH key X` | Add X to LEFT | `[X, A, B, C, D]` |
| `RPUSH key X` | Add X to RIGHT | `[A, B, C, D, X]` |
| `LPOP key` | Pop and remove LEFT element | Returns A; List becomes `[B, C, D]` |
| `RPOP key` | Pop and remove RIGHT element | Returns D; List becomes `[A, B, C]` |
| `LRANGE key 0 -1` | Read elements in order | `[A, B, C, D]` |
| `LLEN key` | Return number of elements in List | 4 |

In queue applications, the most important rule is the **push and pop direction convention**:

- **FIFO**: the element added first is popped first. For instance, producer uses `RPUSH`, consumer uses `LPOP`.
- **LIFO**: the element added most recently is popped first. For instance, producer uses `RPUSH`, consumer uses `RPOP`.
- When moving between Lists, you must also choose **which end of the destination List** receives the element.

A wrong direction choice can reverse processing order while the code still runs without errors.

## 3. LMOVE: The Atomic Element-Moving Command

Redis syntax:

~~~text
LMOVE source destination LEFT|RIGHT LEFT|RIGHT
~~~

Four arguments:

1. `source`: key of the source List.
2. `destination`: key of the destination List.
3. First `LEFT` or `RIGHT`: which end of source to **pop** from.
4. Second `LEFT` or `RIGHT`: which end of destination to **push** onto.

The command returns **the moved element's value**, or `nil` if the source List is empty. When source/destination is not a data type supporting List operations, Redis can return a `WRONGTYPE` error.

### 3.1. Basic Redis CLI Example

Create two lists (examples in this lesson assume the demo keys do not yet exist):

~~~bash
redis-cli RPUSH demo:pending A B C
redis-cli RPUSH demo:processing X Y

redis-cli LRANGE demo:pending 0 -1
# 1) A
# 2) B
# 3) C

redis-cli LRANGE demo:processing 0 -1
# 1) X
# 2) Y
~~~

Move an element from the LEFT of source to the RIGHT of destination:

~~~bash
redis-cli LMOVE demo:pending demo:processing LEFT RIGHT
# "A"
~~~

After the command:

~~~text
demo:pending      = [B, C]
demo:processing   = [X, Y, A]
~~~

Redis executes the pop and push in **one atomic command**: no other client can observe an intermediate state where "A has been popped from pending but not yet pushed into processing."

**The atomicity of LMOVE covers only the transfer between the two Lists.** It does not cover the worker processing files, calling external APIs, writing to a database, or sending emails afterward.

### 3.2. Four Transfer Patterns of LMOVE

Assume each case starts with:

~~~text
source      = [A, B, C]
destination = [X, Y]
~~~

| Command | Moved Element | Source After Command | Destination After Command |
|---|---|---|---|
| `LMOVE source destination LEFT LEFT` | A | `[B, C]` | `[A, X, Y]` |
| `LMOVE source destination LEFT RIGHT` | A | `[B, C]` | `[X, Y, A]` |
| `LMOVE source destination RIGHT LEFT` | C | `[A, B]` | `[C, X, Y]` |
| `LMOVE source destination RIGHT RIGHT` | C | `[A, B]` | `[X, Y, C]` |

Both directions matter:

- The **pop** direction determines which element is picked first.
- The **push** direction determines element ordering inside the destination List.

For example, `RIGHT LEFT` commonly appears in docs describing the `LPUSH + RPOPLPUSH` pattern: producers push new jobs at LEFT, and consumers pick the oldest job at RIGHT and move it to LEFT of processing.

If the producer chose `RPUSH` for FIFO, workers typically use `LEFT RIGHT` when moving to processing to pick the oldest job.

## 4. LMOVE Can Also Rotate Elements Within the Same List

`source` and `destination` can be **the same key**.

~~~text
queue:round-robin = [A, B, C]
~~~

Call:

~~~bash
redis-cli LMOVE queue:round-robin queue:round-robin RIGHT LEFT
# C
~~~

After the command:

~~~text
queue:round-robin = [C, A, B]
~~~

This is a **rotate** operation: the last element moves to the front. Conversely:

~~~bash
redis-cli LMOVE queue:round-robin queue:round-robin LEFT RIGHT
~~~

rotates the first element to the end.

Possible use cases:

- A list of resources needing round-robin cycling.
- A small set of tasks retried under simple rotation.
- Alternating steps in a small workflow.

However, rotating within a single List **does not guarantee fairness** when multiple consumers contend, or if one worker holds a resource longer than another. Be clear about when a queue is appropriate versus another coordination mechanism.

## 5. Moving Between Lists in Spring Data Redis

In Spring Data Redis, the primary API group is `ListOperations<K, V>`:

~~~java
ListOperations<String, String> listOps =
        stringRedisTemplate.opsForList();
~~~

In Spring Data Redis versions supporting `LMOVE`, you can call:

~~~java
listOps.move(
        "demo:pending",
        Direction.LEFT,
        "demo:processing",
        Direction.RIGHT
);
~~~

`Direction` is the enum representing the two ends of a Redis List. In the Spring Data Redis 3.x branch, import:

~~~java
import org.springframework.data.redis.connection.RedisListCommands.Direction;
~~~

### 5.1. Non-Blocking Job Transfer Service Example

~~~java
import org.springframework.data.redis.connection.RedisListCommands.Direction;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class JobTransferService {

    private static final String PENDING = "jobs:pending";
    private static final String PROCESSING = "jobs:processing";

    private final StringRedisTemplate redis;

    public JobTransferService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long enqueue(String jobId) {
        // Producer appends to the end of the list.
        return redis.opsForList().rightPush(PENDING, jobId);
    }

    public String claimNext() {
        // Pop the first element and append it to the end of processing.
        return redis.opsForList().move(
                PENDING,
                Direction.LEFT,
                PROCESSING,
                Direction.RIGHT
        );
    }
}
~~~

Suppose:

~~~text
RPUSH jobs:pending job-101 job-102 job-103
~~~

then three consecutive `claimNext()` calls can return:

~~~text
job-101
job-102
job-103
~~~

assuming no other concurrent consumers and no producer altering order. If multiple workers call `claimNext()` concurrently, each transfer is executed by Redis as an atomic command, so **a specific element at the head of source cannot be claimed by both calls simultaneously**.

Note: this **does not mean** a job ID can never appear twice. If a producer pushes two elements with the same value `job-101`, both copies can be moved and processed.

### 5.2. When the Source List Is Empty

With non-blocking `LMOVE`:

~~~java
String jobId = redis.opsForList().move(
        PENDING, Direction.LEFT,
        PROCESSING, Direction.RIGHT
);

if (jobId == null) {
    // No job available at the time of the call.
}
~~~

Redis returns `nil` when the source List is empty; Spring Data Redis typically maps this to `null` in direct calls. Some APIs can also return `null` inside transaction/pipeline contexts before results are materialized; therefore, do not make the same assumption across all execution modes.

If you need to wait for new jobs instead of polling Redis continuously, use an appropriate blocking command.

## 6. BLMOVE: Moving and Waiting When No Element Is Available

Syntax:

~~~text
BLMOVE source destination LEFT|RIGHT LEFT|RIGHT timeout
~~~

`BLMOVE` has the same element-moving semantics as `LMOVE`, except when source is empty Redis **waits** for data to appear:

- An element arrives before the deadline: moves the element and returns its value.
- Timeout expires while still empty: returns `nil`.
- `timeout = 0` in the Redis protocol means wait indefinitely.
- Redis timeouts use seconds and may support decimal values; exact compatibility depends on the Redis/driver version.

Example:

~~~bash
# Consumer terminal, waiting up to 5 seconds
redis-cli BLMOVE jobs:pending jobs:processing LEFT RIGHT 5
~~~

If another terminal pushes a job:

~~~bash
redis-cli RPUSH jobs:pending job-202
~~~

the waiting consumer can receive:

~~~text
job-202
~~~

and `job-202` has already been moved into `jobs:processing`.

### 6.1. Spring Data Redis Uses Duration for Blocking Operations

~~~java
import java.time.Duration;

import org.springframework.data.redis.connection.RedisListCommands.Direction;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class BlockingJobReceiver {

    private static final String PENDING = "jobs:pending";
    private static final String PROCESSING = "jobs:processing";

    private final StringRedisTemplate redis;

    public BlockingJobReceiver(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String receive() {
        return redis.opsForList().move(
                PENDING,
                Direction.LEFT,
                PROCESSING,
                Direction.RIGHT,
                Duration.ofSeconds(5)
        );
    }
}
~~~

`receive()` can hold the calling thread for the wait duration. If 5 seconds pass with source still empty, the return value is normally `null`.

**Blocking commands should not be called casually on HTTP request threads or a single-threaded scheduler.** A dedicated consumer, a bounded worker executor, or an appropriate background processing architecture makes wait times and application shutdown much easier to control.

### 6.2. Redis Timeout and Client Timeout Must Be Compatible

Suppose `BLMOVE` waits up to 30 seconds, yet the Redis client is configured with a 2-second command timeout. The client may time out after 2 seconds before Redis finishes its wait.

With Lettuce, Spring Data Redis can use dedicated connections for **blocking operations**, though you still must consider:

- The timeout of the `BLMOVE` command itself.
- Client-side command/socket timeouts.
- Number of concurrently waiting connections and pool limits.
- Reconnection, cancellation, and shutdown behavior.
- The case where Redis already moved the element but the client never received the response due to a dropped connection.

Do not treat `BLMOVE` as a guaranteed "either executed or did not execute" read from the client's perspective. A timeout after Redis already moved the element must be handled by inspecting/recovering items in `processing`.

## 7. RPOPLPUSH and BRPOPLPUSH: The Historical Approach

Before Redis introduced `LMOVE`/`BLMOVE`, two common commands were:

~~~text
RPOPLPUSH source destination
BRPOPLPUSH source destination timeout
~~~

They correspond to fixed directions:

~~~text
RPOPLPUSH source destination
≈ LMOVE source destination RIGHT LEFT

BRPOPLPUSH source destination timeout
≈ BLMOVE source destination RIGHT LEFT timeout
~~~

Redis 6.2 introduced `LMOVE` and `BLMOVE` while marking the older pair **deprecated** in favor of a more flexible API. The older commands still frequently appear in legacy systems and tutorials, so knowing what they mean helps when reading legacy code.

In Spring Data Redis, you may encounter:

~~~java
String jobId = redis.opsForList()
        .rightPopAndLeftPush("jobs:pending", "jobs:processing");
~~~

Or the blocking variant with a timeout:

~~~java
String jobId = redis.opsForList()
        .rightPopAndLeftPush(
                "jobs:pending",
                "jobs:processing",
                Duration.ofSeconds(5)
        );
~~~

These methods encode **RIGHT → LEFT**, so they are not a drop-in replacement for an `RPUSH + LEFT → RIGHT` flow if FIFO order must be preserved. In new code on supporting Redis versions, `move(...)` makes both directions explicit.

### 7.1. Do Not Confuse Similarly Named Commands

| Command | Meaning |
|---|---|
| `LMOVE` | Move **one List element** from one List key to another List key |
| `BLMOVE` | `LMOVE` with blocking wait when source List is empty |
| `RPOPLPUSH` | Move source RIGHT element to destination LEFT (legacy) |
| `BRPOPLPUSH` | Blocking version of `RPOPLPUSH` (legacy) |
| `LPOP`/`RPOP` | Pop/remove an element from one List; does not atomically move to another List |
| `MOVE key db` | Move an **entire key** to another logical database where supported; not a List element move |
| `RENAME` | Rename an entire key and its data; not `LMOVE` |

`LMOVE` does not transfer keys to a different Redis server. It remains a Redis List command within the same Redis system serving the participating keys.

## 8. Atomicity: Why Not Use LPOP Followed by RPUSH?

Easy-to-write code:

~~~java
String job = redis.opsForList().leftPop("jobs:pending");
if (job != null) {
    redis.opsForList().rightPush("jobs:processing", job);
}
~~~

Two separate Redis commands leave a gap:

~~~text
Consumer                   Redis
   |                         |
   +---- LPOP pending ------>|
   |<--- job-101 ------------+
   |
   X App crashes before RPUSH
   |
   |               job-101 is gone from pending
   |               and not yet in processing
~~~

`LMOVE` closes this exact gap:

~~~text
Consumer                   Redis
   |                         |
   +---- LMOVE ------------->|
   |       (atomic pop + push on server)
   |<--- job-101 ------------+
   |
   X Crashes after receiving
             |
             +-- job-101 remains in processing
~~~

**Important limitation:** if the Redis primary executed `LMOVE` and a failover occurred before replicas received the change, some results can still be lost due to asynchronous replication. Command atomicity is not a guarantee against data loss during system-wide failures.

### 8.1. Can a MULTI/EXEC Transaction Replace It?

Commands can be grouped in a Redis transaction, yet to move **the exact element just popped** from source to destination, the client needs that value. Calling `LPOP` and then `RPUSH` from Java still leaves a pause between them. Wrapping flawed logic in a standard transaction does not conveniently yield a "pop value and push it into destination" command.

`LMOVE` already expresses the right operation in a single short command. If moving an element requires more complex business conditions, a Lua script on appropriate keys may be an option, subject to error handling and Redis Cluster constraints.

## 9. Designing a Pending → Processing → Acknowledged Queue

Common pattern:

~~~text
                     Producer
                        |
                    RPUSH jobId
                        |
                        v
                 jobs:pending
                        |
                BLMOVE LEFT RIGHT
                        |
                        v
                jobs:processing
                        |
                 Worker processes job
                   /          \
               Success      Failure/crash
                  |               |
             LREM by ID       Keep for
             (acknowledge)    recovery/retry
                  |
                  v
               Complete
~~~

This is a **basic reliable queue pattern**, where every job claimed from pending stays visible in processing until acknowledged.

### 9.1. Producers Should Push Stable IDs, Not Stuff Huge Payloads

Example:

~~~bash
redis-cli RPUSH jobs:pending job-101 job-102 job-103
~~~

Each element is a **unique job ID**; the payload can live in a database or a separate Hash as needed. Benefits of using IDs:

- Smaller Lists.
- Easy job tracing by ID.
- Exact targeting with `LREM` on completion.
- Simpler idempotency in business handling.
- Avoids serializing/deserializing large payloads on every move.

If payloads are stored in Redis alongside IDs, define TTL and cleanup rules when jobs complete. Avoid leaving orphaned payloads indefinitely after items are removed from the List.

### 9.2. Consumer Claims a Job Atomically

~~~java
String jobId = redis.opsForList().move(
        "jobs:pending",
        Direction.LEFT,
        "jobs:processing",
        Direction.RIGHT,
        Duration.ofSeconds(5)
);
~~~

The consumer receives the ID and begins processing. Multiple workers can run concurrently; Redis executes each move atomically so each **element** in pending is moved by only one command at a time.

**ID uniqueness is a separate contract.** If a producer accidentally pushes `job-101` twice, two workers can still claim two copies with the same value.

### 9.3. Acknowledging After Successful Processing

Once business processing succeeds, delete **one element matching the job ID** from `processing`:

~~~java
Long removed = redis.opsForList()
        .remove("jobs:processing", 1, jobId);
~~~

Corresponding Redis command:

~~~bash
redis-cli LREM jobs:processing 1 job-101
~~~

`count = 1` deletes the first matching element scanning from LEFT to RIGHT. When job IDs are unique in processing, this acts as a simple acknowledgement.

Notes:

- `LREM`'s complexity depends on List length; a very long processing List can make ACKs expensive.
- If duplicate job IDs exist, removing the first occurrence may not correspond to the specific attempt being acknowledged.
- If the return value is `0`, the element was no longer in processing; investigate whether it was already ACKed, reclaimed, or hit a synchronization issue.
- Never ACK before business logic completes; if a worker crashes after ACK but before finishing, the job is no longer tracked.

### 9.4. What If a Worker Crashes?

If a worker stops while a job is still in `processing`, Redis Lists have no built-in concept of **"which worker owns this job, how long it has been running, or whether its lease expired."** Without additional metadata or monitoring, the job can sit in processing forever.

A recovery design typically needs:

1. Tracking `IN_PROGRESS` status, claim timestamp, and processing deadline per job.
2. A periodic reclaimer identifying jobs without heartbeats or past their deadline.
3. Checking whether the job actually finished.
4. Moving the job back to pending or to a dead-letter queue based on retry count.
5. Ensuring reclaim operations coordinate safely with active workers and ACKs.

Separate Hashes/ZSets can store deadlines or state, though updating multiple keys requires attention to **atomicity** and Redis Cluster hash slot constraints.

**You cannot use `LMOVE processing pending ...` to arbitrarily move a specific job ID from the middle of processing.** `LMOVE` always pops from the specified **end of the List**; reclaiming a specific job requires finding/removing by ID and re-enqueuing consistently, such as via a script designed for that workload.

### 9.5. Simple Java Worker Template

~~~java
import java.time.Duration;

import org.springframework.data.redis.connection.RedisListCommands.Direction;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisJobWorker {

    private static final String PENDING = "jobs:pending";
    private static final String PROCESSING = "jobs:processing";

    private final StringRedisTemplate redis;
    private final JobHandler handler;

    public RedisJobWorker(
            StringRedisTemplate redis,
            JobHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    public boolean processOne() {
        String jobId = redis.opsForList().move(
                PENDING, Direction.LEFT,
                PROCESSING, Direction.RIGHT,
                Duration.ofSeconds(5)
        );

        if (jobId == null) {
            return false; // Timed out with no job available.
        }

        try {
            handler.handle(jobId);

            Long removed = redis.opsForList()
                    .remove(PROCESSING, 1, jobId);

            if (!Long.valueOf(1L).equals(removed)) {
                // Log and investigate: already ACKed or reclaimed?
                throw new IllegalStateException(
                        "Job is no longer in processing: " + jobId
                );
            }

            return true;
        } catch (Exception failure) {
            // Do not blindly remove the job from processing.
            // A reclaimer or retry policy will handle it later.
            throw failure;
        }
    }

    public interface JobHandler {
        void handle(String jobId);
    }
}
~~~

This is an **illustrative skeleton** for claim–process–ack; it does not include a reclaimer, retry limits, idempotency, graceful shutdown, or database transaction coordination. `processOne()` is blocking, so invoke it from a managed worker thread rather than directly from an HTTP endpoint.

If `handler.handle(jobId)` commits data to the source of truth and the application crashes before `LREM`, the job remains in processing and may be retried. Handlers must be **idempotent** or use status markers/reconciliation against authoritative data, since redelivery can occur.

## 10. Exactly-Once or At-Least-Once?

Atomic element movement fixes **job loss between pop and push**. It does not guarantee exactly-once across the entire job lifecycle.

### 10.1. Case Where Duplicate Processing Can Occur

~~~text
Worker A receives job-101 via BLMOVE
Worker A writes to DB successfully
Worker A crashes before LREM ACK

Reclaimer sees job-101 unacknowledged
Reclaimer moves job-101 back to pending

Worker B receives job-101
Worker B runs processing again
~~~

If business logic is not idempotent (for example, charging a customer twice), the second run can cause severe bugs.

You need:

- Stable, unique job/event identifiers.
- Checking business state before applying side effects.
- Transactions/idempotency keys in the authoritative data store where needed.
- Retry, backoff, and dead-letter policies.
- Distinguishing **job claimed**, **job processed successfully**, and **job ACKed**.

Redis Lists with pending/processing can support **at-least-once** delivery when paired with a reclaimer; they do not automatically provide exactly-once.

### 10.2. Timeout After LMOVE/BLMOVE

If the server already moved `job-101` to processing and the connection drops before returning the response, the worker may receive a timeout/exception without knowing which ID was moved.

Immediately retrying `BLMOVE` may claim **a different job**. Therefore, never assume a timeout means "no job was moved." The system needs a way to inspect processing, identify worker claims, or recover unconfirmed jobs.

Designs requiring strict traceability usually need explicit lease/owner tracking beyond plain Lists.

## 11. When Are Redis Lists Enough, and When Should You Consider Redis Streams?

Moving between Lists fits small-to-medium queues, especially when simplicity is valued:

- Producers push IDs; workers claim via `BLMOVE`.
- Few consumers, with straightforward processing and retry policies.
- You can build and operate your own reclaimer/ACK logic as needed.
- No need to replay event history, manage complex consumer groups, or track per-group pending entries.

When requirements grow, **Redis Streams** are often worth evaluating:

| Requirement | List + LMOVE/BLMOVE | Redis Streams + Consumer Group |
|---|---|---|
| Claim element and wait when empty | Yes, via `BLMOVE` | Yes, via `XREADGROUP BLOCK` |
| Distribute work across multiple consumers | Possible | Possible, per consumer group |
| Track pending delivery/owner | Must design yourself | Pending Entries List per consumer group |
| ACK messages | Custom via `LREM` and metadata | `XACK` |
| Reclaim long-unacknowledged messages | Must design reclaimer yourself | `XCLAIM`/`XAUTOCLAIM` depending on version |
| Replay message history | List does not retain events after pop/ACK | Stream keeps entries until trimmed/deleted |
| Complexity | Simple initially | More concepts, clearer workflow support |
| Exactly-once processing | Not built-in | Not built-in for side effects outside Redis either |

**Streams do not automatically guarantee exactly-once** for operations in external databases or services. Consumers still require idempotency and proper ACK design.

If requirements call for delayed jobs, scheduled execution, attempt counters, multiple consumer groups, or auditability, evaluate dedicated queues/brokers as well. Choose the data model from business requirements, not merely because Redis Lists have fewer commands.

## 12. Interaction with Redis Cluster and Multiple Keys

`LMOVE`/`BLMOVE` is a command touching **two keys**. In Redis Cluster, two keys in the same multi-key command must live in the **same hash slot**.

Do not casually use:

~~~text
jobs:pending
jobs:processing
~~~

in Redis Cluster assuming they share a slot. If they map to different slots, you can hit:

~~~text
CROSSSLOT Keys in request don't hash to the same slot
~~~

### 12.1. Hash Tags for Source and Destination Lists

Use matching hash tags:

~~~text
jobs:{email}:pending
jobs:{email}:processing
~~~

Redis Cluster computes the slot from `email` inside the curly braces, placing both keys in the same slot:

~~~bash
redis-cli -c LMOVE \
  'jobs:{email}:pending' \
  'jobs:{email}:processing' \
  LEFT RIGHT
~~~

When a system has multiple independent queues, use distinct hash tags:

~~~text
jobs:{email}:pending
jobs:{email}:processing

jobs:{invoice}:pending
jobs:{invoice}:processing
~~~

That lets each pair land on different slots for better load distribution.

**Do not share one global hash tag across all queues**, such as `{all-jobs}`, unless you want to funnel all traffic onto a single slot. Also remember that one very hot queue remains a single-slot hotspot regardless of how many Redis Cluster primaries exist.

### 12.2. LMOVE Does Not Transfer Data Between Two Redis Deployments

If source and destination belong to two independent Redis servers outside the same Redis keyspace/command context, `LMOVE` cannot execute atomically across them. That requires a separate data-transfer pipeline with retries, confirmations, and error handling. Do not assume different key names can bridge separate Redis instances or Clusters.

## 13. Serialization of List Elements in Spring Data Redis

A Redis List stores **byte values** in order. `ListOperations` uses the template's serializers for members and keys.

With `StringRedisTemplate`:

~~~java
StringRedisTemplate redis = /* Spring-managed bean */;

redis.opsForList().rightPush("jobs:pending", "job-101");

String moved = redis.opsForList().move(
        "jobs:pending",
        Direction.LEFT,
        "jobs:processing",
        Direction.RIGHT
);
~~~

Keys and elements use string conventions, making them easy to inspect in Redis CLI. When `LMOVE` moves an element, Redis **does not deserialize and re-serialize the value**. It transfers the element's raw bytes between the two Lists on the server.

Consequences:

- Source and destination Lists should share a single **element-format contract**.
- If one template writes JSON objects to source while a consumer uses a String serializer on destination, the consumer may receive raw JSON strings or fail conversion depending on the API and serializer.
- If source holds JDK-serialized bytes, reading them as text in Redis CLI will be hard to interpret.
- Do not change serializers while old messages remain in queues without a compatibility migration plan.

### 13.1. Elements as IDs or Full Payloads?

Two common approaches:

**Store only IDs:**

~~~text
jobs:pending = [job-101, job-102, job-103]
~~~

Payloads reside elsewhere or in a Hash keyed by ID. Easy to ACK by ID, cheap on bandwidth, and avoids shuffling large payloads on every move.

**Store JSON payloads:**

~~~text
jobs:pending = [
  {"jobId":"job-101","type":"EMAIL","recipientId":"u-1"},
  {"jobId":"job-102","type":"REPORT","reportId":"r-7"}
]
~~~

Simple when jobs are small and self-contained, but requires managing JSON schemas, uniqueness, message size, and deployment compatibility. `LREM` matches **the element's value**; regenerating JSON with different bytes can cause ACK matching to fail.

In queues needing clear retry/reclaim behavior, a **stable ID** usually keeps the design simpler.

### 13.2. TTL Belongs to the List Key, Not Individual Elements

Example:

~~~bash
redis-cli EXPIRE jobs:pending 600
redis-cli TTL jobs:pending
~~~

TTL applies to the **entire List key**. Moving an element to `jobs:processing` does not carry an "element TTL" along with it, because Redis Lists do not have per-member TTLs under this model.

Do not set an overly short TTL on `processing` if in-flight jobs have not yet been acknowledged; when the List key expires, every remaining element disappears. Conversely, with neither TTL nor a reclaimer, `processing` can accumulate abandoned jobs forever.

If per-job deadlines are needed, store deadlines/metadata separately and pair them with an appropriate cleanup mechanism.

## 14. Atomicity Scope and Multi-Key Operation Boundaries

Properties to distinguish:

| Property | Provided by LMOVE/BLMOVE? | Explanation |
|---|---|---|
| Pop an element and push it to another List in one command | **Yes** | No gap between pop and push on the Redis server |
| Two consumers claiming the exact same source element | **No**; each command gets a distinct element | However, **two duplicate values** can exist if a producer pushed twice |
| Wait until source has data | `BLMOVE` yes; `LMOVE` no | Must configure an appropriate timeout |
| Confirm a job finished processing | **No** | Must ACK after the business handler succeeds |
| Pick and move an arbitrary job by ID | **No** | `LMOVE` only pops from one end of a List |
| Coordinate database transaction and ACK together | **No** | Requires dedicated consistency and idempotency design |
| Automatically recover jobs from dead workers | **No** | Requires reclaimer/lease/metadata |
| Survive failover without losing any single write | **No built-in guarantee** | Depends on Redis replication/persistence behavior |
| Move across different hash slots in Cluster | **No** | Keys must share a slot for multi-key commands |

This table helps prevent confusing **atomic transfer**, **reliable delivery**, and **exactly-once business execution**.

## 15. Common Pitfalls

### Pitfall 1 — Using LPOP Followed by RPUSH and Assuming It Is Safe

Those are two commands; a worker can crash between them. When the goal is atomic movement, use `LMOVE` or `BLMOVE`.

### Pitfall 2 — Choosing the Wrong Direction and Reversing FIFO Order

If a producer uses `RPUSH` (oldest → newest) and the consumer runs `LMOVE RIGHT LEFT`, it grabs the **newest** element first. For FIFO with `RPUSH`, pop from `LEFT`.

### Pitfall 3 — Treating null as an Error in Every Case

`LMOVE` can return nil when source is empty; `BLMOVE` returns nil on timeout. Spring typically returns null in those cases. Distinguish them from client timeout exceptions, network drops, or command errors.

### Pitfall 4 — Letting BLMOVE Wait Indefinitely Inside a Web Request

Unbounded blocking ties up threads and connections, stalling the application. Use a worker executor, finite timeouts, and proper shutdown handling.

### Pitfall 5 — Using a Processing List Without Ever Acknowledging

Completed jobs stay in `processing`, growing memory and causing a reclaimer to rerun them. ACK only upon success, and monitor unacknowledged job counts.

### Pitfall 6 — ACKing via LREM with Values That Can Duplicate

If the List contains two elements both equal to `"job-101"`, `LREM ... 1 job-101` cannot tell which attempt is being acknowledged. Use unique job IDs or a claim ID/lease model.

### Pitfall 7 — Assuming LMOVE Can Pick an Element from the Middle of a List

`LMOVE` only pops from LEFT or RIGHT. Reclaiming a specific job requires operating by ID with proper synchronization; do not blindly `LMOVE` the head of processing hoping it is the failed job.

### Pitfall 8 — Putting Source and Destination Lists in Different Hash Slots

In Redis Cluster, `LMOVE source destination ...` touches two keys, requiring the same slot. Use hash tags scoped to a **queue/partition pair**, not one global tag for the entire system.

### Pitfall 9 — Assuming Atomic Transfer Means Exactly-Once

A job can finish processing and crash before ACK. A reclaimer returning it to pending will trigger reprocessing. Design idempotent handlers and reconcile against authoritative data.

### Pitfall 10 — Using Different Serializers on Source and Destination

Redis transfers raw element bytes verbatim without converting JSON to Java objects or changing encodings. Consumers must understand the same format.

### Pitfall 11 — Letting a Processing List Grow Unbounded

`LREM` slows down as the List grows; monitor `LLEN processing`, bound workload size, and consider partitioning or Redis Streams when ACK/claim demands grow complex.

### Pitfall 12 — Closing Sockets or Blindly Retrying on Timeout

If Redis already executed the command but the response was lost, retrying can claim a second job. Never assume timeout means the command never ran; build explicit recovery handling.

## 16. Observing and Operating with Redis CLI

Inspect the Lists:

~~~bash
redis-cli TYPE jobs:pending
redis-cli TYPE jobs:processing

redis-cli LLEN jobs:pending
redis-cli LLEN jobs:processing

redis-cli LRANGE jobs:pending 0 9
redis-cli LRANGE jobs:processing 0 9
~~~

`LRANGE 0 9` reads only up to the first 10 elements, which is handy for inspection. Avoid `LRANGE key 0 -1` on potentially huge Lists in routine checks.

Inspect TTL and memory:

~~~bash
redis-cli TTL jobs:pending
redis-cli TTL jobs:processing

redis-cli MEMORY USAGE jobs:pending
redis-cli MEMORY USAGE jobs:processing

redis-cli INFO memory
redis-cli INFO stats
~~~

Meaning:

- `LLEN`: current element count.
- `TYPE`: confirm the key is a List before running List operations.
- `TTL = -1`: key exists with no expiration; `TTL = -2`: key does not exist.
- `MEMORY USAGE`: estimated RAM used by Redis for the key/value.
- `INFO`: Redis resource state and statistics.

Application-side metrics to monitor:

| Metric | Meaning |
|---|---|
| `pending_length` | Whether waiting work is growing or draining |
| `processing_length` | Jobs claimed but not yet ACKed |
| `BLMOVE` wait time | Whether the queue is starved or workers frequently block |
| Processing latency p50/p95/p99 | Whether slow jobs are causing backlogs |
| ACK success/failure counts | Whether the completion flow is healthy |
| Reclaimed/retried job counts | How often workers crash or time out |
| Duplicate business event counts | Whether handlers are genuinely idempotent |
| Redis command timeouts/connection errors | Risk of claims succeeding unknown to the client |
| Redis memory/evicted keys | Risk of losing queues or payloads under resource pressure |

Do not monitor only `pending`. A queue with `pending = 0` yet steadily rising `processing` is not necessarily healthy; jobs may be stuck after being claimed.

## 17. Practice Exercises

### Exercise 1 — FIFO with RPUSH

Given:

~~~text
source      = [job-A, job-B, job-C]
destination = []
~~~

The producer used `RPUSH` to append A, B, C in order. Which command picks A first and appends it to the end of destination?

**Answer:**

~~~text
LMOVE source destination LEFT RIGHT
~~~

After the command:

~~~text
source      = [job-B, job-C]
destination = [job-A]
~~~

### Exercise 2 — Understanding the Direction of RPOPLPUSH

Given:

~~~text
source      = [A, B, C]
destination = [X, Y]
~~~

The command:

~~~text
RPOPLPUSH source destination
~~~

is equivalent to:

~~~text
LMOVE source destination RIGHT LEFT
~~~

Result:

~~~text
source      = [A, B]
destination = [C, X, Y]
Returned value = C
~~~

### Exercise 3 — Blocking Timeout

A worker calls:

~~~text
BLMOVE jobs:pending jobs:processing LEFT RIGHT 5
~~~

and no producer pushes a job within 5 seconds.

**Result:** Redis returns nil on timeout; in a direct Spring Data Redis call, you normally receive null. If the application receives a client-side timeout exception after 2 seconds, that is a client timeout configuration issue distinct from a valid nil return.

### Exercise 4 — Worker Crashes After Claim

A worker claims `job-42` via `LMOVE`, writes to the database successfully, and then crashes before calling `LREM`.

**What can happen:** `job-42` stays in processing; a reclaimer may return the job to pending; another worker runs the same job again. Ensure database updates or side effects are idempotent.

### Exercise 5 — Redis Cluster Reports CROSSSLOT

Two keys:

~~~text
queue:pending
queue:processing
~~~

hash to two different slots. `LMOVE` cannot run across two slots.

**Example adjustment:**

~~~text
queue:{orders}:pending
queue:{orders}:processing
~~~

Sharing a hash tag puts both keys in the same slot. For independent queues, pick distinct tags to distribute load.

### Exercise 6 — Choosing a Structure for a Multi-Worker Queue

Requirements: thousands of jobs/sec, many consumers, knowing which worker owns each job, reclaiming past-deadline jobs, message history, multi-attempt retries, and dead-lettering.

**Decision direction:** `LMOVE`/`BLMOVE` can handle the claim step, but a simple processing List lacks all that metadata. Either build significant supporting structures or consider Redis Streams consumer groups or a dedicated broker.

## 18. Decision Flow for List Move Operations

~~~text
                  Need to move elements between two Lists
                                  |
                    Which order should items be popped?
                        /                  \
               Pop first element        Pop last element
                    LEFT                    RIGHT
                        \                    /
                         +--------+---------+
                                  |
                     Push to head or tail of dest?
                           LEFT / RIGHT
                                  |
                    Need to wait when source is empty?
                          /            \
                        Yes             No
                         |              |
                       BLMOVE         LMOVE
                         \              /
                          +------------+
                                  |
                     Using Redis Cluster?
                          /            \
                        Yes             No
                         |
                  Same slot for source/dest
                         |
                     Claiming job to process?
                          /            \
                        Yes             No
                         |              |
               Processing + ACK       Done
               + Retry/Reclaimer
                         |
               Idempotency + monitoring
~~~

Key points to remember:

- **`LMOVE source destination from to`**: immediately moves one element in a single atomic command, returning nil if source is empty.
- **`BLMOVE source destination from to timeout`**: same, except it waits when source is empty.
- **`ListOperations.move(...)`**: Spring Data Redis API explicitly expressing both directions and providing a blocking variant using `Duration`.
- **`rightPopAndLeftPush(...)`**: legacy API helpful when reading legacy codebases, corresponding to `RIGHT → LEFT`.
- **`pending → processing`**: closes the gap between pop and push, yet still requires ACK, idempotency, and recovery to form a reliable job-processing workflow.

Moving elements between two Lists is a small Redis operation with major implications for queue design. Choose the right LEFT/RIGHT directions, use atomic moves, account for worker wait times, and add acknowledgement/recovery mechanisms whenever jobs genuinely require reliable processing.
