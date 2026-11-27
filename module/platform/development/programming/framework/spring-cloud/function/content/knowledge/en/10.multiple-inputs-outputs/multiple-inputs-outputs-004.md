# Combining Multiple Inputs and Synchronizing Data

## 1. The problem: multiple sources emitting events at their own pace

In **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), business logic can be packaged as a `Supplier`, `Function`, or `Consumer` and registered in Spring. `FunctionCatalog` helps discover and normalize functions, supporting composition and message conversion; an appropriate adapter can invoke the logic via HTTP, event systems, or serverless environments.

When a system has only one input stream, we typically use `Function<Flux<A>, Flux<B>>`. For workflows such as **order and payment reconciliation**, however, data arrives from **two independent sources**:

- `orders.created` emits `OrderCreated` after an order is placed.
- `payments.confirmed` emits `PaymentConfirmed` after a payment transaction is confirmed.

A payment can arrive before or after the order creation message, one source may run faster than the other, and either source may emit duplicate or missing messages. Therefore, **combining multiple inputs** must answer not only "how many ports are there?", but also **"which records should be paired, when should results be emitted, and how long should we wait?"**.

~~~text
orders.created ────────> [ input 0 ] ┐
                                    ├── reconcileOrders ──> [ output 0 ] ──> orders.reconciled
payments.confirmed ────> [ input 1 ] ┘
                           |
              Matching rule by orderId
              and allowed time window
~~~

**Learning objectives:**

1. Correctly interpret multi-input functions using `Tuple2<Flux<...>, Flux<...>>`.
2. Choose among `merge`, `zip`, `combineLatest`, `concat`, and `join`.
3. Understand the differences between **synchronizing by order**, **latest value**, **business key**, and **time**.
4. Write a reactive function that combines orders and payments, mapping input bindings via Spring Cloud Stream.
5. Recognize scenarios involving late data, duplicates, unmatched records, or the need for durable state storage.

## 2. Representing two independent sources with Reactor Tuples

Spring Cloud Function supports *function arity* for reactive functions, using `TupleN` from **Project Reactor** to describe both the port count and each port's data type. For example:

~~~java
Function<
    Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
    Flux<Reconciliation>
>
~~~

This signature has **2 input ports and 1 output port**:

| Element | Data type | Meaning |
| --- | --- | --- |
| `input.getT1()` | `Flux<OrderCreated>` | Order creation stream, input 0 |
| `input.getT2()` | `Flux<PaymentConfirmed>` | Payment confirmation stream, input 1 |
| Return value | `Flux<Reconciliation>` | Reconciliation result, output 0 |

Although `Function.apply(...)` takes only **one Java object** (`Tuple2`), that object holds **two publishers** that an adapter can connect to two independent event sources.

**Distinguish two ways of using tuples:**

~~~java
// Two independent streams -> multi-input port model.
Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>> sources;

// One stream of already-paired items -> one output port.
Flux<Tuple2<OrderCreated, PaymentConfirmed>> pairs;
~~~

`Tuple2<Flux<A>, Flux<B>>` **does not automatically pair** `A` and `B` records together. It merely holds two streams. The combining rule must be decided by Reactor operators inside the function body.

Spring Cloud Function's multi-port arity support focuses on **reactive functions**; writing an imperative `Function<A, Tuple2<B, C>>` does not automatically create two output bindings. Mapping ports to topics/queues is the responsibility of an adapter, typically **Spring Cloud Stream**, rather than something `Tuple2` creates by itself.

## 3. "Data synchronization" can mean several things

Two streams emitting records does not mean adjacent records belong to the same business transaction. Before choosing an operator, distinguish among these options:

| Combining method | Pairing rule | When is output emitted? | Suitable use case |
| --- | --- | --- | --- |
| `Flux.merge(a, b)` | No pairing; interleaves items from two sources into one stream | Whenever either source emits an item | Aggregating events onto a shared channel |
| `Flux.concat(a, b)` | No pairing; processes `a` completely before `b` | In declared source order | Concatenating **finite** sources sequentially |
| `Flux.zip(a, b)` | Pairs the **i-th item** of `a` with the i-th item of `b` | Once both sources have produced an item at that position | Two sources guaranteed to be aligned by position |
| `Flux.combineLatest(a, b, fn)` | Uses the **latest value** from each source | After both have emitted at least once, whenever either source updates | Combining latest state, configuration, or metrics |
| `a.join(b, leftEnd, rightEnd, fn)` | Pairs items **whose active windows overlap** | When a pair falls within overlapping windows | Correlating events within a time span |

