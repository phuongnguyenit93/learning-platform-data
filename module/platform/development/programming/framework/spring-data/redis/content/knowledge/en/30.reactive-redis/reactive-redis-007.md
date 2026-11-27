# Subscriptions, Repeated Command Execution, and Avoiding Manual subscribe() in Spring Data Redis Reactive

In Spring Data Redis Reactive, a call like `redis.opsForValue().set(key, value)` normally does not send a Redis command immediately. It returns a Project Reactor **Publisher**, such as `Mono<Boolean>`, describing the work to perform **when subscribed to**. Therefore, the very same code can have three completely different outcomes:

- Creating the `Mono` without anyone subscribing: **no Redis command is executed**.
- One subscriber subscribes: the Redis command executes along the reactive flow.
- Two subscribers subscribe independently to a cold Publisher: **the command can execute twice**.

This behavior is both a strength of reactive programming and a subtle source of bugs. An extra `GET` might only waste resources, whereas triggering `INCR`, `LPUSH`, `PUBLISH`, or a key deletion multiple times can corrupt business data.

This lesson focuses on the **subscription lifecycle**, **repeated command execution caused by subscribe/retry/repeat**, and **composing Spring WebFlux/Reactive Redis flows** so the framework manages execution instead of calling `subscribe()` manually inside services.

## 1. Mono, Flux, and the Meaning of Subscription

Reactive Streams defines two key roles:

- **Publisher:** source emitting elements, errors, or a completion signal.
- **Subscriber:** consumer registering to receive signals, capable of requesting data and canceling the subscription.

Project Reactor provides:

| Type | Maximum elements | Common Redis usage |
|---|---|---|
| `Mono<T>` | 0 or 1 | `GET`, `SET`, `INCR`, `DEL` |
| `Mono<Void>` | Emits no data, only completion or error | A command chain where only completion confirmation is needed |
| `Flux<T>` | 0 to many | `SCAN`, reading sets, lists, streams, or Pub/Sub |

When you write:

```java
Mono<Boolean> write =
        redis.opsForValue().set("demo:332:state", "READY");
```

`write` is **a description of an asynchronous operation**. It is not a `Boolean` indicating Redis already saved the value. Under the cold publisher model of standard Reactive Redis operations, the command is issued when subscribed to.

### 1.1. Three phases: assembly, subscription, signal

```text
Phase 1 — Assembly
  ReactiveStringRedisTemplate
       |
       +-- opsForValue().set(...)
                |
                v
             Mono<Boolean>
       (builds pipeline, usually does not call Redis yet)

Phase 2 — Subscription
  Subscriber / WebFlux / StepVerifier
                |
                v
             subscribe
                |
                v
          driver sends Redis command

Phase 3 — Signal
  Redis responds
       |
       +--> onNext(Boolean) (if a value is emitted)
       +--> onComplete()
       +--> or onError(exception)
```

In Reactive Streams, a subscriber also has mechanisms to request data (`request(n)`) and cancel (`cancel()`). Reactor and Spring integration classes normally handle these signals for the application; you do not need to write a low-level `Subscriber` for every Redis command.

**Never equate "created a Publisher" with "executed a command."** This is the core difference from blocking `RedisTemplate`: imperative methods normally perform the work during the call and return the result or throw an exception directly.

## 2. Spring Data Redis Reactive Example Setup

A Spring Boot WebFlux application can declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Example test Redis connection in `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 3s
```

With appropriate configuration, Spring Boot auto-configures a `ReactiveStringRedisTemplate` bean. The examples use this template because both keys and values are Strings, making them easy to observe via Redis CLI and avoiding extra JSON serializer setup. In applications with complex models, use `ReactiveRedisTemplate<K,V>` with a suitable `RedisSerializationContext`.

Illustrative service:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveStatusService {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveStatusService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> save(String id, String status) {
        return redis.opsForValue().set("status:" + id, status);
    }

    public Mono<String> find(String id) {
        return redis.opsForValue().get("status:" + id);
    }
}
```

Methods **return Publishers to the caller** instead of calling `subscribe()` themselves. The caller decides how to compose the command with the rest of the flow, and the framework decides when subscription happens.

## 3. Unsubscribed Publisher: No Side Effects Occur

Consider:

```java
public void wrongSave(String id) {
    Mono<Boolean> ignored =
            redis.opsForValue().set("status:" + id, "READY");

    // No subscribe, no return, not chained into a pipeline.
}
```

Even though the source calls `set(...)`, the publisher's write effect is never triggered. The Redis key may still not exist:

```redis
GET status:332
# (nil) if nobody else wrote this key
```

The same situation occurs when chaining operators that only describe operations:

```java
Mono<String> source = redis.opsForValue().get("status:332");

source.map(String::toUpperCase);
// Only creates a new Publisher and discards it; nothing subscribes.
```

Or when a side effect merely constructs a Publisher inside a callback:

```java
return redis.opsForValue().get("status:332")
        .doOnNext(value -> {
            redis.opsForValue().set("audit:332", value);
            // Mono<Boolean> is discarded; no audit write executes.
        });
