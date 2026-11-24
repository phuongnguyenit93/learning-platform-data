# Prefetch and Concurrency in Project Reactor Composing Operators

## 1. Learning Objectives

In Spring WebFlux, a stream often turns each input into a reactive task and merges all results back together. For example, a `Flux<OrderId>` is turned into multiple HTTP requests or multiple R2DBC queries. If too many tasks start at once, the system can exhaust connection pools and memory. If every task runs strictly one after another, a slow source can drag down throughput.

Two parameters are commonly used for tuning:

- **`concurrency` / `maxConcurrency`**: the number of *inner Publishers* allowed to have active subscriptions concurrently at a given moment, for operators that support this parameter.
- **`prefetch`**: the number of elements an operator pre-requests at a given upstream boundary, to keep the pipeline fed with data and avoid requesting one element at a time.

They relate to **backpressure** but solve two different problems. `concurrency` manages how many inner sources are active; `prefetch` manages element demand/buffering. The same `prefetch` value may apply to the **inner Publisher** in `flatMap`, or the **outer Publisher** in `concatMap`, depending on the API. Therefore, you cannot understand these two parameters from their names alone while ignoring their position in the processing diagram.

After this lesson, you will be able to:

1. Distinguish downstream `request(n)`, `concurrency`, and `prefetch`.
2. Correctly read the overloads of `flatMap`, `flatMapSequential`, `concatMap`, `merge`, and `mergeSequential`.
3. Explain why increasing concurrency usually increases in-flight tasks without equating to increasing the number of Java threads.
4. Explain why increasing prefetch can reduce gaps between emissions while also increasing the amount of prepared/buffered data.
5. Test ordering, subscription timing, and inner subscription limits using JUnit/`StepVerifier`.
6. Choose reasonable configurations for Spring WebFlux APIs with multiple independent data sources.

## 2. Foundation: Backpressure and `request(n)`

Reactive Streams uses `Subscription.request(long n)` so a subscriber can signal **demand to receive more elements** from a publisher. A protocol-compliant publisher must not send more `onNext` signals than the valid unfulfilled demand. `onComplete` or `onError` terminates the subscription.

```text
Subscriber                   Operator                  Publisher
    | request(1)                |                          |
    |-------------------------->|                          |
    |                           | request(?), may differ from 1 |
    |                           |------------------------->|
    |                           |<------------ onNext(...) |
    |<------------ onNext(...)  |                          |
    | request(1)                |                          |
    |-------------------------->|  ...                     |
```

The `?` is intentional: demand does not necessarily travel **unchanged** through operators. For example:

- `map` typically has a one-input → one-output relationship, so it is relatively direct.
- `buffer(10)` may need 10 inputs to form one buffer; requesting two buffers downstream can turn into requesting 20 elements upstream.
- `flatMap` creates multiple inner Publishers, so it must request data at **two levels**: the outer to know which inners to create, and each inner to receive its results.
- `concatMap` may pre-fetch outer values even though it subscribes to only **one** inner at a time.

Calling `.subscribe(value -> ...)` and some terminal operations typically request unbounded data (`Long.MAX_VALUE`) downstream. That does not mean every upstream is immediately requested unboundedly: intermediate operators can reshape demand, prefetch, and distribution.

### Observing Bounded Demand

This is a **snippet** to use with the Reactor Core dependency and imports for `Flux`, `BaseSubscriber`, and `Subscription`:

```java
Flux.range(1, 3)
        .doOnRequest(n ->
                System.out.println("upstream request=" + n))
        .subscribe(new BaseSubscriber<Integer>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("received=" + value);
                request(1);
            }
        });
```

Directly on `Flux.range`, requests may be observed as consecutive `1`s, followed by receiving values `1`, `2`, `3`. When operators with queues, fusion, or prefetch are inserted in between, upstream `doOnRequest` calls **may have different sizes**. Do not use a single log line to conclude the entire pipeline consumes strictly one element at a time.

**Backpressure is not rate limiting.** `request(16)` states the number of elements ready to be received; it does not mean the system allows 16 elements/second. Nor does it mean using exactly 16 connections or 16 threads.

## 3. `concurrency`: Limiting Active Inner Publishers

Consider a stream of multiple customer IDs:

```java
Flux<String> customerIds = Flux.just("A", "B", "C", "D");

Flux<Customer> customers = customerIds.flatMap(
        id -> fetchCustomer(id),
        2,
        8
);
```

This is a **design snippet**, requiring `fetchCustomer(String)` returning `Publisher<Customer>` (usually `Mono<Customer>`) and an application `Customer` type. The last two parameters are `concurrency=2` and `prefetch=8`.

