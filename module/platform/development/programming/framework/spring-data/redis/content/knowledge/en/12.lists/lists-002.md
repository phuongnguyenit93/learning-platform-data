# Reading Element Ranges and Bounding List Size in Spring Data Redis

A Redis List is a data structure that stores an **ordered sequence of elements**, in which an application can add and remove elements at both ends. With Spring Data Redis, you typically operate on Redis Lists through `ListOperations<K, V>`, such as `StringRedisTemplate.opsForList()`. When a list contains many elements, two especially important operations are **reading a slice with `LRANGE`** and **retaining only the required portion with `LTRIM`**.

For example, an application manages a user's 100 most recent notifications. Whenever a new notification arrives, the system adds it to a Redis List. The API only reads the 10 most recent notifications and does not want Redis to retain old notifications indefinitely. This seemingly simple problem requires a clear understanding of **left/right ends**, **start–stop indices**, **negative indices**, **read cost**, **size bounding**, and **atomicity under concurrent writes**.

This lesson thoroughly explains these operations in the context of **Spring Data Redis / Lists**, along with Redis CLI and Java examples, pagination, element count capping, TTL handling, concurrency scenarios, and guidance on choosing data structures as lists grow large.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain element ordering in a Redis List when using `LPUSH` and `RPUSH`.
2. Read a range of elements using `LRANGE key start stop` and Spring Data Redis `opsForList().range(key, start, end)`.
3. Understand that **both start and stop are inclusive in the result**, and know how to use negative indices such as `-1` and `-N`.
4. Use `LLEN` / `opsForList().size(key)` to inspect the element count and determine read bounds.
5. Use `LTRIM` / `opsForList().trim(key, start, end)` to **keep a range** and discard elements outside that range.
6. Design a list that keeps only the **N newest elements** in either write direction: `LPUSH + LTRIM 0 N-1` or `RPUSH + LTRIM -N -1`.
7. Understand why two separate push and trim calls can create intermediate states; use a Redis Lua script when an atomic update is needed.
8. Identify issues with offset-based pagination while a list is changing, avoid reading entire large lists, and control both element count and memory footprint.

**Prerequisites:** basic knowledge of Java/Spring Boot, Dependency Injection, basic operations with `StringRedisTemplate`, and Redis keys/values. Examples use Java 17+, Spring Boot 3.x, Spring Data Redis 3.x, and a standard Redis server; `LRANGE`, `LLEN`, and `LTRIM` are core Redis commands.

## 2. Redis List: Order Is the Foundation

A Redis List is ordered from **left to right**. The leftmost element is at index 0; the next element is at index 1; the last element is at index `-1`. Redis allows multiple elements with duplicate values: a List differs from a Set.

Visualize a five-element list:

~~~text
Redis key: demo:list:letters

    LEFT / HEAD                         RIGHT / TAIL
      |                                        |
      v                                        v
    +-----+-----+-----+-----+-----+
    |  A  |  B  |  C  |  D  |  E  |
    +-----+-----+-----+-----+-----+
       0     1     2     3     4     positive index
      -5    -4    -3    -2    -1     negative index
~~~

### 2.1. Two Ways to Add to a List

**`LPUSH`** adds elements to the **left** end:

~~~redis
DEL demo:list:letters
LPUSH demo:list:letters A
LPUSH demo:list:letters B
LPUSH demo:list:letters C
LRANGE demo:list:letters 0 -1
~~~

The result from left → right is:

~~~text
C, B, A
~~~

**`RPUSH`** adds elements to the **right** end:

~~~redis
DEL demo:list:letters
RPUSH demo:list:letters A
RPUSH demo:list:letters B
RPUSH demo:list:letters C
LRANGE demo:list:letters 0 -1
~~~

Result:

~~~text
A, B, C
~~~

**Implications for chronological lists:**

| Insertion Method | Where Is the Newest Element? | How to Read N Newest | How to Keep N Newest |
| --- | --- | --- | --- |
| `LPUSH` | Left end, index 0 | `LRANGE key 0 N-1` | `LTRIM key 0 N-1` |
| `RPUSH` | Right end, index -1 | `LRANGE key -N -1` | `LTRIM key -N -1` |

Both approaches are valid. What matters most is that **all write, read, and trim sites agree on a single convention**. If a service writes with `RPUSH` yet trims with `LTRIM 0 N-1`, it will keep the **oldest** elements instead of the newest ones.

### 2.2. How Lists Differ from Strings or Sets

- **Redis String** fits a single value, JSON blob, or counter; it cannot slice by list element count.
- **Redis List** preserves element order and allows duplicates, making it suitable for ordered lists, recent history, and simple queues.
- **Redis Set** does not preserve positional List read order and removes duplicate elements.
- **Redis Sorted Set** orders by score, which can suit timelines with timestamps/IDs and range queries by milestone.
- **Redis Stream** provides event IDs, consumer groups, and event-reading mechanisms, suitable for event processing needs beyond a simple list.

Do not choose Redis List merely because the data "has multiple items." Choose it when **left/right-end ordering** and List operations genuinely fit the access pattern.

## 3. Reading Element Ranges with LRANGE

Redis command:

~~~redis
LRANGE key start stop
~~~

`start` and `stop` are **positional indices in the List**, not element counts. **The read range is inclusive on both ends**, so:

~~~redis
LRANGE demo:list:letters 0 0
~~~

reads **one** first element, while:

~~~redis
LRANGE demo:list:letters 0 9
~~~

reads at most **10** elements: indices 0 through 9.

### 3.1. Creating a Sample List to Test

Reset the list to a known state:

~~~redis
DEL demo:list:letters
RPUSH demo:list:letters A B C D E
LRANGE demo:list:letters 0 -1
LLEN demo:list:letters
~~~

The list now holds `[A, B, C, D, E]` with length 5.

| Command | Returned Result | Why? |
| --- | --- | --- |
| `LRANGE key 0 0` | `[A]` | Index 0 only |
| `LRANGE key 0 2` | `[A, B, C]` | Indices 0, 1, 2 |
| `LRANGE key 1 3` | `[B, C, D]` | Indices 1, 2, 3 |
| `LRANGE key 2 4` | `[C, D, E]` | Last three elements via positive indices |
| `LRANGE key -3 -1` | `[C, D, E]` | Last three elements via negative indices |
| `LRANGE key -2 -2` | `[D]` | Index -2 is D |
| `LRANGE key 0 -1` | `[A, B, C, D, E]` | Entire list |
| `LRANGE key 3 1` | `[]` | Start comes after stop |
| `LRANGE key 10 12` | `[]` | Start is beyond List length |
| `LRANGE key -100 1` | `[A, B]` | Negative start past the left is clamped to the head |
| `LRANGE key 2 100` | `[C, D, E]` | Stop past the right is clamped to the tail |

