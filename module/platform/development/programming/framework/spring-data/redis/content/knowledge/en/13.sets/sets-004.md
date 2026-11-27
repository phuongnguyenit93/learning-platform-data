# Counting Members and Scanning Sets with SSCAN

## 1. The Problem: How Many Members Are in a Redis Set and How Do We Iterate Over Them?

A Redis **Set** is a collection of unique elements with no fixed order. In Spring Data Redis applications, Sets are commonly used to manage lists of group participants, processed identifiers, role permissions, or tags attached to an entity. Redis deduplicates automatically based on member byte values, so adding the same element twice does not increase the member count.

Suppose a system stores the members of a Java study group:

~~~text
Redis key: learning:group:java:members
Redis data type: set

  "user:101"
  "user:205"
  "user:309"
  "user:417"
  ...
~~~

Two questions commonly arise:

1. **How many members does the group have?** Use the Redis command **SCARD**, corresponding to **SetOperations.size(key)** in Spring Data Redis.
2. **How do we process all members incrementally without pulling a huge set into RAM all at once?** Use **SSCAN**, corresponding to **SetOperations.scan(key, ScanOptions)**.

These two operations solve different problems. **SCARD** returns the number of elements in a Set at the time Redis executes the command. **SSCAN** iterates over elements batch by batch using a *cursor*, splitting the work across multiple Redis calls. SSCAN is neither a fast count nor an immutable snapshot of the data.

## 2. Reviewing the Structure and Uniqueness of a Redis Set

A Set named **learning:group:java:members** can be created via the Redis CLI:

~~~redis
SADD learning:group:java:members user:101 user:205 user:309
SCARD learning:group:java:members
~~~

The first **SADD** returns **3** if none of the three elements previously existed. **SCARD** returns **3**.

Continuing:

~~~redis
SADD learning:group:java:members user:205 user:417
SCARD learning:group:java:members
~~~

Because **user:205** already exists, Redis only adds **user:417**. The element count is now **4**.

| Command | Purpose | Typical Result |
|---|---|---|
| **SADD key member ...** | Add one or more elements | Number of newly added elements |
| **SREM key member ...** | Remove specified elements | Number of removed elements |
| **SCARD key** | Count unique elements | Integer |
| **SISMEMBER key member** | Check if an element is in the Set | 1 or 0 |
| **SMEMBERS key** | Retrieve all elements in one call | List with no guaranteed order |
| **SSCAN key cursor ...** | Iterate members across batches | Next cursor and a batch of elements |
| **SPOP key** | Retrieve and simultaneously remove selected element(s) | Set data is modified |
| **SRANDMEMBER key** | Sample element(s) without removing | Not a full traversal |

Redis Sets do not guarantee positional order like Lists and do not attach scores like Sorted Sets. Even if a `redis-cli` run appears to display members in a seemingly stable order, applications must not depend on that order for business logic or pagination.

## 3. Counting Exact Members with SCARD

### 3.1. Syntax and Output

~~~redis
SCARD key
~~~

Example:

~~~redis
DEL demo:members
SADD demo:members alice bob carol
SCARD demo:members
~~~

Output:

~~~text
(integer) 3
~~~

After removing one member:

~~~redis
SREM demo:members bob
SCARD demo:members
~~~

Output:

~~~text
(integer) 2
~~~

**SCARD** has **O(1)** time complexity per Redis documentation: the command looks up the element count maintained by Redis rather than sending all members to the application to count.

### 3.2. Nonexistent Key

~~~redis
SCARD group:does-not-exist
~~~

Redis returns **0**. From SCARD's perspective, a nonexistent Set and a Set with 0 elements both return a count of 0. In Redis, an empty Set is normally not retained as an independent data structure: when the last element is removed, the Set key may disappear.

If business logic must distinguish *"a group has never been created"* from *"a group currently has 0 members"*, a single Set key and SCARD are not enough. You may need an additional metadata key tracking group existence and define how to keep that metadata consistent.

### 3.3. Key with the Wrong Data Type

~~~redis
SET demo:not-a-set hello
SCARD demo:not-a-set
~~~

Redis returns a **WRONGTYPE** error because SCARD only applies to keys holding a Redis **Set**. This is a data-type error, unlike returning **0** when a key does not exist.

Especially when multiple modules share Redis, use clear namespaces:

~~~text
group:42:members     -> Set
group:42:metadata    -> Hash
group:42:memberCount -> String (only when separate count data is needed)
~~~

Do not let one service use **SET** to write a String to **group:42:members** while another service uses **SADD** on that exact key.

### 3.4. Which Point in Time Does SCARD Reflect?

Redis processes SCARD as an individual command. If request A calls SCARD when the Set has 100 members and request B adds a member immediately afterward, A may receive 100 while a subsequent SCARD returns 101.

