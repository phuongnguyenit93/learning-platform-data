# Using BoundOperations for Sequences of Operations on the Same Key

In Spring Data Redis, ordinary operations typically start from `RedisTemplate` or `StringRedisTemplate`:

~~~java
redis.opsForValue().set("session:42", "ACTIVE");
String state = redis.opsForValue().get("session:42");
redis.expire("session:42", Duration.ofMinutes(15));
~~~

This style is valid and clear. However, when a method performs multiple operations **on the exact same Redis key**, repeating the key name several times is verbose and makes typos or accidental key mismatches easier. Spring Data Redis provides the **BoundOperations** family to bind an operations object to a fixed key.

Example expressing the same idea with `BoundValueOperations`:

~~~java
BoundValueOperations<String, String> session =
        redis.boundValueOps("session:42");

session.set("ACTIVE");
String state = session.get();
session.expire(Duration.ofMinutes(15));
~~~

The difference lies in **how the Java-side API is organized**:

- With `opsForValue()`, the key is passed to every method such as `set(key, value)` or `get(key)`.
- With `boundValueOps(key)`, the key is chosen when creating the bound operations object; subsequent operations reuse that same key.
- Calls are still translated into **Redis commands** sent to the **Redis Server**. BoundOperations is not an in-JVM data copy, does not automatically open a transaction, and does not automatically batch commands into a single send.

This lesson covers **when to bind a key, how to use each type of BoundOperations, and the limits to keep in mind when running command sequences**.

## 1. "Bound" Means Attaching Operations to a Key

The name *BoundOperations* can be understood as **operations bound to a key**: an object holding the context of a single key so each method operates on that key without taking the key parameter again.

~~~text
                   Spring Boot Service
                          |
                          | boundHashOps("cart:42")
                          v
               BoundHashOperations
                 key = "cart:42"
                    /    |    \
                   /     |     \
             put(...) get(...) entries()
                   \     |     /
                    \    |    /
                          v
                     RedisTemplate
                          |
                  RedisConnectionFactory
                          |
                   Lettuce / Jedis
                          |
                     Redis Server
                     key: cart:42
~~~

Each call in the diagram is processed by Spring Data Redis into the corresponding Redis command. The Redis Server holds the actual data; BoundOperations simply offers a **convenient API for the same key**.

Example:

~~~java
BoundHashOperations<String, String, String> cart =
        redis.boundHashOps("cart:42");

cart.put("SKU-A", "2");           // HSET cart:42 SKU-A 2
cart.put("SKU-B", "1");           // HSET cart:42 SKU-B 1
String quantity = cart.get("SKU-A"); // HGET cart:42 SKU-A
~~~

The key name `cart:42` appears once when constructing the object. Both write commands and the read command target the **same Redis Hash**.

### BoundOperations Does Not "Lock" the Redis Key

The word *bound* **does not mean** a distributed lock. Nor does it mean:

- Holding a dedicated TCP connection throughout the object's lifetime.
- Reading the key once and caching data on the Java heap.
- Guaranteeing the key will not be deleted or expire between commands.
- Making the sequence `put() → get() → expire()` atomic.
- Preventing another Spring Boot instance from modifying the same key.

If another application deletes `cart:42`, a subsequent `cart.get("SKU-A")` call can still return `null`. If the key is recreated with a different data type, Hash operations can encounter a `WRONGTYPE` error.

## 2. Commonly Used BoundOperations Types

`RedisTemplate<K, V>` exposes several bound operation entry points. The table below lists common forms; exact generics vary by data type.

| Factory method | Returned interface | Redis type | Common commands/use cases |
|---|---|---|---|
| `boundValueOps(key)` | `BoundValueOperations<K, V>` | String | SET, GET, INCR, append |
| `boundHashOps(key)` | `BoundHashOperations<K, HK, HV>` | Hash | HSET, HGET, HDEL, HGETALL |
| `boundListOps(key)` | `BoundListOperations<K, V>` | List | LPUSH, RPUSH, LPOP, LRANGE |
| `boundSetOps(key)` | `BoundSetOperations<K, V>` | Set | SADD, SISMEMBER, SMEMBERS, SREM |
| `boundZSetOps(key)` | `BoundZSetOperations<K, V>` | Sorted Set | ZADD, ZSCORE, ZREVRANGE |

In the table, `K` is the Redis key type, `V` is the value type, and `HK` and `HV` are the Java types for hash field and hash value.

Exact APIs and overloads should be verified against the Spring Data Redis version in use. The following examples focus on foundational operations and use `StringRedisTemplate` so keys, hash fields, and values are handled as strings.

## 3. Setting Up Spring Boot and StringRedisTemplate

With Spring Boot 3.x and Gradle, the application can include:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Example `application.yml` when Redis Server runs on the development machine:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

The starter brings Spring Data Redis and a Redis driver (usually Lettuce by default) into the application. **Redis Server must still run separately**; the starter does not supply a Redis Server.

