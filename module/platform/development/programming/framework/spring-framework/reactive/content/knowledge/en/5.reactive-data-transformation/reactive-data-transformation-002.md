# flatMap for Work Returning a Publisher

In **Spring Framework Reactive** and **Project Reactor**, `flatMap` is the operator used when an input value must go through **an operation returning a `Publisher`** (typically a `Mono` or `Flux`), and the elements from that publisher are then forwarded down the pipeline. The key idea is that `flatMap` both **transforms** values and **flattens** nested publishers; with `Flux.flatMap`, operations may be active concurrently and results may interleave depending on when they become ready.

Practical examples: given a `userId`, calling an asynchronous API returning `Mono<User>`; given multiple `orderId`s, performing multiple reactive queries and producing a single combined `Flux<Order>`; or from each event creating a `Flux` of child events.

## 1. Learning Objectives

After this lesson, you will be able to:

- Choose appropriately among `map`, `flatMap`, `flatMapMany`, and `flatMapIterable` based on the return type of the transformation function.
- Explain the relationship between the *outer* `Publisher` and the *inner* `Publisher`s, as well as when work gets subscribed.
- Distinguish `Flux.flatMap`, `concatMap`, and `flatMapSequential` in terms of subscription timing, result ordering, and degree of overlap.
- Limit the number of active inner publishers using the `concurrency` parameter; understand `prefetch`, backpressure, and buffering.
- Write WebFlux pipelines without calling `block()` or `subscribe()` manually in controllers/services; handle empty sources, errors, and cancellation.
- Test `flatMap` values in an order-independent way when ordering is not guaranteed.

## 2. The Problem `flatMap` Solves

Suppose we have a profile lookup function:

~~~java
Mono<User> findUser(String userId);
~~~

When the input is `Mono<String>`, the following two expressions produce **two different types**:

~~~java
Mono<String> userId = Mono.just("u42");

Mono<Mono<User>> nested = userId.map(id -> findUser(id));

Mono<User> flattened = userId.flatMap(id -> findUser(id));
~~~

This is a **type illustration snippet**, not a standalone program because `User` and `findUser` are defined by the application.

- `map` takes a function `T -> R`. If `R` happens to be `Mono<User>`, the result becomes `Mono<Mono<User>>`: each outer signal contains **a publisher as a value**. Subscribing to the outer publisher does not mean the inner publisher has been subscribed to.
- `flatMap` takes a function `T -> Mono<R>` for `Mono<T>`. It subscribes to the inner publisher and forwards the value/completion/error appropriately out into a single `Mono<R>`.
- `Flux.flatMap` takes a function `T -> Publisher<R>`. Each input can produce a publisher carrying 0, 1, or many elements, and the results are **merged** into one `Flux<R>`.

Visualization:

~~~text
map:
outer:   "u42"
           |
           v
        findUser
           |
           v
      Mono<User>           -> Mono<Mono<User>>

flatMap:
outer:   "u42"
           |
           v
        findUser
           |
           v
inner:    User              -> Mono<User>
~~~

`flatMap` does not mean “run in parallel”. For a `Mono`, which has at most one outer value, the main concern is **chaining the next publisher**. For a `Flux` with multiple values, `flatMap` can subscribe to multiple inner publishers *eagerly* and **merge** elements arriving from them. The actual degree of overlap depends on the sources and schedulers; the operator itself does not force creating new threads.

## 3. Type Signatures and Operator Selection Rules

| Source | Transformation function | Operator | Result |
| --- | --- | --- | --- |
| `Mono<T>` | `T -> R` (plain value) | `map` | `Mono<R>` |
| `Mono<T>` | `T -> Mono<R>` | `flatMap` | `Mono<R>` |
| `Mono<T>` | `T -> Publisher<R>` that may emit multiple elements | `flatMapMany` | `Flux<R>` |
| `Flux<T>` | `T -> R` | `map` | `Flux<R>` |
| `Flux<T>` | `T -> Publisher<R>` | `flatMap` | `Flux<R>` |
| `Flux<T>` | `T -> Publisher<R>`, need to preserve outer order | `concatMap` / `flatMapSequential` | `Flux<R>` |
| `Flux<T>` | `T -> Iterable<R>` | `flatMapIterable` | `Flux<R>` |

