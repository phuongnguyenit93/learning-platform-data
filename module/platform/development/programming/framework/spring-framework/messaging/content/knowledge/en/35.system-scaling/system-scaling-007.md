# Receiver-Side Concurrency Limits, Buffers, and Maximum Load

As producers and clients scale up, a message receiver can receive more requests than its database, HTTP client, thread pool, or the application itself can process. Without bounds, requests accumulate, queues grow, memory is consumed, and latency spreads. A messaging system may continue receiving messages while no longer having enough resources to process them safely.

Receiver-side load design must control three quantities simultaneously:

- **Concurrency:** number of tasks being processed at the same time.
- **Buffer/queue:** number of messages waiting to be processed.
- **Rate:** number of messages or requests accepted per unit of time.

These three quantities solve different problems. Concurrency limits protect active resources; buffer limits protect memory and wait times; rate limits prevent a producer from sending too fast over a sustained period. Backpressure lets the source adjust to receiver demand when both sides support Reactive Streams.

## 1. Why Does the Receiver Need Load Limits?

A handler may return `Mono` or `Flux`, but that does not mean the application can handle an infinite number of requests. Each request can still consume:

- A database or HTTP client connection.
- Memory to hold payloads, context, intermediate results, and responses.
- CPU to deserialize, validate, and run business logic.
- A slot in a thread pool or scheduler if blocking work is involved.
- A slot in a queue when downstream is slow.
- Broker, socket, and transport resources.

For example, a database connection pool may have only 30 connections. If the server runs 300 concurrent handlers that all query the database, most handlers will wait for a connection. That waiting still consumes memory, increases processing time, and can trigger timeouts across multiple layers.

An overload cascade typically unfolds as follows:

1. Producers emit messages faster than processing speed.
2. Messages arrive at the receiver and wait on downstream resources.
3. Queues or in-flight request counts grow.
4. Latency rises, and timeouts and retries appear.
5. Retries add even more load while downstream is still overloaded.
6. Memory, connections, or thread pools are exhausted and the system becomes unavailable.

Load limits must be placed before expensive resource consumption points. Limiting thread counts only at the end of a pipeline may be insufficient if the application has already accepted and buffered too many payloads upstream.

## 2. Distinguishing Concurrency, Rate Limit, Backpressure, and Buffers

| Mechanism | What Does It Limit? | Question Answered |
|---|---|---|
| Concurrency limit / bulkhead | Number of simultaneously running operations | How many requests are processed concurrently? |
| Rate limit | Number of requests allowed to start in a time window | How many requests per second may a client send? |
| Backpressure | Demand sent backward from subscriber to publisher | How many more items does the consumer currently want? |
| Buffer/queue limit | Number of items held waiting for processing | How many messages are allowed to queue up? |
| Timeout/deadline | Maximum wait or processing duration | How long is a request allowed to wait? |
| Circuit breaker | Ability to call a failing dependency | When should calls to downstream pause temporarily? |

Do not use one mechanism as a substitute for all the others. For example:

- Backpressure does not by itself limit the number of independent requests multiple clients can open.
- A concurrency limit does not stop a producer from continuously sending a new request as soon as the previous one finishes.
- A rate limit does not cap the number of in-flight requests if each request takes a long time.
- A buffer does not increase processing capacity; it only holds waiting messages and must be bounded.
- A timeout cannot free resources if the underlying blocking library does not support cancellation.

A stable receiver typically combines concurrency limits, bounded buffers, appropriate rate limits, timeouts, and rejection or load-shedding mechanisms.

## 3. Backpressure in Reactive Streams and RSocket

Reactive Streams defines a demand mechanism: a subscriber requests a number of items from a publisher via a subscription. The publisher should emit only up to the requested demand.

In Reactor, subscribers can request data using operators or request-control APIs. With RSocket, Request-Stream and Channel convey flow control through `REQUEST_N` frames. The requester announces how many items it wants to receive; the responder regulates emission according to demand.

This prevents a responder from pushing unbounded items into a client that cannot consume them fast enough.

However, distinguish carefully:

- `REQUEST_N` controls the number of items within one stream.
- It is not a global limit on the number of streams or concurrent requests the server accepts.
- A client can still open many independent streams.
- Request-Response has only one response per request; limiting total concurrent requests must still happen at the application layer.
- Fire-and-Forget does not provide the same demand model as a response stream; the server must still bound the work triggered by requests.

Example responder returning a stream:

~~~java
@Controller
class InventoryController {