For **cold inner Publishers that do not complete immediately**:

```text
Outer:       A       B       C       D
                  |
maxConcurrency = 2
                  v
Initial:     subscribe fetch(A), fetch(B)
Waiting:     C, D not yet activated as active inners
B finishes:  frees a slot -> subscribe fetch(C)
A finishes:  frees a slot -> subscribe fetch(D)
```

Practical meaning:

- `concurrency=2` caps **at most two active inner subscriptions** at a time for this operator.
- When an inner finishes, the operator can take another outer item to create/subscribe to the next inner.
- Elements from A and B can still **interleave** in `flatMap`'s output; concurrency does not guarantee output order matching the input IDs.
- `concurrency` also typically influences the initial demand sent to the outer in `flatMap`: enough outer elements are needed to fill open slots.

**Concurrency is not thread count.** A `WebClient` or reactive driver can use an event loop to perform many non-blocking I/O operations simultaneously without creating a thread per inner. Conversely, if the mapper uses a blocking API, two inners can occupy two worker threads or stall the event loop if run in the wrong place. Actual connection counts also depend on the connection pool, HTTP protocol, retries, redirects, and behavior inside each inner.

Do not assume `maxConcurrency=8` is an application-wide limit. If 20 concurrent HTTP requests arrive and **each request** creates a `flatMap(..., 8, ...)` pipeline, the total tasks across all pipelines can be many times greater than 8. To enforce a global quota, you need a shared limiting mechanism at the client, a semaphore, or an appropriate coordination layer.

## 4. `prefetch`: Proactively Requesting Data Ahead

Suppose an inner `Flux<LineItem>` has many elements:

```java
Flux<LineItem> lines = fetchLines(orderId);
```

Waiting for downstream to request one element at a time before notifying the source can generate many round-trips of signal exchange. Prefetch allows an operator to ask for a batch of elements ahead of time for gradual use.

With:

```java
Flux<LineItem> combined = orderIds.flatMap(
        orderId -> fetchLines(orderId),
        3,    // concurrency: at most 3 active inners
        4     // prefetch: initial request amount per inner
);
```

A visual model:

```text
                flatMap(maxConcurrency=3, prefetch=4)
Outer IDs  ----------------------------------------------->
             |            |             |
             v            v             v
         inner #1      inner #2       inner #3
         request(4)    request(4)     request(4)
             |            |             |
             +------------+-------------+
                          |
                 Queue/drain by demand
                          |
                      Downstream
```

In operators that support prefetch, Reactor typically **replenishes demand in batches** once a significant portion of the previously requested amount has been consumed. Reactor documentation describes a heuristic of roughly **75% of prefetch** for many operators. This is an optimization behavior, not a contract that every operator, version, and source calls `request()` with the exact same sequence of numbers; fusion, scalar optimizations, and version changes can alter the logs.

**Do not interpret `prefetch=4` as "an inner may emit at most four elements over its entire lifetime".** Four elements is the initial demand; as elements are consumed, the operator will request more. An inner can perfectly well emit 10,000 elements across multiple rounds.

### Where Does Prefetch Apply?

The easiest point of confusion is **where demand is granted**:

| Operator / Overload | What `concurrency` Controls | Where `prefetch` Primarily Applies |
|---|---|---|
| `flatMap(mapper, concurrency, prefetch)` | Number of simultaneously running inners | Initial request **per inner** |
| `flatMapSequential(mapper, maxConcurrency, prefetch)` | Number of eagerly subscribed inners | Request **per inner**, while potentially buffering results to preserve order |
| `concatMap(mapper, prefetch)` | No concurrency parameter; subscribes each inner sequentially | Requests values from the **outer source** |
| `Flux.merge(sources, concurrency, prefetch)` when `sources` is a `Publisher<Publisher<T>>` | Number of inner sources merged concurrently | Request **per inner source** |
| `Flux.mergeSequential(sources, maxConcurrency, prefetch)` in the corresponding overload | Number of eagerly subscribed active inner sources | Request **per inner source**, buffered to preserve group order |
| `publishOn(scheduler, prefetch)` | No inner concurrency | Request at the boundary **before `publishOn`** when switching schedulers |

Important note: the signatures in the table refer to overloads that **provide the corresponding parameters**. For instance, `Flux.merge(a, b)` takes specific publishers and does not take an additional `prefetch` in the same way. With `concatMap`, `prefetch` on the outer does not raise the number of concurrently subscribed inners above one.

