# Recording Unit of a Subscription Versus Individual Flux Elements

In a reactive application, a `Flux` can emit one element, many elements, or no elements at all. When wrapping an entire `Flux` with a circuit breaker, you need to understand whether the circuit breaker is protecting one execution of the publisher or each independent operation within the stream. This distinction directly affects the number of recorded calls, the failure rate, permissions in `HALF_OPEN`, and how metrics are interpreted.

With Resilience4j Reactor, a circuit breaker placed around a `Flux` typically records **one execution per subscription**. It does not automatically treat every `onNext` signal as an independent call. A single subscription can emit hundreds of elements and still produce only one completion or failure outcome for the circuit breaker. If each element needs to call a separate dependent service, wrap each inner call with a circuit breaker so that each operation has its own statistical outcome.

This is a critical consideration when implementing Spring Cloud CircuitBreaker for reactive streams: define the boundary of a dependent call before deciding where to place the circuit breaker.

## 1. Reactive Streams have subscriptions and element signals

According to the Reactive Streams model, a `Publisher` accepts one or more `Subscriber`s. Each `subscribe()` call creates a subscription. Within that subscription, the publisher can emit the following signals:

- `onNext(value)`: emits a data element.
- `onComplete()`: terminates the stream normally.
- `onError(error)`: terminates the stream with an error.
- `cancel()`: the subscriber requests cancellation of data delivery.

With `Flux<T>`, a subscription can emit 0..N `onNext` signals, then terminate with `onComplete` or `onError` unless cancelled. With `Mono<T>`, a subscription emits at most one element and then terminates.

A circuit breaker is a mechanism for protecting an operation or call that has a success/failure outcome. When applying Resilience4j's Reactor operator to a `Flux`, the operator participates in the subscription process and tracks the terminal outcome of the subscription. `onNext` elements are forwarded downstream; they do not automatically increment the successful call count.

| Concept | Meaning in Reactive Streams | Meaning when a circuit breaker wraps the publisher |
|---|---|---|
| Subscription | One instance of a subscriber registering to receive data from a publisher. | Usually represents one protected execution that is granted permission. |
| `onNext` | A single emitted element. | Merely data within the current execution, not a separate call. |
| `onComplete` | Publisher completes normally. | The execution outcome is recorded as a success. |
| `onError` | Publisher terminates with an error. | The execution outcome is recorded as a failure if the exception is configured to be recorded. |
| `cancel` | Subscriber cancels receiving data. | Not equivalent to completion or error; how permissions are released and metrics are recorded depends on the operator/version. |

For example, a subscription to a `Flux` that emits 500 records and completes normally is still one successful circuit breaker execution. If the publisher emits 200 records and then emits `onError`, that execution ends in failure even though partial data was already delivered to the subscriber.

## 2. Wrapping the entire Flux with a circuit breaker

Resilience4j provides a Reactor operator to wrap a `Mono` or `Flux`. For `Flux`, you can use `CircuitBreakerOperator`:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import reactor.core.publisher.Flux;

public class InventoryStreamService {
    private final CircuitBreaker inventoryStreamCircuitBreaker;
    private final InventoryClient inventoryClient;

    public InventoryStreamService(
            CircuitBreaker inventoryStreamCircuitBreaker,
            InventoryClient inventoryClient) {
        this.inventoryStreamCircuitBreaker = inventoryStreamCircuitBreaker;
        this.inventoryClient = inventoryClient;
    }

