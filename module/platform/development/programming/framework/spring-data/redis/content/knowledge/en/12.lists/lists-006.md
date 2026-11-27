# Element Ordering, Duplicate Elements, and Positional Access Cost

## 1. What Does a Redis List Represent?

In Spring Data Redis, a **List** is a Redis data structure that stores an **ordered sequence of elements** under a single key. It fits workloads that add or remove elements at the head or tail, such as simple task queues, recent event sequences, pending work lists, or stacks.

Three characteristics dictate how Redis Lists are used:

1. **Order matters:** the first element, last element, and relative positions are maintained by Redis in the order commands executed.
2. **Duplicates are permitted:** a value can appear multiple times; unlike a Redis Set, a Redis List does not automatically deduplicate.
3. **Positional access has varying cost:** adding/removing at either end is typically fast, whereas accessing an element deep inside the list requires traversing intermediate elements.

Example:

~~~text
Key: lesson:list:orders

Head (left/head)                           Tail (right/tail)
     |                                           |
     v                                           v
  [order-A] -> [order-B] -> [order-A] -> [order-C]
     0            1            2            3
    -4           -3           -2           -1
~~~

The List above has **4 elements**, in which **order-A appears twice**. Index **0** points to the first element, and index **-1** points to the last element. These are two different ways of numbering positions in the same list.

In Java applications, the corresponding API is **ListOperations**, accessed through **RedisTemplate.opsForList()** or **StringRedisTemplate.opsForList()**.

## 2. Differences Between Redis List and Commonly Confused Structures

| Structure | Ordered | Allows Duplicate Values/Members? | Suitable Use Cases |
| --- | --- | --- | --- |
| **Redis List** | Yes, by insertion and manipulation order | **Yes** | Simple queues, stacks, recent activity lists |
| **Redis Set** | No ordering guarantee | **No** | Membership checks, deduplication |
| **Redis Sorted Set** | Yes, by score and tie-breaking rules | Unique members; writing an existing member updates its score | Leaderboards, rankings |
| **Redis Stream** | Entries have IDs; read as an event log | Payloads can repeat; each entry has its own ID | Event streams needing consumer groups and acknowledgements |
| **Java List in JVM** | Yes | Yes | In-memory data local to one Java process |

Notably, a Redis List stores data **on the Redis Server** and can be accessed concurrently by multiple Spring Boot instances. A plain Java List exists only within a single application process unless synchronized via another mechanism.

Redis does not understand whether **order-A** represents "a unique order" or "two processing attempts for the same order." Redis simply stores byte sequences at two positions. Business rules around duplicates must be enforced by the application.

## 3. List Ordering Is Shaped by Push Commands

### 3.1. RPUSH Appends to the Right

In **interactive redis-cli**, run:

~~~text
RPUSH lesson:row132:queue A B C
LRANGE lesson:row132:queue 0 -1
~~~

Resulting list:

~~~text
[A, B, C]
~~~

**RPUSH key value ...** adds elements to the **tail** in the order they appear in the command. The return value is the List length after the operation.

Continuing:

~~~text
RPUSH lesson:row132:queue D
LRANGE lesson:row132:queue 0 -1
~~~

Result:

~~~text
[A, B, C, D]
~~~

This is intuitive when you want to **preserve input order** across a multi-element push.

### 3.2. LPUSH Prepends to the Left

If from the current list you call:

~~~text
LPUSH lesson:row132:queue urgent
LRANGE lesson:row132:queue 0 -1
~~~

Result:

~~~text
[urgent, A, B, C, D]
~~~

**LPUSH** adds to the **head**. When passing **multiple values in a single LPUSH**, each value is pushed onto the head in command processing order, so the left-to-right order ends up reversed relative to the argument sequence:

~~~text
DEL lesson:row132:multi
LPUSH lesson:row132:multi A B C
LRANGE lesson:row132:multi 0 -1
~~~

Result:

~~~text
[C, B, A]
~~~

Compare with:

~~~text
DEL lesson:row132:multi
RPUSH lesson:row132:multi A B C
LRANGE lesson:row132:multi 0 -1
~~~

Result is **[A, B, C]**.

This matters greatly when reading **leftPushAll(...)** in Spring Data Redis: if you expect the list to keep the left-to-right order of the input collection, verify whether you are pushing at the head or the tail.

### 3.3. Adding, Reading, and Removing Have Different Behaviors