`StringRedisTemplate` is auto-configured by Spring Boot when the required conditions are satisfied. It uses string serializers for keys/values, making it suitable for foundational exercises. Example:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisExampleService {

    private final StringRedisTemplate redis;

    public RedisExampleService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    // BoundOperations examples will use this redis bean.
}
~~~

### Distinguishing RedisTemplate and StringRedisTemplate

`RedisTemplate<K, V>` can be configured with serializers for Java objects as needed. `StringRedisTemplate` is a convenient specialization for Strings. Binding a key **does not change the serializer**:

~~~text
StringRedisTemplate + boundHashOps("cart:42")
    -> string key and field/value according to the template's serializers

RedisTemplate<String, SomeObject> + boundValueOps("object:42")
    -> uses the serializers configured on RedisTemplate
~~~

If one service writes a key using a different serializer, another service cannot automatically read that key as a plain string. BoundOperations only fixes **the key at the API layer**; it does not change Redis byte encoding.

## 4. BoundValueOperations: Multiple Operations on the Same String Key

Suppose you need to store session state. The business operations are:

1. Write the session state.
2. Read the state back.
3. Update the state on new activity.
4. Check/delete data according to the session lifecycle.

### 4.1. Written with Standard OpsForValue

~~~java
String key = "session:status:" + sessionId;

redis.opsForValue().set(
        key, "ACTIVE", Duration.ofMinutes(15));

String current = redis.opsForValue().get(key);

redis.opsForValue().set(
        key, "IDLE", Duration.ofMinutes(15));
~~~

### 4.2. Written with BoundValueOperations

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.BoundValueOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionStatusStore {

    private static final Duration SESSION_TTL =
            Duration.ofMinutes(15);

    private final StringRedisTemplate redis;

    public SessionStatusStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void activate(String sessionId) {
        BoundValueOperations<String, String> session =
                redis.boundValueOps(keyFor(sessionId));

        // Write value and TTL using a single SET operation with expiration.
        session.set("ACTIVE", SESSION_TTL);
    }

    public String getStatus(String sessionId) {
        BoundValueOperations<String, String> session =
                redis.boundValueOps(keyFor(sessionId));
        return session.get();
    }

    public void markIdle(String sessionId) {
        BoundValueOperations<String, String> session =
                redis.boundValueOps(keyFor(sessionId));
        session.set("IDLE", SESSION_TTL);
    }

    private String keyFor(String sessionId) {
        return "session:status:" + sessionId;
    }
}
~~~

Here, a method can obtain the bound operations object and invoke subsequent operations **without passing the key again**. Key construction is also centralized in `keyFor(...)`, reducing the risk of namespace mistakes.

### 4.3. BoundValueOperations with Counters

Redis supports the `INCR` command to increment an integer atomically **at the command level**.

~~~java
import org.springframework.data.redis.core.BoundValueOperations;

public long incrementPageViews(
        StringRedisTemplate redis,
        String pageId) {

    BoundValueOperations<String, String> views =
            redis.boundValueOps("page:views:" + pageId);

    Long next = views.increment();
    if (next == null) {
        throw new IllegalStateException(
                "Redis did not return a counter result");
    }
    return next;
}
~~~

Command mechanism:

~~~text
boundValueOps("page:views:home")
             |
             +-- increment() -> INCR page:views:home
             +-- increment() -> INCR page:views:home
             +-- get()       -> GET  page:views:home
~~~

The advantage of BoundOperations here is **stable key context**. The atomicity of the increment itself comes from the **Redis Server's INCR command**, not from using `BoundValueOperations`.

## 5. TTL with BoundOperations: Convenient, but Understand the Semantics

Many BoundOperations expose key-management operations via shared inheritance, such as `expire(Duration)`. For example:

~~~java
BoundValueOperations<String, String> token =
        redis.boundValueOps("demo:token:123");

token.set("PENDING");
token.expire(Duration.ofMinutes(5));
~~~

This example issues **two Redis commands**:

~~~text
SET demo:token:123 PENDING
EXPIRE demo:token:123 300
~~~

A failure can happen between the two commands. If `SET` succeeds and the application stops before `EXPIRE`, the key may be left without a TTL. Therefore, when a **String value must have a TTL immediately on write**, prefer the overload combining write and expiration:

~~~java
token.set("PENDING", Duration.ofMinutes(5));
~~~

This asks Redis to perform the equivalent of a single `SET ... EX ...`, avoiding a gap between writing and setting the TTL.

### 5.1. Do Not Assume Every Update Command Preserves TTL

TTL behavior depends on the Redis command type:

- A plain String `SET key value` **removes any existing TTL**, unless options to preserve TTL or assign a new TTL are used in the command.
- `SET key value EX ...` replaces the value and sets the requested TTL.
- `HSET` adding or updating fields on an existing Hash **does not automatically extend the TTL** of the whole Hash.
- `INCR` on a String key that already has a TTL typically **preserves the existing TTL**; creating a new key with `INCR` does not automatically assign a TTL.
- When a key expires, the Java-side BoundOperations object still exists, but subsequent commands operate on a key that **is already gone**.

