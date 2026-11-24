# map, flatMap, Combining Results, and Choosing Concurrency in Spring WebFlux

> **Scope:** Reactor Core (`Mono`, `Flux`, Reactive Streams), Spring WebFlux on Spring Framework 6.2.x / Spring Boot 3.5.x with Java 17+. Core focus: **transforming data with `map`/`flatMap`**, **combining multiple publishers with `zip`/`merge`/`concat`/`combineLatest`**, and **choosing appropriate concurrency/prefetch/backpressure/order** when calling WebClient or reactive repositories. Examples run on a WebFlux server without blocking the HTTP event loop, using cURL and WebTestClient/StepVerifier. If using Spring Boot 4.x/Spring Framework 7.x, cross-check the corresponding starter/test packages before copying dependencies.

## 1. Real-World Scenario and Diagram

A system receives a list of product IDs, needs to call a catalog service, and returns JSON. When loading an aggregated profile, it needs to combine account and settings from two independent services.

```text
GET /api/items
    |
Flux<Integer> ids
    |
    + map(id -> key): value -> immediate new value
    |
    + flatMap(id -> Mono<Item>, concurrency):
    |                 |
    |           multiple in-flight I/O calls
    |                 |
    |         Flux<Item> (may reorder)
    |
    + flatMapSequential(id -> Mono<Item>, n):
    |                 |
    |         Flux<Item> preserving input order
    |
    + concatMap(id -> Mono<Item>):
                      |
             each inner runs sequentially

GET /api/profile/{id}
    |
    +--> Mono<Account> -------+
    |                         +--> Mono.zip(...) --> Mono<Profile>
    +--> Mono<Settings> ------+
```

**Questions to answer before picking an operator:** does the mapper return a plain value or a Publisher? Are the calls independent or dependent? Must **output** order be preserved, or also **side-effect** order? How many concurrent requests can downstream handle? Can an item be dropped or is every item mandatory?

## 2. Foundations: Mono, Flux, and Signals

`Mono<T>` emits 0 or 1 element and completes, or terminates with an error. `Flux<T>` emits 0 to N elements (potentially infinite), completes, or errors. A reactive pipeline is typically **lazy**; operators like `map` and `flatMap` build a computation description without executing until subscribed. Spring WebFlux subscribes to the Publisher returned by a controller during the response lifecycle.

Reactive Streams has these signals/concepts:
- `onSubscribe`: hands over the Subscription;
- `request(n)`: consumer requests element count;
- `onNext`: one element, never null;
- `onComplete`: successful completion;
- `onError`: terminal error;
- `cancel`: cancels the subscription.

After terminal `onComplete` or `onError`, a publisher stops emitting normal elements. Cancellation from a browser/disconnected client can propagate upstream, depending on operators/sources/HTTP connectors.

```java
Flux<Integer> source = Flux.just(1, 2, 3);
Flux<Integer> output = source.map(x -> x * 10);
// Not subscribed yet: tasks normally have not run.
```

In a WebFlux HTTP controller: **return `Flux` or `Mono`** so Spring orchestrates the subscription; never call `.subscribe()` in the handler and return `null`. In unit tests, use `StepVerifier.create(output)` to assert signals without calling `block()`.

### 2.1. Cold vs. Hot Sources

`Flux.range(...)` and `Mono.defer(...)` are typically cold: each subscription can replay or re-execute the logic. A hot stream can share an already-running event source. Concurrency on `flatMap` caps **inner subscriptions of that operator instance**, without automatically throttling a shared hot source's overall event rate, a service's connection pool, or total inbound HTTP requests.

## 3. map: One Input Element to One Value

`map(Function<T,R>)` performs a **synchronous** transformation whenever an `onNext` arrives:

```java
Flux<String> labels = Flux.just(1, 2, 3)
        .map(id -> "item-" + (id * 10));
```

The value of `labels.collectList()` when subscribed is equivalent to:

```text
[item-10, item-20, item-30]
```

`map` suits DTO mapping, string normalization, and pure value calculations. It does not spawn threads or turn blocking logic into non-blocking I/O. The mapper must never return `null`; returning null violates the reactive contract.

**Mistake when the mapper returns a Mono:**

```java
Mono<Mono<User>> nested =
        Mono.just(42).map(id -> fetchUserReactive(id));
```

If `fetchUserReactive(int)` returns `Mono<User>`, the outer result is a Mono wrapping a Mono. To get `Mono<User>`, use `flatMap`:

```java
Mono<User> flattened =
        Mono.just(42).flatMap(id -> fetchUserReactive(id));
```

Both snippets require `fetchUserReactive` and class `User` to be defined beforehand.

## 4. flatMap: Create a New Publisher and Flatten

`Mono.flatMap(Function<T,Mono<R>>)` fits a single request needing an asynchronous result from one value. `Flux.flatMap(Function<T,Publisher<R>>)` fits multiple items, capable of keeping multiple inner publishers active.

```java
Mono<User> user = userIdMono
        .flatMap(id -> userRepository.findById(id));

Flux<Product> products = Flux.fromIterable(productIds)
        .flatMap(id -> webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class), 4);
```

Snippets assume `userIdMono`, `userRepository`, `productIds`, `webClient`, and DTOs exist. Advantage: multiple non-blocking network calls can **overlap latency**; drawback: **output order is not guaranteed to match the IDs**.

### 4.1. flatMap Does Not Automatically Create Threads

Example:

```java
Flux<Integer> a = Flux.range(1, 4)
        .flatMap(i -> Mono.just(i * 10));

Flux<Integer> b = Flux.range(1, 4)
        .flatMap(i -> Mono.delay(Duration.ofMillis(100))
                .map(ignore -> i * 10), 2);
```

