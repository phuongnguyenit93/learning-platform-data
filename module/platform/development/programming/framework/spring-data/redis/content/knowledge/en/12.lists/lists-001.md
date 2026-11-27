# Adding and Removing Elements at Both Ends of a List in Spring Data Redis

**Redis List** is a data structure that stores an ordered sequence of elements, allowing elements to be added and removed at the **left end (head)** or **right end (tail)**. In Spring Data Redis, these operations are primarily provided through `ListOperations<K, V>` and the `leftPush`, `rightPush`, `leftPop`, and `rightPop` methods of `RedisTemplate`/`StringRedisTemplate`.

With just four basic operations, an application can build a FIFO queue, a LIFO stack, or a deque (double-ended queue). However, when a Redis List is used for tasks with multiple producers/consumers, it is necessary to clearly understand element ordering, how empty lists are handled, blocking operations, TTL, atomicity, and the limitations of the work-processing model.

## 1. What Is a Redis List?

A Redis List is an ordered sequence of binary string values. Redis preserves the **order between elements**, accepts **duplicate values**, and allows adding/removing at both ends without shifting the entire sequence the way a typical array does.

For example, a list named `shop:dev:jobs:email` contains three elements:

```text
Redis key: shop:dev:jobs:email

LEFT / HEAD                                RIGHT / TAIL
    |                                          |
    v                                          v
  +-------------+-------------+----------------+
  | send-mail-1 | send-mail-2 | send-mail-3    |
  +-------------+-------------+----------------+
      index 0       index 1       index 2
```

The elements in the diagram are shown from left to right in the order of `LRANGE key 0 -1`.

Unlike a Redis Set, a List does not automatically deduplicate elements. Unlike a Sorted Set, a Redis List does not sort by score. If the same string `send-mail-1` is added twice, the list can contain two equal elements at two different positions.

### A Single Redis Key with the List Data Type

The Redis key is `shop:dev:jobs:email`; `send-mail-1` and `send-mail-2` are **elements inside the List**. There is no separate Redis key for each element.

```redis
TYPE shop:dev:jobs:email
```

If the key holds a Redis List, the command returns:

```text
list
```

You cannot use `GET shop:dev:jobs:email` to read a list. `GET` is for Redis strings; for a List, commands such as `LRANGE`, `LINDEX`, `LPOP`, or `RPOP` are needed.

## 2. Four Fundamental Commands: `LPUSH`, `RPUSH`, `LPOP`, `RPOP`

Redis names commands by the direction of the operation:

| Redis Command | Meaning | Spring Data Redis |
|---|---|---|
| `LPUSH key value` | Add an element to the **left / head** | `opsForList().leftPush(key, value)` |
| `RPUSH key value` | Add an element to the **right / tail** | `opsForList().rightPush(key, value)` |
| `LPOP key` | Retrieve and **remove** the element on the left | `opsForList().leftPop(key)` |
| `RPOP key` | Retrieve and **remove** the element on the right | `opsForList().rightPop(key)` |

The letter **L** stands for *left*, **R** stands for *right*, and **PUSH/POP** have the same meaning as push/pop operations in a stack or deque.

Operations on one end of a List have an average time complexity of **O(1) per element**. Therefore, Redis Lists are well suited for workloads that frequently add/remove elements at both ends. Operations that traverse a range or search for an element in the middle of a list have a different cost, depending on the number of elements to process.

### 2.1. `RPUSH`: Appending to the Tail

Starting with a key that does not exist yet:

```redis
RPUSH demo:list:ends A
RPUSH demo:list:ends B
RPUSH demo:list:ends C
LRANGE demo:list:ends 0 -1
```

Result:

```text
1) "A"
2) "B"
3) "C"
```

Progression:

```text
Initial : []
RPUSH A : [A]
RPUSH B : [A, B]
RPUSH C : [A, B, C]
```

Redis `RPUSH` returns the **new length of the List**. When the key does not exist yet, Redis creates a new List. If the key exists but belongs to an incompatible Redis data type, Redis reports `WRONGTYPE`.

### 2.2. `LPUSH`: Prepending to the Head

Continuing from `[A, B, C]`:

```redis
LPUSH demo:list:ends X
LRANGE demo:list:ends 0 -1
```

Result:

```text
1) "X"
2) "A"
3) "B"
4) "C"
```

`LPUSH X` turns the list into `[X, A, B, C]`. If you call `LPUSH Y` next, the new list is `[Y, X, A, B, C]`.

### 2.3. `LPOP`: Retrieving and Removing the First Element

```redis
LPOP demo:list:ends
LRANGE demo:list:ends 0 -1
```

If the list is `[X, A, B, C]`, `LPOP` returns `"X"` and the list becomes:

```text
[A, B, C]
```

This is a **consuming operation**: the value is removed from the List in the same command. If you only want to inspect the first element while keeping the list intact, use `LINDEX key 0` or the `index(key, 0)` API.

### 2.4. `RPOP`: Retrieving and Removing the Last Element

```redis
RPOP demo:list:ends
LRANGE demo:list:ends 0 -1
```

If the list is `[A, B, C]`, `RPOP` returns `"C"` and the list becomes `[A, B]`.

### 2.5. Visualizing All Four Operations Together

