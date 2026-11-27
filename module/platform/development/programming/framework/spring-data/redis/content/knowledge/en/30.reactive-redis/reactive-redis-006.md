# Composing Operations with map, flatMap, concatMap, and then

Spring Data Redis supports **reactive** programming through APIs such as `ReactiveRedisTemplate` and `ReactiveStringRedisTemplate`. Instead of forcing the calling thread to wait for a Redis response with `block()`, each operation returns a Project Reactor publisher, typically `Mono<T>` or `Flux<T>`. The application composes publishers into a processing pipeline and lets the subscriber trigger them.

When writing real business logic, the differences between **`map`, `flatMap`, `concatMap`, and `then`** determine whether a workflow returns the right data, executes in the right order, and avoids unnecessary blocking:

- **`map`:** *synchronously* transforms an emitted value.
- **`flatMap`:** uses an incoming value to create and subscribe to another publisher; very useful for asynchronous Redis calls that depend on an earlier result.
- **`concatMap`:** processes a `Flux` via inner publishers **sequentially**, preserving source emission order.
- **`then`:** waits for upstream to complete successfully, **discards upstream values**, and either completes or runs a subsequent publisher.

This lesson belongs to the **Reactive Redis** chapter of Spring Data Redis and uses Java 21, Spring Boot, Reactor, and Redis to build service-ready examples. The focus is stream semantics—not replacing synchronous calls with a hard-to-follow chain of callbacks.

## 1. Fundamental Model: Redis Returns Publishers, Not Immediate Values

Example in the synchronous API:

~~~java
String value = stringRedisTemplate.opsForValue().get("profile:42");
~~~

In the reactive API:

~~~java
Mono<String> value =
    reactiveRedisTemplate.opsForValue().get("profile:42");
~~~

`value` is a **description of an asynchronous operation**, not the String already read. Spring Data Redis reactive typically issues the Redis command upon subscription. With *cold* publishers created from Redis operations, **each subscription can trigger a fresh Redis access**.

~~~text
ReactiveStringRedisTemplate
            |
            | get("profile:42")
            v
      Mono<String>         no String value available yet
            |
            | map / flatMap / then / ...
            v
      Mono<?> / Flux<?>    describes the operation chain
            |
            | subscribed by WebFlux, StepVerifier, or another subscriber
            v
      Send Redis command
            |
            v
      Emit onNext / onComplete or onError
~~~

With `Mono<T>`, one subscription produces at most one `onNext(T)` followed by `onComplete`, or just `onComplete` if empty, or `onError`. With `Flux<T>`, multiple `onNext` signals may arrive before the terminal signal.

Three signals to distinguish:

| Signal | Meaning | Impact on operators |
| --- | --- | --- |
| `onNext(value)` | A value is available for processing | `map` and `flatMap` apply the mapper to the value |
| `onComplete()` | Stream finished without error | `then` can transition to the next publisher |
| `onError(error)` | Stream failed | Propagates downstream by default; `then` skips the next step |

`Mono.empty()` is not `Mono.just(null)`. Reactor forbids emitting `null` as a value. For instance, Redis `GET` on a non-existent key can return `Mono.empty()`; `map` or `flatMap` mappers are **not invoked** because no `onNext` occurs.

## 2. Reactive Redis APIs to Use

In a Spring Boot project, illustrative dependencies (Gradle Groovy with Spring Boot-managed versions):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

The reactive Redis starter uses an asynchronous-capable driver, commonly Lettuce. A project that only needs reactive Redis without running a WebFlux server can still build reactive pipelines; WebFlux is included here to show returning publishers to the HTTP layer.

Service declaration:

~~~java
package com.example.redis.reactive;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReactiveProfileService {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveProfileService(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }
}
~~~

Commonly used methods:

| Operation | Typical returned publisher | Meaning |
| --- | --- | --- |
| `redis.opsForValue().get(key)` | `Mono<String>` | String value or empty completion when key is missing |
| `redis.opsForValue().set(key, value)` | `Mono<Boolean>` | Write outcome per API |
| `redis.opsForValue().set(key, value, Duration)` | `Mono<Boolean>` | Write value with TTL |
| `redis.opsForValue().increment(key)` | `Mono<Long>` | Counter value after incrementing |
| `redis.delete(key)` | `Mono<Long>` | Number of keys deleted by the operation |
| `redis.hasKey(key)` | `Mono<Boolean>` | Checks whether the key exists |

Element types and exact semantics can vary by operation/template used; do not blindly cast between `Boolean`, `Long`, and `String` just because all call Redis.

## 3. `map` — Synchronously Transforming a Value

`map` receives each upstream value, runs a synchronous transformation function, and emits the transformed value. It **does not start another Redis operation** and provides no mechanism to await another publisher.