**Quick rule of thumb:** look at **the return type of the lambda**. If the transformation function already returns a `Mono`, `Flux`, or another `Publisher`, you generally need a *flat* variant. If it only transforms objects synchronously such as `user.getName()` or `price.multiply(rate)`, using `map` is simpler.

Example:

~~~java
Mono<String> name = userMono.map(User::name); // User -> String
Mono<Address> address = userMono.flatMap(User::loadAddress); // User -> Mono<Address>
Flux<Permission> rights = userMono.flatMapMany(User::streamPermissions);
// User, Address, Permission are illustrative application types.
~~~

Note: `Flux.flatMap(mapper)` processes each source element, creates an inner publisher, and merges them. **The number of output elements does not necessarily equal the number of input elements**: an inner publisher can return `Mono.empty()` (0 elements), `Mono.just(...)` (1 element), `Flux.just(a,b)` (2 elements), or more.

## 4. Subscription, Demand, and Signal Mechanics

A single subscription to a `Flux.flatMap` pipeline can unfold as follows:

1. The final subscriber subscribes to the resulting `Flux`.
2. `flatMap` subscribes to the outer publisher.
3. When outer emits value `x`, the mapper creates inner publisher `P(x)`.
4. `flatMap` subscribes to that inner publisher (within the concurrency limit) and forwards elements emitted by the inner downstream.
5. When an inner completes, its slot can be reused to subscribe to another inner. The entire pipeline completes only when outer has completed **and** all associated inners have completed successfully.
6. If any source errors, the default mode propagates the error downstream and cancels remaining work as appropriate. If the subscriber cancels, cancellation is propagated to outer and active inners to the extent each source supports it.

Example of interleaved results:

~~~text
Outer: A -------- B -------- C
        |          |          |
        v          v          v
Inner A: --- A1 -------- A2 --|
Inner B: - B1 -- B2 ---------|
Inner C: -- C1 -------------|
Merged: A1 ... B1 ... B2 ... C1 ... A2 ...  (order depends on timing)
~~~

The diagram above only illustrates that inners can overlap, not an exact execution schedule. **`Flux.flatMap` does not guarantee preserving the order of outer or keeping elements from one inner contiguous relative to other inners.** Meanwhile, the order of elements emitted by **a single** valid publisher still follows that publisher's signal order.

### Backpressure When Flattening

Reactive Streams uses `request(n)` to express demand from downstream. `flatMap` coordinates demand for outer and the inners, though it does not necessarily forward the exact `request(n)` verbatim to each source. The `concurrency` and `prefetch` parameters affect the number of active subscriptions, the amount of data pre-requested, and internal buffers. If an inner is genuinely an asynchronous source with its own queue/buffer, you must account for that source's memory as well.

`flatMap` **does not automatically slow down an external service** if the HTTP service, SDK, callback, or message broker does not cooperate with demand. When limiting load, combine concurrency limits, timeout policies, connection limits, queue limits, retries, and each source's cancellation capability.

## 5. Runnable Java 17 Example: Chaining Mono and Merging Flux

The following example demonstrates (a) `Mono.flatMap` handling work returning a `Mono`, (b) that pipelines are *lazy* when constructed, and (c) `Flux.flatMap` merging multiple inner publishers. We use addition so the output **does not depend on merge order**.

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'FlatMapDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Create `src/main/java/FlatMapDemo.java`:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class FlatMapDemo {

    private static Mono<String> lookupUser(String id) {
        return Mono.defer(() -> {
            System.out.println("lookup " + id);
            return Mono.just("user-" + id);
        });
    }

    public static void main(String[] args) {
        Mono<String> profile = Mono.just("42")
            .flatMap(FlatMapDemo::lookupUser);

        System.out.println("pipeline created");
        System.out.println("result = " + profile.block());

        Integer sum = Flux.range(1, 3)
            .flatMap(n -> Mono.just(n * 10))
            .reduce(0, Integer::sum)
            .block();

        System.out.println("sum = " + sum);
    }
}
~~~