```text
             LPUSH                 RPUSH
               |                     |
               v                     v
         +-----+-----+-----+-----+-----+
HEAD --> |  A  |  B  |  C  |  D  |  E  | <-- TAIL
         +-----+-----+-----+-----+-----+
               ^                     ^
               |                     |
              LPOP                  RPOP

LPUSH X -> [X, A, B, C, D, E]
RPUSH X -> [A, B, C, D, E, X]
LPOP    -> returns A, list becomes [B, C, D, E]
RPOP    -> returns E, list becomes [A, B, C, D]
```

Each line above illustrates **a single operation** on the initial list, not four operations executed sequentially.

## 3. Adding Multiple Elements: Ordering of `LPUSH` and `RPUSH`

Redis allows adding multiple elements in a single command:

```redis
RPUSH demo:list:many A B C
LRANGE demo:list:many 0 -1
```

The result is `[A, B, C]`, because `RPUSH` adds each element to the right in order.

A common point of confusion lies in `LPUSH`:

```redis
LPUSH demo:list:many X Y Z
LRANGE demo:list:many 0 -1
```

Suppose the list before the command is `[A, B, C]`. Redis pushes `X`, then `Y`, then `Z` onto the head in sequence, so the result is:

```text
[Z, Y, X, A, B, C]
```

The values in the `LPUSH key X Y Z` command appear in **reverse order** when viewed from left to right in the list.

This is also true when an application uses the Spring Data Redis methods:

```java
Long size = redis.opsForList().rightPushAll(
        "demo:list:many",
        List.of("A", "B", "C")
);

Long newSize = redis.opsForList().leftPushAll(
        "demo:list:many",
        List.of("X", "Y", "Z")
);
```

`leftPushAll` does not mean Spring automatically reverses the input list to preserve display order. You must rely on `LPUSH` semantics.

If you want an empty list to have the order `[A, B, C]`, `rightPushAll(key, List.of("A","B","C"))` is the intuitive approach. If you want to push multiple elements to the head while keeping the order `A, B, C` when reading from the left, think carefully about the argument order and use `LPUSH` deliberately.

## 4. Configuring Spring Data Redis and Using `ListOperations`

Spring Boot 3.x example using the starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Connecting to standalone Redis in a development environment:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
```

When auto-configuration conditions match, Spring Boot creates `RedisConnectionFactory` and `StringRedisTemplate`. There is no need to instantiate a new connection in every service.

`StringRedisTemplate` uses string serializers for keys and values, which is convenient for examples demonstrating List commands. In practice, if elements are Java objects, you can use `RedisTemplate<String, Task>` with a JSON value serializer or an appropriate format; in that case, the List is still a **Redis List**, while each List element holds the serialized byte payload of the object.

### Obtaining `ListOperations` from the Template

```java
import org.springframework.data.redis.core.ListOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class QueueService {
    private final ListOperations<String, String> listOps;

    public QueueService(StringRedisTemplate redis) {
        this.listOps = redis.opsForList();
    }
}
```

`ListOperations<K,V>` uses keys of type `K` and values of type `V` according to the template configuration. With `StringRedisTemplate`, both are `String`.

Primary operations:

```java
Long count = listOps.leftPush(key, value);
Long count2 = listOps.rightPush(key, value);

String first = listOps.leftPop(key);
String last = listOps.rightPop(key);
```

`leftPush` and `rightPush` return the **List length after insertion** (as a `Long`). `leftPop` and `rightPop` return the **popped value**, or `null` if no element is available during a non-blocking read. Inside a pipeline/transaction, the direct return value of some calls may be `null` because the framework returns results later.

## 5. Complete Java Example: A Deque Supporting Push/Pop at Both Ends

We build a service that manages a notification list under the `shop:dev:notifications:` namespace.

```java
package com.example.shop.redis;

import java.util.List;
import java.util.Objects;
import org.springframework.data.redis.core.ListOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationDeque {

    private final ListOperations<String, String> lists;

    public NotificationDeque(StringRedisTemplate redis) {
        this.lists = redis.opsForList();
    }

    private String key(String userId) {
        Objects.requireNonNull(userId, "userId");
        if (!userId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid userId");
        }
        return "shop:dev:notifications:" + userId;
    }

    public Long addFirst(String userId, String notificationId) {
        Objects.requireNonNull(notificationId, "notificationId");
        return lists.leftPush(key(userId), notificationId);
    }

    public Long addLast(String userId, String notificationId) {
        Objects.requireNonNull(notificationId, "notificationId");
        return lists.rightPush(key(userId), notificationId);
    }

    public String removeFirst(String userId) {
        return lists.leftPop(key(userId));
    }

    public String removeLast(String userId) {
        return lists.rightPop(key(userId));
    }

    public List<String> snapshot(String userId) {
        List<String> items = lists.range(key(userId), 0, -1);
        return items == null ? List.of() : items;
    }
}
```

Assuming the key does not exist initially:

```java
deque.addLast("u42", "n1");  // [n1]
deque.addLast("u42", "n2");  // [n1, n2]
deque.addFirst("u42", "n0"); // [n0, n1, n2]

String first = deque.removeFirst("u42"); // "n0"
String last = deque.removeLast("u42");   // "n2"