Do not equate `prefetch` with **HTTP response size**, **buffer byte count**, **API requests/second**, or **pool connection count**. It is a demand parameter in **element units** for a publisher.

## 5. Comparing Four Composition Styles: Ordering, Subscriptions, and Resources

| Operator | When Is the Next Inner Subscribed? | Does Output Preserve Outer Group Order? | Can Multiple Inners Run Together? |
|---|---|---|---|
| `concatMap(mapper, prefetch)` | Only after the previous inner completes | Yes | No, by concat semantics |
| `flatMap(mapper, concurrency, prefetch)` | Eagerly, up to concurrency limit | Not guaranteed | Yes |
| `flatMapSequential(mapper, maxConcurrency, prefetch)` | Eagerly, up to concurrency limit | Yes | Yes |
| `Flux.concat(a,b)` | Only after `a` completes successfully | Yes | No, under concat |
| `Flux.merge(a,b)` | Subscribes sources eagerly | Not guaranteed | Yes |
| `Flux.mergeSequential(a,b)` | Subscribes eagerly but emits by group | Yes | Yes |

Example where A is slow and B is fast:

```text
                 0 ms       40 ms       80 ms       200 ms
Source A:        subscribe -------------------------- A1
Source B:        subscribe -- B1 ------- B2

flatMap / merge:                  B1   B2            A1
flatMapSequential / mergeSequential:
                              (buffer B1, B2)        A1, B1, B2
concatMap / concat: (only subscribe B after A completes)
```

With distinct asynchronous sources, increasing concurrency can let B start early and reduce total duration. However, `flatMapSequential` must **hold B's results in a buffer** while A has not yet completed in order to preserve ordering. If A is very slow and many later sources emit large payloads, buffering becomes an important consideration.

Do not call `flatMapSequential` a `sort` by emission time. It preserves **group order by outer position**, not event timestamp ordering.

### `concatMap` Can Prefetch Outer While Staying Sequential

```java
Flux<String> ordered = ids.concatMap(
        id -> fetchText(id),
        8
);
```

`concatMap(..., 8)` can pre-request several `id` values from the outer source, yet **does not start `fetchText(id)` for the next ID** until the previous inner completes. This keeps outer data ready while preserving sequential business steps.

In Reactor 3.6.x, the `concatMap(mapper, 0)` overload allows disabling outer prefetch; check the API docs for your running version if relying on subtle differences between overloads. Large prefetch should not be used to bypass resource limits or expected to replace `concurrency`.

## 6. An Example Calculating Demand and Buffering

Suppose an outer source produces a list of 500 orders. For each order, the inner can return a stream of up to 30 line items:

```java
Flux<LineItem> allLines = orderIds.flatMap(
        id -> queryLines(id),
        4,
        8
);
```

Conceptually:

1. `flatMap` can subscribe to at most **4** inners at the same time.
2. Each inner can receive an initial demand of roughly **8** elements, meaning total initial demand across active inners can be around `4 × 8 = 32` elements.
3. As downstream consumes elements and inners still have data, demand is replenished. New inners can be subscribed as slots open up.
4. If downstream is slower than the inners, elements already requested but not yet emitted downstream can be held in internal queues/buffers.
5. After one order completes, another order can fill the slot; all 500 orders do not need to be active simultaneously.

**The number 32 is only an illustrative model for initial request volume**, not an absolute upper bound for every queue or heap. Why:

- Demand is replenished over time; a single inner can emit more than `prefetch` over its lifetime.
- `flatMap` may have outer/inner queues, processed items awaiting downstream, codec/network buffers, and other operator layers.
- One element can be a 10-byte string or a multi-megabyte object/JSON: `prefetch=8` does not cap at 8 KB or any specific byte size.
- Non-backpressure-compliant sources or hot sources with separate overflow policies may require completely different handling.

When tuning in practice, monitor **active inner count**, queued elements, average object size, heap/GC usage, and downstream capacity. The formula `concurrency × prefetch` is a starting point for understanding pressure, **not a memory guarantee**.

## 7. Runnable Java 17+ Program: Testing Concurrency and Ordering

The following example uses **Reactor Core 3.6.6**, JUnit Jupiter, and `reactor-test`. It is a standalone Java project requiring no Spring WebFlux startup. `Sinks.One` lets the test explicitly finish each inner to show when concurrency slots are freed. `StepVerifier.withVirtualTime` tests the ordering of inners with different delays without depending on wall-clock time.

Create the structure:

```text
reactor-prefetch-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── edu/
                └── demo/
                    └── PrefetchConcurrencyTest.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-prefetch-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.6.6</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/test/java/edu/demo/PrefetchConcurrencyTest.java`:

```java
package edu.demo;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PrefetchConcurrencyTest {

    private static Mono<String> delayed(int id) {
        long delay = switch (id) {
            case 1 -> 100L;
            case 2 -> 20L;
            default -> 40L;
        };
        return Mono.delay(Duration.ofMillis(delay))
                .map(tick -> "R" + id);
    }

    @Test
    void flatMapInterleavesFasterInners() {
        StepVerifier.withVirtualTime(() ->
                Flux.range(1, 3)
                        .flatMap(
                                id -> delayed(id),
                                3,
                                1
                        ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(150))
                .expectNext("R2", "R3", "R1")
                .verifyComplete();
    }

    @Test
    void flatMapSequentialPreservesSourceOrder() {
        StepVerifier.withVirtualTime(() ->
                Flux.range(1, 3)
                        .flatMapSequential(
                                id -> delayed(id),
                                3,
                                1
                        ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(150))
                .expectNext("R1", "R2", "R3")
                .verifyComplete();
    }

    @Test
    void concatMapSubscribesToOneInnerAtATime() {
        List<Sinks.One<Integer>> gates = new ArrayList<>();
        for (int index = 0; index < 3; index++) {
            gates.add(Sinks.one());
        }

        List<Integer> started = new CopyOnWriteArrayList<>();

        Flux<Integer> ordered = Flux.range(1, 3)
                .concatMap(id ->
                        gates.get(id - 1).asMono()
                                .doOnSubscribe(s -> started.add(id)), 2);

        StepVerifier.create(ordered)
                .expectSubscription()
                .then(() -> assertEquals(List.of(1), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(0).tryEmitValue(1)))
                .expectNext(1)
                .then(() -> assertEquals(List.of(1, 2), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(1).tryEmitValue(2)))
                .expectNext(2)
                .then(() -> assertEquals(List.of(1, 2, 3), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(2).tryEmitValue(3)))
                .expectNext(3)
                .verifyComplete();
    }

    @Test
    void flatMapOpensOnlyTwoInitialSlotsAndRefillsThem() {
        List<Sinks.One<Integer>> gates = new ArrayList<>();
        for (int index = 0; index < 4; index++) {
            gates.add(Sinks.one());
        }

        List<Integer> started = new CopyOnWriteArrayList<>();

        Flux<Integer> merged = Flux.range(1, 4)
                .flatMap(id ->
                        gates.get(id - 1).asMono()
                                .doOnSubscribe(s -> started.add(id)),
                        2, 1);

        StepVerifier.create(merged)
                .expectSubscription()
                .then(() -> assertEquals(List.of(1, 2), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(1).tryEmitValue(2)))
                .expectNext(2)
                .then(() -> assertEquals(List.of(1, 2, 3), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(2).tryEmitValue(3)))
                .expectNext(3)
                .then(() -> assertEquals(List.of(1, 2, 3, 4), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(0).tryEmitValue(1)))
                .expectNext(1)
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(3).tryEmitValue(4)))
                .expectNext(4)
                .verifyComplete();
    }
}
```

Run the command in the `reactor-prefetch-demo` directory:

```bash
mvn test
```

Once the environment resolves dependencies successfully, the expected result is **four passing tests**. The test names and assertions explain what was verified:

- `flatMapInterleavesFasterInners`: three inners start eagerly; results arrive in emission order: `R2`, `R3`, `R1`.
- `flatMapSequentialPreservesSourceOrder`: may start eagerly, yet downstream receives `R1`, `R2`, `R3`.
- `concatMapSubscribesToOneInnerAtATime`: despite `prefetch=2`, only one inner is subscribed at a time; `started` progresses as `[1]`, `[1,2]`, `[1,2,3]` after controlled completions.
- `flatMapOpensOnlyTwoInitialSlotsAndRefillsThem`: although outer has 4 elements, initially only inners 1 and 2 are subscribed; when inner 2 finishes, 3 is subscribed; when 3 finishes, 4 is subscribed. Results can arrive in order `2, 3, 1, 4`, differing from outer order.

**Note on test scope:** In the first two tests, `prefetch=1` only serves as the inner configuration parameter; each `Mono` inherently emits at most one value. Thus those two tests primarily demonstrate **composition ordering**, not queue size or throughput when changing prefetch. To measure prefetch impact, you need multi-value inner `Flux` streams and demand/queue instrumentation as shown next.

## 8. Observing Prefetch on Multi-Element Inners