Run `gradle run` or `./gradlew run` if using the Gradle Wrapper (on Windows: `gradlew.bat run`). **Program stdout**, excluding Gradle messages:

~~~text
pipeline created
lookup 42
result = user-42
sum = 60
~~~

Explanation:

- `lookupUser` returns a `Mono<String>` created with `Mono.defer`. Code inside the supplier runs when the publisher is subscribed to, so “lookup 42” appears **after** “pipeline created”.
- `Mono.flatMap` subscribes to the inner `lookupUser("42")`, receives `user-42`, and passes that value out.
- `Flux.range(1, 3)` emits three numbers; each number becomes `Mono.just(n * 10)`. `flatMap` feeds the results into a Flux; `reduce(0, Integer::sum)` computes the sum 10 + 20 + 30, independent of order.
- `block()` in the example is **used only in the `main` method of the command-line program** to retrieve the result and exit the process. In a WebFlux handler/service, you normally **return `Mono` or `Flux`** and do not call `block()` on the event loop.

The Reactor/JUnit versions here are pinned for reproducing a minimal project. In a Spring Boot application, let the **Spring Boot BOM** manage Reactor and compatible dependency versions.

## 6. Result Ordering: flatMap, concatMap, and flatMapSequential

This is a key design decision when outer has multiple values:

| Operator | When inner is subscribed | Output order relative to outer | Characteristics |
| --- | --- | --- | --- |
| `flatMap` | Can subscribe to multiple inners eagerly | **Not guaranteed** | Merges as results arrive; inners can interleave. |
| `concatMap` | Waits for the current inner to complete before subscribing to the next inner | **Guaranteed** | Sequential, avoids interleaving; can be slower because it waits on earlier inners. |
| `flatMapSequential` | Can subscribe to multiple inners eagerly | **Guaranteed** | Overlapping execution, but **buffers** results from later-arriving inners to emit in outer order. |

Suppose two requests call services:

~~~text
ID 1 -> slow service (500 ms)
ID 2 -> fast service (50 ms)
~~~

- With `flatMap`, ID 2's result **can appear before** ID 1's.
- With `concatMap`, the request for ID 2 is only subscribed to after ID 1's publisher completes.
- With `flatMapSequential`, both requests can be subscribed together, but ID 2's result **is held back** until ID 1's result can be emitted in the proper order.

Integration example, assuming `fetchAsync(id)` returns a genuinely asynchronous `Mono<Reply>`:

~~~java
Flux<Integer> ids = Flux.just(1, 2, 3);

Flux<Reply> fastestFirst = ids.flatMap(id -> fetchAsync(id));
Flux<Reply> strictOrder = ids.concatMap(id -> fetchAsync(id));
Flux<Reply> orderedMerge = ids.flatMapSequential(id -> fetchAsync(id));
~~~

The three lines above are three **independent pipelines**. Each new subscription can re-invoke the source/work; you should not blindly subscribe to all three in a production application. `Reply` and `fetchAsync` are illustrative types/methods not defined in the command-line program in section 5.

**Selection rules:**

- If the goal is throughput of independent I/O operations and order does not matter, `flatMap` is usually suitable.
- If each task must wait for the previous task to complete to ensure operation order or business dependencies, use `concatMap`; do not rely on result timing to re-order operations.
- If independent tasks can run with overlap, yet results **must be emitted in input order**, consider `flatMapSequential` and evaluate buffering/head-of-line blocking cost.

### Asynchronous Example Just to Observe Ordering

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<String> calls = Flux.just(1, 2, 3)
    .flatMap(id -> Mono.delay(Duration.ofMillis((4 - id) * 80L))
        .map(tick -> "done-" + id));

calls.doOnNext(System.out::println).blockLast();
~~~

This is an integration Java snippet inside a method (`Flux` and `Mono` imported), which can be placed inside `main`. Because the delay for ID 3 is shorter than for ID 1, runs **typically** see ID 3 arrive earlier; **you must not assert that stdout always has one fixed order** because schedulers and subscription timing can vary. Replacing `flatMap` with `concatMap` preserves the order `done-1`, `done-2`, `done-3`, while also changing how the delays are triggered.

## 7. Controlling Concurrency and Prefetch