List<String> rest = deque.snapshot("u42"); // ["n1"]
```

For `snapshot`, `range(key, 0, -1)` returns all elements in the current order of the list. The code above returns an empty list if the direct result is `null`; in production code, avoid calling `snapshot` this way inside a pipeline/transaction, where `null` may mean **the result has not been returned yet**, rather than an empty list.

This example stores **notification IDs** instead of long notification bodies or sensitive data. The content can be fetched from the corresponding data source when needed. Storing IDs generally reduces element size and keeps the key structure easier to manage.

## 6. Designing a FIFO Queue and a LIFO Stack

The same Redis List can implement different access patterns. **FIFO** (*first in, first out*) means the element added first is retrieved first. **LIFO** (*last in, first out*) means the element added most recently is retrieved first.

### 6.1. FIFO: Add at the Right, Remove from the Left

```text
Producer: RPUSH / rightPush
Consumer: LPOP / leftPop

RPUSH A -> [A]
RPUSH B -> [A, B]
RPUSH C -> [A, B, C]

LPOP   -> A ; list becomes [B, C]
LPOP   -> B ; list becomes [C]
LPOP   -> C ; list becomes []
```

Java:

```java
public Long enqueue(String queueKey, String taskId) {
    return redis.opsForList().rightPush(queueKey, taskId);
}

public String dequeue(String queueKey) {
    return redis.opsForList().leftPop(queueKey);
}
```

Another equally valid FIFO pattern is **`LPUSH` + `RPOP`**, provided the producer and consumer agree consistently on the two ends.

### 6.2. LIFO: Add and Remove at the Same End

```text
Producer: LPUSH / leftPush
Consumer: LPOP / leftPop

LPUSH A -> [A]
LPUSH B -> [B, A]
LPUSH C -> [C, B, A]

LPOP   -> C ; list becomes [B, A]
LPOP   -> B ; list becomes [A]
LPOP   -> A ; list becomes []
```

Java:

```java
public Long push(String stackKey, String item) {
    return redis.opsForList().leftPush(stackKey, item);
}

public String pop(String stackKey) {
    return redis.opsForList().leftPop(stackKey);
}
```

`RPUSH` + `RPOP` is also a LIFO stack. Neither the left nor the right end is inherently "correct" for FIFO/LIFO; **the pair of operations** determines the behavior.

### Quick Selection Table

| How to Add | How to Remove | Behavior |
|---|---|---|
| `RPUSH` | `LPOP` | FIFO |
| `LPUSH` | `RPOP` | FIFO |
| `LPUSH` | `LPOP` | LIFO |
| `RPUSH` | `RPOP` | LIFO |
| Both ends | Both ends | Deque, depending on business logic |

For example, a task queue that processes requests in the order received should use a consistent FIFO model. Conversely, an action history list with the newest items at the front can use `LPUSH`, be read via `LRANGE` or `LINDEX`, and only delete items when necessary, rather than using `LPOP` which immediately erases the history.

## 7. Popping from an Empty List or a Missing Key

A Redis List key **does not need to be pre-created** before calling `LPUSH` or `RPUSH`. If it does not exist yet, the push command automatically creates a List key with the first element.

For a non-existent key or an empty list, `LPOP`/`RPOP` returns nil:

```redis
LPOP demo:list:missing
RPOP demo:list:missing
```

With `StringRedisTemplate` in a normal call:

```java
String value = redis.opsForList().leftPop("demo:list:missing");
// value == null
```

Returning `null` lets the consumer know **no element is currently available**, as opposed to a connection error or exception. The consumer can return a "queue empty" result, wait for the next invocation, or use a blocking operation if appropriate for the business logic.

A Redis List does not persist an empty key of length 0 as an independent entity. When `LPOP`/`RPOP` removes the last element, Redis deletes the List key altogether. Therefore:

```redis
RPUSH demo:list:single only-one
LPOP demo:list:single
EXISTS demo:list:single
```

`EXISTS` returns `0` after the last element is popped, assuming no other writer adds back to the key.

### Distinguishing `null` in a Pipeline or Transaction

In Spring Data Redis, if commands are **queued** in a pipeline or transaction, the method may return `null` even though Redis will execute the command later. In that case, `null` at the call site must not be interpreted as an empty queue. You need to retrieve the results from the corresponding pipeline/transaction mechanism.

## 8. Inspecting Elements at Both Ends Without Removing Them

`leftPop` and `rightPop` are **destructive** operations: after returning the value, the element is no longer in the list. If you only want to inspect it, use `LINDEX`:

```redis
RPUSH demo:list:peek A B C

LINDEX demo:list:peek 0
# "A"

LINDEX demo:list:peek -1
# "C"
```

In Spring Data Redis:

```java
String first = redis.opsForList()
        .index("demo:list:peek", 0);

String last = redis.opsForList()
        .index("demo:list:peek", -1);
```

Index `0` is the leftmost element, and `-1` is the rightmost element. Redis allows negative indices to count from the tail of the list. An out-of-range index returns nil in Redis, which normally becomes `null` in the corresponding Java API.

Reading a snapshot of multiple elements:

```java
List<String> full = redis.opsForList()
        .range("demo:list:peek", 0, -1);

List<String> firstThree = redis.opsForList()
        .range("demo:list:peek", 0, 2);