In the table, `key` is shorthand for `demo:list:letters`. Redis does not treat out-of-bounds indices as errors in these cases; it clamps the range or returns an empty list. This is convenient when the last page has fewer remaining elements.

### 3.2. Negative Indices

Negative indices count from the **right** side:

~~~text
List:             A    B    C    D    E
Positive index:   0    1    2    3    4
Negative index:  -5   -4   -3   -2   -1
~~~

Accordingly:

~~~redis
LRANGE demo:list:letters -1 -1
~~~

returns the last element `E`, and:

~~~redis
LRANGE demo:list:letters -3 -1
~~~

returns `C, D, E` in **left-to-right storage order**. Using negative indices does not automatically reverse the result order.

To fetch the **N newest at the right end**, use `-N` to `-1`. If the List has fewer than N elements, Redis returns all existing elements.

### 3.3. Watch Out for the N - 1 Expression

If you want to read the first 20 elements:

~~~redis
LRANGE demo:list:items 0 19
~~~

Do not write `LRANGE key 0 20` because that command can return **21 elements**. Similarly, pagination with `pageSize=10` starting at 0 has these ranges:

~~~text
Page 0: [0, 9]
Page 1: [10, 19]
Page 2: [20, 29]
...
~~~

This is why Java code typically computes:

~~~java
long start = (long) pageIndex * pageSize;
long end = start + pageSize - 1;
~~~

Ensure `pageIndex >= 0` and `pageSize > 0`; in real systems, cap `pageSize` so a single request cannot ask to read millions of elements.

### 3.4. LRANGE Does Not Remove Elements

`LRANGE` is a **read** command. It leaves the List intact, unlike `LPOP` or `RPOP` which retrieve and remove elements. Example:

~~~redis
LRANGE demo:list:letters 0 1
LLEN demo:list:letters
~~~

After reading 2 elements, the List length is still 5.

This behavior suits APIs that display history or recent lists. If you are building a queue where a consumer must **claim and remove elements from the queue**, use pop operations or an appropriate queue mechanism; `LRANGE` neither acknowledges processing nor removes elements from the queue.

## 4. Reading Ranges with Spring Data Redis

In Spring Data Redis, the typical interface is:

~~~java
ListOperations<String, String> operations =
        stringRedisTemplate.opsForList();

List<String> values = operations.range(
        "demo:list:letters", 1, 3
);
~~~

The example result is `[B, C, D]`.

Key APIs:

| Redis | Spring Data Redis | Meaning |
| --- | --- | --- |
| `LRANGE key start stop` | `opsForList().range(key, start, end)` | Read range without deleting |
| `LLEN key` | `opsForList().size(key)` | Read element count |
| `LTRIM key start stop` | `opsForList().trim(key, start, end)` | Keep range, remove everything outside |
| `LINDEX key index` | `opsForList().index(key, index)` | Read one element by index |
| `LPUSH key value` | `opsForList().leftPush(key, value)` | Add at left end |
| `RPUSH key value` | `opsForList().rightPush(key, value)` | Add at right end |
| `LPOP key` | `opsForList().leftPop(key)` | Pop and delete left element |
| `RPOP key` | `opsForList().rightPop(key)` | Pop and delete right element |

`range(...)` and `size(...)` can return `null` when invoked inside certain pipeline or transaction contexts because results are collected and returned later. In normal synchronous calls, `range(...)` on a missing key typically returns an empty list, and `size(...)` returns 0. Never assume `null` means an empty List in every context.

### 4.1. Minimal Application Configuration

In a Spring Boot application with a BOM managing dependency versions:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Run Redis locally for hands-on practice:

~~~bash
docker run --name redis-list-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-list-lab redis-cli PING
~~~

A successful `PING` command returns `PONG`. If port 6379 is already taken, pick a different host port and update the application configuration.

Spring Boot 3.x:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

This example assumes the application runs on the host machine and Docker Redis binds the host port to loopback. If the application also runs in Docker Compose, use the Redis service name on the same network. In production environments, configure ACLs/authentication, TLS where needed, network restrictions, and proper secrets; never expose unauthenticated Redis to the Internet.

### 4.2. Why Is StringRedisTemplate Suitable for This Lab?

`StringRedisTemplate` uses string serializers for keys and values. For a List storing messages as short text or application-generated JSON strings, the data can be inspected with `redis-cli LRANGE`.

When using `RedisTemplate<String, EventDto>` to store objects, you must **explicitly configure serializers** for keys and values. If you rely on the default binary serializer, values in the CLI may be unreadable and another application cannot decode them without knowing the format. The generic type `<String, EventDto>` does not automatically configure a JSON value serializer.

In the code snippets below, each List element is a `String`. This is a simple data contract that keeps the focus on indices, ranges, and trimming.

## 5. Java Service: Reading Elements and Paginating

Suppose the List stores messages in **oldest on the left, newest on the right** order because the service appends with `RPUSH`.

Create `RecentMessageService.java`:

~~~java
package com.example.redis;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RecentMessageService {

    private final StringRedisTemplate redis;

    public RecentMessageService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void append(String userId, String message) {
        validateUserId(userId);
        if (message == null || message.isBlank()) {
            throw new IllegalArgumentException("Message is required");
        }

        redis.opsForList().rightPush(key(userId), message);
    }

    public List<String> firstPage(String userId, int size) {
        validatePageSize(size);
        List<String> values = redis.opsForList()
                .range(key(userId), 0, size - 1L);
        return requireDirectResult(values);
    }

    public List<String> lastMessages(String userId, int limit) {
        validatePageSize(limit);
        List<String> values = redis.opsForList()
                .range(key(userId), -((long) limit), -1);
        return requireDirectResult(values);
    }

    public List<String> lastMessagesNewestFirst(String userId, int limit) {
        List<String> result = new ArrayList<>(lastMessages(userId, limit));
        Collections.reverse(result);
        return result;
    }

    public List<String> page(String userId, int pageIndex, int pageSize) {
        if (pageIndex < 0) {
            throw new IllegalArgumentException("Page index must be >= 0");
        }
        validatePageSize(pageSize);

        long start = Math.multiplyExact((long) pageIndex, pageSize);
        long end = Math.addExact(start, pageSize - 1L);

        List<String> values = redis.opsForList()
                .range(key(userId), start, end);
        return requireDirectResult(values);
    }

    public long size(String userId) {
        Long value = redis.opsForList().size(key(userId));
        if (value == null) {
            throw new IllegalStateException("Redis length is unavailable");
        }
        return value;
    }

    private List<String> requireDirectResult(List<String> values) {
        if (values == null) {
            throw new IllegalStateException(
                    "LRANGE did not return a direct result");
        }
        return List.copyOf(values);
    }

    private void validatePageSize(int size) {
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "Page size must be between 1 and 100");
        }
    }

    private void validateUserId(String userId) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("User ID is required");
        }
    }

    private String key(String userId) {
        validateUserId(userId);
        return "shop:user:" + userId + ":recent-messages";
    }
}
~~~