Example normalizing a display name after reading from Redis:

~~~java
import java.util.Locale;
import reactor.core.publisher.Mono;

public Mono<String> displayName(String userId) {
    return redis.opsForValue()
        .get("user:" + userId + ":name")
        .map(String::trim)
        .map(name -> name.toUpperCase(Locale.ROOT));
}
~~~

Flow:

~~~text
GET user:42:name
      |
      v
Mono<String> ("  Lan  ")
      |
      v map(String::trim)
    "Lan"
      |
      v map(toUpperCase)
    "LAN"
      |
      v subscriber
~~~

Each mapper receives an **actual value**, not a `Mono`. This transformation suits:

- Trimming whitespace, normalizing characters.
- Converting strings to DTOs or numbers via synchronous code.
- Selecting a field from an object.
- Small CPU computations that do not require asynchronous I/O.

Parsing example:

~~~java
Mono<Long> count = redis.opsForValue()
    .get("metrics:page-views")
    .map(Long::parseLong);
~~~

If the string is not a valid number, `Long.parseLong` throws `NumberFormatException`. Reactor turns that exception into an `onError` signal for downstream handling. Do not automatically convert missing or malformed values into `0` unless business rules explicitly define that behavior.

### When the key does not exist

~~~java
Mono<String> name = redis.opsForValue()
    .get("user:missing:name")
    .map(String::trim)
    .defaultIfEmpty("Unnamed guest");
~~~

When `GET` emits `Mono.empty()`, `map` does not run; `defaultIfEmpty` supplies the fallback value. This is cleaner than checking `name == null` inside the mapper: in Reactor, mappers never receive null values.

### Common mistake: `map` returning `Mono<Mono<T>>`

The following does not sequence operations as intended:

~~~java
Mono<Mono<String>> nested = redis.opsForValue()
    .get("user:42:email")
    .map(email -> redis.opsForValue().get("email:owner:" + email));
~~~

`map` turns `email` into a **Mono object**; the result type becomes `Mono<Mono<String>>`. The inner publisher is not automatically subscribed to fetch the owner data. To make a follow-up Redis call using the email value, use `flatMap`.

## 4. `flatMap` — Depending on an Earlier Result for Asynchronous I/O

`flatMap` takes an upstream value, creates an inner publisher, subscribes to that inner publisher, and flattens its emissions into the outer publisher.

Example reading an email and then looking up the owner's name via another key:

~~~java
public Mono<String> ownerName(String userId) {
    return redis.opsForValue()
        .get("user:" + userId + ":email")
        .flatMap(email ->
            redis.opsForValue().get("email:owner-name:" + email)
        )
        .switchIfEmpty(Mono.just("Not found"));
}
~~~

Execution flow:

~~~text
GET user:42:email
       |
       v
 "lan@example.test"
       |
       v flatMap(email -> GET email:owner-name:<email>)
       |
       v
    "Nguyen Lan"
       |
       v
 subscriber
~~~

The `GET email:owner-name:...` command **only has the full key after** the email read returns a value. `flatMap` expresses this data dependency without blocking threads or calling `block()`.

### Save to Redis then read back the value

~~~java
import java.time.Duration;

public Mono<String> storeThenRead(String key, String value) {
    return redis.opsForValue()
        .set(key, value, Duration.ofMinutes(5))
        .flatMap(saved -> {
            if (!Boolean.TRUE.equals(saved)) {
                return Mono.error(new IllegalStateException(
                    "Redis did not accept the write"
                ));
            }
            return redis.opsForValue().get(key);
        });
}
~~~

`set` returns `Mono<Boolean>`, and `flatMap` inspects the write result to decide whether to issue a follow-up `GET`. If the write failed, the publisher emits an error. If it succeeded, the read runs **after** the write finishes.

Compare with:

~~~java
Mono<String> incorrect = redis.opsForValue()
    .set("example:key", "new")
    .map(saved -> redis.opsForValue().get("example:key"))
    .map(Object::toString);
~~~

That `map` converts a publisher into its `toString()` representation rather than returning the Redis key's content.

### When upstream is empty, `flatMap` does not run

~~~java
Mono<String> result = redis.opsForValue()
    .get("user:missing:email")
    .flatMap(email -> redis.opsForValue().get("owner:" + email))
    .switchIfEmpty(Mono.error(
        new java.util.NoSuchElementException("User not found")
    ));
~~~

If the first step returns `Mono.empty()`, the lambda inside `flatMap` is never invoked. `switchIfEmpty` handles missing data explicitly.

## 5. `flatMap` with `Flux`: Multiple Inner Publishers Can Run Concurrently