Example A runs largely synchronously on the subscription; B uses an async timer. `flatMap` is a **flatten/merge** operator, not a `new Thread(...)` instruction.

With a blocking JDBC source:

```java
// Anti-pattern on the WebFlux event loop.
return Flux.fromIterable(ids)
        .flatMap(id -> Mono.fromCallable(
                () -> jdbcRepository.findById(id)));
```

Subscribing to a blocking Callable on the current thread can still block the event loop. Temporary bridge:

```java
return Flux.fromIterable(ids)
        .flatMap(id -> Mono.fromCallable(
                        () -> jdbcRepository.findById(id))
                .subscribeOn(Schedulers.boundedElastic()), 4);
```

The second snippet offloads blocking calls to `boundedElastic`, yet **does not turn JDBC into a reactive database driver**. You still must bound tasks, threads/queues, and DB pools, and consider Spring MVC or R2DBC depending on architecture.

### 4.2. flatMapMany for a Mono Input

When fetching multiple orders from a single account:

```java
Flux<Order> orders = accountMono
        .flatMapMany(account -> orderRepository.findByAccount(account.id()));
```

Here the repository returns `Flux<Order>`; `Mono.flatMapMany` transitions from 0..1 to 0..N. Using `map(account -> Flux<Order>)` would yield `Mono<Flux<Order>>` instead of a sequence of orders.

### 4.3. How flatMap Differs from map When Empty

With `Mono.empty()`, there is no `onNext` to invoke either `map` or `flatMap` mappers. To handle absence intentionally, use `switchIfEmpty(...)` or `defaultIfEmpty(...)` for valid default values rather than assuming “the mapper failed”.

## 5. flatMap, flatMapSequential, concatMap: Choosing by Ordering

```java
Flux<Item> fastest = ids.flatMap(this::fetch, 3);
Flux<Item> ordered = ids.flatMapSequential(this::fetch, 3);
Flux<Item> serial = ids.concatMap(this::fetch);
```

| Criterion | flatMap(mapper,3) | flatMapSequential(mapper,3) | concatMap(mapper) |
| --- | --- | --- | --- |
| Can subscribe multiple inners early | Yes | Yes | No, inners run one after another |
| Max active inners in example | 3 | 3 | 1 |
| Output matches input order | Not guaranteed | **Yes** | **Yes** |
| Interleaves values across inners | Yes | Not in output per source order | No |
| Buffers when later result arrives first | No source-order reordering needed | May queue waiting on earlier inner | No async inner overlap |
| When to use | Independent I/O, prioritize throughput | Preserve output order while overlapping I/O | Side effects must run sequentially |

**Easy trap:** `flatMapSequential` guarantees **output emission order**, while inner operations/side effects can still execute **concurrently**. If write A must complete before write B starts on the same aggregate, use `concatMap` or appropriate reactive sequencing; DB transactions/versioning are still required to protect against races across **different HTTP requests**.

### 5.1. Head-of-Line Example

Input IDs [1,2,3], inner ID=1 takes 300ms, ID=2 80ms, ID=3 40ms:
- `flatMap` may emit 3, 2, 1.
- `flatMapSequential` may finish 3 and 2 early, yet **buffers them in a queue** and emits 1, 2, 3.
- `concatMap` waits for 1 to finish before subscribing to 2, then 3.

Exact timing and interleaving depend on schedulers and sources. Tests must not assert a fixed order for `flatMap`. With `flatMapSequential` under high concurrency and large items, the reorder queue increases memory usage and time-to-first-byte when the first inner is slow.

### 5.2. Why Not Sort After flatMap?

`flatMap(...).sort(comparator)` or `collectList().map(list -> sort(...))` must collect all items until the source completes, making it unsuitable for infinite streams and growing memory with data size. `flatMapSequential` uses source-order semantics without sorting the entire stream, though it still buffers early-finishing inners.

### 5.3. Does map Preserve Order?

`Flux.map` transforms `onNext` signals in the order emitted by upstream without reordering. If upstream was already reordered by an earlier `flatMap`, `map` **does not restore** the original order.

## 6. concurrency: Active Inner Subscriptions, Not Thread Count

`Flux.flatMap(mapper, concurrency)` caps the number of active inner publishers in that pipeline. It does not spawn threads itself, does not limit all callers across the server, and is not equivalent to the HTTP connection pool max size.

Example:

```java
Flux<Product> result = Flux.fromIterable(ids)
        .flatMap(id -> client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class), 8);
```

When each inner is a WebClient `Mono<Product>`, at most roughly 8 HTTP exchanges are in flight per subscription from that operator, depending on connector/pooling/response/retries. Yet 100 concurrent HTTP requests, each with `flatMap` concurrency 8, can spawn **up to roughly 800 active inner operations** (an intuitive upper bound, not guaranteed 800 connections).

**Two layers of limits are required:**
- local per-pipeline concurrency (`flatMap` argument);
- global controls (client pools/bulkheads/rate limits, per-tenant quotas, ingress concurrency, downstream capacity).

### 6.1. How to Choose Concurrency

There is no single magic number for all workloads. For a request fanning out 30 IDs, evaluate:
- average/p95/p99 latency per remote call;
- downstream RPS/concurrent request quotas;
- HTTP client max connections/pending acquires;
- memory per in-flight request, payload sizes, JSON decoding;
- retries/429/503/timeouts and DB/CPU saturation;
- count of simultaneously active inbound requests.