The methods above demonstrate different read patterns:

- `firstPage(userId, 10)` fetches the first 10 leftmost elements (which in this RPUSH example are the oldest messages).
- `lastMessages(userId, 10)` fetches up to 10 **rightmost** elements in **oldest → newest** order.
- `lastMessagesNewestFirst(...)` fetches the same slice and reverses it in Java to display **newest → oldest**. The underlying list in Redis stays unchanged.
- `page(userId, 0, 10)` reads indices 0..9; `page(userId, 1, 10)` reads 10..19.
- `size(userId)` maps to `LLEN`; there is no need to load every element just to count them.

The 100-element limit in the example prevents unbounded requests from returning excessive data. Production applications should set limits based on element size, network load, and UX; it does not have to be 100.

`List.copyOf(values)` creates an unmodifiable Java list so callers cannot accidentally mutate the returned collection. It does not add cross-request consistency in Redis. If the service runs inside a pipeline/transaction, handling `null` should follow that API rather than assuming direct synchronous results.

### 5.1. Using the Example in a Controller

A minimal REST controller:

~~~java
package com.example.redis;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/users/{userId}/messages")
public class RecentMessageController {

    private final RecentMessageService messages;

    public RecentMessageController(RecentMessageService messages) {
        this.messages = messages;
    }

    @GetMapping("/latest")
    public List<String> latest(
            @PathVariable String userId,
            @RequestParam(defaultValue = "10") int limit) {
        return messages.lastMessagesNewestFirst(userId, limit);
    }

    @GetMapping
    public List<String> page(
            @PathVariable String userId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        return messages.page(userId, page, size);
    }
}
~~~

Example API calls:

~~~http
GET /users/u42/messages/latest?limit=10
GET /users/u42/messages?page=0&size=10
~~~

This controller only illustrates reading a List. In a real system, authentication and authorization checks are required: **never assume a caller is authorized to view notifications merely because they know `userId` in the URL**. If sensitive data is stored, also consider List contents, TTL, and logging.

### 5.2. If Writing with LPUSH, Read Logic Changes

If new items are added using:

~~~java
redis.opsForList().leftPush(key, message);
~~~

then the left end holds the **newest** element. In that case:

~~~java
List<String> newest = redis.opsForList().range(key, 0, 9);
~~~

already returns up to 10 elements in newest → oldest order. There is no need to read `-10, -1` and reverse the result, because those are the 10 elements at the right end (the older ones).

## 6. LLEN: Reading Size Without Loading Data

Redis:

~~~redis
LLEN demo:list:letters
~~~

Spring Data Redis:

~~~java
Long length = stringRedisTemplate.opsForList()
        .size("demo:list:letters");
~~~

If the key is a List with 5 elements, the result is 5. If the key **does not exist**, Redis `LLEN` returns 0. If the key exists but holds a different Redis type (e.g., String), the command returns `WRONGTYPE`.

**Do not call `LRANGE key 0 -1` and take `list.size()` just to count elements.** `LLEN` has **O(1)** complexity, whereas reading the entire List takes time and network bandwidth proportional to the number of elements.

### 6.1. LLEN and LRANGE Do Not Form a Shared Snapshot

Suppose:

~~~text
T1: Request A calls LLEN -> 100
T2: Request B RPUSH adds 1 -> 101
T3: Request A calls LRANGE 90 99 -> reads a slice under the new state
~~~

A's two commands execute at **two different points in time**. With concurrent writers, the count and the range can reflect two different states. This is usually acceptable for a recent-history UI; if count and elements must be consistent within a single snapshot, choose an appropriate transaction/script mechanism or data design.

In pagination APIs, a length returned as `totalCount` should be treated as **the length observed at read time**, unless an exact snapshot has been designed.

### 6.2. Empty Redis Lists and Missing Keys

When a List has all elements popped or trimmed away, Redis usually deletes the empty key. Therefore `LLEN key = 0` cannot distinguish "List was never created" from "List had all items removed." If business logic needs to record creation state or processing progress, store metadata in a separate key or another data source.

## 7. LTRIM: Keeping a Range and Deleting the Rest

The name `LTRIM` sometimes leads learners to think the command "trims from the left." In reality, the command:

~~~redis
LTRIM key start stop
~~~

**keeps elements from index start through stop, inclusive at both ends**; all elements **outside that range** are removed. Indices are evaluated against the List state when the command executes.

Example:

~~~redis
DEL demo:list:letters
RPUSH demo:list:letters A B C D E
LTRIM demo:list:letters 1 3
LRANGE demo:list:letters 0 -1
~~~

Remaining result:

~~~text
B, C, D
~~~

`LTRIM key 1 3` does not delete elements at indices 1..3; it does the opposite: it **keeps** those elements.

### 7.1. Several LTRIM Cases

Suppose each row starts from the List `[A, B, C, D, E]`:

| Command | Remaining List | Interpretation |
| --- | --- | --- |
| `LTRIM key 0 2` | `[A, B, C]` | Keep first 3 elements on the left |
| `LTRIM key -3 -1` | `[C, D, E]` | Keep last 3 elements on the right |
| `LTRIM key 1 3` | `[B, C, D]` | Keep middle slice |
| `LTRIM key 0 -1` | `[A, B, C, D, E]` | Keep everything |
| `LTRIM key 3 1` | List is completely deleted | Empty range |
| `LTRIM key 20 30` | List is completely deleted | Start exceeds size |
| `LTRIM key -100 1` | `[A, B]` | Keep from start to index 1 |

When no elements remain after trimming, Redis does not keep an empty List as a standalone key; the key is usually deleted.

### 7.2. LTRIM Is a Destructive Operation

`LRANGE` only reads; `LTRIM` **actually removes elements**. If a List holds critical business data with no other storage copy, trimming in the wrong direction can cause data loss.

Before putting `LTRIM` on a write path, answer: "Are the discarded elements still stored in another database/log?", "Have they already been consumed/processed?", and "Is this list intentionally just a recent cache/window?"