Thus, for sessions needing *sliding expiration*, the code must decide which operations refresh TTL and issue the appropriate commands. Never treat binding a key as giving the key an automatic lifecycle.

### 5.2. Two Commands Do Not Automatically Form an Atomic Operation

~~~java
Long count = counter.increment();
counter.expire(Duration.ofMinutes(10));
~~~

These remain two separate commands. If you need to set a TTL **only on the first increment** atomically, you must design a suitable mechanism such as a Lua script or a Redis transaction/conditional solution; using BoundOperations does not solve race conditions by itself.

## 6. BoundHashOperations: Operating on Multiple Fields of a Single Hash Key

A very natural fit for BoundOperations is **one Hash per object or aggregate**, because multiple operations target the same Redis key while varying the field.

Suppose user 42's shopping cart is stored in a Redis Hash:

~~~text
Key: cart:42
Type: Hash
Fields:
    SKU-101 -> "2"
    SKU-205 -> "1"
    SKU-310 -> "4"
~~~

### 6.1. Code with BoundHashOperations

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.data.redis.core.BoundHashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartStore {

    private static final Duration CART_TTL =
            Duration.ofMinutes(30);

    private final StringRedisTemplate redis;

    public CartStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void addItem(String userId, String sku, int quantity) {
        BoundHashOperations<String, String, String> cart =
                redis.boundHashOps(cartKey(userId));

        cart.put(sku, Integer.toString(quantity));
        cart.expire(CART_TTL);
    }

    public String getQuantity(String userId, String sku) {
        BoundHashOperations<String, String, String> cart =
                redis.boundHashOps(cartKey(userId));

        return cart.get(sku);
    }

    public Map<String, String> getCart(String userId) {
        BoundHashOperations<String, String, String> cart =
                redis.boundHashOps(cartKey(userId));

        return cart.entries();
    }

    public void removeItem(String userId, String sku) {
        BoundHashOperations<String, String, String> cart =
                redis.boundHashOps(cartKey(userId));

        cart.delete(sku);
    }

    public void removeCart(String userId) {
        redis.delete(cartKey(userId));
    }

    private String cartKey(String userId) {
        return "cart:" + userId;
    }
}
~~~

This snippet illustrates a **per-user Hash key** boundary:

| Java Method | Equivalent Redis Command | Affected Scope |
|---|---|---|
| `cart.put("SKU-101", "2")` | `HSET cart:42 SKU-101 2` | One field |
| `cart.get("SKU-101")` | `HGET cart:42 SKU-101` | One field |
| `cart.entries()` | `HGETALL cart:42` | Entire Hash |
| `cart.delete("SKU-101")` | `HDEL cart:42 SKU-101` | One field |
| `cart.expire(Duration...)` | `EXPIRE cart:42 ...` | TTL of the Hash key |
| `redis.delete("cart:42")` | `DEL cart:42` | Entire Hash |

### 6.2. When Does BoundHashOperations Shine Most?

When a method needs to read or modify several fields of the **same aggregate**:

~~~java
BoundHashOperations<String, String, String> profile =
        redis.boundHashOps("profile:42");

profile.put("displayName", "Lan");
profile.put("locale", "vi-VN");
profile.put("theme", "dark");

String theme = profile.get("theme");
Map<String, String> allFields = profile.entries();
~~~

Instead of passing `"profile:42"` on every call, each line only specifies the field. This makes it obvious that the operations act on **a single logical object**.

### 6.3. Notes on TTL and Concurrent Updates

`cart.put(...)` and `cart.expire(...)` in the example are **two Redis commands**. If the requirement states "every update must apply TTL atomically," use an appropriate transaction or script. Additionally:

- Two services can update **two different fields** of the same Hash without rewriting an entire JSON blob.
- If business logic requires updating **multiple fields together** under an invariant, consecutive `put` calls are not atomic as a group.
- `entries()` reads the entire Hash; if a Hash has a very large number of fields, prefer reading only needed fields or using an appropriate scan/pagination mechanism to avoid huge payloads per request.

**BoundHashOperations is an API for working with a Hash key, not a transactional lock over that Hash.**

## 7. BoundListOperations: One List with Multiple Operations

A Redis List is commonly used when an ordered sequence of values is needed. For example, a recent notifications list per user:

~~~text
Key: notifications:user42
Type: List
Items:
  event-C
  event-B
  event-A
~~~

### 7.1. Example Using BoundListOperations

~~~java
import java.util.List;

import org.springframework.data.redis.core.BoundListOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RecentNotificationStore {

    private final StringRedisTemplate redis;

    public RecentNotificationStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void push(String userId, String eventId) {
        BoundListOperations<String, String> notifications =
                redis.boundListOps(key(userId));

        // New elements are added on the left (head of the List).
        notifications.leftPush(eventId);

        // Keep at most 100 elements, indexes 0..99.
        notifications.trim(0, 99);
    }

    public List<String> recent(String userId, long limit) {
        if (limit <= 0) {
            return List.of();
        }

        BoundListOperations<String, String> notifications =
                redis.boundListOps(key(userId));

        List<String> values = notifications.range(0, limit - 1);
        return values == null ? List.of() : values;
    }

    private String key(String userId) {
        return "notifications:" + userId;
    }
}
~~~