```

`range(key, start, end)` uses a range that is **inclusive at both ends**. `range(key, 0, 2)` returns at most the first three elements. The `LRANGE` command is a read-only operation and does not remove elements.

`LLEN` checks the length:

```java
Long size = redis.opsForList().size("demo:list:peek");
```

Normally `size` returns `0` if the key does not exist. When running inside a pipeline/transaction, the immediate return value can still be `null`.

## 9. Popping Multiple Elements in a Single Pop

Modern versions of Redis and Spring Data Redis support popping multiple elements from one end, such as Redis `LPOP key count` and `RPOP key count`.

```redis
RPUSH demo:list:batch A B C D E
LPOP demo:list:batch 2
```

Result:

```text
1) "A"
2) "B"
```

The list becomes `[C, D, E]`.

Correspondingly in Spring Data Redis 3.x:

```java
List<String> firstTwo = redis.opsForList()
        .leftPop("demo:list:batch", 2);

List<String> lastTwo = redis.opsForList()
        .rightPop("demo:list:batch", 2);
```

With `rightPop(key, 2)`, the returned order follows the direction of popping from right to left; do not assume the result always preserves the original `LRANGE` order.

For example, given the list `[A, B, C, D]`:

```text
LPOP key 2 -> [A, B], list becomes [C, D]
RPOP key 2 -> [D, C], list becomes [A, B]
```

Each multi-element pop command is a single Redis operation; there is no need to split it into multiple `LPOP` calls if you genuinely need to retrieve up to a batch in one command. Still, popping multiple elements **removes** them from the list at execution time.

These overloads depend on the library version and the Redis server; when working with legacy systems, verify the actual Spring Data Redis API and the Redis commands supported by the server.

## 10. Blocking Pop: Waiting for Elements Instead of Polling Continuously

`LPOP` and `RPOP` return immediately when the list is empty. If a worker continuously calls `LPOP` every few milliseconds, it generates many idle requests and wastes CPU/network resources.

Redis provides `BLPOP` and `BRPOP` to **wait until an element is available**, up to a specified timeout.

```redis
BLPOP demo:list:blocking 5
```

This command waits for up to about 5 seconds. If a producer executes in time:

```redis
RPUSH demo:list:blocking task-101
```

`BLPOP` can wake up and return **both the key name and the value**:

```text
1) "demo:list:blocking"
2) "task-101"
```

Redis returns the key name because native `BLPOP` can wait on multiple keys. When calling `leftPop` through `ListOperations` with a single key, the application receives the corresponding **value** directly.

### Spring Data Redis: `leftPop(key, timeout)` and `rightPop(key, timeout)`

```java
import java.time.Duration;

String task = redis.opsForList().leftPop(
        "demo:list:blocking",
        Duration.ofSeconds(5)
);
```

In Spring Data Redis 3.x, the overload accepting `Duration` supports the corresponding blocking pop call. If no item arrives within the timeout, the method normally returns `null`. Redis/native clients may differ in timeout resolution or unit conversion across versions; you should use an explicit finite timeout.

A FIFO consumer can use:

```java
public String awaitNextJob(String queueKey) {
    return redis.opsForList().leftPop(
            queueKey, Duration.ofSeconds(5));
}
```

To ensure FIFO, the producer must insert using `rightPush` or `rightPushAll`. If the producer uses `leftPush` instead, a `leftPop` consumer will produce LIFO semantics.

### What Happens When Multiple Consumers Wait Simultaneously?

Suppose two workers both call blocking pop on the same Redis List. When an element is added, Redis delivers that element to **only one** successful pop operation; it does not let both workers retrieve the exact same element in two separate single pop commands.

However, this only prevents an element from being popped twice while it is still in the list. It **does not guarantee** that the task is processed successfully: if the worker receives the item and then crashes before saving the result, the item has already been deleted.

### Blocking Pop Consumes Waiting Resources

In a synchronous Spring MVC/Jedis application, a blocking pop can hold a thread and a connection for the entire wait duration. With many waiting workers, you must size the connection pool, thread count, and timeout properly; do not open thousands of indefinite blocking pops without capacity planning.

In a reactive application, choose an appropriate driver and API to avoid blocking the event loop. Do not call synchronous blocking APIs directly on the WebFlux event loop.

## 11. Java Consumer Example with a Finite Timeout

A simple service receiving tasks from a Redis List:

```java
package com.example.jobs;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class EmailTaskQueue {

    private static final String KEY = "shop:dev:jobs:email";

    private final StringRedisTemplate redis;

    public EmailTaskQueue(StringRedisTemplate redis) {
        this.redis = redis;
    }

    // Producer: append to tail (FIFO).
    public Long submit(String taskId) {
        return redis.opsForList().rightPush(KEY, taskId);
    }

    // Consumer: take from head, up to 3 seconds.
    public String takeNext() {
        return redis.opsForList().leftPop(
                KEY, Duration.ofSeconds(3));
    }
}
```

A worker can call:

```java
String taskId = queue.takeNext();

if (taskId == null) {
    // Wait timed out; no new task is currently available.
    return;
}