| Command | Affected Elements | Pops/Deletes Elements from List? |
| --- | --- | --- |
| **LPUSH** | Adds at head | Does not delete existing elements |
| **RPUSH** | Adds at tail | Does not delete existing elements |
| **LINDEX** | Reads at position | **Read-only** |
| **LRANGE** | Reads a slice | **Read-only** |
| **LPOP** | Head of list | **Retrieves and deletes** first element |
| **RPOP** | Tail of list | **Retrieves and deletes** last element |
| **LSET** | Specified position | Overwrites value at that position |
| **LINSERT** | Before/after a pivot | Inserts element and shifts later positions |
| **LREM** | Elements with matching value | Deletes one or more occurrences |
| **LTRIM** | Keeps only specified range | Deletes elements outside the range |

Do not look only at command names "left/right" and guess FIFO/LIFO order: check **which end is written** and **which end is read/removed** in each workflow.

## 4. Positional Indices: Positive, Negative, and Inclusive Ranges

Redis Lists support indices:

- **0** is the first element.
- **1** is the second element.
- **-1** is the last element.
- **-2** is the second-to-last element.
- If the index is beyond the List length, **LINDEX** returns nil.

Create sample data:

~~~text
RPUSH lesson:row132:index apple banana cherry date
~~~

Read commands:

~~~text
LINDEX lesson:row132:index 0
LINDEX lesson:row132:index 2
LINDEX lesson:row132:index -1
LINDEX lesson:row132:index -2
LINDEX lesson:row132:index 99
~~~

Expected outputs are **apple**, **cherry**, **date**, **cherry**, and **nil**, respectively.

### 4.1. LRANGE Includes Both Start and Stop

~~~text
LRANGE lesson:row132:index 0 -1
LRANGE lesson:row132:index 0 1
LRANGE lesson:row132:index 1 2
LRANGE lesson:row132:index -2 -1
~~~

Explanation:

| LRANGE Command | Returned Range |
| --- | --- |
| 0 -1 | Entire List: apple, banana, cherry, date |
| 0 1 | First two elements: apple, banana |
| 1 2 | Second and third elements: banana, cherry |
| -2 -1 | Last two elements: cherry, date |

**LRANGE's stop index is inclusive**, meaning the element at stop is also returned if within the List. This is a common contrast with many Java APIs that use end-exclusive bounds.

If start exceeds the length or the range yields no valid elements, LRANGE returns an empty list. Negative indices do not reverse order; they simply locate positions relative to the end.

### 4.2. LSET Overwrites an Existing Position

~~~text
LSET lesson:row132:index 1 blueberry
LRANGE lesson:row132:index 0 -1
~~~

The list becomes:

~~~text
[apple, blueberry, cherry, date]
~~~

**LSET** replaces the value at index 1; **it does not insert a new element**. If the index is out of range, Redis reports **index out of range**; LSET does not expand the List to reach the requested position.

### 4.3. An Index Is a Current Position, Not a Stable ID

Suppose an application sees **banana** at index 1. Another client calls LPUSH with a new value; banana shifts to index 2. If the application then calls LSET at index 1 thinking it is updating banana, it can overwrite **the wrong element**.

~~~text
Initial:                 [apple, banana, cherry]
Client A reads index 1   -> banana
Client B LPUSH urgent    -> [urgent, apple, banana, cherry]
Client A LSET index 1    -> overwrites apple, not banana
~~~

Therefore **do not use list indices as long-lived record identifiers** in systems with multiple writers. When updating an entity by ID is needed, a Hash/per-key model or a structure with stable identifiers is typically more suitable.

## 5. Redis Lists Allow Duplicate Elements

Create a List:

~~~text
RPUSH lesson:row132:duplicates A B A C A
LRANGE lesson:row132:duplicates 0 -1
LLEN lesson:row132:duplicates
~~~

Redis stores everything:

~~~text
[A, B, A, C, A]
~~~

And **LLEN** returns **5**, not 3. The List does not collapse duplicate copies of A.

If a system tracks page views and a user opens the same URL three times, three identical entries can be completely valid. Conversely, if the List represents "unique pending tasks," three identical entries can cause duplicate execution.

### 5.1. LPOS Finds the Position of a Value

~~~text
LPOS lesson:row132:duplicates A
LPOS lesson:row132:duplicates B
LPOS lesson:row132:duplicates missing
LPOS lesson:row132:duplicates A COUNT 0
~~~

In the state above:

- LPOS searching for the first **A** normally returns position **0**.
- LPOS searching for **B** returns **1**.
- A missing value returns nil.
- With **COUNT 0** on Redis versions supporting LPOS and COUNT, Redis can return **all matching positions** in scan order.

Avoid repeatedly scanning an entire very large List to check existence; **LPOS has linear scan cost proportional to the elements inspected**. If the main goal is membership testing or deduplication, a **Redis Set** is usually a better fit.

