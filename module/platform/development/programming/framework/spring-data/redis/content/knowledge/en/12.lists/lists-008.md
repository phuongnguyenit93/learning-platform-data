# Choosing Between Lists and Streams Based on Job-Processing Requirements

When building an asynchronous job-processing system with **Spring Data Redis**, you typically need a **queue**: an API or producer creates jobs, while one or more workers claim and process them later. Redis offers at least two data structures commonly considered for this role:

- **Redis List:** an ordered list suitable for simple queues using commands such as `LPUSH`, `RPOP`, `BLPOP`, `BRPOP`, or `BLMOVE`.
- **Redis Streams:** a log of ID-bearing records supporting positional reads, **consumer groups**, **pending entries**, and **acknowledgements (ACK)** through commands such as `XADD`, `XREADGROUP`, `XACK`, `XPENDING`, and `XAUTOCLAIM`.

Both structures can transfer a job from a producer to a consumer, yet **they differ in how jobs are retained, whether completion is acknowledged, how failures recover when a worker crashes, and how multiple consumers coordinate**.

> Key idea: **Lists** suit simple queues when losing a job is acceptable or when you design your own recovery. **Streams + consumer groups** fit better when you need tracking of delivered-but-unacknowledged jobs, retries, and backlog visibility. Still, Streams do not automatically provide *exactly-once* guarantees or replace idempotency design.

## 1. Start from Job Requirements, Not Command Names

Suppose an ordering system has an API receiving invoice generation requests. Processing can take several seconds, so the API pushes a job into Redis and returns a response while a worker handles it asynchronously:

~~~text
      POST /orders/42/invoice
                  |
                  v
           Invoice API
                  |
             enqueue job
                  v
              Redis
                  |
                  v
            Invoice Worker
                  |
        generate invoice, send email...
                  |
                  v
                done
~~~

Before choosing List or Streams, answer:

1. If a worker **claims a job and crashes** before finishing, must the job be retried?
2. If a job runs **twice**, is the business effect still safe?
3. Should multiple workers **split** the work, or must multiple systems **each receive** every event?
4. Do you need visibility into which jobs are **waiting**, **delivered** but unacknowledged, or **failing repeatedly**?
5. How long must jobs be retained? Are there data limits and cleanup policies?
6. Must an event log be kept so later consumers can replay past records?
7. Does processing depend strictly on execution order?
8. Is Redis just a **lightweight helper queue**, or a critical component requiring explicit recovery, observability, and coordination?

The two approaches yield different answers to these questions, even though both run on the same Redis Server and are accessible through Spring Data Redis.

## 2. Quick Comparison Table: Redis List vs. Redis Streams

| Criterion | Redis List | Redis Streams |
|---|---|---|
| Structure | Ordered sequence of elements | Sequence of records with **IDs** and fields |
| Enqueue job | `LPUSH` / `RPUSH` | `XADD` |
| Read job | `LPOP` / `RPOP` or blocking variants | `XREAD` or `XREADGROUP` |
| When a consumer takes a job simply | Pop **removes the element from the List** | Read **does not automatically delete the record from the Stream** |
| Wait for data | `BLPOP` / `BRPOP` / `BLMOVE` | `XREAD BLOCK` / `XREADGROUP BLOCK` |
| Built-in consumer groups | No | Yes, via `XGROUP` and `XREADGROUP` |
| Track delivered but un-ACKed | Not built-in with direct pop | Has **Pending Entries List (PEL)** per consumer group |
| ACK processed job | No native ACK command for a simple pop | `XACK` |
| Reclaim jobs from failed consumers | Must design yourself (e.g., processing List + timeout) | `XCLAIM` / `XAUTOCLAIM`, paired with a retry policy |
| Multiple consumers sharing load | Competing pops on the same List | Consumers in the same group split new records |
| Multiple groups receiving the same event | Must duplicate data or build custom fan-out | Each consumer group tracks its own position and state |
| Re-read old data | No, once popped from the List | Yes, while retained; requires proper offset/group handling |
| Application complexity | Low for minimal queues | Higher: groups, IDs, ACKs, pending, retries, retention |
| Metadata overhead | Simple queue structure | Additional IDs, group state, and pending/consumer tracking |
| Best suited for | Short, simple jobs; tolerable loss or custom recovery | Jobs needing ACKs, retries, pending tracking, multiple consumers/groups |

**Lists are not "unusable for reliable queues"**: you can add a processing list and acknowledgement logic. However, Redis **Streams provide much of that management out of the box at the protocol level**, so when recovery demands grow, rebuilding it on Lists quickly becomes laborious and harder to operate.

## 3. Redis List: Understanding a Simple Queue

A Redis List stores elements in order from **left (head)** to **right (tail)**. Commands:

~~~text
LPUSH key value   -> add to the left
RPUSH key value   -> add to the right
LPOP  key         -> pop and delete from the left
RPOP  key         -> pop and delete from the right
BLPOP key timeout -> wait for an element on the left if List is empty
BRPOP key timeout -> wait for an element on the right if List is empty
~~~

To build a **FIFO (first in, first out)** queue, pair:

- **LPUSH + RPOP/BRPOP**: producer pushes on the left, consumer pops from the right.
- Or **RPUSH + LPOP/BLPOP**: producer pushes on the right, consumer pops from the left.

### 3.1. Illustrating LPUSH + BRPOP

Suppose the List starts empty:

~~~text
LPUSH jobs:ready job-1
LPUSH jobs:ready job-2
LPUSH jobs:ready job-3

Left (head)                  Right (tail)
  [job-3]  [job-2]  [job-1]

BRPOP jobs:ready 5  -> receives job-1

Remaining list:
  [job-3]  [job-2]
~~~

The job is popped off the List, meaning **Redis no longer holds that element in the source List**. This is both an advantage for simple queues (no ACK needed to clear source entries) and a risk when a worker crashes.

### 3.2. Trying It with redis-cli

On a lab Redis instance:

~~~bash
DEL demo:jobs:ready
LPUSH demo:jobs:ready job-1
LPUSH demo:jobs:ready job-2
LRANGE demo:jobs:ready 0 -1
BRPOP demo:jobs:ready 5
BRPOP demo:jobs:ready 5
BRPOP demo:jobs:ready 5
~~~

The first two BRPOP calls receive the two jobs. The third waits up to five seconds on the empty List and then returns an empty result.

**BRPOP's timeout** is how long to wait for an item, not how long "Redis keeps the job after the worker takes it." In synchronous APIs, blocking calls hold a Java worker thread and an active connection. Run consumers in bounded background workers rather than blocking on BRPOP directly inside HTTP request paths without good reason.

## 4. Key Risk of Lists: Pop First, Process Later

Consider a straightforward consumer:

~~~text
T0: Redis List contains job-42
T1: Worker A calls BRPOP -> Redis removes job-42 from the List
T2: Worker A calls the invoice generation API
T3: Worker A crashes before saving the invoice
~~~

At **T3**, the job is gone from the source List. Unless another system tracks job state or requeues it, no record remains for another consumer to pick up.