None of the operators in this table natively understands `orderId` across orders and payments. The **business key** must be checked in your logic. If consistency must survive crashes, restarts, and hours of delay, pure in-memory reactive joining may not be sufficient.

### 3.1. Positional combining: `zip`

Suppose two sources are already aligned so that items at the same position represent the same measurement:

~~~java
Flux<String> stations = Flux.just("HN", "HCM", "DN");
Flux<Integer> readings = Flux.just(28, 32, 30);

Flux<String> reports = Flux.zip(
        stations,
        readings,
        (station, temperature) -> station + "=" + temperature);

// Output data: "HN=28", "HCM=32", "DN=30".
~~~

`zip` waits for both sources to produce an item at a given position before emitting a result. If one source emits slowly, the next position's output must wait for that source. When no further pairs can be formed because one source has completed, `zip` terminates; leftover items from the other source do not produce outputs.

However, **emission order is not a business key**. For example:

~~~text
orders:   O-101, O-102
payments: O-102, O-101

zip by position:
          (O-101, O-102)  <- wrong orderId
          (O-102, O-101)  <- wrong orderId
~~~

Therefore, do not use `zip` to reconcile orders by `orderId` if the two sources can arrive out of order, miss messages, or contain duplicates.

### 3.2. Latest-state combining: `combineLatest`

A monitoring system has a temperature stream and a dynamically changing alert-threshold stream. The business logic needs to compare the **latest temperature** with the **latest threshold**, rather than pairing one-to-one by position:

~~~java
Flux<Double> temperatures = Flux.just(28.0, 29.0);
Flux<Double> thresholds = Flux.just(30.0, 27.0);

Flux<String> alerts = Flux.combineLatest(
        temperatures,
        thresholds,
        (temperature, threshold) ->
                temperature >= threshold ? "ALERT" : "NORMAL");
~~~

This operator starts emitting only after **each source has emitted at least one value**. Thereafter, whenever one source updates, it combines with the most recent value observed from the other source. A value can participate in **multiple results**, and intermediate values may not all be used if a source emits rapidly.

`combineLatest` is suitable for combining state; it **does not match a payment to its corresponding order**. Pairing sources by latest snapshot can produce mismatched pairs whenever multiple order IDs interleave.

### 3.3. Simply merging events: `merge`

~~~java
Flux<String> allEvents = Flux.merge(
        orders.map(order -> "ORDER:" + order.id()),
        payments.map(payment -> "PAYMENT:" + payment.orderId()));
~~~

`merge` emits items from both sources onto a single stream **without** pairing them and without guaranteeing global order between the two sources. If key-based processing is needed after merging, you must implement a stateful processing step or use an appropriate stream-processing tool.

`concat` also joins data into one stream, but only subscribes to the next source after the preceding source completes. Thus `concat` is unsuitable for combining two continuously emitting topics that **never complete**: the second source might never be subscribed to.

## 4. Key-based and time-windowed reconciliation

Suppose each order has:

~~~text
OrderCreated(id, totalVnd)
~~~

and each payment has:

~~~text
PaymentConfirmed(orderId, paidVnd)
~~~

We want to emit a `Reconciliation` when **an order and a payment with the same ID** are observed within a **maximum correlation window of 30 seconds**.

Two conditions must be considered independently:

1. **Key:** `order.id()` must equal `payment.orderId()`.
2. **Time:** both events must arrive within the allowed span so they coexist in the join window.

~~~text
Event arrival time (illustrative)

orders:    O-101 ───────────────── O-102 ───────────>
           |<--------- 30s ------->|

payments:       P(O-101) ───────────────── P(O-102) ─>

Result: O-101 can be paired while the window is still open.
        O-102 is only paired if payment arrives in time.
~~~

In Reactor, `Flux.join(...)` creates pairs when the **active windows of two items overlap**. Each window is closed by a programmatically specified publisher. When using `Mono.delay(Duration.ofSeconds(30))`, the duration is measured by the wall clock/scheduler at pipeline execution time, **not automatically inferred from a business timestamp in the payload**.

## 5. Complete example: two inputs, one result stream

This example uses **Java 17+** with `record`, Spring Cloud Function, and Project Reactor. The data types are declared inside the configuration class so it can run standalone inside a Spring Boot application with the appropriate dependencies configured.

~~~java
import java.time.Duration;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.function.Tuple2;

@Configuration
public class ReconcileConfiguration {

