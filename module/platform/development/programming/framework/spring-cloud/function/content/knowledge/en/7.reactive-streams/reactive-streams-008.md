# Element Ordering When Using map, flatMap, and concatMap

## 1. The Problem: Receiving A → B → C Yet Emitting B → C → A

Suppose a system receives three order events in the sequence **A, B, C**. Each event goes through a risk-check service:

- A takes 300 ms.
- B takes 100 ms.
- C takes 200 ms.

If processed **sequentially**, the results arrive in A, B, C order. If three asynchronous requests are fired simultaneously, B may finish first, followed by C, and finally A.

In **Spring Cloud Function**, business logic can be packaged using `Supplier`, `Function`, or `Consumer`, looked up via `FunctionCatalog`, chained via composition, and run behind HTTP, event, or serverless adapters. For functions accepting `Flux<T>`, choosing the Reactor operator defines a critical part of the contract: **the order of emitted results and the order in which side effects start**.

Four common operators must be distinguished:

| Operator | Transformation | Concurrent inner tasks | Output order relative to source |
| --- | --- | --- | --- |
| `map` | Synchronous `T -> R` | Spawns no inner publishers | **Preserves** input signal order |
| `flatMap` | `T -> Publisher<R>`, merging inner publishers | Can run concurrently | **No ordering guarantee** |
| `concatMap` | `T -> Publisher<R>`, chaining inner publishers sequentially | At most one inner publisher subscribed at a time | **Preserves** source order and intra-publisher order |
| `flatMapSequential` | `T -> Publisher<R>`, subscribes concurrently yet emits in source order | Can run concurrently | **Preserves emission order**, not necessarily side-effect order |

**Core point:** “Are the outputs in order?” and “Were the business operations executed sequentially?” are **two different questions**.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the ordering semantics of `map`, `flatMap`, `concatMap`, and `flatMapSequential`.
2. Know why `map` is wrong for handling an API returning `Mono<R>` when your goal is `Flux<R>`.
3. Choose the right operator when requirements involve output order, write order, throughput, or latency.
4. Identify the impact of data sources, errors, retries, subscriptions, and external adapters.
5. Write reactive functions reusable across `FunctionCatalog`, composition, HTTP, events, and serverless.
6. Test ordering with `StepVerifier` and virtual time to avoid flaky tests.

## 2. “Preserve Order”—Whose Order?

For a `Flux<T>`, *source order* is the sequence of `onNext` signals seen by the subscription. For example:

~~~java
Flux<String> ids = Flux.just("A", "B", "C");
~~~

This publisher emits A, then B, then C on every normal subscription.

However, if data already passed through a multi-partition queue, an upstream `flatMap`, or a hot source with multiple producers, the `onNext` sequence **may already differ from the real-world event creation order**. Downstream `map` or `concatMap` can only preserve the order **that it actually receives**; it cannot deduce and restore an “original order” from external systems.

Distinguish four kinds of ordering:

| Order type | Question to answer |
| --- | --- |
| **Source** order | Which `T` enters the operator earlier/later? |
| **Start** order | Does the I/O request for A start before B? |
| **Side-effect completion** order | Does write transaction A complete before write transaction B? |
| **Result emission** order | Does the output subscriber receive `R(A)` before `R(B)`? |

`flatMapSequential` can preserve **result emission order** even if B finished its I/O before A. If sending an email, transferring funds, or updating state happens inside the inner publisher, result emission order **does not automatically guarantee side-effect order**.

~~~mermaid
flowchart TB
    IN["Source emits A → B → C"] --> Q{"Choose operator"}
    Q --> MAP["map: synchronous transformation"]
    Q --> FLAT["flatMap: run inner publishers concurrently"]
    Q --> CONCAT["concatMap: chain inner publishers sequentially"]
    Q --> SEQ["flatMapSequential: concurrent, ordered emission"]
    MAP --> O1["A' → B' → C'"]
    FLAT --> O2["Possibly B' → C' → A'"]
    CONCAT --> O3["A' → B' → C'"]
    SEQ --> O4["A' → B' → C'"]
~~~

## 3. map: Transforming Each Element While Preserving Source Order

`map` takes a synchronous transformation function `Function<T,R>`:

~~~java
Flux<String> result = Flux.just(" A ", " B ", " C ")
    .map(String::trim)
    .map(String::toLowerCase);
~~~

The subscriber receives `"a"`, `"b"`, `"c"` in order. `map` callbacks run as `onNext` elements arrive; they do not spawn extra schedulers or run asynchronous I/O.

Example with business types:

~~~java
record OrderEvent(String id, long amountCents) {}
record Decision(String id, boolean accepted) {}

Function<Flux<OrderEvent>, Flux<Decision>> validate = events ->
    events.map(order ->
        new Decision(order.id(), order.amountCents() > 0)
    );
~~~