Here, `leftPush` and `trim` operate on the same List key. Each Redis command keeps its own semantics:

~~~text
LPUSH notifications:42 event-C
LTRIM notifications:42 0 99
~~~

**Important reminder:** these are two separate commands. If multiple publishers push notifications concurrently, commands can interleave between `LPUSH` and `LTRIM`; if the size cap must be enforced atomically with the write, use a Lua script or an equivalent mechanism.

### 7.2. Blocking List Operations Do Not Change Just Because You Use BoundOperations

List APIs may support timeout-based pop operations corresponding to `BLPOP`/`BRPOP` depending on the method. For example, `rightPop(Duration.ofSeconds(5))` can wait when the List is empty:

~~~java
BoundListOperations<String, String> queue =
        redis.boundListOps("jobs:pending");

String jobId = queue.rightPop(Duration.ofSeconds(5));

if (jobId == null) {
    // Wait timeout elapsed with no job available.
}
~~~

BoundOperations still only fixes the key. **Blocking calls still block the calling thread** in the synchronous API and may require dedicated connections depending on the driver/factory. Do not invoke synchronous blocking operations directly on a WebFlux event loop; use an appropriate worker/executor or a reactive API instead.

If using a List as a queue, also design error recovery: an item popped from the List is not automatically returned to the queue if the consumer crashes. BoundOperations adds neither acknowledgments nor retries.

## 8. BoundSetOperations: Managing Unique Element Sets

For instance, each course has a set of enrolled users:

~~~text
Key: course:redis:members
Type: Set
Members:
  user-42
  user-57
  user-91
~~~

### 8.1. Operating on the Same Redis Set

~~~java
import java.util.Set;

import org.springframework.data.redis.core.BoundSetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CourseMemberStore {

    private final StringRedisTemplate redis;

    public CourseMemberStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void enroll(String courseId, String userId) {
        BoundSetOperations<String, String> members =
                redis.boundSetOps("course:" + courseId + ":members");
        members.add(userId);
    }

    public boolean isEnrolled(String courseId, String userId) {
        BoundSetOperations<String, String> members =
                redis.boundSetOps("course:" + courseId + ":members");

        return Boolean.TRUE.equals(members.isMember(userId));
    }

    public void leave(String courseId, String userId) {
        BoundSetOperations<String, String> members =
                redis.boundSetOps("course:" + courseId + ":members");
        members.remove(userId);
    }

    public Set<String> getMembers(String courseId) {
        BoundSetOperations<String, String> members =
                redis.boundSetOps("course:" + courseId + ":members");
        return members.members();
    }
}
~~~

Benefits:

- `add(...)` adds a member; by definition, a Redis Set stores no duplicate values.
- `isMember(...)` checks whether a user belongs to the Set.
- `remove(...)` removes a member.
- `members()` returns the set of members, suitable when set size is bounded.

For very large sets, `members()` can transfer massive payloads; consider scanning/pagination or changing the storage layout based on access patterns. Binding the key does not eliminate the cost of reading the whole Set.

### 8.2. Set Differs from List

If you need **unique membership checks**, Set fits. If you need to preserve **order and duplicate occurrences**, List has different semantics. BoundOperations is merely an API matching the chosen data structure; choosing the wrong Redis type cannot be fixed by binding the key.

## 9. BoundZSetOperations: Leaderboards on the Same Key

A Redis Sorted Set pairs each member with a score. For example, a daily leaderboard:

~~~text
Key: leaderboard:2026-11-12
Type: Sorted Set
Members / Scores:
  user-42 -> 120.0
  user-57 -> 87.5
  user-91 -> 150.0
~~~

### 9.1. Working with BoundZSetOperations

~~~java
import java.util.Set;

import org.springframework.data.redis.core.BoundZSetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardStore {

    private final StringRedisTemplate redis;

    public LeaderboardStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private BoundZSetOperations<String, String> board(String day) {
        return redis.boundZSetOps("leaderboard:" + day);
    }

    public void recordScore(
            String day,
            String userId,
            double score) {
        board(day).add(userId, score);
    }

    public Double scoreOf(String day, String userId) {
        return board(day).score(userId);
    }

    public Set<String> topTen(String day) {
        return board(day).reverseRange(0, 9);
    }

    public void removeUser(String day, String userId) {
        board(day).remove(userId);
    }
}
~~~

Equivalent commands:

~~~text
ZADD leaderboard:2026-11-12 120.0 user-42
ZSCORE leaderboard:2026-11-12 user-42
ZREVRANGE leaderboard:2026-11-12 0 9
ZREM leaderboard:2026-11-12 user-42
~~~