### 5.2. LREM Removes Matching Occurrences

LREM has the form:

~~~text
LREM key count value
~~~

Meaning of **count**:

| count | Removal Behavior |
| --- | --- |
| **count > 0** | Removes up to count matching elements, scanning **head to tail**. |
| **count < 0** | Removes up to abs(count) matching elements, scanning **tail to head**. |
| **count = 0** | Removes **all** elements matching value. |

Example:

~~~text
RPUSH lesson:row132:remove A B A C A
LREM lesson:row132:remove 1 A
LRANGE lesson:row132:remove 0 -1
~~~

Result:

~~~text
[B, A, C, A]
~~~

Only the **first A** is removed. Continuing:

~~~text
LREM lesson:row132:remove -1 A
LRANGE lesson:row132:remove 0 -1
~~~

Result:

~~~text
[B, A, C]
~~~

This time the **last A** is removed. Finally:

~~~text
LREM lesson:row132:remove 0 A
LRANGE lesson:row132:remove 0 -1
~~~

Result:

~~~text
[B, C]
~~~

**LREM compares values**, without distinguishing two equal-value entries by independent IDs. If each occurrence represents a distinct event, removing by value can delete the wrong event or too many events.

### 5.3. Checking First Then Calling LPUSH Does Not Guarantee Uniqueness

A flawed attempt at deduplication:

~~~java
if (redis.opsForList().index("lesson:row132:tasks", 0) == null) {
    redis.opsForList().leftPush("lesson:row132:tasks", "job-42");
}
~~~

This code inspects only index 0 and **does not check the entire List**; even if you used LPOS across the entire List, **check-then-push** still consists of two separate commands. Two requests can both see the value absent and both push **job-42**.

If uniqueness is required, enforce the constraint in an appropriate place—for instance, combining a Set and a List in a Lua script/transaction per custom rules, or using a Redis Set when order is unnecessary. Do not expect a Redis List to enforce uniqueness on its own.

## 6. Positional Access Cost: Why O(1) and O(N) Differ

In algorithm analysis, **N** is the number of elements in the List. Notation:

- **O(1)**: cost does not grow linearly with element count; operations focused on the head/tail typically have this property.
- **O(N)**: in the worst case, traversal touches a number of elements proportional to List length.
- **O(S + M)**: describes slicing a range, combining the cost to seek to the start offset and the cost to return **M elements**.

Modern Redis implements Lists with a structure optimized for operations at both ends, typically nodes of packed elements inside a quicklist. Internal details can change across versions, configurations, and List lengths, yet the **command cost model** is what matters during design.

### 6.1. Cost Table for Common Operations

| Command | Typical Complexity | Practical Meaning |
| --- | --- | --- |
| **LPUSH / RPUSH** | O(1) per element | Adding at head/tail scales well to long Lists. |
| **LPOP / RPOP** | O(1) per element | Fast popping from head/tail. |
| **LLEN** | O(1) | Reads length without scanning elements. |
| **LINDEX** | O(N) worst case | Must traverse to the target position; near head/tail is cheaper. |
| **LSET** | O(N) worst case | Must locate the position before overwriting value. |
| **LRANGE** | O(S + M) | Pays to seek to start and return M elements. |
| **LPOS** | O(N) worst case | Searches for value by scanning the list. |
| **LINSERT** | O(N) | Scans for pivot, then inserts before/after pivot. |
| **LREM** | O(N + M) algorithmically | Scans for value and removes matching occurrences. |
| **LTRIM** | Proportional to number of removed elements | Must drop elements outside the retained slice. |

**Note:** these are complexities in terms of element count and access pattern, not a promise that every command takes a fixed number of microseconds. Value size, network latency, serialization, CPU/memory pressure, and Redis configuration still affect actual latency.

### 6.2. Why LINDEX 0 Differs from LINDEX in the Middle of a List

Suppose a List has one million elements:

~~~text
LINDEX very:large:list 0
LINDEX very:large:list -1
LINDEX very:large:list 500000
~~~

Reading the first or last element leverages Redis's structure for very fast access near either end. Reading an element in the middle requires **traversing to that position** across intermediate elements/nodes.

In the worst case, the cost scales as **O(N)** with List length. Therefore, a Redis List **should not be treated like a Java array offering O(1) random access at any index**.

A large index does not always mean scanning from the head in all versions/internal layouts: Redis can traverse from whichever end (head or tail) is closer. The key rule remains: **accessing deep inside the middle of a List can be far more expensive than operating at either end**.