Thus, SCARD provides **the exact count at the time the command executes**, not an immutable value throughout a long-lived HTTP request. You should not assume the data remains unchanged after that count.

## 4. SCARD in Spring Data Redis: SetOperations.size()

Spring Data Redis exposes **SetOperations<K, V>** via **RedisTemplate.opsForSet()**:

~~~java
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

// stringRedisTemplate is a Spring-injected bean.
SetOperations<String, String> sets =
    stringRedisTemplate.opsForSet();

Long count = sets.size("learning:group:java:members");
~~~

**size(key)** maps to Redis **SCARD**. With a synchronous template and a normal call, the result is a **Long** representing the member count.

Service example:

~~~java
package com.example.learning.membership;

import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class GroupMemberService {
    private final SetOperations<String, String> sets;

    public GroupMemberService(StringRedisTemplate redis) {
        this.sets = redis.opsForSet();
    }

    private String membersKey(String groupId) {
        if (groupId == null || groupId.isBlank()) {
            throw new IllegalArgumentException("groupId is required");
        }
        return "learning:group:" + groupId + ":members";
    }

    public long countMembers(String groupId) {
        Long count = sets.size(membersKey(groupId));
        if (count == null) {
            throw new IllegalStateException(
                "Redis did not return a cardinality result"
            );
        }
        return count;
    }

    public boolean addMember(String groupId, String userId) {
        Long added = sets.add(membersKey(groupId), "user:" + userId);
        return Long.valueOf(1L).equals(added);
    }

    public boolean removeMember(String groupId, String userId) {
        Long removed = sets.remove(membersKey(groupId), "user:" + userId);
        return Long.valueOf(1L).equals(removed);
    }
}
~~~

In this example:

- **countMembers()** uses SCARD to get the actual element count.
- **addMember()** returns **true** when a new member was actually added, **false** if that member was already present.
- **removeMember()** returns **true** when an existing member was removed.
- Both SADD/SREM and SCARD are handled by Redis command by command; there is no need to read the entire Set.

In pipeline mode or inside a queued Redis transaction, Spring Data Redis may temporarily return **null** for some operations until results are received later. The example above is for normal synchronous calls, not inside **MULTI** or a pipeline.

### Why Not Use members().size()?

~~~java
// Unsuitable when you only need the count of a large Set:
long count = sets.members("learning:group:java:members").size();
~~~

**members(key)** maps to **SMEMBERS**, downloading all data to Java. If the Set has hundreds of thousands or millions of elements, this consumes unnecessary network, RAM, and processing time. **size(key)** uses SCARD and returns only a single integer.

A useful rule: **need the count, call SCARD; need to know if one element exists, call SISMEMBER; need to traverse many elements, choose SSCAN**.

## 5. SSCAN: Cursor-Based Set Iteration

### 5.1. Redis Syntax

~~~redis
SSCAN key cursor [MATCH pattern] [COUNT count]
~~~

Where:

- **key**: Redis key name holding the Set.
- **cursor**: scan cursor for the iteration. Starts at **0**.
- **MATCH pattern**: filters returned members using Redis *glob*-style patterns.
- **COUNT count**: hints at the amount of work Redis should do per iteration, not an exact limit on the number of returned members.

Each SSCAN call returns two parts:

1. **Next cursor**: the value to pass into the next iteration.
2. **Batch members**: the list of members found in the current pass.

Example:

~~~redis
SADD demo:scan user:1 user:2 user:3 user:4 user:5
SSCAN demo:scan 0 COUNT 2
~~~

An illustrative output might look like:

~~~text
1) "5"
2) 1) "user:2"
   2) "user:4"
~~~

Then continue with the cursor returned by Redis:

~~~redis
SSCAN demo:scan 5 COUNT 2
~~~

The cursor and elements in the example only illustrate response structure. **There is no guarantee an actual run uses cursor 5, returns exactly two elements, or follows this order.** For small Sets using memory-optimized representations, Redis may even return all members in the very first pass with next cursor **0**, regardless of a small COUNT value.

### 5.2. Standard Cursor Loop

~~~text
cursor = "0"

do:
    response = SSCAN setKey cursor MATCH pattern COUNT hint
    cursor   = response.nextCursor
    process all response.members
while cursor != "0"
~~~

Important rules:

- **Initial 0** means start scanning.
- **Returned 0** means that scan cycle has finished.
- You must **process the batch just received** before concluding completion, even when the next cursor is 0.
- **An empty batch with a non-zero next cursor does not mean there is no more data.** You must keep calling SSCAN.
- The cursor is not a page offset, member ordinal, or position you can increment by adding 1. Only use the **initial 0** or the cursor Redis actually returned from the previous iteration.

Do not invent arbitrary cursors or modify a cursor to jump to "page 3". Under SCAN mechanics, the cursor holds minimal client-side traversal state; Redis does not offer a stably ordered result set like a SQL query with **ORDER BY** and **LIMIT/OFFSET**.