Note: `add(member, score)` typically sets the provided score; **it does not mean adding to the existing score**. If business logic requires adding a delta atomically, use the corresponding increment operation (such as `incrementScore(...)`) rather than reading the score, adding in Java, and writing back.

BoundZSetOperations is convenient because all operations on one leaderboard target the same Redis key, but if a leaderboard grows unboundedly you must define a retention policy, cap member counts, or partition by day/tenant. A very large Sorted Set is still a single key living in a single hash slot under Redis Cluster.

## 10. Comparing BoundOperations with `opsFor...` APIs

Both approaches **operate on the exact same Redis data** when the template, key, and arguments match:

| Using template directly | Using bound operations | Equivalent Redis command |
|---|---|---|
| `redis.opsForValue().get(key)` | `redis.boundValueOps(key).get()` | GET |
| `redis.opsForValue().set(key, value)` | `redis.boundValueOps(key).set(value)` | SET |
| `redis.opsForHash().put(key, field, value)` | `redis.boundHashOps(key).put(field, value)` | HSET |
| `redis.opsForHash().get(key, field)` | `redis.boundHashOps(key).get(field)` | HGET |
| `redis.opsForList().leftPush(key, value)` | `redis.boundListOps(key).leftPush(value)` | LPUSH |
| `redis.opsForSet().add(key, member)` | `redis.boundSetOps(key).add(member)` | SADD |
| `redis.opsForZSet().add(key, member, score)` | `redis.boundZSetOps(key).add(member, score)` | ZADD |

Notably, **the difference is mainly in expressing intent and code structure**:

~~~java
// Using OpsForHash: key is passed every time.
redis.opsForHash().put(cartKey, "SKU-A", "2");
redis.opsForHash().put(cartKey, "SKU-B", "1");
redis.opsForHash().get(cartKey, "SKU-A");

// Using BoundHashOperations: expresses the same aggregate.
BoundHashOperations<String, String, String> cart =
        redis.boundHashOps(cartKey);
cart.put("SKU-A", "2");
cart.put("SKU-B", "1");
cart.get("SKU-A");
~~~

Do not assume switching to BoundOperations will:

- Collapse three Redis commands into one command.
- Save three network round-trips by automatically enabling pipelining.
- Hold a single physical RedisConnection across all three commands.
- Make all operations atomic together.
- Automatically speed up Redis server processing.

To reduce round-trips, consider **batch-capable Redis commands**, `RedisTemplate.executePipelined(...)`, or restructuring commands. To achieve atomicity, use an atomic Redis command, transaction, or script as required. BoundOperations does not replace those mechanisms.

## 11. When to Create and Hold BoundOperations

A key-bound BoundOperations object is created as follows:

~~~java
BoundValueOperations<String, String> bound =
        redis.boundValueOps("session:42");
~~~

This is a Java-side API object. **It does not mean the Redis Server has allocated the key**, nor does it mean a network connection has been opened simply because you bound a key.

### 11.1. Prefer Creating Within a Business Scope

For instance, when handling a request to update a cart:

~~~java
public void changeCart(String userId) {
    String cartKey = "cart:" + userId;
    BoundHashOperations<String, String, String> cart =
            redis.boundHashOps(cartKey);

    cart.put("SKU-A", "3");
    cart.put("SKU-B", "1");
    String count = cart.get("SKU-A");
}
~~~

A local variable `cart` both shortens the code and shows reviewers that every operation works on the **same cart**.

### 11.2. Avoid Binding a Single User's Key Inside a Singleton Service

Problematic design:

~~~java
@Service
public class WrongCartStore {

    private final BoundHashOperations<String, String, String> cart;

    public WrongCartStore(StringRedisTemplate redis) {
        // Every subsequent request operates on user 42's cart.
        this.cart = redis.boundHashOps("cart:42");
    }
}
~~~

When a service handles multiple users, a bound operations field hardcoded to `cart:42` causes requests to mistakenly write to user 42's cart. A better design is holding the **template/factory** in the singleton and creating BoundOperations with the key resolved for the **current request/context**.

If a key is genuinely a shared, immutable service-level key (such as an intentionally designed global counter), holding a BoundOperations object for that key can be reasonable. The issue is not object creation itself, but **key correctness and concurrent usage**.

### 11.3. Do Not Manage RedisConnection Manually Just Because You Use BoundOperations

For routine operations, the template manages borrowing and returning connections via `RedisConnectionFactory`. You do not need:

~~~java
// No need to obtain a connection manually for ordinary boundValueOps examples.
RedisConnection conn = connectionFactory.getConnection();
~~~

Use the template/bound API within Spring's lifecycle. When low-level callbacks, transactions, or pipelines are needed, follow the template's APIs and corresponding connection-management rules.

## 12. BoundOperations Does Not Create a Transaction or Snapshot

This is the most important limitation to understand in this lesson.

Suppose:

~~~java
BoundValueOperations<String, String> balance =
        redis.boundValueOps("balance:user42");

String current = balance.get();
long next = Long.parseLong(current) - 100;
balance.set(Long.toString(next));
~~~