    @MessageMapping("inventory.watch")
    Flux<InventoryUpdate> watch(InventoryRequest request) {
        return inventoryService.watch(request.sku());
    }
}
~~~

The requester can control demand when subscribing:

~~~java
Flux<InventoryUpdate> updates = requester
    .route("inventory.watch")
    .data(request)
    .retrieveFlux(InventoryUpdate.class);
~~~

When the consumer requests fewer items, flow control can slow emission down. This is an essential mechanism for Request-Stream and Channel, yet the server must still control subscription counts, stream creation cost, and load on the data source.

Do not assume every Spring Messaging transport provides end-to-end Reactive Streams backpressure. RSocket has protocol-level flow control. With STOMP, WebSocket, or a specific broker, adapters and brokers may have their own buffering, prefetch, or acknowledgement mechanisms. Verify the capabilities of the actual transport in use.

## 4. Limiting Concurrency in a Reactor Pipeline

The **`flatMap`** operator accepts a concurrency parameter to limit how many inner publishers are subscribed to simultaneously within a single subscription.

~~~java
Flux<EnrichedOrder> enriched = Flux.fromIterable(orderIds)
    .flatMap(
        id -> orderService.loadAndEnrich(id),
        8
    );
~~~

With concurrency set to 8, this pipeline runs at most eight inner operations at once. When one operation finishes, the pipeline can subscribe to the next operation.

You can also pass a prefetch value to adjust how many items are requested upfront from each inner publisher:

~~~java
Flux<Result> results = requests.flatMap(
    request -> remoteService.call(request),
    8,
    1
);
~~~

In this example, up to eight inner publishers are processed concurrently and the prefetch per inner publisher is one item. Actual values should be chosen based on processing cost and downstream capacity.

Other operators:

- **`concatMap`:** processes items sequentially one at a time, subscribing to the next inner publisher only after the previous one completes.
- **`flatMapSequential`:** allows inner publishers to run concurrently while preserving output emission order to match input order.
- **`parallel`:** splits work into rails for CPU-bound processing; not a system-wide request-limiting mechanism.

Important: `flatMap` concurrency is scoped to a single subscription. If there are 100 clients, each with a `flatMap` pipeline of concurrency 8, total inner operations can still reach 800. To enforce a global limit, use shared admission control or a bulkhead at the service/application level.

## 5. Limiting Concurrent Requests on the Receiver Side

With an RSocket annotated controller, you can enforce a global or per-operation-group limit before calling an expensive service. The example below uses a non-blocking `Semaphore` to cap active reactive operations at 64:

~~~java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Mono;

@Controller
class ReportController {

    private final Semaphore permits = new Semaphore(64);
    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @MessageMapping("reports.generate")
    Mono<Report> generate(ReportRequest request) {
        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                return Mono.error(
                    new RejectedExecutionException(
                        "Receiver is at capacity"
                    )
                );
            }

            return Mono.defer(() -> reportService.generate(request))
                .doFinally(signal -> permits.release());
        });
    }
}
~~~

How it works:

1. **`Mono.defer`** delays acquiring a permit until the request is actually subscribed to.
2. **`tryAcquire`** does not block the thread. If no permits remain, the request is rejected immediately.
3. Once a permit is acquired, the reactive service is invoked.
4. **`doFinally`** releases the permit when the publisher completes, errors, or receives cancellation.
5. Once the operation finishes, another request can use the returned permit.

This is a fail-fast example: there is no queue waiting for permits. This fits when clients can handle overload errors and retry under a bounded policy.

The service in the example returns `Mono` and must respect cancellation. If calling an un-cancellable blocking API, subscriber cancellation may happen before the blocking work actually stops. In that case, do not treat `doFinally` execution as the moment physical resources were freed. Configure timeouts in the blocking client and use bounded executors/bulkheads to control the running tasks themselves.

### Fail-Fast or Wait in a Queue?

There are two common policies:

- **Fail-fast:** when permits run out, return an overload error immediately. The advantage is avoiding extra queueing; clients can back off and retry.
- **Bounded wait queue:** allow a finite number of requests to wait for permits. Bound both item count and wait time; reject when the queue is full or the deadline expires.

Do not use an unbounded queue to make the system appear to accept every request. The longer the queue, the staler requests are when processed and the more likely they will miss business deadlines.

## 6. Bulkheads by Dependency and by Tenant

A single global limit can prevent server overload, yet still fail to protect individual dependencies. For instance, reporting holds database connections longer than an order-lookup API. If both share the same pool and the same semaphore, reporting tasks can starve lookup capacity.

