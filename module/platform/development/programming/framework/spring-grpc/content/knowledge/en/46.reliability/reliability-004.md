# Bulkhead by client or method

In a Spring gRPC application, a single client often calls multiple RPC methods on the same dependency. If one method becomes slow or experiences a traffic spike, it can consume all threads and processing capacity meant for the remaining methods. A **bulkhead** limits the number of concurrent calls within each scope, isolating load and preserving capacity for critical work.

Bulkheads can be placed at two scopes:

- **By client/dependency:** a shared limit across all RPCs calling a downstream service.
- **By method:** each RPC method has its own limit so an expensive method cannot exhaust capacity for other methods.

Both scopes can be used together: a client-level bulkhead caps total calls to the dependency; method-level bulkheads enforce tighter caps for individual operations.

## 1. What does a bulkhead protect?

A bulkhead limits concurrency—the number of operations allowed to run simultaneously. When permits run out, new calls can be rejected immediately or wait for a configured duration. For gRPC clients using blocking stubs, a semaphore bulkhead is a straightforward choice: acquire a permit before the RPC and release it when the RPC finishes, including on error or deadline expiration.

A bulkhead differs from other reliability mechanisms:

| Mechanism | Purpose |
| --- | --- |
| Deadline | Bounds how long an RPC is allowed to run |
| Retry | Retries transient failures according to policy |
| Circuit breaker | Stops calling a dependency when error/slowness rates exceed thresholds |
| Bulkhead | Limits concurrent calls and isolates capacity |
| Load balancing | Selects a suitable backend for the call |

A deadline prevents a single call from holding resources indefinitely, while a bulkhead prevents too many calls from consuming resources at once. Both are needed when downstream latency fluctuates.

## 2. Choosing scope: client or method

Suppose `InventoryService` exposes two RPCs:

- `GetStock`: queries inventory, typically fast and high-frequency.
- `ReserveStock`: reserves stock, may check multiple conditions and require more resources.

Limits can be configured as follows:

| Bulkhead | Scope | Example limit |
| --- | --- | ---: |
| inventory-client | Total calls across InventoryService | 30 |
| inventory-get-stock | GetStock only | 12 |
| inventory-reserve-stock | ReserveStock only | 5 |

When `ReserveStock` receives many concurrent calls, it can occupy at most its 5 dedicated permits; `GetStock` calls can still use their own capacity, while the combined total of both methods remains capped by the 30 client-level permits.

Using only method-level bulkheads can still allow excessive total calls to the dependency if there are many methods. Using only a client-level bulkhead lets a single method consume nearly all shared permits. Combine both layers when a dependency has multiple operations with differing costs and priorities.

## 3. Configuring Resilience4j in Spring

With blocking gRPC stubs, use a semaphore bulkhead and set `maxWaitDuration` to zero so calls over the limit are rejected immediately:

~~~java
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryBulkheadConfiguration {

    @Bean("inventoryClientBulkhead")
    Bulkhead inventoryClientBulkhead() {
        BulkheadConfig config = BulkheadConfig.custom()
            .maxConcurrentCalls(30)
            .maxWaitDuration(Duration.ZERO)
            .build();
        return Bulkhead.of("inventory-client", config);
    }

    @Bean("inventoryGetStockBulkhead")
    Bulkhead inventoryGetStockBulkhead() {
        BulkheadConfig config = BulkheadConfig.custom()
            .maxConcurrentCalls(12)
            .maxWaitDuration(Duration.ZERO)
            .build();
        return Bulkhead.of("inventory-get-stock", config);
    }

    @Bean("inventoryReserveStockBulkhead")
    Bulkhead inventoryReserveStockBulkhead() {
        BulkheadConfig config = BulkheadConfig.custom()
            .maxConcurrentCalls(5)
            .maxWaitDuration(Duration.ZERO)
            .build();
        return Bulkhead.of("inventory-reserve-stock", config);
    }
}
~~~