This is still:

~~~text
GET balance:user42
(Java subtracts 100)
SET balance:user42 newValue
~~~

Two application instances can read the same initial balance and overwrite each other's result. Using the **same BoundValueOperations object** inside a method does not make that sequence atomic.

### 12.1. Use Atomic Commands Whenever Possible

If the requirement is simply incrementing/decrementing a counter, replace the read–modify–write sequence with the corresponding Redis operation:

~~~java
BoundValueOperations<String, String> counter =
        redis.boundValueOps("stock:SKU-A");

Long remaining = counter.decrement();
~~~

With a valid numeric data type, Redis executes the decrement/increment atomically on the server. **However**: an atomic decrement can still drive stock negative; if business rules mandate "only decrement while enough stock remains," an atomic condition via a Lua script or suitable mechanism is required—you cannot rely solely on `decrement`.

### 12.2. Multi-Field/Multi-Command Sequences Need Their Own Mechanism

Example:

~~~java
BoundHashOperations<String, String, String> order =
        redis.boundHashOps("order:42");

order.put("status", "PAID");
order.put("paidAt", "2026-11-12T10:00:00Z");
order.expire(Duration.ofDays(7));
~~~

These operations do not become a single command just because they share `order`. If "status and paidAt must always be updated together," look at:

- A Hash operation that writes multiple fields in **a single HSET command** when that satisfies the invariant.
- A Redis `MULTI/EXEC` transaction with appropriate semantics and constraints.
- A Lua script executed on the Redis Server when conditional/atomic logic is required.

If both a relational database and Redis participate in a workflow, BoundOperations also **does not** create a distributed transaction across both systems.

## 13. BoundOperations and Pipelining Are Different

Suppose you need to write 1,000 fields of **one** Hash. Two approaches:

**Approach 1 — Many calls on one bound operations object:**

~~~java
BoundHashOperations<String, String, String> batch =
        redis.boundHashOps("batch:example");

for (int i = 0; i < 1000; i++) {
    batch.put("field-" + i, "value-" + i);
}
~~~

This issues many `HSET` calls. BoundOperations avoids repeating the key 1,000 times in code, but **does not automatically reduce round-trips**.

**Approach 2 — A single multi-field HSET** when the data is already assembled:

~~~java
Map<String, String> fields = Map.of(
        "field-1", "value-1",
        "field-2", "value-2",
        "field-3", "value-3"
);

BoundHashOperations<String, String, String> batch =
        redis.boundHashOps("batch:example");

batch.putAll(fields);
~~~

`putAll(...)` updates multiple fields in a single Hash operation via Spring Data Redis's API, suitable when the field count and payload size are reasonable.

When work spans multiple keys or multiple commands without a direct batch form, `RedisTemplate.executePipelined(...)` can cut round-trip overhead. Pipelines **are not atomic transactions**, and certain methods called inside a pipeline have different return-value semantics than standalone calls.

### 13.1. When to Use Which Tool?

| Need | Suitable tool |
|---|---|
| Multiple operations on the same key, readable code | BoundOperations |
| Writing multiple fields of the same Hash at once | `BoundHashOperations.putAll(...)` / HashOperations |
| Reading multiple fields of a Hash at once | `multiGet(...)` on Hash operations |
| Sending many commands to reduce round-trips | Pipeline, batch commands |
| Multiple commands that must be atomic under Redis semantics | Atomic command, transaction, or Lua script |
| Commands across different keys | Standard `opsFor...` or separate bound operations per key |

These options can be combined, provided you respect the lifecycle and APIs supported by Spring Data Redis. Binding a key does not remove the need to handle concurrency, transactions, or performance.

## 14. Key Design and BoundOperations Objects

When choosing BoundOperations, name keys cleanly by aggregate:

~~~text
profile:user:42
cart:user:42
session:status:42
course:redis:members
leaderboard:2026-11-12
~~~

Then code reflects the same context:

~~~java
String key = "profile:user:" + userId;
BoundHashOperations<String, String, String> profile =
        redis.boundHashOps(key);

profile.put("locale", "vi-VN");
profile.put("theme", "dark");
~~~

Key considerations:

1. **Do not embed sensitive data directly in key names** (passwords, secret tokens, unnecessary personal data).
2. **Do not access another user's key** due to ID mix-ups or broken authorization checks. Redis APIs do not enforce application-level authorization by userId.
3. Choose consistent prefixes and naming conventions so String/Hash/List keys are not mixed by type.
4. For multi-tenant systems, design appropriate namespaces/ACLs; BoundOperations does not isolate tenants automatically.
5. With Redis Cluster, the entire contents of **one key** reside in one hash slot. Using bound operations does not distribute a huge key across multiple shards.

### 14.1. BoundOperations Is Not Meant for Rapidly Changing Keys

If processing 1,000 users where each user has a separate key, writing:

~~~java
for (String userId : userIds) {
    BoundValueOperations<String, String> state =
            redis.boundValueOps("state:" + userId);
    state.set("ACTIVE");
}
~~~

