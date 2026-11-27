# Distinguishing Per-Message Processing Functions from Stream-Composing Functions

In Spring Cloud Stream, a function can process each message individually or work with an entire asynchronous data stream. Both approaches look quite similar because they both use `Supplier`, `Function`, and `Consumer`, yet the way the framework invokes the function, how data flows through the application, and how errors are handled have important differences.

**An imperative function (per-message processing function)** receives a payload or a `Message<?>` on each invocation. **A reactive function (stream-processing function)** receives a publisher such as `Flux<T>` and returns another publisher to describe a continuous data-processing pipeline. Spring Cloud Stream connects those functions to bindings and binders to transmit data across Kafka, RabbitMQ, or Pulsar.

Understanding both models helps you choose the processing approach that fits your business requirements, avoid creating manual subscriptions, control backpressure, and avoid confusing a single message containing multiple elements with a stream of messages.

## 1. Two Ways of Viewing Data

In the per-message model, the application receives a payload, processes it, and returns a result or performs a business side effect. The framework invokes the function for each delivered message:

```text
Message A -> Function(A) -> Result A
Message B -> Function(B) -> Result B
Message C -> Function(C) -> Result C
```

In the reactive model, the application receives a publisher representing a sequence of elements. The function is invoked to construct a processing pipeline; operators describe how each element is transformed, filtered, grouped, or combined:

```text
Flux<A, B, C, ...> -> Function(Flux) -> Flux<Result A, Result B, ...>
```

The core difference lies in the input type and the function invocation lifecycle:

| Characteristic | Per-message processing | Reactive stream processing |
|---|---|---|
| Input type | `T` or `Message<T>` | `Flux<T>` or corresponding publisher |
| Function invocation | Once per message | Typically once to receive the publisher and build the pipeline |
| Processing unit | A single message | A stream of multiple elements over time |
| Transformation | Direct payload processing | Uses operators such as `map`, `filter`, `flatMap`, `buffer`, `window` |
| Orchestration | Framework/binder invokes the function per message delivery | Reactor orchestrates subscriptions, signals, and backpressure within the pipeline |
| Best suited for | Independent per-message business logic | Continuous streams, multi-element transformations, batch/group processing, or stream composition |

A `Message<List<T>>` is still a single message whose payload is a list. It differs from `Flux<T>`, which is a publisher that can emit multiple elements over time and has its own subscription lifecycle.

## 2. Per-Message Processing Functions with Supplier, Function, and Consumer

In the imperative model, the commonly used function signatures are:

```java
Supplier<OrderCreated>
Function<OrderCreated, OrderEnriched>
Consumer<OrderCreated>
```

- `Supplier<T>` produces an output value each time it is invoked. With Spring Cloud Stream, an imperative supplier is typically polled on a schedule to produce messages.
- `Function<T, R>` receives a payload of type `T`, processes it, and returns a result of type `R` for that message.
- `Consumer<T>` receives a payload of type `T` and performs a business side effect without producing an output binding from a return value.

Example of a function processing an order event:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderEnriched> enrichOrder(
            CustomerDirectory customerDirectory) {
        return event -> new OrderEnriched(
            event.orderId(),
            customerDirectory.displayName(event.customerId()),
            event.totalAmount()
        );
    }
}

record OrderCreated(String orderId, String customerId, long totalAmount) {}
record OrderEnriched(String orderId, String customerName, long totalAmount) {}
```

When a message arrives at `enrichOrder-in-0`, the framework converts the payload to `OrderCreated` and invokes the function. The `OrderEnriched` result is sent via `enrichOrder-out-0`. Each function invocation corresponds to one input message.

An imperative consumer is suitable when each message needs to update a record or call a service:

```java
@Bean
Consumer<OrderCreated> updateOrderProjection(OrderProjectionService service) {
    return event -> service.apply(event);
}
```

Here, `Consumer` has no output binding. The framework invokes the consumer for each delivered `OrderCreated`. If the consumer writes to a database, you must determine when commit and ACK/offset occur, and make the operation safe when a message is redelivered.

## 3. Reactive Functions Receiving and Returning Flux

With Reactor, `Flux<T>` represents a sequence that can emit from 0 to many elements. `Mono<T>` represents at most one element. Spring Cloud Stream can connect a reactive function to bindings using signatures such as `Function<Flux<T>, Flux<R>>`.

Example of transforming an event stream:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;

@Configuration
class ReactiveOrderFunctions {

    @Bean
    Function<Flux<OrderCreated>, Flux<OrderEnriched>> enrichOrders() {
        return orders -> orders
            .filter(order -> order.totalAmount() > 0)
            .map(order -> new OrderEnriched(
                order.orderId(),
                order.customerId().toUpperCase(),
                order.totalAmount()
            ));
    }
}
```