Bulkheads isolate resources by group:

- Dedicated limit for database queries.
- Dedicated limit for payment services.
- Dedicated limit for report generation tasks.
- Dedicated limit per tenant or client when fairness is needed.

For example, keep a separate semaphore per dependency or use a bulkhead library such as Resilience4j. Each bulkhead needs a cap and an overflow policy: reject, wait in a bounded queue, or return an appropriate fallback.

Per-tenant limits prevent one heavy customer from monopolizing total system capacity. When implementing them, bound the number of limiters created to avoid unbounded maps keyed by tenant ID.

Do not use one shared semaphore for the entire application if request types vary greatly in duration and priority. Partition by the downstream resources each operation actually consumes.

## 7. Bounded Buffers and Overflow Policies

Buffers are helpful when producer and consumer speeds fluctuate differently. But buffers must be bounded.

With backpressure-compliant sources, prefer letting demand propagate back to the source rather than adding large buffers. With hot sources or callback APIs that cannot pause emission, a buffer may be needed to absorb short bursts.

Example capping a buffer at 256 items and erroring when full:

~~~java
Flux<Event> buffered = hotEventSource
    .onBackpressureBuffer(
        256,
        dropped -> metrics.counter("events.buffer.overflow").increment(),
        BufferOverflowStrategy.ERROR
    );
~~~

Choose a policy based on data semantics:

| Policy | Behavior | When Appropriate |
|---|---|---|
| `ERROR` | Emits an error when buffer is full | Silent data loss is unacceptable |
| `DROP_OLDEST` | Discards the oldest item | Only the most recent data matters |
| `DROP_LATEST` | Discards the newly arriving item | Preferring to keep the existing backlog |
| `LATEST` | Retains only the latest value | Replaceable snapshot state or telemetry |
| Bounded queue + reject | Rejects when queue hits its limit | Commands needing explicit overload feedback |

Drop strategies are appropriate only when the business domain tolerates losing updates. Do not use drop policies for payment commands, order creation, or events requiring preservation unless another storage/replay mechanism exists.

Monitor queue depth, overflow counts, queue wait time, and oldest message age. Looking solely at processed message counts will not reveal a rapidly growing queue.

## 8. Prefetch and Concurrency Limits in JMS Listeners

In JMS, consumer concurrency is configured on the listener container. Spring supports the **`concurrency`** attribute on **`@JmsListener`** when the underlying container supports it.

Example:

~~~java
@Component
class OrderConsumer {

    @JmsListener(
        destination = "orders.commands.submit",
        concurrency = "3-10"
    )
    public void handle(SubmitOrderCommand command) {
        orderService.submit(command);
    }
}
~~~

The **`3-10`** setting asks the listener container to maintain concurrency between three and ten consumers according to container capabilities. Actual consumer counts, scaling behavior, and session allocation depend on the listener container type and provider.

When raising concurrency, check:

- Whether the database connection pool can serve all consumers.
- Whether the broker has enough resources for the configured consumers and prefetch.
- When acknowledgements and transactions occur.
- Whether messages can be redelivered if a listener fails.
- Whether processing order is required by business rules.

Increasing consumers can boost throughput until another dependency becomes the bottleneck. Beyond that point, raising concurrency only increases contention and latency.

Prefetch is the number of messages a broker can deliver ahead to a consumer or channel per provider configuration. Overly large prefetch can leave messages sitting in consumer memory and cause uneven distribution across consumers. Overly small prefetch can reduce throughput due to round trips. Configure per your specific broker and test with realistic load.

## 9. STOMP and WebSocket: Controlling Load at Broker and Application

In STOMP over WebSocket, clients can send messages to application destinations and subscribe to broker destinations. Spring's simple broker provides basic subscription and broadcast support, yet not all flow-control, acknowledgement, prefetch, or persistence features of a dedicated message broker are available.

Under heavy load, consider:

- Using a broker relay to a dedicated broker when scalability and queue management are needed.
- Configuring connection, subscription, and frame-size limits at the transport/broker layer.
- Bounding the number of requests accepted by application handlers.
- Using bounded executors and task queues for inbound/outbound channels when appropriate.
- Setting message size limits and validating payloads before deep deserialization.
- Defining a policy when clients send faster than processing speed.

Do not assume a prefix such as `/topic` or `/queue` automatically creates load limits or queue semantics in the simple broker. Prefixes are primarily destination conventions; actual behavior depends on the broker and Spring configuration.