Start small (e.g., 2–8 **purely as an experimental starting point**, not a universal rule) and increase under load testing while monitoring throughput, tail latency, memory, and error rates. Once downstream or a pool is saturated, raising concurrency usually only increases queues, timeouts, and retry storms.

### 6.2. prefetch vs. concurrency

Another overload:

```java
Flux<R> output = source.flatMap(
        value -> mapperReturningFlux(value),
        4,   // number of active inner publishers
        16   // prefetch: request-ahead count per inner
);
```

This snippet is not standalone; `source` and `mapperReturningFlux` are illustrative placeholders. `prefetch` tunes demand/queueing; it **does not** allocate 16 threads, and does not mean exactly 16 items always sit in RAM.

Rough pressure estimate for multi-value inner streams: `concurrency × prefetch × average item size`. This is only an approximation, excluding outer buffers, HTTP response encoders, Reactor/Netty buffers, object overhead, and caches. When inners emit at most one value like Mono, prefetch matters less than when each inner is a long Flux.

### 6.3. Protecting Against Infinite Streams and Hanging Inners

If an inner never completes and concurrency slots fill up, subsequent input items may stall. Use `timeout(Duration)`, client timeouts, and circuit breakers/bulkheads where appropriate; for infinite/hot publishers, mind cancellation/buffering semantics instead of casually writing `flatMap(concurrency=1000)`.

## 7. Combining Independent Results with Mono.zip

A profile endpoint needing account and settings:

```java
Mono<Account> account = accountService.find(id);
Mono<Settings> settings = settingsService.find(id);

Mono<Profile> profile = Mono.zip(
        account, settings,
        (a, s) -> new Profile(a.id(), a.name(), s.theme()));
```

`Mono.zip` emits a result only when **every source produces a value**. If both sources are asynchronous and independent, their latencies can overlap. If one source errors, zip typically propagates the error and cancels the remaining running sources. If one source completes empty, zip cannot invoke the combinator.

**Do not misunderstand:** zipping two remote calls does not create a distributed transaction, does not guarantee snapshot consistency across two databases, and does not prove the user is authorized to read the results. Authorization on each source/data scope must still be enforced.

### 7.1. zipWith and Tuples

```java
Mono<Tuple2<Account, Settings>> pair = accountMono.zipWith(settingsMono);

Mono<Profile> combined = accountMono.zipWith(
        settingsMono,
        (a, s) -> new Profile(a.id(), a.name(), s.theme()));
```

These are snippets requiring `import reactor.util.function.Tuple2` and DTOs. Use `zipWith` when one Mono is already the left-hand side; empty/error semantics match `zip`.

### 7.2. zipWhen for Dependent Requests

```java
Mono<Profile> profile = accountService.find(id)
        .zipWhen(account ->
                settingsService.findByAccount(account.id()))
        .map(pair -> new Profile(
                pair.getT1().id(),
                pair.getT1().name(),
                pair.getT2().theme()));
```

`zipWhen` builds the right-hand Publisher **after the account value arrives**, so it is not equivalent to “two independent sources starting simultaneously”. For a simple dependency chain, you can also use:

```java
Mono<Profile> profile = accountService.find(id)
        .flatMap(account -> settingsService.findByAccount(account.id())
                .map(settings -> new Profile(
                        account.id(), account.name(), settings.theme())));
```

When a tuple is unnecessary, nested `flatMap`/`map` is often clearer.

### 7.3. Zip with Mono.empty or Mono<Void>

```java
Mono<User> user = userRepository.findById(id);
Mono<Settings> absent = Mono.empty();

Mono<Tuple2<User, Settings>> zipped = Mono.zip(user, absent);
```

`zipped` typically completes empty without emitting a tuple. `Mono<Void>` also has “no onNext” for zip; never write `Mono.zip(writeAuditReturningVoid, getUser)` expecting a pair. When **awaiting completion of operations with no return values**, use `Mono.when(publisherA, publisherB)` or `then(...)` sequencing per error/transaction needs.

If missing user means 404:

```java
Mono<User> user = userRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "User not found")));
```

If settings are optional and a default is valid:

```java
Mono<Settings> settings = settingsService.find(id)
        .defaultIfEmpty(new Settings("light"));
```

Never assign a permissive default expanding access when a permission service is empty/errored. The Reactor FAQ also warns that with zip and empty sources, some sources might **not even be subscribed** in specific cases; never tie mandatory side effects to an assumption that “zip subscribes to everything” without protocol guarantees.

## 8. Flux.zip, merge, concat, and combineLatest

### 8.1. Flux.zip: Pairing by Index

```java
Flux<String> zipped = Flux.zip(
        Flux.just("A", "B", "C"),
        Flux.just(1, 2),
        (letter, number) -> letter + number);
```

Output when subscribed:

```text
A1
B2
```

For two finite Fluxes, zip pairs 1:1 positionally and terminates once no more pairs can be formed because one source completed. `C` has no number to pair with, so it never appears. If one source emits faster, zip may queue/buffer while waiting for the other.

### 8.2. Flux.merge: Interleaving by Emission Time

```java
Flux<String> first = Flux.just("A1", "A2")
        .delayElements(Duration.ofMillis(100));
Flux<String> second = Flux.just("B1", "B2")
        .delayElements(Duration.ofMillis(60));
Flux<String> merged = Flux.merge(first, second);
```

Both sources are subscribed eagerly; output can interleave. An example order like `B1,A1,B2,A2` is just **one possibility**. Never assert a single hardcoded order on async sources with uncontrolled timing.

Use `merge` for independent event streams when cross-source ordering does not matter, such as unifying notification topics.

### 8.3. Flux.concat: Source A Then Source B