    public Flux<StockUpdate> streamUpdates(String sku) {
        return inventoryClient.streamUpdates(sku)
            .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker));
    }
}
```

In this example, `inventoryClient.streamUpdates(sku)` can emit multiple `StockUpdate` items. The circuit breaker protects the subscription to that stream. If a subscriber receives 100 elements and the stream completes, the circuit breaker records one successful outcome. If another subscriber subscribes again to a cold source, the second subscription is a new execution and can record an additional outcome.

To use `CircuitBreakerOperator`, the application needs Resilience4j's Reactor integration module, typically `resilience4j-reactor`, along with the corresponding circuit breaker and Reactor modules. Module versions must stay aligned with the Resilience4j version managed by the Spring Cloud starter.

## 3. Flux element count is not the circuit breaker call count

Suppose a subscription to an inventory service emits 1,000 updates and completes. If the circuit breaker wraps the entire `Flux`, the circuit breaker statistics reflect one execution, not 1,000 successful calls.

| Behavior of one subscription | Number of `onNext` | Terminal outcome | Recorded execution count |
|---|---:|---|---:|
| Stream emits 10 elements and completes | 10 | Success | 1 |
| Stream emits 1,000 elements and completes | 1,000 | Success | 1 |
| Stream emits 200 elements then emits a recorded error | 200 | Failure | 1 |
| Stream completes without emitting any elements | 0 | Success | 1 |

An empty `Flux` that completes normally is still a subscription that ends in success. Zero elements does not mean a failed call. If business logic requires at least one element, validate that condition in application code and convert it into an appropriate business error when needed; the circuit breaker does not automatically infer that an empty stream is an error.

Similarly, an emitted data item carrying a "not found" or "unavailable" status can still be delivered via `onNext`. If the publisher completes normally, the circuit breaker typically treats that as a technical success. To treat that business outcome as a failure, the application must turn it into an error signal or use an appropriate result classification mechanism.

## 4. When each element represents an independent call

There are cases where each input element triggers a separate request to a dependent service. In that situation, the circuit breaker should be placed around each inner request rather than only wrapping the entire input `Flux`.

For example, each SKU in an input stream requires looking up stock via a `Mono<Stock>` call:

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class InventoryLookupService {
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryLookupService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Flux<Stock> lookupAll(Flux<String> skuStream) {
        return skuStream.flatMap(sku ->
            circuitBreakerFactory.create("inventory-item").run(
                inventoryClient.getStock(sku),
                error -> Mono.just(Stock.unavailable(sku))
            ),
            16
        );
    }
}
```

Here, each SKU creates a separate `Mono` call through the `inventory-item` circuit breaker. Each inner publisher is subscribed to as `flatMap` processes the input element, so each request can contribute its own outcome to the circuit breaker statistics. The `16` parameter limits how many inner publishers are processed concurrently within one `flatMap` invocation; it is not a global bulkhead configuration, and multiple concurrent subscriptions to `lookupAll` can still increase total concurrent requests.

If you want sequential processing, you can use `concatMap` instead of `flatMap`. If you need to cap concurrency across multiple requests and multiple subscribers, consider a Bulkhead or load limiting at an appropriate layer. Circuit breakers and concurrency limits solve two different problems.

## 5. Converting a Flux into a single Mono result

Spring Cloud CircuitBreaker's reactive API typically works with `Mono<T>` for a single reactive call. If a dependent operation returns a finite `Flux<T>` and business logic needs the entire result as one unit, you can collect the stream into a `Mono<List<T>>` with `collectList()` and wrap that `Mono`:

```java
import java.util.Collections;
import java.util.List;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class InventoryBatchService {
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryBatchService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Mono<List<StockUpdate>> loadBatch(String warehouseId) {
        Mono<List<StockUpdate>> batch = inventoryClient.streamUpdates(warehouseId)
            .collectList();

        return circuitBreakerFactory.create("inventory-batch").run(
            batch,
            error -> Mono.just(Collections.emptyList())
        );
    }
}
```

With this approach, the entire finite stream is collected into a list, and the circuit breaker protects a single batch-fetch operation. If the source emits an error after several elements, `collectList()` emits an error instead of returning a partial list; the fallback is invoked for that execution. This aggregation fits when the element count is bounded and the business logic requires the whole result.

Do not use `collectList()` for an unbounded or very large stream. The publisher only builds the list upon completion, and the list must hold all elements in memory. For continuous streams, choose a different protection boundary, such as individual finite batch requests or independent per-item operations.

## 6. Cold Flux, multiple subscriptions, and execution counts

Many publishers in Reactor are cold: data and source operations are only executed when a subscriber subscribes. Each subscription to a cold publisher typically creates a new source execution.