Given `[A, B, C]`, the output is `[Decision(A), Decision(B), Decision(C)]` in input order, provided transformations succeed and no other upstream/downstream operator alters ordering.

### 3.1. map Does Not Mean Parallel Execution

~~~java
Flux<Integer> values = Flux.range(1, 5)
    .map(value -> expensiveCalculation(value));
~~~

Even if `expensiveCalculation` is CPU-heavy, `map` does not automatically distribute five calculations across five threads. On a sequential source, it runs in step with incoming signals. A slow calculation delays emitting subsequent elements.

**Do not call a blocking API inside `map`** on threads sensitive to blocking:

~~~java
// Unsuitable for blocking I/O on an event loop:
events.map(event -> blockingHttpClient.call(event));
~~~

Prefer a reactive client returning `Mono<R>` and flatten with an appropriate operator. If a blocking library is unavoidable, isolate the work via `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` with bounded concurrency and timeouts.

### 3.2. map Cannot “Fix” Already Reordered Input

~~~java
Flux<String> alreadyReordered = Flux.just("B", "A", "C");
Flux<String> mapped = alreadyReordered.map(String::toLowerCase);
~~~

`mapped` still emits `b, a, c`. If business logic requires ordering by sequence number, retain the sequence key in the payload and build an explicit reordering mechanism.

## 4. flatMap: Multiple Inner Publishers Can Interleave Results

`flatMap` is useful when each element triggers an asynchronous task:

~~~java
Function<String, Mono<String>> lookup = id ->
    remoteClient.lookup(id); // Mono<String>

Flux<String> found = Flux.just("A", "B", "C")
    .flatMap(lookup);
~~~

For asynchronous tasks, `flatMap` can subscribe to additional inner publishers before earlier ones finish. As results arrive, it **merges signals** from inner publishers into the output stream whenever ready.

Therefore:

- A may start before B yet finish after B.
- The subscriber may receive B's result before A's.
- When each inner publisher is a multi-element `Flux<R>`, emissions from different inner publishers can also **interleave**.
- `flatMap` makes no commitment to preserve the original order of `T`.

### 4.1. Fixed-Delay Simulation

The example below simulates processing latencies without needing an HTTP server:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<String> a = Mono.just("A")
    .delayElement(Duration.ofMillis(300));
Mono<String> b = Mono.just("B")
    .delayElement(Duration.ofMillis(100));
Mono<String> c = Mono.just("C")
    .delayElement(Duration.ofMillis(200));

Flux<String> merged = Flux.just(a, b, c)
    .flatMap(inner -> inner);
~~~

If all three inner publishers are subscribed to nearly simultaneously, results arrive in the order **B, C, A**. This example uses varying delays to expose the difference; **it does not mean `flatMap` always scrambles order**. If tasks finish in order or only one inner publisher runs at a time, output can still happen to match source order.

~~~mermaid
sequenceDiagram
    participant F as flatMap
    participant A as Mono(A) 300 ms
    participant B as Mono(B) 100 ms
    participant C as Mono(C) 200 ms
    participant D as Subscriber

    F->>A: subscribe A
    F->>B: subscribe B
    F->>C: subscribe C
    B-->>F: B completes
    F-->>D: onNext(B)
    C-->>F: C completes
    F-->>D: onNext(C)
    A-->>F: A completes
    F-->>D: onNext(A)
~~~

### 4.2. flatMap Does Not Automatically Create Asynchrony

If the mapper returns an immediately completing `Mono.just(...)`, output may often follow source order:

~~~java
Flux<String> result = Flux.just("A", "B", "C")
    .flatMap(id -> Mono.just(id.toLowerCase()));
~~~

That is **not** an ordering guarantee of `flatMap`; it is merely an artifact of synchronous immediate completion in that trivial example.

Once a real client library or scheduler is involved, completion order can shift. Never use a single “output happened to be in order” test to conclude that `flatMap` preserves order.

### 4.3. Concurrency Limits

~~~java
Flux<Decision> decisions = orders.flatMap(
    riskClient::check,
    8
);
~~~

The parameter `8` caps the number of **concurrent active inner publishers at this operator within a single subscription**. It helps control load, yet does not turn `flatMap` into an order-preserving operator. With `concurrency = 1`, inner publishers normally run sequentially, though if explicit sequential ordering is your goal, `concatMap` communicates intent far better.

This number is also not a global cap across multiple pipelines, instances, or the whole cluster.

## 5. concatMap: Finish One Inner Publisher Before Starting the Next

`concatMap` looks structurally similar to `flatMap`:

~~~java
Flux<String> ordered = Flux.just("A", "B", "C")
    .concatMap(id -> remoteClient.lookup(id));
~~~

At the inner-publisher level, however, `concatMap` processes them in source order: **A's inner publisher is subscribed to and processed to completion before moving on to B's**, and then C's.

If all inner publishers succeed and each emits one result, the output order is A, B, C regardless of whether B could complete faster on its own.