## 6. How SSCAN Differs from SMEMBERS and SCAN

| Aspect | SCARD | SMEMBERS | SSCAN | SCAN |
|---|---|---|---|---|
| Target | One Set | One Set | One Set | **Keys** in the database |
| Result | Count | All members | Member batches + cursor | Key name batches + cursor |
| Suitable for very large Sets | Very suitable when only count is needed | Risk of huge response | Suitable for incremental traversal | Not a tool for iterating members of a Set |
| Stable ordering | Not applicable | No | No | No |
| Filtering with MATCH | No | No | Filters **members** | Filters **key names** |
| May return duplicates in a full scan | Not applicable | In a Set, each member is unique | Possible, due to SCAN properties | Possible |

Distinguish these two commands:

~~~redis
SCAN 0 MATCH learning:group:* COUNT 100
~~~

This command searches for **Redis key names** matching **learning:group:\*** in the database.

~~~redis
SSCAN learning:group:java:members 0 MATCH user:* COUNT 100
~~~

This command iterates over **members inside one specific Set**, returning only members matching **user:\***.

**SSCAN** does not take a **TYPE** option like SCAN; the key being scanned is already a Set. If the key points to a Redis String or Hash, SSCAN cannot scan it and will fail with a wrong data type error.

## 7. MATCH: Filtering Members by Glob Pattern

**MATCH** is used by Redis to filter returned members during scanning. Patterns match according to glob rules, not Java regular expressions.

Some patterns:

| MATCH | Meaning |
|---|---|
| **user:\*** | Members starting with **user:** |
| **\*:premium** | Members with suffix **:premium** |
| **user:??** | Members starting with **user:** followed by two unit characters matching glob per Redis byte comparison |
| **user:[12]\*** | Members starting with **user:1** or **user:2** |
| **\*** | Every member |

Example:

~~~redis
SADD group:demo user:1 user:2 bot:1 guest:1 user:3
SSCAN group:demo 0 MATCH user:* COUNT 10
~~~

The command returns members Redis encountered during that scan pass matching **user:\***; to complete a full traversal, continue following the cursor until it returns 0.

### MATCH Does Not Limit How Much Data Redis Must Inspect

Redis may scan a portion of the internal structure first and then apply the pattern filter. If the match rate is low, many SSCAN iterations can return **empty batches** even though matching members still exist in later iterations.

For example, a Set has one million members, of which only one hundred start with **vip:**. Using **MATCH vip:\*** does not turn the Redis Set into a prefix query index; Redis still has to traverse the set to find matching items.

If the application frequently asks "how many VIP members are there?" or "list VIP members separately", consider maintaining a **separate Set for VIPs** or an index structure updated alongside the source data. Adding MATCH alone will not give O(1) prefix counting.

## 8. COUNT Is a Work Hint, Not an Exact Page Size

Example:

~~~redis
SSCAN group:demo 0 COUNT 100
~~~

**COUNT 100** indicates the desired amount of work per scan call. Redis may return fewer than 100, more than 100, or **0 elements**. For a Set small enough to use a compact internal encoding, Redis may return all members in a single call.

Important consequences:

1. **COUNT is not equivalent to LIMIT 100.**
2. **COUNT 100 does not guarantee 100 members per batch.**
3. **A small COUNT does not guarantee responses are strictly capped in memory or latency.**
4. **A larger COUNT usually reduces round trips**, though each pass may process more data and cause latency spikes.
5. **COUNT can be adjusted between iterations**, as long as you still pass the cursor Redis returned for that scan loop.

When choosing COUNT, monitor network latency, member size, per-batch processing time, and Redis resources. There is no single optimal COUNT value for every application.

If the application needs at most 50 exact results returned over HTTP, **COUNT 50** does not by itself produce a safe, stable 50-item page. You must design dedicated pagination and ordering or cap application-emitted items, while accounting for the limits of cursor traversal.

## 9. Guarantees and Limitations of a Full SSCAN

SSCAN is designed for incrementally iterating over a collection that can change at runtime. It **does not hold a fixed snapshot** for the entire traversal.

Under SCAN-family semantics:

- If an element **exists continuously from the start to the end of a full iteration**, Redis guarantees it appears at least once during the full scan.
- An element **may be returned multiple times**. Applications must tolerate duplicate handling or design idempotent operations.
- For elements **added or removed during the scan**, there is no guarantee whether they will appear or not.
- If the dataset **grows unboundedly** while scanning, a full iteration is not guaranteed to terminate under all conditions.
- A single **SSCAN** pass is one Redis command, but **multiple SSCAN passes** do not form an atomic transaction.

Example of two concurrent requests:

~~~text
Worker A                           Worker B
--------                           --------
SSCAN members 0
  -> cursor 27
                                   SADD members user:999