The numbers above are illustrative only. Choose limits based on workers, connections, CPU, latency, and the dependency's throughput capacity. If the application runs multiple replicas, each process has its own bulkhead; cluster-wide concurrency can reach the per-process limit multiplied by the replica count. Never treat a local limit as a cluster-wide quota.

Set `maxWaitDuration` small or zero so excess requests fail fast. If waiting is permitted, wait time must fit within the RPC's overall deadline and must not exhaust the incoming server's thread pool.

## 4. Wrapping generated stubs with client- and method-level bulkheads

A gateway is the right place to enforce outbound limits consistently. The example below applies both the overall client bulkhead and the dedicated `GetStock` bulkhead:

~~~java
import io.github.resilience4j.bulkhead.Bulkhead;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;

public final class InventoryGateway {

    private final InventoryServiceGrpc.InventoryServiceBlockingStub stub;
    private final Bulkhead clientBulkhead;
    private final Bulkhead getStockBulkhead;
    private final Bulkhead reserveStockBulkhead;

    public InventoryGateway(
            InventoryServiceGrpc.InventoryServiceBlockingStub stub,
            @Qualifier("inventoryClientBulkhead")
            Bulkhead clientBulkhead,
            @Qualifier("inventoryGetStockBulkhead")
            Bulkhead getStockBulkhead,
            @Qualifier("inventoryReserveStockBulkhead")
            Bulkhead reserveStockBulkhead) {
        this.stub = stub;
        this.clientBulkhead = clientBulkhead;
        this.getStockBulkhead = getStockBulkhead;
        this.reserveStockBulkhead = reserveStockBulkhead;
    }

    public GetStockResponse getStock(GetStockRequest request)
            throws Exception {
        return clientBulkhead.executeCallable(() ->
            getStockBulkhead.executeCallable(() ->
                stub.withDeadlineAfter(2, TimeUnit.SECONDS)
                    .getStock(request)));
    }

    public ReserveStockResponse reserveStock(
            ReserveStockRequest request) throws Exception {
        return clientBulkhead.executeCallable(() ->
            reserveStockBulkhead.executeCallable(() ->
                stub.withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                    .reserveStock(request)));
    }
}
~~~

Calls acquire permits in client-then-method order. If the method bulkhead rejects, `executeCallable` at the client layer still releases its permit as execution unwinds out of the supplier. With zero wait duration, requests do not hold a client permit while waiting for a method permit.

Place the deadline inside the supplier so the RPC budget starts only once the call is allowed to proceed. If permit wait time must be accounted for, compute the deadline before entering the bulkhead and pass the remaining time to the stub; with `maxWaitDuration` set to zero, permit wait time is negligible.

Never create a new bulkhead per request. Bulkheads must be shared beans or instances per dependency/method so they actually cap aggregate concurrency.

## 5. Mapping bulkhead rejections to gRPC statuses

When a bulkhead runs out of permits, Resilience4j throws `BulkheadFullException` before the generated stub sends the RPC. If the current method is serving another caller, the edge service can translate the capacity rejection into a status matching the API contract:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import io.github.resilience4j.bulkhead.BulkheadFullException;

public final class CatalogGrpcService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    private final InventoryGateway inventoryGateway;

    public CatalogGrpcService(InventoryGateway inventoryGateway) {
        this.inventoryGateway = inventoryGateway;
    }

    @Override
    public void getAvailability(
            GetAvailabilityRequest request,
            StreamObserver<GetAvailabilityResponse> observer) {
        try {
            GetStockResponse stock = inventoryGateway.getStock(
                GetStockRequest.newBuilder()
                    .setSku(request.getSku())
                    .build());

            observer.onNext(GetAvailabilityResponse.newBuilder()
                .setSku(stock.getSku())
                .setAvailableQuantity(stock.getAvailableQuantity())
                .build());
            observer.onCompleted();
        } catch (BulkheadFullException rejected) {
            observer.onError(Status.RESOURCE_EXHAUSTED
                .withDescription("inventory concurrency limit reached")
                .asRuntimeException());
        } catch (io.grpc.StatusRuntimeException downstreamError) {
            observer.onError(downstreamError);
        } catch (Exception unexpected) {
            observer.onError(Status.INTERNAL
                .withDescription("inventory request failed")
                .asRuntimeException());
        }
    }
}
~~~

