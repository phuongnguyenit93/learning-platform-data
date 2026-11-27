# Choosing Synchronous or Reactive Processing Based on Real Workload

Spring Cloud Function allows expressing business logic as `Supplier<T>`, `Function<I, O>`, and `Consumer<T>`, looking them up via `FunctionCatalog`, chaining functions into compositions, and deploying the same logic over HTTP, events, or serverless environments. When a function receives a request, calls a database or external API, and returns a result, the two models usually considered are **synchronous (imperative)** and **reactive**.

This choice affects how threads are held, how I/O is orchestrated, concurrency control, error propagation, cancellation, and memory consumption. Yet **reactive is not automatically faster than synchronous**. A reactive pipeline can handle many concurrent pending I/O operations with fewer waiting threads when the entire call path is non-blocking. Conversely, a small CPU-bound function or an application using synchronous JDBC/JPA can be simpler and more efficient under the imperative model.

Within the **Performance** chapter, this lesson helps you decide based on **actual workload characteristics** rather than hype:

1. Distinguish synchronous calls returning values directly from `Mono`/`Flux` publishers that complete later.
2. Recognize CPU-bound, blocking I/O, non-blocking I/O, streaming, and batch workloads.
3. Write two versions of the same business logic using `Function<QuoteRequest, QuoteResult>` and `Function<Flux<QuoteRequest>, Flux<QuoteResult>>`.
4. Control concurrency, backpressure, queues, and downstream wait times.
5. Avoid calling `block()` or manually calling `subscribe()` in the wrong places inside reactive functions.
6. Handle JDBC/JPA, transactions, context propagation, errors, and retries according to the execution model.
7. Measure p50/p95/p99, throughput, thread usage, allocation, and error rates to select the right model.

> **Example scope:** Java 17+ and Spring Cloud Function on compatible Spring Boot/Spring Framework versions. `RestClient` is available since Spring Framework 6.1; reactive examples use Spring WebFlux, Reactor, and `WebClient`. Virtual threads apply only when running JDK 21+ with supporting runtime configuration. Verify dependencies, adapters, and APIs for your project version before applying.

## 1. Where do the two processing models differ?

### Synchronous: returns a result immediately during the call

An imperative function typically takes the form:

```java
Function<QuoteRequest, QuoteResult>
```

When a caller invokes `apply(request)`, the function executes its steps and returns a `QuoteResult` or throws an exception. If the function body makes a synchronous HTTP or JDBC call, the current thread typically **waits** until I/O finishes.

```text
Thread T1
  ├─ receives request
  ├─ calls synchronous pricing API
  ├─ waits for response        ← thread is occupied
  ├─ computes result
  └─ returns QuoteResult
```

Strengths include readable control flow, direct stack traces, and smooth integration with blocking libraries and synchronous transactions. What needs management is the **number of threads held while waiting on I/O**.

### Reactive: returns a publisher describing the work

A reactive function can take the form:

```java
Function<Flux<QuoteRequest>, Flux<QuoteResult>>
```

Calling `apply(requests)` typically **builds a publisher**; it does not mean every request has already been processed. Work begins when the publisher is subscribed to. With non-blocking I/O, the thread can be released while waiting on the network, then resume when a signal arrives.

```text
Reactive pipeline
  ├─ receives request signal
  ├─ dispatches non-blocking I/O
  ├─ yields control back to event loop
  ├─ response arrives → resumes pipeline
  └─ emits QuoteResult
```

Strengths include coordinating many concurrent I/O operations with fewer waiting threads, asynchronous composition, cancellation, and backpressure across segments supporting Reactive Streams. In return, the execution model differs: lazy subscription, operator concurrency, context propagation, signal-based errors, and more complex debugging.

| Criterion | Synchronous | Reactive |
| --- | --- | --- |
| Result | Value `T` or exception | Publisher `Mono<T>`/`Flux<T>` |
| Execution timing | During the method call | Typically after subscription |
| Blocking I/O | Holds thread while waiting | Can yield thread if client is non-blocking |
| Concurrency | Thread pools, request threads, virtual threads | Schedulers/event loops and subscriptions |
| Backpressure | Manually bound queues/concurrency | Reactive Streams protocol inside publisher chains |
| Stack traces | Usually direct | May span multiple asynchronous boundaries |
| JDBC/JPA | Natural integration | Blocking; must isolate or use a reactive driver |
| Streaming | Must manage iterators/callbacks manually | `Flux<T>` models item streams natively |
| Complexity | Usually lower for sequential flows | Higher if the team is unfamiliar with Reactor |
| Performance | Can be very good for matching workloads | Can excel for high I/O concurrency/streaming |

There is no rule that “reactive is always faster” or “synchronous is always better.” Compare on the same business logic, adapters, dependencies, load, and SLAs.

## 2. CPU-bound vs. I/O-bound matters more than syntax

Before picking a model, classify the primary work:

| Workload | Example | Characteristics | What to try first |
| --- | --- | --- | --- |
| CPU-bound | Hashing, computation, large-scale transforms | Continuous CPU usage, minimal I/O wait | Imperative, or reactive with bounded CPU work |
| Blocking I/O | JDBC, JPA, blocking files, synchronous SDKs | Thread waits on database/network/disk | Imperative; or isolate blocking work |
| Non-blocking I/O | WebClient/Reactor Netty, R2DBC | Can yield thread while waiting | Reactive under high concurrency |
| Streaming | Event streams, continuous data feeds | Needs rate and memory management | Reactive when adapter/source supports it |
| Bounded batch | Processing 100–10,000 records | Can batch and cap parallelism | Either; measure throughput and tail latency |
| Low traffic, short I/O | Low-load internal APIs | Pipeline overhead may not pay off | Imperative is usually easier to operate |

### CPU-bound work is not automatically accelerated by reactive

If a function runs a 10 ms CPU loop with no I/O, wrapping the result in `Mono.fromCallable(...)` does not make the computation finish faster. Running more concurrent CPU tasks than available cores can increase context switching and contention.

Reactive helps when a task can **yield its thread while waiting**, not merely because the return type is `Mono`.

### Blocking I/O does not become non-blocking just by wrapping in Mono

`Mono.fromCallable(() -> jdbcRepository.findById(id))` only defers invocation. It **does not automatically choose a scheduler**. If subscribed on an event loop, JDBC still blocks the event loop.

When forced to use a blocking library inside a reactive pipeline, isolate it on an appropriate scheduler and bound concurrency; even better, consider a non-blocking driver if your architecture and transaction model allow it.

## 3. One business problem, two implementations

Example quoting service: a request carries a product SKU and quantity; the system calls a pricing service and returns the total price. Shared DTOs:

```java
package demo.performance;

public record QuoteRequest(String sku, int quantity) {}
```

```java
package demo.performance;

public record QuoteResult(
    String sku,
    int quantity,
    long totalVnd
) {}
```

The endpoint below is an illustrative host:

```text
https://pricing.example.internal/v1/quotes
```

This is not a public API to call. In a real application, the host must come from trusted configuration; never accept arbitrary URLs from user payloads.

### Synchronous version

```java
package demo.performance;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class BlockingQuoteFunctions {

    @Bean("quoteBlocking")
    public Function<QuoteRequest, QuoteResult> quoteBlocking(
        RestClient pricingRestClient
    ) {
        return request -> {
            if (request == null ||
                request.sku() == null ||
                request.sku().isBlank() ||
                request.quantity() <= 0) {
                throw new IllegalArgumentException(
                    "Invalid quote request"
                );
            }

            QuoteResult result = pricingRestClient.post()
                .uri("/v1/quotes")
                .body(request)
                .retrieve()
                .body(QuoteResult.class);

            if (result == null) {
                throw new IllegalStateException(
                    "Pricing service returned an empty body"
                );
            }
            return result;
        };
    }
}
```

This example assumes `RestClient` is configured and injected from a shared bean. The function takes a DTO, validates it, calls the synchronous API, and returns a DTO. While waiting on the HTTP call, the executing thread is held.

### Reactive version

```java
package demo.performance;

import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class ReactiveQuoteFunctions {

    @Bean("quoteReactive")
    public Function<
        Flux<QuoteRequest>,
        Flux<QuoteResult>
    > quoteReactive(
        @Qualifier("pricingWebClient") WebClient client
    ) {
        return requests -> requests.flatMap(request -> {
            if (request == null ||
                request.sku() == null ||
                request.sku().isBlank() ||
                request.quantity() <= 0) {
                return Mono.error(
                    new IllegalArgumentException(
                        "Invalid quote request"
                    )
                );
            }

            return client.post()
                .uri("/v1/quotes")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(QuoteResult.class);
        }, 16);
    }
}
```

`flatMap(..., 16)` permits at most 16 inner publishers to run concurrently **within this pipeline subscription**. It is not a global cap across all invocations or all replicas. If a publisher represents a long stream, apply policies aligned with total load and downstream limits.

`flatMap` can emit results out of input order. When ordering must be preserved, consider `flatMapSequential(...)` or `concatMap(...)` and measure throughput/latency trade-offs.

Both functions share the same business contract, yet you cannot compare them by calling one synchronous and one reactive function directly while ignoring adapters/subscriptions. Run both through equivalent deployment paths with identical payloads.

## 4. FunctionCatalog and function names do not dictate the execution model

Spring Cloud Function can register both imperative and reactive functions into `FunctionCatalog`. For example:

```yaml
spring:
  cloud:
    function:
      definition: quoteBlocking
```

Or:

```yaml
spring:
  cloud:
    function:
      definition: quoteReactive
```

The function name selects which bean/chain to expose or invoke. **Simply changing the name from `quoteBlocking` to `quoteReactive` does not turn JDBC into non-blocking code**; the signature, internal implementation, clients, and adapters must all align.

| Signature | Description |
| --- | --- |
| `Function<QuoteRequest, QuoteResult>` | One input value, one output value in a synchronous call |
| `Function<Mono<QuoteRequest>, Mono<QuoteResult>>` | One input publisher, one result publisher |
| `Function<Flux<QuoteRequest>, Flux<QuoteResult>>` | Incoming request stream, outgoing result stream |
| `Supplier<QuoteResult>` | Supplies a single synchronous value |
| `Supplier<Flux<QuoteResult>>` | Supplies a stream |
| `Consumer<QuoteRequest>` | Processes a single synchronous value |
| `Consumer<Flux<QuoteRequest>>` | Consumes a stream |

