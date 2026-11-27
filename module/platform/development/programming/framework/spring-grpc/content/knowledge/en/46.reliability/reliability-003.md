# Circuit breaker for gRPC dependencies

In a Spring gRPC application, one service often calls other gRPC services to complete a request. If a dependency is slow or fails repeatedly, incoming requests can keep tying up threads, connections, and waiting resources. A **circuit breaker** tracks dependency call outcomes, pauses sending requests when the error rate or slow-call rate exceeds a threshold, and then allows a limited number of probes when the dependency has a chance to recover.

A circuit breaker protects the caller from continuing to hammer a failing dependency. It does not fix the dependency itself, does not limit concurrency on its own, and does not replace deadlines. With gRPC, combine the breaker with deadlines, load balancing, bounded retries, and semantically accurate status-code handling.

## 1. The three states of a circuit breaker

| State | Behavior | State transition |
| --- | --- | --- |
| `CLOSED` | Allows calls through to the dependency and records outcomes | Opens when failure rate or slow-call rate exceeds threshold |
| `OPEN` | Rejects calls immediately without sending requests to the dependency | Transitions to HALF_OPEN after wait duration |
| `HALF_OPEN` | Allows only a limited number of probe calls | Closes if probes succeed well enough; re-opens if probes fail or are too slow |

Basic flow:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: errors or slow calls exceed threshold
    OPEN --> HALF_OPEN: wait duration elapses
    HALF_OPEN --> CLOSED: probes recover
    HALF_OPEN --> OPEN: probes keep failing
~~~

In `OPEN`, the client fails fast instead of waiting on a connection doomed to fail. In `HALF_OPEN`, the breaker caps trial calls to prevent a flood of requests hitting a freshly recovered dependency all at once.

## 2. Choosing which errors count as failures

Not every gRPC status means the dependency is unhealthy. For example, `NOT_FOUND` can be a normal business result; `INVALID_ARGUMENT` is a caller error; `PERMISSION_DENIED` and `UNAUTHENTICATED` are permission/identity errors. Counting all of these as failures can trip the breaker even when the dependency is functioning properly.

A common policy:

| gRPC status | Count as failure for dependency breaker? | Reason |
| --- | --- | --- |
| `UNAVAILABLE` | Yes | Dependency or transport is unavailable |
| `DEADLINE_EXCEEDED` | Usually yes | Dependency failed to finish within the time budget |
| `INTERNAL` / `UNKNOWN` | Policy-dependent; usually yes if unexpected server error | May reflect a dependency failure |
| `RESOURCE_EXHAUSTED` | Depends on cause | Could be caller quota, message limit, or dependency overload |
| `NOT_FOUND` | Usually no | May be a valid business outcome |
| `INVALID_ARGUMENT` | No | Caller needs to fix the request |
| `UNAUTHENTICATED` / `PERMISSION_DENIED` | No | Credential or authorization error |
| `CANCELLED` | Usually no | Caller or parent call cancelled |

Rules must reflect the specific dependency. For example, `RESOURCE_EXHAUSTED` caused by an overloaded downstream server can signal that the breaker should open; the same status caused by a single tenant exhausting its quota does not necessarily reflect the health of the whole dependency.

## 3. Configuring Resilience4j in Spring

Resilience4j provides a `CircuitBreaker` that can wrap calls to a generated gRPC stub. Example bean configuring a dedicated breaker for the inventory dependency:

~~~java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GrpcResilienceConfiguration {

    @Bean
    CircuitBreaker inventoryCircuitBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(
                CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(20)
            .minimumNumberOfCalls(10)
            .failureRateThreshold(50)
            .slowCallRateThreshold(60)
            .slowCallDurationThreshold(Duration.ofMillis(300))
            .waitDurationInOpenState(Duration.ofSeconds(5))
            .permittedNumberOfCallsInHalfOpenState(3)
            .automaticTransitionFromOpenToHalfOpenEnabled(true)
            .recordException(GrpcResilienceConfiguration::isDependencyFailure)
            .build();

        return CircuitBreaker.of("inventory-grpc", config);
    }

    private static boolean isDependencyFailure(Throwable error) {
        if (!(error instanceof StatusRuntimeException grpcError)) {
            return false;
        }

        Status.Code code = grpcError.getStatus().getCode();
        return code == Status.Code.UNAVAILABLE
            || code == Status.Code.DEADLINE_EXCEEDED
            || code == Status.Code.INTERNAL
            || code == Status.Code.UNKNOWN;
    }
}
~~~

