# Using Reactive Operations Groups in Spring Data Redis

When building a Spring WebFlux application or a processing flow based on Project Reactor, you typically want to access Redis without **blocking threads while waiting for I/O**. Spring Data Redis provides `ReactiveRedisTemplate` and `ReactiveStringRedisTemplate` for this purpose. Instead of calling `RedisTemplate` and receiving results immediately on the current thread, the reactive API returns `Mono<T>` or `Flux<T>`; Redis commands execute when the reactive stream is subscribed to.

The focus of this lesson is **the Reactive Operations groups**. A template does not only offer `GET`/`SET`: it provides API groups aligned with Redis data types, such as **Value, Hash, List, Set, Sorted Set, Geo, HyperLogLog, and Stream**. Choosing the right operations group makes code express the data structure clearly, use appropriate Redis commands, and compose cleanly with Reactor streams.

Example:

```java
Mono<String> value =
        reactiveStringRedisTemplate.opsForValue().get("config:theme");

Mono<Long> number =
        reactiveStringRedisTemplate.opsForValue().increment("metrics:views");

Flux<String> members =
        reactiveStringRedisTemplate.opsForSet().members("tags:article:42");
```

These three expressions **do not return synchronous data**. They create reactive publishers; callers must compose them with `map`, `flatMap`, `zip`, `collectList`, `then`, and so on, or return them directly to WebFlux. Never call `.block()` to force a reactive flow to execute synchronously on the event-loop.

This lesson walks through configuring the template, understanding `Mono`/`Flux`, using each operations group, composing multiple operations, bounding concurrency, handling errors, serialization, and common mistakes.

## 1. Where Does Reactive Redis Fit in the Application?

A typical flow:

```text
HTTP request
    |
    v
Spring WebFlux Controller
    |
    | Mono<ProductDto> / Flux<ProductDto>
    v
Reactive Service
    |
    | ReactiveRedisTemplate / ReactiveStringRedisTemplate
    v
ReactiveRedisConnectionFactory
    |
    | Reactive-capable Redis client (typically Lettuce)
    v
Redis server
    |
    v
Results flow back as Reactor signals
```

Here, *reactive* mainly describes **how the Java side organizes I/O operations**:

- Does not tie up a thread merely waiting per Redis response in blocking mode.
- Can compose asynchronous tasks using `Mono` and `Flux`.
- Propagates completion, error, and cancellation signals.
- Can bound the number of concurrent in-flight operations when handling many keys.

Reactive **does not mean** Redis executes every command in parallel or that individual Redis commands become more atomic. Redis still has the same server, connection, key type, transaction, cluster, and persistence constraints as when accessed via the imperative API.

### 1.1. How do `Mono` and `Flux` differ?

| Reactor type | Meaning | Redis examples |
|---|---|---|
| `Mono<String>` | At most one value, or empty/error | `GET` a single key |
| `Mono<Boolean>` | A single boolean result | `SET`, `HSET`/boolean check operations |
| `Mono<Long>` | A single numeric result | `INCR`, `SADD`, `DEL` |
| `Flux<String>` | Stream of multiple values | Redis Set members, Redis List elements |
| `Flux<Map.Entry<...>>` | Multiple entries | Redis Hash fields/values |
| `Flux<MapRecord<...>>` | Multiple records | Reading a Redis Stream |

A missing key typically makes `opsForValue().get(key)` complete with `Mono.empty()`, **not emit Java `null`** as a `Mono` value.

Example:

```java
Mono<String> theme =
        redis.opsForValue()
                .get("user:42:theme")
                .defaultIfEmpty("light");
```

If Redis cannot find the key, the stream emits `"light"`. If Redis returns a connection failure, that is an **error signal**, not a cache miss; `defaultIfEmpty` does not convert connection errors into default values.

### 1.2. Commands typically run only upon subscription

```java
Mono<Boolean> write =
        redis.opsForValue().set("demo:reactive:key", "hello");
```

The snippet above only builds a publisher. In the standard Reactor model, the Redis call is triggered when a subscription occurs. In a WebFlux application, for example, the framework subscribes to the publisher returned by the controller.

Avoid writing:

```java
public void update() {
    redis.opsForValue().set("demo:key", "value");
    // Publisher is discarded: nothing triggers execution.
}
```

Instead:

```java
public Mono<Boolean> update() {
    return redis.opsForValue().set("demo:key", "value");
}
```

Or if the method only needs to signal completion:

```java
public Mono<Void> update() {
    return redis.opsForValue()
            .set("demo:key", "value")
            .then();
}
```

`then()` waits for the preceding publisher to finish, discards its Boolean value, and forwards completion or error as `Mono<Void>`.

## 2. Initializing Spring Data Redis Reactive

For Spring Boot using WebFlux, typical dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
}
```

If the application already includes the relevant dependencies from another module, do not declare duplicates. Keep Spring Boot/Spring Data Redis versions aligned with your BOM; the examples below illustrate common API groups without tying to a single fixed version.

Illustrative connection settings in `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
```

In production, replace `localhost` with your actual Redis address and configure TLS, authentication, and standalone/Sentinel/Cluster topology as deployed.

Spring Boot can provide `ReactiveRedisConnectionFactory`, `ReactiveRedisTemplate`, or `ReactiveStringRedisTemplate` when auto-configuration conditions are met. The examples below prefer `ReactiveStringRedisTemplate` because **keys and values are Strings**, making Redis easy to inspect via CLI.

A simple service:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingRedisService {

    private final ReactiveStringRedisTemplate redis;

    public GreetingRedisService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> writeGreeting(String userId, String greeting) {
        return redis.opsForValue()
                .set("greeting:" + userId, greeting);
    }

    public Mono<String> readGreeting(String userId) {
        return redis.opsForValue()
                .get("greeting:" + userId);
    }
}
```

When implementing a reactive API, do not swap `ReactiveStringRedisTemplate` for `StringRedisTemplate` inside the same service and assume it remains non-blocking. The two templates differ in usage and return types.

## 3. Overview of Reactive Operations Groups

`ReactiveRedisTemplate<K, V>` provides operation groups corresponding to Redis data types. With `ReactiveStringRedisTemplate`, `K` and `V` are typically `String`.

| Group | Access API | Redis structure | Common use cases |
|---|---|---|---|
| **Value** | `opsForValue()` | String | Simple caches, counters, tokens |
| **Hash** | `opsForHash()` | Hash | Profile fields, metadata |
| **List** | `opsForList()` | List | Ordered lists, simple queues |
| **Set** | `opsForSet()` | Set | Membership, tags, unique relationships |
| **Sorted Set** | `opsForZSet()` | Sorted Set | Leaderboards, rankings, scored items |
| **Geo** | `opsForGeo()` | Sorted-set-backed geospatial index | Locations and distances |
| **HyperLogLog** | `opsForHyperLogLog()` | HyperLogLog | Cardinality estimation |
| **Stream** | `opsForStream()` | Redis Stream | Event logs, consumer groups |