### 6.3. Why LRANGE 0 -1 Can Overload Redis

~~~text
LRANGE very:large:list 0 -1
~~~

This command requests **every element**. Even when seeking to the start is cheap, Redis still has to read, assemble, and transmit **N elements** over the network. When the List is large, this consumes substantial CPU, temporary memory, and bandwidth.

If you only need the first 20 elements, bound the range:

~~~text
LRANGE very:large:list 0 19
~~~

If you only need the last 20 elements:

~~~text
LRANGE very:large:list -20 -1
~~~

**Stop is inclusive**; the range 0 19 has at most 20 elements. Bound returned element counts when building APIs.

### 6.4. Offset Pagination Has Growing Cost

For example, a screen fetching 20 elements per page:

~~~text
LRANGE very:large:list 0 19
LRANGE very:large:list 20 39
LRANGE very:large:list 20000 20019
~~~

Pages at deep offsets can require more traversal to reach the starting point. Moreover, when another client calls LPUSH/LPOP, elements **shift positions**. Index-based pagination can therefore produce duplicates or skipped items between two requests.

For large datasets needing stable pagination, consider a structure with **stable identifiers/sort keys** or a different retrieval model. Lists remain great for reading the **N newest elements** at one end; they are less suited for deep random queries over very long lists.

## 7. FIFO, LIFO, and Choosing Push/Pop Ends

A List can serve as a queue or a stack depending on which ends are chosen.

### 7.1. FIFO Queue: First In, First Out

A common pattern:

~~~text
RPUSH lesson:row132:fifo job-A
RPUSH lesson:row132:fifo job-B
RPUSH lesson:row132:fifo job-C
LPOP lesson:row132:fifo
LPOP lesson:row132:fifo
~~~

Two LPOP calls retrieve **job-A**, then **job-B**. Each new element is added at the **tail**, and the oldest element is popped from the **head**.

~~~mermaid
flowchart LR
    A["RPUSH job-A, job-B, job-C"] --> B["[A, B, C]"]
    B --> C["LPOP"]
    C --> D["Returns A; [B, C] remains"]
~~~

Another option is LPUSH at the head and RPOP at the tail; that also gives FIFO. What matters is **pushing and popping at opposite ends**.

### 7.2. LIFO Stack: Last In, First Out

~~~text
RPUSH lesson:row132:stack A B C
RPOP lesson:row132:stack
RPOP lesson:row132:stack
~~~

Two RPOP calls retrieve **C**, then **B**. When pushing and popping at the **same end**, the List behaves like a stack.

### 7.3. Ordering When Multiple Producers Write Concurrently

Suppose producer A and producer B both RPUSH to the same key:

~~~text
Producer A: RPUSH queue job-A
Producer B: RPUSH queue job-B
~~~

Each RPUSH command is atomic; Redis establishes an execution order for commands arriving at the same key. However, if two producers send requests nearly simultaneously, the application **cannot rely on log timestamps across two machines** to assert that A is guaranteed to precede B.

List order reflects **the order in which Redis executed the commands**, whereas business logic requiring global ordering by event timestamp needs an explicit sequencing mechanism.

### 7.4. Duplicate Elements in a Queue

~~~text
RPUSH lesson:row132:jobs email:42 email:42 email:43
LPOP lesson:row132:jobs
LPOP lesson:row132:jobs
~~~

Both LPOP calls can return **email:42**. A Redis List does not know that the first email succeeded and skip the second.

If the application must not process duplicate jobs, enforce **idempotency** at the worker layer or use an appropriate queue mechanism rather than relying on a List to deduplicate.

## 8. Blocking Pop: Waiting for Elements Without Continuous Polling

When a queue is temporarily empty, a worker can use **BLPOP** or **BRPOP** to wait for an element to arrive.

Example in redis-cli:

~~~text
BLPOP lesson:row132:wait 2
~~~

Here **2** is the timeout in seconds; if no element exists, Redis waits up to about 2 seconds and then returns an empty result. If an element arrives while waiting, Redis returns **the key name and the popped value**.

In Spring Data Redis, blocking `ListOperations` APIs can accept `Duration`:

~~~java
String job = redis.opsForList().leftPop(
        "lesson:row132:wait",
        Duration.ofSeconds(2)
);
~~~

When the timeout expires with no element, the result can be null; worker code must handle that case.

**Blocking pop occupies a connection while waiting**, so consider connection pools, worker counts, timeouts, and graceful shutdown. In reactive WebFlux environments, do not invoke blocking APIs on the event loop without proper isolation.

### Does Blocking Pop Guarantee Successful Processing?