~~~text
 Redis List       Worker A            Database
     |               |                   |
     | -- job-42 ---> |                  |
     | (popped, lost from list)          |
     |               X crash             |
     |               |                   |
     |        no native ACK/retry        |
~~~

This is the boundary of **destructive pop**. It works well for jobs that:

- Can be regenerated from another data source.
- Are low-impact if an isolated job is dropped.
- Have reconciliation/repair jobs outside Redis.
- Run quickly and prioritize operational simplicity.

It is unsuitable if failure means **permanently losing a mandatory business action** that the system cannot recover.

### 4.1. Do Multiple Consumers Popping Concurrently Process Duplicates?

If two consumers call `BRPOP` on the same List, a popped element is **delivered to only one successful pop call** in Redis at that moment. This enables load sharing across multiple workers.

However:

- Redis does not guarantee the worker completes after popping.
- If a producer pushes **two entries with the same jobId**, two consumers can run the same business action twice.
- If external retry logic exists, a job may be re-enqueued and run again.

Thus, even the List pattern requires **idempotency** for sensitive operations.

## 5. Making Lists More Reliable: Ready List and Processing List

To avoid losing a job immediately upon dequeue, you can use **two Lists**:

~~~text
jobs:ready                  jobs:processing
    |                              ^
    |                              |
    +-- BLMOVE RIGHT LEFT ---------+
              (atomic move)
                        |
                      Worker
                        |
                   succeeded?
                  /          \
                Yes          No/crash
                 |              |
       LREM from processing   Job stays in
                            processing list
~~~

Redis provides `LMOVE`/`BLMOVE` to **atomically move an element from a source List to a destination List**. `BLMOVE` waits if the source List is empty.

Example:

~~~bash
LPUSH jobs:ready job-42
BLMOVE jobs:ready jobs:processing RIGHT LEFT 5
~~~

After the command, the job is removed from `jobs:ready` yet retained in `jobs:processing` before the worker runs. Upon success:

~~~bash
LREM jobs:processing 1 job-42
~~~

Here, `LREM` serves as an **application-defined completion acknowledgement**. It is not a native consumer-stateful ACK like Redis Streams.

### 5.1. Why Does This Approach Still Require Building a Lot Yourself?

A processing List only preserves the element after transfer:

1. **Who owns the job?** If multiple workers share one processing list, you must track which worker holds which job.
2. **How long has the job been stuck?** You must store delivery timestamps or lease deadlines, not just the payload.
3. **When should it retry?** A process scanning the processing list or an index must detect overdue jobs.
4. **How do you prevent concurrent retry while the original worker is still running?** You need ownership state, leases/fencing, or idempotency.
5. **How do you stop `LREM` from removing the wrong element?** Use unique job IDs or uniquely identifiable envelopes.
6. **Can requeuing alter order?** Yes, and this must be accepted or handled.
7. **What if the job succeeds but crashes before acknowledgement?** The job gets retried and may run twice.

Redis Streams handle much of this via **consumer groups, delivery counts, PEL, ACK, and claim**, making them worth considering once requirements reach this point.

**Do not use BRPOPLPUSH in new designs merely because old tutorials show it:** on modern Redis, `LMOVE`/`BLMOVE` are the commands to evaluate first. Still verify compatibility with your Redis Server and driver versions.

## 6. Redis Streams: ID-Bearing Records Instead of Immediate-Pop Elements

A Redis Stream is an **append-only log ordered by ID**. Producers append records with `XADD`. Each record has:

- **Stream key:** the stream's name, e.g., `jobs:invoice:stream`.
- **Record ID:** record identifier, typically shown as `milliseconds-sequence`.
- **Fields and values:** job payload, e.g., `jobId`, `type`, `orderId`.

Example:

~~~bash
XADD jobs:invoice:stream * jobId job-42 type CREATE_INVOICE orderId 42
XADD jobs:invoice:stream * jobId job-43 type CREATE_INVOICE orderId 43
~~~

Redis returns IDs like:

~~~text
"1762965000000-0"
"1762965000001-0"
~~~

These are **illustrative IDs**, not IDs to hardcode. Passing `*` instructs Redis to generate IDs following Stream rules.

Unlike Redis List pops:

~~~text
List:
  BRPOP -> element leaves source List

Streams:
  XREAD / XREADGROUP -> record is read/delivered
                        yet can remain in Stream
  XACK -> acknowledges group processing,
          does NOT delete the record from Stream
~~~

Retaining record IDs and data makes Streams fit a wider range of job-management requirements.

### 6.1. A Stream Is Not an "Infinite Retention" Queue

Entries remain until deleted/trimmed or until the key is deleted/evicted per configuration. Moreover, survival across restarts/failovers depends on **Redis persistence (RDB/AOF)**, replication, and operations.

Streams **do not automatically guarantee zero data loss in every failure**. When very high durability is required, design and evaluate the entire write path, persistence, retention, failover, producer retries, and authoritative storage.

## 7. Two Ways to Read Streams: XREAD and XREADGROUP

### 7.1. XREAD: Positional Reading Without Requiring a Group

Example:

~~~bash
XREAD COUNT 10 STREAMS jobs:invoice:stream 0-0
~~~

The client reads records with IDs greater than the passed offset. To resume later, **the client must track the last seen ID** under this read mode. Losing that offset and picking the wrong starting point can skip or re-read records.

With `XREAD BLOCK`, clients can wait for new records when none match yet.

**XREAD does not create consumer groups or a PEL.** If three independent consumers read the stream from the same offset, all three receive the same records. Therefore, do not use XREAD assuming Redis will distribute each job to a single consumer.

### 7.2. XREADGROUP: Distributing Work Within a Consumer Group

A consumer group tracks:

- Group name.
- Position for delivering new records (last-delivered ID).
- Consumers belonging to the group.
- **Pending Entries List (PEL)** tracking delivered-but-unacknowledged records.

Example of a group named `invoice-workers` with two consumers:

~~~text
                        jobs:invoice:stream
                        [ID-1][ID-2][ID-3][ID-4]
                                 |
                                 v
                   Consumer group: invoice-workers
                          /             \
                         /               \
                  consumer-a          consumer-b
                  ID-1, ID-3          ID-2, ID-4
                         \               /
                          \             /
                        Pending entries
                        until XACKed
~~~

This diagram illustrates **work distribution**; it does not guarantee strict round-robin balancing or equal consumer speeds. Which consumer polls and is ready influences delivery.

All consumers in **the same group** cooperate to split work. If **another group** exists, such as `analytics-workers`, that group keeps its own read cursor and can independently receive the same Stream records.

## 8. Creating a Consumer Group and Receiving Jobs

Suppose we want **each invoice job delivered to one consumer in the group**.

### 8.1. Creating the Group

~~~bash
XGROUP CREATE jobs:invoice:stream invoice-workers 0 MKSTREAM
~~~

Explanation:

- `jobs:invoice:stream`: Stream name.
- `invoice-workers`: consumer group name.
- `0`: group starts from the beginning of the Stream (reads existing backlog if records remain).
- `MKSTREAM`: creates an empty Stream if it does not yet exist.