// Illustrative example only. Real processing requires
// managing retries, idempotency, and completion status.
process(taskId);
```

This is a **simple** consumer pattern. The element is removed from Redis as soon as `takeNext` returns, so if `process(taskId)` fails, the Redis List does not automatically put the task back. For critical work, you must add processing acknowledgment, retry, and failure-recovery mechanisms.

If a producer wants to insert a priority task at the **head** of the list, `leftPush` can do that, but processing order is no longer strictly FIFO. When a system needs a priority queue, consider an appropriate data structure instead of mixing multiple priority levels into a single List without a clear contract.

## 12. Atomicity: Each Push/Pop Is an Atomic Command

`LPUSH`, `RPUSH`, `LPOP`, and `RPOP` are single Redis operations. On the Redis server executing commands, a pop command will not return the same element to two consumers across two concurrent pops.

For example, two workers popping from the list `[task-1]`:

```text
Worker A: LPOP jobs -> "task-1"
Worker B: LPOP jobs -> nil

Or if B arrives first:
Worker B: LPOP jobs -> "task-1"
Worker A: LPOP jobs -> nil
```

There is no state in which both successful pop commands retrieve the same `task-1` element from a single occurrence in the list. This is because popping and deleting happen in one command.

### Avoid Checking `LLEN` Before Calling `LPOP`

Seemingly reasonable code:

```java
Long size = redis.opsForList().size(key);

if (size != null && size > 0) {
    return redis.opsForList().leftPop(key);
}
return null;
```

There is a **race condition**: after reading `LLEN` but before `LPOP`, another worker may have popped the last element. In that case, `leftPop` still returns `null`. Conversely, after `LLEN` reports 0, a producer may push an element immediately afterward.

Instead of calling `LLEN` first to "guarantee an element exists," call `leftPop` directly and handle `null`. `LLEN` is suitable for observing length, not as a mechanism to reserve an element for a worker.

### Pushing and Popping at Both Ends Does Not Create a Business Transaction

If a service both calls `RPUSH` on a queue and writes to a relational database, those two operations reside in two separate systems. Redis does not automatically guarantee that both succeed or both roll back. Similarly, a worker that pops and then handles an HTTP request can fail after popping.

The atomicity of **a single Redis command** does not equate to application-wide exactly-once processing.

## 13. When In-Flight Tasks Must Be Retained: Moving Elements to Another List

`LPOP`/`RPOP` immediately deletes an item from the List. For a task queue where silent loss is unacceptable, a classic pattern is to atomically move an item from a **pending** List to a **processing** List, and only remove it from processing once it has been handled successfully.

Modern Redis provides the `LMOVE` command:

```redis
LMOVE jobs:pending jobs:processing LEFT RIGHT
```

It pops the leftmost element of `jobs:pending` and pushes it onto the right side of `jobs:processing` in **a single atomic command on one Redis server**.

```text
Before:
pending:    [task-1, task-2, task-3]
processing: []

LMOVE pending processing LEFT RIGHT

After:
pending:    [task-2, task-3]
processing: [task-1]
```

Spring Data Redis provides the `ListOperations.move(...)` API in supported versions:

```java
import org.springframework.data.redis.connection.RedisListCommands.Direction;

String task = redis.opsForList().move(
        "shop:dev:jobs:pending",
        Direction.LEFT,
        "shop:dev:jobs:processing",
        Direction.RIGHT
);
```

When you need to **wait** for an element before moving it, Redis supports `BLMOVE` (and Spring Data Redis supports a move overload with a timeout in the corresponding versions). Exact API names and availability depend on the Redis, Spring Data Redis, and driver versions.

### Why Is This Still Not a Complete Reliable Queue?

Moving from pending to processing reduces the risk of "worker crashes right after pop and nobody knows where the item went," but essential problems remain to be solved:

1. **Acknowledgment:** how do you know which task has finished processing and may be removed from processing?
2. **Recovery:** if a worker crashes, what scans stuck tasks in processing and moves them back to pending?
3. **Ownership/timeout:** which worker is currently handling the task, and after how long can it be retried?
4. **Idempotency:** if the task finishes processing but the ACK fails, will a retry trigger side effects a second time?
5. **Duplicate payloads:** `LREM` matches by value and can delete the wrong element if multiple tasks share identical payloads; use unique IDs and controlled ACK rules.

With Redis Cluster, the `pending` and `processing` keys used by `LMOVE` must belong to the **same hash slot** to support atomic multi-key operations, for example:

```text
shop:dev:jobs:{email}:pending
shop:dev:jobs:{email}:processing
```

Both use the hash tag `email` so they map to the same slot. Do not use a single overly broad hash tag for every queue in the system if doing so concentrates load onto a single node.

When you need consumer groups, pending-message tracking, and built-in ACK/reclaim mechanisms, **Redis Streams** with consumer groups are usually a better fit than plain Redis Lists. Redis Lists remain useful for simple queues, deques, and structures requiring fast operations at both ends.

## 14. TTL and the Lifecycle of a Redis List

Redis TTL applies at the **key level**, not to individual List elements. When you set:

```redis
RPUSH demo:list:ttl A B C
EXPIRE demo:list:ttl 60
```

the entire Redis List will expire after roughly 60 seconds. Redis does not automatically give `A` a 60-second TTL while giving `B` a 120-second TTL inside the same key under the standard TTL model.

### Do Normal Push/Pop Operations Preserve TTL?

`LPUSH`/`RPUSH` commands update the contents **within the same List key**, and generally **do not clear an existing TTL** on the key while the key still exists. Conversely, if the key ceases to exist because it expired or its last element was popped, a new `RPUSH` recreates the key **without a TTL** until the application sets an expiry again.

Example:

```redis
RPUSH demo:list:ttl one
EXPIRE demo:list:ttl 120
RPUSH demo:list:ttl two
TTL demo:list:ttl
```

`TTL` still reflects the remaining time; it is not reset to 120 seconds by `RPUSH`.

However, if both elements are removed one by one with `LPOP`, the key disappears. A subsequent `RPUSH` creates a new key, and that new key does not automatically inherit the previous expiry.

### TTL in Spring Data Redis

```java
String key = "shop:dev:notifications:u42";