No. **LPOP/BLPOP removes the element from the List upon returning**, before the application completes business logic:

1. Worker receives a job via BLPOP.
2. Redis has already removed the job from the queue.
3. Worker encounters an error or the process stops before finishing.
4. The job is no longer in the source queue for another worker to pick up automatically.

If you need **at-least-once**, acknowledgements, pending lists, retries, and failed-worker recovery, design them explicitly. One List pattern moves jobs from a ready queue to a processing queue atomically via **LMOVE/BLMOVE** (on supported Redis versions), then acknowledges by removing from processing; stuck-job recovery and duplicate handling are still required.

**Redis Streams** with consumer groups and acknowledgements are generally better suited when delivery guarantees and pending-message visibility are needed. Redis Lists remain very useful for simple queues when this limitation is accepted and handled clearly.

## 9. Updates Inside a List: Watch Out for O(N)

### 9.1. LINSERT Searches for a Pivot Element

~~~text
RPUSH lesson:row132:insert A C D
LINSERT lesson:row132:insert BEFORE C B
LRANGE lesson:row132:insert 0 -1
~~~

Result:

~~~text
[A, B, C, D]
~~~

**LINSERT** searches for pivot value **C** and inserts B before it. If multiple elements have value C, Redis uses the first match per command rules. Finding the pivot can require scanning the List, so LINSERT is O(N) in the worst case.

If frequent insertions at arbitrary positions in very long Lists are needed, this structure may not be suitable.

### 9.2. LSET Updates by Index

~~~text
LSET lesson:row132:insert 2 C2
LRANGE lesson:row132:insert 0 -1
~~~

The result is **[A, B, C2, D]**. LSET updates the value at index 2, but must seek to that position; cost can grow with depth.

### 9.3. LTRIM Keeps a Recent Window

An application wanting to store at most the **100 most recent events** can run:

~~~text
LPUSH lesson:row132:recent event-new
LTRIM lesson:row132:recent 0 99
~~~

LPUSH puts event-new at the head; LTRIM keeps at most the first 100 elements and drops everything outside. This is a sound List pattern for bounded recent history.

However, **LPUSH and LTRIM are two separate commands**. If you need to guarantee the list never exceeds the cap even across concurrent client interleavings, combine them in a Redis transaction or Lua script. In many cache/analytics applications, a brief overshoot between the two commands is acceptable; decide based on real requirements.

Do not assume **LTRIM is O(1) in every case**. Cost depends on the number of elements removed and the List's current layout; trimming a huge batch of elements can be expensive.

### 9.4. LTRIM and Empty Keys

When all elements are removed from a List via pop or trim, Redis typically removes **the key itself** from the keyspace. Then:

~~~text
TYPE lesson:row132:empty
LLEN lesson:row132:empty
~~~

TYPE returns **none**, and LLEN on a missing key returns **0**. Do not confuse an empty List with an existing key carrying a TTL: in Redis, empty List structures are usually not retained as standalone data keys.

## 10. TTL Applies to the List Key, Not Individual Elements

Redis lets you set expiration on the **entire key**:

~~~text
RPUSH lesson:row132:ttl A B C
EXPIRE lesson:row132:ttl 60
TTL lesson:row132:ttl
RPOP lesson:row132:ttl
TTL lesson:row132:ttl
~~~

Under normal conditions, RPOP does not reset the key's TTL. When TTL expires, **the entire List** disappears, not just a single element.

Cases to distinguish:

- LPUSH/RPUSH on a List that already has a TTL typically preserves its current expiration.
- Creating a new List via LPUSH/RPUSH when the key does not exist does not automatically set a TTL; apply EXPIRE or an appropriate design if expiry is required.
- If all elements are popped, the key is deleted; its TTL no longer exists.
- Redis Lists do not natively support independent TTLs per element. If each entry needs its own deadline, consider separate keys, a Sorted Set with timestamp scores, or another data model.

For example, a "queue of jobs that must run before 12:00" cannot rely solely on a 1-hour List TTL to know which individual jobs expired. Store each job's deadline and handle expiration in business rules.

## 11. Spring Boot Example: Preserving Order, Allowing Duplicates, and Positional Access

### 11.1. Dependencies and Configuration

With Spring Boot 3.x using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Example local Redis Server configuration:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

This is an illustrative connection configuration; if the app runs in a container or Redis uses ACL/TLS, configure the appropriate host and settings. Spring Boot typically auto-configures a **StringRedisTemplate** bean when the starter and connection settings are present.

Because elements in this example are Strings, **StringRedisTemplate** keeps values readable in redis-cli.

### 11.2. Complete Service