Depending on the group and command, the return type can be `Mono<T>` or `Flux<T>`. Never guess whether an operation returns Boolean, Long, or Flux from the group name alone; check the signature of the method you are calling.

This section uses standard Spring Data Redis Reactive APIs; exact generic parameters may vary with serializer and library version.

## 4. Value Operations: Strings, Counters, and Caches

The `opsForValue()` group works with Redis Strings, including text strings, string-encoded integers, and bytes produced by serializers.

### 4.1. `SET` and `GET` with TTL

```java
import java.time.Duration;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public class OneTimeTokenCache {

    private final ReactiveStringRedisTemplate redis;

    public OneTimeTokenCache(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> save(String requestId, String tokenHash) {
        return redis.opsForValue().set(
                "otp:" + requestId,
                tokenHash,
                Duration.ofMinutes(2)
        );
    }

    public Mono<String> find(String requestId) {
        return redis.opsForValue()
                .get("otp:" + requestId);
    }
}
```

`set(key, value, Duration)` stores data with a TTL in the corresponding Redis operation. This is safer than calling `set(...)` and `expire(...)` in two separate steps when business rules require new keys to always have an expiration.

`GET` returns a single-value publisher; if the key is missing, `Mono` normally completes empty. If the Redis command fails, the publisher emits `onError`, not empty.

### 4.2. Atomic counters with `increment`

A view counter:

```java
public Mono<Long> increaseViews(String articleId) {
    return redis.opsForValue()
            .increment("views:article:" + articleId);
}
```

Redis executes `INCR` atomically with respect to other clients on that server. Avoid replacing it with a Java `GET` -> parse -> `SET(value + 1)` sequence, because concurrent requests can read the same old value and overwrite each other.

Notes:

- `INCR` does not automatically set a TTL on the key.
- Calling `INCR` then `EXPIRE` as two separate publishers **does not become a transaction** just because you chain them with `flatMap`.
- If you require "initialize counter and TTL atomically," use an appropriate mechanism such as Lua/Redis Functions or another guaranteed design.
- A Redis String containing a non-numeric value causes increment to fail, emitting `onError`.

### 4.3. Providing a fallback with `switchIfEmpty`

```java
public Mono<String> readTheme(String userId) {
    String key = "theme:" + userId;

    return redis.opsForValue()
            .get(key)
            .switchIfEmpty(Mono.just("light"));
}
```

This returns `"light"` if the key does not exist. If reading the database is also reactive, use `Mono.defer` so the data source is only queried on a cache miss:

```java
public Mono<String> findTheme(String userId) {
    String key = "theme:" + userId;

    return redis.opsForValue()
            .get(key)
            .switchIfEmpty(
                Mono.defer(() -> loadThemeFromDatabase(userId))
            );
}

// Application-defined method; must be implemented using
// a real reactive data source.
private Mono<String> loadThemeFromDatabase(String userId) {
    return reactivePreferenceStore.findTheme(userId);
}
```

`Mono.defer` is useful because the source query is only constructed/invoked when the cache returns empty, rather than eagerly doing work outside the publisher. A `Mono` built from a true cold reactive source is normally already lazy, yet `defer` clarifies the fallback boundary and any logic used to build the publisher.

## 5. Hash Operations: Storing Multiple Fields Under One Key

Redis Hashes suit objects with multiple small attributes that need field-level reads or updates.

Example data:

```redis
HSET profile:u42 name "An" city "Da Nang" status "ACTIVE"
HGET profile:u42 name
HGETALL profile:u42
```

With the reactive template, the corresponding group is `opsForHash()`.

### 5.1. Configuring String-typed Hash operations

```java
import java.util.Map;

import org.springframework.data.redis.core.ReactiveHashOperations;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public class ReactiveProfileStore {

    private final ReactiveHashOperations<String, String, String> hashOps;

    public ReactiveProfileStore(ReactiveStringRedisTemplate redis) {
        this.hashOps = redis.opsForHash();
    }

    public Mono<Boolean> setStatus(String userId, String status) {
        return hashOps.put(
                "profile:" + userId,
                "status",
                status
        );
    }

    public Mono<String> getStatus(String userId) {
        return hashOps.get(
                "profile:" + userId,
                "status"
        );
    }

    public Mono<Map<String, String>> readAll(String userId) {
        return hashOps.entries("profile:" + userId)
                .collectMap(
                    Map.Entry::getKey,
                    Map.Entry::getValue
                );
    }
}
```

`hashOps.get(...)` returns a `Mono` containing the field value if present. `entries(...)` emits field/value pairs as a `Flux`; `collectMap` gathers them into a `Mono<Map<...>>`.

For Hashes with a very large number of fields, `entries().collectMap(...)` builds a map in JVM memory. Do not use it blindly on unbounded Hashes.

### 5.2. Hash fields are not independent Redis keys

```text
Redis key: profile:u42
  ├── name   = An
  ├── city   = Da Nang
  └── status = ACTIVE
```

Redis TTL is normally set on **the key `profile:u42`**, not on individual Hash fields in the standard model. If each field needs a different expiration, check the capabilities of your Redis and Spring Data versions carefully, or model them as separate keys.

Do not think:

```java
hashOps.put("profile:u42", "status", "ACTIVE");
```

creates an independent key named `status`. It updates a field inside the Hash at key `profile:u42`.

### 5.3. How do Hashes and JSON objects differ?

- **Hash:** suits updating/reading individual fields, such as changing `status` without re-serializing the entire object.
- **JSON in a Redis String:** suits reading/writing the entire object as a single payload; requires serializing/deserializing the whole object per application policy.

With Hashes, field names and values require suitable serializers. With JSON strings, payload schema/versioning must be controlled. Neither approach automatically replaces the other in all cases.

## 6. List Operations: Order and Head/Tail Operations

Redis Lists store elements in insertion order. Reactive List Operations can push elements to the head/tail and read ranges.