SSCAN members 27
  -> cursor 9
                                   SREM members user:101
SSCAN members 9
  -> cursor 0
~~~

You cannot conclude from this scan whether **user:999** was definitely read or **user:101** was definitely read, because they mutated during traversal.

### 9.1. Why Can a Unique Set Still Yield Duplicates During a Scan?

Set uniqueness applies to **the data state in Redis**. SSCAN, by contrast, is a sequence of steps traversing internal structures by cursor. If the hash table resizes, the traversal path may revisit an already seen member. These are two independent concepts:

- **A Set never stores two copies of the same member at the same time.**
- **An SSCAN result stream can emit the same member multiple times.**

If each element triggers sending an email, billing, or side effects, never assume "scanning a Set means processing each item once". You need idempotency or explicit processing-state tracking.

### 9.2. Is Using SSCAN to Count by Pattern Accurate?

Suppose:

~~~redis
SSCAN members 0 MATCH vip:* COUNT 100
~~~

If you sum **all batch lengths**, you may **double-count** the same member because SCAN does not promise uniqueness across passes. If you use a Java **Set** to deduplicate, memory usage grows with every observed member. If data changes during traversal, the result still does not represent a consistent snapshot.

To know the **total member count**, use SCARD. To know the **exact real-time count of VIP members**, consider a dedicated data structure or an appropriately consistent update/counting mechanism; SSCAN + MATCH cannot replace a guaranteed count.

## 10. Scanning a Set in Spring Data Redis with SetOperations.scan()

### 10.1. Core API

~~~java
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

SetOperations<String, String> sets = stringRedisTemplate.opsForSet();

ScanOptions options = ScanOptions.scanOptions()
    .match("user:*")
    .count(200)
    .build();

try (Cursor<String> cursor =
         sets.scan("learning:group:java:members", options)) {

    while (cursor.hasNext()) {
        String member = cursor.next();
        System.out.println(member);
    }
}
~~~

**SetOperations.scan(key, options)** returns a **Cursor<V>**. Spring Data Redis manages issuing multiple **SSCAN** commands as needed so the consumer can iterate seamlessly. The application only loops over the cursor; it does not manually extract string cursors at this API level.

**You must close the Cursor after use** via **try-with-resources** or an equivalent close mechanism. A Cursor can hold an underlying connection/associated resource throughout the traversal; forgetting to close it leaks resources, especially when exiting early or when an exception occurs.

### 10.2. ScanOptions Parameters

~~~java
ScanOptions options = ScanOptions.scanOptions()
    .match("user:*")
    .count(200)
    .build();
~~~

- **match("user:*")** restricts emitted members using a glob pattern.
- **count(200)** provides a work-size hint to Redis per SSCAN call.
- If neither filtering nor a COUNT hint is needed, you can use **ScanOptions.NONE**.

ScanOptions applies across several SCAN-family commands, and because we call **opsForSet().scan(key, options)**, Redis executes **SSCAN**, not database-level key SCAN.

### 10.3. Processing One Element at a Time Instead of Collecting into a List

~~~java
public void processMembers(
        String groupId,
        java.util.function.Consumer<String> consumer) {

    String key = "learning:group:" + groupId + ":members";
    ScanOptions options = ScanOptions.scanOptions()
        .count(256)
        .build();

    try (Cursor<String> cursor = sets.scan(key, options)) {
        while (cursor.hasNext()) {
            consumer.accept(cursor.next());
        }
    }
}
~~~

In the example, **sets** is a **SetOperations<String, String>** injected into the class. Each member is passed to the callback without accumulating the entire Set into a List.

However, the callback must still handle errors and bound task duration appropriately. If the callback performs slow HTTP requests or long database calls, the scan loop stretches out and may hold resources longer than desired. For large-volume jobs, it is usually better to separate **batch fetching** from **work processing**, or use a queue/stream with acknowledgment semantics when distributing work.

## 11. Complete Service Example: Counting and Scanning Group Members

The example below uses a Redis Set to manage user IDs. The service provides three functional areas: adding/removing members, counting with SCARD, and scanning with SSCAN.

~~~java
package com.example.learning.membership;