is valid, yet here the bound object is created for just a single command before being discarded. A direct call can be shorter and clearer:

~~~java
for (String userId : userIds) {
    redis.opsForValue().set("state:" + userId, "ACTIVE");
}
~~~

If bulk write throughput across many keys is needed, look at batching/pipelining or data modeling rather than assuming creating BoundOperations makes it faster.

## 15. Distinguishing BoundOperations Mistakes from Data/Redis Errors

| Symptom | Cause to check | How to handle |
|---|---|---|
| `boundHashOps(key).get(field)` returns `null` | Key/field does not exist or has expired | Check key name, field, and TTL |
| Calling `boundHashOps` on a key previously used with `boundValueOps` throws `WRONGTYPE` | The key on the server is a String, not a Hash | Choose consistent key namespaces and data types |
| `get()` sees an old value even though code just called `set()` on another branch | Concurrent overwrite, another endpoint, read timing, cache/replica logic | Inspect access patterns, concurrency, and topology |
| Replacing `set(value, Duration)` with `set(value)` drops the TTL | SET without TTL usually clears previous expiration | Set TTL inside SET or use appropriate options |
| `put()` followed by `expire()` occasionally leaves a key without TTL | Two non-atomic commands or interrupted execution | Use an atomic solution when TTL is a strict invariant |
| Code binds a key but Redis has no key | Creating a bound object does not execute a write command | Invoke a write operation; check the result |
| A singleton writes every user's data into the same key | BoundOperations initialized with a fixed key at the wrong scope | Create bound objects per user/request |
| `entries()` or `members()` is slow | Collection is too large or fetching everything at once | Read selectively, scan safely, bound collection sizes |
| GET/SET timeouts | Connectivity, Redis Server, driver/pool, or network | Diagnose RedisConnectionFailure/timeouts at the proper layer |
| Unreadable bytes/strings returned | Mismatched serializers/key encodings across clients | Check template serializers and namespaces |

### 15.1. WRONGTYPE Example

~~~bash
SET demo:mixed hello
HGET demo:mixed field
~~~

The Redis Server returns an error because `demo:mixed` is currently a **String**, yet the client sent a **Hash** command. Similarly, if Spring code binds:

~~~java
redis.boundValueOps("demo:mixed").set("hello");
redis.boundHashOps("demo:mixed").put("field", "value");
~~~

using BoundOperations does not automatically convert a String key into a Hash. Design clear key prefixes or manage data migrations explicitly.

### 15.2. Key Expiring Mid-Sequence

~~~text
T0: boundHashOps("cart:42")
T1: HSET cart:42 SKU-A 2
T2: EXPIRE cart:42 1
T3: (1 second elapses; Redis deletes the key)
T4: HGET cart:42 SKU-A -> nil
~~~

The `cart` object in Java can still be called at T4, even though the Redis Server has already deleted the key. **Bound does not mean pinning the key in Redis memory**.

## 16. Hands-On Lab: One Cart, One BoundHashOperations

To see the "same key" idea clearly, try a small lab runnable in a service or test. Redis Server must be running and the application must have `StringRedisTemplate` configured.

### 16.1. Illustrative Code

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.UUID;