~~~java
package example.redis;

import java.util.List;
import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RecentActivityStore {

    private static final String KEY = "lesson:row132:activities";

    private final StringRedisTemplate redis;

    public RecentActivityStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /** Push at head so the most recent activity comes first. */
    public long record(String activity) {
        if (activity == null || activity.isBlank()) {
            throw new IllegalArgumentException("activity must not be blank");
        }

        Long size = redis.opsForList().leftPush(KEY, activity);
        return Objects.requireNonNull(size, "Redis did not return list size");
    }

    /** Read up to limit most recent activities without removing them. */
    public List<String> latest(int limit) {
        if (limit <= 0 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }

        List<String> entries = redis.opsForList().range(KEY, 0, limit - 1);
        return entries == null ? List.of() : entries;
    }

    /** Read current position, zero-based; null if no element exists. */
    public String atIndex(long index) {
        return redis.opsForList().index(KEY, index);
    }

    /** Remove the oldest element at the tail. */
    public String removeOldest() {
        return redis.opsForList().rightPop(KEY);
    }

    /** Current number of elements. */
    public long size() {
        Long length = redis.opsForList().size(KEY);
        return length == null ? 0L : length;
    }

    /** Remove all elements whose value matches activity. */
    public long removeAll(String activity) {
        Long removed = redis.opsForList().remove(KEY, 0, activity);
        return removed == null ? 0L : removed;
    }
}
~~~

Example sequential calls:

~~~java
store.record("VIEW:42");
store.record("CLICK:42");
store.record("VIEW:42");

List<String> latest = store.latest(10);
String first = store.atIndex(0);
String oldest = store.removeOldest();
~~~

After three records, the List from head to tail is:

~~~text
[VIEW:42, CLICK:42, VIEW:42]
~~~

The latest VIEW:42 sits at the head, while the older VIEW:42 stays at the tail. **String first** receives VIEW:42. **removeOldest()** returns and removes the VIEW:42 at the tail.

To delete every VIEW:42, **removeAll("VIEW:42")** uses LREM with count = 0. That behavior makes sense when removing an activity type, but **deletes all duplicate events** if they represent separate occurrences.

### 11.3. Inspecting Data with redis-cli

After the service writes data:

~~~text
TYPE lesson:row132:activities
LLEN lesson:row132:activities
LRANGE lesson:row132:activities 0 -1
LINDEX lesson:row132:activities 0
LINDEX lesson:row132:activities -1
~~~

TYPE is **list**. Redis CLI prints String values directly because StringRedisTemplate typically uses a UTF-8 serializer.

If an application uses RedisTemplate with a different serializer, elements may appear as hard-to-read bytes. **Positional access costs of Redis Lists remain the same**, though how you inspect data changes.

### 11.4. Bounding to the 100 Most Recent Activities

To keep the list from growing indefinitely, you can add a method:

~~~java
public void recordBounded(String activity) {
    if (activity == null || activity.isBlank()) {
        throw new IllegalArgumentException("activity must not be blank");
    }

    redis.opsForList().leftPush(KEY, activity);
    redis.opsForList().trim(KEY, 0, 99);
}
~~~

This is the **keep 100 recent elements** pattern, using two separate Redis commands. If multiple producers require a strict cap and atomic push + trim, combine them via a Lua script or appropriate transaction. Every trim also pays the cost of removing elements; avoid using this pattern to prune millions of elements inside a single request.

## 12. Reading Lists Under Concurrency

A single operation like LPUSH, RPUSH, LPOP, RPOP, or LINDEX is executed atomically by Redis at the command level. However, multiple sequential calls from Spring Data Redis **do not automatically form an atomic snapshot**.

### 12.1. LLEN Followed by LINDEX May Not Reflect the Same State

~~~java
Long len = redis.opsForList().size(key);
String last = redis.opsForList().index(key, len - 1);
~~~

Between the two calls, another client may call LPOP or LTRIM, changing the length and element positions. The List might even become empty, causing index to return null.

Therefore, if the goal is simply reading the current last element, **LINDEX key -1** is simpler and saves a round trip. If you want to **pop and remove** the last element atomically, use **RPOP**.

### 12.2. LRANGE and Concurrent Updates

Each individual LRANGE sees the List state when Redis executes that command. Yet if a pagination API calls:

~~~text
LRANGE activity:list 0 9
LRANGE activity:list 10 19
~~~

and a client calls LPUSH between the two calls, old positions shift. The two pages can overlap or skip elements even though each command worked properly.

If event history requires stable IDs, stable offsets, or checkpointed consumption, consider Streams or another storage model per requirements.