`Flux.flatMap` provides useful overloads:

~~~java
Flux<Reply> merged = ids.flatMap(id -> fetchAsync(id), 8);

Flux<Reply> tuned = ids.flatMap(id -> fetchUpdates(id), 8, 16);
~~~

This is an illustrative snippet with `ids` as `Flux<Integer>`, `fetchAsync` returning `Mono<Reply>`, and `fetchUpdates` returning `Flux<Reply>`. Meaning:

- `concurrency = 8`: limits the number of **inner publishers concurrently subscribed / awaiting completion** as coordinated by `flatMap`. This is not a promise of using exactly eight threads or having only eight physical connections in every system.
- `prefetch = 16`: configures how many elements `flatMap` prepares to pre-request from **each inner publisher**. Actual effectiveness depends on the inner and downstream demand; for an inner `Mono` emitting only one value, this parameter usually has less effect than for an inner `Flux` emitting many elements.

Another example where each inner actually emits two elements:

~~~java
Flux<Integer> grouped = Flux.range(1, 10)
    .flatMap(id -> Flux.just(id * 10, id * 10 + 1), 4, 2);
~~~

There are at most four active inners during the merge, and the prefetch parameter is two. The two elements from each inner can interleave with elements from other inners, so **do not write tests relying on outer order** unless using an order-preserving operator.

Do not set concurrency very high just to make things “faster”: with 2,000 IDs calling a service, high concurrency can exhaust connection pools, overload APIs, grow queues, or cause timeouts. Set limits based on downstream quotas, latency, resources, connection counts, payload size, and load testing results. Tune prefetch after measuring queues/memory rather than relying on a single “optimal” number for every pipeline.

## 8. Mono.flatMap, Mono.flatMapMany, and Empty Sources

### When the Input is a Mono and the Inner Has At Most One Element

~~~java
Mono<Order> order = orderRepository.findById("o1");
Mono<Customer> customer = order.flatMap(
    value -> customerRepository.findById(value.customerId())
);
~~~

`Mono.flatMap` returns `Mono<Customer>`. This is an integration snippet; the repositories and domain types must exist in the application.

### When the Input is a Mono but the Inner Can Emit Multiple Elements

~~~java
Mono<Customer> customer = customerRepository.findById("c1");
Flux<Order> orders = customer.flatMapMany(
    value -> orderRepository.findAllByCustomerId(value.id())
);
~~~

Use `flatMapMany` to obtain `Flux<Order>` instead of trying to cram multiple elements into one `Mono`.

### When the Input is Empty

~~~java
Mono<String> noId = Mono.empty();
Mono<String> result = noId.flatMap(
    id -> Mono.just("user-" + id)
);
~~~

`result` also completes empty; the mapper **is not called** when outer emits no `onNext`. In lookup operations, you can explicitly choose how to handle “not found”:

~~~java
Mono<User> requiredUser = userRepository.findById(id)
    .switchIfEmpty(Mono.error(new IllegalArgumentException("User not found")));
~~~

Note: `switchIfEmpty` handles **no elements emitted**; it does not catch API errors. If an inner fails, the error travels via `onError` and you can use `onErrorResume`/`retryWhen` when business logic permits.

### When the Input Produces a Synchronous Collection

~~~java
Flux<Integer> values = Flux.just(1, 2)
    .flatMapIterable(n -> java.util.List.of(n, n * 10));
~~~

Here the mapper returns an `Iterable`, not a `Publisher`. `flatMapIterable` is preferable to wrapping every collection in `Flux.fromIterable(...)` when you only need to flatten an existing collection. Still, do not construct a huge collection just to flatten it: the collection is still allocated up front.

## 9. Error Handling at the Inner Level and Pipeline Level

By default, an erroring inner can cause `flatMap` to emit `onError` and cancel the sources still running. For streams that need to process each ID independently, decide whether **a failed ID is allowed to be skipped**.

**Catching errors inside the mapper — isolated per element:**

~~~java
Flux<Result> results = ids.flatMap(id ->
    callRemote(id)
        .onErrorResume(error -> {
            logFailure(id, error);
            return Mono.empty(); // Intentionally drop this ID's result.
        }),
    8
);
~~~