import org.springframework.data.redis.core.BoundHashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartBoundDemo {

    private final StringRedisTemplate redis;

    public CartBoundDemo(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void demonstrate() {
        String key = "demo:cart:" + UUID.randomUUID();
        BoundHashOperations<String, String, String> cart =
                redis.boundHashOps(key);

        try {
            cart.put("SKU-A", "2");
            cart.put("SKU-B", "1");
            cart.expire(Duration.ofMinutes(2));

            String quantityA = cart.get("SKU-A");
            Map<String, String> allItems = cart.entries();

            System.out.println("Quantity SKU-A = " + quantityA);
            System.out.println("Cart items = " + allItems);

            cart.delete("SKU-B");
            System.out.println("After remove = " + cart.entries());
        } finally {
            redis.delete(key);
        }
    }
}
~~~

**How to read the output:**

- After calling `put(...)` twice, the Hash key has two fields.
- `cart.get("SKU-A")` normally returns `"2"`.
- `cart.entries()` returns a map with both fields assuming no competing writes/deletes/expirations outside the example.
- After `cart.delete("SKU-B")`, the map retains `SKU-A`.
- Finally, `redis.delete(key)` cleans up the demo key; this is a whole-key operation.

Generating the key with a UUID avoids colliding with business data. The two-minute TTL acts as a safety net if execution stops before cleanup.

**Note:** this is a simple operational example. Calling `put(...)` twice and `expire(...)` still issues separate commands, not a single transaction.

### 16.2. Verifying with redis-cli

While the example keeps the key alive, the corresponding Redis commands are:

~~~bash
HSET demo:cart:example SKU-A 2
HSET demo:cart:example SKU-B 1
HGET demo:cart:example SKU-A
HGETALL demo:cart:example
HDEL demo:cart:example SKU-B
EXPIRE demo:cart:example 120
TTL demo:cart:example
DEL demo:cart:example
~~~

The name `demo:cart:example` is used for manual inspection via redis-cli, separate from the random key in the Java code. They follow the same Redis semantics, though **they are not the same actual key** unless you deliberately change the name during the lab.

### 16.3. Modifying the Lab Yourself

Try three variations:

1. **Replace the Hash with a JSON String**: a `BoundValueOperations` storing the whole cart; observe how editing one SKU requires updating the entire JSON.
2. **Lower the TTL to one second**: wait over one second, call `cart.get("SKU-A")`, and observe the result; the bound object does not protect the key from expiring.
3. **Write as a String then read as a Hash on the same key name**: identify the wrong-type error and explain why namespaces matter.

These experiments clarify the API and do not replace dedicated transaction, concurrency, and performance testing.

## 17. When Should You Choose BoundOperations?

**Use it when:**

- A method performs multiple operations on the same Redis key.
- An aggregate is stored in a Hash/List/Set/Sorted Set and frequently requires multiple field/member calls.
- You want to avoid repeating the key across many lines and reduce namespace typos.
- You want the code to clearly express "working with user X's cart" or "working with day Y's leaderboard."
- You want to group operations on a single key inside a readable method.

**Unnecessary when:**

- There is only a single simple call per key.
- Processing batches across many different keys with one operation per key.
- The core requirement is atomic transactions, pipelining, Lua scripts, or multi-key management in Redis Cluster; those require dedicated mechanisms.
- A low-level API needs fine-grained control over `RedisConnection`/driver lifecycles.

What matters is **readability and consistency in business code**. BoundOperations can be a great choice, though it does not have to replace every `opsFor...` call.

## 18. Self-Check Questions

**1. After calling `redis.boundValueOps("status:42")`, has Redis created the key `status:42`?**

Not necessarily. Binding creates a Java object attached to the key; the key only appears on the Redis Server when a write command or data-creating operation runs.

**2. Does `BoundHashOperations` make multiple `put(...)` calls run atomically as a group?**

No. The calls are separate commands; use an appropriate batch command, transaction, or script when business logic requires atomicity.

**3. Can you use `BoundValueOperations` to store JSON and then switch to `BoundHashOperations` on the same key?**

Not arbitrarily. A Redis key has one data type at a time. Issuing Hash commands on a key currently holding a String can trigger `WRONGTYPE`.

**4. Does `expire(Duration)` on BoundHashOperations set TTL per field or for the whole Hash key?**

Under standard Redis key TTL usage, it sets the TTL for **the entire Hash key**. Upon expiration, all fields in the key disappear.

**5. Why shouldn't you store a userId-bound operations object in a singleton if the service serves multiple users?**

Because the bound object is tied to the chosen key. Initializing it with user A's key and reusing it for user B causes reads and writes to target the wrong user's data.

**6. Does using BoundOperations reduce network round-trips when calling `put(...)` 100 times?**

Not automatically. Each `put(...)` is still normally a separate Redis command. Use appropriate batching or pipelining when reducing round-trips is the goal.

**7. Can BoundOperations be used with `StringRedisTemplate`?**

Yes. For example, `BoundValueOperations<String, String>` and `BoundHashOperations<String, String, String>`. Keys/values follow `StringRedisTemplate`'s serializers.

**8. Can two threads modify the same key even if each thread creates its own BoundOperations?**

Yes. BoundOperations does not lock data. You must still address concurrency, atomic commands, and business invariants.

**9. Why is `set(value, Duration)` usually better than `set(value)` followed by `expire(Duration)` for Strings requiring a mandatory TTL?**

Because setting the value and expiration in a single Redis command reduces the risk of a key being written successfully without a TTL if an error occurs between two commands.

**10. What is the main difference between `opsForHash().get(key, field)` and `boundHashOps(key).get(field)`?**

Both read a Hash field in Redis. The second carries a fixed key inside the bound object, making sequences of operations on the same key cleaner.

## Key Takeaways

~~~text
RedisTemplate
    |
    +-- opsForValue().get(key)
    +-- opsForHash().put(key, field, value)
    |
    | When multiple operations target the same key:
    v
BoundOperations
    |
    +-- boundValueOps(key) -> get(), set(), increment()
    +-- boundHashOps(key)  -> get(field), put(field, value)
    +-- boundListOps(key)  -> leftPush(value), range(...)
    +-- boundSetOps(key)   -> add(member), isMember(member)
    +-- boundZSetOps(key)  -> add(member, score), reverseRange(...)
    |
    v
Still sends standard Redis commands through the driver
to the Redis Server and applies the same Redis semantics.
~~~

**BoundOperations is a cleaner, less repetitive way in Spring Data Redis to express a sequence of operations on the same Redis key.** Use it when a method works on a fixed aggregate; at the same time, always keep **key binding** distinct from independent concerns such as **TTL, serialization, atomicity, transactions, pipelining, concurrency, and connection management**.