Example:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class RecentActivityStore {

    private final ReactiveStringRedisTemplate redis;

    public RecentActivityStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> add(String userId, String activityId) {
        return redis.opsForList()
                .leftPush("recent:activity:" + userId, activityId);
    }

    public Flux<String> recent(String userId) {
        return redis.opsForList()
                .range("recent:activity:" + userId, 0, 19);
    }

    public Mono<String> takeLatest(String userId) {
        return redis.opsForList()
                .leftPop("recent:activity:" + userId);
    }
}
```

Meaning:

- `leftPush`: inserts an element at the head of the List.
- `range(key, 0, 19)`: reads up to the first 20 elements in List order.
- `leftPop`: retrieves and removes the head element; this mutates Redis data.

With Redis CLI, you can inspect:

```redis
LPUSH recent:activity:u42 a1
LPUSH recent:activity:u42 a2
LRANGE recent:activity:u42 0 19
LPOP recent:activity:u42
```

### 6.1. Does a Reactive List replace Redis Streams for job queues?

Lists can back a simple queue, yet `leftPop`/`rightPop` **removes the element from the List**. If a worker receives an element and crashes before finishing processing, the application needs its own recovery mechanism.

Redis Streams with consumer groups provide explicit pending tracking and `ACK` support for replayable message processing. When jobs must not be lost, do not rely solely on a `pop` without state persistence or atomic handoff mechanisms.

### 6.2. Caution when reading large Lists

`range(key, 0, -1)` can fetch the entire List and stream huge numbers of elements through `Flux`. A Reactor `Flux` does not turn a Redis command returning an entire dataset into server-side pagination. Bound read ranges (`0..19`, `20..39`, etc.) when Lists can grow large.

## 7. Set Operations: Membership and Unique Elements

Redis Sets are useful when you only need to know **whether an element belongs to a collection**, without caring about order.

Example storing article tags:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ArticleTagStore {

    private final ReactiveStringRedisTemplate redis;

    public ArticleTagStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> addTags(String articleId, String... tags) {
        return redis.opsForSet()
                .add("tags:article:" + articleId, tags);
    }

    public Mono<Boolean> hasTag(String articleId, String tag) {
        return redis.opsForSet()
                .isMember("tags:article:" + articleId, tag);
    }

    public Flux<String> tags(String articleId) {
        return redis.opsForSet()
                .members("tags:article:" + articleId);
    }
}
```

A Redis Set does not store duplicate elements like a List. `add(...)` normally returns the number of **newly** added elements, not the total number of arguments passed.

### 7.1. Do not use Sets when order is required

`members(...)` returns a `Flux`, but element order is not a stable business order. Do not take the first element from `Flux` and treat it as "the first tag added."

If chronological order or score order is required, consider a List or Sorted Set depending on the domain.

### 7.2. Membership checks are more efficient than loading the whole Set

An unsuitable pattern:

```java
return redis.opsForSet().members("tags:article:" + articleId)
        .any(tag::equals);
```

This can force the application to inspect many elements. When you only need to check whether an element exists, use:

```java
return redis.opsForSet()
        .isMember("tags:article:" + articleId, tag);
```

That delegates membership testing to the proper Redis operation rather than transferring the whole Set to search in Java.

## 8. Sorted Set Operations: Ranking by Score

Redis Sorted Sets (ZSet) store elements alongside a **score**, supporting ordering and rank/score range queries.

Problem: user leaderboard.

```redis
ZADD leaderboard:week:46 120 user:42
ZADD leaderboard:week:46 350 user:99
ZADD leaderboard:week:46 270 user:17
ZREVRANGE leaderboard:week:46 0 2
```

With Reactive Operations:

```java
import org.springframework.data.domain.Range;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveLeaderboard {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveLeaderboard(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> setScore(
            String boardKey,
            String userId,
            double score
    ) {
        return redis.opsForZSet()
                .add(boardKey, userId, score);
    }

    public Flux<String> topTen(String boardKey) {
        return redis.opsForZSet()
                .reverseRange(boardKey, Range.closed(0L, 9L));
    }
}
```

In the Reactive ZSet API, `Range<Long>` expresses a **rank/index** range, distinct from score range queries. Distinguish `Range<Long>` for positions from `Range<Double>`/corresponding types when calling `rangeByScore` methods in your Spring Data version.

If you want scores alongside elements, use the "with scores" methods that return tuples containing both value and score; choose the exact API instead of calling `reverseRange` and expecting scores.

### 8.1. When to choose ZSet over Set?

| Requirement | Suitable structure |
|---|---|
| Check whether a tag exists | Set |
| List unique members, order not required | Set |
| Rank by score | Sorted Set |
| Fetch top N | Sorted Set |
| Store list in head/tail insertion order | List |
| Process event stream needing IDs/consumer groups | Stream |

Sorted Sets can still grow very large. Limit top-N reads and define cleanup policies for obsolete members instead of always reading the entire leaderboard.

## 9. Geo Operations: Coordinates and Location Search

Redis provides geospatial commands (coordinate data stored using a Sorted-Set-compatible structure), and Spring Data Redis Reactive provides the `opsForGeo()` group.

Example storing a location:

```java
import org.springframework.data.geo.Point;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public class DriverLocationStore {

    private final ReactiveStringRedisTemplate redis;

    public DriverLocationStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> updateLocation(
            String driverId,
            double longitude,
            double latitude
    ) {
        return redis.opsForGeo().add(
                "drivers:geo",
                new Point(longitude, latitude),
                driverId
        );
    }
}
```

Points to remember:

- `Point` takes coordinates in **longitude, latitude** order.
- Coordinates must fall within the range supported by Redis GEO and be validated/normalized before storing.
- If updating locations frequently, decide how stale data is removed/expired and how to distinguish online drivers from outdated coordinates.
- Radius searches can return many results; limit count and sorting when only the nearest drivers are needed.
- Redis GEO does not automatically handle access control for personal location data.

Example calculating the distance between two members stored in the same Geo key:

```java
Mono<org.springframework.data.geo.Distance> distance =
        redis.opsForGeo()
                .distance("drivers:geo", "driver:42", "driver:99");
```

If a member does not exist, the result may be empty per the API. Never interpret missing distance data as distance `0` when business logic must distinguish "same location" from "missing coordinates."

Specific radius/search APIs can vary by Redis and Spring Data version; select overloads matching `Distance`, `Circle`, `GeoResults`, and the expected result type.

## 10. HyperLogLog Operations: Estimating Unique Element Counts

HyperLogLog (HLL) is useful when you want to **estimate cardinality**—such as daily unique visitors—without storing every user ID in a massive Redis Set.

Redis CLI:

```redis
PFADD visitors:2026-11-13 u42 u99 u17
PFCOUNT visitors:2026-11-13
```