```

`doOnNext` runs the callback when data arrives, but the callback creates another Publisher without wiring it into the pipeline. The `set` call here will not run just because it appears inside the lambda.

### Writing it properly with flatMap

```java
public Mono<String> readAndAudit(String id) {
    String statusKey = "status:" + id;
    String auditKey = "audit:" + id;

    return redis.opsForValue().get(statusKey)
            .flatMap(value ->
                    redis.opsForValue().set(auditKey, value)
                            .thenReturn(value));
}
```

`flatMap` integrates the inner Publisher into the current chain, and `thenReturn(value)` re-emits the value only after the write finishes successfully. When the caller subscribes to the outer stream, both `GET` and `SET` are on the execution path.

**Rule:** if an operation returns a `Mono` or `Flux` whose effect must happen, **compose** it with `flatMap`, `concatMap`, `then`, `zipWhen`, `when`, or another suitable operator—never call the method and discard the Publisher.

## 4. One Subscription, One Execution; Repeated Subscriptions Send Repeated Commands

For most regular Redis operations, the Publisher is **cold**: each subscriber starts the flow from the beginning and makes the source redo the work.

Example:

```java
Mono<Long> increment =
        redis.opsForValue().increment("counter:332");

increment.subscribe(result ->
        System.out.println("first = " + result));

increment.subscribe(result ->
        System.out.println("second = " + result));
```

Two `subscribe` calls on the same `Mono<Long>` can issue **two `INCR` commands**:

```text
counter:332 initially = 0

Subscriber A --------> INCR counter:332 ---> 1
Subscriber B --------> INCR counter:332 ---> 2

Final value in Redis: 2
```

Because execution is asynchronous, do not assume Subscriber A always gets `1` and Subscriber B always gets `2`. What is certain in a non-error scenario is two increments from two subscriptions, while completion order depends on actual scheduling.

### 4.1. A very common WebFlux bug

```java
public Mono<Long> wrongIncrement() {
    Mono<Long> operation =
            redis.opsForValue().increment("counter:332");

    operation.subscribe(value ->
            System.out.println("log value = " + value));

    return operation;
}
```

In WebFlux, the framework subscribes to the returned Publisher to build the HTTP response. Because the service already subscribed manually once, **two `INCR` commands** can happen: one from the manual logging subscription and one from WebFlux.

Correct:

```java
public Mono<Long> incrementAndLog() {
    return redis.opsForValue()
            .increment("counter:332")
            .doOnNext(value ->
                    System.out.println("counter = " + value));
}
```

`doOnNext` does not create a subscription on its own. When the HTTP layer subscribes once, the chain runs one increment and one attached log action. Use a logging framework rather than `System.out` in production.

### 4.2. Use doOnSubscribe for observation, not to trigger the source

```java
Mono<Long> increment =
        redis.opsForValue().increment("counter:332")
                .doOnSubscribe(subscription ->
                        System.out.println("A subscription started"));
```

Nothing is logged from `doOnSubscribe` without a subscriber. If the Publisher is subscribed to twice, the log appears twice. `doOnSubscribe` is useful for investigating subscription counts, but you should not put data-mutating business logic inside this callback.

## 5. Return Mono/Flux from WebFlux, Never Subscribe in Controllers/Services

A reactive endpoint should return a Publisher:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/counters")
public class CounterController {

    private final ReactiveStringRedisTemplate redis;

    public CounterController(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    @PostMapping("/{name}/increment")
    public Mono<Long> increment(@PathVariable String name) {
        return redis.opsForValue().increment("counter:" + name);
    }

    @GetMapping("/{name}")
    public Mono<ResponseEntity<String>> read(@PathVariable String name) {
        return redis.opsForValue().get("counter:" + name)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

Proper flow:

```text
HTTP POST /api/counters/demo/increment
      |
      v
Controller returns Mono<Long>
      |
      v
Spring WebFlux handles response and subscribes
      |
      v
Reactive Redis sends INCR
      |
      v
Mono emits new counter value
      |
      v
WebFlux writes HTTP response
```

Returning `Mono` for WebFlux to handle ensures:

- Redis errors enter the request's error-handling chain.
- Subscription lifetime is tied to the request/response lifecycle.
- Cancellation propagates from downstream.
- Trace context and operators like `timeout`, `retryWhen`, and `onErrorResume` stay in one unified flow.
- You do not have to manage a `Disposable` manually for each HTTP request.

**Never return `Mono.just("OK")` after manually calling `subscribe()` on a Redis write and treat it as finished.** The HTTP response could report success before Redis finishes writing or even if the write fails.

Incorrect example:

```java
@PostMapping("/wrong")
public Mono<String> wrong() {
    redis.opsForValue()
            .set("order:332", "APPROVED")
            .subscribe();

    return Mono.just("OK");
}
```

Fixed:

```java
@PostMapping("/correct")
public Mono<ResponseEntity<Void>> correct() {
    return redis.opsForValue()
            .set("order:332", "APPROVED")
            .thenReturn(ResponseEntity.noContent().build());
}
```

`thenReturn` runs only after `set` completes successfully. It does not turn Redis into a transaction with a database or another system, yet it guarantees the response of this flow depends on the Redis operation completing.

## 6. Composing Multiple Redis Operations While Subscribing Only at the Boundary

### 6.1. Write before read: then

```java
public Mono<String> saveThenRead(String id, String value) {
    String key = "status:" + id;

    return redis.opsForValue().set(key, value)
            .then(redis.opsForValue().get(key));
}
```

Upon subscription, Spring runs `SET`, waits for it to finish, and only then subscribes to `GET`. The Boolean result from `SET` is discarded by `then`.

### 6.2. Run conditional commands: flatMap

```java
public Mono<Boolean> markDoneIfPending(String id) {
    String key = "task:" + id;

    return redis.opsForValue().get(key)
            .flatMap(current -> {
                if (!"PENDING".equals(current)) {
                    return Mono.just(false);
                }

                return redis.opsForValue().set(key, "DONE");
            })
            .defaultIfEmpty(false);
}
```

The snippet above **only illustrates composition** and still has a race condition: another client could modify the key between `GET` and `SET`. If business logic needs atomic check-and-update, use an appropriate atomic command or a Lua script/concurrency control. Reactor does not combine two Redis commands into one atomic operation.

### 6.3. A sequence of multiple keys and ordering: concatMap

```java
import reactor.core.publisher.Flux;