### 12.3. Two Consumers Cannot Receive the Same Element from One LPOP

If a single entry sits at the head of a List and two workers both call LPOP, only one command gets that entry. The other worker gets the next entry or nil depending on queue state. That is pop atomicity.

However, if **two entries have identical values**, two workers can still both receive **the same String content** because they are two distinct List elements.

Example:

~~~text
RPUSH queue job-42 job-42
LPOP queue
LPOP queue
~~~

Both pops can return job-42, which is completely valid. Distinguish **two elements with duplicate content** from **a single element popped twice**.

## 13. Choosing Data Structures Based on Access Patterns

A Redis List excels when primary operations are **adding or removing at either end**. It is less suitable when the application constantly needs to search, update, or delete values at arbitrary positions.

| Requirement | Is Redis List Suitable? | Reason |
| --- | --- | --- |
| Simple FIFO queue | **Yes** | RPUSH + LPOP; fast operations at both ends |
| LIFO stack | **Yes** | LPUSH + LPOP or RPUSH + RPOP |
| Keep 50 most recent activities | **Yes** | LPUSH + LTRIM and small-range LRANGE |
| Allow multiple events with identical content | **Yes** | List preserves duplicate elements |
| Only need to check if an ID already exists | **Consider Set** | Membership check in a List can require O(N) scan |
| Allow only unique members | **Consider Set** | List does not deduplicate |
| Need a score-based leaderboard | **Consider Sorted Set** | List does not sort by score |
| Frequently find/update middle elements | **Often suboptimal** | LINDEX/LSET/LINSERT can be O(N) |
| Deep, stable pagination under writes | **Often unsuitable** | Offsets cost more and indices shift on insert/delete |
| Event stream with consumer groups, ack, and pending | **Consider Streams** | List pop has no built-in acknowledgement |
| Access records by ID | **Consider Hash/separate keys** | List index is not a stable identifier |

### When Should Structures Be Combined?

A system might use:

- **List** to preserve the order of IDs to process.
- **Set** to check whether an ID is already enqueued.
- **Hash** to store job details by ID.

However, when multiple Redis structures must stay consistent together, separate GET/SET/SADD/RPUSH calls introduce races and failure windows. Design appropriate scripts, transactions, or recovery mechanisms—especially when multiple Spring Boot instances run concurrently.

Do not add Sets or Hashes merely because it sounds thorough; if a List already fits your duplication and ordering needs, a simpler structure is usually easier to operate.

## 14. A Few Notes on Running on Redis Cluster

Redis Cluster partitions the keyspace into hash slots. Any **single-List-key** operation such as LPUSH, RPUSH, LPOP, LLEN, LINDEX, or LRANGE can be routed by a cluster-aware client to the node owning that key's slot.

If you use a command touching **two keys**, such as moving an element from a waiting queue to a processing queue with LMOVE, keys in Redis Cluster must satisfy the same-slot constraint.

One naming approach uses **hash tags**:

~~~text
queue:{email-worker}:waiting
queue:{email-worker}:processing
~~~

Both keys share **email-worker** inside curly braces, so Redis Cluster maps them to the same slot. That allows LMOVE between the two Lists to route cleanly.

However:

- Do not place **all** queues in the system under one global tag just to move items in one queue.
- Two keys in the same slot solve only routing/placement; they do not automatically build acknowledgements or retries.
- In Spring Data Redis, the key name serializer must preserve the hash tag syntax in the actual raw bytes.

## 15. Comprehensive Hands-on Lab

Goal: observe **ordering**, **duplicate elements**, **index access**, **position shifts**, and **the difference between pop and read**.

Practice on local Redis or a writable learning Redis environment:

~~~bash
redis-cli -h 127.0.0.1 -p 6379
~~~

In interactive mode, run each step.

### Step 1. Create a List with Duplicate Elements

~~~text
RPUSH lesson:row132:lab A B A C
LLEN lesson:row132:lab
LRANGE lesson:row132:lab 0 -1
~~~

Expect LLEN = 4; List from left to right is **[A, B, A, C]**.

### Step 2. Read Using Positive and Negative Indices

~~~text
LINDEX lesson:row132:lab 0
LINDEX lesson:row132:lab 2
LINDEX lesson:row132:lab -1
LRANGE lesson:row132:lab 1 2
~~~

Expect **A**, **A**, **C**, and slice **[B, A]**. LRANGE does not delete elements.

### Step 3. Prepend at the Head and Observe Position Shifts

~~~text
LPUSH lesson:row132:lab urgent
LRANGE lesson:row132:lab 0 -1
LINDEX lesson:row132:lab 1
~~~