    public record OrderCreated(String id, long totalVnd) {}

    public record PaymentConfirmed(String orderId, long paidVnd) {}

    public record Reconciliation(
            String orderId,
            long totalVnd,
            long paidVnd,
            boolean amountMatches) {}

    private record Candidate(
            OrderCreated order,
            PaymentConfirmed payment) {}

    @Bean
    public Function<
            Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
            Flux<Reconciliation>> reconcileOrders() {

        return sources -> {
            Flux<OrderCreated> orders = sources.getT1();
            Flux<PaymentConfirmed> payments = sources.getT2();

            return orders
                    .join(
                            payments,
                            // How long each order is held waiting for a payment.
                            order -> Mono.delay(Duration.ofSeconds(30)),
                            // How long each payment is held waiting for an order.
                            payment -> Mono.delay(Duration.ofSeconds(30)),
                            Candidate::new)
                    // join pairs every pair with overlapping windows;
                    // keep only pairs with the same business key.
                    .filter(candidate -> candidate.order().id()
                            .equals(candidate.payment().orderId()))
                    .map(candidate -> {
                        OrderCreated order = candidate.order();
                        PaymentConfirmed payment = candidate.payment();

                        return new Reconciliation(
                                order.id(),
                                order.totalVnd(),
                                payment.paidVnd(),
                                order.totalVnd() == payment.paidVnd());
                    });
        };
    }
}
~~~

**Explanation:**

1. `sources.getT1()` is the order creation stream; `sources.getT2()` is the payment stream.
2. `join` observes both sources and emits candidate pairs whenever their windows overlap.
3. `Candidate::new` holds references to one order and one payment.
4. `filter` checks for a **matching `orderId`**, discarding pairs that only overlapped in time with different IDs.
5. `map` builds the result, distinguishing between **a pair being found** and **whether the amounts match**.

Sample input:

| Source | Message | Amount |
| --- | --- | ---: |
| Order | `OrderCreated("O-101", 500000)` | 500,000 |
| Order | `OrderCreated("O-102", 900000)` | 900,000 |
| Payment | `PaymentConfirmed("O-102", 900000)` | 900,000 |
| Payment | `PaymentConfirmed("O-101", 450000)` | 450,000 |

If the events arrive within overlapping windows:

- Result `O-101`: `amountMatches = false`.
- Result `O-102`: `amountMatches = true`.

Even though payment `O-102` arrived **before** payment `O-101`, the two records are still reconciled by **business key**, not by position in each source.

### Limitations of this example

This is an **educational model for combining two streams in memory**:

- Windows using `Mono.delay` measure **processing time**, not *event time* extracted from a timestamp field in the data.
- `join` can produce **multiple pairs** if multiple events with the same key appear within overlapping windows (for example, a retried payment). Filtering by key does not automatically deduplicate records.
- `join` first considers all pairs with overlapping windows and only then filters by key; under high throughput and large numbers of retained records, candidate pair counts and compute overhead can grow significantly.
- No output is produced for orders whose payment never arrives or arrives too late: **emitting no result** differs from actively emitting a `TIMEOUT` result.
- Window state lives in-process. Application restarts, subscription cancellations, or pipeline errors can lose pending correlations.

In production systems, you must define timeout policies, late-arrival handling, idempotency, state durability, and compensation responsibilities. When strong guarantees are needed, use a stream processor with **state stores, windowing, and recovery**, or persist state keyed by `orderId` in a database with consistent update rules.

## 6. Mapping two input ports with Spring Cloud Stream

Spring Cloud Stream is a common adapter for connecting reactive functions to messaging systems. For the `reconcileOrders` bean, the default binding names are:

| Binding | Source or destination | Logical data type |
| --- | --- | --- |
| `reconcileOrders-in-0` | `orders.created` | `OrderCreated` |
| `reconcileOrders-in-1` | `payments.confirmed` | `PaymentConfirmed` |
| `reconcileOrders-out-0` | `orders.reconciled` | `Reconciliation` |

`application.yml` configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: reconcileOrders
    stream:
      bindings:
        reconcileOrders-in-0:
          destination: orders.created
          content-type: application/json
        reconcileOrders-in-1:
          destination: payments.confirmed
          content-type: application/json
        reconcileOrders-out-0:
          destination: orders.reconciled
          content-type: application/json
~~~

**How to read binding names:** `-in-0` corresponds to `getT1()`, `-in-1` corresponds to `getT2()`, and `-out-0` is the returned `Flux<Reconciliation>` stream. The bean name in `definition` must match the registered bean.