Actual signatures supported by an adapter must be verified against its version and integration type. Do not assume every broker or serverless adapter shares WebFlux's streaming/backpressure semantics.

## 5. Synchronous processing can still handle concurrency well

A common misconception is: “blocking means one platform thread per request, so only reactive can handle many requests.” In reality, examine:

- Server thread pool and queue policy.
- Outbound connection pool.
- Whether virtual threads (JDK 21+) are enabled.
- Average and tail I/O latency.
- CPU cores, memory, downstream capacity, and replica count.

### Traditional thread-per-request

With synchronous requests, a thread may wait on I/O. If 300 requests simultaneously wait on an API taking 200 ms, occupied threads can be high depending on server and concurrency settings.

That does not mean raising the thread pool to 10,000 is the answer. Thread stacks, scheduling, and downstream pools can become bottlenecks.

### Virtual threads as an option for blocking code

JDK 21+ supports virtual threads. With a compatible Spring Boot version and configuration, an app can run many blocking operations without dedicating one platform thread per waiting task.

```yaml
spring:
  threads:
    virtual:
      enabled: true
```

This property applies only in supporting Spring Boot versions running on JDK 21+. Verify that executors and server components integrate cleanly with virtual threads.

**Virtual threads do not turn JDBC or blocking HTTP into non-blocking I/O**, nor do they let a database handle unlimited connections. Connection pools, rate limits, and downstream capacity still must be bounded. Certain native calls or synchronized blocks can affect virtual-thread unmounting depending on the JDK.

Virtual threads are worth benchmarking when code uses JDBC/JPA or blocking SDKs, flows are sequential, synchronous transactions are needed, and the team wants to preserve imperative stack traces. This is an option to benchmark, not a universal recommendation for every application.

## 6. Reactive pays off only when the primary wait is non-blocking

A pipeline may contain:

```text
Function<Flux<Request>, Flux<Response>>
  ├─ WebClient (non-blocking)
  ├─ R2DBC (non-blocking database driver)
  ├─ Reactor operators
  └─ WebFlux / reactive adapter
```

This path has the opportunity to juggle many in-flight I/O operations with fewer waiting threads. However, if the pipeline contains:

```text
WebClient → blocking JDBC query → blocking legacy SDK
```

then JDBC/SDK still block. They must be isolated or replaced with non-blocking clients/drivers; changing the function signature alone solves nothing.

### Wrapping blocking calls with boundedElastic

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<Price> findPrice(String sku) {
    return Mono.fromCallable(
        () -> jdbcRepository.findPrice(sku)
    ).subscribeOn(Schedulers.boundedElastic());
}
```

This example lives inside a reactive service where `jdbcRepository.findPrice(...)` is blocking. `boundedElastic()` offloads execution to a scheduler meant for blocking tasks instead of running on the event loop.

However:

1. `boundedElastic` has thread/queue limits governed by Reactor configuration and version; it is not infinite.
2. Bound upstream concurrency so tasks do not pile endlessly into the queue.
3. The database pool still caps active queries/connections.
4. If one request makes multiple blocking calls, total latency still includes their wait times.
5. Never offload arbitrary CPU work onto `boundedElastic`.

For critical workloads, consider a dedicated bounded scheduler with an explicit lifecycle. Never allocate a new scheduler per invocation.

## 7. CPU-bound work: bound parallelism to real hardware resources

A reactive pipeline can run CPU work on the parallel scheduler:

```java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