When the source is a `Flux<T>`, `flatMap` can subscribe to multiple inner publishers at once. Results are emitted **as they complete**, not necessarily in input element order.

Example loading cached names for multiple products:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

public Flux<String> loadProductNames(List<String> ids) {
    return Flux.fromIterable(ids)
        .flatMap(id ->
            redis.opsForValue()
                .get("product:" + id + ":name")
                .map(value -> id + "=" + value)
                .defaultIfEmpty(id + "=(missing)"),
            8 // Up to 8 active inner publishers per operator configuration.
        );
}
~~~

Given input `["p-1", "p-2", "p-3"]`, output may arrive as:

~~~text
p-2=Keyboard
p-1=Monitor
p-3=Mouse
~~~

That **does not mean Redis misbehaved**: `flatMap` allows waiting for responses concurrently and merges results as data arrives.

Keep two limits in mind:

1. `concurrency=8` is an operator-level limit on active inner publishers, not an exact guarantee on socket count or simultaneous commands on the Redis server.
2. Merging does not preserve input element order. If business logic requires preserving order, choose another operator.

### When should you use `flatMap`?

Appropriate when:

- Each source element triggers an independent Redis operation.
- Output order does not matter, or items carry IDs and can be sorted later.
- You want bounded concurrency for higher throughput.
- Load on Redis and downstream resources can be kept bounded.

Avoid unbounded `flatMap` on streams with huge item counts assuming Redis, the driver, and memory can always handle the load. `Flux.flatMap` provides `concurrency` and `prefetch` overloads; configure them intentionally rather than relying blindly on defaults.

## 6. `concatMap` — Processing Each Publisher in Order

`concatMap` is for `Flux`. It maps each element to an inner publisher, but **only subscribes to the next inner publisher after the previous one completes**. Consequently, outputs preserve the source's inner-publisher order for all emitted items.

Example writing status updates in order of occurrence:

~~~java
public Flux<Boolean> writeStatusesInOrder(List<String> statuses) {
    return Flux.fromIterable(statuses)
        .concatMap(status ->
            redis.opsForValue()
                .set("demo:current-status", status)
        );
}
~~~

Given input `["RECEIVED", "VALIDATED", "COMPLETED"]`, the application issues `SET` commands sequentially: the next command is only subscribed to once the previous one finishes. Thus, **within this stream**, operations run in the expected order.

~~~text
Flux:       RECEIVED    VALIDATED    COMPLETED
                |           |            |
                v           |            |
           SET RECEIVED     |            |
                |           |            |
           complete         |            |
                |           v            |
                |      SET VALIDATED     |
                |           |            |
                |      complete          |
                |           |            v
                |           |      SET COMPLETED
                |           |            |
                v           v            v
            Result 1    Result 2     Result 3
~~~

This example **is not a transaction** and does not lock the key against other clients. Another service can still modify `demo:current-status` between steps; `concatMap` only enforces subscription and completion ordering **within this pipeline**.

### Comparing on the same `Flux` source

~~~java
Flux<String> keys = Flux.just("a", "b", "c");

Flux<String> concurrently = keys.flatMap(key ->
    redis.opsForValue()
        .get(key)
        .defaultIfEmpty("(missing)")
);

Flux<String> sequentially = keys.concatMap(key ->
    redis.opsForValue()
        .get(key)
        .defaultIfEmpty("(missing)")
);
~~~

| Property | `flatMap` | `concatMap` |
| --- | --- | --- |
| Inner publisher execution | Can be concurrent | Sequential, one inner publisher at a time |
| Result order | May be out of order | Preserves source inner order |
| Throughput on independent I/O | Can be higher | Can be lower due to waiting per step |
| When processing has ordering dependencies | Needs extra design | Better suited when ordering is required |
| Concurrency control | Uses `concurrency` parameter | Semantically processes one inner at a time |

Reactor also offers `flatMapSequential`: it subscribes to several inner publishers concurrently while **emitting results in source order**, buffering results that finish early. Useful for balancing throughput and output order, at the cost of extra memory. `concatMap` is the easiest to reason about when **side effects themselves** must execute sequentially.

### `concatMap` and business-level ordering guarantees

Do not conclude that using `concatMap` alone guarantees system-wide event ordering:

- Two different HTTP requests create **two separate subscriptions** that run in parallel.
- Multiple application instances run independent pipelines.
- Another subscriber may write to the same Redis key.
- Retries after failures may re-execute an earlier operation.

If global ordering or state constraints across multiple writers are required, add single-writer routing, versioning, optimistic locking, Lua scripts, or an appropriate business protocol.

## 7. `then` — Waiting for Completion, Ignoring Upstream Values

`then` differs from `map` and `flatMap` because it cares about the **completion signal** rather than data values:

~~~java
Mono<Void> completed = redis.opsForValue()
    .set("demo:key", "value")
    .then();
~~~

`set` normally emits a `Boolean`; `then()` **discards that value** and returns `Mono<Void>` once upstream completes successfully. If upstream errors, the error still propagates downstream.

Pay special attention: if upstream emits `Boolean.FALSE` yet **completes normally**, `then()` treats the stream as completed; it does not interpret `false` as a business failure. When you must verify `Boolean.TRUE`, check it before `then()`.

~~~java
Mono<Void> safelyWritten = redis.opsForValue()
    .set("demo:key", "value")
    .flatMap(ok -> Boolean.TRUE.equals(ok)
        ? Mono.<Void>empty()
        : Mono.<Void>error(
            new IllegalStateException("Write not accepted")
        )
    );
~~~

### Chaining operation A then operation B with `then(Mono)`

Example writing an audit entry before invalidating cache:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

public Mono<Long> auditThenDelete(String id) {
    String auditKey = "audit:last-invalidated:" + id;
    String cacheKey = "cache:profile:" + id;

    return redis.opsForValue()
        .set(auditKey, "INVALIDATE", Duration.ofDays(1))
        .flatMap(ok -> Boolean.TRUE.equals(ok)
            ? Mono.just(true)
            : Mono.<Boolean>error(
                new IllegalStateException("Audit write failed")
            )
        )
        .then(redis.delete(cacheKey));
}
~~~

The result of `auditThenDelete` is `Mono<Long>`, emitting the number of deleted cache keys. It does not emit the audit command's `Boolean` because `then(...)` discards the upstream value.

~~~text
SET audit ... (with TTL)
         |
         v
    Check Boolean
         |
         +-- false/error --> onError, skip DELETE
         |
         v
   upstream complete
         |
         v
   DELETE cache:profile:id
         |
         v
     Mono<Long>
~~~

**`then` orders execution within one subscription; it does not create an atomic transaction.** If the audit write succeeds and Redis fails before `DELETE`, the audit record remains while the cache is not deleted. If business rules require both changes atomically, use a specialized Redis mechanism or another coordination design.

### `thenReturn` and `thenMany`

Common variants:

~~~java
Mono<String> confirmation = redis.opsForValue()
    .set("demo:flag", "READY")
    .thenReturn("Write request submitted");
~~~

`thenReturn(value)` discards the upstream value and emits a fixed value once upstream completes. Note that the chain above only confirms upstream completed; it **does not check `Boolean.TRUE`**. Add a check before `thenReturn` if needed.

~~~java
Flux<String> values = redis.opsForValue()
    .set("demo:prepared", "1")
    .thenMany(
        Flux.just("key:a", "key:b")
            .concatMap(key ->
                redis.opsForValue()
                    .get(key)
                    .defaultIfEmpty("(missing)")
            )
    );
~~~

`thenMany` waits for the preceding publisher to complete and then switches to another `Flux`. This fits "prepare" then "emit multiple results" sequences.

### Difference between `then` and `flatMap` when upstream is empty

~~~java
Mono<String> missing =
    redis.opsForValue().get("nonexistent");

Mono<String> viaFlatMap =
    missing.flatMap(value -> redis.opsForValue().get("fallback"));

Mono<String> viaThen =
    missing.then(redis.opsForValue().get("fallback"));
~~~

If `missing` completes empty:

- `viaFlatMap` also completes empty, **never calling** `GET fallback`.
- `viaThen` still calls `GET fallback`, because it only waits for upstream to **complete without error**, requiring no `onNext`.

Therefore, for "if Redis lacks the key, query another source," the right operator is usually **`switchIfEmpty`**, not `then`:

~~~java
Mono<String> value = redis.opsForValue()
    .get("cache:key")
    .switchIfEmpty(loadFromSource());
~~~

If `loadFromSource()` has side effects right when **constructing the publisher**, wrap it in `Mono.defer(() -> loadFromSource())` to defer constructing the fallback source until actually needed. With a proper cold publisher API, subscribing to the fallback only happens when upstream is empty.

## 8. Operator Selection Table by Purpose