public Flux<Long> incrementInOrder(Iterable<String> ids) {
    return Flux.fromIterable(ids)
            .concatMap(id ->
                    redis.opsForValue().increment("counter:" + id));
}
```

`concatMap` waits for the previous Publisher to finish before moving to the next element, making execution order predictable. For **independent** operations, consider `flatMap(..., concurrency)` for higher throughput:

```java
public Flux<Long> incrementWithBoundedConcurrency(
        Iterable<String> ids) {
    return Flux.fromIterable(ids)
            .flatMap(
                    id -> redis.opsForValue()
                            .increment("counter:" + id),
                    8
            );
}
```

`flatMap` can execute multiple commands concurrently and emit results out of input order. Pick a concurrency limit suited to Redis load and connection counts rather than leaving it unbounded. Regardless of which operator you choose, if a caller re-subscribes to the entire cold `Flux`, **source operations can also run again**.

### 6.4. zip/when are not Redis transactions

`Mono.zip(a, b)` awaits results from two Publishers. `Mono.when(a, b)` awaits completion of two Publishers without keeping their values. They are useful for independent tasks, yet:

- They do not guarantee two Redis commands form a transaction.
- If one command fails, the other may already have executed or be in flight.
- Operators may cancel uncompleted upstreams on error.
- If one `Mono` source is empty, `zip` has early-termination semantics to watch out for.

For flows that must run **sequentially**, use `then` or `flatMap`; for Redis atomicity requirements, pick a proper data mechanism instead of relying on `zip`.

## 7. Nested Publisher Bug: Mono<Mono<T>>

`map` only transforms **values**; it does not subscribe to a Publisher returned by the lambda:

```java
Mono<Mono<Boolean>> nested =
        redis.opsForValue().get("status:332")
                .map(value ->
                        redis.opsForValue().set("audit:332", value));
```

If the caller only subscribes to `nested`, it receives a `Mono<Boolean>` as its emitted item. The inner `audit` write Publisher still has not run unless something subscribes to it separately.

Fix:

```java
Mono<Boolean> composed =
        redis.opsForValue().get("status:332")
                .flatMap(value ->
                        redis.opsForValue().set("audit:332", value));
```

Rule:

| Operator | Lambda returns | Result |
|---|---|---|
| `map(value -> transform(value))` | A plain value `R` | `Mono<R>` |
| `map(value -> redisCall(value))` | `Mono<R>` | `Mono<Mono<R>>`, execution easily missed |
| `flatMap(value -> redisCall(value))` | `Mono<R>` | `Mono<R>`, integrated into pipeline |
| `flatMapMany(value -> redisFlux(value))` | `Flux<R>` | `Flux<R>` |
| `then(redisCall)` | Next Publisher | Waits for upstream completion then runs next publisher |

A symptom of this bug is seeing logs at the start of a pipeline while secondary Redis keys are never updated. Never fix it by adding `subscribe()` inside the lambda; fix the composition structure instead.

## 8. repeat and retry Cause Redis Commands to Execute Repeatedly

The risk does not only come from writing two `subscribe()` calls. Several Reactor operators **automatically re-subscribe to upstream** under specific conditions.

### 8.1. repeat: re-running after normal completion

```java
Mono<Long> increment =
        redis.opsForValue().increment("counter:332");

Flux<Long> values = increment.repeat(2);
```

When a subscriber consumes `values` and every attempt succeeds, `repeat(2)` performs **two additional repetitions after the initial run**, totaling **three `INCR` executions**. No error occurs, yet the counter increments three times.

```text
subscribe to repeat(2) Flux
    |
    +--> INCR #1 --> complete
    +--> INCR #2 --> complete
    +--> INCR #3 --> complete
```

An unbounded `repeat()` on a fast-completing source can hammer Redis continuously. If polling is desired, add an explicit delay and cap iterations/termination criteria; never use unbounded repeat as an uncontrolled polling loop.

### 8.2. retry: re-running on error

```java
Mono<Long> incrementWithRetry =
        redis.opsForValue().increment("counter:332")
                .retry(2);
```

`retry(2)` allows up to **two retries** beyond the initial attempt—meaning up to **three subscriptions** to upstream.

Suppose Redis already executed `INCR` but the reply was lost to a timeout. The application sees an error and retries, causing another `INCR`. The final counter value can end up larger than the number of business actions the caller thinks happened.

**Retry is not "re-await the reply."** In Reactor semantics, retry re-subscribes to upstream, so the source work re-executes if the Publisher is cold.

### 8.3. retryWhen with exponential backoff

```java
import java.time.Duration;
import reactor.util.retry.Retry;

Mono<String> readWithRetry =
        redis.opsForValue().get("status:332")
                .retryWhen(
                        Retry.backoff(3, Duration.ofMillis(200))
                                .maxBackoff(Duration.ofSeconds(2))
                                .jitter(0.5)
                );