The example below lets you observe `request(n)` when an outer source creates three inner `Flux` streams. This is a **snippet inside a Java method** importing `Flux`, `BaseSubscriber`, and `Subscription`:

```java
Flux<Integer> result = Flux.range(1, 3)
        .flatMap(id ->
                Flux.range(id * 10, 5)
                        .hide()
                        .doOnSubscribe(s ->
                                System.out.println("inner " + id
                                        + " subscribed"))
                        .doOnRequest(n ->
                                System.out.println("inner " + id
                                        + " request=" + n)),
                2, 2);

result.subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("received=" + value);
        request(1);
    }
});
```

How to read the logs:

1. Even though the outer has 3 IDs, at most 2 inners are initially subscribed because `concurrency=2`.
2. `prefetch=2` causes inners to be requested in batches rather than every element waiting on a new downstream request.
3. When one inner finishes, the third ID can become an active inner.
4. `BaseSubscriber` at the end only calls `request(1)` at a time, yet the intermediate operator can still proactively request ahead and hold some data.
5. `hide()` is used to reduce the effect of certain *fusion* optimizations when observing signals; exact log details can still vary across Reactor versions and thread interleavings.

**Do not treat one specific log sequence as the sole valid output.** `flatMap` does not guarantee element ordering **across** inners; refill algorithms and queues can differ from a naive `2,2,2` repetition. To verify critical requirements, write assertions on the required behavior or use `StepVerifier`, while also measuring with monitoring tools in a real application.

### Why Do `Mono` and `Flux` Need Different Prefetch Tuning?

- An inner `Mono<T>` emits at most **one** value. Raising prefetch from 1 to 16 generally does not produce 15 extra results from that inner. When many `WebClient` `.bodyToMono(...)` calls run concurrently, **concurrency, connection pool, and timeouts** usually matter more than prefetch.
- An inner `Flux<T>` can emit thousands of elements. Prefetch then affects how much demand runs ahead and queue/memory pressure, especially when downstream processes slowly.
- If an inner returns a `Flux` from a streaming HTTP decoder or R2DBC, whether backpressure propagates through the entire network/database driver still depends on the implementation. Do not equate `request(16)` with the driver or remote server performing exactly 16 physical operations.

## 9. Purposeful Tuning in Spring WebFlux

Example of a service calling a non-blocking API to fetch multiple records per customer ID:

```java
@Service
public class CustomerQueryService {
    private final WebClient client;

    public CustomerQueryService(WebClient client) {
        this.client = client;
    }

    public Flux<CustomerRecord> loadRecords(Flux<String> customerIds) {
        int maxConcurrency = 8;
        int innerPrefetch = 16;

        return customerIds.flatMap(id ->
                        client.get()
                                .uri("/customers/{id}/records", id)
                                .retrieve()
                                .bodyToFlux(CustomerRecord.class),
                maxConcurrency,
                innerPrefetch);
    }
}
```

This is an **integration snippet**: it requires `CustomerRecord` as a project data type, a `WebClient` bean, imports for `org.springframework.stereotype.Service`, `org.springframework.web.reactive.function.client.WebClient`, and `reactor.core.publisher.Flux`, plus a real upstream API. It is not yet a standalone runnable Spring Boot project.

What happens within a single subscription:

- Up to 8 inner reactive HTTP streams can be active, depending on the number of customer IDs and source availability.
- Each inner `Flux<CustomerRecord>` receives demand per the prefetch setting and refill algorithm.
- Results from different customers can interleave. If the API must return customers in input ID order, consider `flatMapSequential` with the same parameters; the trade-off may be increased buffering.
- This is an **operator-level limit within one subscription**. Actual requests, connections, and upstream load are also governed by pools, retries, HTTP client limits, multiple concurrent subscribers, and the target service.
- With `bodyToMono(CustomerRecord.class)`, each inner produces at most one element; choosing a small/default `prefetch` is usually enough, prioritizing `maxConcurrency` and client pool management.

If business logic strictly requires finishing the previous customer before moving to the next customer:

```java
return customerIds.concatMap(id ->
        client.get()
                .uri("/customers/{id}/records", id)
                .retrieve()
                .bodyToFlux(CustomerRecord.class),
        8);
```

Here `8` is the **prefetch of outer IDs** in the `concatMap` overload, **not eight concurrent HTTP requests**. The previous source must complete before moving to the next source.

### Do Not Use Operator Parameters as Substitutes for Other Limits

`concurrency=8` is **not** equivalent to:

- At most 8 requests/second (that is a time-based rate limit).
- At most 8 active requests across the entire system (other subscriptions/requests exist).
- Connection pool having only 8 connections (the pool is configured separately).
- Every request definitely having an 8-second timeout (timeouts are configured separately).
- Having 8 dedicated threads for 8 inners (Reactor does not default to creating a thread per inner).

To cap API calls system-wide, use a mechanism with a wide enough shared scope such as a connector pool limit, gateway/service concurrency control, or upstream quota. For timeouts, use timeouts on `WebClient`/client and/or `.timeout(...)` in the pipeline. For retries, decide the policy and placement of `retryWhen` separately; retries can multiply actual upstream accesses.

## 10. `flatMapSequential`: High Concurrency Can Cause Head-of-Line Blocking

Suppose inner A takes 5 seconds, while B and C return data after 50 ms:

```text
Outer order: A, B, C

A:  ────────────────────────────────────── A1, complete
B:  ─ B1, B2, complete
C:  ── C1, C2, complete

flatMap(A,B,C):
    B1, B2, C1, C2, A1  (one possible order)

flatMapSequential(A,B,C):
    [buffer B1,B2,C1,C2 while waiting for A]
    A1, B1, B2, C1, C2
```

`flatMapSequential` lets B/C run eagerly; **output is still blocked behind A** to preserve ordering. This is called head-of-line blocking at the emission stage, and can increase time-to-first-element latency even when many background tasks have already finished.

With inner `Flux` streams returning lots of data, raising `maxConcurrency` and `prefetch` together can cause later sources to produce large amounts of results that must be buffered:

- If full group ordering is mandatory, measure the size and wait time of those buffers.
- If ordering is not mandatory, `flatMap`/`merge` can deliver elements downstream sooner.
- If each inner carries large payloads, consider lower concurrency, lower prefetch, or a paged/chunked stream design.
- If an inner never completes, `flatMapSequential` may never emit subsequent groups even if they are ready; explicit timeouts or cancellation are required.

This is why you cannot assume "higher concurrency is always better": the more sources run early, the more data may have to wait for output order.

## 11. What Other Boundaries Does Prefetch Cross?

Multiple operators in the same pipeline can reshape demand together. Read the pipeline from **downstream back to upstream** to spot the actual boundaries:

```java
Flux<LineItem> result = orderIds
        .flatMap(id -> queryLines(id), 4, 8)
        .publishOn(Schedulers.parallel(), 16)
        .limitRate(32);
```

This is a snippet requiring `orderIds`, `queryLines`, `LineItem`, imports for `Flux`, `Schedulers`, and appropriate dependencies.

- `flatMap(...,4,8)`: up to 4 active inners; each inner is prefetched by 8 elements.
- `publishOn(...,16)`: moves downstream processing to the specified scheduler and uses prefetch for demand at the boundary before `publishOn`.
- `limitRate(32)`: splits large downstream demand into upstream batches according to the operator's threshold; it does **not** cap at 32 elements/second.
- The demand and queues of these operators **interact**; you cannot take `4 × 8 + 16 + 32` as an exact formula for heap usage.

`publishOn` also switches execution context; it is **not** a default way to automatically run every inner in parallel. I/O sources already have their own asynchronous scheduling; add `publishOn` or `subscribeOn` when there is a clear purpose. If the mapper contains blocking JDBC, prioritize redesigning the driver or isolating blocking work properly rather than "fixing" it by increasing prefetch.

### How Do Prefetch and `limitRate` Relate?

`limitRate(highTide)` is a tool to throttle upstream demand in batches; `limitRate(highTide, lowTide)` lets you tune the replenishment point. Prefetch is a parameter **internal to a specific operator**, adjusting its input demand. Both use `request(n)` but operate at different boundaries and serve different purposes.

Example:

```java
Flux.range(1, 100)
        .limitRate(16)
        .doOnNext(System.out::println)
        .subscribe();
```

This is a snippet and does not represent a 16 elements/second limit. Default `subscribe()` is willing to receive everything; `limitRate(16)` shapes how the upstream source is requested into batches to avoid passing a single unbounded request straight through.

## 12. Errors, Cancellation, Hot Sources, and Backpressure

### Errors and Cancellation

With `flatMap`, an inner emitting `onError` normally causes the overall result to fail fast with that error and cancels other inners. When a subscription is cancelled from downstream, the operator attempts to cancel active inners and drop remaining queued elements according to the operator's discard support.

```java
Flux<LineItem> result = orderIds
        .flatMap(id -> queryLines(id), 4, 8)
        .timeout(Duration.ofSeconds(5));
```