```java
Flux<StockUpdate> coldUpdates = Flux.defer(() ->
    inventoryClient.fetchCurrentUpdates()
);

Flux<StockUpdate> protectedUpdates = coldUpdates
    .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker));
```

If two independent components subscribe to `protectedUpdates`, the cold source can be invoked twice and the circuit breaker can record two executions. Merely creating the `Flux` variable does not mean the request has been sent; the request starts when a subscription occurs.

This also means a reactive-level retry can create a new subscription. If the retry operator sits outside the circuit breaker, each retry attempt can pass through the circuit breaker and be counted as a separate execution. Account for this behavior when designing retries, sliding windows, and failure thresholds.

## 7. Hot, share, and cache alter execution boundaries

With hot or shared publishers, the number of downstream subscribers does not necessarily equal the number of times the upstream source is executed. Operators such as `share()`, `publish().refCount()`, and `cache()` can share or retain source results.

Where the circuit breaker is placed relative to these operators determines whether it measures the upstream source or the downstream subscriptions:

```java
// Circuit breaker before share: protects the shared source execution.
Flux<StockUpdate> sharedProtectedSource = inventoryClient.streamUpdates("SKU-1")
    .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker))
    .share();

// Circuit breaker after share: each downstream subscription passes through the operator.
Flux<StockUpdate> protectedSharedView = inventoryClient.streamUpdates("SKU-1")
    .share()
    .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker));
```

In the first example, `share()` shares the already-protected publisher. The shared source typically has a single upstream subscription during the sharing lifecycle, so the circuit breaker observes that upstream execution. In the second example, the operator is after `share()`: each downstream subscriber can create its own subscription through the circuit breaker even though the source is shared. In that case, the count recorded by the circuit breaker can exceed the number of times the source actually called the service.

`cache()` can also replay stored data without calling the dependent service again. If the circuit breaker is placed after cache, subscribers reading cached data can still be counted as subscriptions passing through the circuit breaker, even though no new network request reaches the service. If your goal is to measure errors and latency of network calls, place the circuit breaker boundary around the actual network operation and carefully consider cache placement.

There is no single right placement for every application. Determine whether you want to protect and measure the data source, the shared stream, or each individual subscriber before choosing operator ordering.

## 8. Mid-stream errors and fallback placement

A `Flux` can emit several elements and then emit an error. A circuit breaker wrapping the entire publisher detects the error at the terminal signal and can record a failed execution. Elements already emitted before the error cannot be retracted.

With Resilience4j's Reactor operator, you can place fallback handling downstream of the circuit breaker:

```java
Flux<StockUpdate> result = inventoryClient.streamUpdates("SKU-1")
    .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker))
    .onErrorResume(error -> fallbackUpdates("SKU-1", error));
```

In this order, the circuit breaker sees `onError` before `onErrorResume` turns the error into a fallback stream. It can record the failure, while the subscriber receives fallback data according to application policy.

If you handle errors before passing the publisher into the circuit breaker:

```java
Flux<StockUpdate> result = inventoryClient.streamUpdates("SKU-1")
    .onErrorResume(error -> fallbackUpdates("SKU-1", error))
    .transform(CircuitBreakerOperator.of(inventoryStreamCircuitBreaker));
```

then the circuit breaker may only see the fallback stream complete normally and record a success. This distorts the failure rate if the goal is to measure original errors from the dependent service. Place the fallback after the circuit breaker when you want the circuit breaker to record source failures before the application recovers the stream.

A fallback for `Flux` must return a compatible `Publisher` and must account for elements emitted before the error. For example, appending fallback data after a partial stream can produce a result set mixing real data and fallback data. For business cases requiring whole-batch consistency, you can collect into `Mono<List<T>>` so results are only emitted after successful completion.

## 9. Long-lived streams and cancellation

Traditional circuit breakers fit operations with a clear start and end. A finite `Flux` usually has an `onComplete` or `onError` signal, so the operator can record the final outcome.

A long-lived or never-ending `Flux`, such as a WebSocket, Kafka, or continuous update stream, does not produce per-element success/failure outcomes when a circuit breaker wraps the entire stream. If the stream stays open for hours, the circuit breaker may keep the execution in an in-progress state for most of that time; the failure rate does not reflect individual events.