```

`Retry.backoff(3, ...)` allows up to three **retries** after the first call if the source keeps failing. This operator fits pure-read `GET`s or operations verified to be safely retryable, provided errors are transient and load budgets permit.

In real applications, add an error filter:

```java
Mono<String> guardedRead =
        redis.opsForValue().get("status:332")
                .retryWhen(
                        Retry.backoff(3, Duration.ofMillis(200))
                                .filter(this::isTransientConnectionFailure)
                );
```

`isTransientConnectionFailure(Throwable)` is an **application-defined method**, not a built-in Spring API. Never retry serializer mismatches, data type errors, or permanent business errors just because `retryWhen` is convenient.

### 8.4. Table of repeated command execution possibilities

| Construct | How many times can a Redis command be issued? | Caution |
|---|---|---|
| Create `Mono`, no subscriber | 0 | Work is silently dropped |
| One subscriber on cold Mono | Usually 1 | Pipeline must handle errors |
| Two subscribers on same cold Mono | Usually 2 | Writes/decrements/increments run twice |
| `repeat(2)` | Up to 3 times when each completes | Repeats even without errors |
| `retry(2)` | Up to 3 times on continuous errors | Can duplicate side effects |
| `retryWhen(Retry.backoff(3,...))` | Up to 4 times | Filter errors, configure backoff and idempotency |
| `cache()` on cold Mono | Usually shares one subscription and caches result for later subscribers | Caches errors/completions too; alters semantics |
| `share()` on Flux | Can share one upstream across concurrent subscribers | Not durable storage or replay by default |

Counts reflect typical behavior when a source Publisher is successfully subscribed to; they do not guarantee how many commands the Redis server **successfully processed** if network errors or cancellations occur.

## 9. Why Retrying Write Operations Requires Idempotency

Separate two layers:

- **Client side:** failed to receive the `INCR` reply.
- **Redis server reality:** `INCR` may already have run, or may not have run.

```text
Application                Redis
    |                        |
    | INCR payment:counter   |
    |----------------------->| (increments counter)
    |      X connection lost |
    |< - - - - - - - - - - - |
    |                        |
    | retry / resubscribe    |
    | INCR payment:counter   |
    |----------------------->| (increments a second time)
    |<-----------------------| returns result
```

From the client's perspective, a failure on the first attempt is never enough to prove the command did not execute.

### 9.1. Command comparison

| Redis command | Safety when re-sending the same request |
|---|---|
| `GET key` | Read-only; relatively safe to retry, though state may have changed |
| `SET key fixedValue` | Often idempotent if no concurrent writes interleave; watch update order |
| `DEL key` | Often idempotent in final state; return count and concurrent recreation cases can differ |
| `INCR key` | Non-idempotent: each execution increments |
| `LPUSH key value` | Non-idempotent: can append duplicate items |
| `PUBLISH channel value` | Does not guarantee receivers won't get duplicates on publisher retry |
| `XADD stream * ...` | Can append a new record with a new ID on every send |

These notes are guidelines, not a replacement for analyzing concurrent write paths.

### 9.2. A safer approach: request key + atomic processing

If business rules state "award points only once per eventId," you need an identifier mechanism:

```text
eventId = evt-332-abc
counter key = points:{user-7}
dedupe key = processed:{user-7}:evt-332-abc
```

You can write a Lua script (using same-slot keys in Cluster) to:

1. Check whether `eventId` was already applied.
2. If already processed, return "already applied."
3. If not, update the counter and mark the event applied.

This lets a re-sent request be recognized, though the script must still define TTLs, post-write errors, and clear return codes. If side effects span a database or external service outside Redis, coordinate idempotency in the **system owning the side effect** rather than relying solely on a Redis key.

**Do not apply `retryWhen` globally to all write commands**. Choose retry rules per command type and business semantics.

## 10. Using cache, share, and defer for the Right Purpose

Two subscriptions to a cold Mono normally re-run the Redis command. Sometimes you want to share **a single execution's** result across multiple consumers in the same scope:

```java
Mono<String> readOnce =
        redis.opsForValue()
                .get("status:332")
                .cache();
```

`cache()` turns the Mono into a shareable/memoizing source: multiple subscribers can receive the same terminal signal instead of re-reading Redis. However, this is **in-memory Reactor caching inside the Publisher object**, not a Redis key TTL.

### 10.1. Two sides of cache()

```text
Without cache():
  Subscriber A --> Redis GET
  Subscriber B --> Redis GET

With cache():
  Subscriber A --+
                 +--> one source subscription --> Redis GET
  Subscriber B --+           |
                             v
                       shared result
```

However, `cache()` has trade-offs:

- It can retain **stale values** even after the Redis key changes.
- It can cache **errors** and empty completions; later subscribers will not automatically re-trigger GET.
- If attached to a long-lived singleton Publisher with unbounded `cache()`, the value can stay in the JVM for the bean's entire lifetime.
- Unsuitable for "patching" `INCR` or state transitions with side effects unless scope and lifecycle are explicitly defined.

To cache a result in Reactor for a bounded duration:

```java
Mono<String> shortLived =
        redis.opsForValue()
                .get("status:332")
                .cache(Duration.ofSeconds(2));