If `$` is chosen when creating the group, the group starts after existing records at creation time, meaning normal reads see only records added afterward. **Choosing `0` vs. `$` must follow backlog requirements**, never guesswork.

Create the group only once. Running `XGROUP CREATE` again for an existing group returns an error such as `BUSYGROUP`. In multi-instance deployments, make group initialization **idempotent with proper error handling**, rather than letting every worker race to create the group without handling already-exists errors.

### 8.2. Writing Records

~~~bash
XADD jobs:invoice:stream * jobId job-42 orderId 42
XADD jobs:invoice:stream * jobId job-43 orderId 43
~~~

### 8.3. Consumer Reading Undelivered Records

~~~bash
XREADGROUP GROUP invoice-workers consumer-a COUNT 10 BLOCK 5000 STREAMS jobs:invoice:stream >
~~~

Components:

| Component | Meaning |
|---|---|
| `GROUP invoice-workers consumer-a` | Read as consumer-a within the group |
| `COUNT 10` | Read up to a maximum number of records per call |
| `BLOCK 5000` | Wait up to 5000 ms if no new matching record is available |
| `STREAMS jobs:invoice:stream >` | Read records **never yet delivered** to any consumer in the group |

When records exist, Redis delivers them to the consumer and places them in the group's **PEL**, attributed to that consumer.

**When no records arrive, hitting the BLOCK timeout is normal**, not a Redis Server error. The consumer can loop again or check shutdown requests.

### 8.4. Acknowledging After Processing

Suppose a record has ID `1762965000000-0` and the worker finishes processing it:

~~~bash
XACK jobs:invoice:stream invoice-workers 1762965000000-0
~~~

`XACK` clears the pending state of that ID **in that group**. It **does not** delete the record from the Stream and **does not** acknowledge on behalf of other groups.

Removing records from the Stream is a separate concern, handled via `XDEL` or retention with `XTRIM`/`XADD ... MAXLEN`, coordinated with replay needs, pending entries, and retention windows.

## 9. PEL: Pending Entries List Shows Which Jobs Are Un-ACKed

This is the standout difference from popping directly off a List.

When a worker receives a record via `XREADGROUP`, Redis records the **pending** state:

~~~text
Stream:
  ID-1 -> job-42
  ID-2 -> job-43

Group: invoice-workers

PEL:
  ID-1 -> consumer-a (delivered, not yet ACKed)
  ID-2 -> consumer-b (delivered, not yet ACKed)
~~~

If consumer-a finishes and sends:

~~~text
XACK jobs:invoice:stream invoice-workers ID-1
~~~

then ID-1's pending entry in the group is cleared. ID-2 stays pending until consumer-b ACKs, or until the system executes retry/claim/group maintenance workflows.

### 9.1. Inspecting the PEL with XPENDING

~~~bash
XPENDING jobs:invoice:stream invoice-workers
~~~

This returns a summary of pending record counts and distribution across consumers. You can inspect details by ID range/count and consumer when investigating.

Example:

~~~bash
XPENDING jobs:invoice:stream invoice-workers - + 10
~~~

Detailed entries can include **record ID**, **consumer**, **idle time**, and **delivery count**. These help spot seemingly stuck jobs, though long idle time **does not by itself prove the job failed**: the worker might be executing a long-running task. Timeout/lease policies should reflect real processing durations.

### 9.2. XACK Is Not "Marking Success in the Database"

XACK updates only **consumer group state inside Redis**. It does not write to your business database, confirm email delivery, or commit a cross-system transaction.

Code must send ACK **after the job meets completion criteria**; ACKing beforehand and then failing causes Redis to consider the record resolved even though the work never completed.

## 10. Worker Crashes: Why Must Pending Entries Be Handled?

Consider a scenario:

~~~text
T0  XADD job-42
T1  consumer-a XREADGROUP -> receives job-42, added to PEL
T2  consumer-a begins generating invoice
T3  consumer-a crashes before XACK
T4  consumer-b is still running
~~~

Key facts:

- The job **does not vanish** from the Stream merely because it was read.
- The group still tracks the pending state of the delivered record.
- However, **consumer-b will not automatically receive that record by continuously reading `>`**. The `>` symbol requests *new, never-delivered* records for the group; job-42 was already delivered and sits in pending.

Therefore, alongside the new-record read loop, a Streams worker system needs a **pending recovery loop**.

### 10.1. Reading a Consumer's Own Pending Entries

A consumer can re-read its own pending records using an explicit offset, such as:

~~~bash
XREADGROUP GROUP invoice-workers consumer-a COUNT 10 STREAMS jobs:invoice:stream 0
~~~

This differs from `>`. With an ID other than `>`, group reads target pending entries already assigned to the calling consumer within the requested ID range. This lets a restarted process recover its own work when reusing the same consumer name, yet **does not reclaim pending entries from other consumers**.

### 10.2. Reclaiming Pending Entries from Dead Consumers

Redis provides `XCLAIM` and `XAUTOCLAIM`. Example:

~~~bash
XAUTOCLAIM jobs:invoice:stream invoice-workers consumer-b 30000 0-0 COUNT 10
~~~

Explanation:

- Targets group `invoice-workers`.
- Transfers ownership to `consumer-b` for pending entries meeting the minimum idle threshold.
- `30000` is the minimum idle time of **30,000 milliseconds**.
- `0-0` is the starting scan cursor.
- `COUNT 10` caps how many entries to evaluate per pass.

`XAUTOCLAIM` returns the next cursor and claimed entries; recovery logic must iterate the cursor across passes when backlogs are large. Verify Redis Server support for this command (Redis 6.2+).

**Claiming does not process or ACK the job.** Consumer-b must:

1. Inspect the payload, delivery count, and retry policy.
2. Safely reprocess the job.
3. Send `XACK` upon completion per business rules.
4. Route unrecoverable errors to a **dead-letter** mechanism or failure store per design.

### 10.3. Why Is Idle Time Alone Not Enough?

If worker-a is running a very long task and worker-b claims the record solely because it has been idle over 30 seconds, **both workers can execute the same job concurrently**. Choose appropriate min-idle thresholds, consider heartbeats/leases, and enforce idempotency or fencing whenever side effects reach external systems.

Redis Streams support **detecting and reclaiming pending entries**, yet cannot know on their own whether an external side effect already completed.

## 11. At-Most-Once, At-Least-Once, and Exactly-Once

Delivery terms cause confusion unless you distinguish **message receipt**, **business processing**, and **state persistence**.

### 11.1. Direct List Pop: Job Loss Can Occur

If a worker pops from a List and crashes, the job can be lost from the queue. This approach **has no native post-pop retry** and risks dropping work. Such configurations often exhibit *at-most-once* delivery at the pop step due to destructive pop, though duplicates can still arise from producer retries, upstream retries, or duplicate payloads.

### 11.2. Streams + Process Then ACK: Toward At-Least-Once

Typical flow:

~~~text
XREADGROUP -> receive job
    |
    v
Business processing
    |
    v
Commit result successfully
    |
    v
XACK
~~~