### 5.1. Simulating the Same Three Processing Times

~~~java
Flux<String> ordered = Flux.just("A", "B", "C")
    .concatMap(id -> switch (id) {
        case "A" -> Mono.just("A")
            .delayElement(Duration.ofMillis(300));
        case "B" -> Mono.just("B")
            .delayElement(Duration.ofMillis(100));
        default -> Mono.just("C")
            .delayElement(Duration.ofMillis(200));
    });
~~~

Output arrives in the order **A, B, C**. Because the tasks run sequentially in this example, total elapsed time is roughly `300 + 100 + 200 = 600 ms`, excluding scheduling overhead.

Timeline model:

~~~text
0 ms         300 ms     400 ms             600 ms
A: [---------- done]
B:             [--- done]
C:                         [------ done]
Output:       A          B                  C
~~~

Unlike `flatMap`, B is not started early just because it has lower latency. This is the trade-off: better ordering and side-effect control at the cost of lower throughput for independent I/O.

### 5.2. concatMap Preserves Order Even When Each Inner Publisher Emits Multiple Items

~~~java
Flux<String> result = Flux.just("A", "B")
    .concatMap(id -> Flux.just(id + "-1", id + "-2"));
~~~

The output is:

~~~text
A-1, A-2, B-1, B-2
~~~

Both items from publisher A emit before publisher B begins. If you replace `concatMap` with `flatMap` on asynchronous inner publishers, A's and B's results can interleave.

### 5.3. Preserving Emission Order Is Not a Transaction Guarantee

`concatMap` only guarantees sequential subscription/processing of inner publishers. If `repository.save(order)` returns a `Mono<Void>` that completes **only after the write truly succeeds**, `concatMap` helps ensure B does not start writing before A finishes.

However, if an API returns a publisher that completes immediately after **enqueuing a command** while the real transaction runs later in an external system, publisher completion order alone does not guarantee real commit order. Client/repository contracts and transactions remain decisive.

## 6. flatMapSequential: Run Concurrently, Emit in Order

When you want both higher throughput and downstream delivery in source order, Reactor provides `flatMapSequential`:

~~~java
Flux<String> output = Flux.just("A", "B", "C")
    .flatMapSequential(id -> remoteClient.lookup(id), 8);
~~~

This operator subscribes to multiple inner publishers **concurrently**, while buffering results from later publishers if an earlier publisher has not emitted/completed enough to preserve order.

When A is slower than B and C, B and C finish early and **wait for A**. Once A can be emitted in order, the operator drains the buffered results.

| Aspect | `flatMap` | `flatMapSequential` | `concatMap` |
| --- | --- | --- | --- |
| Subscribes to inner publishers concurrently | Yes | Yes | No, processes sequentially |
| Can B's result overtake A? | Yes | No | No |
| Can B's side effect run before A completes? | Yes | **Yes** | No, if A's publisher reflects real completion |
| May buffer results waiting for earlier publisher | May have queue/prefetch | **Yes, to preserve order** | No need to buffer results of earlier inner tasks |
| Risk of slow A stalling B/C output | Lower | **Yes, head-of-line blocking** | Yes, because B/C have not started yet |
| Primary trade-off | Output order | Memory/latency from waiting | Lower concurrency/throughput |

### 6.1. Why Doesn't flatMapSequential Protect Database Write Order?

~~~java
Flux<String> written = Flux.just("A", "B", "C")
    .flatMapSequential(id ->
        repository.write(id)
            .thenReturn(id),
        8
    );
~~~

`written` emits A, B, C. Yet the `repository.write(...)` calls were subscribed concurrently. B may **finish writing before A**, with only B's output signal held back until A completes. Therefore, for strict sequential updates to a single aggregate, `concatMap` is safer to reason about.

### 6.2. Head-of-Line Blocking and Memory

If A takes 30 seconds while B through Z finish in 100 ms, `flatMapSequential` must buffer many results so A is emitted first. That increases memory usage and latency. Bound concurrency/prefetch and configure sensible timeouts on large streams.

When ordering is required **only on output** and side effects may run concurrently, `flatMapSequential` is valuable. When **side effects themselves must be serialized**, use `concatMap`.

## 7. map with Async Functions: The Common Flux<Mono<R>> Mistake

Suppose:

~~~java
interface RiskClient {
    Mono<Decision> check(OrderEvent order);
}
~~~

This line **does not produce `Flux<Decision>`**:

~~~java
Flux<Mono<Decision>> nested =
    orders.map(riskClient::check);
~~~

`map` turns each `OrderEvent` into **a `Mono<Decision>` object**. Each inner `Mono` still needs a subscriber; without flattening, the check work may never run. To get `Flux<Decision>`:

~~~java
// Prioritize throughput, allowing reordered results:
Flux<Decision> fast = orders.flatMap(riskClient::check, 8);