```java
Flux<String> out = Flux.concat(
        Flux.just("A1", "A2"),
        Flux.just("B1", "B2"));
```

Deterministic output:

```text
A1
A2
B1
B2
```

`concat` waits for A to complete before subscribing to B. If A is **infinite**, B is never subscribed under standard `concat`.

### 8.4. mergeSequential: Subscribe Eagerly While Preserving Source Order

`Flux.mergeSequential(...)` subscribes to multiple sources eagerly and emits in source order; suited when you want async work to overlap while keeping group A before group B. Like `flatMapSequential`, it queues outputs from B while A is slow. It does **not** guarantee that A and B's side effects happen sequentially.

### 8.5. combineLatest: Latest State

```java
Flux<String> dashboard = Flux.combineLatest(
        temperatureFlux,
        humidityFlux,
        (temperature, humidity) ->
                "temperature=" + temperature + ",humidity=" + humidity);
```

Once every source has emitted at least one value, `combineLatest` emits a combined latest value whenever any source updates. Suited for dashboards/sensor states, not index-based pairing. Values may come from different points in time, providing no DB transaction-consistent snapshot. If any source has never emitted, there are not yet enough “latest values” to combine.

### 8.6. Decision Table

| Goal | Operator |
| --- | --- |
| Combine two independent Monos, requiring both values | `Mono.zip` |
| Next source needs the previous source's output | `flatMap` / `zipWhen` |
| Pair elements by index | `Flux.zip` |
| Interleave events across sources as they arrive | `merge` |
| Emit all of A then B | `concat` |
| Subscribe eagerly while preserving output by source | `mergeSequential` |
| Combine the latest value from each stream | `combineLatest` |
| Fan-out many inner publishers, throughput priority | `flatMap(fn,n)` |
| Fan-out while preserving output order | `flatMapSequential(fn,n)` |
| Process inners sequentially with execution order | `concatMap(fn)` |

## 9. Error Handling When Composing

### 9.1. flatMap Is Fail-Fast by Default

```java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(id -> fetchProduct(id), 4);
```

If one inner emits `onError`, composition typically emits a terminal error and cancels remaining inners. If the API requires **all products**, this can be the right choice.

If a 404 error may be skipped:

```java
Flux<Product> bestEffort = Flux.fromIterable(ids)
        .flatMap(id -> fetchProduct(id)
                .onErrorResume(ProductNotFoundException.class,
                        ex -> Mono.empty()), 4);
```

Fragment: `ProductNotFoundException` must be defined. Never use an empty fallback for all exceptions if the app needs visibility into 500s/timeouts. To report partial failures, return a per-item DTO with success/error rather than silently dropping items.

### 9.2. Partial Result DTO

```java
record ItemResult(int id, String value, String error) {}

Flux<ItemResult> result = Flux.fromIterable(ids)
        .flatMap(id -> fetchProduct(id)
                .map(p -> new ItemResult(id, p.name(), null))
                .onErrorResume(ex -> Mono.just(
                        new ItemResult(id, null, "remote_failed"))), 4);
```

Snippet; `ids`, `fetchProduct`, and `Product` must exist. Never forward raw exception messages containing credentials/IPs/SQL to clients. If order must be preserved, use `flatMapSequential`; HTTP status choice for partial success belongs to the API contract.

### 9.3. Empty and Errors in zip

If one source is empty, `zip` can complete empty. If one source errors, `zip` typically fails fast and cancels remaining sources. For a failing permission service, **never** default to `onErrorReturn(new Permissions("ADMIN"))`; fail closed so privileges are never escalated.

### 9.4. Retry + Timeout Without Creating a Retry Storm

```java
Mono<Product> call = fetchProduct(id)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .filter(ex -> ex instanceof TransientFailure));
```

Snippet needs `import reactor.util.retry.Retry` and class `TransientFailure`. Here `retryWhen` allows up to 2 additional retries per filter; backoff and deadlines must still align with SLOs and per-request budgets. With 100 inbound calls × 5 fan-out × 3 attempts, load multiplies sharply when dependencies fail. Never blindly retry 4xx/permission errors or side-effecting POSTs.

### 9.5. flatMapDelayError

`flatMapDelayError(mapper, concurrency, prefetch)` defers errors until eligible active/queued work finishes. It **does not turn errors into partial success**: a terminal error is still emitted at the end. When item-wise reporting is desired, a per-inner error DTO is usually clearer.

### 9.6. onErrorContinue Is a Sensitive Choice

`onErrorContinue` has operator-dependent semantics and can cause surprising behavior upstream. Avoid using it by default to “skip any bad item”; prefer `onErrorResume` placed **inside the mapper** with explicit contracts and metrics.

## 10. Schedulers and Avoiding Blocking the Event Loop

`flatMap` does not create threads on its own. Reactor offers:
- `subscribeOn(scheduler)`: affects where subscription/source and upstream run.
- `publishOn(scheduler)`: shifts execution context of subsequent operators.
- `Schedulers.boundedElastic()`: suited for bridging bounded legacy blocking tasks.
- `Schedulers.parallel()`: suited for bounded CPU work; never use for blocking JDBC.