The thresholds in the example are only a starting point: a 20-call window, requiring at least 10 calls before evaluating, opening at a 50% failure rate or 60% slow-call rate, and waiting 5 seconds before `HALF_OPEN`. Tune them to traffic volume, latency SLOs, and the dependency's recovery characteristics.

`recordException` determines which exceptions count as failures. Exceptions not matched by the predicate do not raise the failure rate. Do not configure every `StatusRuntimeException` as a failure if the dependency can return business statuses like `NOT_FOUND`.

## 4. Wrapping generated stub calls

Isolating dependency calls behind a gateway ensures the circuit breaker is applied consistently:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import java.util.concurrent.TimeUnit;

public final class InventoryGateway {

    private final InventoryServiceGrpc.InventoryServiceBlockingStub stub;
    private final CircuitBreaker circuitBreaker;

    public InventoryGateway(
            InventoryServiceGrpc.InventoryServiceBlockingStub stub,
            CircuitBreaker circuitBreaker) {
        this.stub = stub;
        this.circuitBreaker = circuitBreaker;
    }

    public GetStockResponse getStock(GetStockRequest request) {
        return circuitBreaker.executeSupplier(() ->
            stub.withDeadlineAfter(500, TimeUnit.MILLISECONDS)
                .getStock(request));
    }
}
~~~

`executeSupplier` invokes the supplier only when the breaker permits it. If the breaker is `OPEN`, Resilience4j throws `CallNotPermittedException` and the generated stub is not called. An RPC deadline is still necessary because the breaker evaluates the outcome only after the call finishes; without a deadline, a hung call can hold the breaker and thread far too long.

In a request chain, a child call's deadline should not exceed the parent request's remaining deadline. Use the smaller of the dependency's own budget and the parent deadline; reserve part of the budget for processing the response after the dependency returns.

## 5. Mapping an OPEN breaker to a gRPC status on the external API

When a dependency breaker opens, the upstream service needs to return a meaningful error to its caller instead of letting an internal exception turn into `UNKNOWN`:

~~~java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.stub.StreamObserver;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

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
        } catch (CallNotPermittedException openBreaker) {
            observer.onError(Status.UNAVAILABLE
                .withDescription("inventory dependency temporarily unavailable")
                .asRuntimeException());
        } catch (StatusRuntimeException downstreamError) {
            observer.onError(mapDownstreamError(downstreamError));
        }
    }

    private RuntimeException mapDownstreamError(
            StatusRuntimeException error) {
        Status.Code code = error.getStatus().getCode();
        if (code == Status.Code.NOT_FOUND
                || code == Status.Code.INVALID_ARGUMENT
                || code == Status.Code.PERMISSION_DENIED
                || code == Status.Code.UNAUTHENTICATED) {
            return Status.fromCode(code)
                .withDescription("request could not be completed")
                .asRuntimeException();
        }

        if (code == Status.Code.DEADLINE_EXCEEDED) {
            return Status.DEADLINE_EXCEEDED
                .withDescription("inventory dependency timed out")
                .asRuntimeException();
        }

        if (code == Status.Code.UNAVAILABLE
                || code == Status.Code.INTERNAL
                || code == Status.Code.UNKNOWN) {
            return Status.UNAVAILABLE
                .withDescription("inventory dependency failed")
                .asRuntimeException();
        }

        return Status.fromCode(code)
            .withDescription("inventory dependency request failed")
            .asRuntimeException();
    }
}
~~~

Adapt the mapping example to your API contract. Do not expose hostnames, exception messages, or internal dependency details in the status description. If a business fallback is safe, the service can return cached data or a degraded state instead of an error; do not fabricate values that mislead callers about exact stock levels.

## 6. Testing breaker opening and fail-fast behavior