// Process sequentially, preserving order without overlapping tasks:
Flux<Decision> sequential = orders.concatMap(riskClient::check);

// Call concurrently, but emit results in input order:
Flux<Decision> orderedOutput =
    orders.flatMapSequential(riskClient::check, 8);
~~~

Never use `doOnNext(order -> riskClient.check(order))` instead of these operators: `doOnNext` only executes synchronous side effects inside its callback; any returned inner publisher is neither subscribed to nor awaited.

## 8. Complete Spring Cloud Function Example: Three Ways to Inspect Orders

Below is a Java 17+ configuration using `record`. `DecisionClient` is a business API returning `Mono<Decision>`, implemented by an HTTP client or reactive repository in the application.

~~~java
package demo.ordering;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class OrderingFunctions {

    public record OrderEvent(
        String orderId,
        long sequence,
        long amountCents
    ) {}

    public record Decision(
        String orderId,
        long sequence,
        boolean accepted
    ) {}

    public interface DecisionClient {
        Mono<Decision> decide(OrderEvent event);
    }

    // Inline synchronous transformation preserving source order.
    @Bean
    public Function<Flux<OrderEvent>, Flux<OrderEvent>> positiveOrders() {
        return input -> input.filter(event ->
            event.amountCents() > 0
        );
    }

    // Allows multiple concurrent I/O calls, no output order guarantee.
    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> decideFast(
            DecisionClient client) {
        return input -> input.flatMap(client::decide, 8);
    }

    // Each operation completes before the next begins.
    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> decideInOrder(
            DecisionClient client) {
        return input -> input.concatMap(client::decide);
    }

    // Concurrent operations, subscriber receives output in source order.
    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> decideOutputInOrder(
            DecisionClient client) {
        return input -> input.flatMapSequential(client::decide, 8);
    }
}
~~~

### 8.1. Interpreting the Three Choices

Given an input source:

~~~java
Flux<OrderingFunctions.OrderEvent> events = Flux.just(
    new OrderingFunctions.OrderEvent("A", 1, 100),
    new OrderingFunctions.OrderEvent("B", 2, 200),
    new OrderingFunctions.OrderEvent("C", 3, 300)
);
~~~

If the hypothetical service returns B's decision faster than A's:

- `decideFast` can emit `Decision(B)` before `Decision(A)`.
- `decideInOrder` emits A's decision, then B's, then C's; B is processed only after A's publisher finishes.
- `decideOutputInOrder` can finish processing B before A, yet holds B's result to emit it after A's.

For independent decisions with distinct `orderId` keys, out-of-order results may be perfectly acceptable in exchange for higher throughput. For a sequence of updates to the same aggregate ordered by `sequence`, design explicit sequentiality or version checks.

### 8.2. Exposing Functions via FunctionCatalog and Composition

Spring Cloud Function uses `FunctionCatalog` for lookup, type conversion, and composition of function beans. For example, filtering before sequential checking:

~~~properties
spring.cloud.function.definition=positiveOrders|decideInOrder
~~~

Logically, a `Flux<OrderEvent>` passes through `positiveOrders`, and remaining elements flow sequentially into `decideInOrder`. The `filter` operator preserves the order of **surviving elements**; `concatMap` preserves that order in the output.

If higher throughput is required and output order does not matter, the adapter can choose:

~~~properties
spring.cloud.function.definition=positiveOrders|decideFast
~~~

These two configurations are **two independent alternatives**; deploy only the appropriate definition. Defining a composition does not itself create an HTTP endpoint or broker connection: you still need the corresponding adapter, bindings, and environment configuration.

## 9. When Is Preserving Order a Business Requirement?

### 9.1. Cases Where Reordering Is Acceptable

Suppose three orders A, B, C belong to three distinct customers. The risk-check service shares no state across orders and every result carries `orderId`. If downstream correlates results by ID, `flatMap` may fit well.

~~~java
Flux<Decision> decisions = orders.flatMap(
    client::decide, 8
);
~~~

Results can arrive in any order. **Never match results to orders by list index**; always use `orderId` or a correlation ID attached to the result.

### 9.2. Cases Where Side-Effect Order Must Be Preserved

Consider events for **the same e-wallet**:

~~~text
A: add 100
B: subtract 50 if balance is sufficient
C: lock wallet
~~~

If B or C runs concurrently with A, business state outcomes can differ due to state dependencies. Choose `concatMap` within a single pipeline for the same key, or design key-based partitioning with proper ordering/transactions.

Using `concatMap` **on one publisher alone** still does not guarantee system-wide order if the same wallet is processed concurrently across **multiple partitions, subscriptions, or instances**. You need key-based partitioning, concurrency control, and transactional guards at the persistence layer.

### 9.3. Cases Where Only Response Order Matters

A report calling multiple independent APIs may want report rows to stay in the original request order:

~~~java
Flux<ReportLine> lines = requests
    .flatMapSequential(reportService::fetch, 10);