```java
Mono<LegacyRecord> record = Mono.fromCallable(
                () -> jdbcService.findRecord(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Does not make JDBC non-blocking; you must bound pools/queues and consider Spring MVC for predominantly blocking architectures.

**Anti-pattern in a WebFlux controller:**

```java
@GetMapping("/bad")
Product bad() {
    return webClient.get().uri("/products/1").retrieve()
            .bodyToMono(Product.class).block();
}
```

Terminal `block` can stall or be forbidden on Reactor non-blocking event loops. The controller should instead:

```java
@GetMapping("/good")
Mono<Product> good() {
    return webClient.get().uri("/products/1").retrieve()
            .bodyToMono(Product.class);
}
```

Both snippets assume `webClient`, `Product`, and `@RestController`; in real apps return the Publisher to Spring WebFlux so the framework subscribes and manages the response. Never spawn a detached `subscribe()` inside a handler.

## 11. Runnable Demo: Spring Boot 3.5 + Java 17

The example uses `Mono.delay` to simulate async I/O, without a database or external service. Endpoints:
- `GET /api/demo/map`: deterministic map;
- `GET /api/demo/flat?concurrency=2`: `flatMap` may reorder;
- `GET /api/demo/ordered`: `flatMapSequential` keeps ID order;
- `GET /api/demo/serial`: sequential `concatMap`;
- `GET /api/demo/profile/{id}`: `zip` independent account and settings;
- `GET /api/demo/zip`, `/concat`, `/merge`: combining semantics.

### 11.1. POM Fragment

Generate a project at [Spring Initializr](https://start.spring.io/) with Maven/Java 17/Spring Boot 3.5.x, selecting **Spring Reactive Web (WebFlux)**. Main dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

This is a POM fragment generated by Initializr, not the entire POM. To keep the server reactive, do not add `spring-boot-starter-web` to this demo; when both are present in Boot 3.x, Servlet MVC is normally prioritized.

### 11.2. Complete Java Code

Put the entire contents in `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record ItemView(int id, String label) {}
record AccountView(int id, String name) {}
record SettingsView(String theme) {}
record ProfileView(int id, String name, String theme) {}

@Service
class AsyncDemoService {

    // For IDs 1..4, delays are 320, 240, 160, 80 ms respectively.
    Mono<ItemView> loadItem(int id) {
        long millis = 80L * (5 - id);
        return Mono.delay(Duration.ofMillis(millis))
                .map(tick -> new ItemView(id, "item-" + id));
    }

    Mono<AccountView> loadAccount(int id) {
        return Mono.delay(Duration.ofMillis(100))
                .map(tick -> new AccountView(id, "user-" + id));
    }

    Mono<SettingsView> loadSettings(int id) {
        return Mono.delay(Duration.ofMillis(70))
                .map(tick -> new SettingsView("dark"));
    }
}

@RestController
@RequestMapping("/api/demo")
class DemoController {

    private final AsyncDemoService service;

    DemoController(AsyncDemoService service) {
        this.service = service;
    }

    @GetMapping("/map")
    Flux<Integer> mapped() {
        return Flux.range(1, 4).map(i -> i * 10);
    }

    @GetMapping("/flat")
    Flux<ItemView> flattened(
            @RequestParam(defaultValue = "2") int concurrency) {
        if (concurrency < 1 || concurrency > 4) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "concurrency must be between 1 and 4");
        }
        return Flux.range(1, 4)
                .flatMap(service::loadItem, concurrency);
    }

    @GetMapping("/ordered")
    Flux<ItemView> ordered() {
        return Flux.range(1, 4)
                .flatMapSequential(service::loadItem, 3);
    }

    @GetMapping("/serial")
    Flux<ItemView> serial() {
        return Flux.range(1, 4)
                .concatMap(service::loadItem);
    }

    @GetMapping("/profile/{id}")
    Mono<ProfileView> profile(@PathVariable int id) {
        if (id < 1) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "id must be positive"));
        }
        return Mono.zip(
                service.loadAccount(id),
                service.loadSettings(id),
                (account, settings) -> new ProfileView(
                        account.id(), account.name(), settings.theme()));
    }

    @GetMapping("/zip")
    Flux<String> zipped() {
        return Flux.zip(
                Flux.just("A", "B", "C"),
                Flux.just(1, 2),
                (letter, number) -> letter + number);
    }

    @GetMapping("/concat")
    Flux<String> concatenated() {
        return Flux.concat(
                Flux.just("A1", "A2"),
                Flux.just("B1", "B2"));
    }

    @GetMapping("/merge")
    Flux<String> merged() {
        Flux<String> a = Flux.just("A1", "A2")
                .delayElements(Duration.ofMillis(100));
        Flux<String> b = Flux.just("B1", "B2")
                .delayElements(Duration.ofMillis(60));
        return Flux.merge(a, b);
    }
}
```

### 11.3. Code Explanation

The file has a single public top-level class and package-private records/classes: valid in Java 17. Spring Boot WebFlux subscribes to the publishers for HTTP responses, with no `.block()` or manual `.subscribe()`. `Mono.delay` creates simulated async timers, not real HTTP network traffic. `flatMap(concurrency)` only bounds inner subscriptions per request. `flatMapSequential`/`concatMap` emit IDs 1..4, though `concatMap` does not launch inners concurrently. `Mono.zip` requires both Account and Settings. `Flux.zip` drops letter C because there is no third number. `Flux.merge` has non-deterministic output order.

This demo has no auth/DB/CSRF/rate limiting/metrics; do not deploy it publicly as a production API.

### 11.4. Running

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

If the server port is unchanged, test against `http://localhost:8080`.

### 11.5. Comparing Results

**Map:**

```bash
curl -i http://localhost:8080/api/demo/map
```

Status 200, deterministic JSON body:

```json
[10,20,30,40]
```

**FlatMap (order depends on scheduling):**

```bash
curl -i 'http://localhost:8080/api/demo/flat?concurrency=3'
```