redis.opsForList().rightPush(key, "n101");
redis.expire(key, Duration.ofMinutes(30));
```

These two calls are **two separate commands**. If the application fails after `rightPush` but before `expire`, the key may be left without a TTL. If TTL is a mandatory requirement across the entire operation, design an appropriate atomic mechanism (such as a Lua script), while also considering Redis Cluster and workload size.

If many elements have independent lifecycles, packing them all into a single List with a key-level TTL may not be appropriate. Consider separate keys per element, a Sorted Set by timestamp, or another data structure depending on your goal.

## 15. Controlling List Length and Memory Pressure

A List that continuously receives `RPUSH` without a consumer or a cap mechanism can grow very large. Redis has to keep the data in RAM; this affects memory capacity, persistence, and eviction policies.

You can monitor length with:

```redis
LLEN shop:dev:jobs:email
```

Or in Spring Data Redis:

```java
Long length = redis.opsForList().size("shop:dev:jobs:email");
```

### Example: Keeping at Most N Most Recent History Elements

If a List serves as a most-recent-first history at the head, the producer can `LPUSH` the new item and then `LTRIM` to keep the first N items:

```redis
LPUSH shop:dev:history:u42 event-new
LTRIM shop:dev:history:u42 0 99
```

This is expected to keep at most the 100 most recent elements, assuming no concurrent operation modifies the list between the two commands. In Spring Data Redis:

```java
String key = "shop:dev:history:u42";
redis.opsForList().leftPush(key, "event-new");
redis.opsForList().trim(key, 0, 99);
```

**Note:** `LPUSH` followed by `LTRIM` are two Redis commands. In the gap between them, another client might observe a list longer than the cap or another writer might push an element. If you need an atomic "push and trim" rule, use an appropriate script/transaction with proper resource limits.

Do not enforce a cap by deleting unprocessed elements from a **work queue** unless losing tasks is an acceptable policy. List trimming works well for recent events/caches, but is not inherently suitable for critical job queues.

## 16. Serializers: Lists Store Byte Values, Not Java Objects Directly

A Redis List does not know whether an element is a Java `String`, `UUID`, `Task`, or JSON. Spring Data Redis uses the template's **value serializer** to encode each element on `leftPush`/`rightPush` and decode it on `leftPop`/`rightPop`.

With `StringRedisTemplate`:

```java
redis.opsForList().rightPush("demo:list:string", "task-101");
```

The value is stored as a UTF-8 string.

With `RedisTemplate<String, Task>` using a JSON serializer, each List element is a JSON payload (still using the Redis List data type).

Example DTO:

```java
public record EmailTask(String id, String recipientId) {}
```

Configuring a dedicated template:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class EmailTaskRedisConfig {

    @Bean
    RedisTemplate<String, EmailTask> emailTaskRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, EmailTask> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(EmailTask.class));
        template.afterPropertiesSet();
        return template;
    }
}
```

Usage:

```java
String queueKey = "shop:dev:jobs:email-json";

emailTaskRedisTemplate.opsForList().rightPush(
        queueKey, new EmailTask("t101", "u42"));

EmailTask task = emailTaskRedisTemplate.opsForList()
        .leftPop(queueKey);
```

Writers and readers of the same queue must agree on the serializer and schema. If the producer writes JSON while the consumer uses `JdkSerializationRedisSerializer` or a serializer for another class, deserialization can fail even though the Redis List still holds the intact byte payload.

When interoperating with non-Java services, agreeing on a schema-backed JSON format or another language-agnostic format is usually easier to manage than relying on native Java serialization.

### Key Names Are Not Serialized the Same Way as Values

`RedisTemplate` has its own `keySerializer`. To make inspection with the Redis CLI easy and share keys across services, `StringRedisSerializer` is typically used for key names alongside a separate serializer for List items.

`ListOperations` does not have a single "list" serializer that turns an entire Java `List<T>` into a Redis List. It executes Redis List commands on individual elements, each serialized according to the template configuration. Storing a Java `List<T>` as JSON inside a Redis string via `opsForValue()` is a **different** data model from a Redis List.

## 17. Redis Cluster and Operations at Both Ends of a List

Single-key `LPUSH`, `RPUSH`, `LPOP`, and `RPOP` work naturally in Redis Cluster, because a single Redis key maps to one hash slot and a cluster-aware client routes the command to the node owning that slot.

For example, independent queues:

```text
shop:prod:jobs:email
shop:prod:jobs:sms
shop:prod:jobs:reports
```

These keys can reside on different slots/nodes, and pushing/popping on each individual key causes no multi-key issues.

However, operations combining multiple keys such as `LMOVE source destination LEFT RIGHT` must satisfy the same-slot constraint. Otherwise, `CROSSSLOT` can occur.