~~~

Requests can execute concurrently, while report lines are emitted in request order. This is sound when `fetch` side effects are independent and memory can tolerate head-of-line buffering.

## 10. How Do Errors, Timeouts, and Retries Affect Ordering?

Any of these operators can emit `onError` when an inner publisher fails. In Reactive Streams, `onError` is a terminal signal: a failed publisher cannot emit further elements in the same subscription without an appropriately scoped recovery construct.

### 10.1. One Element's Error Can Stop the Whole Pipeline

~~~java
Flux<Decision> decisions = orders.concatMap(
    client::decide
);
~~~

If B emits an unhandled error, the output stream can terminate at B; C may never run. The fact that `concatMap` preserves order on success **does not mean it automatically skips failed elements and moves on**.

With `flatMap`, concurrently running inner publishers can also be canceled when an error propagates downstream. Some external operations may already have started or completed before cancellation arrives.

### 10.2. Scoping Error Handling Per Element

If business rules permit recording an “indeterminate” status, handle errors inside each order's inner publisher:

~~~java
enum Status { APPROVED, REJECTED, UNAVAILABLE }

record Result(String orderId, Status status) {}

Function<Flux<OrderEvent>, Flux<Result>> resilient = events ->
    events.concatMap(event ->
        riskService.evaluate(event)
            .timeout(Duration.ofSeconds(2))
            .onErrorResume(error ->
                Mono.just(
                    new Result(event.orderId(), Status.UNAVAILABLE)
                )
            )
    );
~~~

`OrderEvent` and `riskService.evaluate` are hypothetical application types/APIs where `evaluate` returns `Mono<Result>`. `UNAVAILABLE` signals a transient failure, distinct from `REJECTED` representing a business rejection. After emitting the fallback for B, `concatMap` can proceed to C in order.

Never turn an error into “approved” or silently drop events when business rules require complete recording. When errors must trigger retries or dead-lettering, let the error propagate to the appropriate handler.

### 10.3. flatMapDelayError and concatMapDelayError

Reactor includes delay-error variants for certain situations, such as `flatMapDelayError` and `concatMapDelayError`. The general idea is letting other inner publishers keep processing before signaling the terminal error. However:

- Delaying errors **does not mean losing errors**; the end of the stream still emits an error signal to handle.
- `flatMapDelayError` **does not restore output ordering** to `flatMap`.
- `concatMapDelayError` still requires evaluating source, prefetch, and error-emission behavior.
- Delay-error variants do not replace dead-letter queues, idempotency, or transactions.

When you need a result for every order even if some fail, a business result type like `Result(orderId, status, errorCode)` is usually clearer than relying solely on a terminal error signal.

### 10.4. Retries Change Execution Counts

~~~java
Flux<Decision> retried = orders
    .concatMap(event -> client.decide(event).retry(2));
~~~

Retrying **inside** each inner publisher can re-invoke the operation for **the same** event before moving to the next event. With `concatMap`, this remains sequential across inner publishers.

If you place `retry(2)` **on the outside**:

~~~java
Flux<Decision> retriedAll = orders
    .concatMap(client::decide)
    .retry(2);
~~~

a failure makes the system re-subscribe to upstream. With a cold source, A may be processed again. Ordering within each pass may remain intact, yet **repeated side effects** remain a risk. You need idempotency or checkpoints if re-execution causes unwanted effects.

## 11. Backpressure, Prefetch, and Performance Trade-Offs

### 11.1. When Is flatMap Faster?

When inner publishers are genuinely asynchronous and independent, `flatMap` exploits I/O wait time: while waiting on A, B and C can run. If tasks are completely synchronous or CPU-bound on a single thread, `flatMap` does not create extra parallel capacity.

Also avoid setting concurrency too high. It can exhaust sockets, requests, connections, or temporary memory. Appropriate bounds depend on real load, pools, and target service quotas.

### 11.2. concatMap Reduces Overlap at the Cost of Latency

`concatMap` makes ordering and “finish A before starting B” easy to reason about, yet a very slow A stalls everything behind it. In continuous event ingestion, if the source outpaces sequential processing, add backpressure or a durable queue at the ingestion boundary.

### 11.3. flatMapSequential Incurs Buffering Cost

To emit results in order, `flatMapSequential` may hold early-finishing results while waiting on the leading publisher. When inner publishers emit many elements or A stalls for a long time, buffered memory can grow noticeably.

| Goal | Usually appropriate choice | Main trade-off |
| --- | --- | --- |
| In-place value transformation | `map` | Cannot be used for publisher-returning tasks |
| Independent I/O, prioritize throughput | `flatMap(..., concurrency)` | Output order may change |
| Must serialize side effects | `concatMap` | Fewer concurrent tasks |
| Independent I/O, source-ordered output | `flatMapSequential(..., concurrency)` | Buffering and head-of-line blocking |
| Parallel CPU work | Dedicated scheduler/partition design | Requires resource management; plain `flatMap` is insufficient |
| Per-key ordered orders, many keys in parallel | Partition by key and process each key sequentially | Must avoid unbounded group count and state explosion |