This is an integration snippet; `Result`, `callRemote`, and `logFailure` are provided by the application. Each failed inner is turned into an empty completion and the other IDs have a chance to continue. **This approach intentionally drops the result of a failed ID**; it is inappropriate if every record must succeed.

**Catching errors outside — pipeline-wide scope:**

~~~java
Flux<Result> results = ids
    .flatMap(id -> callRemote(id), 8)
    .onErrorResume(error -> {
        logFailure("pipeline", error);
        return Flux.empty();
    });
~~~

When an error occurs, execution switches to the fallback for the **entire** Flux. In-flight inners may be canceled; do not interpret this as “skip just one ID and continue the whole list”.

If you need to collect errors after processing the remaining elements, Reactor provides `flatMapDelayError(mapper, concurrency, prefetch)`, though you must clearly design the error policy, resources, and how partial success is reported. `flatMapDelayError` does **not** turn failed operations into successes or retry them automatically.

For asynchronous APIs prone to timeouts:

~~~java
Flux<Result> results = ids.flatMap(
    id -> callRemote(id)
        .timeout(java.time.Duration.ofSeconds(3)),
    8
);
~~~

Each inner's timeout is propagated as an error. You can place `onErrorResume` **inside** to handle that error individually. On timeout or cancel, the publisher may attempt to cancel I/O, but it does not guarantee that a third-party operation was rolled back. Check idempotency and side effects if retrying.

## 10. Spring WebFlux Application Example: Asynchronous Data Enrichment

Suppose an API wants to return a list of orders along with customer names. A reactive repository emits `Flux<Order>`; WebClient returns `Mono<CustomerDto>`. `flatMap` is well suited for composing requests that depend on each order:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

@RestController
public class OrderController {
    private final OrderRepository orderRepository;
    private final WebClient customerClient;

    public OrderController(
            OrderRepository orderRepository,
            WebClient customerClient
    ) {
        this.orderRepository = orderRepository;
        this.customerClient = customerClient;
    }

    @GetMapping("/orders/enriched")
    public Flux<OrderView> enrichedOrders() {
        return orderRepository.findAll()
            .flatMap(order -> customerClient.get()
                .uri("/customers/{id}", order.customerId())
                .retrieve()
                .bodyToMono(CustomerDto.class)
                .map(customer -> new OrderView(
                    order.id(), customer.name()
                )), 8);
    }
}
~~~

**This is an integration code snippet**, not a standalone program. It requires a Spring Boot application with `spring-boot-starter-webflux`, a `WebClient` configured with a base URL, and the types `OrderRepository`, `Order`, `CustomerDto`, and `OrderView`. Minimal example of the data types (which can be replaced with real classes/records):

~~~java
record Order(String id, String customerId) {}
record CustomerDto(String name) {}
record OrderView(String orderId, String customerName) {}
~~~

The `OrderRepository` contract needs a method equivalent to `Flux<Order> findAll()`; in projects using Spring Data, declare a repository/adapter for the real domain. Do not create an empty repository and assume the endpoint will work.

Execution flow:

1. WebFlux subscribes to `Flux<OrderView>` when handling the HTTP response.
2. `findAll()` emits each `Order`. The mapper builds a WebClient request returning `Mono<CustomerDto>`.
3. `flatMap(..., 8)` allows up to eight active inner requests as coordinated by the operator.
4. Each successful response is `map`ped into an `OrderView`, then emitted to the HTTP response as it becomes ready.
5. The order of the `OrderView` elements **may differ from the order of `findAll()`**; if the API contract requires input order, consider `flatMapSequential(..., 8)`, or apply sorting by a business key with a reasonable data limit.

**Do not write it like this:**

~~~java
// Wrong implementation on the WebFlux event loop:
return orderRepository.findAll()
    .map(order -> customerClient.get()
        .uri("/customers/{id}", order.customerId())
        .retrieve()
        .bodyToMono(CustomerDto.class)
        .block());
~~~