When a subscriber cancels a subscription, that is a `cancel` signal, not `onComplete` or `onError`. How the operator releases permissions and records cancellation can differ across library versions. Do not assume cancellation is treated as success or failure. Test cancellation behavior against the exact Resilience4j Reactor version in use.

For long-lived streams, consider:

- Protecting connection establishment or stream-opening operations as separate operations.
- Using timeouts, heartbeats, and reconnect policies suited to the streaming protocol.
- Protecting individual requests or finite batches sent over the stream if those are the actual business units to measure.
- Tracking connection failures, reconnect counts, processing latency, and error events with dedicated metrics.

Do not wrap an infinite stream in a circuit breaker and interpret circuit openings as per-message error rates.

## 10. Testing subscription and outcome counts

You can use `Flux.defer` to count how many times the source is subscribed to and `StepVerifier` to verify emitted elements. Example with Resilience4j's Reactor operator:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class FluxCircuitBreakerTest {

    @Test
    void countsOneExecutionForEachSubscriptionNotEachElement() {
        CircuitBreaker circuitBreaker = CircuitBreaker.ofDefaults("updates");
        AtomicInteger subscriptions = new AtomicInteger();

        Flux<Integer> source = Flux.defer(() -> {
            subscriptions.incrementAndGet();
            return Flux.just(10, 20, 30, 40);
        });

        Flux<Integer> protectedFlux = source
            .transform(CircuitBreakerOperator.of(circuitBreaker));

        StepVerifier.create(protectedFlux)
            .expectNext(10, 20, 30, 40)
            .verifyComplete();

        StepVerifier.create(protectedFlux)
            .expectNext(10, 20, 30, 40)
            .verifyComplete();

        assertEquals(2, subscriptions.get());
        assertEquals(2, circuitBreaker.getMetrics().getNumberOfSuccessfulCalls());
    }
}
```

The source emits four elements per subscription, yet after two subscriptions, the circuit breaker records two successful executions. This result proves that the number of `onNext` signals is not the number of calls recorded when the operator wraps the entire `Flux`.

You can add the following test cases:

1. One subscription emitting multiple elements and completing: verify one success.
2. One subscription emitting a few elements then `onError`: verify one failure if the exception is recorded.
3. Two subscriptions to a cold publisher: verify two source executions.
4. Multiple subscribers to a `share()` or `cache()` publisher: verify that circuit breaker placement determines recorded subscription counts and source call counts.
5. Cancelling a subscription before the publisher terminates: verify permission and metrics behavior for the version in use.
6. An input `Flux` calling multiple inner `Mono`s: verify each inner call has its own circuit breaker outcome.

## 11. Choosing the circuit breaker boundary by business unit

Before placing the operator, answer the question: what constitutes one failure that the system needs to track? It could be opening a stream connection, fetching a batch, looking up an SKU, or sending a command. That unit should correspond to a dependent operation that can succeed or fail independently.

| Protection goal | Appropriate organization |
|---|---|
| One request fetching a complete finite update list | Wrap the entire `Flux` or collect into `Mono<List<T>>` if an intact batch result is required. |
| Each SKU triggers a separate lookup request | Place the circuit breaker inside `flatMap`/`concatMap` around each inner `Mono`. |
| Multiple subscribers reading from one shared source | Decide whether to measure upstream once or each downstream subscriber and place the operator before/after `share` accordingly. |
| Infinite stream or long-lived connection | Protect connection and reconnect operations; use separate metrics per event or request. |
| Publisher emits partial data then errors | Place the circuit breaker before the fallback if source errors must be recorded; clearly decide whether partial data is acceptable. |

When implementing Spring Cloud CircuitBreaker, the reactive factory typically protects a `Mono` representing a single call. For `Flux` streams, you can use Resilience4j's Reactor operator directly or convert a finite stream into a single `Mono` result if the entire stream is one business unit. When each element represents an independent request, protect each inner request. Defining the right subscription boundary ensures that failure rates, probe counts, and metrics accurately reflect the calls your system actually intends to protect.