import java.util.Objects;
import java.util.function.Consumer;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisGroupMembership {
    private final SetOperations<String, String> sets;

    public RedisGroupMembership(StringRedisTemplate redis) {
        this.sets = redis.opsForSet();
    }

    private String key(String groupId) {
        if (groupId == null || groupId.isBlank()) {
            throw new IllegalArgumentException("groupId is required");
        }
        return "learning:group:" + groupId + ":members";
    }

    public boolean add(String groupId, String memberId) {
        if (memberId == null || memberId.isBlank()) {
            throw new IllegalArgumentException("memberId is required");
        }
        Long added = sets.add(key(groupId), memberId);
        return Long.valueOf(1L).equals(added);
    }

    public boolean remove(String groupId, String memberId) {
        Long removed = sets.remove(key(groupId), memberId);
        return Long.valueOf(1L).equals(removed);
    }

    public long count(String groupId) {
        return Objects.requireNonNull(
            sets.size(key(groupId)),
            "SCARD did not return a value"
        );
    }

    public void forEachMember(
            String groupId,
            Consumer<String> action) {

        ScanOptions options = ScanOptions.scanOptions()
            .count(200)
            .build();

        try (Cursor<String> cursor = sets.scan(key(groupId), options)) {
            while (cursor.hasNext()) {
                action.accept(cursor.next());
            }
        }
    }

    public void forEachMatchingMember(
            String groupId,
            String globPattern,
            Consumer<String> action) {

        ScanOptions options = ScanOptions.scanOptions()
            .match(globPattern)
            .count(200)
            .build();

        try (Cursor<String> cursor = sets.scan(key(groupId), options)) {
            while (cursor.hasNext()) {
                action.accept(cursor.next());
            }
        }
    }
}
~~~

Usage example:

~~~java
membership.add("java", "user:101");
membership.add("java", "user:205");
membership.add("java", "user:101"); // Does not increase member count.

long total = membership.count("java"); // 2, assuming no other updates.

membership.forEachMatchingMember(
    "java",
    "user:*",
    userId -> System.out.println("Found " + userId)
);
~~~

The variable **membership** represents a Spring-managed **RedisGroupMembership** bean. For real workloads, callbacks should only perform **idempotent** operations or include duplicate-handling guards, because a full scan can emit the same element multiple times.

### Why Doesn't the Service Return a List of the Whole Set?

A **List<String> getAllMembers()** method might be convenient for groups with a few dozen elements, but if the Set grows to millions of members, collecting the entire List forces the application to hold all data in RAM. Interfaces based on **Consumer**, **Iterator**, or streams/publishers fit batch work much better.

If an HTTP API only needs the total count, exposing **count()** is enough; there is no need to open a cursor. If the UI needs ordered pagination, do not promise that SSCAN yields stable pages: design dedicated sorting/indexing keys and proper paging semantics.

## 12. Reactive Scanning with ReactiveSetOperations.scan()

In Spring WebFlux applications using Reactor, Spring Data Redis also provides a reactive API:

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.ScanOptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveMemberReader {
    private final ReactiveStringRedisTemplate redis;

    public ReactiveMemberReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> count(String groupId) {
        return redis.opsForSet().size(
            "learning:group:" + groupId + ":members"
        );
    }

    public Flux<String> scan(String groupId) {
        ScanOptions options = ScanOptions.scanOptions()
            .match("user:*")
            .count(200)
            .build();

        return redis.opsForSet().scan(
            "learning:group:" + groupId + ":members",
            options
        );
    }
}
~~~

Here:

- **size(key)** returns **Mono<Long>** because the count result is an asynchronous value.
- **scan(key, options)** returns **Flux<String>**; the reactive API automatically issues SSCAN commands based on subscriber demand.
- Do not call **block()** inside a WebFlux request-handling path just to unwrap a Long or List.
- Do not call **subscribe()** manually inside a controller when you can return **Mono/Flux** for the framework to manage lifecycle.

Example service processing each member with bounded concurrency:

~~~java
public Flux<ProcessResult> processReactive(
        String groupId,
        java.util.function.Function<String, Mono<ProcessResult>> processor) {

    return scan(groupId)
        .flatMap(member -> processor.apply(member), 8);
}
~~~

**ProcessResult** is an illustrative business result DTO. The argument **8** limits how many inner publishers **flatMap** runs concurrently; it does not guarantee each SSCAN command fetches only eight members. Choose the concurrency limit based on processing cost, backpressure, and downstream capacity.

If you require each member to be processed at most once, blindly calling **distinct()** on a Flux can retain all seen elements in memory and defeat streaming benefits for huge Sets. Design idempotency at the processing layer instead of keeping every ID in memory by default.

### Reactive vs. Imperative Resource Lifecycle

With the imperative API, the **Cursor** must be closed when finished, typically via **try-with-resources**. With the reactive API, the subscriber and Reactor operators govern subscription lifecycle; you still must avoid fire-and-forget subscriptions, unbounded concurrency, or leaving a Flux unconsumed.

**Flux** helps manage application-level backpressure, yet SSCAN remains a sequence of Redis commands with variable batch sizes. Do not treat **COUNT** or backpressure as a strict guarantee of the number of elements returned per scan pass.

## 13. Fast Counting Does Not Mean Fast Scanning

Suppose a Set has **2 million members**:

~~~text
learning:group:large:members
  user:1
  user:2
  ...
  user:2000000
~~~