| Purpose | Primary operator | Example |
| --- | --- | --- |
| Normalize GET result | `map` | `get(key).map(String::trim)` |
| Parse JSON to DTO with light synchronous code | `map` | `get(key).map(jsonMapper::read...)` with proper exception handling |
| Read another Redis key from an ID | `flatMap` | `get(userKey).flatMap(v -> get(otherKey(v)))` |
| Write Redis then read based on write result | `flatMap` | `set(...).flatMap(ok -> get(...))` |
| Many independent keys allowing concurrency | `Flux.flatMap` | `Flux.fromIterable(ids).flatMap(this::load, 8)` |
| Process mutations in input order | `Flux.concatMap` | `Flux.fromIterable(events).concatMap(this::apply)` |
| Wait for A to finish then run B, ignoring A's value | `then` | `writeAudit().then(deleteCache())` |
| Only need completion signal | `then()` | `delete(key).then()` |
| Complete A then emit a fixed value | `thenReturn` | `write().thenReturn("ok")` |
| Complete A then emit multiple elements from B | `thenMany` | `initialize().thenMany(loadAll())` |
| When GET has no data | `switchIfEmpty` | `get(key).switchIfEmpty(load())` |

Quick decision flow:

~~~text
Have an upstream value?
         |
         +-- Need synchronous value transformation? --------> map
         |
         +-- Need another publisher depending on it? -------> flatMap
         |
         +-- Multiple values needing ordered processing? ---> concatMap
         |
         +-- Only await completion, discard value? ---------> then
~~~

## 9. A Business Example Combining Multiple Operators

Suppose a service receives a list of product IDs and needs to:

1. Read each product's name from Redis.
2. Normalize the name with `trim()`.
3. Write a "last-viewed" marker for each ID.
4. Return results in the exact order of the input IDs.

A reactive implementation:

~~~java
package com.example.redis.reactive;

import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductViewService {

    private final ReactiveStringRedisTemplate redis;

    public ProductViewService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public record ProductView(String id, String name) {
    }

    public Flux<ProductView> loadAndRecordViews(List<String> ids) {
        return Flux.fromIterable(ids)
            .concatMap(id -> {
                String productKey = "product:" + id + ":name";
                String viewKey = "product:" + id + ":last-viewed";

                return redis.opsForValue()
                    .get(productKey)
                    .map(String::trim)
                    .filter(name -> !name.isBlank())
                    .flatMap(name ->
                        redis.opsForValue()
                            .set(
                                viewKey,
                                "viewed",
                                Duration.ofMinutes(1)
                            )
                            .flatMap(saved -> Boolean.TRUE.equals(saved)
                                ? Mono.just(new ProductView(id, name))
                                : Mono.<ProductView>error(
                                    new IllegalStateException(
                                        "Cannot write view marker for " + id
                                    )
                                )
                            )
                    )
                    .switchIfEmpty(
                        Mono.just(new ProductView(id, "(missing)"))
                    );
            });
    }
}
~~~

For each ID, the pipeline performs:

~~~text
id
 |
 v
GET product:<id>:name
 |
 +-- missing/blank string --> ProductView(id, "(missing)")
 |
 v
map(trim) + filter
 |
 v
flatMap(SET last-viewed with TTL)
 |
 +-- returns false --> onError
 |
 v
ProductView(id, name)
 |
 v
concatMap advances to next ID
~~~

Operator breakdown:

- `map(String::trim)` transforms the already-fetched value without calling Redis.
- `filter` turns blank strings into empty completions.
- `flatMap` writes the Redis marker before emitting `ProductView`.
- `switchIfEmpty` supplies a placeholder record for products with no name in cache. It handles **empty** only, without hiding Redis errors.
- `concatMap` ensures the read/write chain of the **next ID** starts only after the previous ID's publisher completes.

For applications that only display data and do not require ordered side effects, switching `concatMap` to `flatMap(..., concurrency)` allows reading multiple keys concurrently, though output order may no longer match input ID order.

### Why not use `then` in this example?

We need to keep the product name to construct `ProductView`. Replacing the write check block with `thenReturn(new ProductView(id, name))` without inspecting the `Boolean` would still emit success even if `SET` completed normally with `false`. `flatMap` fits better because we need **the return value of Redis SET** to decide.

However, if business logic only needs to wait for a command already validated via a checking operator and then return a DTO, you can combine `thenReturn` after the check:

~~~java
Mono<ProductViewService.ProductView> result =
    redis.opsForValue()
        .set("view:key", "1")
        .filter(Boolean.TRUE::equals)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("SET rejected")
        ))
        .thenReturn(new ProductViewService.ProductView(
            "p-1", "Keyboard"
        ));
~~~

## 10. What Happens When an Error Occurs?

In a reactive pipeline, a Redis error or mapper exception produces an `onError` signal. By default, this error terminates the downstream chain:

~~~java
Flux<String> results = Flux.just("a", "b", "c")
    .concatMap(key -> redis.opsForValue().get(key));
~~~

If querying `b` emits an error, the chain stops before processing `c`. In a concurrent `flatMap`, other inner publishers may already have started before the error is observed; downstream cancellation **does not guarantee** Redis commands already sent will be undone.

### Recovering per item or for the entire pipeline?