public Flux<Score> calculateScores(Flux<Input> inputs) {
    return inputs
        .publishOn(Schedulers.parallel())
        .map(this::cpuIntensiveCalculation);
}
```

This is an illustrative snippet; `Input` and `Score` are domain types. `Schedulers.parallel()` targets CPU-bound work with parallelism bounded to runtime resources.

Not every pipeline needs `publishOn(Schedulers.parallel())`. Crossing a scheduler boundary adds queue/scheduling overhead and can obscure code flow. If the computation is tiny, running on the current thread may be more efficient.

When CPU is the bottleneck:

- Profile hotspots and allocations before changing the execution model.
- Avoid running more heavy computations concurrently than CPU capacity allows.
- Choose appropriate batch sizes and concurrency levels.
- Improve algorithms and data structures before adding threads.
- Measure throughput and tail latency near CPU saturation.

**Reactive does not create extra CPU cores**; it only provides an asynchronous work-coordination model.

## 8. Backpressure: control flow rate instead of just raising concurrency

Reactive Streams defines a protocol for subscribers to request how many items they can consume. Backpressure helps stages in a publisher chain coordinate pace, yet **it does not automatically guarantee end-to-end backpressure across every adapter or broker**.

Example `flatMap` with concurrency:

```java
Flux<QuoteResult> results = requests.flatMap(
    request -> callPricing(request),
    16
);
```

This limits concurrent inner publishers within one subscription. It is not a global limit across all pipelines. If upstream continues emitting rapidly, Reactor operators coordinate demand and buffering according to each operator's semantics.

| Operator | Concurrency/ordering | When to consider |
| --- | --- | --- |
| `map(...)` | Synchronous on signal, adds no async concurrency | Fast transformations |
| `concatMap(...)` | One inner publisher at a time, preserves order | Downstream must be sequential |
| `flatMap(..., concurrency)` | Multiple inner publishers, may reorder | Independent I/O, bounded concurrency |
| `flatMapSequential(..., concurrency)` | Concurrent execution, emits in source order | Order must be preserved |
| `buffer(size)` | Collects items into batches | API/broker supports bounded batching |

Do not set maximum concurrency just because you can. If the pricing service can only tolerate 50 concurrent requests, setting `flatMap(..., 500)` across multiple replicas can overload it. Account for replica count, pools, rate limits, response times, queues, and retries.

HTTP WebFlux can support reactive request/response bodies; broker binders have their own prefetch, batch, ack, and concurrency settings; serverless adapters may hand each event in as a finite object. Consequently, `Flux<T>` in a function does not guarantee a broker stops delivering messages when downstream slows down. Check your specific adapter and enforce bounds at every boundary.

## 9. Thread pools, connection pools, and function concurrency are three distinct limits

| Limit | Controls | Does NOT control |
| --- | --- | --- |
| Web server request threads | Request threads per server model | Outbound HTTP connection count |
| Reactor event loops | Where I/O signals are processed | CPU parallelism across all tasks |
| BoundedElastic scheduler | Scheduled blocking tasks | Database capacity |
| Outbound HTTP pool | Connections to remote host | Number of requests accepted at ingress |
| JDBC pool | Database connections | HTTP client concurrency |
| `flatMap concurrency` | Inner subscriptions in a pipeline | Cluster-wide total concurrency |
| Broker consumer concurrency/prefetch | Delivery/processing from broker | Outbound HTTP pool |

An instance might have 16 outbound connections while accepting 200 concurrent invocations; many invocations will wait on the pool. If the pending queue is unbounded, memory and latency can climb.

**Good design needs layered boundedness:** ingress concurrency, pipeline concurrency, connection pools, pending queues, and deadlines. No single limit protects the whole system alone.

## 10. Using Little's Law to estimate in-flight work

Little's Law:

\[
L = \lambda W
\]

where `L` is the average number of items in the system, `λ` is the average throughput (requests/second), and `W` is the average time spent in the system (seconds).

For example, if an API receives **200 requests/second** and average time spent in the downstream call segment is **0.25 seconds**:

\[
L = 200 \times 0.25 = 50
\]

About 50 requests are in flight on average in that segment. This is not a recommendation to set pool size to 50; factor in bursts, tail latency, replicas, and downstream capacity.

If there are 8 replicas and each allows 20 concurrent inner requests, theoretical pipeline concurrency can reach:

\[
8 \times 20 = 160
\]

If downstream can only handle 80 concurrent requests, lower per-instance concurrency, add system-wide rate limiting/bulkheads, or scale downstream capacity. Reactive does not automatically divide concurrency budgets across replicas.

## 11. Transactions: imperative and reactive do not share the same transaction model

### Synchronous JDBC/JPA transactions

Traditional Spring transaction management typically uses `PlatformTransactionManager` and binds transaction resources to the executing thread's context. Synchronous JDBC/JPA code aligns naturally with imperative functions running within that transaction boundary.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BlockingOrderService {

    private final OrderRepository repository;

    public BlockingOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public OrderReceipt createOrder(OrderRequest request) {
        return repository.saveAndCreateReceipt(request);
    }
}
```

```java
@Bean
Function<OrderRequest, OrderReceipt> createOrder(
    BlockingOrderService service
) {
    return service::createOrder;
}
```

This example assumes `OrderRepository` is a JDBC/JPA repository and the method is invoked through a Spring proxy. Self-invocation within the same object can bypass proxy semantics; verify call paths.

### Reactive transactions