**SCARD** can return **2,000,000** without downloading 2 million IDs to Java. By contrast, **SSCAN** still must perform an **O(N) full iteration** if you want to traverse all members. Incremental iteration merely breaks the total work into smaller steps; it does not eliminate the O(N) cost of the entire traversal.

| Goal | Appropriate Approach | Cost / Limitation |
|---|---|---|
| Display total number of people in the group | SCARD / size() | O(1) per count |
| Check if user:101 is a member? | SISMEMBER / isMember() | Direct lookup, no scan needed |
| Export a large member list | SSCAN / scan() | Multiple passes, total cost proportional to N |
| Filter members with prefix vip: | SSCAN MATCH | Still traverses the Set; MATCH is not an index |
| Fetch all members of a very small group | SMEMBERS / members() | Single response containing all members |
| Stable pagination by join date | Separate data structure/index | Sets do not carry join-date ordering |

Never use SSCAN for problems that already have a direct command. For instance, merely to check if **user:101** has joined the group:

~~~java
Boolean present = sets.isMember(
    "learning:group:java:members",
    "user:101"
);
~~~

This command is far better than SSCANning the whole Set and searching for **user:101** in Java.

## 14. Handling Duplicate Emissions and Concurrent Changes During Scans

### 14.1. Tasks Should Be Idempotent

Suppose a worker uses SSCAN to sync members of a Redis Set to a search system. If a member appears twice during the scan, an **upsert by user ID** can be designed safely for repeated calls. By contrast, **incrementing a counter** or **sending a notification** every time a member is seen can trigger twice.

~~~text
SSCAN emits "user:101"
       |
       v
Process user:101 pass 1

SSCAN may emit "user:101" again
       |
       v
Process user:101 pass 2
~~~

If business logic requires each person to receive only one notification per campaign, use **campaign ID + member ID** as the job identifier and apply a separate acknowledgment/idempotency mechanism. Using a Redis Set as an ID source and SSCAN as the reader does not provide delivery guarantees.

### 14.2. Do Not Mutate a Set Arbitrarily While Scanning It

A job like:

~~~java
try (Cursor<String> cursor = sets.scan(key, ScanOptions.NONE)) {
    while (cursor.hasNext()) {
        String member = cursor.next();
        sets.remove(key, member);
    }
}
~~~

may work in some situations, but it mutates the data structure while traversing it, making SCAN's limitations around added/removed elements and duplicate emissions significant. It should not be treated as a strictly guaranteed "process every member exactly once and drain the Set" workflow.

If the goal is simply deleting the entire Set, **DEL key** is clearer. If you need work processing with "in-progress/completed" states, consider Redis Streams, a queue with acknowledgments, or an appropriate progress-tracking model.

### 14.3. If a Snapshot Is Strictly Required

SSCAN does not provide a snapshot. Depending on requirements, you can:

- Pause writes to the Set within a controlled window and run a full iteration, while still handling duplicates.
- Copy or move data into a separate snapshot structure before processing, after weighing memory cost and consistency.
- Use a database/query with snapshot semantics or stable ordering if that is an essential requirement.

Do not simply chain multiple SSCAN calls and claim "all members were captured accurately at one point in time". Achieving that requires a consistency mechanism outside SSCAN itself.

## 15. Can SSCAN Be Used for a Pagination API?

A frontend might ask for a URL:

~~~text
GET /groups/java/members?cursor=0&pageSize=50
~~~

Technically, the backend can forward the Redis cursor to keep scanning. However, **an SSCAN cursor is not a stable pagination token**:

- Member order is undefined.
- COUNT does not guarantee exactly 50 members.
- Different passes may return duplicate members.
- Members added/removed while the user flips pages may appear or be skipped.
- A cursor cannot be used as a page number to jump to an arbitrary page.

If the requirement is merely **streaming chunks of data for file export or batch jobs**, SSCAN can fit. If the requirement is **a stable pagination experience sorted by name or join date**, use a Sorted Set by score, a database index, or a dedicated snapshot mechanism.

When forced to expose a Redis cursor in an internal API, document its **best-effort** semantics, validate cursor format, enforce expiration, check group access permissions, and disclaim snapshot guarantees. Never reuse a cursor from one Redis key on another key, and never let clients arbitrarily tamper with cursors.

## 16. Redis Cluster: SSCAN Only Scans One Specific Set

Redis Cluster partitions keys across hash slots. A Set like **learning:group:java:members** belongs to one slot and lives on the node responsible for that slot.

When calling:

~~~redis
SSCAN learning:group:java:members 0 COUNT 200
~~~

Redis processes the members of **the specified Set key**. SSCAN does not automatically scan every Set across all master nodes in the Cluster.

Applications using Spring Data Redis with a Cluster-capable driver typically route to the node holding the key and handle redirects accordingly. When topology changes or failover happens mid-scan, be prepared for errors, retries, and possibly restarting a new scan loop; never treat a cursor as an immutable snapshot across cluster transitions.