If one key fails to read yet you want the remaining keys to continue:

~~~java
Flux<String> resilient = Flux.just("a", "b", "c")
    .concatMap(key ->
        redis.opsForValue()
            .get(key)
            .defaultIfEmpty("(missing)")
            .onErrorResume(error ->
                Mono.just("(error reading " + key + ")")
            )
    );
~~~

Place `onErrorResume` **inside** `concatMap` so a single key's error is handled at item scope. Placing it at the end of the whole chain causes the first error to replace the rest of the stream with a single fallback value and terminate the stream.

Never use `onErrorResume(e -> Mono.empty())` across all errors and treat missing data as normal—especially for timeouts, authentication failures, or Redis downtime. Distinguish missing keys (`Mono.empty()`) from failed Redis operations (`Mono.error(...)`).

### Retries can re-run operations

~~~java
Mono<Long> incremented = redis.opsForValue()
    .increment("counter:orders")
    .retry(1);
~~~

This is **dangerous if a timeout happens after Redis already executed `INCR` but before the client receives the response**: the retry can increment twice.

Retries are often needed for transient network errors, but must be based on error classification, backoff, idempotency, and observability of actual state. `retry` does not make a non-idempotent operation safe.

When conditional atomic updates are needed, use appropriate Redis operations or scripts/protocols; chaining `get().flatMap(current -> set(...))` itself is **not** an atomic read-modify-write under concurrent writers.

## 11. Subscription, Backpressure, and Avoiding `block()`

A Reactor pipeline needs a subscriber:

~~~java
Mono<String> name = redis.opsForValue()
    .get("user:42:name")
    .map(String::trim);

// Only created the publisher; no String result has been fetched yet.
~~~

In a WebFlux Controller, the standard pattern is **returning the publisher**:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/users")
class UserController {

    private final ReactiveProfileService service;

    UserController(ReactiveProfileService service) {
        this.service = service;
    }

    @GetMapping("/{id}/name")
    Mono<String> name(@PathVariable String id) {
        return service.displayName(id);
    }
}
~~~

This illustrates the controller piece; `ReactiveProfileService` must implement `displayName` as shown earlier. Spring WebFlux subscribes to and consumes the publisher during the HTTP request lifecycle.

Avoid writing:

~~~java
// Anti-pattern on a reactive processing path:
String value = redis.opsForValue().get("user:42:name").block();
~~~

`block()` blocks the thread waiting on Redis, defeating the primary benefit of non-blocking I/O. On Reactor/Netty non-blocking threads, calling `block()` can throw an exception or severely reduce concurrency. Only use it at explicitly controlled synchronous boundaries, not as the default way to compose logic.

Another anti-pattern:

~~~java
public Mono<String> updateAndRead(String key) {
    redis.opsForValue().set(key, "NEW").subscribe();
    return redis.opsForValue().get(key);
}
~~~

Here there are **two independent subscriptions**. There is no guarantee `SET` completes before `GET`. Errors in the write subscription are also detached from the flow the HTTP caller awaits. To preserve ordering and error propagation, **compose**:

~~~java
public Mono<String> updateAndRead(String key) {
    return redis.opsForValue()
        .set(key, "NEW")
        .filter(Boolean.TRUE::equals)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("SET rejected")
        ))
        .then(redis.opsForValue().get(key));
}
~~~

### Backpressure does not automatically bound all load sources

Reactor supports request-demand signaling between publisher and subscriber, yet that does not mean Redis creates an unboundedly safe queue for every operator. If an input `Flux` has millions of items and uses `flatMap` with high concurrency, pressure on Redis and application memory remains substantial.

Good practices:

- Use `flatMap(mapper, concurrency)` when I/O operations are independent but active publishers must be capped.
- Use `concatMap` when ordering matters or inner publishers must execute sequentially.
- Do not call `collectList()` on large streams when streaming processing suffices.
- Configure timeouts per business requirements and use bounded retry policies.
- Monitor connection pools, pending requests, Redis latency, and memory.

## 12. Understanding Atomicity When Composing Redis Operations

Reactor operators define **data dependencies and subscription ordering**, not Redis transactions.

Example:

~~~java
Mono<String> sequence = redis.opsForValue()
    .get("stock:sku-42")
    .flatMap(raw -> {
        long stock = Long.parseLong(raw);
        long updated = stock - 1;
        return redis.opsForValue()
            .set("stock:sku-42", Long.toString(updated))
            .thenReturn("done");
    });
~~~

Two clients reading `10` simultaneously can both write `9`, resulting in a **lost update**. `flatMap` only ensures a single request's write depends on its own read; it does not lock the Redis key against other requests.

If you merely need to decrement a numeric counter already stored in Redis, use an atomic command:

~~~java
Mono<Long> stockAfter =
    redis.opsForValue().decrement("stock:sku-42");
~~~

If you need to prevent decrementing below 0, a standalone `DECR` is not enough; consider a Lua script that checks and decrements in one Redis operation, or another concurrency control suited to your topology.

Similarly:

~~~java
redis.opsForValue().set("session:42", "ACTIVE")
    .then(redis.expire("session:42", Duration.ofMinutes(30)));
~~~

Even though `then` orders the two commands, if `SET` succeeds and the connection drops before `EXPIRE`, the key may lack a TTL. In this case, prefer writing **with TTL**:

~~~java
Mono<Boolean> result = redis.opsForValue()
    .set("session:42", "ACTIVE", Duration.ofMinutes(30));
~~~

All commands in these examples use `ReactiveStringRedisTemplate`, so keys/values are strings. When using `ReactiveRedisTemplate<K, V>` with custom serializers, review the corresponding mappings and publisher types.

## 13. Testing Operators with StepVerifier

`StepVerifier` is the `reactor-test` tool for subscribing to publishers and asserting `onNext`, `onComplete`, and `onError` signals. For this lesson, separate:

1. **Operator semantics unit tests** without Redis, using `Mono`/`Flux` test publishers.
2. **Integration tests** against real Redis to verify Spring Data Redis read/write paths and composition.

### 13.1. Unit tests: `map`, `flatMap`, `concatMap`, and `then`

~~~java
import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import org.junit.jupiter.api.Test;

class ReactorCompositionTest {

    @Test
    void mapTransformsValue() {
        Mono<String> result = Mono.just("  Lan  ")
            .map(String::trim);

        StepVerifier.create(result)
            .expectNext("Lan")
            .verifyComplete();
    }

    @Test
    void flatMapFlattensAnotherPublisher() {
        Mono<String> result = Mono.just("42")
            .flatMap(id -> Mono.just("user:" + id));

        StepVerifier.create(result)
            .expectNext("user:42")
            .verifyComplete();
    }

    @Test
    void concatMapKeepsSourceOrder() {
        Flux<String> result = Flux.just("first", "second", "third")
            .concatMap(value ->
                Mono.just(value)
                    .delayElement(Duration.ofMillis(
                        "first".equals(value) ? 30 : 5
                    ))
            );

        StepVerifier.create(result)
            .expectNext("first", "second", "third")
            .verifyComplete();
    }

    @Test
    void thenIgnoresValueAndRunsNextPublisher() {
        Mono<String> result = Mono.just("ignored")
            .then(Mono.just("after"));

        StepVerifier.create(result)
            .expectNext("after")
            .verifyComplete();
    }

    @Test
    void flatMapSkipsMapperWhenUpstreamIsEmpty() {
        Mono<String> result = Mono.<String>empty()
            .flatMap(value -> Mono.just("should-not-run"))
            .defaultIfEmpty("fallback");

        StepVerifier.create(result)
            .expectNext("fallback")
            .verifyComplete();
    }
}
~~~

The delays in the `concatMap` test merely simulate inner publishers with varying latencies; **assertions verify ordering**, not network performance, and do not depend on exact `Thread.sleep` timings.

### 13.2. Spring Data Redis integration test with Testcontainers

Example Spring Boot + real Redis test verifying a `SET` composed with `GET` via `then` and the final value:

~~~java
package com.example.redis.reactive;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Testcontainers
@SpringBootTest(classes = ReactiveRedisCompositionTest.TestApp.class)
class ReactiveRedisCompositionTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    ReactiveStringRedisTemplate redis;

    @Test
    void writeThenReadIsOrderedWithinSubscription() {
        String key = "test:reactive:" + UUID.randomUUID();

        Mono<String> workflow = redis.opsForValue()
            .set(key, "hello")
            .filter(Boolean.TRUE::equals)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("SET rejected")
            ))
            .then(redis.opsForValue().get(key));

        try {
            StepVerifier.create(workflow)
                .expectNext("hello")
                .verifyComplete();
        } finally {
            // Test cleanup: subscribe to delete the key; never call block()
            // on production reactive request paths.
            StepVerifier.create(redis.delete(key))
                .expectNextCount(1)
                .verifyComplete();
        }
    }
}
~~~

This example assumes auto-configuration creates `ReactiveStringRedisTemplate` for the test Redis properties; the machine running integration tests needs Docker or a compatible container runtime. `try/finally` cleans up the key even if assertions fail. This test proves ordering within one subscription; **it does not prove the operations form a Redis transaction**.

### 13.3. Testing that errors skip subsequent steps

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

AtomicBoolean secondStarted = new AtomicBoolean(false);