`block()` blocks the thread during processing and can be rejected by Reactor on non-blocking threads. If you remove `block()` while still using `map`, the pipeline returns `Flux<Mono<CustomerDto>>` instead of the fetched customer objects. In a WebFlux handler, let the framework subscribe to the returned publisher; **do not call `subscribe()` inside the controller to kick off requests and return an early response**.

If each order needs both customer and payment at the same time, you can use `Mono.zip(customerMono, paymentMono)` **inside each mapper** when both sources actually emit a value to combine. When two sources only signal completion via `Mono<Void>`, use `Mono.when(...)` or `then(...)` instead of `zip`, because `zip` requires values from the sources to combine.

## 11. Blocking Sources, Hot Publishers, and Practical Limits

`flatMap` does not automatically offload blocking work to a separate thread:

~~~java
// Wrong: legacyBlockingCall(id) already runs synchronously inside the mapper.
Flux<Result> wrong = ids.flatMap(id ->
    Mono.just(legacyBlockingCall(id))
);
~~~

When forced to integrate a blocking API, you can isolate it using `fromCallable` and `Schedulers.boundedElastic()`:

~~~java
import reactor.core.scheduler.Schedulers;

Flux<Result> isolated = ids.flatMap(
    id -> Mono.fromCallable(() -> legacyBlockingCall(id))
        .subscribeOn(Schedulers.boundedElastic()),
    8
);
~~~

This is an integration snippet. Concurrency limits must not be ignored: boundedElastic threads are a finite resource, and JDBC connections/file I/O also have their own limits. When a genuinely reactive driver is available, prefer end-to-end non-blocking.

**Hot sources** can emit data before a subscriber registers or when downstream is slow. If a mapper creates an inner from a hot source, late subscription can miss signals; do not assume `flatMap` will replay events. You must identify each source's hot/cold contract, replay, backpressure, and cancellation behavior.

**Infinite streams:** `flatMap` can keep emitting indefinitely when outer or an inner never terminates. Therefore `collectList()`, `reduce(...)`, or `blockLast()` only complete when the source finishes. For infinite streams, consider `take(n)`, timeouts, windows, cancellation, and appropriate memory bounds; do not collect infinitely into a `List`.

**Business ordering dependencies:** if ID 2 must update after ID 1, `flatMap` can violate side-effect order even if `sort()` is used afterward to reorder the results. `sort()` only sorts **output values after they have been produced**; it does not undo the order of I/O operations. Use `concatMap` for sequential constraints or an appropriate transaction/serialization mechanism.

## 12. Testing with StepVerifier

Add `src/test/java/FlatMapTest.java` to the project from section 5 (`reactor-test` and JUnit dependencies are already declared):

~~~java
import java.util.Set;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class FlatMapTest {

    @Test
    void mergedValuesAreCorrectWithoutAssumingOrder() {
        Mono<Set<Integer>> values = Flux.just(1, 2, 3)
            .flatMap(n -> Mono.just(n * 10))
            .collectList()
            .map(Set::copyOf);

        StepVerifier.create(values)
            .expectNext(Set.of(10, 20, 30))
            .verifyComplete();
    }

    @Test
    void concatMapPreservesOuterAndInnerOrder() {
        Flux<String> result = Flux.just(1, 2, 3)
            .concatMap(n -> Flux.just(n + "a", n + "b"));

        StepVerifier.create(result)
            .expectNext("1a", "1b", "2a", "2b", "3a", "3b")
            .verifyComplete();
    }

    @Test
    void recoverOneInnerErrorWithoutStoppingTheOthers() {
        Mono<Set<Integer>> values = Flux.range(1, 3)
            .flatMap(n -> n == 2
                ? Mono.<Integer>error(
                    new IllegalStateException("bad"))
                    .onErrorReturn(-2)
                : Mono.just(n))
            .collectList()
            .map(Set::copyOf);

        StepVerifier.create(values)
            .expectNext(Set.of(1, -2, 3))
            .verifyComplete();
    }
}
~~~

Run `gradle test` or the corresponding Gradle Wrapper. All three tests are expected to **PASS**:

- The first test checks the **set of values** from `flatMap`, avoiding reliance on a merge order that is not guaranteed.
- The second test checks the ordering contract of `concatMap` across two elements from each inner.
- The third test places `onErrorReturn` **inside the mapper**, so the error on input 2 is replaced with -2 without terminating the other inputs.