If the data model is "one Set per group":

~~~text
learning:group:java:members   -> one Redis Set key
learning:group:spring:members -> another Redis Set key
learning:group:redis:members  -> another Redis Set key
~~~

To traverse **all groups**, you first need a list of groups or an appropriate keyspace scan mechanism. **SSCAN** on one group key only scans members inside that group.

## 17. Memory, Latency, and Operations

SSCAN is generally better suited for large datasets than SMEMBERS because the application can consume results incrementally. However, how you invoke and process it still determines operational impact.

### 17.1. Signals Worth Observing

| Signal | Meaning |
|---|---|
| Duration of a single SSCAN command | Are any batches unusually slow? |
| Total duration of a full iteration | Does job completion speed meet requirements? |
| Number of members processed | Detects job progress growing too fast or too slowly |
| Redis errors or reconnects | Do scans have to restart or recover? |
| Latency of other Redis requests | Is scanning impacting online services? |
| Worker heap memory | Are we accidentally collecting all members into a List/Set? |
| Duplicate rate and idempotent behavior | Are repeated side effects occurring? |

When a job scans a huge Set, do not simply crank COUNT very high to reduce round trips. You may need application-side concurrency limits, sensible processing batch sizes, and to avoid running multiple concurrent full scans on the same key.

### 17.2. Choosing COUNT Intentionally

Suppose a service needs to scan a large Set to sync members:

~~~java
ScanOptions options = ScanOptions.scanOptions()
    .count(500)
    .build();
~~~

**500 is just an initial baseline value.** Tune it based on member size, network latency, and downstream processing time. If each member triggers a remote API call taking 100 ms, the bottleneck is much more likely the downstream system than the number of SSCAN calls.

### 17.3. Do Not Hold a Cursor Across Multiple HTTP Requests

A Spring Data Redis **Cursor** is tied to a data-access lifecycle. Do not store it in a singleton service across multiple threads, do not serialize the Cursor object directly into a response, and do not keep it open for minutes waiting for a user to click "Next Page".

If a long-running job is needed, manage it at the worker layer with an explicit resource lifecycle, or persist independent job state. If stable API pagination is needed, use a data model suited for pagination.

## 18. Common Mistakes

### Mistake 1: Using SMEMBERS to Get the Count

~~~java
int count = sets.members(key).size();
~~~

This downloads the entire Set before counting. With large datasets, it spikes network and memory usage. Replace with:

~~~java
Long count = sets.size(key);
~~~

### Mistake 2: Stopping Scan on an Empty Batch

~~~text
SSCAN key 0 MATCH vip:* COUNT 10
  -> cursor="18", members=[]
~~~

Stopping here can miss matching members appearing in later passes. Terminate only when **next cursor = 0**.

### Mistake 3: Treating COUNT as Page Size

**COUNT 50** does not promise returning 50 elements and does not provide stable pagination. Do not rely on it to guarantee a UI response of exactly 50 members.

### Mistake 4: Forgetting to Close the Cursor

~~~java
Cursor<String> cursor = sets.scan(key, ScanOptions.NONE);
// Partially iterate and return without closing: may leak resources.
~~~

Use **try-with-resources** so it closes even on early return or exception.

### Mistake 5: Believing SSCAN Never Emits Duplicates

A Redis Set holds no duplicate members, yet a full scan result may emit the same member more than once. Handle idempotently or deduplicate in a controlled manner.

### Mistake 6: Using MATCH for Fast Conditional Counting

SSCAN MATCH still traverses the Set; summing batch counts can double-count and is not a snapshot. If you need fast counts by category, model separate subsets or dedicated counters.

### Mistake 7: Confusing SCAN and SSCAN

~~~redis
SCAN 0 MATCH group:*
~~~

This searches for keys. To scan members of a Set:

~~~redis
SSCAN group:java:members 0
~~~

### Mistake 8: Treating SCARD and SSCAN as the Same Snapshot

~~~text
SCARD key -> 1000
SSCAN key ... -> reads members over several seconds
~~~

If another request runs SADD/SREM in between, the scanned member count may not match the initial SCARD. This is a difference in observation time and scan semantics, not necessarily a serializer bug.

### Mistake 9: Failing to Check Data Type and Serializers

SetOperations requires the Redis key to hold type **set**. Another service might use **SET** on the same key or use an incompatible serializer, causing WRONGTYPE or undecodable Java data.

### Mistake 10: Huge HTTP Responses Despite Using SSCAN

If a service scans batch by batch but still **collects** all members into a List and returns one giant JSON payload, memory and response size still scale with N. Streaming only helps when the consuming layer also processes in small chunks or enforces clear limits.

## 19. Self-Check Exercises

### Exercise 1 — Counting After Adding Duplicates

Redis runs:

~~~redis
DEL exercise:set
SADD exercise:set a b c
SADD exercise:set b c d
SCARD exercise:set
~~~

**Answer:** **4**, because only a, b, c, d are unique members.

### Exercise 2 — Nonexistent Key

~~~redis
SCARD unknown:key
~~~

**Answer:** **0**. If the key has type String instead of Set, the command does not return 0; it fails with a wrong data type error.

### Exercise 3 — Empty Batch with Non-Zero Cursor

One pass:

~~~text
SSCAN key 0 MATCH premium:* COUNT 5
  -> cursor="37"
  -> members=[]
~~~

**Question:** Should we stop scanning?

**Explanation:** No. Use cursor **37** for the next pass and continue until Redis returns next cursor **0**.

### Exercise 4 — COUNT = 10

**Question:** Does **SSCAN key 0 COUNT 10** always return exactly 10 members?

**Explanation:** No. COUNT is a work hint, not an exact limit. Small Set structures may even be returned in full in a single pass.

### Exercise 5 — Counting by Prefix

A Set contains 100,000 members, of which 500 start with **vip:**. Can **SCARD key** directly return 500?

**Explanation:** No, SCARD returns the total member count of the Set. **SSCAN MATCH vip:\*** can find matching members, though without fast counting or snapshot guarantees. If prefix queries are frequent, consider maintaining a dedicated Set for VIP members.

### Exercise 6 — Scanning During Concurrent Writes

A job is running SSCAN while a request adds **user:999**. Is the job guaranteed to see **user:999** in this scan?

**Explanation:** No. Members added while a scan is in progress may or may not appear. A full scan only provides limited guarantees for elements continuously present from start to finish.

### Exercise 7 — Closing the Cursor

Which snippet manages resources better?

~~~java
// A:
Cursor<String> cursor = sets.scan(key, options);
while (cursor.hasNext()) {
    handle(cursor.next());
}

// B:
try (Cursor<String> cursor = sets.scan(key, options)) {
    while (cursor.hasNext()) {
        handle(cursor.next());
    }
}
~~~

**Explanation:** **B** closes the Cursor even if `handle` throws an error or the loop exits early.

### Exercise 8 — Why Does count() Differ from Processed Item Count?

**Scenario:** SCARD before a job returns 10,000. After a full SSCAN, the system logs 10,008 callback invocations.

**Explanation:** There may be duplicate member emissions during the scan, or concurrent Set updates. Do not strictly compare the two numbers and claim Redis miscounted; account for observation timing, duplicates, and mutations.

### Exercise 9 — Choosing the Right Command

**Requirement:** An API only needs to return **true** if **user:100** belongs to group **java**.

**Explanation:** Use **SISMEMBER** via **SetOperations.isMember(key, member)**. Do not use SCARD or a full SSCAN to check a single member.

### Exercise 10 — Pagination Problem

**Requirement:** The UI displays newest members by join date, allowing stable pages 1, 2, 3.

**Explanation:** Sets and SSCAN have no join-date ordering and do not guarantee stable pagination. Store ordering information in another structure (such as a Sorted Set or an appropriate database/index).

## 20. References

- [Redis — SCARD](https://redis.io/docs/latest/commands/scard/)
- [Redis — SSCAN](https://redis.io/docs/latest/commands/sscan/)
- [Redis — SCAN and cursor iteration guarantees](https://redis.io/docs/latest/commands/scan/)
- [Redis — Sets](https://redis.io/docs/latest/develop/data-types/sets/)
- [Spring Data Redis — SetOperations API](https://docs.spring.io/spring-data-redis/docs/current/api/org/springframework/data/redis/core/SetOperations.html)
- [Spring Data Redis — ReactiveSetOperations API](https://docs.spring.io/spring-data-redis/docs/current/api/org/springframework/data/redis/core/ReactiveSetOperations.html)

## 21. Summary

For Redis Sets, **SCARD** is the fast, direct way to count unique members. In Spring Data Redis, the corresponding operation is **SetOperations.size(key)**. If you only need the count, do not load the entire Set with SMEMBERS or SSCAN and count in Java.

**SSCAN** is meant for incrementally scanning members of a Set via a cursor. Start at cursor **0**, process each received batch, and continue with the next cursor until Redis returns **0**. **MATCH** filters members by glob pattern; **COUNT** is only a hint, not a fixed page size. With imperative Spring Data Redis, use **SetOperations.scan(key, ScanOptions)** and always **close the Cursor**; with the reactive API, use **ReactiveSetOperations.scan(...)** to obtain a Flux.

Key takeaway for production use: **SSCAN is not a snapshot and may emit duplicate members**. Results can change if the Set is mutated during the scan, and a scan pass does not guarantee side effects execute once. Choose SCARD for counts, SISMEMBER for membership checks, SSCAN for incremental batch traversal, and another data model when ordering or stable pagination is required.