For temporary notification lists that can be rebuilt, trimming is usually appropriate. For a task list that must be processed once without loss, a simple Redis List with trimming may not meet requirements; design proper queues, retries, acknowledgements, or use Redis Streams.

## 8. Bounding List Size: Keeping the N Newest Elements

An application writing continuously to a Redis List can cause the element count to grow unbounded unless a lifecycle policy exists. A common approach is **each time an element is added, retain only the N newest elements**.

### 8.1. Using RPUSH: Keeping the N Rightmost Elements

Suppose the List represents history from oldest → newest. Append on the right:

~~~redis
DEL demo:recent:events
RPUSH demo:recent:events event-1
RPUSH demo:recent:events event-2
RPUSH demo:recent:events event-3
RPUSH demo:recent:events event-4
RPUSH demo:recent:events event-5
LRANGE demo:recent:events 0 -1
~~~

Before trim:

~~~text
[event-1, event-2, event-3, event-4, event-5]
~~~

Keep only the 3 newest elements:

~~~redis
LTRIM demo:recent:events -3 -1
LRANGE demo:recent:events 0 -1
LLEN demo:recent:events
~~~

After trim:

~~~text
[event-3, event-4, event-5]
LLEN = 3
~~~

In general:

~~~text
RPUSH key newItem
LTRIM key -N -1
~~~

If N is greater than the current number of elements, `LTRIM -N -1` still keeps the entire List. There is no need to call `LLEN` first to check whether trimming is needed.

### 8.2. Using LPUSH: Keeping the N Leftmost Elements

In some UIs, newest → oldest order is more convenient:

~~~redis
DEL demo:recent:events
LPUSH demo:recent:events event-1
LPUSH demo:recent:events event-2
LPUSH demo:recent:events event-3
LPUSH demo:recent:events event-4
LPUSH demo:recent:events event-5
LRANGE demo:recent:events 0 -1
~~~

List before trim:

~~~text
[event-5, event-4, event-3, event-2, event-1]
~~~

Keep only the 3 newest elements:

~~~redis
LTRIM demo:recent:events 0 2
LRANGE demo:recent:events 0 -1
~~~

Result:

~~~text
[event-5, event-4, event-3]
~~~

In general:

~~~text
LPUSH key newItem
LTRIM key 0 N-1
~~~

### 8.3. Why Not Call LLEN and Compute the Range?

An approach many people think of:

~~~text
RPUSH key item
length = LLEN key
if length > N:
    LTRIM key length-N length-1
~~~

For keeping the rightmost items, `LTRIM key -N -1` already expresses the requirement directly. The `LLEN`-based approach costs an extra round trip and can read the length from a different point in time if concurrent writers modify the List.

**N must be greater than 0.** When N=0, `-N` becomes 0; `LTRIM key 0 -1` ends up keeping the entire List, opposite to the intent of "keep 0 elements." If business logic wants to store no elements, handle that branch separately by not pushing or by deleting the key cleanly.

## 9. Java: Append and Bound Size

Once you have standardized on writing with `RPUSH`, a simple service can be written as:

~~~java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class BoundedRecentListService {

    private static final int MAX_ALLOWED_ITEMS = 500;
    private final StringRedisTemplate redis;

    public BoundedRecentListService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void append(String feedId, String event, int maxItems) {
        validateFeedId(feedId);
        validateMaxItems(maxItems);
        if (event == null || event.isBlank()) {
            throw new IllegalArgumentException("Event is required");
        }

        String key = key(feedId);
        redis.opsForList().rightPush(key, event);
        redis.opsForList().trim(key, -((long) maxItems), -1);
    }

    public List<String> readLatest(String feedId, int limit) {
        validateFeedId(feedId);
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "Limit must be between 1 and 100");
        }

        List<String> result = redis.opsForList()
                .range(key(feedId), -((long) limit), -1);
        if (result == null) {
            throw new IllegalStateException("Redis range unavailable");
        }
        return List.copyOf(result);
    }

    public long size(String feedId) {
        Long result = redis.opsForList().size(key(feedId));
        if (result == null) {
            throw new IllegalStateException("Redis size unavailable");
        }
        return result;
    }

    private void validateFeedId(String feedId) {
        if (feedId == null || feedId.isBlank()) {
            throw new IllegalArgumentException("Feed ID is required");
        }
    }

    private void validateMaxItems(int maxItems) {
        if (maxItems < 1 || maxItems > MAX_ALLOWED_ITEMS) {
            throw new IllegalArgumentException(
                    "maxItems must be between 1 and " + MAX_ALLOWED_ITEMS);
        }
    }

    private String key(String feedId) {
        validateFeedId(feedId);
        return "shop:feed:" + feedId + ":recent";
    }
}
~~~

Example invocation:

~~~java
boundedRecentListService.append("feed-42", "event-A", 3);
boundedRecentListService.append("feed-42", "event-B", 3);
boundedRecentListService.append("feed-42", "event-C", 3);
boundedRecentListService.append("feed-42", "event-D", 3);

List<String> latest =
        boundedRecentListService.readLatest("feed-42", 3);
long count = boundedRecentListService.size("feed-42");
~~~

Under RPUSH ordering, the expected output is:

~~~text
latest = [event-B, event-C, event-D]
count  = 3
~~~

In the code above, `maxItems` should be a limit governed by the **application**, rather than letting external clients arbitrarily raise it to millions. If every feed must keep strictly 100 elements, a fixed configuration constant can be used instead of passing a parameter on every call.

**Important limitation of this example:** `rightPush(...)` and `trim(...)` are **two separate Redis commands**. With multiple concurrent writers or a requirement that "the List must never exceed N elements, even momentarily," use an atomic operation such as a Lua script or an appropriate transaction, shown next.

## 10. Why Separate RPUSH + LTRIM Are Not Fully Atomic

Each Redis command such as `RPUSH` or `LTRIM` executes atomically at the single-command level. However, a **sequence of two commands** is not automatically atomic.

Suppose a List has a cap of 3:

~~~text
Initial: [A, B, C] (3 elements)

Writer 1: RPUSH D
             List: [A, B, C, D]             (4 elements)

Reader:   LRANGE key 0 -1
             sees 4 elements

Writer 1: LTRIM key -3 -1
             List: [B, C, D]                (3 elements)
~~~

Between `RPUSH` and `LTRIM`, a reader can observe a size exceeding the cap. If the application crashes or loses its connection after push but before trim, the List may remain over the limit until the next trim.

When multiple writers append concurrently, commands can interleave:

~~~text
Writer A: RPUSH D
Writer B: RPUSH E
Writer A: LTRIM -3 -1
Writer B: LTRIM -3 -1
~~~