The framework provides a `Flux<OrderCreated>` to the function. The function returns a `Flux<OrderEnriched>` describing the transformation pipeline. The framework manages subscribing to the pipeline according to Spring Cloud Stream's integration model. Do not call `subscribe()` inside the function just to make the pipeline run; manually subscribing can detach the work from the framework-managed lifecycle, making errors and completion signals hard to coordinate properly.

A reactive function is typically invoked once to set up the pipeline rather than being called again separately for each message like an imperative function. Elements are processed as the publisher emits signals and the subscriber requests data.

## 4. Bindings of Imperative and Reactive Functions

Binding names are derived from the bean name and data direction in the same way across both models. The difference lies in the payload types the function receives and returns:

| Bean | Input binding | Output binding |
|---|---|---|
| `Function<OrderCreated, OrderEnriched> enrichOrder` | `enrichOrder-in-0` | `enrichOrder-out-0` |
| `Function<Flux<OrderCreated>, Flux<OrderEnriched>> enrichOrders` | `enrichOrders-in-0` | `enrichOrders-out-0` |
| `Consumer<OrderCreated> updateProjection` | `updateProjection-in-0` | None |

Example configuration for a reactive function:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.created
          group: order-enrichment
          content-type: application/json
        enrichOrders-out-0:
          destination: orders.enriched
          content-type: application/json
```

The binder receives messages from the `orders.created` destination, converts payloads into elements of the input stream, and forwards results from the output publisher to `orders.enriched`. How the binder receives, acknowledges, and dispatches messages depends on the specific broker and configuration.

You do not need to create a separate binding for each element in a `Flux`. A single binding represents the function's data stream; elements are emitted through that publisher.

## 5. Chaining Operators to Process Streams

A reactive function can compose multiple operators into a single pipeline. Some commonly used operators:

| Operator | Role | Usage example |
|---|---|---|
| `map` | Synchronously transforms each element. | Convert `OrderCreated` to `OrderSummary`. |
| `filter` | Keeps only elements matching a condition. | Drop events without valid values. |
| `flatMap` | Converts each element into another publisher and merges results. | Call a reactive service to enrich data. |
| `concatMap` | Processes inner publishers sequentially in order. | Preserve order when each event must complete before the next. |
| `buffer(n)` | Groups up to `n` elements into a collection. | Write multiple records in batches. |
| `window(n)` | Splits the stream into sub-streams. | Process each data window separately. |
| `distinct` | Eliminates duplicate elements according to selected criteria. | Reduce duplicate elements within the pipeline scope. |
| `take(n)` | Takes at most the first `n` elements. | Limit data in a finite task. |

Example combining filtering, asynchronous enrichment, and batching:

```java
Function<Flux<OrderCreated>, Flux<List<OrderEnriched>>> enrichInBatches = orders ->
    orders
        .filter(order -> order.totalAmount() > 0)
        .flatMap(order -> customerClient.findCustomer(order.customerId())
            .map(customer -> new OrderEnriched(
                order.orderId(), customer.name(), order.totalAmount()
            )))
        .buffer(50);