```

This is an **in-memory Mono TTL**; it does not alter Redis `EXPIRE` or key `TTL`. Across multiple application instances, each instance maintains its own memory.

### 10.2. share() with Flux and hot-source exceptions

With a cold `Flux`, each subscriber normally triggers a new upstream execution. `share()` turns a stream into a **multicast** for concurrent subscribers:

```java
Flux<String> shared =
        Flux.defer(() ->
                    redis.opsForSet().members("active:users"))
                .share();
```

This example only illustrates sharing a finite `Flux`, not a reliable application-wide data cache. Late subscribers can **miss earlier items**, and once all subscribers leave, upstream may be re-subscribed when new subscribers arrive. `share()` does not persist history like a Redis Stream and does not guarantee a Redis query executes only once over the application's lifetime.

### 10.3. defer: recreate logic when subscription begins

`Mono.defer` runs a factory **at subscription time**:

```java
Mono<String> newRequestIdPerSubscription =
        Mono.defer(() -> {
            String requestId = java.util.UUID.randomUUID().toString();
            return redis.opsForValue()
                    .set("request:" + requestId, "CREATED")
                    .thenReturn(requestId);
        });
```

Each new subscription generates a new `requestId`. Contrast this with:

```java
String requestId = java.util.UUID.randomUUID().toString();

Mono<String> sameIdForEverySubscription =
        redis.opsForValue()
                .set("request:" + requestId, "CREATED")
                .thenReturn(requestId);
```

In the second approach, the UUID is generated at **assembly time** and every subscription reuses the same ID. Choose behavior per business semantics: sometimes reusing one `requestId` is the exact goal for idempotent retries, not a bug. `defer` does not make a Redis operation "execute once"; it can make **factory steps re-run** on every subscription.

## 11. subscribe(), block(), and Misleading Behaviors

### 11.1. Zero-argument subscribe()

```java
redis.opsForValue().set("demo:332", "READY").subscribe();
```

The command may start asynchronously, but:

- The caller never receives the confirming `Boolean`.
- Errors may not be observed where business logic needs to react.
- The request or job can finish before the write completes.
- There is no proper management of `Disposable`, timeout, or cancellation.

Even `subscribe(value -> log.info(...))` only adds a value callback; without an error handler and lifecycle ownership, it remains unmanaged fire-and-forget.

### 11.2. block() also creates a subscription

```java
String value =
        redis.opsForValue().get("demo:332").block();
```

`block()` **subscribes and waits** for the result—it does not merely "read a property already inside the Mono." Calling `block()` twice on a cold source can issue two Redis commands.

Never use `block()` on a WebFlux request path or on Netty event-loop/non-blocking threads: it can exhaust threads and Reactor may throw an error. In tests or controlled imperative boundaries, `block()` may be used intentionally, but never mix it into reactive services.

### 11.3. subscribeOn and publishOn do not make logic blocking

`subscribeOn(scheduler)` controls the subscription context and `publishOn(scheduler)` switches the execution context for downstream signals. Neither means "the Redis command runs immediately" nor adds a subscriber on its own.

```java
Mono<String> source =
        redis.opsForValue()
                .get("demo:332")
                .publishOn(reactor.core.scheduler.Schedulers.parallel())
                .map(String::toUpperCase);
```

The chain still requires a subscription to run. With a reactive Redis driver (typically Lettuce/Netty), I/O commands are already non-blocking, so there is usually no reason to wrap every Redis call in `Schedulers.boundedElastic()`. `boundedElastic` fits isolating **blocking** legacy APIs, not general reactive flows.

## 12. Cancellation and Timeout Bugs: "Stop Waiting" Does Not Mean "Undo"

Consider:

```java
Mono<Long> write =
        redis.opsForValue()
                .increment("counter:332")
                .timeout(Duration.ofMillis(150));
```

If a timeout triggers, Reactor cancels the upstream subscription per operator semantics and emits an error downstream. However:

- The Redis command may already have been sent and even executed.
- Canceling the subscription does not guarantee the server can undo the command.
- Retrying after a timeout can increment the counter again.
- Receiving `TimeoutException` on the client is not proof the command never ran.

This is especially dangerous when a controller receives a request whose response is no longer needed (HTTP client closes connection) after side effects were already dispatched to Redis. For critical state-changing operations, design idempotency and outcome verification.

### 12.1. Distinguishing empty, error, and cancel

| Reactor signal | Meaning | Redis example |
|---|---|---|
| `onNext(value)` | Publisher emits a result | `GET` finds a String |
| `onComplete` | Publisher finishes normally | `GET` completes empty when key is absent |
| `onError(error)` | An error was emitted | Connection failure or command error |
| `cancel` | Downstream no longer wants signals | HTTP client disconnects, timeout, or limiting operator |

`Mono.empty()` is **not** a Redis error. When a key does not exist, `GET` normally completes empty. Use `switchIfEmpty` or `defaultIfEmpty` when a fallback is needed:

```java
public Mono<String> getOrDefault(String id) {
    return redis.opsForValue().get("status:" + id)
            .defaultIfEmpty("UNKNOWN");
}
```

Never use `retryWhen` to handle empty results: retries only trigger on `onError`, not when a publisher completes with no elements.

## 13. Side-Effect Operators: doOnNext, doOnSuccess, doFinally

Reactor offers several observation operators:

```java
public Mono<Boolean> saveWithSignals(String key, String value) {
    return redis.opsForValue().set(key, value)
            .doOnSubscribe(s ->
                    log.debug("Subscribed to Redis SET {}", key))
            .doOnNext(result ->
                    log.debug("Redis SET result={}", result))
            .doOnError(error ->
                    log.warn("Redis SET failed for {}", key, error))
            .doFinally(signal ->
                    log.debug("Redis SET terminated with {}", signal));
}
```

This example assumes an SLF4J `log` field is declared in the class. `doFinally` runs when the stream ends via complete, error, or cancel; it is suited for cleanup or recording per-subscription metrics.

Key points to remember:

- `doOnNext` only runs when an element is actually emitted. It does not run for `Mono.empty()`.
- `doOnSuccess` on a Mono runs when the Mono finishes successfully; its argument can be `null` if the Mono completed empty.
- `doOnError` does not swallow or recover from errors; the error continues downstream unless handled by `onErrorResume`/`onErrorReturn` or another operator.
- `doOnSubscribe` and `doFinally` can run **multiple times** when multiple subscriptions or retry/repeat resubscriptions occur.

Never put critical Publisher-returning business actions inside `doOnNext` and discard the returned Publisher. Use `flatMap` or `then` to establish explicit dependencies.

## 14. Logging and Measuring Redis Command Execution Counts

When suspecting repeated command execution, attach a hook near the source:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger subscriptions = new AtomicInteger();

Mono<Long> operation =
        redis.opsForValue()
                .increment("counter:332")
                .doOnSubscribe(s -> {
                    int n = subscriptions.incrementAndGet();
                    System.out.println("Source subscription #" + n);
                });
```