Once the trim operations succeed, the List returns to its bounded size; however, the **intermediate state** is unprotected. If business requirements tolerate a brief length slightly above N with self-healing on subsequent writes, the two-command approach can be simple enough. If a strict invariant is needed at all times, combine them into an atomic server-side Redis operation.

### 10.1. Pipelining Is Not a Transaction

A commonly suggested approach is sending `RPUSH` and `LTRIM` in a pipeline to reduce round trips. Pipelining only **batches commands over the network**; it **does not prevent commands from other clients from interleaving between them**.

`MULTI/EXEC` can ensure commands run consecutively in a Redis transaction, while a Lua script executes combined logic on the server in a single call. For short "push then trim" logic, Lua is usually the most direct and reusable way to express it.

## 11. Lua Script: Appending and Bounding Size in One Operation

Redis supports Lua scripts executed sequentially on the server. You can combine `RPUSH`, `LTRIM`, and `LLEN` into **a single atomic script**.

### 11.1. Lua Script

~~~lua
-- KEYS[1]: Redis List key
-- ARGV[1]: new value
-- ARGV[2]: positive integer maxItems

local maxItems = tonumber(ARGV[2])
if not maxItems or maxItems < 1 or maxItems % 1 ~= 0 then
    return redis.error_reply("maxItems must be a positive integer")
end

redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], -maxItems, -1)
return redis.call('LLEN', KEYS[1])
~~~

On Redis, the commands inside the script execute as a unit without interference from other requests in between. Readers only see the List **before or after** the script; they never observe the state where `RPUSH` ran without `LTRIM`.

The script returns the List size after trimming, which is useful for observability. Java code should validate `maxItems` before passing it and apply appropriate limits to the value/payload.

**Note:** atomic script execution does not mean every error "rolls back" like a database transaction. If a script modifies data and then raises a runtime error in a later step, Redis does not automatically undo commands executed before the error. Scripts should therefore be short, called with valid inputs, and avoid logic prone to failing after writes.

### 11.2. Configuring the RedisScript Bean

~~~java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration(proxyBeanMethods = false)
public class BoundedListScriptConfig {

    @Bean
    RedisScript<Long> appendAndTrimScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setResultType(Long.class);
        script.setScriptText("""
            local n = tonumber(ARGV[2])
            if not n or n < 1 or n % 1 ~= 0 then
                return redis.error_reply("maxItems must be positive")
            end
            redis.call('RPUSH', KEYS[1], ARGV[1])
            redis.call('LTRIM', KEYS[1], -n, -1)
            return redis.call('LLEN', KEYS[1])
            """);
        return script;
    }
}
~~~

`DefaultRedisScript<Long>` specifies the Java return type as `Long`. The `LLEN` command inside the script returns a Redis integer, which matches this type. With `StringRedisTemplate`, the keys and arguments passed to the script are serialized as Strings.

### 11.3. Executing the Script with StringRedisTemplate

~~~java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class AtomicBoundedListService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> appendAndTrimScript;

    public AtomicBoundedListService(
            StringRedisTemplate redis,
            RedisScript<Long> appendAndTrimScript) {
        this.redis = redis;
        this.appendAndTrimScript = appendAndTrimScript;
    }

    public long append(String feedId, String value, int maxItems) {
        if (feedId == null || feedId.isBlank()) {
            throw new IllegalArgumentException("Feed ID is required");
        }
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Value is required");
        }
        if (maxItems < 1 || maxItems > 500) {
            throw new IllegalArgumentException("maxItems out of range");
        }

        String key = "shop:feed:" + feedId + ":recent";
        Long size = redis.execute(
                appendAndTrimScript,
                List.of(key),
                value,
                Integer.toString(maxItems)
        );

        if (size == null) {
            throw new IllegalStateException("Redis returned no size");
        }
        return size;
    }
}
~~~

Advantages of this code:

1. Only a single `execute(...)` call from Java.
2. Redis performs `RPUSH` and `LTRIM` in the same script, preventing readers from seeing a List temporarily exceeding N.
3. The service does not need to call `LLEN` first and calculate trim bounds manually.
4. The return value is the post-operation List length.

Switch to **LPUSH** if you want the newest element at the left end:

~~~lua
redis.call('LPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], 0, n - 1)
return redis.call('LLEN', KEYS[1])
~~~

Do not switch to LPUSH while keeping `LTRIM -n -1`: doing so would accidentally drop the newly added element and keep older ones.

### 11.4. Using MULTI/EXEC Instead of Lua

A Redis transaction queues multiple commands between `MULTI` and `EXEC` so the server runs them sequentially when `EXEC` executes. It can also satisfy the `RPUSH + LTRIM` requirement without other operations interleaving. However, you must understand how Spring Data Redis manages connections and transactions; do not call `multi()`/`exec()` arbitrarily on connections in a service without controlling their lifecycle.

When you only need a short operation with clear inputs and output like "append and keep N," a Lua script is usually easier to express and maintain. For more complex rules, compare transactions, Lua, and data models before implementing.

## 12. Element Count Limits Are Different from Memory Limits

`LTRIM` bounds the **number of elements**, not the byte size of each element:

~~~text
List A: 100 elements × 20 bytes   ≈ 2 KB payload
List B: 100 elements × 200 KB     ≈ 20 MB payload
~~~

These are payload estimates excluding data-structure, key, and Redis memory allocator overhead. Both have `LLEN = 100` yet consume vastly different amounts of memory.

### 12.1. Why Should Payload Size Also Be Bounded?

A client could push a very large JSON payload into a List, causing:

- Redis to consume excessive RAM even though the element count never exceeds N.
- `LRANGE` reading a small page to transfer megabytes over the network.
- Deserialization to consume CPU and increase GC pressure in Java.
- HTTP responses larger than the UI requires.
- Trimming to free large allocations, incurring memory-management overhead.

Real-world designs should enforce a **maximum element size**, **maximum List length**, **request page size**, and **TTL/retention** when data does not need to live forever. You can store only IDs/summaries in the List and keep full payloads in another store when appropriate.

### 12.2. Growth Across Users or Keys

A limit of 100 elements per List does not mean the system stores only 100 elements. If every user has a List:

~~~text
1,000,000 users × 100 elements/List
   = up to 100,000,000 elements
~~~

This is a multiplication of potential element counts, not an exact RAM forecast. Account for key count, average value size, TTL, memory policy, and user scale rather than inspecting `LLEN` on a single sample key and assuming memory is safe.

## 13. Time Complexity of LRANGE, LLEN, and LTRIM

Redis applies internal optimizations to Lists, yet each command still carries a distinct cost.

| Command | Commonly Cited Complexity | Meaning |
| --- | --- | --- |
| `LLEN` | **O(1)** | Retrieves length without scanning elements |
| `LRANGE` | **O(S + N)** | S relates to the distance to traverse to the start offset; N is the number of elements returned |
| `LTRIM` | **O(N)** where N is the number of removed elements | Removing many elements can be costly |
| `LINDEX` | **O(N)** depending on position | Avoid repeatedly reading deep List indices in a loop when LRANGE can be used |
| `LPUSH` / `RPUSH` | Typically **O(1)** per element | Appending/prepending at ends fits sequential streams |

For large Lists, Redis optimizes traversal from whichever end is closer; however, **deep offsets** and **large read ranges** still consume substantial resources. A single `LRANGE 0 -1` on a million-element List incurs major data-transfer and object-allocation cost even if Redis replies.

### 13.1. Do Not Use LRANGE to Read an Entire Huge List

The command:

~~~redis
LRANGE shop:feed:global 0 -1
~~~

can be handy when debugging a small List. In production, however, if the List is long, it:

1. Forces Redis to gather and return a huge number of elements.
2. Produces a large response payload, consuming network bandwidth.
3. Causes the Java client to allocate many Strings/objects and potentially increase GC.
4. Can slow down other requests sharing Redis.

For UI APIs, bound page sizes or fetch only elements near the ends of the List, such as `LRANGE key 0 19` or `LRANGE key -20 -1`. If the requirement is to query hundreds of thousands of elements deep inside a List, re-evaluate the data structure.

### 13.2. LTRIM Is Usually Cheap When Dropping Only a Few Elements Each Time

If a List is maintained at a cap of 100 and each request pushes one element and trims, typically only one old element is removed once the list is full. However, if a List accidentally grows to millions of elements and then runs `LTRIM -100 -1`, Redis must remove a massive number of elements at once, which can cause noticeable latency.

Therefore, **enforce the bound directly on the write path** rather than relying solely on a periodic cron job to trim after data has ballooned. For huge legacy keys needing cleanup, plan an operational procedure and measure impact before bulk trimming.

## 14. Offset Pagination When the List Is Changing

`LRANGE` provides index-based pagination:

~~~text
pageIndex = 0, pageSize = 10 -> LRANGE 0 9
pageIndex = 1, pageSize = 10 -> LRANGE 10 19
pageIndex = 2, pageSize = 10 -> LRANGE 20 29
~~~

This works conveniently for a List that **rarely changes** or is short. However, if the List continuously receives new elements, offsets can cause **duplicate or skipped elements** across requests.

### 14.1. Example with LPUSH

Suppose the List stores newest → oldest:

~~~text
Initial: [F, E, D, C, B, A]
Client reads page 0, size 3 -> [F, E, D]

New message G is pushed via LPUSH:
New list: [G, F, E, D, C, B, A]

Client reads page 1, size 3 -> indices 3..5 -> [D, C, B]
~~~

Element D appears **twice** across the two pages because indices shifted right when prepending at the left end. If items are trimmed/deleted between reads, the client can also miss elements.

### 14.2. What About RPUSH Followed by LTRIM?

With RPUSH, new elements are added at the tail; trimming to keep the last N drops elements from the head, shifting the offsets of remaining elements to the left. A client reading page 1 by offset can observe the underlying dataset shift between calls.

Hence, **offset pagination on a List does not guarantee a stable snapshot** under concurrent writes/deletes. This is not a Spring Data Redis bug, but an inherent property of using positional indices over mutable data.

### 14.3. Alternatives

- If the UI only needs the "10 latest events," a single bounded `LRANGE` call is usually sufficient.
- If viewing paginated history within a stable snapshot is needed, consider pinning the result set per request/session or using a data store that supports snapshots.
- If time/ID-based pagination is needed while data changes continuously, a Redis Sorted Set with score/ID or a database supporting keyset pagination may be a better fit.
- For events requiring ID-based retrieval, consumer groups, and retention policies, Redis Streams may be a better choice than Redis Lists.
- For long-term retention and complex queries, a dedicated database is usually the primary source of truth, with Redis serving as a cache for recent pages.

Choose the tool based on **page stability, tolerance for skipped/duplicate items, and storage requirements**, not merely the convenience of `LRANGE`.

## 15. TTL and List Lifecycle Policies

`LTRIM` bounds element count; `EXPIRE` bounds **key lifetime**. The two mechanisms are independent:

~~~redis
RPUSH demo:recent:events event-1 event-2
EXPIRE demo:recent:events 3600
TTL demo:recent:events
~~~

The key can expire after one hour even if the List contains only two elements. Conversely, using only `LTRIM -100 -1` without a TTL can leave 100 elements stored in Redis for an inactive user indefinitely.

### 15.1. Do Push/Trim Preserve TTL?

For a List that already has an expiration, modifying its contents via `LPUSH`, `RPUSH`, and `LTRIM` normally **does not clear the key's TTL**. However, if `LTRIM` removes all elements and causes the key to be deleted, that key's expiration disappears as well.

If the List does not exist yet and an `RPUSH` creates a new key, the new key **does not automatically get a TTL**. You need to decide:

- **TTL from first creation:** set expiration when the key is first created, without extending it on each append.
- **TTL from last activity:** refresh expiration after every append.
- **No TTL, capped at N:** retain recent data indefinitely, requiring management of inactive keys and total memory.

### 15.2. Avoiding the Gap Between Append and Setting TTL

If you need to guarantee a TTL is set whenever a new List is created, calling separately:

~~~java
redis.opsForList().rightPush(key, value);
redis.expire(key, Duration.ofHours(1));
~~~

leaves a gap between the two commands. If the process crashes after push and before expire, the List may live indefinitely. If you call `expire(...)` every time, the TTL is continuously renewed, changing the retention policy.

You can add TTL handling to the script from Section 11:

~~~lua
local maxItems = tonumber(ARGV[2])
local ttlSeconds = tonumber(ARGV[3])
if not maxItems or maxItems < 1 or maxItems % 1 ~= 0 then
    return redis.error_reply("invalid maxItems")
end
if not ttlSeconds or ttlSeconds < 1 or ttlSeconds % 1 ~= 0 then
    return redis.error_reply("invalid ttl")
end

redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], -maxItems, -1)

if redis.call('TTL', KEYS[1]) == -1 then
    redis.call('EXPIRE', KEYS[1], ttlSeconds)
end

return redis.call('LLEN', KEYS[1])
~~~