Reactive databases such as R2DBC typically require `ReactiveTransactionManager` and a transaction context bound to the reactive pipeline, not synchronous thread-local transactions.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderService {

    private final ReactiveOrderRepository repository;
    private final TransactionalOperator tx;

    public ReactiveOrderService(
        ReactiveOrderRepository repository,
        TransactionalOperator tx
    ) {
        this.repository = repository;
        this.tx = tx;
    }

    public Mono<OrderReceipt> createOrder(OrderRequest request) {
        return repository.save(request)
            .map(this::toReceipt)
            .as(tx::transactional);
    }

    private OrderReceipt toReceipt(OrderEntity entity) {
        return new OrderReceipt(
            entity.orderId(),
            entity.lineCount(),
            entity.totalVnd()
        );
    }
}
```

This example assumes a reactive repository and a `TransactionalOperator` backed by a compatible reactive transaction manager. You cannot swap in blocking JDBC and expect the pipeline to behave as a reactive transaction.

### Do not switch threads arbitrarily across transaction boundaries

- Synchronous JDBC/JPA transactions do not propagate safely across reactive scheduler boundaries.
- Reactive transaction context must stay within the same reactive chain and propagate properly.
- Never apply imperative `@Transactional` and assume it spans an async `Flux` after the method returns.
- When integrating both reactive and blocking stores, define separate transaction boundaries; never assume one local transaction covers both systems.

If business logic requires synchronous transactions and uses a JDBC database, an **imperative function can be the lower-risk choice** compared to switching to reactive solely for higher concurrency.

## 12. Context propagation: security, tracing, and correlation

In imperative code, many frameworks rely on `ThreadLocal` to hold security contexts, logging MDC, or transaction contexts. In reactive code, execution can hop threads between operators; `ThreadLocal` does not automatically follow every signal.

Reactor provides `Context` for subscription-scoped metadata; Spring Security, Micrometer Observation, and tracing offer matching integration mechanisms when configured. Never copy context manually by reading `ThreadLocal` on one thread and assuming the next thread sees the same value.

| Context | Requirement |
| --- | --- |
| Correlation/trace ID | Preserve across async boundaries via tracing propagation |
| Security principal | Never lose or mix principals across requests |
| Tenant ID | Bind strictly per invocation; never store in mutable singletons |
| Locale | Clear scope and propagation |
| Transaction context | Use the transaction manager matching the execution model |
| Request-scoped data | Never store in singleton fields |

When migrating an imperative function to reactive, test security, tracing, and tenant isolation — not just output DTOs.

## 13. Error handling: exceptions vs. reactive error signals

### Imperative

Exceptions thrown inside `Function.apply(...)` can be handled by the adapter's error mapping. Errors may stem from validation, downstream timeouts, or bugs; never turn all failures into a silent default result.

```java
@Bean
Function<QuoteRequest, QuoteResult> quote(RestClient client) {
    return request -> {
        try {
            return callPricing(client, request);
        } catch (org.springframework.web.client.ResourceAccessException ex) {
            throw new PricingUnavailableException(
                "Pricing service is unavailable", ex
            );
        }
    };
}
```

This snippet assumes a `callPricing(...)` method and application exception class. The adapter determines how exceptions map to HTTP status codes or event error channels.

### Reactive

In Reactor, errors are emitted as terminal signals:

```java
return client.post()
    .uri("/v1/quotes")
    .bodyValue(request)
    .retrieve()
    .bodyToMono(QuoteResult.class)
    .onErrorMap(
        WebClientResponseException.class,
        ex -> new PricingUnavailableException(
            "Pricing service returned an error", ex
        )
    );
```

This is a reactive pipeline fragment requiring the exception class and imports. `onErrorMap` translates the error type; it does not turn failure into success.

With `requests.flatMap(this::callPricing, 16)`, if one inner publisher emits an error without a recovery policy, the entire downstream `Flux` may terminate with an error, canceling remaining in-flight inner work per operator semantics.

If the contract permits per-item error results, define an explicit outcome type:

```java
public sealed interface QuoteOutcome
    permits QuoteSuccess, QuoteFailure {}

public record QuoteSuccess(QuoteResult value)
    implements QuoteOutcome {}

public record QuoteFailure(String code, String message)
    implements QuoteOutcome {}