The response contains all four objects ID=1..4, though order might be [3,2,1,4] or similar. **Never assert a hardcoded order** in tests. If `concurrency=0` or `concurrency=5`, the endpoint returns 400 due to the 1..4 range check.

**FlatMapSequential:**

```bash
curl -i http://localhost:8080/api/demo/ordered
```

JSON array ordered by ID:

```json
[
 {"id":1,"label":"item-1"},
 {"id":2,"label":"item-2"},
 {"id":3,"label":"item-3"},
 {"id":4,"label":"item-4"}
]
```

**ConcatMap:**

```bash
curl -i http://localhost:8080/api/demo/serial
```

Also yields IDs 1, 2, 3, 4, yet subscribes to each inner only after the previous finishes. In this demo, total time is usually longer than overlapping inner calls; exact latency is not guaranteed.

**Mono.zip profile:**

```bash
curl -i http://localhost:8080/api/demo/profile/7
```

Body:

```json
{"id":7,"name":"user-7","theme":"dark"}
```

The two sources delay ~100ms and ~70ms; when overlapping properly, total time is near the max latency plus overhead, not 170ms or exactly 100ms by default. `id=0` returns 400.

**Flux.zip vs. Flux.concat:**

```bash
curl -i http://localhost:8080/api/demo/zip
curl -i http://localhost:8080/api/demo/concat
```

Bodies respectively:

```json
["A1","B2"]
```

```json
["A1","A2","B1","B2"]
```

**Flux.merge:**

```bash
curl -i http://localhost:8080/api/demo/merge
```

Results include A1, A2, B1, B2, while cross-source order depends on timing. A1 precedes A2 from source A and B1 precedes B2 from source B.

**PowerShell:** use `curl.exe` instead of the PowerShell `curl` alias on some versions:

```powershell
curl.exe -i "http://localhost:8080/api/demo/map"
curl.exe -i "http://localhost:8080/api/demo/flat?concurrency=3"
curl.exe -i "http://localhost:8080/api/demo/ordered"
curl.exe -i "http://localhost:8080/api/demo/profile/7"
```

## 12. Testing with WebTestClient and StepVerifier

### 12.1. Test Dependencies

Add to the Spring Boot 3.5 POM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Boot BOM manages versions. `reactor-test` supplies `StepVerifier`; Spring Test and the WebFlux stack support `WebTestClient`.

### 12.2. HTTP Integration Test

Save `src/test/java/com/example/demo/ReactiveCombinationTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveCombinationTest {

    @Autowired
    WebTestClient client;

    @Test
    void mapProducesValues() {
        client.get().uri("/api/demo/map")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .json("[10,20,30,40]");
    }

    @Test
    void orderedMaintainsInputOrder() {
        client.get().uri("/api/demo/ordered")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$[0].id").isEqualTo(1)
                .jsonPath("$[1].id").isEqualTo(2)
                .jsonPath("$[2].id").isEqualTo(3)
                .jsonPath("$[3].id").isEqualTo(4);
    }

    @Test
    void zipCombinesProfile() {
        client.get().uri("/api/demo/profile/7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7)
                .jsonPath("$.name").isEqualTo("user-7")
                .jsonPath("$.theme").isEqualTo("dark");
    }

    @Test
    void invalidConcurrencyIsRejected() {
        client.get().uri("/api/demo/flat?concurrency=0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

The tests do not assert order on `/flat` because the operator makes no ordering guarantee. On very slow CI environments, adjust `WebTestClient`/app timeouts instead of inserting `Thread.sleep()` in tests.

### 12.3. Operator Unit Tests

Save `src/test/java/com/example/demo/OperatorTest.java`:

```java
package com.example.demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OperatorTest {

    @Test
    void mapIsDeterministic() {
        StepVerifier.create(Flux.just(1, 2, 3)
                        .map(i -> i * 10))
                .expectNext(10, 20, 30)
                .verifyComplete();
    }

    @Test
    void zipStopsWithShortest() {
        StepVerifier.create(Flux.zip(
                        Flux.just("A", "B", "C"),
                        Flux.just(1, 2),
                        (a, b) -> a + b))
                .expectNext("A1", "B2")
                .verifyComplete();
    }

    @Test
    void emptyMonoMakesZipEmpty() {
        StepVerifier.create(
                        Mono.zip(Mono.just(1),
                                Mono.<String>empty()))
                .verifyComplete();
    }

    @Test
    void concatKeepsBothSourcesInOrder() {
        StepVerifier.create(
                        Flux.concat(
                                Flux.just("A1", "A2"),
                                Flux.just("B1", "B2")))
                .expectNext("A1", "A2", "B1", "B2")
                .verifyComplete();
    }

    @Test
    void collectListProducesList() {
        StepVerifier.create(
                        Flux.just("A", "B").collectList())
                .expectNext(List.of("A", "B"))
                .verifyComplete();
    }
}
```

These are time-independent **semantic** unit tests. If you need to test actual concurrency:
- instrument inside `Mono.defer(...)` to count active subscriptions;
- increment an `AtomicInteger` on subscribe and decrement in `doFinally(...)`;
- drive controlled completions via `Sinks.One`/virtual scheduler;
- assert `peak active <= concurrency`;
- never measure the counter at **assembly** time, because assembly is not subscription.

### 12.4. Running Tests

```bash
# macOS/Linux
./mvnw test

# Windows
mvnw.cmd test
```

## 13. WebClient Practice: Avoiding Serial HTTP Calls

Aggregating independent product and inventory data:

```java
Mono<Product> product = catalogClient.get()
        .uri("/products/{id}", id).retrieve()
        .bodyToMono(Product.class);