Mono<String> sequence = Mono.<String>error(
        new IllegalStateException("first step failed")
    )
    .then(Mono.defer(() -> {
        secondStarted.set(true);
        return Mono.just("second");
    }));

StepVerifier.create(sequence)
    .expectError(IllegalStateException.class)
    .verify();

assertThat(secondStarted.get()).isFalse();
~~~

In this test snippet, `assertThat` is an AssertJ assertion. `Mono.defer` accurately verifies that the second publisher is neither constructed nor subscribed to after upstream emits `onError`.

## 14. Common Mistakes When Composing Operations

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Returning `Mono<Mono<T>>` | Used `map` to create an inner publisher | Use `flatMap` when chaining another reactive operation |
| `map`/`flatMap` never runs | `GET` returned `Mono.empty()` | Handle with `defaultIfEmpty` or `switchIfEmpty` |
| Results for multiple keys arrive out of order | Used `Flux.flatMap` with concurrent inner publishers | Use `concatMap` for sequential execution; consider `flatMapSequential` if only output order matters |
| Seeing Publisher `toString()` instead of Redis data | Missing subscription or logging `Mono.toString()` | Return the publisher to WebFlux or use `StepVerifier` in tests |
| Writing and reading same key yields stale data | Two independent `subscribe()` calls | Compose with `flatMap` or `then` |
| Operation returning `false` still runs next step | `then` discards upstream value | Inspect the `Boolean` via `flatMap`/`filter` before `then` |
| `then` drops data needed later | Operator intentionally discards `onNext` | Use `map`/`flatMap` when the value must be preserved |
| One error stops the entire `Flux` | `onError` escaped the inner publisher | Place `onErrorResume` inside the item scope if allowed by business rules |
| Retry triggers an extra `INCR` | Timeout occurred after Redis processed the command | Design idempotency and controlled retries |
| `block()` slows down or fails WebFlux | Blocked a non-blocking thread | Compose publishers; let WebFlux subscribe |
| `concatMap` runs slower than expected | Intentionally awaits each inner publisher | Use bounded `flatMap` if operations are independent |
| Composing `get().flatMap(set())` still has races | Operators do not create transactions | Use Redis atomic operations/scripts or versioning |
| `SET` then `EXPIRE` via `then` still drops TTL | Two commands are not atomic across failures | Use `set(key, value, Duration)` |
| Subscribing twice to a publisher writes twice | Cold publisher runs per subscription | Manage subscription lifecycle; avoid casual extra subscriptions |
| Large `Flux` overloads Redis | Unbounded concurrency and downstream buffering | Set concurrency limits and monitor heap/connections/latency |

## 15. Guidelines for Project Adoption

When implementing reactive Redis with Spring Data Redis:

1. **Write services that return publishers.** Never call `block()` or manual `subscribe()` inside a reactive request path just to unwrap results.
2. **Use `map` for light synchronous transformations.** Blocking tasks like JDBC or synchronous file I/O require proper integration layers and schedulers; `map` does not make blocking code non-blocking.
3. **Use `flatMap` when a later operation depends on an earlier result.** Handle empty and error cases explicitly.
4. **Use `concatMap` when inner operation order truly matters.** If you only need ordered outputs with concurrency, evaluate `flatMapSequential` and its buffering cost.
5. **Use `then` when only completion matters.** If the preceding publisher returns a `Boolean` or business status, validate it before discarding it.
6. **Bound concurrency.** When processing many keys, specify explicit concurrency and never spawn millions of simultaneous subscriptions.
7. **Design error handling and retries.** Do not mask every Redis failure with default values; distinguish misses, timeouts, and data errors.
8. **Never confuse composition with atomicity.** Ordering created by `then`/`concatMap` is only pipeline order—it does not block other writers or roll back completed steps.
9. **Test Reactor signals.** `StepVerifier` verifies values, empty completions, errors, completion, and ordering; integration tests confirm Redis executes the expected commands.

## 16. Conclusion

`map`, `flatMap`, `concatMap`, and `then` are essential tools for composing Spring Data Redis reactive operations into clear pipelines:

- **`map`** transforms an existing value.
- **`flatMap`** passes a value into another asynchronous publisher and flattens the result.
- **`concatMap`** executes publishers produced from a `Flux` sequentially, preserving source order.
- **`then`** awaits completion, discards the prior result, and continues to the next step on success.

Sound design goes beyond picking the right operator. You must understand that `Mono.empty()` differs from errors, subscriptions trigger Redis execution, retries can replay side effects, and operators **do not automatically create Redis transactions**. When those boundaries stay clear, reactive code is easier to read, easier to test, and unlocks non-blocking I/O without sacrificing business correctness.