Backpressure regulates **consumption demand**, whereas concurrency bounds **inner tasks**. Even with concurrency set to 8, an external broker will not necessarily slow down to match demand if the adapter cannot propagate Reactive Streams signals back to the source.

## 12. Preserving Order Per Key Instead of Across the Whole Stream

A system with thousands of customers might require:

- **Within the same `customerId`:** process A, then B, then C.
- **Across different customers:** allow parallel processing to boost throughput.

This is a **per-key** ordering requirement; there is no need to serialize the entire event stream. Reactor has `groupBy` to split a stream into keyed groups, allowing `concatMap` within each group:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> byCustomer =
    input -> input
        .groupBy(OrderEvent::customerId)
        .flatMap(group ->
            group.concatMap(client::decide),
            8
        );
~~~

This is a **design sketch**: `OrderEvent` needs `customerId()`, and `client.decide` returns `Mono<Decision>`. It shows elements within **a subscribed group** processed sequentially, while results across different groups can interleave.

**Be very cautious with `groupBy` in production:** a large key space or unconsumed groups can cause large queues or pipeline stalls, especially when `flatMap` limits how many groups are subscribed concurrently. With high-cardinality keys, fixed broker/consumer partitions or keyed worker queues are usually much easier to control.

An in-process `groupBy` also **does not prevent the same key from being processed concurrently on another instance**. When strict system-wide ordering is required, ensure routing and key ownership across nodes.

## 13. Message<T>, Correlation IDs, and Mismatching Risks

Whenever output order can change, carry a **correlation key** alongside each element. Example:

~~~java
Function<
    Flux<org.springframework.messaging.Message<OrderEvent>>,
    Flux<org.springframework.messaging.Message<Decision>>
> decisionsWithHeaders = messages ->
    messages.flatMap(message ->
        client.decide(message.getPayload())
            .map(decision ->
                org.springframework.messaging.support.MessageBuilder
                    .withPayload(decision)
                    .copyHeaders(message.getHeaders())
                    .build()
            ),
        8
    );
~~~

Each inner publisher retains a reference to **its corresponding input message** via closure, so even if a result arrives late it still carries the right event's metadata. Some system headers like ID/timestamp may be regenerated; binders may also convert or filter headers across transports. Explicitly identify mandatory business headers such as `eventId` or `correlationId`.

### 13.1. Never Correlate by Positional Index

Dangerous mistake:

~~~java
List<OrderEvent> inputs = ...;
List<Decision> outputs = ...; // Collected from unordered flatMap

// Wrong to assume outputs[i] always corresponds to inputs[i].
~~~

With `flatMap`, output position is not a stable correlation key. Use `orderId`, `eventId`, or a correlation ID. If output strictly must match input order, consider `flatMapSequential` within the publisher scope and evaluate its buffering cost.

### 13.2. Reactor Output Order Is Not Broker Arrival Order

Even when a function uses `concatMap`, the adapter sending messages to a broker may involve multiple connections, partitions, retries, or workers. The order **a Reactor subscriber sees** and the order **a consumer in another system sees** do not necessarily match.

For end-to-end guarantees, verify routing keys, partitioning, producer/consumer settings, retries, and ordering configuration in your concrete binder. Never treat Reactor operator ordering as a substitute for transport delivery contracts.

## 14. Finite Streams, Continuous Streams, and Ordering Impact

### 14.1. Finite Sources

A `Flux.just(...)` usually emits in deterministic order and completes. With finite sources, `StepVerifier` can verify the entire output. If you genuinely must **re-sort by sequence number** after unordered processing, you can use `sort`:

~~~java
Flux<OrderEvent> sorted = events
    .sort(java.util.Comparator.comparingLong(OrderEvent::sequence));
~~~

`sort` must **wait for the entire upstream to complete** and buffer items to sort them. This suits bounded finite batches of manageable size, and **is unsuitable for sorting an infinite stream**.

### 14.2. Long-Lived Streams

With continuous event streams, you rarely have an “entire” list to sort. When sequence-ordered processing is required, consider mechanisms such as:

- Partitioning by key and preserving order per partition.
- Checking `sequence`/version in the database to reject stale updates.
- Bounded buffered windows with expiration rules for missing events.
- Durable queues to recover late or out-of-order events.

The right choice depends on your goal: output order in a single subscription, side-effect order for one aggregate, or durable ordering across systems.

### 14.3. A Flux Signature Does Not Change Function Invocation Count

In Spring Cloud Function, `Function<Flux<T>, Flux<R>>` may have `apply(flux)` called once to construct a long-lived pipeline. Once subscribed, `map`/`flatMap`/`concatMap` callbacks run per element. Do not mistake each `onNext` for the framework re-invoking the outer function lambda.