This configuration requires the **Spring Cloud Stream** dependency and a corresponding binder (Kafka, RabbitMQ, or another supported system), alongside Spring Cloud Function/Reactor. A `Function` bean does not create brokers or topics on its own. Depending on the binder, you must configure connectivity, serializers/content types, permissions, and error-handling mechanisms for your deployment environment.

### Message types and metadata

Each port has its own payload type, so JSON conversion must produce the corresponding Java type. For instance, a JSON payload sent to `reconcileOrders-in-1` must have fields matching `PaymentConfirmed`, not the `OrderCreated` structure.

If headers such as `correlationId`, source event timestamp, or trace ID are needed, explicitly design how to preserve them when transforming inputs into results. Input message headers are **not automatically** preserved in every function output; you can use `Message<T>` and selectively copy headers as required.

## 7. Testing data synchronization and heterogeneous ordering

Because the business logic lives inside a functional bean, we can test it **without starting a broker**. Example with JUnit 5 and `reactor-test`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Comparator;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.util.function.Tuples;

class ReconcileConfigurationTest {

    @Test
    void matchesByOrderIdEvenWhenPaymentsArriveInReverseOrder() {
        var config = new ReconcileConfiguration();

        var orders = Flux.just(
                new ReconcileConfiguration.OrderCreated("O-101", 500_000L),
                new ReconcileConfiguration.OrderCreated("O-102", 900_000L));

        var payments = Flux.just(
                new ReconcileConfiguration.PaymentConfirmed("O-102", 900_000L),
                new ReconcileConfiguration.PaymentConfirmed("O-101", 450_000L));

        var result = config.reconcileOrders()
                .apply(Tuples.of(orders, payments))
                // The example has exactly two valid pairs: complete right after two results.
                .take(2)
                .sort(Comparator.comparing(
                        ReconcileConfiguration.Reconciliation::orderId));

        StepVerifier.create(result)
                .expectNext(
                        new ReconcileConfiguration.Reconciliation(
                                "O-101", 500_000L, 450_000L, false),
                        new ReconcileConfiguration.Reconciliation(
                                "O-102", 900_000L, 900_000L, true))
                .verifyComplete();
    }
}
~~~

`take(2)` is used to verify **the two expected pairs over finite sources** and cancel the pipeline once two results arrive, avoiding waiting for the 30-second windows to expire. `sort` allows verifying results independently of the order in which `join` emits pairs; `join` does not guarantee emission order when multiple pairs overlap.

In a comprehensive test suite, include the following scenarios:

| Scenario | What to verify |
| --- | --- |
| Payment arrives before order | Still pairs properly if within the window |
| Sources run at different speeds | Pipeline does not assume item `i` of both sources belongs to the same transaction |
| Payment arrives after window closes | Does not pair; separate timeout/compensation mechanism works as designed |
| Duplicate payment or order | Results are not recorded twice thanks to idempotency policy |
| Invalid or missing `orderId` | No valid reconciliation emitted; error-recording policy applies |
| One source stops or emits an error | Defines how waiting, retry, cancellation, or subscription recovery behaves |
| Multiple overlapping order IDs | Only same-key pairs match, no cross-matching |

For time-dependent scenarios, use Reactor's **virtual time** in tests and control event emission timings explicitly. Avoid testing with `Thread.sleep(...)` because it is slow and flaky.

## 8. Synchronizing by processing time vs. event time

Two interpretations of time lead to very different behaviors:

**Processing time:** the moment the application receives or executes the operator. `Mono.delay(Duration.ofSeconds(30))` in the example uses this type of time. If a payment is created at 10:00 but reaches the application at 10:05, the window is still measured from when the pipeline observes the event.

**Event time:** the business timestamp recorded in the payload or metadata at the source. If the system must pair transactions whose business timestamps are at most 30 seconds apart, you must compare timestamps and handle *out-of-order* events, *watermarks*, lateness bounds, and windowing policies.

~~~text
Source A creates O-101 at 10:00:00 ──────> app receives at 10:00:01
Source B creates P-101 at 10:00:20 ──────> app receives at 10:05:00

Event time difference:      20 seconds
Processing time difference: nearly 5 minutes
~~~

This case would count as "within the same 30-second window" by event time, yet **falls outside** the 30-second processing-time window of `join` using `Mono.delay`. Reactor's `join` does not automatically provide watermarks or durable state stores. If the requirement is event-time processing and late data handling on continuous topics, consider windowed joins in Kafka Streams/a suitable stream processor, or persist time-bounded state by key in a database.