`RESOURCE_EXHAUSTED` fits when the API wants to signal exhausted quota/concurrency capacity. Some systems choose `UNAVAILABLE` to indicate the dependency temporarily cannot accept more load. Pick consistent semantics and document them for clients; never turn business errors like `NOT_FOUND` into bulkhead rejections.

Do not return internal exception messages to callers. Log the reason, bulkhead name, and method separately so operations can distinguish client-wide saturation from a specific method running out of permits.

## 6. Testing method bulkheads isolating concurrent calls

The test below holds one `GetStock` call in flight using a latch. The method bulkhead has only one permit, so the second call is rejected immediately and never reaches the dependency. The client-wide bulkhead has two permits to prove the method limit is what rejected the call:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.bulkhead.BulkheadFullException;
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class InventoryBulkheadTest {

    private Server server;
    private ManagedChannel channel;
    private ExecutorService clientExecutor;
    private CountDownLatch firstCallEntered;
    private CountDownLatch releaseFirstCall;
    private AtomicInteger dependencyCalls;
    private InventoryGateway gateway;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        firstCallEntered = new CountDownLatch(1);
        releaseFirstCall = new CountDownLatch(1);
        dependencyCalls = new AtomicInteger();
        clientExecutor = Executors.newSingleThreadExecutor();

        InventoryServiceGrpc.InventoryServiceImplBase service =
            new InventoryServiceGrpc.InventoryServiceImplBase() {
                @Override
                public void getStock(
                        GetStockRequest request,
                        StreamObserver<GetStockResponse> observer) {
                    dependencyCalls.incrementAndGet();
                    firstCallEntered.countDown();
                    try {
                        if (!releaseFirstCall.await(2, TimeUnit.SECONDS)) {
                            observer.onError(Status.DEADLINE_EXCEEDED
                                .asRuntimeException());
                            return;
                        }
                        observer.onNext(GetStockResponse.newBuilder()
                            .setSku(request.getSku())
                            .setAvailableQuantity(7)
                            .build());
                        observer.onCompleted();
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        observer.onError(Status.CANCELLED
                            .asRuntimeException());
                    }
                }
            };

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(service)
            .build()
            .start();
        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        Bulkhead clientBulkhead = Bulkhead.of(
            "inventory-client-test",
            BulkheadConfig.custom()
                .maxConcurrentCalls(2)
                .maxWaitDuration(Duration.ZERO)
                .build());
        Bulkhead getStockBulkhead = Bulkhead.of(
            "inventory-get-stock-test",
            BulkheadConfig.custom()
                .maxConcurrentCalls(1)
                .maxWaitDuration(Duration.ZERO)
                .build());
        Bulkhead reserveBulkhead = Bulkhead.of(
            "inventory-reserve-test",
            BulkheadConfig.custom()
                .maxConcurrentCalls(1)
                .maxWaitDuration(Duration.ZERO)
                .build());

        gateway = new InventoryGateway(
            InventoryServiceGrpc.newBlockingStub(channel),
            clientBulkhead,
            getStockBulkhead,
            reserveBulkhead);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        releaseFirstCall.countDown();
        if (clientExecutor != null) {
            clientExecutor.shutdownNow();
            assertTrue(clientExecutor.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void secondGetStockIsRejectedWhileFirstCallHoldsMethodPermit()
            throws Exception {
        GetStockRequest request = GetStockRequest.newBuilder()
            .setSku("SKU-42")
            .build();

        Future<GetStockResponse> firstCall =
            clientExecutor.submit(() -> gateway.getStock(request));

        assertTrue(firstCallEntered.await(1, TimeUnit.SECONDS));

        assertThrows(
            BulkheadFullException.class,
            () -> gateway.getStock(request));
        assertEquals(1, dependencyCalls.get());

        releaseFirstCall.countDown();
        GetStockResponse response = firstCall.get(2, TimeUnit.SECONDS);
        assertEquals("SKU-42", response.getSku());
        assertEquals(1, dependencyCalls.get());
    }
}
~~~

`directExecutor()` runs the handler on the first call's dispatch thread; the test submits the first call on a separate executor so the main test thread can still issue the second call. Latches enforce deterministic ordering: the first call has entered the server before the rejection assertion runs. Never use `Thread.sleep()` to simulate contention.

The test verifies three things: the first call holds the permit, the second call fails with `BulkheadFullException`, and the dependency receives only one request. Once the first call completes, the permit is released and the method can accept subsequent calls.

To test the **client-level bulkhead**, flip the limits in the fixture: give the client bulkhead one permit and the `GetStock` bulkhead two permits. Hold the first call in the server using the same two latches; the second call will be rejected immediately at the client bulkhead and the downstream counter remains one. Flipping the limits clearly identifies which layer is rejecting the call.

## 7. Semaphore bulkhead vs. thread-pool bulkhead

Resilience4j provides two primary isolation modes:

| Type | How it works | Best suited when |
| --- | --- | --- |
| Semaphore bulkhead | Limits concurrent calls via permits; creates no separate thread pool | Using blocking stubs or work that already has an appropriate executor |
| Fixed thread-pool bulkhead | Uses a bounded thread pool and queue | You want a dedicated worker pool per dependency or to isolate blocking work |

A semaphore bulkhead does not create threads. It only controls how many calls may enter. A fixed thread-pool bulkhead adds an executor/queue; a full queue can also reject calls. Do not create a large queue to hide a slow dependency because queued requests still consume memory and may expire their deadline while waiting.

With blocking stubs, a semaphore bulkhead is usually easy to reason about: the permit is held for the entire synchronous call. With async stubs or streaming RPCs, you must hold the permit until the terminal event (`onCompleted`, `onError`, or cancellation). Never wrap only the call initiation and release immediately when the method returns, because the stream would keep running unbounded.

## 8. Cancellation and deadlines must release permits

For blocking calls, `executeCallable` manages acquire/release across both success and exception paths. When a deadline expires or a call is cancelled, the blocking stub exits with an exception and the permit is returned. Ensure you never catch exceptions while managing a manual semaphore and forget to release it in a `finally` block.

For async calls, tie release to exactly one terminal callback. Avoid double-releasing if both cancellation and error callbacks pass through cleanup logic. When a caller cancels a stream, cancel the downstream call and release the permit once callback handling finishes.

Never let a call hold a permit while waiting in an unbounded queue. Configure downstream deadlines and bulkhead wait times shorter than the remaining deadline.

## 9. Avoiding bulkhead configurations that bottleneck the whole system

Common design mistakes:

- **Limits set too low:** valid requests are rejected frequently even though the dependency still has capacity.
- **Limits set too high:** the bulkhead no longer protects the dependency or worker pool.
- **One bulkhead shared across all dependencies:** errors or high load on one dependency drain permits needed by another dependency.
- **New bulkhead per request:** imposes no real aggregate limit.
- **Queue too long:** latency climbs and requests expire their deadlines before running.
- **Long waits in nested bulkheads:** calls hold an outer permit while waiting on an inner permit.
- **Ignoring replica count:** cluster-wide concurrency exceeds dependency capacity.

Measure actual concurrency, rejection rates, queue wait times, latency, and downstream call counts before tuning. If one method frequently rejects while other methods have spare capacity, consider raising that method's dedicated quota or shedding load on that operation; do not automatically raise the client-wide ceiling.

## 10. Integrating with circuit breakers and retries

Bulkheads, circuit breakers, and retries can all wrap the same RPC, but ordering affects resource usage and statistics:

- A bulkhead outside retry holds one permit for the entire logical operation, including backoff delays.
- Retry outside a bulkhead acquires/releases a permit per attempt, avoiding holding permits during backoff waits.
- The circuit breaker should observe real downstream failures; internal bulkhead rejections should not count as dependency failures by default.

Choose the order based on your goals and test attempt counts, held permits, and final statuses. With multi-attempt retries, the total deadline must cover backoff. Do not immediately retry `BulkheadFullException` because new requests only add load to an already busy system.

## 11. Metrics and observability

Monitor each bulkhead by dependency and method:

- Maximum permits, active permits, and available permits.
- Accepted call count and rejected call count.
- Permit wait duration if waiting is enabled.
- RPC latency and deadline-exceeded rate.
- Concurrency per method.
- Rate of `RESOURCE_EXHAUSTED` or `UNAVAILABLE` caused by admission policies.

Resilience4j provides an event publisher to record rejections:

~~~java
getStockBulkhead.getEventPublisher()
    .onCallRejected(event ->
        log.warn("GetStock bulkhead rejected a call: {}", event));
~~~

If using Micrometer integration, export metrics by dependency name and method. Avoid using user ID, SKU, or request ID as metric tags due to high cardinality; keep those values in controlled traces/logs.

## 12. Testing through the Spring application context

In-process tests verify that the gateway and bulkheads work together, but they do not prove Spring injected the right beans or production configuration. Add integration tests to:

- Start the application context with the dependency/method bulkhead beans.
- Verify `GetStock` and `ReserveStock` use their respective dedicated bulkheads.
- Keep one method busy and prove the other method is still accepted while client-wide capacity has permits left.
- Verify total calls to the same dependency do not exceed the client bulkhead.
- Verify `BulkheadFullException` is mapped to the public status required by the API contract.
- Verify metrics and graceful shutdown of channels/executors.

If using the `@Bulkhead` annotation, verify methods are invoked through the Spring proxy; self-invocation can bypass proxy advice. A gateway explicitly wrapping the generated stub generally makes permit scope and deadlines clearer.

## 13. Recommended test matrix

| Scenario | Expected outcome | Downstream |
| --- | --- | --- |
| Calls below limit | Succeed | Calls sent |
| Exceeds method bulkhead | Rejected fast | Excess calls not sent |
| Exceeds client bulkhead | Rejected fast | Excess calls not sent |
| GetStock busy, ReserveStock has permits | ReserveStock still accepted if client capacity remains | Yes |
| RPC completes or fails | Permit released | Can accept new calls |
| Deadline/cancellation | Permit released | Call terminated |
| Dependency slow | Concurrency remains capped at threshold | Does not exceed limit |
| Multiple application replicas | Total capacity accounted per process | Within cluster-wide budget |

## 14. Key takeaways and self-check

**Bulkhead by client or method** limits concurrency at two layers: a shared bulkhead protects total calls to a dependency, while dedicated bulkheads protect individual RPC methods from starving others. For blocking generated stubs, use Resilience4j semaphore bulkheads, short `maxWaitDuration`, and finite deadlines. Test with an in-process server, latches, and counters to prove excess calls are rejected before reaching downstream.

Self-check:

1. When should you use a shared client-level bulkhead and when do you need separate method-level bulkheads?
2. Why might method-level bulkheads alone fail to cap total dependency load?
3. How does a semaphore bulkhead differ from a fixed thread-pool bulkhead?
4. Why must async/streaming RPCs hold permits until the terminal callback?
5. Why should you not retry immediately when a bulkhead rejects a call?
6. How do you calculate total concurrency when the application runs multiple replicas?

Properly scoped bulkheads help Spring gRPC preserve capacity for critical operations, limit blast radius when one method spikes, and shed excess load before it exhausts the entire application's resources.