Tests should prove that after enough dependency errors, the breaker transitions to `OPEN` and subsequent requests never touch the server. Use an in-process server to simulate a dependency returning `UNAVAILABLE`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class InventoryCircuitBreakerTest {

    private Server server;
    private ManagedChannel channel;
    private CircuitBreaker breaker;
    private InventoryGateway gateway;
    private AtomicInteger dependencyCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        dependencyCalls = new AtomicInteger();

        InventoryServiceGrpc.InventoryServiceImplBase dependency =
            new InventoryServiceGrpc.InventoryServiceImplBase() {
                @Override
                public void getStock(
                        GetStockRequest request,
                        StreamObserver<GetStockResponse> observer) {
                    dependencyCalls.incrementAndGet();
                    observer.onError(Status.UNAVAILABLE
                        .withDescription("dependency is down")
                        .asRuntimeException());
                }
            };

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(dependency)
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .recordException(error ->
                error instanceof StatusRuntimeException grpcError
                    && grpcError.getStatus().getCode()
                        == Status.Code.UNAVAILABLE)
            .build();

        breaker = CircuitBreaker.of("inventory-test", config);
        var stub = InventoryServiceGrpc.newBlockingStub(channel);
        gateway = new InventoryGateway(stub, breaker);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
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
    void opensAfterRepeatedUnavailableAndRejectsWithoutCallingServer() {
        GetStockRequest request = GetStockRequest.newBuilder()
            .setSku("SKU-42")
            .build();

        for (int attempt = 0; attempt < 2; attempt++) {
            StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> gateway.getStock(request));
            assertEquals(
                Status.Code.UNAVAILABLE,
                error.getStatus().getCode());
        }

        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());

        assertThrows(
            CallNotPermittedException.class,
            () -> gateway.getStock(request));

        assertEquals(2, dependencyCalls.get());
    }
}
~~~

The first two calls reach the dependency and receive `UNAVAILABLE`; the two-call window reaches a 100% failure rate, so the breaker opens. The third call is rejected immediately and `dependencyCalls` stays at two. The test needs no `Thread.sleep()` because the `OPEN` state triggers immediately once enough samples exist.

This test focuses on the `OPEN` state. You can add a `HALF_OPEN` test using a controllable clock or short synchronized wait durations; avoid relying on long sleeps to make tests stable.

## 7. Failure rate, slow-call rate, and statistics windows

A circuit breaker usually uses a sliding window to calculate error rates:

- **Count-based window:** computed over the most recent N calls.
- **Time-based window:** computed over calls within a time span.
- **Minimum number of calls:** evaluates only after enough samples exist, preventing a single error from tripping the breaker.
- **Failure rate threshold:** minimum error percentage required to open the breaker.
- **Slow-call rate threshold:** percentage of calls exceeding the slow-call duration threshold required to open the breaker.

Choose the window based on traffic. For low-traffic dependencies, a large count window may take too long to accumulate samples; for high-traffic dependencies, a time window reflects recent failures better. The slow-call threshold should align with your SLO and be shorter than the downstream deadline so the breaker can detect a degrading dependency before all calls time out.

## 8. Combining circuit breaker, retry, deadline, and bulkhead

Each mechanism solves a different problem:

| Mechanism | What it protects |
| --- | --- |
| Deadline | Bounds how long an RPC may hold resources |
| Retry | Retries transient failures according to policy |
| Circuit breaker | Stops calling a dependency when error/slowness rate is too high |
| Bulkhead | Limits concurrent calls or resources allocated to a dependency |
| Load balancing | Selects another healthy backend to serve traffic |

Do not let retries amplify failures. If the breaker wraps the entire retry operation, the breaker typically records the final outcome of one logical call; if retry wraps the breaker, each attempt can be counted individually. Choose the decorator order deliberately and test the actual attempt count.

Do not use a breaker instead of a bulkhead: while `CLOSED`, many concurrent calls can still enter the dependency. With blocking stubs, thread/connection limits and deadlines are especially important to avoid exhausting worker pools.

## 9. Breaker scope and the HALF_OPEN state

Create a separate breaker per dependency or group of operations sharing failure semantics. Never use a single global breaker for all gRPC dependencies: an inventory outage should not stop calls to payment or identity services.