The List becomes **[urgent, A, B, A, C]**. The element at index 1 is now **A**, whereas before LPUSH index 1 held **B**.

### Step 4. Delete One of Multiple Duplicate Elements

~~~text
LREM lesson:row132:lab 1 A
LRANGE lesson:row132:lab 0 -1
~~~

Only the first A is deleted; result is **[urgent, B, A, C]**. The second A remains.

### Step 5. Pop the Last Element and Update by Position

~~~text
RPOP lesson:row132:lab
LSET lesson:row132:lab 1 B2
LRANGE lesson:row132:lab 0 -1
~~~

RPOP retrieves C and removes it from the List. LSET updates B at index 1 to B2; result is **[urgent, B2, A]**.

### Step 6. Bound the Length

~~~text
LTRIM lesson:row132:lab 0 1
LRANGE lesson:row132:lab 0 -1
LLEN lesson:row132:lab
~~~

Only **[urgent, B2]** remains, length 2.

### Step 7. Test TTL

~~~text
EXPIRE lesson:row132:lab 60
TTL lesson:row132:lab
LPUSH lesson:row132:lab newest
TTL lesson:row132:lab
~~~

TTL counts down over time; LPUSH on an existing key does not extend its TTL.

### Step 8. Clean Up Keys Created in This Lab

~~~text
DEL lesson:row132:queue
DEL lesson:row132:multi
DEL lesson:row132:index
DEL lesson:row132:duplicates
DEL lesson:row132:remove
DEL lesson:row132:fifo
DEL lesson:row132:stack
DEL lesson:row132:jobs
DEL lesson:row132:insert
DEL lesson:row132:recent
DEL lesson:row132:ttl
DEL lesson:row132:activities
DEL lesson:row132:lab
~~~

These cleanup commands delete only the demo keys created for this lesson. Never run FLUSHDB or FLUSHALL to clean up a small lab because they affect unrelated data.

## 16. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Added A, B, C with LPUSH but see C, B, A | LPUSH prepends each value at the head | Use RPUSH to preserve input argument order |
| Same ID appears multiple times | Lists allow duplicate elements | Decide if duplicates are valid; enforce uniqueness separately if needed |
| LINDEX in the middle of a large List is slow | Must traverse to middle position, O(N) | Prefer operations at both ends or an ID-keyed structure |
| API returns huge payloads | LRANGE 0 -1 fetches every element | Bound ranges; avoid reading huge Lists in full |
| Pagination duplicates or skips elements | LPUSH/LPOP shifts indices between reads | Use stable IDs/cursors if consistency is required |
| LSET updates the wrong element | Indices reflect only current positions | Never use indices as long-term IDs |
| LREM deletes more records than intended | count = 0 deletes all duplicate values | Choose count and entry identification rules carefully |
| Jobs disappear when a worker fails | LPOP removes items before processing completes | Use processing list/ack workflow or Redis Streams |
| TTL disappears after List empties | Pop/trim deletes the key | Check EXISTS/TYPE and key-recreation policy |
| Reading fails with GET | Key is a Redis List, not a String | Check TYPE key and use LRANGE/LINDEX |
| Multiple Java calls behave inconsistently | Sequential commands are not atomic | Use a single suitable command, transaction, or script as needed |

## 17. Choosing Operations by Goal

When reading Spring Data Redis code that uses **opsForList()**, ask yourself:

1. **What order is desired?** If newest first at the head, LPUSH; to keep left-to-right input order, usually RPUSH.
2. **Are duplicate elements acceptable?** If not, a plain Redis List is not enough.
3. **Should reads be non-destructive?** LINDEX/LRANGE only read; LPOP/RPOP both return and remove elements.
4. **Are operations mostly at both ends or in the middle?** Both-end operations are a strength; deep random access can be O(N).
5. **How big can the list grow?** Bound size, output, and history to avoid full LRANGE scans on huge Lists.
6. **Are there multiple producers/consumers?** Single commands are atomic, but indices can shift and multi-step workflows require consistency design.
7. **Must items return if processing fails?** For reliable queues, build pending/ack/retry mechanisms or use a structure with built-in support.

**Key Takeaways:** A Redis List maintains order across insertion/removal commands and **allows duplicate values**. LPUSH, RPUSH, LPOP, and RPOP typically cost O(1) per element, while deep positional access via LINDEX/LSET, searches via LPOS/LREM, or reading large ranges can incur linear cost. In Spring Data Redis, design around real access patterns: use Lists where both-end access shines, treat indices as transient positions, and always explicitly handle duplicates, key lifetimes, and concurrency.