```text
shop:prod:jobs:{email}:pending
shop:prod:jobs:{email}:processing
```

Sharing the `email` hash tag places both keys in the same slot, but you should not force **all queues** in the system onto one slot by using an overly broad hash tag.

Redis Cluster only supports logical database `0`. Separate queues by namespace in key names rather than trying to select DB 1 or DB 2 in Cluster mode.

For `MOVED`, `ASK`, and topology changes, a cluster-capable client such as Lettuce/Jedis in cluster mode is responsible for routing/redirection; the application should not pin all queues to a single Redis node when the Cluster has multiple primaries.

## 18. Concurrency: Producers, Consumers, and Processing Order

A List can have multiple producers and consumers. Redis executes each `RPUSH`/`LPOP` command atomically, but **completion order** outside Redis is not necessarily the same as **dequeue order** from the queue.

Example:

```text
FIFO Queue: [task-A, task-B]

Worker 1: LPOP -> task-A, takes 10 seconds to process
Worker 2: LPOP -> task-B, takes 1 second to process

Completion:
task-B finishes before task-A
```

The queue still **dispatched tasks in FIFO order**, yet completion order reversed due to parallel execution. If business logic requires completion strictly in order, you need additional coordination (such as a sequential consumer per partition/entity), rather than relying solely on `RPUSH` + `LPOP`.

### Waiting on Multiple Queues and Priorities

The native Redis `BLPOP` command can accept multiple keys in priority order within the command. When multiple keys already have items available, Redis picks according to the order of keys listed in the command, following `BLPOP` semantics. The `leftPop(key, timeout)` API on `ListOperations` shown in this lesson focuses on a single key; if you need to wait on multiple queues simultaneously, use a compatible driver/Spring Data Redis API and design around Cluster constraints.

Do not infer "task priority" semantics merely from queue names or from having multiple workers waiting. Fairness, starvation, retries, and ordering across multiple queues must be explicitly defined.

## 19. Reliability Issues: Lost, Duplicated, and Reprocessed Tasks

A common scenario:

```text
Producer -> RPUSH task-101 -> Redis List
                                |
Consumer <- LPOP task-101 -----+
     |
     +--> calls external service
              |
              +--> error or consumer crashes
```

The task has already been removed from the List. Redis does not know whether it succeeded or failed, and it does not automatically restore a popped task.

This leads to different architectural choices:

| Requirement Level | Design Direction |
|---|---|
| Simple queue where occasional item loss is acceptable | `RPUSH` + `LPOP` or `LPUSH` + `RPOP` |
| Need to wait for items and avoid polling | `BLPOP`/`BRPOP` with an appropriate timeout |
| Need to track tasks received but not yet ACKed | Pending/processing pattern with `LMOVE`/`BLMOVE`, recovery, and well-designed ACK |
| Need consumer groups, pending tracking, ACK, and claim | Consider Redis Streams |
| Require durable transactions with a database outside Redis | Design outbox/transactional messaging aligned with the data store and business requirements |

Redis persistence (RDB/AOF) also has its own durability guarantees. Just because an `RPUSH` operation returns success does not mean the data is durably synced under every power-loss, failover, or persistence-configuration scenario. When strict delivery guarantees are required, evaluate the entire pipeline from producer to consumer, not just the choice of Redis List commands.

To reduce side effects during retries, each task should have a stable **idempotency identifier**; business processing must define how receiving the same task a second time is accepted or ignored.

## 20. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Popped in reverse of expected order | Using `LPUSH` + `LPOP` when expecting FIFO | Use `RPUSH` + `LPOP` or `LPUSH` + `RPOP` |
| `leftPop` returns `null` | List/key does not exist or has no items left | Handle empty queue; in pipeline/transaction, read results via the corresponding mechanism |
| `rightPush` fails with `WRONGTYPE` | Key already exists as a Redis string/hash/set instead of List | Check `TYPE key` and key naming conventions |
| `leftPushAll` reverses input order | Semantics of pushing each element toward the head | Account for push order or choose `rightPushAll` |
| Worker blocks for a very long time in `leftPop(key, timeout)` | Blocking pop with a long configured timeout | Use finite timeouts and manage connection/thread pools |
| Task disappears when worker fails | `LPOP` removes the item before processing finishes | Design ACK/retry; consider pending/processing or Streams |
| Queue keeps growing | Producer is faster than consumers; no backpressure | Monitor `LLEN`, tune throughput, and set overload policies |
| List hits TTL unexpectedly | TTL is on the key, not on individual elements | Define expiry policy and key-recreation behavior |
| Key recreated after emptying has no TTL | Popping the last element causes Redis to delete the old key | Reapply expiry when creating a new key or change the model |
| Payload deserialization error | Writer/reader use different serializers or classes | Align format, versioning, and serializer |
| `CROSSSLOT` error when moving from pending to processing | Two Redis List keys are in different slots | Use matching hash tags for the related key pair |

### Never Use `KEYS *` to Inspect a Large Queue

To inspect a specific list, use `TYPE`, `LLEN`, and a bounded `LRANGE`:

```bash
redis-cli TYPE shop:dev:jobs:email
redis-cli LLEN shop:dev:jobs:email
redis-cli LRANGE shop:dev:jobs:email 0 9
redis-cli TTL shop:dev:jobs:email
```