```

```java
Flux<QuoteOutcome> outcomes = requests.flatMap(
    request -> callPricing(request)
        .<QuoteOutcome>map(QuoteSuccess::new)
        .onErrorResume(ex -> Mono.just(
            new QuoteFailure("PRICING_FAILED", "Unable to quote")
        )),
    16
);
```

This is a **partial-result contract**; use it only if callers accept that individual items can fail independently. Never swallow errors indiscriminately to return empty objects, as that hides incidents and corrupts data.

## 14. Retries and cancellation

Reactive publishers support cancellation when a subscriber cancels or a client disconnects; however, cancellation **does not guarantee** every external I/O operation stops immediately. With blocking JDBC/SDK calls, threads may keep running or resources remain held until the call finishes.

| Operation type | How to handle |
| --- | --- |
| Idempotent GET with transient network error | Bounded retries with backoff and jitter if contract allows |
| POST creating order/payment | Use an idempotency key; never retry blindly |
| HTTP 400 from invalid input | Do not retry the same payload |
| HTTP 429/503 | Respect throttling/`Retry-After` and retry budgets |
| Pool acquire timeout | Investigate saturation/concurrency before retrying |
| Broker redelivery | Account for both binder retries and in-function retries |

A reactive pipeline can use retry operators, yet retry count, backoff, and overall deadline must be explicitly configured. Never configure unbounded retries.

- Do not call `subscribe()` manually inside a function just to “kick it off”; return the publisher so the framework/adapter manages subscription.
- Do not spawn untracked background tasks and return success early if the contract requires completion.
- When a request is canceled, clean up resources and stop cancellable work.
- With event brokers, define ack/nack semantics when a subscription cancels.

## 15. Supplier and Consumer in both models

| Imperative | Reactive | Meaning |
| --- | --- | --- |
| `Supplier<T>` | `Supplier<Flux<T>>` | Supplies a single value or stream |
| `Function<I,O>` | `Function<Flux<I>,Flux<O>>` | Transforms a request or stream |
| `Consumer<T>` | `Consumer<Flux<T>>` | Processes an event or stream |

Example reactive supplier:

```java
@Bean
public Supplier<Flux<QuoteResult>> quoteFeed(WebClient client) {
    return () -> client.get()
        .uri("/v1/quote-feed")
        .retrieve()
        .bodyToFlux(QuoteResult.class);
}
```

This example assumes the endpoint emits a stream compatible with the decoder; how the supplier is triggered depends on the adapter. Do not assume every adapter subscribes with identical semantics.

Example reactive consumer:

```java
@Bean
public Consumer<Flux<AuditEvent>> auditEvents(
    AuditService auditService
) {
    return events -> events.concatMap(auditService::store);
}
```

Here `AuditService.store(...)` must return a reactive publisher such as `Mono<Void>`. `concatMap` processes sequentially to preserve order. If the store uses blocking JDBC, never call it directly on the event loop.

## 16. WebFlux and MVC are separate adapter choices

Do not confuse:

- **Imperative/reactive function signature:** how the function handles inputs/outputs.
- **Web MVC/WebFlux adapter/runtime:** how the HTTP server receives requests and sends responses.
- **Outbound `RestClient`/`WebClient`:** how the function calls external services.

A WebFlux app can still invoke blocking libraries; blocking I/O does not automatically become non-blocking. Imperative functions can also be used in apps with reactive components, provided you understand which thread executes them and whether they block an event loop.

When exposing Spring Cloud Function over HTTP, verify that your adapter/version supports the chosen function signature and codecs. When running over Spring Cloud Stream, verify binder concurrency, poller/prefetch, batching, ack, and retry settings. On serverless, verify the handler/event model and platform execution limits.

## 17. Choosing a model by workload type

| Real-world condition | What to try | What to verify |
| --- | --- | --- |
| CPU-bound, minimal I/O | Imperative or bounded CPU scheduler | CPU saturation, throughput, allocation |
| JDBC/JPA, synchronous transactions | Imperative; virtual threads if suitable | Pool connections, blocking concurrency, transactions |
| Non-blocking outbound HTTP, many waiting requests | Reactive WebClient | Event loop, pool, pending queue, p99 |
| Long streams or time-series data | Reactive Flux | Backpressure at every boundary, cancellation, memory |
| Low traffic, simple logic | Imperative | Latency and operational overhead |
| SDK offers blocking API only | Imperative or isolate blocking | Scheduler/thread limits, timeouts, cancellation |
| Coordinating multiple non-blocking APIs | Reactive | Error/cancellation/context propagation |
| Fixed-size batches | Either | Batch size, concurrency, memory, and partial failures |
| Team inexperienced with Reactor | Imperative first if SLOs are met | Learning/debugging cost and maintainability |

**Pick the simplest model that meets SLOs and resource budgets.** If imperative meets throughput, p95/p99, and memory targets with appropriate thread/virtual-thread settings, do not rewrite to reactive merely because the app handles many requests.

If the workload is genuinely I/O-bound with high concurrency, long streams, and non-blocking downstream libraries, reactive is worth benchmarking because it can reduce waiting threads and manage backpressure better.

## 18. Fair performance benchmarking

A sound benchmark must compare identical work:

1. Same logic and validation.
2. Same request/response schemas, payload sizes, and downstream behavior.
3. Same JDK, Spring Boot, Spring Cloud Function, CPU/memory, and adapters.
4. Same concurrency, arrival rate, warm-up duration, and test length.
5. Same connection pool limits, timeouts, and retry policies.
6. Measure error rates, timeouts, and cancellations as well.

| Metric | Meaning |
| --- | --- |
| Throughput (req/s) | Completed requests per second |
| p50/p95/p99 latency | Latency distribution, especially the tail |
| Error/timeout rate | Failures under load, not just successful calls |
| Active threads | Is the thread pool saturated? |
| Event-loop utilization | Is the reactive I/O loop being blocked? |
| Connection pool active/idle/pending | Is outbound I/O bottlenecked? |
| CPU utilization | Is the workload CPU-bound or thread-waiting? |
| Heap/allocation/GC | Object allocation cost and pauses |
| Queue depth/consumer lag | Is upstream piling up work? |
| Cancellation/retry count | Is work being aborted or amplified? |

A single `curl` verifies endpoints and contracts, not behavior under high concurrency. Use load tests with controlled arrival rates/concurrency, adequate warm-up, and multiple runs. Never compare an imperative run on an idle machine against a reactive run while CPU is busy elsewhere.

### Micrometer measuring a synchronous function

```java
import java.util.function.Function;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

@Bean("quoteTimed")
public Function<QuoteRequest, QuoteResult> quoteTimed(
    @org.springframework.beans.factory.annotation.Qualifier("quoteBlocking")
    Function<QuoteRequest, QuoteResult> delegate,
    MeterRegistry registry
) {
    Timer timer = Timer.builder("app.quote.duration")
        .tag("mode", "imperative")
        .register(registry);

    return request -> timer.record(
        () -> delegate.apply(request)
    );
}
```

The timer measures the full completion time of the synchronous delegate, including blocking I/O inside it. The example assumes `MeterRegistry` and `quoteBlocking` beans exist; `@Qualifier` avoids ambiguity if multiple functions share the same type.

### Micrometer measuring reactive completion

```java
import java.util.function.Function;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import reactor.core.publisher.Flux;