## 10. Rate Limiting and Inbound Rate Control

A concurrency limit controls how many operations run simultaneously; a rate limit controls how many operations start per unit of time.

For example, an API may handle at most 50 concurrent requests and still get overwhelmed if a producer continuously fires 10,000 very fast requests per second. A rate limiter caps admission rate by policy.

Common algorithms:

- **Token bucket:** tokens replenish at a fixed rate; allows bursts up to bucket capacity.
- **Leaky bucket:** processes or emits requests at a steady rate, smoothing bursts.
- **Fixed window:** counts requests per time window; simple, though bursts can occur across window boundaries.
- **Sliding window:** counts requests over a sliding window to reduce boundary effects.

Rate limits can apply per API, tenant, user, IP, or message type. Avoid relying solely on IP when many users share NAT or proxies.

If using Resilience4j `RateLimiter`, configure `limitForPeriod`, `limitRefreshPeriod`, and `timeoutDuration` appropriately. In multi-instance systems, an in-memory limiter per instance does not automatically enforce a cluster-wide quota; use a shared quota mechanism or per-instance quota allocation.

When rejecting due to a rate limit, return a recognizable error and optionally a retry-after interval. Do not retry immediately upon rate-limiting because that worsens bursts.

## 11. Sizing Limits from Actual Capacity

Do not pick concurrency solely from CPU counts or default thread counts. Measure processing times, dependency usage, and resource limits.

Little's Law provides a useful relationship:

\[
L = \lambda W
\]

Where:

- \(L\) is the average number of requests currently in the system.
- \(\lambda\) is average throughput, in requests per second.
- \(W\) is the average time a request spends in the system, in seconds.

For example, if the system processes 120 requests/second and average processing time is 0.15 seconds:

\[
L = 120 \times 0.15 = 18
\]

On average, roughly 18 requests are active. This is a steady-state average, not a recommended maximum concurrency configuration. When choosing limits, also consider p95/p99 latency, bursts, downstream capacity, queueing delay, and headroom.

A sizing workflow:

1. Measure throughput and latency for each operation type.
2. Identify the slowest dependency and its connection pool.
3. Measure CPU, heap, threads, connections, and queue depth as load increases.
4. Step up concurrency incrementally to find where throughput saturates.
5. Set limits below the saturation point to preserve headroom.
6. Run burst tests and soak tests to detect creeping backlogs.
7. Set queue limits and maximum wait times from business deadlines.

For example, a database with 40 connections does not mean setting 40 requests system-wide if one request opens multiple connections or other operations share the pool. Account for total connections holdable by all consumers combined.

## 12. Deadlines and Queue Wait Times

A request can miss its business deadline before its turn to execute arrives. Therefore, queues need not only size bounds but also wait-time bounds.

Example of a request with a total three-second deadline:

~~~java
Mono<Result> result = admissionControl.submit(request)
    .timeout(Duration.ofSeconds(3));
~~~

If admission control includes a queue, the timeout should cover both permit wait time and processing time, or the system must distinguish the two deadlines explicitly.

Reject expired messages before consuming expensive resources. If messages carry producer timestamps or deadlines, use a trusted time source, account for clock skew, and never trust arbitrary client-supplied timestamps when they affect resource access.

For durable messages in a broker, rejection may trigger redelivery. Have retry, dead-letter, and poison-message policies so invalid messages are not redelivered endlessly.

## 13. Testing Concurrency Limits and Buffers

Tests must verify limits actually hold under concurrent load, not just that a single request succeeds.

Example testing `flatMap` concurrency:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ConcurrencyTest {

    @Test
    void shouldLimitConcurrentInnerOperations() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Flux.range(1, 20)
                    .flatMap(
                        item -> Mono.defer(() -> {
                            int current = active.incrementAndGet();
                            maximum.accumulateAndGet(current, Math::max);

                            return Mono.delay(Duration.ofSeconds(1))
                                .thenReturn(item)
                                .doFinally(signal ->
                                    active.decrementAndGet()
                                );
                        }),
                        4
                    )
            )
            .thenAwait(Duration.ofSeconds(5))
            .expectNextCount(20)
            .verifyComplete();

        assertTrue(maximum.get() <= 4);
        assertEquals(0, active.get());
    }
}
~~~

The test emits 20 items and caps concurrent inner operations at four. Virtual time verifies delayed operations without waiting five real seconds.

This tests concurrency within one subscription. To test a global limiter, run multiple concurrent subscriptions sharing the same limiter and assert total active operations never exceed the cap.