This is a snippet; it requires importing `Duration` and real sources. Here `.timeout(Duration)` bounds **the wait time between signals** or from subscribe to the first element—it is not inherently a five-second deadline for an entire multi-element request. You must design appropriate HTTP client timeouts and business deadlines. Cancellation does not guarantee work outside Reactor always stops immediately if the source library does not honor cancellation.

If you want to delay errors until other inners have a chance to finish, Reactor provides `flatMapDelayError(mapper, concurrency, prefetch)` and merge delay-error variants. This **does not fix errors**; it only changes when the terminal error is emitted, and can increase queue occupancy, wait times, and resource usage.

### Hot Sources and Sources That Ignore Demand

`prefetch` assumes upstream honors request/demand. With a hot publisher, elements can arrive externally regardless of subscriber speed; you must check overflow policies: bounded buffer, drop, latest, fail, or persisting to a durable system.

Do not treat `prefetch=8` as a mechanism that automatically makes a Kafka broker, socket, database, or every `Sinks.Many` produce exactly eight elements. Driver, broker, and codec behavior must be examined separately.

If an outer source uses `groupBy` to create many groups where each group is not yet consumed, a `flatMap` with too low a `maxConcurrency` can sometimes stall the pipeline or deadlock because unconsumed groups are not drained. This is a case where concurrency must be chosen based on the **actual group count** and consumption strategy, rather than hardcoding a low value for every source.

## 13. A Data-Driven Tuning Workflow

A repeatable workflow:

1. **Identify ordering requirements**: interleaving allowed (`flatMap`/`merge`), source order required (`flatMapSequential`), or sequential completion per source (`concatMap`).
2. **Count actual inners**: does each input ID create one `Mono`, a multi-element `Flux`, or multiple HTTP calls inside a single inner? This is the unit to bound.
3. **Pick a moderate initial concurrency** compatible with the connection pool and upstream quota; do not set it overly high just to "run fast".
4. **Pick prefetch based on data shape**: for single-value `Mono`, little tuning is needed; for large `Flux`, consider record size, downstream speed, and queue budget.
5. **Set timeout/cancellation/error policies** so no inner hangs indefinitely and occupies a concurrency slot forever.
6. **Load test at realistic scale**, tracking throughput, p50/p95/p99 latency, heap, GC, active/waiting connections, failed requests, and queue depth.
7. **Adjust one variable at a time** (e.g., concurrency 4 → 8 while holding prefetch fixed; then prefetch 8 → 16 at the same load) to see which change actually helps.
8. **Test bursts and slow downstream**, because buffers typically grow sharply only when source speed exceeds consumption speed.

There is no "optimal" prefetch/concurrency number for every project. Illustrative numbers like `2`, `4`, `8`, `16` in this article **are not production default recommendations**.

### Symptom and Adjustment Patterns

| Symptom | Possible Cause | Where to Investigate |
|---|---|---|
| High latency, spare pool capacity, independent APIs running sequentially | `concat`/`concatMap` does not match requirements | Consider `flatMap` with bounded concurrency if interleaving is allowed |
| Many timeouts/429/503 from upstream when raising concurrency | Exceeding quota/pool or overloading remote | Lower concurrency, control retries and quotas |
| Rapid heap/GC growth with `flatMapSequential` | Slow early source, many later sources emitting results that must be buffered | Lower concurrency/prefetch, re-evaluate ordering requirements |
| Large `Flux` progresses unevenly despite spare CPU/network | Prefetch too low or sporadic downstream requests | Observe `doOnRequest` and queues, and try controlled prefetch increases |
| Slow downstream, queues growing | Production rate exceeds consumption rate | Lower prefetch/concurrency, apply demand/backpressure at the source |
| Many HTTP requests despite small per-pipeline concurrency | Multiple concurrent subscriptions or inners issuing multiple requests | Enforce global/connection-pool limits, inspect client-level metrics |
| JDBC mapper stalling the event loop | Blocking work on the wrong scheduler | Use a suitable stack or isolate blocking sources; raising concurrency does not fix the root cause |

## 14. Common Misconceptions to Avoid