Here `ARGV[3]` is the TTL in seconds. This implements the policy **any key without an expiration receives a TTL**. It will also assign a TTL to an existing legacy key that previously had none, so use it only in namespaces where every List is expected to expire. If you need to strictly detect "the key was newly created in this script," the logic can check `EXISTS` **before** `RPUSH`.

### 15.3. TTL Does Not Replace Trim

TTL deletes the entire key upon expiration; it does not keep the List's element count bounded while the key is alive. Conversely, LTRIM only bounds length and does not automatically clean up keys of inactive users. When both constraints are required, combine them intentionally.

## 16. Redis List and Serializer Selection

Spring Data Redis sends elements to Redis as bytes. Declaring:

~~~java
RedisTemplate<String, MessageDto> redisTemplate;
~~~

does not automatically guarantee JSON. You must configure appropriate serializers for keys and values.

### 16.1. String Lists

For short messages or IDs:

~~~java
StringRedisTemplate template = ...;
template.opsForList().rightPush("shop:recent:ids", "id-42");
template.opsForList().rightPush("shop:recent:ids", "id-43");
List<String> ids = template.opsForList()
        .range("shop:recent:ids", 0, -1);
~~~

The CLI displays elements as plain strings:

~~~redis
LRANGE shop:recent:ids 0 -1
~~~

### 16.2. JSON Object Lists

If a List holds DTOs, use a `RedisTemplate<String, MessageDto>` configured with:

- `StringRedisSerializer` for the **key**.
- A **typed** JSON serializer for `MessageDto` (matching the Spring Data Redis version in use).
- Schema and versioning rules for elements.
- JSON size limits so each `LRANGE` does not transfer excessive data.

With Spring Data Redis 3.x, typed JSON typically uses `Jackson2JsonRedisSerializer<MessageDto>`; in the Spring Data Redis 4.x line, the corresponding Jackson 3 serializer is `JacksonJsonRedisSerializer<MessageDto>`. Do not mix 3.x and 4.x imports. Redis Lists do not care whether JSON is valid; reading clients must know the value format.

### 16.3. Avoid Mixing Multiple Serializers on the Same List

If Writer A pushes String elements, Writer B writes objects with JDK serialization, and Reader C uses a JSON serializer, a single `LRANGE` call can return byte values in incompatible formats. Deserialization can fail the **entire page read** because of one element.

Every List should have a **consistent format contract**: key prefix, value type, serializer, version, and schema evolution policy. When upgrading formats, use a new namespace or an explicit migration rather than mixing element formats inside the same List.

## 17. Concurrency and Read Consistency

A single `LRANGE` command reads a slice reflecting the List state when Redis executes that command; a single `LTRIM` command modifies the List as a separate operation. However, a sequence of independent commands does not create a cross-time snapshot.

### 17.1. A Page Can Shift When the Next Request Arrives

~~~text
Request A -> LRANGE 0 9           (state T1)
Writer B  -> LPUSH newItem        (state T2)
Request A -> LRANGE 10 19         (state T3)
~~~

Pages may overlap or skip items. If the requirement is merely displaying "most recent," this is usually acceptable; if the system must report exact point-in-time results, another mechanism is needed.

### 17.2. An Atomic Script Does Not Guarantee Zero Data Loss Across Infrastructure

The `RPUSH + LTRIM` script ensures no other client interleaves between the two operations **while the script executes on the Redis server**. However, a successful write does not automatically guarantee data has been durably persisted to disk or replicated before a server failure. If data is critical, design persistence, replication, acknowledgements, backups, and reconciliation accordingly.

### 17.3. Avoid Storing Work Items That Must Be Processed in a Trimmed List

If a List acts as a queue and a worker has not yet claimed a task, `LTRIM` can delete that task simply to enforce the size cap. For rebuildable UI history, dropping old items is fine. For job processing, design proper job claiming, retries, and safeguards against dropping work.

## 18. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `LRANGE key 0 10` returns 11 elements | Stop index is inclusive | Use `0 9` to read at most 10 elements |
| Reading newest returns old elements | Using `RPUSH` then `LRANGE 0 N-1` | Read `-N -1` or switch to the LPUSH convention |
| Only old items remain after trim | Using `RPUSH` yet trimming the left end | Use `LTRIM -N -1` |
| New elements disappear after trim | Using `LPUSH` yet trimming the right end | Use `LTRIM 0 N-1` |
| Entire list gets deleted | Start > stop or start is out of range | Check index calculation and validate N |
| Cap N=0 leaves the List intact | `LTRIM key -0 -1` is equivalent to `LTRIM 0 -1` | Reject `N <= 0` or handle a no-storage policy separately |
| List occasionally exceeds N | `RPUSH` and `LTRIM` are two commands | Use a Lua script/transaction when an immediate invariant is required |
| `LLEN` returns 0; unclear if key ever existed | Redis does not retain empty Lists | Use separate metadata if distinction is needed |
| API responds slowly on large pages | `LRANGE` returns too many elements or huge payloads | Cap page size, value size, and offset |
| Pagination returns duplicate items | Writes/deletes shift indices | Use snapshots/cursors/Sorted Sets if stability is required |
| Redis reports `WRONGTYPE` | Key holds String/Hash/Set instead of List | Check `TYPE key` and namespace |
| Java deserialization fails | Writer/reader use different serializers | Standardize value format and migrations |
| Key disappears unexpectedly | TTL, eviction, emptied by LTRIM, deleted by another service | Check TTL, eviction policy, logs, and key ownership |
| List never expires | Key created by RPUSH without EXPIRE | Apply TTL at creation time, possibly via script |
| Memory grows despite capped LLEN | Too many keys or huge individual elements | Cap payload size, TTL, total keys, and monitor memory |

### 18.1. Inspection Commands with redis-cli

~~~redis
TYPE shop:feed:feed-42:recent
LLEN shop:feed:feed-42:recent
LRANGE shop:feed:feed-42:recent 0 9
LRANGE shop:feed:feed-42:recent -10 -1
TTL shop:feed:feed-42:recent
MEMORY USAGE shop:feed:feed-42:recent
SCAN 0 MATCH shop:feed:*:recent COUNT 100
~~~

`MEMORY USAGE` can help estimate the memory footprint of a key when supported by the Redis server. `SCAN` returns a cursor; to scan through everything, keep calling with the returned cursor until cursor 0.

Never run `KEYS *` on a large production keyspace, and never run `FLUSHDB`/`FLUSHALL` as a "quick fix" without understanding the scope of deleted data. When investigating issues, test `LTRIM` only on test keys or keys confirmed safe to lose elements.

## 19. Hands-on Lab: History of the 20 Most Recent Events

**Problem:** build an API that records short events per device and retains at most the 20 most recent events. The frontend can read the 5 latest events or paginate by index in the current List.