```

In this example, each valid element is enriched via a reactive call, and then up to 50 results are grouped into a list. The output type is now `Flux<List<OrderEnriched>>`, no longer `Flux<OrderEnriched>`. Downstream consumers must understand that each output message may carry a list rather than a single event.

`flatMap` allows asynchronous operations to overlap, so the output order may differ from the input order. If ordering must be preserved, consider `concatMap` or `flatMapSequential` and evaluate the throughput impact.

## 6. Backpressure and Rate Control

Backpressure is a mechanism that lets a subscriber signal to a publisher how many elements it is ready to receive. In Reactor, a subscriber can request data on demand instead of forcing the publisher to emit all data immediately.

Backpressure is useful when the emission rate exceeds the processing rate. Operators such as `limitRate`, `buffer`, `onBackpressureBuffer`, or `onBackpressureDrop` can tune how a pipeline reacts to rate mismatches, though each option has different consequences:

- `limitRate` adjusts upstream demand in batches.
- `buffer` holds data in memory until enough elements accumulate or a buffer emission condition is met.
- `onBackpressureBuffer` queues elements waiting to be processed, but requires a bounded capacity to avoid unbounded memory growth.
- `onBackpressureDrop` discards elements when downstream cannot keep up; only appropriate when the business logic allows losing dropped elements.

Example limiting the number of elements requested per batch:

```java
Function<Flux<OrderCreated>, Flux<OrderCreated>> controlledOrders = orders ->
    orders.limitRate(100);
```

Backpressure in Reactor does not mean the broker automatically stops publishing or that every binder translates demand to the broker in the same way. Some binders use their own polling, prefetch, internal buffering, or acknowledgement mechanisms. Therefore, you need to understand the limits at both the Reactor pipeline and the broker: queue depth, consumer lag, prefetch, partition count, and producer rate.

## 7. Do Not Block the Reactive Stream with Blocking APIs

A reactive pipeline is beneficial only when operations inside it do not unnecessarily hold threads waiting on I/O. Calling synchronous JDBC, `RestTemplate`, `Thread.sleep()`, or a blocking API inside `map` can hold the execution thread until the operation completes.

If a reactive client is available, compose publishers using `flatMap`:

```java
Function<Flux<OrderCreated>, Flux<OrderEnriched>> enrichReactively = orders ->
    orders.flatMap(order ->
        customerWebClient.getCustomer(order.customerId())
            .map(customer -> new OrderEnriched(
                order.orderId(), customer.name(), order.totalAmount()
            ))
    );
```

If calling a blocking API is unavoidable, isolate that operation on an appropriate scheduler and limit concurrency. The example below illustrates the Reactor technique; choose the scheduler and limit based on actual load:

```java
import reactor.core.scheduler.Schedulers;

Function<Flux<OrderCreated>, Flux<OrderEnriched>> enrichBlocking = orders ->
    orders.flatMap(order ->
        reactor.core.publisher.Mono.fromCallable(() ->
            blockingCustomerService.load(order.customerId())
        )
        .subscribeOn(Schedulers.boundedElastic())
        .map(customer -> new OrderEnriched(
            order.orderId(), customer.name(), order.totalAmount()
        )),
        8
    );
```

Limiting concurrency in `flatMap` prevents spawning too many blocking tasks simultaneously. However, using a scheduler does not turn a blocking API into a truly reactive API; monitor threads, queues, and timeouts.

## 8. Imperative Supplier and Reactive Supplier

An imperative supplier such as `Supplier<OrderCreated>` is typically invoked by a poller to produce individual messages. In contrast, `Supplier<Flux<OrderCreated>>` returns a publisher that can emit multiple elements.

```java
@Bean
Supplier<Flux<OrderCreated>> orderEvents(OrderEventService service) {
    return service::liveEvents;
}
```

With a continuous reactive supplier, the framework typically obtains the publisher and subscribes according to the binding lifecycle; the supplier is not re-invoked every second like an imperative supplier simply because a default poller exists. If the publisher is a continuous stream, creating repeated subscriptions can cause duplicate reads or waste resources.

If a reactive supplier returns a finite stream and needs to be polled periodically, Spring Cloud Function provides `@PollableBean` to mark a reactive supplier that should be polled:

```java
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import reactor.core.publisher.Flux;