| Misconception | Correct Understanding |
|---|---|
| "`concurrency=8` means exactly eight threads" | It limits active inners in the operator; threads are decided by the runtime/scheduler. |
| "`prefetch=16` means at most 16 elements in the entire stream" | It is the initial/per-batch input demand; total emissions can be very large. |
| "`flatMap(...,8,16)` and `concatMap(...,16)` both run 16 inners" | `flatMap` runs multiple inners; `concatMap` subscribes to one inner at a time. |
| "`prefetch` has only one meaning across every operator" | You must check whether it applies to outer, inner, or a scheduler boundary. |
| "`flatMap` preserves outer order" | Results can interleave. Use `flatMapSequential` if group order is required. |
| "`flatMapSequential` uses no extra memory" | Results from early-finishing inners can be buffered while waiting on earlier inners. |
| "Increasing concurrency always increases throughput" | Throughput is bounded by remote capacity, CPU, pools, quotas, queues, and backpressure. |
| "`prefetch` is a byte limit" | The parameter counts **elements**, regardless of object size. |
| "`prefetch` is a rate limit" | It is not elements/second or requests/second. |
| "A `request(1)` at the end always makes upstream receive request 1" | Intermediate operators can reshape requests. |
| "A Publisher returning `Mono` will consume all 32 elements of prefetch" | `Mono` emits at most one element; prefetch impact on inner `Mono`s is typically minor. |
| "Just setting concurrency gives a system-wide limit" | The limit is usually **per subscription** and does not govern logic inside an inner. |
| "Switching `merge` to `concat` only changes output order" | It also changes subscription timing and concurrency level. |
| "Using WebFlux makes every source automatically non-blocking" | Blocking I/O inside a mapper can still stall the event loop. |

## 15. Self-Check Questions

**Question 1.** A `Flux.range(1, 100)` is mapped to 100 API-calling `Mono`s. You use `.flatMap(mapper, 5, 20)`. What value is closest to the number of simultaneously active inners?

**Answer:** At most **5** active inners at a time in this operator. `20` is per-inner prefetch, though each `Mono` emits at most one result; it is not 20 HTTP requests/second.

**Question 2.** With `.concatMap(mapper, 10)`, are ten inners subscribed concurrently?

**Answer:** No. `concatMap` processes inners **sequentially**; `10` is the outer prefetch in this overload.

**Question 3.** Does `flatMapSequential(..., 8, 32)` preserve the order of each outer group? What is the consequence if the first group is very slow?

**Answer:** Yes; however, later groups may already emit elements internally and must be buffered until the first group finishes, increasing latency and memory pressure.

**Question 4.** Why can you not deduce from `concurrency=4` that the entire application has only four HTTP connections?

**Answer:** Because the limit belongs to one operator/subscription; the application may have multiple concurrent subscriptions, an inner may open multiple connections, and the HTTP client's connection pool is managed separately.

**Question 5.** You need to check the exact requests upstream receives after setting prefetch. What should you use?

**Answer:** Attach `doOnRequest` on the right side of the operator, use `StepVerifier`/`BaseSubscriber` to control downstream demand, and watch out for fusion, replenishment optimizations, and Reactor version differences. Do not guess actual requests from a single line of code alone.

**Question 6.** Should you prioritize increasing `concurrency` or `prefetch` when `WebClient` returns a single-element `Mono` per ID and results are slow due to many independent I/O calls waiting long?

**Answer:** Check concurrency capability and connection pool limits first. Very large inner prefetch usually does not help much because a `Mono` emits at most one element; controlled increases in concurrency can help if upstream can handle it.

## 16. Key Takeaways

Three most important ideas:

- **`concurrency` limits how many inner Publishers are subscribed concurrently** on operators that support it. It expresses *overlap* of work, not directly threads or requests/second.
- **`prefetch` is element-based pre-demand at a specific boundary**. With `flatMap`, it typically tunes each inner; with `concatMap`, it tunes the outer. Prefetch keeps the pipeline supplied with data but can increase buffering.
- **Do not tune in isolation from business requirements**: ordering constraints, slow-source latency, element counts per inner, connection pools, cancellation, memory, and backpressure determine which configuration fits.

Start from the `request(n)` contract, identify the operator's **outer/inner** roles, and then use timing tests and resource observation to pick your values.

## Official References

- Project Reactor, **Flux API** (`flatMap`, `flatMapSequential`, `concatMap`, `merge`, `mergeSequential`): https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Flux.html
- Project Reactor, **Reactor Core Reference – Backpressure and Ways to Reshape Requests**: https://projectreactor.io/docs/core/3.6.6/reference/
- Project Reactor, **StepVerifier and Virtual Time**: https://projectreactor.io/docs/core/3.6.6/reference/testing.html
- Project Reactor, **Which Operator Do I Need?**: https://projectreactor.io/docs/core/3.6.6/reference/apdx-operatorChoice.html
- Reactive Streams, **JVM Specification**: https://www.reactive-streams.org/
- Spring Framework, **WebFlux**: https://docs.spring.io/spring-framework/reference/web/webflux.html