@Bean("quoteReactiveTimed")
public Function<Flux<QuoteRequest>, Flux<QuoteResult>>
        quoteReactiveTimed(
            @org.springframework.beans.factory.annotation.Qualifier("quoteReactive")
            Function<Flux<QuoteRequest>, Flux<QuoteResult>> delegate,
            MeterRegistry registry
        ) {
    Timer timer = Timer.builder("app.quote.stream.duration")
        .tag("mode", "reactive")
        .register(registry);

    return input -> Flux.defer(() -> {
        Timer.Sample sample = Timer.start(registry);
        return Flux.defer(() -> delegate.apply(input))
            .doFinally(signal -> sample.stop(timer));
    });
}
```

This timer measures the **entire stream subscription**, stopping on complete/error/cancel. For long-lived streams, total duration is less useful per request; measure per-item latency or time to first item. In real applications, ensure only one instrumentation layer records the same metric to avoid double counting.

### Microbenchmarks and load tests answer two different questions

- **JMH:** measures local code, operator, or algorithm cost under controlled conditions.
- **Load test:** measures end-to-end API/broker behavior, networking, queues, concurrency, backpressure, and errors.

Never use microsecond JMH numbers to claim production HTTP p99.

## 19. Hypothetical results matrix example

Suppose the same API calls a pricing service under an I/O-bound workload. The numbers below are **illustrative only**, not Spring Cloud Function benchmarks:

| Metric | Imperative thread pool | Imperative virtual threads | Reactive WebClient |
| --- | ---: | ---: | ---: |
| Throughput | 700 req/s | 900 req/s | 1,050 req/s |
| Warm p95 | 180 ms | 145 ms | 125 ms |
| Warm p99 | 420 ms | 330 ms | 290 ms |
| CPU | 42% | 44% | 38% |
| Peak threads | 220 | 55 platform + virtual tasks | 24 event-loop/scheduler threads |
| Error rate | 0.1% | 0.1% | 0.1% |

You cannot conclude from this table that reactive is always better. Results shift when downstream caps concurrency, workloads are CPU-bound, reactive code hides blocking calls, schedulers/event loops are misconfigured, or networking dominates latency.

A choice succeeds only when it **meets performance budgets, error budgets, maintainability, and operational requirements**.

## 20. Common migration mistakes

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Low reactive throughput | Blocking JDBC/SDK on event loop | Use a non-blocking driver or isolate blocking work |
| `Mono` does not execute | No subscriber | Return publisher for adapter to manage; tests must subscribe |
| Calling `subscribe()` inside function and returning early | Detaches work from request lifecycle | Return publisher and let framework manage it |
| Event loop blocked | `block()`, JDBC, file I/O | Never block on the event loop |
| Memory grows under load | Unbounded queues/pending work/buffers | Bound concurrency and queues |
| Flux outputs arrive out of order | `flatMap` completes out of input order | Use `concatMap` or `flatMapSequential` |
| One error aborts entire batch | Flux terminal error signal | Define partial-result or batch-failure contract |
| Transaction fails to cover all operations | Imperative manager used inside reactive chain | Pick the matching transaction manager |
| Security/MDC context lost | Relied on `ThreadLocal` across async boundary | Use proper context propagation |
| Retries create duplicate data | Non-idempotent POST | Use idempotency keys and retry budgets |
| Good p50 but bad p99 | Queueing, pool saturation, bursts | Monitor tail latency and pending counts |
| Virtual threads remain slow | DB pool/downstream is the bottleneck | Bound concurrency and measure I/O |
| Complex reactive code with no gain | Low load or CPU-bound workload | Keep imperative if it meets SLOs |

## 21. Selection and migration roadmap

1. **Classify the workload:** CPU-bound, blocking I/O, non-blocking I/O, stream, or batch.
2. **Record baseline:** throughput, p50/p95/p99, errors, threads, pools, CPU, heap, and GC.
3. **Identify bottlenecks:** function logic, JSON conversion, database, HTTP, broker, or queues.
4. **Pick the right imperative variant:** existing thread pool or virtual threads when supported by runtime.
5. **Try reactive only with clear justification:** heavy non-blocking I/O, streaming, or high concurrency.
6. **Inventory every blocking call** in the pipeline; do not look only at the `Flux` signature.
7. **Bound concurrency/backpressure/pools** and set downstream deadlines.
8. **Test transactions, security context, cancellation, retries, and error mapping.**
9. **Load test with identical adapters and payloads**, never comparing a core function against an end-to-end endpoint.
10. **Keep the simplest model meeting SLOs**, preserving results and config for rollback if needed.

### Pre-decision checklist

- [ ] Know whether most time goes to CPU or I/O.
- [ ] Know whether downstream libraries are blocking or non-blocking.
- [ ] Measured p95/p99 and error rates under load.
- [ ] Calculated replica counts, pool sizes, and total concurrency.
- [ ] Bounded queues and pending work.
- [ ] Verified transaction managers and context propagation.
- [ ] Verified cancellation, retries, and idempotency.
- [ ] Confirmed adapters support the chosen function signature.
- [ ] Measured cold/first/warm if deploying on serverless.
- [ ] Compared operational cost and team complexity.

## 22. Practice exercises

**Exercise 1 — CPU or I/O?** A function reads 3 JDBC tables, sums totals, and returns JSON. Should you switch to reactive solely because concurrency is high?

*Answer:* Not yet. JDBC is blocking. Measure DB time, transactions, pools, and concurrency first; imperative with an appropriate pool/virtual threads may work well. Reactive helps only if replaced with a reactive driver and non-blocking pipeline or properly isolated blocking calls.

**Exercise 2 — Mono.fromCallable.** Why isn't `Mono.fromCallable(() -> jdbc.find(id))` enough by itself to avoid blocking the event loop?

*Answer:* It defers the callable, yet still runs on the subscribing scheduler unless specified; isolate blocking work onto a suitable scheduler or change the driver.

**Exercise 3 — FunctionCatalog.** Does changing `spring.cloud.function.definition=quoteBlocking` to `quoteReactive` automatically switch execution to non-blocking?

*Answer:* No. You must register a reactive function returning publishers, use non-blocking clients, and run on compatible adapters.

**Exercise 4 — Backpressure.** Does `flatMap(callRemote, 16)` mean the entire application makes at most 16 outbound requests?

*Answer:* No. It bounds inner publishers within a single subscription/pipeline; other invocations and replicas can still run concurrently.

**Exercise 5 — Preserving order.** Twenty requests need concurrent API calls while outputs must preserve input order. Which operators can you consider?

*Answer:* `flatMapSequential(..., concurrency)` processes concurrently while emitting results in source order; `concatMap` preserves order via sequential execution.

**Exercise 6 — Virtual threads.** Does enabling virtual threads let a database accept unlimited connections?

*Answer:* No. The JDBC pool and database capacity still constrain concurrency; virtual threads only change the cost of holding a thread while waiting.

**Exercise 7 — Transactions.** A reactive function calls a JDBC repository inside `flatMap` and uses imperative `@Transactional`. Can you assume the transaction spans the publisher?

*Answer:* No. Synchronous transaction managers typically bind resources to threads; reactive chains need a compatible reactive transaction manager and context.

**Exercise 8 — Flux errors.** One out of 100 items fails in the pricing API. Are the other 99 results always emitted?

*Answer:* No. An error from one inner publisher can terminate the entire `Flux` depending on operator/policy. For partial results, model errors as values or isolate per item.

**Exercise 9 — Retrying POST.** A payment creation API times out. Should you configure three automatic retries in the reactive pipeline?

*Answer:* Only if the idempotency contract guarantees safety, e.g., an idempotency key and retry budget; otherwise it can create duplicate payments.

**Exercise 10 — Little's Law.** Throughput is 200 req/s and average time in the downstream call segment is 0.25 s. What is the estimated average in-flight count?

*Answer:* `L = 200 × 0.25 = 50` requests. This is an average over the measured interval, not an exact pool configuration.

**Exercise 11 — Event loop.** A reactive function calls `WebClient` and then calls `block()` to get the response before returning. What can happen?

*Answer:* The event loop gets blocked waiting, stalling other requests and hurting throughput. Keep the publisher reactive and return it to the framework.

**Exercise 12 — Decision.** An imperative API using JDBC and virtual threads already meets its p99 SLO, has simple code, and needs no streaming. Should you migrate it to reactive?

*Answer:* No compelling reason. Keep the current model while it satisfies SLOs, resource limits, and operations; migrate only when workload/bottleneck evidence justifies it.

## 23. Key takeaways

- **Synchronous returns results directly; reactive returns a publisher executed upon subscription.**
- **Reactive does not make work faster on its own**; primary gains come from non-blocking I/O, controlled concurrency, and streaming.
- **CPU-bound work is not accelerated merely by `Mono`/`Flux`**; optimize algorithms and bound CPU parallelism.
- **Blocking JDBC/JPA and blocking SDKs still block** when wrapped in a reactive pipeline; isolate them with a suitable scheduler or choose non-blocking drivers.
- **Virtual threads are worth evaluating for blocking workloads** on JDK 21+ and compatible Spring Boot, though they do not remove connection pool/downstream limits.
- **Backpressure inside a publisher chain is not guaranteed end-to-end across every adapter/broker**; bound concurrency, queues, and prefetch at each boundary.
- **Transactions, security context, tracing, cancellation, and error semantics differ** between imperative and reactive; test thoroughly when migrating.
- **Measure the same end-to-end path**: throughput, p50/p95/p99, error rates, threads/pools, CPU, heap, and queues.
- **Pick the simplest model meeting SLOs** and workload characteristics; never switch to reactive solely for trends.

**References:**

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Streams — Specification](https://www.reactive-streams.org/)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Boot — Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)

These examples help design and compare both execution models. When deploying, verify exact Spring Cloud Function, Boot, Reactor, adapter, and database driver versions; measure on representative workloads while preserving business contracts and resource limits.