If the worker crashes **before XACK**, the record stays pending and can be retried. This forms the basis for **at-least-once** delivery when retention, pending recovery, and retries are implemented properly.

However, if business logic **already succeeded** and the worker crashes **before XACK**, the job will run again:

~~~text
T0: consumer-a receives job-42
T1: invoice created successfully in database
T2: consumer-a crashes before XACK
T3: consumer-b claims job-42 and reprocesses it
~~~

**Reprocessing must not mean creating two invoices.** The application needs idempotency so the same job ID never triggers business side effects twice.

### 11.3. Do Streams Guarantee Exactly-Once?

**Not automatically.** Redis Streams cannot atomically span:

- Writing to an external database,
- Calling a payment gateway,
- Sending an email,
- And sending `XACK` to Redis,

merely by using consumer groups. Operations across separate systems do not form a distributed transaction automatically.

A practical approach:

- Attach a unique **jobId/idempotency key** to each business request.
- In the result store, record processed state with a **unique constraint** or atomic check.
- If a job was already processed, the retrying consumer skips side effects and ACKs the record.
- For external side effects lacking idempotency support, design explicit reconciliation.

For example, job `invoice-job-42` allows creating only one invoice keyed by a unique business constraint. On retry, the database write sees the invoice already exists and avoids creating a second copy.

**Summary:** Streams make *at-least-once* processing far easier than direct List pops, whereas **exactly-once effects** remain a system-level problem requiring idempotency, transactions, outboxes, and well-defined business boundaries.

## 12. Consumer Groups: Sharing Load and Delivering Events to Multiple Groups

Given one Stream:

~~~text
              jobs:invoice:stream
                  [1][2][3][4]
                       |
             +---------+---------+
             |                   |
       Group: billing      Group: analytics
             |                   |
       +-----+-----+          +--+--+
       |           |          |     |
    worker-a    worker-b    worker-c worker-d
~~~

Two patterns to distinguish:

**Within one group:** consumers cooperate to split new records. Each record is delivered to one consumer in the group initially; it can be claimed/retried if unacknowledged.

**Across two groups:** each group keeps its own cursor and state. The same record retained in the Stream can be processed by both the billing group and the analytics group, provided groups are initialized/read to include it.

This helps when an `order-created` event must trigger **multiple independent systems**, each requiring its own checkpoints and ACKs. With a simple Redis List, one pop removes the element from the source queue; delivering the same job to two systems requires duplicating queues or custom plumbing.

### 12.1. Do Not Confuse Consumer Name with Group Name

- **Group name** identifies a logical processing pipeline/group, such as `invoice-workers`.
- **Consumer name** identifies a specific consumer within that group, such as `invoice-worker-instance-07`.

If multiple processes concurrently share the **same consumer name** carelessly, tracking pending ownership and recovery gets messy. Typically, assign stable per-instance/per-worker consumer names during runtime, paired with a cleanup strategy for retired consumers and their pending entries.

### 12.2. Delivery Order Does Not Equal Completion Order

Streams order records by ID, yet two workers take different amounts of time:

~~~text
Record 100-0 -> worker-a, takes 20 seconds
Record 101-0 -> worker-b, takes 1 second

worker-b finishes before worker-a.
~~~

Therefore, **a multi-worker consumer group does not guarantee completion in Stream ID order**. If business rules require per-order sequencing, design partition/key routing, limit concurrency per aggregate, or enforce ordering at the processing layer.

## 13. Data Retention and Trimming in Streams

Redis Streams **do not automatically delete records upon XACK**. That helps when bounded replay or auditing is desired, yet causes memory to grow unless capped:

~~~text
XADD every second -> Stream grows
XREADGROUP -> delivers record
XACK -> clears pending in group
     -> record stays in Stream
~~~

Relevant commands:

~~~bash
XLEN jobs:invoice:stream
XINFO STREAM jobs:invoice:stream
XINFO GROUPS jobs:invoice:stream
XPENDING jobs:invoice:stream invoice-workers
~~~

### 13.1. Bounding Stream Length

Example appending a record with an approximate cap:

~~~bash
XADD jobs:invoice:stream MAXLEN ~ 100000 * jobId job-44 orderId 44
~~~

`MAXLEN ~ 100000` instructs Redis to perform **approximate trimming** to keep length controlled. The exact retained count is not strictly 100,000 records; approximate trimming can be more efficient depending on workload.

You can also trim explicitly:

~~~bash
XTRIM jobs:invoice:stream MAXLEN ~ 100000
~~~

**Important:** never trim blindly by count if consumers or groups still need older records. Depending on Redis version and options, trimming/deleting records can leave pending IDs referenced without their payloads, or cause lagging groups to miss trimmed entries. Base retention on:

1. Which groups still need to read records?
2. Which records remain pending and unfinished?
3. How long at most can a consumer stay offline?
4. Should unrecoverable/archived items be stored in a DLQ or durable store?
5. How long must ACKed logs remain for audit or replay?

A proper retention strategy often requires more thought than a fixed `MAXLEN`.

### 13.2. A Redis Stream Can Also Become a Big Key

A Stream holding tens of millions of records is still **one Redis key**. In Redis Cluster, a key lives in one hash slot; read/write load for that key concentrates on the primary node owning that slot.

At very high throughput, you may need to shard across multiple streams by domain, tenant, shard, or time, such as:

~~~text
jobs:invoice:shard:0
jobs:invoice:shard:1
jobs:invoice:shard:2
jobs:invoice:shard:3
~~~

However, sharding multiplies groups/consumers, routing logic, and monitoring, and breaks global ordering. Partition only when justified by clear metrics, not prematurely.

## 14. Spring Data Redis Example with Redis List

### 14.1. Minimal Configuration