Other tests should cover:

- Requests rejected with the expected error when permits are exhausted.
- Permits returned after both completion and error.
- Cancellation releasing permits when operations actually stop.
- Buffers overflowing according to the configured policy when full.
- Rate limiters allowing the exact expected request count per window.
- Tenant A unable to exhaust tenant B's quota.
- Queue wait timeouts firing before total request deadlines expire.
- Retries not bypassing configured concurrency or rate limits.

## 14. Observability and Operations Under Overload

Collect metrics to see when a receiver approaches its limits:

- Active operation count and remaining permits.
- Requests rejected due to concurrency or rate limits.
- Queue depth, queue wait time, and oldest message age.
- Buffer overflows, dropped message counts, and redelivered counts.
- Throughput by route, destination, tenant, and message type.
- Handler and dependency p50, p95, and p99 latency.
- Active connections in database/HTTP pools.
- Timeouts, retries, open circuit breakers, and downstream errors.

Logs should include correlation ID, normalized route or destination, tenant ID where permitted, and rejection reason. Never log sensitive payloads or credentials.

Under overload, respond in order:

1. Stop admitting work beyond capacity via admission control.
2. Keep queues bounded and reject or dead-letter messages per policy.
3. Dampen synchronized retries with backoff and jitter.
4. Protect dependencies with bulkheads and circuit breakers.
5. Drain backlogs safely after dependencies stabilize.
6. Verify throughput and latency return to normal levels.

Do not automatically raise concurrency every time a queue grows. If the database is already saturated, adding workers worsens contention and latency.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using only `flatMap` concurrency to limit the whole server | Each subscription has its own limit; total load still grows with clients | Use a global limiter or shared bulkhead |
| Assuming RSocket `REQUEST_N` limits concurrent requests | `REQUEST_N` controls items within a stream, not total streams | Add responder-side admission control |
| Using unbounded buffers | Heap grows until the system destabilizes | Use bounded queues and an overflow policy |
| Raising consumer concurrency without measuring downstream | Database or HTTP pools become overloaded | Size by bottleneck and measure under load |
| Using only rate limits | Slow requests can still pile up even if start rate is capped | Combine concurrency limits and timeouts |
| Using only concurrency limits | Large bursts can keep replacing finished requests continuously | Add rate limits if needed |
| Calling blocking semaphore `acquire` on an event loop | Blocks reactive processing threads | Use `tryAcquire` or an asynchronous limiter |
| Releasing permits while blocking tasks keep running | Physical tasks can exceed the limit | Manage cancellation and actual task lifecycles |
| Retrying immediately on overload | Causes a retry storm | Backoff, jitter, and retry caps |
| Using one queue for all operation types | Slow tasks block fast tasks | Separate bulkheads and queues by dependency |
| Not measuring queue wait time | Old messages can expire before processing | Track message age and deadlines |

## 16. Pre-Production Checklist

- [ ] Concurrency limits defined for each operation type.
- [ ] Shared admission control in place when bounding the entire receiver.
- [ ] Per-dependency and per-tenant limits considered.
- [ ] Reactive threads are never blocked waiting for permits.
- [ ] Cancellation and permit release semantics are clear.
- [ ] Buffers and queues have finite capacity.
- [ ] Overflow policies match data-preservation requirements.
- [ ] Backpressure is used where supported by transport and publisher.
- [ ] `requestN` is not confused with concurrent stream or request limits.
- [ ] Rate limits and concurrency limits are designed separately.
- [ ] Timeouts cover queue wait and operation deadlines.
- [ ] JMS concurrency and broker prefetch match downstream capacity.
- [ ] STOMP/broker relay behavior verified against actual semantics.
- [ ] Metrics cover active requests, queue depth, rejections, latency, and downstream pools.
- [ ] Burst, load, and soak tests have been executed.
- [ ] Retry, dead-letter, and idempotency policies exist for rejections and redeliveries.

## 17. References

- [Project Reactor Reference: Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html) — creating and consuming Publishers; demand and subscriptions.
- [Project Reactor API: Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) — `flatMap`, `concatMap`, `limitRate`, and backpressure operators.
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — Request-Stream, Channel, responders, and RSocket integration.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — `REQUEST_N` and protocol-level flow control.
- [Spring Framework Reference: JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html) — listener containers and concurrency configuration.
- [Resilience4j](https://resilience4j.readme.io/docs/bulkhead) — bulkheads, concurrency isolation, and rate limiting.