`LRANGE key 0 -1` returns the entire list, which can consume significant network/memory if the list is very large. In production, fetch only a small slice when debugging; avoid logging payloads containing sensitive data.

## 21. Hands-on Practice: Using a List as Both FIFO and LIFO

The following commands illustrate behavior on a standalone test Redis instance using the `demo:` namespace. Run them on a dedicated Redis environment for practice.

### Exercise A — FIFO

```bash
redis-cli RPUSH demo:lesson127:fifo job-1 job-2 job-3

redis-cli LRANGE demo:lesson127:fifo 0 -1
# job-1, job-2, job-3

redis-cli LPOP demo:lesson127:fifo
# job-1

redis-cli LPOP demo:lesson127:fifo
# job-2

redis-cli LLEN demo:lesson127:fifo
# 1
```

`RPUSH` adds new items to the tail. `LPOP` retrieves the oldest item at the head.

### Exercise B — LIFO

```bash
redis-cli LPUSH demo:lesson127:lifo job-1 job-2 job-3

redis-cli LRANGE demo:lesson127:lifo 0 -1
# job-3, job-2, job-1

redis-cli LPOP demo:lesson127:lifo
# job-3

redis-cli LPOP demo:lesson127:lifo
# job-2
```

Because `LPUSH` inserts each item at the head, `LPOP` retrieves the most recently added item.

### Exercise C — Inspecting Both Ends and TTL

```bash
redis-cli RPUSH demo:lesson127:ends A B C

redis-cli LINDEX demo:lesson127:ends 0
# A

redis-cli LINDEX demo:lesson127:ends -1
# C

redis-cli EXPIRE demo:lesson127:ends 60
redis-cli LPUSH demo:lesson127:ends X
redis-cli TTL demo:lesson127:ends
# Still has remaining expiration time
```

`LINDEX` inspects without deleting the element; `LPUSH` adds an element at the head without automatically extending the existing key's TTL.

### Exercise D — Blocking Pop Across Two Terminals

Terminal A:

```bash
redis-cli BLPOP demo:lesson127:blocking 10
```

During the wait window, Terminal B:

```bash
redis-cli RPUSH demo:lesson127:blocking task-42
```

Terminal A can receive the result containing the key name and `task-42`. If 10 seconds elapse before Terminal B pushes, Terminal A receives nil; repeat the exercise to observe the case where an item arrives within the wait window.

`BLPOP` **consumes** the item rather than merely "listening" to notifications. If you want fan-out so multiple subscribers all receive an event, List pop is not a Pub/Sub model; choose Redis Pub/Sub or Redis Streams depending on delivery and retention requirements.

## 22. Self-Check Questions

**1. Given List `[A, B]`, what is the new list after calling `LPUSH key X Y`?**

The command pushes `X` and then `Y` onto the head, so the result is `[Y, X, A, B]`.

**2. For a FIFO queue where the producer calls `rightPush`, what should the consumer call?**

The consumer uses `leftPop` (or blocking `leftPop(key, Duration)`) to retrieve the oldest item at the head.

**3. Which API reads the last element while keeping the List unchanged?**

Use `opsForList().index(key, -1)`, corresponding to Redis `LINDEX key -1`. `rightPop` will delete the element.

**4. If a Redis List has only one element left and a consumer calls `LPOP`, does the key still exist?**

Normally no. Redis deletes the List key when the last element is popped. A subsequent push creates a new key.

**5. How does `leftPop(key, Duration.ofSeconds(5))` differ from `leftPop(key)`?**

The timeout variant waits up to roughly 5 seconds for an element to appear; the non-timeout variant returns immediately. In synchronous systems, waiting can occupy a connection/thread.

**6. Why is atomic popping not enough to guarantee each task is processed successfully exactly once?**

Because the task is deleted immediately upon pop. A worker can crash before finishing, or finish processing but fail before ACK in an ACK-based model; separate retry, idempotency, and state tracking are needed.

**7. In Redis Cluster, what condition must two List keys used with `LMOVE` satisfy?**

They must belong to the same hash slot so Redis can execute the multi-key operation atomically under Cluster rules.

**8. Why should `LTRIM` not be used automatically on a critical queue?**

Because `LTRIM` deletes elements outside the retained range. On a queue with unprocessed items, that can cause task loss; trim only when business policy permits dropping elements.

## 23. Conclusion

In Spring Data Redis, working with both ends of a Redis List is clearly expressed through **`leftPush`, `rightPush`, `leftPop`, and `rightPop`**. Pairing push and pop at **opposite ends** creates a FIFO queue; pairing them at the **same end** creates a LIFO stack. `leftPushAll`/`rightPushAll` add multiple elements but require attention to ordering, while `index` and `range` inspect the list without removing elements.

Each push/pop is an atomic Redis command, yet **popping removes an item immediately**, which is insufficient on its own for job-processing systems that require retries and ACKs. Blocking pop avoids polling, but requires proper timeouts and connection management. TTL applies to the **entire List key**; when a key empties and is recreated, the old expiry does not automatically return. In Redis Cluster, single-List-key operations are straightforward, whereas commands moving elements across multiple List keys must respect hash slots. Understanding these rules helps you choose the right Spring Data Redis APIs and build queues, stacks, or deques with predictable behavior.