Reactive API:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public class UniqueVisitorCounter {

    private final ReactiveStringRedisTemplate redis;

    public UniqueVisitorCounter(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> recordVisitor(String day, String userId) {
        return redis.opsForHyperLogLog()
                .add("visitors:" + day, userId);
    }

    public Mono<Long> estimatedVisitors(String day) {
        return redis.opsForHyperLogLog()
                .size("visitors:" + day);
    }
}
```

Semantics:

- `add(...)` updates the HLL structure and returns a result per the API contract.
- `size(...)` yields an **estimate**, not an exact counter.
- HyperLogLog suits large-scale unique analytics and is **unsuitable** for answering "does user X belong to this set?"
- If exact membership or exact counts are required, evaluate a Redis Set or another data store.

Never use HLL for access control, duplicate-order prevention, or any business invariant requiring exact membership accuracy.

## 11. Stream Operations: Records with IDs and Consumer Groups

Redis Streams store events ordered by ID, support re-reading from known positions, and support consumer groups.

Example publishing an event:

```redis
XADD stream:orders * type CREATED orderId o-42
```

Spring Data Redis Reactive offers `opsForStream()` for Stream operations. Illustrative Java form:

```java
import java.util.Map;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public class OrderEventWriter {

    private final ReactiveStringRedisTemplate redis;

    public OrderEventWriter(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<RecordId> publishCreated(String orderId) {
        MapRecord<String, String, String> record =
                StreamRecords.newRecord()
                        .in("stream:orders")
                        .ofMap(Map.of(
                                "type", "CREATED",
                                "orderId", orderId
                        ));

        return redis.opsForStream().add(record);
    }
}
```

`RecordId` identifies the position of the appended event. If the producer requires idempotency, do not assume retrying `XADD` avoids duplicates: with `*`, Redis can assign a brand-new ID to the same business event.

### 11.1. Reading once from an offset

```java
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import reactor.core.publisher.Flux;

public Flux<?> readExisting() {
    return redis.opsForStream()
            .read(
                StreamOffset.create(
                    "stream:orders",
                    ReadOffset.from("0-0")
                )
            );
}
```

`Flux<?>` here merely emphasizes the publisher category when illustrating the API. In real services, declare `MapRecord<K, HK, HV>` or the record type matching your serializer and `opsForStream().read(...)` overload.

`ReadOffset.from("0-0")` reads entries **with IDs greater than `0-0`** still retained in the stream. It does not create an infinite polling loop, manage checkpoints automatically, or guarantee trimmed entries remain readable.

### 11.2. `ReadOffset.latest()` and `lastConsumed()` are not equivalent

- `latest()` reads from the end of the stream at read time, typically corresponding to `$` in `XREAD`; repeated use without tracking processed IDs can **skip entries arriving between polls**.
- `from(id)` reads after a specific ID; appropriate when maintaining checkpoints.
- `lastConsumed()` typically pairs with a **consumer group** and the semantics of receiving entries not yet delivered to the group, corresponding to `>` in `XREADGROUP`.

With consumer groups, you must design **ACKs**, pending entry handling, reclaiming, and retention. A Java `Flux` does not automatically guarantee business processing succeeded or was ACKed in Redis.

### 11.3. Redis Streams do not mean a reactive application is automatically safe

Even when using `Flux<MapRecord<...>>`, you still need:

- Checkpoints or consumer groups initialized at the right offset.
- Never ACKing before critical side effects succeed.
- Idempotency when messages can be redelivered.
- Pending reclaim mechanisms if a consumer crashes.
- Bounds on concurrent message processing and retry timing.
- Sufficient retention so unprocessed data is not trimmed away.

Choose `opsForStream()` for Stream's data structure and delivery semantics, not merely because the method returns a `Flux`.

## 12. Summary of Return Types Across Operations Groups

A common source of bugs is confusing `Mono` with `Flux` or misunderstanding empty emissions.

| Operation | Typical publisher type | Meaning |
|---|---|---|
| Value `get` | `Mono<V>` | 0 or 1 value; empty if key missing |
| Value `set` | `Mono<Boolean>` | Single write command result |
| Value `increment` | `Mono<Long>` | Numeric value after increment |
| Hash `get` | `Mono<HV>` | 0 or 1 field value |
| Hash `entries` | `Flux<Map.Entry<HK, HV>>` | Multiple fields/values |
| List `leftPush` | `Mono<Long>` | List length/result per command |
| List `range` | `Flux<V>` | Multiple List elements |
| Set `isMember` | `Mono<Boolean>` | Single membership answer |
| Set `members` | `Flux<V>` | Multiple members, order not guaranteed |
| ZSet `reverseRange` | `Flux<V>` | Elements within rank range |
| Geo `distance` | `Mono<Distance>` | Distance if both members have coordinates |
| HyperLogLog `size` | `Mono<Long>` | Estimated cardinality |
| Stream `add` | `Mono<RecordId>` | Created entry ID |
| Stream `read` | `Flux<...Record...>` | Entries read |

Note: some Redis operations may return Boolean or numeric types differently depending on the API version. This table covers common groups and types, and does not replace checking the actual overload signature in your project.

## 13. Combining Operations with Reactor

Reactive APIs shine when operations are **chained into a pipeline** instead of being fired separately with results ignored.

### 13.1. Chaining dependent steps with `flatMap`

Problem: look up a user's group ID, then read the members of that group.

```java
public Flux<String> membersOfUsersGroup(String userId) {
    return redis.opsForValue()
            .get("user:" + userId + ":group-id")
            .flatMapMany(groupId ->
                redis.opsForSet().members("group:" + groupId + ":members")
            );
}
```

Here:

1. `GET` group ID produces a `Mono<String>`.
2. `flatMapMany` turns the group ID into a `Flux<String>` of members.
3. If no group ID exists in Redis, the `Mono` is empty and the Set read never runs.
4. If a step errors, the error signal propagates unless the application defines an explicit recovery policy.

Avoid writing:

```java
String groupId =
        redis.opsForValue().get("user:" + userId + ":group-id").block();
```

and then using `groupId` to read further on the WebFlux event-loop. That blocks the thread waiting on Redis and can degrade throughput or throw a runtime error when `.block()` is called on a non-blocking thread.

### 13.2. Running independently and combining with `Mono.zip`

When two **independent** keys need to be read:

```java
public Mono<UserDashboard> dashboard(String userId) {
    Mono<String> theme = redis.opsForValue()
            .get("theme:" + userId)
            .defaultIfEmpty("light");

    Mono<Long> views = redis.opsForValue()
            .get("views:user:" + userId)
            .map(Long::parseLong)
            .defaultIfEmpty(0L);

    return Mono.zip(theme, views)
            .map(tuple -> new UserDashboard(
                    userId,
                    tuple.getT1(),
                    tuple.getT2()
            ));
}

public record UserDashboard(
        String userId,
        String theme,
        long views
) {}
```

`zip` can subscribe to independent sources within the same flow, yet **does not create an atomic snapshot**: another client can still update `theme` between the two reads.

Important note: if one of the `Mono`s completes empty without `defaultIfEmpty`, `Mono.zip` can complete empty without building a tuple. When designing multi-field responses, decide explicitly how cache misses are represented.

### 13.3. `then` and `thenReturn` when only the subsequent result is needed

To write a cache entry and then return the DTO:

```java
public Mono<ProductDto> saveCache(
        String key,
        ProductDto product
) {
    String json = serializeProduct(product);

    return redis.opsForValue()
            .set(key, json)
            .thenReturn(product);
}
```

`thenReturn(product)` emits `product` **when the SET publisher completes normally**. It does not turn a `Boolean.FALSE` result into an exception; if the write command has Boolean semantics that must be checked, handle them explicitly instead of ignoring them.

If caching is purely an optimization, ignoring cache write errors within a bounded scope may be acceptable per policy. If the cache must exist to preserve an invariant, never swallow write errors.

## 14. Reactive Cache-Aside Example with a Reactive Data Source

Suppose a service reads a product by ID. Redis stores JSON and the database is the source of truth.

Source interface:

```java
public interface ReactiveProductStore {
    Mono<ProductDto> findById(String id);
}
```

DTO:

```java
public record ProductDto(String id, String name) {}
```

Service:

```java
import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.JsonProcessingException;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ProductCacheService {

    private static final Duration TTL = Duration.ofMinutes(5);

    private final ReactiveStringRedisTemplate redis;
    private final ReactiveProductStore store;
    private final ObjectMapper mapper;

    public ProductCacheService(
            ReactiveStringRedisTemplate redis,
            ReactiveProductStore store,
            ObjectMapper mapper
    ) {
        this.redis = redis;
        this.store = store;
        this.mapper = mapper;
    }

    public Mono<ProductDto> findById(String productId) {
        String key = "cache:product:v1:" + productId;

        Mono<ProductDto> fromCache = redis.opsForValue()
                .get(key)
                .map(this::decode);

        Mono<ProductDto> fromSource = Mono.defer(() ->
                store.findById(productId)
                    .flatMap(product ->
                        redis.opsForValue()
                            .set(key, encode(product), TTL)
                            .thenReturn(product)
                    )
        );

        return fromCache.switchIfEmpty(fromSource);
    }

    private String encode(ProductDto product) {
        try {
            return mapper.writeValueAsString(product);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Cannot serialize product", ex
            );
        }
    }

    private ProductDto decode(String json) {
        try {
            return mapper.readValue(json, ProductDto.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                "Invalid cached product JSON", ex
            );
        }
    }
}
```

Flow:

```text
GET Redis key
    |
    +-- HIT  -> decode JSON -> Mono<ProductDto>
    |
    +-- MISS -> ReactiveProductStore.findById()
                    |
                    +-- DB has data
                    |      |
                    |      +-- SET Redis EX TTL
                    |      +-- return ProductDto
                    |
                    +-- DB missing -> Mono.empty()
```

### 14.1. Limitations of this cache-aside example

- If the DB source does not find the item, the service returns `Mono.empty()` without **negative-caching** the result; a short-TTL sentinel can be added if needed.
- If the Redis read errors, `switchIfEmpty` **does not run** because Redis emits `onError`, not an empty `onComplete`.
- If the Redis write fails after the DB returned the product, the current code emits an error instead of returning the product. For non-mandatory caches, handle write errors individually so DB responses still succeed.
- When multiple concurrent requests miss, all can query the DB; reactive does not prevent cache stampedes automatically.
- JSON serialization in the example is JVM CPU work, not Redis I/O. For large payloads, manage CPU/heap and schema versions.
- When a product updates, the write path must invalidate the cache or update the entry under an appropriate consistency strategy.

### 14.2. Allowing cache errors while still reading the data source

If business policy treats Redis as an optimization layer that can be bypassed on failure, isolate the fallback logic:

```java
public Mono<ProductDto> findByIdAllowCacheFailure(String id) {
    String key = "cache:product:v1:" + id;

    Mono<ProductDto> fromSource = Mono.defer(() ->
        store.findById(id)
            .flatMap(product ->
                redis.opsForValue()
                    .set(key, encode(product), Duration.ofMinutes(5))
                    .onErrorResume(cacheWriteError -> {
                        // Record metric/log for cacheWriteError.
                        return Mono.just(false);
                    })
                    .thenReturn(product)
            )
    );

    return redis.opsForValue()
            .get(key)
            .map(this::decode)
            .onErrorResume(cacheReadError -> {
                // Record metric/log; cache read error is not DB not-found.
                return Mono.empty();
            })
            .switchIfEmpty(fromSource);
}
```

Here:

- `onErrorResume` on the **Redis read step** turns a cache read failure into a cache miss under a fail-open policy.
- `onErrorResume` on the **Redis write step** lets the product still be returned if Redis fails to save.
- Errors from `store.findById(id)` are not swallowed by the two cache error handlers because handler scope is tightly bounded.

Never wrap the **entire** pipeline in `.onErrorResume(ex -> Mono.empty())` if doing so turns DB errors, parse errors, or authorization errors into "not found."

## 15. Reactive Serialization: String Templates and Object Templates

`ReactiveStringRedisTemplate` is handy for strings, counters, and JSON text. When the application wants Redis to return DTOs directly, you can configure a `ReactiveRedisTemplate<String, ProductDto>` with custom serializers.

Example compatible with common Spring Data Redis/Jackson 2 APIs:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProductReactiveRedisConfiguration {

    @Bean
    public ReactiveRedisTemplate<String, ProductDto> productRedisTemplate(
            ReactiveRedisConnectionFactory connectionFactory
    ) {
        var keySerializer = new StringRedisSerializer();
        var valueSerializer =
                new Jackson2JsonRedisSerializer<>(ProductDto.class);

        RedisSerializationContext<String, ProductDto> context =
                RedisSerializationContext
                    .<String, ProductDto>newSerializationContext(
                        keySerializer
                    )
                    .value(valueSerializer)
                    .build();

        return new ReactiveRedisTemplate<>(
                connectionFactory,
                context
        );
    }
}
```

Different Spring Data Redis and Jackson versions may provide different serializers or builders; when upgrading to newer Jackson stacks, pick compatible APIs. Across all versions, the rule stays the same: **serializers for keys, values, hash keys, and hash values must match how the data was written**.

Using the object template:

```java
public Mono<Boolean> save(ProductDto product) {
    return productRedisTemplate.opsForValue()
            .set("product:object:" + product.id(), product);
}

public Mono<ProductDto> find(String productId) {
    return productRedisTemplate.opsForValue()
            .get("product:object:" + productId);
}
```

### 15.1. Each template has its own byte convention

If the same key:

```text
product:object:p42
```

is written by a template using a JSON serializer but read by a template using a String serializer or JDK serializer, the application may hit deserialization errors or garbled data.

Never assume looking up the same Java key string is enough for two templates to understand the same value. Redis stores bytes; serializers define their meaning.

### 15.2. Be careful with JSON containing type metadata

Some generic JSON serializers embed type info inside JSON. When data comes from untrusted sources, polymorphic deserialization must restrict allowed types and Redis read/write permissions. For DTOs with clear structure, type-bound serializers are usually easier to govern.

If the DTO schema changes between two running application versions, plan backward compatibility, versioned namespaces, or safe cache eviction/rebuilding.

## 16. Reactor Composition Does Not Automatically Create Redis Transactions

Suppose the code does:

```java
return redis.opsForValue().set("order:42:status", "PAID")
        .then(redis.opsForValue().increment("metrics:paid-orders"));
```

The two commands execute in order: the increment is only subscribed to after `set` completes normally.

However, that **does not guarantee**:

- Both writes execute atomically.
- No commands from another client interleave between them.
- If `increment` fails, Redis automatically rolls back `set`.
- Redis and a synchronous PostgreSQL transaction commit together.

`then`, `flatMap`, and `concatMap` are **publisher coordination** tools, not Redis `MULTI`/`EXEC` commands.

If business logic needs multiple keys updated without interleaving or conditional checks followed by atomic writes, use appropriate Redis mechanisms such as Lua/Redis Functions or supported transaction APIs with proper connection scope. Even `MULTI`/`EXEC` lacks general rollback for commands that already executed successfully at runtime.

### 16.1. Atomic commands remain preferred when sufficient

Instead of:

```java
return redis.opsForValue().get("counter")
        .map(Long::parseLong)
        .flatMap(v ->
            redis.opsForValue().set("counter", Long.toString(v + 1))
        );
```

use:

```java
return redis.opsForValue().increment("counter");
```

`INCR` avoids lost updates that `GET` + `SET` can suffer. *Reactive* does not remove race conditions from read-modify-write sequences.

## 17. Concurrency, Ordering, and Bounding Redis Calls

Given a list of many IDs:

```java
List<String> ids = List.of("p1", "p2", "p3");
```

You can read them with `Flux`:

```java
public Flux<String> cachedValues(List<String> ids) {
    return Flux.fromIterable(ids)
            .flatMap(id ->
                redis.opsForValue().get("cache:product:" + id)
            );
}
```

`GET` calls are created from the input items. However, `flatMap` allows results to arrive **not necessarily in ID order**, and by default can open significant concurrency.

### 17.1. Limiting concurrency

```java
public Flux<String> cachedValuesBounded(List<String> ids) {
    int concurrency = 16;

    return Flux.fromIterable(ids)
            .flatMap(
                id -> redis.opsForValue()
                        .get("cache:product:" + id),
                concurrency
            );
}
```

The limit `16` is only an example. Choose limits based on Redis latency, payload sizes, connection resources, and application processing speed.

### 17.2. Preserving input order when needed

If you want the output stream in ID order:

```java
public Flux<String> cachedValuesOrdered(List<String> ids) {
    return Flux.fromIterable(ids)
            .concatMap(id ->
                redis.opsForValue()
                    .get("cache:product:" + id)
                    .defaultIfEmpty("NOT_CACHED")
            );
}
```

`concatMap` executes inner publishers sequentially, useful when strict order is required, though at lower concurrency.

Another option is `flatMapSequential`, which runs multiple inner publishers concurrently and emits results in source order; account for the cost of buffering early results while waiting for earlier publishers to finish.

**Note:** when a `Mono` is empty, `flatMap`/`concatMap` emits no item for it. If you must preserve the `id -> result` association, return a wrapper containing both the ID and miss status instead of raw `Flux<String>`.

Example:

```java
public record CacheLookup(String id, String value, boolean found) {}

public Flux<CacheLookup> lookupAll(List<String> ids) {
    return Flux.fromIterable(ids)
            .flatMapSequential(
                id -> redis.opsForValue()
                    .get("cache:product:" + id)
                    .map(value -> new CacheLookup(id, value, true))
                    .defaultIfEmpty(new CacheLookup(id, "", false)),
                16
            );
}
```

Here `""` is merely a placeholder in the record when `found=false`; do not infer from it that valid values are never empty strings.

### 17.3. `Flux` is not an automatic Redis pipeline

Multiple `GET` operations initiated by `flatMap` may be scheduled efficiently by the driver, yet **never assume this constitutes a Redis transaction** or a single `MGET` command.

If all operations are the same kind and Redis has a suitable multi-key command, consider that API to reduce round trips while checking Redis Cluster hash-slot constraints and result ordering.

Optimize for **actual total latency and resources**, not just the number of publishers created.

## 18. Backpressure in Reactor and Redis Limits

Reactor supports **backpressure**: subscribers can request only the amount of data they can consume. However, do not infer that a `Flux` from Redis automatically converts every command into a partial read matching the requested count.

Example:

```java
redis.opsForSet()
        .members("huge:set")
        .take(20)
```

`take(20)` caps the items forwarded downstream. Depending on the Redis command and driver behavior, the server-side operation may still fetch a large set before Reactor trims it down to 20. For large Sets, choose a cursor/scanning API rather than always calling `SMEMBERS`.

Similarly:

```java
redis.opsForList().range("huge:list", 0, -1)
```

can fetch the entire List from Redis. Switching the consumer to item-by-item `Flux` processing does not undo the server cost of `LRANGE 0 -1`.

Guidelines:

- Use `LRANGE` with small ranges, and ZSet ranges capped to top N.
- For large Hashes/Sets, consider scan-based APIs where supported by your Spring Data Redis version, understanding `SCAN`'s non-snapshot behavior when data mutates.
- Bound concurrent requests with `flatMap(..., concurrency)`.
- Avoid `collectList()` or `collectMap()` on potentially unbounded or very large `Flux` streams.
- For Stream consumers, account for batch size, ack/retry, retention, and handler capacity, not just `Flux` demand.

## 19. Timeouts, Errors, and Fallbacks

Each Redis publisher can terminate in three main ways:

```text
onNext(value) + onComplete -> result produced
onComplete                 -> no value
onError(error)             -> failure
```

These are three distinct states.

### 19.1. Distinguishing missing keys from Redis errors

```java
Mono<String> value = redis.opsForValue()
        .get("config:feature-x")
        .defaultIfEmpty("OFF");
```

If the key is missing, it emits `"OFF"`. If Redis disconnects, it still emits an error.

To fall back on errors too:

```java
Mono<String> value = redis.opsForValue()
        .get("config:feature-x")
        .onErrorResume(ex -> {
            // Explicit log/metric: Redis unavailable.
            return Mono.just("OFF");
        })
        .defaultIfEmpty("OFF");
```

However, **do not apply generic fallbacks** to security control data or values that must be accurate. Never convert an authorization read error into "allowed" just to keep an API returning a response.

### 19.2. Client-side timeouts

```java
import java.time.Duration;

public Mono<String> readWithTimeout(String key) {
    return redis.opsForValue()
            .get(key)
            .timeout(Duration.ofSeconds(2));
}
```

Reactor's `timeout` emits an error signal if the publisher does not finish within the window. It **does not prove** the Redis server never received or executed the command. For side-effecting commands like `INCR`, automatically retrying after a timeout can mutate data a second time.

Reactor timeouts, Redis client timeouts, and network timeouts have distinct semantics and behaviors; configure wait limits deliberately without mixing them up.

### 19.3. `retryWhen` requires idempotency

For reads:

```java
return redis.opsForValue()
        .get(key)
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
        );
```

This is illustrative; in production **filter strictly for transient error types** and avoid retrying data errors like `WRONGTYPE` or serialization errors.

For writes:

```java
redis.opsForValue().increment("payment:counter");
```

do not retry automatically without an idempotency mechanism, as the command may already have incremented before the connection dropped the response.

## 20. Do Not Manually `.subscribe()` Inside Services and Ignore the Result

A common mistake:

```java
public Mono<ProductDto> findProduct(String id) {
    redis.opsForValue()
        .set("audit:last-product", id)
        .subscribe(); // fire-and-forget

    return productStore.findById(id);
}
```

Problems:

- The service starts a subscription detached from the returned publisher.
- The request can complete before the Redis write finishes.
- Errors in the detached subscription bypass the request's error handling.
- Execution order between the Redis write and DB read is undefined.
- Canceling the returned flow does not control the manually subscribed task.

If the audit write must happen before the DB read:

```java
public Mono<ProductDto> findProduct(String id) {
    return redis.opsForValue()
        .set("audit:last-product", id)
        .then(productStore.findById(id));
}
```

If auditing is strictly best-effort, still use a monitored async mechanism with explicit error handling rather than uncoordinated `subscribe()` calls.

Practical rule: **return or compose publishers**, letting the calling layer or web framework manage subscriptions. Only subscribe manually at boundaries designed to manage lifecycles, such as workers or event processors.

## 21. Beware of `block()`, JPA, and Non-Reactive I/O

Unsuitable example inside a WebFlux service:

```java
public Mono<String> find(String key) {
    String cached = reactiveRedis.opsForValue().get(key).block();

    if (cached != null) {
        return Mono.just(cached);
    }

    return Mono.just(jpaRepository.findById(key).toString());
}
```

Problems:

- `block()` blocks the executing thread and can throw errors on event-loop threads.
- Standard JPA is a blocking API; calling it directly inside a reactive pipeline also blocks threads.
- Wrapping the result in `Mono.just(...)` does not turn an already-executed blocking DB call into non-blocking I/O.

If you must use a blocking source during an architectural transition, isolate it on a scheduler meant for blocking work per Reactor design, for example:

```java
Mono<ProductDto> productMono =
        Mono.fromCallable(() -> blockingProductStore.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
```

This is a **temporary bridge for blocking sources**, not a substitute for R2DBC or a genuine reactive source. Under heavy traffic, manage connection pools, concurrent tasks, and resource caps instead of offloading all JDBC/JPA onto an uncontrolled scheduler.

For end-to-end reactive applications, pair `ReactiveRedisTemplate` with corresponding reactive DBs and clients.

## 22. Atomic Redis Commands, Transactions, and Scripts in the Reactive Model

Choosing the right Reactive Operations group also relates to **business guarantees**:

| Requirement | API/strategy to consider |
|---|---|
| Increment a counter | `opsForValue().increment(...)` |
| Add unique members | `opsForSet().add(...)` |
| Update a single Hash field | `opsForHash().put(...)` |
| Add score to a leaderboard | `opsForZSet().add(...)` |
| Write two keys in order | Reactor `.then(...)` only coordinates ordering, not transactions |
| Check balance then deduct | Lua/Redis Function or appropriate optimistic concurrency |
| Record events needing ACK/replay | `opsForStream()` + consumer group + recovery |
| Atomic sync between Redis and PostgreSQL | Not provided by a single Reactive Operation; design transaction boundaries and recovery |

When an operation needs multi-step read-check-write on the Redis server, use Spring Data Redis's scripting API if your reactive version provides the appropriate overloads. Even when invoked via `Flux`/`Mono`, scripts still carry standard Redis Lua constraints: no other commands interleave during execution, long-running scripts block other commands, and there is no general rollback if a script errors after partial writes.

Spring's reactive transaction management and Redis transactions are separate scopes. Do not assume `@Transactional` on a `Mono`-returning method converts Redis operations into `MULTI`/`EXEC`, nor creates a distributed commit with a database.

## 23. WebFlux Controller Example Using Reactive Operations

A controller returning publishers directly:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/articles")
public class ArticleController {

    private final ArticleMetricsService metrics;

    public ArticleController(ArticleMetricsService metrics) {
        this.metrics = metrics;
    }

    @PostMapping("/{id}/views")
    public Mono<ResponseEntity<Long>> increase(
            @PathVariable String id
    ) {
        return metrics.increaseViews(id)
                .map(ResponseEntity::ok);
    }

    @GetMapping("/{id}/views")
    public Mono<ResponseEntity<Long>> current(
            @PathVariable String id
    ) {
        return metrics.currentViews(id)
                .map(ResponseEntity::ok);
    }
}
```

Service:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ArticleMetricsService {

    private final ReactiveStringRedisTemplate redis;

    public ArticleMetricsService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> increaseViews(String articleId) {
        return redis.opsForValue()
                .increment("views:article:" + articleId);
    }

    public Mono<Long> currentViews(String articleId) {
        return redis.opsForValue()
                .get("views:article:" + articleId)
                .map(Long::parseLong)
                .defaultIfEmpty(0L);
    }
}
```

Here:

- The controller does not call `.subscribe()` or `.block()`.
- WebFlux subscribes when producing the HTTP response.
- The counter uses atomic Redis `INCR`.
- `GET` cache misses are handled explicitly via `defaultIfEmpty(0L)`.
- If Redis errors, the error propagates through the `Mono`; the application handles it via controller advice or a corresponding error policy.

If the API must distinguish "counter key never existed" from "counter is 0," do not use `defaultIfEmpty(0L)` without adding an explicit status representation.

## 24. Testing Reactive Operations with `StepVerifier`

Project Reactor provides `reactor-test` and `StepVerifier` to verify publisher signal sequences.

Example integration test running against a test Redis instance:

```java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class ArticleMetricsServiceTest {

    private final ArticleMetricsService metrics;

    ArticleMetricsServiceTest(ArticleMetricsService metrics) {
        this.metrics = metrics;
    }

    @Test
    void incrementEmitsNewValue() {
        StepVerifier.create(metrics.increaseViews("test-article-1"))
                .expectNextCount(1)
                .verifyComplete();
    }
}
```

The example illustrates the `StepVerifier` API; in a real project, fixtures should inject `ArticleMetricsService` through the Spring test context and prepare/clean up Redis keys before each test for predictable values. If the key already exists, `INCR` still returns a number, though the exact value will differ.

Example testing cache-miss behavior:

```java
StepVerifier.create(
    reactiveStringRedisTemplate.opsForValue()
        .get("test:missing:key")
)
    .verifyComplete();
```

The precondition is that this key truly does not exist in the test Redis instance. `verifyComplete()` asserts the publisher completes empty, unlike `expectNext("...")`.

### 24.1. Why not call `.block()` in every test?

Some integration tests may call `.block()` on an appropriate test thread to seed data, yet using `StepVerifier` accurately asserts `onNext`, `onComplete`, `onError`, and timing behavior in the Reactor model.

Never write a test that merely constructs a `Mono` and ends—without a subscription, the Redis operation may never execute.

### 24.2. Scenarios to include

- `GET` with existing and missing keys.
- Redis connection failures and fallback behavior.
- Malformed Redis values, e.g., unparseable numbers.
- Hash/List/Set/ZSet operations with isolated test data.
- Actual cache TTL after writing.
- Concurrent `INCR` requests to observe command atomicity.
- Output ordering with `flatMap`/`concatMap`.
- Stream flows with consumer groups, ACK/pending, and idempotency if used.
- Cancellations/timeouts under slow network conditions.

Scenarios needing a real Redis server can use an isolated test instance or Testcontainers per project infrastructure. Never use production data as test fixtures.

## 25. Observing and Operating a Reactive Redis Application

To confirm that reactive operations improve throughput, measure real metrics rather than merely changing return types to `Mono`.

| Metric | Meaning |
|---|---|
| Redis command latency | Redis operation duration by command type |
| Request p50/p95/p99 | Latency observed at the API/WebFlux layer |
| Redis server CPU/memory | Identifies throughput bottlenecks |
| Network throughput/RTT | Shows Redis communication overhead |
| Concurrent Redis operations | Detects overload from `flatMap` fan-out |
| Client connection usage | Monitors connection pool/routing |
| Reactor scheduler blocking | Detects `block()` or blocking libraries on the event-loop |
| Cache hit/miss | Evaluates how often primary queries are avoided |
| Serialization errors | Detects incompatible data |
| Redis timeouts/retries | Spots slow networks, driver failures, or retry storms |
| Stream lag/pending | When using consumer groups, tracks unprocessed records |

Micrometer/observability can measure Redis and API latencies depending on Spring Boot, driver, and tracing configuration. Avoid using every user ID or unique Redis key as a metric label, as cardinality will explode.

Note: reactive does not remove Redis server limits. A single `SMEMBERS` on a huge Set, a slow Lua script, or commands scanning large datasets can still increase latency for all other commands on Redis.

## 26. Common Mistakes When Moving from `RedisTemplate` to Reactive Operations

**"Creating a `Mono` runs the command."** Not necessarily. Typical publishers are lazy and must be subscribed to by a responsible layer.

**"Calling `.subscribe()` inside a service makes commands run faster."** That is usually uncontrolled fire-and-forget, prone to lost errors and broken business ordering.

**"Using `.block()` in WebFlux to unwrap values for Java logic."** It blocks threads, breaks the reactive model, and can fail on event-loop threads.

**"`Mono.empty()` means the Redis server failed."** No. Missing keys/fields complete empty; Redis failures flow through `onError`.

**"`defaultIfEmpty` handles timeouts too."** No. Error handling requires error-aware operators such as `onErrorResume` and an explicit policy.

**"`flatMap` preserves input order."** No. Use `concatMap` or `flatMapSequential` when order matters.

**"`flatMap` over thousands of keys is free because it doesn't block threads."** No. The Redis server, network, client buffers, and memory still have limits. Bound concurrency.

**"`Flux` from `SMEMBERS` has backpressure so Redis only reads a few elements."** Do not assume that. The underlying command can fetch the entire Set before Reactor emits items one by one.

**"`ReactiveRedisTemplate` understands every JSON object automatically."** No. Serializers and schemas must be configured explicitly.

**"Hash fields have individual TTLs like standalone Redis keys."** False under standard Hash key TTL semantics; check API/version support if specialized features exist.

**"Redis Sets always have stable order because they return `Flux`."** No. `Flux` describes how elements are emitted, not ordering inside a Redis Set.

**"HyperLogLog is an exact unique counter."** No. It is an estimation structure.

**"Stream `lastConsumed` automatically ACKs all records."** No. Delivery and ACK are separate, and pending entries require recovery.

**"`.then(...)` creates an atomic transaction."** No. It only chains publisher execution order.

**"Reactive Redis creates distributed transactions with PostgreSQL."** No. Two independent systems require dedicated consistency and recovery architectures.

## 27. Matrix for Choosing Reactive Operations by Problem

| Problem | Group to choose | Notes |
|---|---|---|
| String/config cache | Value | TTL, serializer, cache misses |
| Counters and rate metrics | Value | Use `increment`, not manual `GET`/`SET` |
| Multi-attribute profile | Hash | Field-level updates, key-level TTL |
| Recent activity list | List | Bound `range`, avoid reading everything |
| Tags, membership, unique IDs | Set | Unordered |
| User rankings | Sorted Set | Scores, ranks, cap top N |
| Driver/warehouse locations | Geo | Coordinates, query radius, data permissions |
| Unique user estimation | HyperLogLog | Accepts estimation error |
| Events needing replay/consumer groups | Stream | IDs, offsets, ACK, pending, retention |
| Combining two independent Redis reads | Reactor `Mono.zip` | Does not create an atomic snapshot |
| Step B depends on A | Reactor `flatMap` | Does not guarantee multi-key atomicity |
| Many independent keys | `Flux` + concurrency limit | Avoid excessive fan-out |
| Multi-step atomic operations | Appropriate Redis script/transaction | Do not rely on Reactor chains alone |
| Blocking DB inside WebFlux | Isolate blocking or switch to reactive source | Avoid blocking the event-loop |

Not all data must be stored in Redis using one pattern. Picking the structure closest to the required operations reduces command count and improves maintainability compared to forcing a single JSON Redis String everywhere.

## 28. Workflow for Designing a Reactive Redis Operation

Before writing code, answer in order:

1. **Which Redis data structure represents the data?** String, Hash, List, Set, ZSet, Geo, HyperLogLog, or Stream?
2. **Which native Redis operation expresses the requirement most accurately?** `INCR`, `HGET`, `SISMEMBER`, `ZADD`, `XADD`, etc.
3. **Does the result have at most one value or many?** Use `Mono`/`Flux` appropriately and handle empty results.
4. **Are the operations independent or dependent?** Use `zip`, `flatMap`, `then` per desired semantics.
5. **Are atomicity or ordering required?** If yes, rely on Redis mechanisms and transactions—never infer them from Reactor operators.
6. **Are TTL, serialization, or dedicated namespaces needed?** Decide this upfront in key design.
7. **Could the dataset become very large?** Bound ranges, paginate/scan properly, and avoid unbounded collection.
8. **Can the app face retries, timeouts, or cancellations?** For writes, define idempotency and uncertain write states.
9. **What is the expected concurrency?** Bound fan-out and measure Redis, server, and client behavior.
10. **Who owns subscribing to the publisher?** Controller, worker, scheduler, or another lifecycle manager.
11. **What must be observed in production?** Latency, errors, memory, reconnects, and relevant business metrics.
12. **Are there any blocking points in the flow?** Avoid `.block()` and blocking I/O on the event-loop.

## 29. Conclusion

The Reactive Operations groups in Spring Data Redis bring Redis data structures into the Project Reactor model:

- **`opsForValue()`** for Strings, simple caches, and counters.
- **`opsForHash()`** for multi-field data.
- **`opsForList()`** for ordered lists and head/tail operations.
- **`opsForSet()`** for unique membership.
- **`opsForZSet()`** for rankings/scores.
- **`opsForGeo()`** for coordinates and spatial queries.
- **`opsForHyperLogLog()`** for cardinality estimation.
- **`opsForStream()`** for event records with IDs and consumer groups.

These APIs return `Mono`/`Flux`, enabling `map`, `flatMap`, `zip`, `concatMap`, `then`, and other operators to construct asynchronous flows without blocking while waiting on Redis. Still, **Reactor only orchestrates execution flow**—it does not create Redis transactions, eliminate race conditions in `GET`/`SET` sequences, make heavy commands cheap, or remove the need for retry/idempotency design.

A solid Reactive Redis application begins with **choosing the right data structure, using the matching operations group, keeping publishers properly composed, managing concurrency, and understanding the exact consistency Redis provides**. With those boundaries clear, Reactive Redis is an effective tool for both WebFlux APIs and large-scale asynchronous processing.