Conversely, in an imperative per-message `Function<T,R>` model, the adapter may call `apply(t)` once per message. The two models have different invocation boundaries; application-level ordering must align with the adapter's actual boundary.

## 15. Testing Ordering with StepVerifier and Virtual Time

A test that merely runs `flatMap` over immediately completing `Mono.just` instances and observes in-order results **does not prove** the operator guarantees ordering. Introduce differing latencies intentionally.

Complete test example below using JUnit 5, `reactor-test`, and Java 17+:

~~~java
package demo.ordering;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OperatorOrderingTest {

    private static Mono<String> delayed(String id) {
        Duration delay = switch (id) {
            case "A" -> Duration.ofMillis(300);
            case "B" -> Duration.ofMillis(100);
            default -> Duration.ofMillis(200);
        };
        return Mono.just(id).delayElement(delay);
    }

    @Test
    void mapKeepsInputOrder() {
        StepVerifier.create(
                Flux.just("A", "B", "C")
                    .map(String::toLowerCase)
            )
            .expectNext("a", "b", "c")
            .verifyComplete();
    }

    @Test
    void flatMapMayEmitByCompletionTime() {
        StepVerifier.withVirtualTime(
                () -> Flux.just("A", "B", "C")
                    .flatMap(OperatorOrderingTest::delayed)
            )
            .thenAwait(Duration.ofMillis(650))
            .expectNext("B", "C", "A")
            .verifyComplete();
    }

    @Test
    void concatMapEmitsInSourceOrder() {
        StepVerifier.withVirtualTime(
                () -> Flux.just("A", "B", "C")
                    .concatMap(OperatorOrderingTest::delayed)
            )
            .thenAwait(Duration.ofMillis(650))
            .expectNext("A", "B", "C")
            .verifyComplete();
    }

    @Test
    void flatMapSequentialEmitsInSourceOrder() {
        StepVerifier.withVirtualTime(
                () -> Flux.just("A", "B", "C")
                    .flatMapSequential(
                        OperatorOrderingTest::delayed,
                        3
                    )
            )
            .thenAwait(Duration.ofMillis(650))
            .expectNext("A", "B", "C")
            .verifyComplete();
    }
}
~~~

Here `StepVerifier.withVirtualTime` replaces Reactor's time scheduler with a virtual clock when the publisher is created **inside the factory**. That avoids waiting 650 ms in wall-clock time.

Expectations reflect the timing model:

- `flatMap` subscribes to all three inner publishers almost simultaneously; B emits after 100 ms, C after 200 ms, A after 300 ms.
- `concatMap` waits 300 ms for A, then 100 ms for B, then 200 ms for C; after roughly 600 ms it has emitted A, B, C.
- `flatMapSequential` lets B/C finish early yet emits in A, B, C order as the buffer drains.

**Note:** This tests deterministic publishers using a virtual time scheduler. It does not exercise network failures, real I/O client threads, or broker message ordering.

### 15.1. Verifying Side-Effect Ordering with Counters

When non-overlapping writes are a key requirement, check **how many inner publishers are active at once**, not just the final output list.

~~~java
AtomicInteger active = new AtomicInteger();
AtomicInteger maxActive = new AtomicInteger();

Flux<String> pipeline = Flux.just("A", "B", "C")
    .concatMap(id ->
        Mono.defer(() -> {
            int current = active.incrementAndGet();
            maxActive.accumulateAndGet(current, Math::max);

            return Mono.just(id)
                .delayElement(Duration.ofMillis(10))
                .doOnTerminate(() -> active.decrementAndGet());
        })
    );
~~~

When subscribed and awaited to completion, `maxActive` is expected not to exceed 1. In this example, the counter decrements on the inner publisher's terminal signal, matching when `concatMap` transitions to the next inner task. Even so, checking publisher concurrency **does not by itself verify transaction commits in external services**.

### 15.2. Avoid Tests Dependent on Thread.sleep

~~~java
// Avoid in ordering unit tests:
Thread.sleep(200);
assertEquals(...);
~~~

Tests relying on real wall-clock timing are prone to flakiness under heavy CI load. For Reactor timers, `withVirtualTime` is ideal. When testing real I/O or brokers, use integration tests with finite timeouts, identifiable test data, and explicit wait conditions rather than assuming a specific thread-scheduling speed or order.

## 16. Common Design Pitfalls and Fixes