Suppose:

```java
Flux<Long> repeated = operation.repeat(2);
```

When a downstream subscriber consumes `repeated`, the hook near the source runs three times in the normal case. It measures **upstream subscriptions**, not definitive proof that the server successfully executed exactly three Redis commands if network failures occur.

To investigate:

1. Log `requestId`, `eventId`, Redis key, and subscription count.
2. Place `doOnSubscribe` near the source to spot resubscriptions from `retry`/`repeat`.
3. Record exceptions and the operators in use.
4. Compare Redis state against the expected side-effect count.
5. In tests, use dedicated keys and `StepVerifier` to assert the exact result of each subscription.

Never print credentials, tokens, or sensitive payloads in logs. Avoid running `MONITOR` on production Redis to hunt for duplicate commands without accounting for performance cost and data exposure risks; prefer metrics and application logs.

## 15. Testing Subscriptions with Reactor StepVerifier

In controlled tests, `StepVerifier` acts as the **subscriber** for the Publisher under test. Simply constructing a Publisher without calling `verify()` does not trigger the operation.

Example integration test with a test Redis instance:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveRedisSubscriptionTest {

    @Autowired
    ReactiveStringRedisTemplate redis;

    @Test
    void sameColdMonoCanIncrementTwice() {
        String key = "test:332:counter";

        StepVerifier.create(redis.opsForValue().set(key, "0"))
                .expectNext(true)
                .verifyComplete();

        Mono<Long> increment = redis.opsForValue().increment(key);

        // Creating the Mono does not increment the counter yet.
        StepVerifier.create(increment)
                .expectNext(1L)
                .verifyComplete();

        // Subscribing again -> triggers INCR a second time.
        StepVerifier.create(increment)
                .expectNext(2L)
                .verifyComplete();

        StepVerifier.create(redis.opsForValue().get(key))
                .expectNext("2")
                .verifyComplete();
    }
}
```

Test dependencies:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'io.projectreactor:reactor-test'
```

The test uses a test Redis instance and dedicated keys—never run against production data. The `assertThat` import in the sample is optional because assertions happen inside `StepVerifier`; real projects can omit unused imports.

### 15.1. Testing repeat

```java
StepVerifier.create(
        redis.opsForValue()
                .increment("test:332:counter")
                .repeat(2)
)
    .expectNext(3L, 4L, 5L)
    .verifyComplete();
```

This continues from the previous test where the counter stood at `2`. One subscription to `repeat(2)` executes the source three times, bringing the value to `5`. Do not use `StepVerifier` to mask unsafe retries: test commands must have clear effects on isolated data.

### 15.2. Detecting a discarded Publisher

```java
Mono<Boolean> write =
        redis.opsForValue().set("test:332:not-subscribed", "YES");

// write has not been subscribed to yet, so this is only assembly.
StepVerifier.create(redis.opsForValue().get("test:332:not-subscribed"))
        .verifyComplete();

StepVerifier.create(write)
        .expectNext(true)
        .verifyComplete();

StepVerifier.create(redis.opsForValue().get("test:332:not-subscribed"))
        .expectNext("YES")
        .verifyComplete();
```

Ensure the key does not already exist before the test, e.g., delete it explicitly in setup. Otherwise, the initial `get` could emit a leftover value from a previous run, breaking test isolation.

## 16. Important Exception: Redis Pub/Sub Returns a Hot Flux

So far, this lesson has focused on **Redis data commands** using the cold Publisher model. However, not every `Flux` is cold. Redis Pub/Sub is an important distinction.

A Redis Pub/Sub listener stream is a **live stream of events over time**, where messages from publishers are not retained to replay for new subscribers. Spring Data Redis describes reactive message streams as **hot sequences**: events may arrive even when the application subscriber is not ready to consume them.

Example:

```java
Flux<?> messages =
        reactiveRedisTemplate.listenToChannel("app:updates");
```

This stream does not share the same semantics as `redis.opsForValue().get(key)`:

- `GET` is a finite operation; a second cold subscription usually re-reads Redis.
- Pub/Sub is a live event stream; late subscribers are not replayed past events by Redis.
- Listening holds dedicated connection/subscription resources requiring lifecycle management.
- When multiple application consumers need to share one subscription, design stream sharing and backpressure explicitly rather than assuming each `subscribe` behaves like an independent `GET`.

Spring Data Redis provides `ReactiveRedisMessageListenerContainer` to manage registrations, message delivery, and resources. In applications listening to multiple channels, use the container rather than spawning ad-hoc `listenToChannel` calls.

### 16.1. Clarify what "subscribe" refers to

Two different concepts share the word subscribe:

| Term | Meaning |
|---|---|
| `Mono/Flux.subscribe()` | Registering a **Reactive Streams subscriber**, activating/receiving signals from a Publisher |
| Redis `SUBSCRIBE channel` | Subscribing to a **Redis Pub/Sub channel** on a Redis connection |

An application may use a Reactor subscription to start a Redis Pub/Sub flow, yet they are two distinct API layers. The guideline "avoid manual `subscribe()` in services" **does not mean applications can never listen to Redis Pub/Sub**.

### 16.2. When manual subscribe is allowed: lifecycle-owned boundaries

For HTTP requests, WebFlux manages subscriptions. However, a background component running from application startup—such as a Pub/Sub consumer or scheduled processor—needs a **subscription owner** and cleanup on shutdown.

Conceptual example:

```java
import jakarta.annotation.PreDestroy;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Component;
import reactor.core.Disposable;

@Component
public class UpdateSubscriptionLifecycle {

    private final ReactiveStringRedisTemplate redis;
    private Disposable subscription;

    public UpdateSubscriptionLifecycle(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    @EventListener(ApplicationReadyEvent.class)
    public synchronized void start() {
        if (subscription != null && !subscription.isDisposed()) {
            return;
        }

        subscription = redis.listenToChannel("app:updates")
                .subscribe(
                        msg -> handleUpdate(msg.getMessage()),
                        error -> reportListenerFailure(error)
                );
    }

    @PreDestroy
    public synchronized void stop() {
        if (subscription != null) {
            subscription.dispose();
            subscription = null;
        }
    }

    private void handleUpdate(String payload) {
        // Illustrative only: do not use this callback for blocking I/O.
    }

    private void reportListenerFailure(Throwable error) {
        // Log and trigger real recovery policy.
    }
}
```

This example uses `subscribe` **at the top-level application boundary**, not hidden inside a service called by WebFlux. It tracks `Disposable`, handles errors, and cleans up resources on shutdown. Production deployments also need reconnect/resubscribe strategies, readiness verification, throughput control, and handler error handling. Pub/Sub is **at-most-once**, so reconnecting does not replay lost messages.

If `handleUpdate` must call another reactive API, do not casually trigger nested `subscribe()` calls inside the callback. Chain the processing using `concatMap` or `flatMap(..., concurrency)` with explicit error handling and lifecycle management.

## 17. When Is Manual Subscribe Actually Needed?

"Do not subscribe manually" is an **architectural guideline**, not an absolute ban.

| Location | Who should own the subscription? | Recommendation |
|---|---|---|
| WebFlux controller returning `Mono`/`Flux` | Spring WebFlux | **Return the Publisher**, never call `subscribe()` |
| Service called by controller | Caller/downstream | **Compose and return** |
| Reactive repository or Redis adapter | Downstream | Return Mono/Flux describing the operation |
| Reactor test | `StepVerifier` | `verify()` is the intentional subscription point |
| Reactive application runner / background processor | Lifecycle-managing component | Can subscribe once, store `Disposable`, handle errors |
| Long-lived Pub/Sub listener | Container or lifecycle component | Configure subscription/recovery management |
| Imperative code needing to wait for result | Explicit integration boundary | `block()` can be used carefully, outside the WebFlux event loop |

For scheduled jobs, avoid calling `subscribe()` on every timer tick if the previous run might still be executing. You may need a queue, `concatMap`, running-state guards, concurrency limits, or a pipeline-wide scheduler to keep runs from overlapping.

## 18. Common Mistakes and Fixes

| Symptom | Possible cause | Resolution |
|---|---|---|
| `SET` called in code but key missing | Publisher created and discarded without subscription | Return/compose the Mono into caller's flow |
| `INCR` increments twice per HTTP request | Service called `subscribe()` and WebFlux subscribed again | Remove manual subscribe; use `doOnNext` for logging |
| Redis receives command multiple times for one HTTP request | `retry`/`repeat` or multiple downstream subscriptions | Place `doOnSubscribe` near source, inspect operator chain |
| `doOnNext` runs but audit key is never written | Lambda created a `Mono` and discarded it | Use `flatMap` or `then` |
| Code produces `Mono<Mono<Boolean>>` | Used `map` instead of `flatMap` | Flatten the Publisher with `flatMap` |
| HTTP returns OK before Redis writes | Fire-and-forget `subscribe()` in controller | Return the write Mono; use `thenReturn` |
| Retry causes duplicate decrements/increments | Redis ran command but client lost reply | Design idempotency; do not blindly retry writes |
| `GET` misses key yet skips `onErrorResume` | Source completed empty, not with an error | Use `defaultIfEmpty`/`switchIfEmpty` |
| `block()` fails on event loop | Blocking inside a non-blocking thread | Return Mono/Flux, remove `block()` from WebFlux |
| `cache()` returns stale data after Redis changes | Cached inside Mono without invalidation | Define cache scope/TTL, or read Redis every time |
| `share()` causes late subscribers to miss elements | Hot multicast does not replay history | Choose replay/cache if actually needed; size memory/lifecycle |
| Pub/Sub listener misses events | Hot stream, subscriber offline or not ready | Manage readiness/recovery; use Streams if replay is needed |
| Job spawns hundreds of concurrent subscriptions | Each loop calls `subscribe()`, no concurrency cap | Compose one pipeline and cap in-flight commands |
| Errors silently vanish | `subscribe()` lacks an error handler | Keep errors in pipeline and handle at owning boundary |