Tests should compare using a `Set` only when values are **unique** and order truly does not matter; this approach loses multiplicity information for duplicate elements. If business logic requires preserving multiplicity, verify a histogram/count or compare a list sorted by key instead of converting straight to a `Set`.

With inners using `Mono.delay` and schedulers, use `StepVerifier.withVirtualTime(...)` or a controllable scheduler to test time-based behavior; do not use `Thread.sleep` and assert an output order that the operator does not guarantee.

## 13. Common Mistakes and Fixes

| Pattern / issue | Why it is wrong or risky | How to fix |
| --- | --- | --- |
| `map(id -> repo.findById(id))` when query results are needed | Creates `Flux<Mono<User>>`; the inner is not flattened automatically. | Use `flatMap(id -> repo.findById(id))`. |
| `flatMap(id -> Mono.just(transform(id)))` for a purely synchronous transformation | Unnecessary publisher, harder to read; if `transform` blocks, it still blocks. | Use `map` for pure functions; integrate blocking calls with an appropriate adapter. |
| Assuming `Flux.flatMap` preserves ID order | Fast inners can emit before slow inners. | Use `concatMap` or `flatMapSequential` depending on requirements. |
| Setting very high concurrency | Can overload services/DB, connection pools, queues, and memory. | Start with a measured limit and run load tests. |
| Using `sort()` to “fix” side-effect order | Only sorts results, does not fix the order of external actions. | Serialize tasks with `concatMap` if operation order is mandatory. |
| Catching errors after `flatMap` thinking it only skips one input | Recovery applies at the pipeline level and may cancel other inners. | Handle errors inside each inner if you want per-ID isolation. |
| Assuming every input always yields one output | An inner can be empty or emit multiple values. | Define the 0..N contract and how missing/multiple results are handled. |
| Calling `subscribe()` inside a service and returning another publisher | Breaks the caller's completion/error/cancellation chain. | Return the composed publisher so the caller/framework subscribes. |
| Calling `block()` inside a mapper running on the event loop | Blocks reactive processing, causing stalls or runtime errors. | Use non-blocking APIs; isolate bounded blocking adapters when unavoidable. |
| Collecting an infinite `Flux` with `collectList()` | The publisher never completes; memory grows as values keep arriving. | Set boundaries, limits, window/take, or consume as a stream. |

## 14. Checklist for Applying to a Real Pipeline

1. **Check the mapper's type:** does it return a plain value or a `Mono`/`Flux`? Choose `map` or `flatMap` from the type contract, not based on method names.
2. **Determine independence:** may a later input run before an earlier input finishes? If not, choose `concatMap` or an appropriate sequential mechanism.
3. **Define ordering requirements:** does the response need to preserve outer order? If yes while allowing I/O overlap, consider `flatMapSequential` and its buffer footprint.
4. **Set load limits:** measure concurrent requests, latency, connection pools, prefetch, queue capacity, and dependency capacity.
5. **Decide the error/empty policy:** if an ID is not found, times out, or fails, should it be skipped, replaced with a default, retried, or fail the whole pipeline? Place handling at the right level—inner or pipeline-wide.
6. **Preserve the cancellation chain:** return the publisher from the WebFlux handler and add timeouts/cleanup where needed; do not detach execution with `subscribe()` or block with `block()`.
7. **Write tests matching the contract:** test values and counts, test order only when the operator guarantees it, and test errors/cancellation/slow sources when they matter.

**Remember:** `map` transforms `T -> R`; `flatMap` is used when the next step returns `Publisher<R>` and you need to bring the inner's signals into the pipeline. For multiple outer values, `flatMap` prioritizes merging as results arrive and **does not guarantee order**; choose `concatMap` or `flatMapSequential` when order is part of the contract.

## References

- Reactor Core Reference Guide: https://projectreactor.io/docs/core/release/reference/
- Reactor Flux API — `flatMap`, `concatMap` and `flatMapSequential`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Mono API — `flatMap` and `flatMapMany`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring Framework WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Reactive Streams specification: https://www.reactive-streams.org/