In Spring Boot 3.x with Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Example `application.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 5s
~~~

This configuration illustrates Redis Server running on the local development machine. Redis Server must be started separately. Under Docker Compose, `host` is normally the Redis service name rather than `localhost` inside the Spring Boot container.

### 14.2. Producer and Consumer for a Simple Queue

~~~java
package com.example.redisjobs;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SimpleListJobQueue {

    private static final String QUEUE = "jobs:invoice:list";

    private final StringRedisTemplate redis;

    public SimpleListJobQueue(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void enqueue(String jobId) {
        // LPUSH at the head of the List.
        redis.opsForList().leftPush(QUEUE, jobId);
    }

    public String receiveOnce() {
        // BRPOP at the tail of the List, waiting up to 5 seconds.
        return redis.opsForList().rightPop(
                QUEUE,
                Duration.ofSeconds(5)
        );
    }
}
~~~

Meaning:

- `enqueue("job-42")` pushes an ID onto the queue.
- `receiveOnce()` waits up to five seconds and returns the job ID if available.
- If the queue stays empty through the timeout, the result is normally `null`.
- Once the job ID is returned, the element has already been **popped off the List**, with no native ACK step.

**Run `receiveOnce()` in a background worker**, never on a reactive event loop or unboundedly inside HTTP request threads. Each blocking call holds the calling thread while waiting and may use a dedicated connection depending on driver/factory configuration.

### 14.3. Single-Invocation Consumer

~~~java
public void processOneListJob(
        SimpleListJobQueue queue,
        InvoiceProcessor processor) {

    String jobId = queue.receiveOnce();
    if (jobId == null) {
        // No job within 5 seconds; this is not an error.
        return;
    }

    processor.process(jobId);
}
~~~

`InvoiceProcessor` here is a business abstraction, e.g., a component exposing `void process(String jobId)`. This example **adds no automatic retries**. If `processor.process(jobId)` throws an exception after popping, the application must handle it explicitly; the Redis List does not automatically return the job to the queue.

## 15. Spring Data Redis Example with Streams

Streams introduce a few extra concepts: records, groups, consumer identity, offsets, and ACKs.

### 15.1. Initializing the Group in a Test Environment

So the Java code below can focus on producer/consumer logic, create the group first via redis-cli:

~~~bash
XGROUP CREATE jobs:invoice:stream invoice-workers 0 MKSTREAM
~~~

This command runs only once per group. In production apps, group initialization should be organized as an idempotent provisioning/migration step that handles existing-group errors cleanly.

### 15.2. Producer Appending Records with StreamOperations

~~~java
package com.example.redisjobs;

import java.util.Map;

import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoiceStreamProducer {

    private static final String STREAM = "jobs:invoice:stream";

    private final StringRedisTemplate redis;

    public InvoiceStreamProducer(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId enqueue(String jobId, String orderId) {
        return redis.opsForStream().add(
                StreamRecords.string(Map.of(
                        "jobId", jobId,
                        "orderId", orderId,
                        "type", "CREATE_INVOICE"
                )).withStreamKey(STREAM)
        );
    }
}
~~~

`StreamRecords.string(...).withStreamKey(...)` builds a record with string fields/values targeting the specified Stream. `opsForStream().add(...)` sends the equivalent of `XADD` and returns a `RecordId` on success in normal synchronous calls.

**A Stream `RecordId` and a business `jobId` are two distinct identifiers:**

- `RecordId` (e.g., `1762965000000-0`) identifies the entry in the Redis Stream, used for ACK/pending.
- `jobId` (e.g., `invoice-job-42`) identifies the business job, used for idempotency and reconciliation.

If a producer retries after a Redis request times out even though `XADD` actually succeeded, **the same jobId can appear under two different RecordIds**. Use a business-level idempotency key rather than trusting RecordId to prevent duplicates.

### 15.3. Consumer Reading New Records and ACKing After Processing

~~~java
package com.example.redisjobs;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoiceStreamConsumer {

    private static final String STREAM = "jobs:invoice:stream";
    private static final String GROUP = "invoice-workers";

    private final StringRedisTemplate redis;
    private final InvoiceProcessor processor;

    public InvoiceStreamConsumer(
            StringRedisTemplate redis,
            InvoiceProcessor processor) {
        this.redis = redis;
        this.processor = processor;
    }

    public void pollOnce(String consumerName) {
        List<MapRecord<String, Object, Object>> records =
                redis.opsForStream().read(
                        Consumer.from(GROUP, consumerName),
                        StreamReadOptions.empty()
                                .count(10)
                                .block(Duration.ofSeconds(2)),
                        StreamOffset.create(
                                STREAM,
                                ReadOffset.lastConsumed()
                        )
                );

        if (records == null || records.isEmpty()) {
            // No new records within the wait window.
            return;
        }

        for (MapRecord<String, Object, Object> record : records) {
            Map<Object, Object> fields = record.getValue();
            String jobId = String.valueOf(fields.get("jobId"));

            // Business processing must be idempotent and validate payload.
            processor.process(jobId);

            // ACK only after process(...) completes per business criteria.
            redis.opsForStream().acknowledge(
                    STREAM, GROUP, record.getId());
        }
    }
}
~~~

In this example, a background worker calls `pollOnce("invoice-worker-1")` repeatedly within an application-managed lifecycle. Each call reads up to 10 new records and blocks up to two seconds if none are available yet.

Steps:

1. `Consumer.from(GROUP, consumerName)` provides the group/consumer identity.
2. `ReadOffset.lastConsumed()` in a group context reads new undelivered records, corresponding to `>`.
3. `StreamReadOptions` sets `COUNT` and `BLOCK`.
4. `processor.process(jobId)` runs business processing.
5. `acknowledge(...)` sends `XACK` for the successfully processed record.

**If `processor.process(...)` throws an exception, the record is not ACKed in this snippet** and remains pending. Still, this is only the starting point: the example **does not yet implement pending recovery, retries, DLQ, attempt caps, or graceful shutdown**, all of which are required for production operations.

### 15.4. Why Should You Never ACK Inside a finally Block?

This is an anti-pattern:

~~~java
try {
    processor.process(jobId);
} finally {
    redis.opsForStream().acknowledge(
            STREAM, GROUP, record.getId());
}
~~~

If processing fails, `finally` still ACKs, removing the record from the PEL and preventing retries. **ACK only once you have decided the job truly succeeded or has been intentionally routed to an error-handling path.**

### 15.5. What Error Handling Must Be Added to This Example?

Minimal code must be expanded for real production systems:

- **Payload validation:** missing `jobId` must be treated as a malformed record, never turning `"null"` into an ID.
- **Retry policy:** distinguish transient errors from unrecoverable errors.
- **Recovery:** periodically read/claim pending entries from dead consumers rather than only reading `>`.
- **Idempotency:** prevent duplicate side effects on redelivery.
- **DLQ / failure store:** record repeatedly failing entries and failure reasons for investigation.
- **Monitoring:** alert on aged pending entries, inactive consumers, and abnormal stream growth.
- **Backpressure:** bound concurrent records processed to match downstream capacity.
- **Lifecycle:** never spawn unbounded threads; give workers controlled startup and shutdown.

## 16. StreamMessageListenerContainer: When You Do Not Want to Write a Polling Loop Yourself

Spring Data Redis also provides listener abstractions for Streams, such as `StreamMessageListenerContainer` and corresponding reactive APIs depending on version.

Concept:

~~~text
Spring application
      |
      v
StreamMessageListenerContainer
      |
      | poll Stream / consumer group per config
      v
MessageListener callback
      |
      | business processing
      v
XACK if acknowledgement strategy requires
~~~

The container manages polling, threads/executors, and listener lifecycles. Keep these distinctions clear:

- **The container does not automatically turn business logic into exactly-once.**
- If choosing an auto-ACK strategy, understand **when** ACK fires relative to business processing.
- If using manual ACK, the callback must ACK the proper group/record after processing.
- Pending recovery, retries, poison messages, retention, and monitoring still require explicit design.

In systems with only a few workers, calling `StreamOperations.read(...)` inside a background worker is great for learning. As complexity grows, the container reduces boilerplate plumbing, yet **does not replace correctness design in job processing**.

## 17. Distinguishing List, Streams, and Pub/Sub

All three may come up when discussing "sending an event through Redis," yet they serve different goals:

| Structure/Mechanism | Does Data Persist Without Consumers? | Can Offline Consumers Catch Up? | Native Processing ACK? |
|---|---|---|---|
| Redis List | Yes, while elements remain in the List | Can pop upon reconnecting, **if not already popped** | No built-in ACK for simple pop |
| Redis Streams | Yes, until records are deleted/trimmed | Can replay via offsets/groups while data is retained | Yes, `XACK` per consumer group |
| Redis Pub/Sub | Does not retain a backlog in basic Pub/Sub | No replay of messages missed while offline | No PEL or per-message ACK |

**Do not pick Pub/Sub as a mandatory-delivery job queue** just because publish/subscribe APIs look simple. Pub/Sub fits real-time notifications where dropping messages for offline subscribers is acceptable or a separate state API resynchronizes state.

Streams fit better when multiple systems observe an event and require per-group checkpoints. Still, **Redis Streams are not an infinitely durable event store**: retention, persistence, and error handling must be defined explicitly.

## 18. Connection and Blocking Read Implications

Both `BRPOP` (List) and `XREADGROUP BLOCK` (Streams) can **block on a Redis connection** until data arrives or the timeout expires.

In Spring Data Redis:

- Synchronous APIs like `ListOperations.rightPop(..., Duration)` hold the calling thread while waiting.
- `StreamOperations.read(..., StreamReadOptions.block(...))` can block similarly.
- With Lettuce, blocking commands typically use dedicated connections per factory/driver configuration; size pools and concurrent workers carefully.
- Pub/Sub uses long-lived connections/subscriptions rather than short request/reply pops or stream polls.

If you spawn 100 background workers all blocking simultaneously, watch connection pools, thread counts, Redis clients, timeouts, and concurrency. Choosing Streams does not eliminate connection overhead while waiting.

### 18.1. Redis Timeout vs. Client Timeout

Different timeout layers:

| Timeout Type | Example | Meaning |
|---|---|---|
| Waiting for job in Redis List | `BRPOP queue 5` | Wait up to 5 seconds for an element |
| Waiting for record in Stream | `XREADGROUP BLOCK 5000` | Wait up to 5000 milliseconds for a matching record |
| Command/client timeout | Driver/Boot config | How long the client waits for a response |
| Pool borrow timeout | Pool `max-wait` | How long to wait to borrow a connection |
| Business retry/visibility timeout | Application policy | When a job is considered potentially stuck and claimable |

If `BRPOP` times out and returns `null`, that can be a **normal empty-queue condition**. If a worker fails to borrow a connection from the pool, that is a **client resource issue**. If a Stream holds pending records too long, that indicates **unacknowledged work or slow processing**.

You cannot fix all three merely by raising `spring.data.redis.timeout`.

## 19. Ordering Issues: FIFO Alone Is Not Enough for Job Processing

Lists preserve pop order in FIFO when producer and consumer use the proper two ends. Streams assign monotonically increasing IDs and allow logical ordered reads.

However, **delivery order differs from completion order**:

~~~text
Job A delivered first -> worker-1 takes 15 seconds
Job B delivered later -> worker-2 takes 1 second

Job B finishes before Job A
~~~

When requirements demand "every event for the same order must be processed strictly in order":

- Limit concurrency per order or per partition.
- Avoid letting multiple workers mutate the same aggregate concurrently without versioning/locking.
- Use state machines, version fields, unique constraints, or out-of-order guards.
- When sharding by orderId, route all events for the same order consistently, and still plan for retries.

**Do not pick Streams merely because IDs increase and assume strict end-to-end processing order.**

## 20. Backlogs, DLQs, and Retries: Streams Help Manage Them, Not Complete Them

A production job-processing system typically spans many states:

~~~text
       NEW RECORD
           |
           v
       DELIVERED
           |
       PROCESSING
        /      \
       /        \
   SUCCESS     FAILURE
      |           |
      v           v
     XACK       retryable?
                 /    \
               Yes     No
                |       |
                v       v
           Pending /   Failure store/
           XAUTOCLAIM  Dead-letter
                |       |
                v       v
             RETRY     manual handling
~~~

### 20.1. Pending Does Not Mean Failed

A record may be pending because:

- A worker is legitimately running a multi-minute task.
- A worker crashed.
- The ACK call failed after processing succeeded.
- A worker errored out without handling failure.
- A worker lost connectivity mid-step.

Therefore, **pending ≠ failed**. Recovery logic requires wait thresholds, delivery counts, business state checks, and duplicate-suppression guards.

### 20.2. Designing a Dead Letter Queue (DLQ)

Redis Streams do not automatically create a DLQ meaning "after N failures, move the job here." The application must define:

1. When to stop retrying.
2. What to store: original payload, jobId, error type, last error, timestamps.
3. Whether failed items live in another Stream/List or a database.
4. How writing to the DLQ and ACKing the original record coordinate.
5. Who/what handles replaying jobs from the DLQ.

Example dedicated Stream:

~~~text
jobs:invoice:stream
jobs:invoice:dlq
~~~

When a job fails permanently, a worker can append an error record to the DLQ and ACK the original entry per policy. If writing to the DLQ and ACKing are separate commands, account for crashes between them; in Redis Cluster, multi-key scripts/transactions remain subject to hash slot constraints. Never assume "having a DLQ" means zero data can ever be lost.

## 21. Observability and Operations

### 21.1. Metrics to Track for Lists

~~~bash
LLEN jobs:invoice:list
~~~

`LLEN` reflects List length at read time, suitable for monitoring ready-to-pop backlogs.

When using ready + processing:

~~~bash
LLEN jobs:ready
LLEN jobs:processing
~~~

Monitor both the processing backlog and how long jobs stay there, not only the ready queue. Lists do not natively provide delivery counts or consumer ownership, so external metadata is needed to see who holds each job.

### 21.2. Metrics to Track for Streams

~~~bash
XLEN jobs:invoice:stream
XINFO GROUPS jobs:invoice:stream
XINFO CONSUMERS jobs:invoice:stream invoice-workers
XPENDING jobs:invoice:stream invoice-workers
~~~

Metrics to collect:

- Stream length and `XADD` rate.
- Pending count per group and per consumer.
- Age of the oldest pending record.
- Successful completion/ACK rate and retry rate.
- Delivery/retry counts and job failure rate.
- Consumers that stopped heartbeating/polling.
- Per-group lag/backlog where provided by the Redis version.
- Memory usage, Redis CPU, command latency, network, and connection pool wait time.

**XLEN does not equal unprocessed job count.** It counts all entries currently retained in the Stream, including ACKed entries not yet trimmed. To measure per-group backlog, combine group info, pending counts, and offset/lag rather than relying on XLEN alone.

### 21.3. When Should Alarms Fire?

Warning signs include:

- Pending entries rising steadily while ACKs stop.
- An inactive consumer holding many pending entries.
- Job processing duration exceeding SLA.
- Trimming approaching the oldest record still needed by a slow consumer.
- Redis memory growing due to unbounded retention.
- Connection borrow wait rising because too many consumers are blocking.

Tune thresholds to each workload instead of applying one universal number everywhere.

## 22. Multi-Instance Processing and Redis Cluster

Both a Redis List and a Stream are **a single Redis key per queue/stream**. In Redis Cluster, each key belongs to one hash slot. Therefore:

- Running multiple Spring Boot instances does not split a single Stream key across multiple nodes.
- Multiple consumer groups/consumers reading one Stream key still concentrate load on the slot holding that key.
- When extreme throughput or workload isolation is needed, shard queues/Streams across multiple keys.
- Commands touching multiple keys simultaneously in Cluster must respect **same hash slot constraints**, such as the ready+processing List pattern using BLMOVE.

### 22.1. Note on Ready and Processing Lists in Redis Cluster

`BLMOVE` touches **two Redis keys**. In Redis Cluster, keys in a multi-key command must satisfy the same-slot rule. Use hash tags intentionally:

~~~text
jobs:{invoice}:ready
jobs:{invoice}:processing
~~~

Both keys share the `invoice` hash tag and map to the same slot, allowing two-key move operations. Still, all traffic for this group hits that one slot; if invoice traffic is massive, design dedicated sharding.

### 22.2. Sharding Streams Requires Attention to Ordering

Example sharding by customerId:

~~~text
jobs:invoice:shard:0
jobs:invoice:shard:1
jobs:invoice:shard:2
~~~

Each Stream has its own IDs and group state. There is no automatic **global order** across separate Streams. If business rules require per-orderId sequencing, route records for the same order consistently to one shard, while still handling retries and out-of-order execution when multiple consumers run concurrently within that shard.

## 23. Making Decisions Through Concrete Scenarios

### Scenario A — Logging a Non-Critical Action Where Loss Is Acceptable

**Requirement:** a background worker updates auxiliary metrics; losing an occasional job can be recomputed from source data.

**You can start with a List** and `LPUSH/BRPOP`. Prioritize simplicity and fewer moving operational parts. Still bound backlog size, configure timeouts, and add basic error handling.

### Scenario B — Generating Invoices That Must Be Processed

**Requirement:** jobs must not "disappear" if a worker claims them and crashes; retries, pending tracking, and avoiding duplicate invoices are mandatory.

**Evaluate Streams + consumer groups**, paired with:

- ACK after persisting the outcome.
- Pending recovery via `XAUTOCLAIM` or an equivalent mechanism.
- Idempotency keyed by invoice job ID.
- Retries/backoff and a DLQ/failure store.
- Appropriate retention and persistence.

When legal/financial durability requirements are strict, treat the Redis queue as **one component** of the solution rather than the sole source of truth; use transactions/outboxes and proper business storage architecture.

### Scenario C — Sending Real-Time Notifications to Online Users

**Requirement:** offline users fetch current state from an API; missed instant notifications are acceptable.

Evaluate **Redis Pub/Sub** when real-time fire-and-forget semantics fit. There is no need to adopt Streams just to broadcast a signal that needs no ACK.

### Scenario D — Both Billing and Analytics Must Receive Every Event

**Requirement:** every event from the order service must be processed by two independent pipelines.

Streams with **two consumer groups** are a natural fit:

~~~text
Stream: order-events
Group 1: billing
Group 2: analytics
~~~

Each group keeps its own offset, pending entries, and ACKs. A single Redis List with competing pops splits events across consumers and **cannot** deliver a copy to every group.

### Scenario E — A Task List Waiting for Users to Click a Button

**Requirement:** a per-user list of tasks that must be displayed, sorted, or individually deleted; not background worker consumption.

Do not pick Streams merely because the word "task" appears. A **List, Sorted Set, Hash**, or relational database may fit better depending on access and query patterns. A Redis queue fits only when the requirement truly is **handing work off to consumers**.

## 24. Decision Tree: Choosing List vs. Streams

~~~text
                Need to pass work between producers and workers?
                                |
                   +------------+------------+
                   |                         |
                  No                        Yes
                   |                         |
            Pick another                     v
            data type           Need ACK/retry/pending tracking?
                                      /           \
                                    Yes            No
                                    |               |
                                    v               v
                              Redis Streams     Is losing a job
                              + consumer group  after pop acceptable?
                                    |             /          \
                                    |           Yes           No
                                    |            |             |
                                    |            v             v
                                    |       Simple Redis   List + processing
                                    |           List       or Streams
                                    |                          |
                                    +--------------------------+
                                                 |
                                                 v
                             Do multiple groups need every event?
                                   /                \
                                 Yes                 No
                                 |                    |
                                 v                    v
                         Streams + independent   Evaluate complexity,
                               groups            load, and operations
                                   \                /
                                    \              /
                                     v            v
                                Design idempotency,
                               retention, timeouts, DLQ,
                                 persistence & monitoring
~~~

**Practical rule:** favor the **simplest solution that meets failure and recovery requirements**, not the solution with the fewest initial lines of code. A short List queue looks easy to write initially, yet becomes expensive if you later have to bolt on ACKs and retries.

## 25. Common Misconceptions

**"BRPOP is just like XREADGROUP because both wait for jobs."** Incorrect. BRPOP pops and removes the element from the List; XREADGROUP delivers the record and keeps it pending until ACKed.

**"XACK deletes the record from the Stream."** Incorrect. XACK clears the pending state inside one consumer group. Retention/deletion of records is a separate step.

**"Consumer groups automatically retry every failed job."** Incorrect. The PEL tracks pending entries, yet the application must orchestrate re-reading/claiming, error handling, and ACKing per policy.

**"Calling XREADGROUP with `>` automatically redelivers old jobs."** Incorrect. `>` requests new, undelivered records in the group; pending entries must be handled separately.

**"Streams guarantee exactly-once."** Incorrect. Crashing after a business commit and before ACK can cause reprocessing. Business-level idempotency is required.

**"ACK means data is durably flushed to disk."** Incorrect. ACK confirms processing inside a Redis group; durability across restarts/failovers depends on persistence and other configuration.

**"Lists can never be used for reliable queues."** Not strictly true. You can combine ready/processing lists, atomic moves, and custom retry logic, though complexity rises.

**"Two workers in the same group both receive every event."** Incorrect. Sharing a group splits load. To let multiple independent groups each receive every event, create separate groups.

**"An ACKed Stream record can be deleted immediately regardless of other consumers."** Never assume that. Another group may still need the record, or audit/replay rules may require longer retention.

**"Increasing IDs guarantee jobs finish in order."** Incorrect. Parallel processing and retries can reorder completion.

**"Adding more consumers always makes things faster."** Incorrect. Throughput is bounded by the Redis node/slot, network, downstream dependencies, connection pools, and business bottlenecks.

**"Redis Streams never lose messages."** Incorrect. Trimming, deletion, eviction, persistence settings, or operational mistakes can all cause data loss.

## 26. Guided Hands-on Exercises

### Exercise 1 — Observing Destructive Pop in a List

~~~bash
DEL lab:list:jobs
LPUSH lab:list:jobs job-A job-B
LRANGE lab:list:jobs 0 -1
BRPOP lab:list:jobs 2
LRANGE lab:list:jobs 0 -1
~~~

Answer:

1. Which element is popped first?
2. Does it still appear in `LRANGE` after popping?
3. If the consumer crashes immediately after BRPOP, does Redis keep any state indicating the job is in flight?

### Exercise 2 — Observing a Processing List

~~~bash
DEL lab:list:ready lab:list:processing
LPUSH lab:list:ready job-C
BLMOVE lab:list:ready lab:list:processing RIGHT LEFT 2
LRANGE lab:list:ready 0 -1
LRANGE lab:list:processing 0 -1
LREM lab:list:processing 1 job-C
~~~

Answer:

1. Why does the job remain in Redis after the BLMOVE step?
2. When a worker crashes before LREM, what finds and retries the job?
3. If two jobs share the payload `job-C`, what risk does value-based LREM pose?

### Exercise 3 — Observing Pending Entries in Streams

~~~bash
DEL lab:stream:jobs
XGROUP CREATE lab:stream:jobs lab-workers 0 MKSTREAM
XADD lab:stream:jobs * jobId job-D
XREADGROUP GROUP lab-workers worker-1 COUNT 1 STREAMS lab:stream:jobs >
XPENDING lab:stream:jobs lab-workers
XLEN lab:stream:jobs
~~~

Copy the **actual Record ID** returned by XADD or XREADGROUP. Then run:

~~~bash
XACK lab:stream:jobs lab-workers <actual-record-id>
XPENDING lab:stream:jobs lab-workers
XLEN lab:stream:jobs
~~~

Here `<actual-record-id>` is a placeholder and must be replaced with the real ID (for example `1762965000000-0`), without typing angle brackets or the placeholder text literally.

Observe:

- The pending count changes after XACK.
- XLEN does not automatically drop merely because an entry was ACKed.
- The consumer group manages acknowledgement state separately from the Stream's stored entries.

### Exercise 4 — Simulating Worker Crash and Claim

On a Redis Server supporting `XAUTOCLAIM`:

1. XADD another job.
2. Have `worker-1` call XREADGROUP, **without ACKing**.
3. Inspect `XPENDING`.
4. Wait past the lab's idle threshold.
5. Have `worker-2` call `XAUTOCLAIM` to claim the pending entry.
6. Simulate processing and then `XACK`.

Example claim command once the entry is sufficiently idle:

~~~bash
XAUTOCLAIM lab:stream:jobs lab-workers worker-2 5000 0-0 COUNT 10
~~~

In this lab, five seconds is only for quick testing. **Never use 5000 ms as a production retry threshold** when real jobs may take longer to run.

### Exercise 5 — Designing Idempotency

Suppose a consumer processes `invoice-job-42`, saves the invoice to the database successfully, and crashes before XACK. When the job is claimed and retried:

- How do you detect the invoice already exists?
- Which job ID acts as the immutable business identifier?
- Where should the unique constraint or database transaction live?
- When is it safe to ACK without creating duplicate side effects?

Sketch the business state diagram before writing more code. This matters far more than memorizing a specific Redis command.

## 27. Reinforcement Questions

**1. What kind of queue does LPUSH + BRPOP suit?**

A simple FIFO queue: producer pushes on the left, consumer pops from the right. When the List is empty, BRPOP waits up to the timeout; upon popping, the element leaves the source List.

**2. Why does direct List popping risk losing jobs?**

Because the element is deleted from the queue before the consumer finishes processing; a crash after popping can leave no copy available to retry.

**3. What does BLMOVE solve, and what does it leave unsolved?**

BLMOVE can atomically move an element from a ready List to a processing List, keeping delivered jobs visible. However, ownership tracking, timeouts, claiming/requeuing, ACKs, and retries must still be built separately.

**4. How are Redis Streams structured differently?**

Each record has an ID and fields/values; reading a record does not automatically remove it from the Stream. Offsets, consumer groups, and retention policies can be used.

**5. What is the PEL?**

The Pending Entries List, where a consumer group tracks records delivered but not yet ACKed, along with ownership and details supporting monitoring and recovery.

**6. Does XACK delete the record's content from the Stream?**

No. It acknowledges the record inside one group and clears its pending state; data removal/trimming is handled by separate retention operations.

**7. Why doesn't a new consumer receive old pending entries using XREADGROUP with `>`?**

Because `>` requests records never yet delivered within the group. Pending entries already have an owner; read the consumer's own pending entries or claim from another owner via the appropriate mechanism.

**8. Does XAUTOCLAIM mean the job has already been processed successfully?**

No. It transfers ownership of sufficiently idle pending entries; the new consumer must still process and ACK upon completion.

**9. Can you claim Streams provide exactly-once?**

No. A job can run again after a crash before ACK. Idempotency and proper transaction boundaries are required for business side effects.

**10. Why can the same Stream serve both billing and analytics?**

Each consumer group maintains its own offsets, pending entries, and ACKs. Two groups can independently process the same records for different purposes while consumers within each group split load.

**11. Why does XLEN not equal the number of unfinished jobs?**

Because XLEN counts all records currently retained in the Stream, including ACKed records not yet trimmed. Pending counts, offsets/lag, and business status must be monitored separately.

**12. If consumers must process strictly in order, is adding more workers good?**

No. Concurrent consumers can finish out of delivery order. Design per-aggregate partitioning/serialization or explicit ordering controls.

**13. Does a Stream need a size bound?**

Yes. Without retention, records grow continuously and consume memory. Yet trimming too aggressively can deprive slow consumers or pending entries of their payloads.

**14. Should you choose List or Streams when jobs must retry after worker crashes?**

Streams with consumer groups are usually the more natural choice thanks to PEL/ACK/claim, or use Lists with ready/processing and custom recovery if you have a clear reason.

## Key Takeaways

~~~text
REDIS LIST
  Producer: LPUSH / RPUSH
  Consumer: BRPOP / BLPOP
  -> Pop = element leaves source List
  -> Simple, but crash after pop can lose jobs
  -> For recovery: ready/processing Lists + custom logic

REDIS STREAMS
  Producer: XADD -> record ID + fields
  Consumer group: XREADGROUP
  -> Record delivered and tracked in PEL until ACK
  -> XACK clears pending state; does not delete Stream record
  -> XPENDING inspects; XAUTOCLAIM/XCLAIM reclaims stuck jobs
  -> Needs retry policy, idempotency, DLQ, retention, monitoring

CHOOSE LIST WHEN
  -> Queue is small and minimal, post-pop loss risk is acceptable,
     or an independent recovery system exists

CHOOSE STREAMS WHEN
  -> Need ACKs, retries, pending tracking, consumer groups,
     replay, and per-group progress management

BOTH REQUIRE
  -> Controlling worker count, timeouts, keys/slots, memory,
     connections, persistence, and business semantics
~~~

**Choosing between List and Streams should be based not on how many lines of Java call Redis, but on what happens when the system fails.** If you simply need to pop an element and run straightforward work, a List can suffice. If jobs must be tracked across *delivered → processing → acknowledged*, or require failed-consumer recovery and multiple independent consumer groups, Streams with consumer groups generally provide a stronger foundation. Regardless of the option chosen, **idempotency, retries, retention, and safeguarding business effects** remain the application's responsibility.