## 19. Self-Study Exercises

### Exercise 1 — Not subscribed, not written

1. Delete the key `lab:332:state` in test Redis.
2. Create `Mono<Boolean> write = redis.opsForValue().set("lab:332:state", "READY")` without subscribing.
3. Check the key via Redis CLI `GET lab:332:state`; it still does not exist.
4. Run `StepVerifier.create(write).expectNext(true).verifyComplete()`.
5. Re-check in Redis CLI; the key now holds `READY`.

### Exercise 2 — Two subscriptions, two increments

1. `SET lab:332:counter 0`.
2. Create one `Mono<Long>` from `increment("lab:332:counter")`.
3. Subscribe twice using `StepVerifier` or a test with managed subscriptions.
4. Verify the final counter is `2`.
5. Note why having a single Java `Mono` instance does not mean only one Redis command is sent.

### Exercise 3 — Forgotten command inside callback

1. Read `lab:332:state`.
2. Inside `doOnNext`, call `redis.opsForValue().set("lab:332:audit", value)` and discard the Publisher.
3. Run the read flow with `StepVerifier`.
4. Observe that the audit key is never created.
5. Replace with `flatMap(value -> redis.opsForValue().set(...).thenReturn(value))` and re-test.

### Exercise 4 — Retry and repeat

1. Initialize a counter key to `0`.
2. Subscribe once to `increment(...).repeat(2)` and confirm the counter reaches `3`.
3. Explain why the execution count is 3, not 2.
4. For `retry(2)`, build a test source that simulates failures to observe resubscription count; never disrupt production Redis networking.
5. Propose safe policies for a `GET` and an `INCR` after a timeout.

### Exercise 5 — Properly architected WebFlux controller

1. Build a POST endpoint returning `Mono<Long>` from `increment(...)`.
2. Add `doOnNext` to log the value.
3. Do not call `subscribe()` in the controller or service.
4. Send one HTTP request and verify the Redis counter increments once without retries.
5. Temporarily add `subscribe()` inside the service in a test environment to observe the double-increment bug, then remove it.

### Exercise 6 — Comparing Pub/Sub with Redis GET

1. Create a `Mono<String>` for `GET` and compare its effect when subscribed twice.
2. Create a listener stream on `app:updates` via a reactive listener.
3. Publish messages before and after the listener becomes ready.
4. Observe that messages sent prior to subscription are not replayed.
5. Explain why hot Pub/Sub cannot substitute for a Redis Stream with history and ACKs.

## 20. Key Principles to Remember

1. **A Publisher is a description**, not a Redis command result. For ordinary reactive Redis commands, execution triggers upon subscription.
2. **Every subscription to a cold source can re-run the Redis command.** Be especially careful with `INCR`, `LPUSH`, `XADD`, `PUBLISH`, and non-idempotent side effects.
3. **retry/repeat mean resubscription.** `repeat(2)` normally creates three executions when the source completes; `retry(2)` can create three attempts on persistent errors.
4. **Compose—do not fire-and-forget.** Use `flatMap`, `then`, `concatMap`, and return Publishers to WebFlux; avoid hidden `subscribe()` calls in services.
5. **Cancellation and timeouts do not undo Redis.** A command may already have run even when the client sees an error; design retries and idempotency around business semantics.
6. **cache/share/defer change repetition and sharing scope.** Use them intentionally, not as universal fixes for duplicate bugs.
7. **Pub/Sub is a distinct hot-stream case.** Subscribing to a message stream requires lifetime/readiness management, unlike subscribing to a `GET` Mono.
8. **Manual subscribe belongs only at clearly owned boundaries**, such as lifecycle-managed background listeners with a `Disposable`; for HTTP requests, let the framework subscribe.

## References

- [Spring Data Redis — Reactive Redis Support](https://docs.spring.io/spring-data/redis/reference/redis/redis-reactive.html): `ReactiveRedisTemplate` and the non-blocking Redis operations model.
- [Spring Data Redis API — ReactiveRedisTemplate](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/ReactiveRedisTemplate.html): `Mono`/`Flux` and reactive Redis methods.
- [Spring Data Redis — Reactive Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub-receiving.html): `ReactiveRedisMessageListenerContainer`, `listenToChannel`, and subscription management.
- [Project Reactor — Introduction to Reactive Programming](https://projectreactor.io/docs/core/release/reference/coreFeatures.html): cold/hot publishers, assembly, and subscription.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `retry`, `retryWhen`, `onErrorResume`, and error-handling patterns.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `subscribeOn`, `publishOn`, and blocking vs. non-blocking execution.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` as a controlled subscriber.
- [Spring Framework — WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): controllers returning reactive types handled by WebFlux.
- [Redis — INCR](https://redis.io/docs/latest/commands/incr/): increment command with side effects when executed repeatedly.
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): message delivery characteristics and lack of default replay.