| Symptom | Common cause | Remedy |
| --- | --- | --- |
| Input A, B, C yields B, C, A | `flatMap` interleaves asynchronous results | Use `concatMap` or `flatMapSequential` as required |
| Used `flatMapSequential` yet DB still writes B before A | Inner operations run concurrently | Use `concatMap` when side-effect order is required |
| Output type is `Flux<Mono<R>>` | Used `map` with a `Mono<R>`-returning API | Flatten with an appropriate operator |
| `concatMap` is too slow | Independent I/O operations run sequentially | Consider concurrency-bounded `flatMap` if reordering is allowed |
| `flatMapSequential` spikes memory | B/C results wait on slow A | Bound concurrency, add timeouts, and monitor buffers |
| Used `map` yet results appear “out of original order” | Upstream emitted out of business order | Carry sequence/correlation IDs; fix the source or reorder explicitly |
| Duplicate writes on retry | Subscription or side effects re-executed | Use idempotency, transactions, and checkpoints |
| Order holds in unit tests but breaks via broker | Adapter/partition/retry alters delivery path | Add integration tests at the transport boundary |
| Error on B prevents C from running | Inner publisher error terminates the subscription | Choose fail-fast or per-element error handling |
| `map` stalls the event loop | Callback contains blocking operations | Use reactive clients or isolate blocking work on an appropriate scheduler |
| Only per-customer order needed, yet entire stream serialized | Applied `concatMap` across all keys | Partition by key with bounded resources |
| Stalls when using `groupBy` with many keys | Too many unsubscribed/unconsumed groups | Use bounded partitions or design proper group management |

## 17. Practical Operator Selection Rules

~~~mermaid
flowchart TD
    START["Each element must be processed"] --> ASYNC{"Does mapper return Publisher<R>?"}
    ASYNC -->|No, returns synchronous R| MAP["map"]
    ASYNC -->|Yes| ORDER{"Need to preserve side-effect order?"}
    ORDER -->|Yes| CONCAT["concatMap"]
    ORDER -->|No| OUT{"Need output in source order?"}
    OUT -->|Yes| SEQ["flatMapSequential\n+ concurrency limit"]
    OUT -->|No| FLAT["flatMap\n+ concurrency limit"]
    MAP --> TEST["Verify source,\nerrors, and adapter"]
    CONCAT --> TEST
    SEQ --> TEST
    FLAT --> TEST
~~~

Before choosing, ask concrete questions:

1. Is the input actually ordered, and is there a sequence/key to verify against?
2. Is the transformation synchronous, or does it return `Mono`/`Flux`?
3. Is **result emission** order critical, or is **external side-effect** order critical?
4. Can independent keys be processed in parallel?
5. Can an inner publisher emit multiple results, fail, or never complete?
6. How many tasks may run concurrently, and is head-of-line blocking a risk?
7. Will retries or resubscriptions repeat side effects?
8. Across HTTP, binders, or serverless, does the adapter preserve the required ordering contract?

## 18. Self-Assessment Questions

1. Why does `Flux.just("A","B","C").map(...)` preserve the source's emission order?
2. If three API requests take 300, 100, and 200 ms respectively, in what order can `flatMap` emit results?
3. Does `flatMap` always change output order? Why should you never rely on accidental in-order results?
4. How does `concatMap` differ from `flatMapSequential` regarding **when inner operations start**?
5. Why can `flatMapSequential` emit outputs A, B, C in order while write B still commits before write A?
6. What is the return type of `orders.map(client::check)` if `check` returns `Mono<Decision>`?
7. When should you choose `flatMap(..., 8)`, and does `8` limit total requests across the whole cluster?
8. Why can a downstream `concatMap` fail to restore event order if the source already emitted B before A?
9. If an inner publisher errors, how does placing `onErrorResume` inside the inner publisher differ from placing it outside the entire stream?
10. Why can `retry` repeat side effects even when result ordering stays correct?
11. When serving many customers where order only matters per customer, how should concurrency be structured?
12. How does `StepVerifier.withVirtualTime` help verify the difference among the three operators?
13. Can you rely on Reactor operator ordering to claim Kafka or RabbitMQ will deliver messages in order end-to-end?
14. If one inner publisher never completes, how are `concatMap` and `flatMapSequential` affected?

## 19. References

- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/) — `map`, `flatMap`, `concatMap`, `flatMapSequential`, subscriptions, and backpressure.
- [Project Reactor Test Reference](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier`, `withVirtualTime`, and asserting signal order.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — imperative/reactive functions and the `Function<Flux<T>, Flux<R>>` contract.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — functions over binders and message processing boundaries.

Java examples use Java 17+ with Reactor and Spring Cloud Function. Subscription, retry, and transport ordering behaviors must be verified against your deployed framework and binder versions.

**Key takeaway:** `map` preserves source signal order for synchronous value transformations; `flatMap` merges inner publishers and can emit in completion order; `concatMap` subscribes to and processes inner publishers sequentially to preserve order and avoid overlapping tasks; `flatMapSequential` runs concurrently while preserving **result emission** order, without guaranteeing **side-effect** order. When deploying Spring Cloud Function over HTTP, events, or serverless, identify clearly where order must be protected, pick the matching operator, and verify both the publisher and the adapter.