Mono<Stock> stock = inventoryClient.get()
        .uri("/stock/{id}", id).retrieve()
        .bodyToMono(Stock.class);

Mono<ProductPage> page = Mono.zip(
        product, stock, ProductPage::new);
```

Snippet needs WebClient beans/DTOs and `id`. If recommendations depend on product category:

```java
Mono<RecommendationPage> page =
        catalogClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class)
                .flatMap(product ->
                        recommendationClient.get()
                                .uri("/categories/{cat}/recommendations",
                                        product.category())
                                .retrieve()
                                .bodyToFlux(Product.class)
                                .take(10)
                                .collectList()
                                .map(items -> new RecommendationPage(
                                        product, items)));
```

We must fetch the product first since the recommendation URL depends on its category; `flatMap` expresses that dependency. If you need to preserve UI rank order from a list of IDs, use `flatMapSequential(this::fetchProduct, concurrency)`. For updates requiring strict side-effect order, use `concatMap` alongside datastore transaction/version policies.

### 13.1. Layered Limits Together

```java
Flux<Product> products = Flux.fromIterable(ids)
        .take(50)
        .flatMap(id -> fetchProduct(id)
                .timeout(Duration.ofSeconds(2)), 5);
```

`take(50)` caps IDs pulled from the Flux, yet if `ids` was already materialized as a huge List beforehand, that List's memory still exists. Enforce limits at the request parser/API boundary. `flatMap(...,5)` only bounds concurrency for one subscription; HTTP client pools and global rate limits must still be configured separately.

## 14. Backpressure, Memory, and HTTP Responses

Common sources of memory growth:
- `flatMapSequential` buffering later inners that finish early;
- `zip` buffering from a fast source waiting on a slow source;
- `collectList()` collecting the entire source until completion;
- `buffer(n)` accumulating batches;
- `cache()` on hot/unbounded Fluxes with unlimited history;
- `onBackpressureBuffer()` without `maxSize`;
- response conversion, decoder buffers, Netty ByteBufs, and downstream client pool pending queues.

**Backpressure does not mean heap is always bounded.** Every collection/queue and concurrency setting must have business/storage caps.

In WebFlux, returning `Flux<T>` with `application/json` can be encoded/streamed via a non-blocking writer rather than necessarily collecting everything upfront like MVC. However, if the handler itself calls `collectList()`, data is already buffered before the writer can stream; on infinite streams, completion never arrives.

With `text/event-stream` or NDJSON, each item can be flushed/streamed individually; when an error occurs **after HTTP headers/body have committed**, the status cannot reliably switch from 200 to 500. Design application event-errors/connection-close handling and retry/cancellation for long streams. With a `Mono.zip` returning a DTO after dependencies finish, errors usually occur before writing the body, making 4xx/5xx mapping easier.

### 14.1. combineLatest Does Not Create a Transactional Snapshot

If a dashboard combines price A (at t=1) with quantity B (at t=2), `combineLatest` can emit a pair from data **at different transaction timestamps**. For finance or strict invariants, use a shared API/DB snapshot/version rather than `combineLatest` alone.

### 14.2. Cancellation Does Not Undo Committed DB Changes

When a browser disconnects, the upstream Publisher may be cancelled, yet committed DB side effects do not automatically roll back. Never treat HTTP cancellation as a substitute for transactions or distributed saga compensation. Use idempotency keys, transactions/outboxes, and operation statuses when business rules require them.

### 14.3. Context, Auth, and Secrets

Reactor Context differs from Java `ThreadLocal`. Do not assume MDC/`SecurityContextHolder` is automatically available on every scheduler thread. Use Spring Security reactive context/proper context propagation, pass verified identity/tenant explicitly downstream, and scope every query to verified permissions. During concurrent fan-out, prevent cross-tenant leaks and never log raw Authorization tokens in errors or logs.

## 15. Common Mistakes

| Symptom | Root Cause | Fix |
| --- | --- | --- |
| `Mono<Mono<T>>` | Used `map` with a Mono-returning function | Use `flatMap` |
| `Flux<Flux<T>>` | Used `map` with a Flux-returning function | Use `flatMap`/`concatMap` |
| Items out of order | `flatMap` merges by completion time | Use `flatMapSequential` or `concatMap` |
| Side effects written out of order | Multiple inners ran concurrently | Use `concatMap`, DB locks/versioning |
| Slow due to one-at-a-time processing | `concatMap` used on independent I/O | Use `flatMap` with measured concurrency |
| High wait time and memory growth | `flatMapSequential` queue waiting on first inner | Reduce concurrency/prefetch, drop ordering if allowed |
| Raised concurrency, no throughput gain | Downstream/pool saturated or blocking source | Measure latency, pools, schedulers, RPS |
| Zip produces no output | One source is empty/`Mono<Void>` | Use `switchIfEmpty`/`when`/`then` per contract |
| Secondary zip branch never subscribed | Empty source caused zip to complete early | Never bind mandatory side effects to zip subscription |
| Zip drops trailing items | One Flux is shorter | Expected semantics; pick `merge`/`combineLatest` if different goal |
| Concat never runs B | A is infinite | Switch to `merge` or bound A |
| `merge` does not keep global order | Values interleave | Use `concat` |
| `combineLatest` emits nothing yet | Has not received one value from every source | Provide defaults/initialization |
| WebFlux controller blocks event loop | Used `block()`/JDBC/`Thread.sleep` | Use reactive I/O or `boundedElastic` bridge |
| High queues, rising 429/503 | Fan-out multiplies inbound concurrency | Add bulkheads/rate limits/pool caps |
| Single error aborts whole batch | `flatMap`/`zip` fail-fast | Per-item `onErrorResume`/result DTO |
| Timeouts/retries worsen load | Unbounded or excessive retries | Set deadlines/backoff/filters/jitter |
| Partial errors hidden | `onErrorResume` returns empty for all errors | Classify and report missing items clearly |
| Broken concurrency test | Counting mapper assembly instead of subscriptions | Use `Mono.defer` + `doFinally` |
| Cannot change HTTP error status | Response already committed | Error event/close and pre-validation |
| `collectList` OOM | Source too large or infinite | Enforce limits/pagination/streaming |
| Lost tenant context | `ThreadLocal` not propagated | Reactor Context/auth-scope propagation |
| Flaky unit test order | Asserting fixed order on `flatMap`/`merge` | Assert item set without assuming order |

## 16. Review Checklist

1. Does the function in `map` return a plain value or a Publisher?
2. Is the source Mono (0..1) or Flux (0..N), cold or hot?
3. Could it be empty or `Mono<Void>`? How will `zip` behave?
4. Do you need output order or side-effect execution order? Those are two distinct requirements.
5. When should `flatMapSequential` be used instead of `concatMap`, accepting the queue cost?
6. Is actual concurrency bounded both per request and system-wide?
7. Do prefetch/inner cardinality/item sizes risk heap growth?
8. Are retries, timeouts, cancellation, and downstream connection pools configured?
9. For concurrent writes, are DB transactions/optimistic locking applied?
10. Should errors fail-fast or per-item, and can clients detect partial success?
11. Are there any blocking operations on Netty/event-loop threads?
12. Are CORS/auth/tenant ACLs/rate limits enforced during WebClient fan-out?
13. Does the HTTP writer stream or `collectList`? How are post-commit errors handled?
14. Are there deterministic tests for `map`/`zip`/`concat` and `flatMapSequential` order?
15. Are concurrency tests based on active subscriptions rather than wall-clock timing?
16. Are p95/p99 latency, active connections, queues, 429/503, and memory measured with slow downstream?

## 17. Self-Check

**Q1.** Given `Mono<UserId>.map(id -> fetchUser(id))`, if `fetchUser` returns `Mono<User>`, what is the resulting type?

**Answer:** `Mono<Mono<User>>`. Use `flatMap` to get `Mono<User>`.

**Q2.** Does `flatMap(mapper, 3)` mean the application uses exactly three threads?

**Answer:** No. It bounds active inner subscriptions/in-flight work for that operator, not total application threads.

**Q3.** What should you choose to preserve output order while still overlapping calls?

**Answer:** `flatMapSequential`, accepting buffering when later inners finish early.

**Q4.** If A must commit before B starts, is `flatMapSequential` sufficient?

**Answer:** No. Use `concatMap`/sequencing and protect DB transactions/concurrency.

**Q5.** What happens if one Mono in `Mono.zip` is empty?

**Answer:** There is not enough data to combine; zip typically completes empty.

**Q6.** What does `Flux.zip("A","B","C"` and `1,2)` return?

**Answer:** Pairs A1 and B2; C has no matching element in the other source so it is not emitted.

**Q7.** A dashboard needs the latest values whenever any sensor updates?

**Answer:** `combineLatest`, once every source has emitted at least one value.

**Q8.** If one of two sources in `Flux.concat` never completes, what happens to the second source?

**Answer:** The second source waits forever (absent timeouts or cancellation).

**Q9.** Why can concurrency 100 be slower than 10?

**Answer:** It can saturate downstream pools/CPU/queues or trigger 429/503; benchmark under realistic load.

**Q10.** Is calling `.block()` inside a WebFlux HTTP controller advisable?

**Answer:** Avoid it; return `Mono`/`Flux` and compose async work instead of blocking the event loop.

## 18. Official References

- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): Reactor/WebFlux non-blocking architecture.
- [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Reactive Streams, Mono, Flux, and backpressure.
- [Spring Framework — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): Publisher response encoding, stream semantics.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): composing non-blocking HTTP calls.
- [Spring Framework — WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): `bodyToMono`/`bodyToFlux`.
- [Project Reactor Core — Reference Guide](https://projectreactor.io/docs/core/release/reference/): transforming/combining streams, schedulers, error handling, testing.
- [Project Reactor — Flux Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `flatMap`, `flatMapSequential`, `concatMap`, `merge`, `zip`, `combineLatest`, `prefetch`.
- [Project Reactor — Mono Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `Mono.zip`/`zipWhen`/`flatMap`.
- [Project Reactor FAQ — zipWith/zipWhen empty sources](https://projectreactor.io/docs/core/release/reference/faq.html#faq.zip.empty): why nothing emits with `Mono<Void>`/empty.
- [Spring Boot 3.5 — Reactive Web](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux starter, reactive server.
- [Spring Boot 3.5 — Application Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `WebTestClient`.
- [Reactive Streams Specification](https://www.reactive-streams.org/): Publisher/Subscriber/Subscription demand, cancellation.

**Conclusion:** `map` computes synchronous values, `flatMap` flattens Publisher results allowing inner async calls to progress concurrently without guaranteeing order; `flatMapSequential` preserves **output** order, and `concatMap` serializes **inner execution**. Combine independent results with `Mono.zip`, dependent ones with `flatMap`/`zipWhen`, positional pairs with `Flux.zip`, time-interleaved streams with `merge`, sequential streams with `concat`, and latest states with `combineLatest`. Choose concurrency based on downstream limits, total inbound load, backpressure/prefetch/memory, timeouts, error semantics, and benchmarks rather than “higher is always faster”.