In `HALF_OPEN`, allow only a limited number of probes. Probes should be RPCs representative of real serving ability, have short deadlines, and produce no side effects. If enough probes succeed, the breaker closes; if they keep failing or remain slow, the breaker re-opens and starts a new wait period.

Resilience4j state typically lives inside the client process. If the application runs multiple instances, each instance can open or close its breaker at different times. Do not assume a local breaker acts as a cluster-wide state coordinator.

## 10. Metrics and observability

Track at minimum:

- Breaker state: `CLOSED`, `OPEN`, `HALF_OPEN`.
- Counts of successful, failed, rejected, and slow calls.
- Failure rate and slow-call rate.
- State transition count and time spent in `OPEN`.
- Downstream `UNAVAILABLE`/`DEADLINE_EXCEEDED` counts.
- Retry attempts and retry success rate.
- Dependency p50/p95/p99 latency.

Resilience4j provides an event publisher to log state transitions:

~~~java
inventoryCircuitBreaker.getEventPublisher()
    .onStateTransition(event ->
        log.warn("Inventory breaker transition: {}", event));
~~~

If using Resilience4j's Micrometer/Actuator integration, export metrics by dependency name and monitor via dashboards/alerts. Avoid attaching user ID, request ID, or SKU as metric tags due to high cardinality; those values belong in controlled traces/logs instead.

## 11. Testing through the Spring application context

In-process tests verify how the breaker wraps the generated stub and how statuses are recorded. They do not prove Spring registered the right beans, properties, or Micrometer binders. Add Spring integration tests to:

- Start the application context with the breaker bean and a real client channel.
- Verify the gateway receives the expected breaker by dependency name.
- Call a fake dependency returning `UNAVAILABLE` multiple times and verify the breaker transitions to `OPEN`.
- Verify subsequent calls fail fast without reaching the server.
- Verify metrics/events are emitted to the expected registry.
- Verify graceful recovery when the dependency recovers and the breaker moves to `HALF_OPEN` then `CLOSED`.

If using `@CircuitBreaker`, verify that methods are invoked through the Spring proxy; self-invocation can bypass proxy advice. For gRPC service methods and generated stubs, explicit wrapping in a gateway generally makes deadline/retry/breaker ordering easier to inspect.

## 12. Recommended test matrix

| Scenario | Expected outcome | Dependency call |
| --- | --- | --- |
| Dependency returns success | Breaker stays CLOSED | Yes |
| Dependency returns UNAVAILABLE enough times | Breaker transitions to OPEN | Sample calls go through |
| Breaker is OPEN | Calls fail fast | No |
| Wait duration elapses | Breaker transitions to HALF_OPEN | Limited probes only |
| Probes succeed | Breaker closes again | Yes |
| Probes fail/are slow | Breaker re-opens | Probe goes through |
| Dependency returns NOT_FOUND | Not counted as failure per example policy | Yes |
| Caller sends CANCELLED | Not counted as dependency failure by default | Depends on whether call reached server |
| Retry is enabled | Attempt count stays within overall deadline | Per policy |

## 13. Key takeaways and self-check

**Circuit breaker for gRPC dependencies** tracks errors and slow calls to transition `CLOSED` → `OPEN` → `HALF_OPEN`, avoiding continued calls to a degrading dependency. In Spring, use Resilience4j to wrap generated stubs, classify gRPC statuses via `recordException`, set a deadline per RPC, and map an `OPEN` breaker to an appropriate availability error on the external API. Tests must prove rejected calls never touch the dependency.

Self-check:

1. Why should `NOT_FOUND` not be counted as a dependency failure by default?
2. How do `OPEN` and `HALF_OPEN` differ?
3. Why does a circuit breaker not replace deadlines or bulkheads?
4. How does the ordering of retry and circuit breaker affect failure counting?
5. Why does each dependency need its own failure policy?
6. How do you prove that calls rejected when the breaker is `OPEN` never reach the server?

A properly configured circuit breaker helps Spring gRPC fail fast when dependencies fail, limits load during recovery, and restores traffic in a controlled way once the dependency is healthy again.