### 19.1. Data Convention

~~~text
Key:      demo:device:<deviceId>:events
Value:    each element is a String containing event information
Order:    RPUSH -> oldest on the left, newest on the right
Limit:    20 elements / device
Read latest: LRANGE key -5 -1
Cap:      RPUSH + LTRIM -20 -1 in one Lua script
~~~

If you want newest-first display, reverse the elements in the response or standardize on the LPUSH convention from the start. Do not flip the write direction while old Lists still exist without migrating the data.

### 19.2. Practice Steps

1. Start local Redis and verify `PING` returns `PONG`.
2. Create a Spring Boot app with `StringRedisTemplate` connected to Redis.
3. Create a service with an `appendEvent(deviceId, text)` method invoking the `RPUSH + LTRIM -20 -1` script.
4. Create a `latest(deviceId, 5)` method using `range(key, -5, -1)`.
5. Create a `page(deviceId, pageIndex, pageSize)` method; cap `pageSize` at 20.
6. Record 25 events numbered `event-1` through `event-25`.
7. Check `LLEN` and `LRANGE key 0 -1`; only `event-6` through `event-25` should remain.
8. Check `LRANGE key -5 -1`; expect `event-21` through `event-25` in oldest → newest order.
9. Test two concurrent writers on the same key; with the script, the List must never expose a state exceeding 20 elements between push and trim.
10. Optionally, configure a TTL according to a predefined rule so keys of inactive devices expire over time.

### 19.3. Observing Results in Redis

After executing 25 appends:

~~~redis
LLEN demo:device:d42:events
LRANGE demo:device:d42:events 0 -1
LRANGE demo:device:d42:events -5 -1
LRANGE demo:device:d42:events 0 4
TTL demo:device:d42:events
~~~

Expected logical results when no other writers or expirations interfere:

| Command | Result |
| --- | --- |
| `LLEN` | 20 |
| `LRANGE 0 -1` | `event-6` through `event-25` |
| `LRANGE -5 -1` | `event-21` through `event-25` |
| `LRANGE 0 4` | `event-6` through `event-10` |
| `TTL` | -1 if no expiration is set, or remaining seconds if TTL was set |

These are the **expected outcomes of the lab**, not output from a pre-recorded run. When investigating discrepancies, verify push direction, inclusive stop index, TTL, key name, and how the serializer writes elements.

### 19.4. Extension Exercises

**Exercise A — Newest on the left:** switch the service to `LPUSH` and `LTRIM 0 19`, then update the API reading the 5 latest events to `LRANGE 0 4`. Explain why reversing the returned list is no longer needed.

**Exercise B — Byte size limits:** if a single event can be 1 MB long, propose how to bound the payload size or store only IDs in the List and read details from another source.

**Exercise C — Pagination during concurrent writes:** have the frontend read page 0 and page 1 while the device continues sending events. Observe duplicates/omissions, then explain why offset pagination does not guarantee a stable snapshot.

**Exercise D — TTL:** design the List to expire 24 hours after the first event, or 24 hours after the most recent event. Compare how TTL is set and the impact on data.

**Exercise E — Data that must not be lost:** change the requirement: every event must be processed reliably by ID, with retries when a worker fails. Explain why Redis Streams or a message broker should be evaluated instead of using only a trimmed Redis List.

## 20. Self-Review Questions

1. When using `LPUSH`, at which index does the new element land? What about `RPUSH`?
2. How many elements at most does `LRANGE key 0 9` return? Why?
3. Which element does `LRANGE key -1 -1` retrieve?
4. From which end of the list do negative indices count in a Redis List?
5. Why does `LRANGE key -3 -1` not automatically reverse element order?
6. What happens when `start > stop` or start exceeds the List length?
7. How does `LRANGE` differ from `LPOP`/`RPOP` in terms of mutating the List?
8. What advantage does `LLEN` have over reading the whole List and counting elements in Java?
9. Does `opsForList().range(key, start, end)` treat `end` as exclusive?
10. Does `LTRIM key 1 3` delete elements 1..3 or keep them?
11. To keep the 100 newest elements after `RPUSH`, what `LTRIM` range should be used?
12. To keep the 100 newest elements after `LPUSH`, what range should be used?
13. Why is `LTRIM key -0 -1` not a way to delete the entire List?
14. If `RPUSH` and `LTRIM` run separately, what intermediate state can a reader observe?
15. Does pipelining turn two push/trim commands into a single atomic operation?
16. How does a Lua script guarantee the List size limit in a single operation?
17. If a List is always capped at 100 elements, why can Redis still consume a lot of RAM?
18. Why can reading page 1 after a new element is pushed via `LPUSH` duplicate an element from page 0?
19. How do `TTL` and `LTRIM` govern two different aspects of a List's lifecycle?
20. Does Redis keep an empty List key after `LTRIM` removes all elements?
21. In what scenarios are Sorted Sets/Streams or a database better suited than a List with offset pagination?
22. If the code uses `RedisTemplate<String, MyDto>`, what determines the byte format of each List element?

## 21. References

- [Redis — LRANGE](https://redis.io/docs/latest/commands/lrange/): start/stop indices, negative indices, result bounds, and complexity.
- [Redis — LTRIM](https://redis.io/docs/latest/commands/ltrim/): keeping a range of elements and implementing bounded lists.
- [Redis — LLEN](https://redis.io/docs/latest/commands/llen/): getting element count in O(1) complexity.
- [Redis — LPUSH](https://redis.io/docs/latest/commands/lpush/) and [RPUSH](https://redis.io/docs/latest/commands/rpush/): adding elements at both ends of a List.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/) and [TTL](https://redis.io/docs/latest/commands/ttl/): managing key time-to-live.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): combining operations in a server-side Redis Lua script.
- [Spring Data Redis Reference — Redis support](https://docs.spring.io/spring-data/redis/reference/redis.html): working with Redis via templates and data structures.
- [Spring Data Redis — ListOperations JavaDoc](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/ListOperations.html): `range`, `trim`, `size`, `leftPush`, and `rightPush` APIs.

**Key Takeaways:** `LRANGE` reads an **inclusive range covering both start and stop**; `LLEN` retrieves the length without loading elements; `LTRIM` **keeps the specified range and deletes everything else**. To retain the N newest elements, keep the write direction consistent: **`LPUSH + LTRIM 0 N-1`** or **`RPUSH + LTRIM -N -1`**. When the cap is a strict invariant at every moment, combine push and trim using a Lua script or an appropriate transaction; at the same time, control per-element payload size, TTL, and pagination stability when the List changes continuously.