@PollableBean
Supplier<Flux<OrderCreated>> pendingOrders(OrderEventService service) {
    return () -> Flux.fromIterable(service.findPendingOrders());
}
```

When using `@PollableBean`, you must understand poller configuration, element splitting, and source state. If the source returns the same list on the next poll, messages may be emitted multiple times. Claim or mark records safely and design idempotent consumers.

## 9. Error Handling in a Reactive Pipeline

Errors in a reactive pipeline are propagated as `onError` signals. When an operator throws an exception, the pipeline can terminate unless the error is handled with an appropriate operator.

Several handling approaches:

- `onErrorMap`: translates the error into a more meaningful exception type.
- `onErrorResume`: switches to a fallback publisher or recovery stream.
- `onErrorContinue`: skips an element causing an error and continues where operators support it; use cautiously because it can mask data errors.
- `retry`/`retryWhen`: resubscribes to the publisher according to a retry policy.

Example retrying a lookup operation that may encounter transient errors:

```java
Function<Flux<OrderCreated>, Flux<OrderEnriched>> enrichWithRetry = orders ->
    orders.flatMap(order ->
        customerWebClient.getCustomer(order.customerId())
            .map(customer -> new OrderEnriched(
                order.orderId(), customer.name(), order.totalAmount()
            ))
            .retryWhen(reactor.util.retry.Retry.backoff(3, java.time.Duration.ofMillis(200)))
    );
```

Retry at the Reactor layer retries the publisher operation inside the pipeline. It differs from retry/redelivery managed by the binder or broker. If the entire function fails, how messages are acknowledged, redelivered, or routed to a DLQ depends on the binder and configuration. Do not stack multiple layers of retries without calculating total attempts and wait time.

Distinguish transient errors from data errors that cannot be fixed by retrying. Messages with invalid schemas or contract violations generally need to be handled via an error channel/DLQ rather than retried repeatedly.

## 10. Ordering and Concurrency in Reactive Streams

A reactive pipeline can process multiple elements concurrently. Operators like `flatMap` and `parallel` can increase throughput, but results may complete out of input order. `concatMap` serializes inner publishers; `flatMapSequential` allows concurrent execution while emitting results in source order.

Choose operators according to business requirements:

| Requirement | Suggested operator | Trade-off |
|---|---|---|
| Synchronous per-element transformation | `map` | Creates no I/O concurrency. |
| Calling multiple reactive services concurrently | `flatMap` | May alter result order; requires concurrency limits. |
| Asynchronous processing while emitting in source order | `flatMapSequential` | May have to buffer early-completing results. |
| Sequential per-element processing | `concatMap` | Preserves order, though throughput may be lower. |

Ordering of a Flux inside the application also does not automatically extend broker ordering guarantees. Kafka guarantees ordering only within a partition; RabbitMQ and Pulsar have their own rules by queue/subscription. If a function runs with multiple partitions or consumers, define the ordering scope required by the business logic.

## 11. Message, Batch, and Stream Are Not the Same Concept

The following representations have different meanings:

| Type | Meaning |
|---|---|
| `OrderCreated` | A single business payload. |
| `Message<OrderCreated>` | A message containing payload and headers. |
| `List<OrderCreated>` | A collection inside a single object/payload. |
| `Message<List<OrderCreated>>` | A message whose payload is a collection. |
| `Flux<OrderCreated>` | A publisher emitting multiple elements over time. |
| `Flux<Message<OrderCreated>>` | A publisher emitting messages, each with its own payload and headers. |

If the binder delivers a message whose payload is a list, an imperative function can accept `List<OrderCreated>` and process a batch in one invocation. If the function accepts `Flux<OrderCreated>`, the framework is providing a publisher of multiple elements. Do not assume that enabling batch mode automatically turns a `Function<T,R>` signature into `Function<Flux<T>,Flux<R>>`; batch mode and reactive processing are two different model choices.

## 12. When Should You Choose Each Model?

Choose an imperative function when each message is an independent business unit, the logic is straightforward, you want clear per-message control, or the team does not yet need a reactive pipeline. This model is easy to read, easy to debug, and fits most consumers doing CRUD processing, updating projections, or executing individual tasks.

Choose a reactive function when the problem genuinely requires stream-level processing: transforming multiple elements, calling multiple reactive services, filtering, grouping, combining streams, or regulating rate with backpressure. The reactive model can reduce thread overhead when I/O is asynchronous and the pipeline is properly designed.

Do not convert every function to reactive just to use `Flux`. If processing consists of only a single synchronous operation per message, `Function<T,R>` or `Consumer<T>` is usually simpler. Reactive code introduces concepts of subscription, demand, cancellation, scheduler, and error signals; use it only when those capabilities provide real value.

## 13. Testing Imperative and Reactive Functions

An imperative function can be tested by calling the function directly with a payload:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Function;

import org.junit.jupiter.api.Test;

// Uses the same OrderCreated and OrderEnriched records declared above.
class ImperativeFunctionTest {

    private final Function<OrderCreated, OrderEnriched> function = event ->
        new OrderEnriched(event.orderId(), event.customerId(), event.totalAmount());

@Test
void enrichesOneOrder() {
    OrderCreated input = new OrderCreated("order-1", "customer-1", 500);

    OrderEnriched result = function.apply(input);

    assertEquals("order-1", result.orderId());
}
}
```