## 9. Operational limits when joining multiple streams

### 9.1. Pending state and memory limits

Every event can remain in a window for a period of time. At high event rates, buffering records while waiting for their counterparts consumes memory. You must decide:

- How long can a window stay open at most, and how many records can wait concurrently?
- How many records should be kept per key?
- After a timeout, is the record discarded, routed to an error stream, or persisted for investigation?
- During sudden traffic spikes, how does the system bound memory and apply backpressure?

Do not use `collectList()`, unbounded `cache()`, or a `Map` that stores every event forever on a continuous stream. These approaches can cause unbounded memory growth without lifecycle and TTL management.

### 9.2. Message duplicates and idempotency

Many messaging systems provide **at-least-once** delivery, so the same message can be redelivered. With two sources, redelivery can cause one order to match multiple payments or vice versa. Use an event ID/transaction ID and deduplication policies or unique constraints where results are persisted; do not treat `filter` by `orderId` as sufficient.

### 9.3. Error on one branch and subscription lifecycle

`join` subscribes to both sources to observe events concurrently. An unhandled error from either source can terminate the entire pipeline; define a retry or error-handling strategy across the adapter/binder and Reactor logic. With reactive functions, error handling occurs within the publisher chain and may differ from per-invocation retry of an imperative function.

### 9.4. Ordering, backpressure, and scaling

Do not assume **global ordering** across partitions, topics, or message producers. When scaling out to multiple instances, two events with the same key may land on **two different instances**, preventing an in-memory join from finding the match. Designing partition keys/affinity or using shared/durable state storage is part of the solution.

Backpressure helps subscribers regulate flow rate within the reactive pipeline, but it does not by itself provide durable storage, distributed state, or protection against message loss during broker/instance failures.

## 10. Choosing a solution based on business requirements

| Requirement | Reference approach |
| --- | --- |
| Merge multiple events into one feed without pairing | `merge` |
| Concatenate two finite sources, preserving first source then second | `concat` |
| Pair items by position when both sources are aligned | `zip` |
| Track results computed from the latest values of multiple sources | `combineLatest` |
| Pair events with overlapping time windows | `join`, combined with key checks if needed |
| Pair by `orderId` with timeouts, retries, duplicates, late data, and state recovery | Stream processor/state store or database with an explicit reconciliation strategy |

With Spring Cloud Function, the choice above lives inside the **function body**; the `Function<Tuple2<Flux<A>, Flux<B>>, Flux<R>>` signature preserves the **2 inputs → 1 output** contract. `FunctionCatalog` and adapters handle registration, lookup, message conversion, and wiring sources. Composition via `|` is **sequential function chaining**, not an automatic mechanism to synchronize two independent sources.

## 11. Self-check questions

**Question 1.** Two topics for orders and payments emit the exact same number of items, but items may arrive out of order. Should you use `Flux.zip` for reconciliation?

**Answer:** No. `zip` pairs by position and does not check the `orderId` key. You need key-based matching with time and late-data policies.

**Question 2.** How many input bindings does `Function<Tuple2<Flux<A>, Flux<B>>, Flux<C>>` have in Spring Cloud Stream if the bean is named `combineEvents`?

**Answer:** Two input bindings: `combineEvents-in-0` and `combineEvents-in-1`. There is one output binding: `combineEvents-out-0`.

**Question 3.** Why is `Flux.combineLatest` unsuitable for matching individual payment transactions to orders?

**Answer:** It takes the latest value from each source, can reuse the same value multiple times, and has no awareness of business keys. The two latest values do not necessarily belong to the same transaction.

**Question 4.** Why does joining with `join` + `Mono.delay(30 seconds)` fail to satisfy a requirement to reconcile transactions created at most 30 seconds apart according to payload timestamps?

**Answer:** The example's window measures **pipeline processing time**, not event timestamps. Delayed or out-of-order data requires event-time handling, watermarks, or keyed waiting state.

**Question 5.** If a payment arrives but its order does not arrive before the window expires, does the function above automatically emit `TIMEOUT`?

**Answer:** No. The function only emits `Reconciliation` for pairs that satisfy its conditions; emitting timeout results or missing-event alerts must be designed separately.

## References

- [Spring Cloud Function — Programming Model, Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Functional binding and multiple inputs/outputs](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Project Reactor — Flux API: zip, merge, combineLatest, and join](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Project Reactor — Reactive operators: Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html)