A reactive function should be tested with Reactor Test (`StepVerifier`) to verify elements, ordering, completion, and errors:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

// Uses the same OrderCreated and OrderEnriched records declared above.
class ReactiveFunctionTest {

    private final Function<Flux<OrderCreated>, Flux<OrderEnriched>> reactiveFunction =
        orders -> orders.map(order -> new OrderEnriched(
            order.orderId(), order.customerId(), order.totalAmount()
        ));

@Test
void transformsOrderStream() {
    Flux<OrderCreated> input = Flux.just(
        new OrderCreated("order-1", "customer-1", 100),
        new OrderCreated("order-2", "customer-2", 200)
    );

    Flux<OrderEnriched> output = reactiveFunction.apply(input);

    StepVerifier.create(output)
        .expectNextMatches(order -> order.orderId().equals("order-1"))
        .expectNextMatches(order -> order.orderId().equals("order-2"))
        .verifyComplete();
}
}
```

Additional tests should verify:

- Whether an empty stream completes properly.
- Invalid elements are filtered, mapped to errors, or recovered according to contract.
- `flatMap` has an appropriate concurrency limit.
- Ordering is preserved when business requirements demand it.
- Cancellation and timeouts do not leave dangling subscriptions or leaked resources.
- Bindings convert payloads and headers properly when using Test Binder.

The Test Binder helps test binding integration within the application scope, but it does not fully simulate backpressure, partition assignment, ACKs, or every broker characteristic. For guarantees depending on Kafka, RabbitMQ, or Pulsar, run integration tests with the corresponding binder/broker.

## 14. Observing Reactive Pipelines in Operations

Beyond broker metrics, monitor per-element processing time, emission/consumption rates, buffered element counts, errors by type, retry counts, and latency from message receipt to output emission. For pipelines using `flatMap`, monitor concurrent task counts and wait time for dependent services.

Attach `eventId` and `correlationId` to logs/traces to correlate stages. Avoid logging sensitive full payloads. If backlog grows while CPU stays low, downstream I/O may be slow or demand may be constrained. If memory grows, check for unbounded buffers, `collectList()` on long-lived streams, or unreleased publishers.

Do not arbitrarily call `block()` or `subscribe()` inside a function to "get the result immediately." Such calls can break reactive orchestration, cause deadlocks, or detach errors from the binder. Let data continue flowing through the publisher and composition operators.

## 15. Model Selection Workflow

Before writing a processing function in Spring Cloud Stream, answer:

1. Does the function need to process each payload independently or see the entire data stream?
2. Should a single invocation produce exactly one result, no result, or multiple results?
3. Is there a need to filter, group, combine, or regulate rates across elements?
4. Do dependent services have reactive APIs or only blocking APIs?
5. Are there ordering requirements by partition, key, or entity?
6. Where are backpressure, buffering, and concurrency limits controlled?
7. Should an error in one element fail the entire pipeline or be recovered individually?
8. Which delivery semantics and reactive integration behaviors does the chosen binder support?
9. Which tests verify the required payloads, completion, errors, and broker characteristics?

If the answers require processing only one message at a time, start with `Function<T,R>` or `Consumer<T>`. If the problem requires composing and orchestrating an asynchronous sequence of elements, use `Function<Flux<T>, Flux<R>>` and appropriate Reactor operators. Choosing based on data shape and processing requirements keeps the application clear, testable, and stable in production.
