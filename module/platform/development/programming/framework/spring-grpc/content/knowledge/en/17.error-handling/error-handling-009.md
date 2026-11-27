# Dependency errors and UNAVAILABLE

**Chapter:** Error handling  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers, generated Java code, and unary or streaming RPCs. This lesson focuses on errors arising when a service needs to call a dependency such as another gRPC service, an HTTP API, a database, or a message broker; how to recognize transient failures and accurately map them to the `UNAVAILABLE` gRPC status.

## 1. When is a dependency error UNAVAILABLE?

An RPC can be valid at the API and domain layers, yet unable to complete because a dependent system is temporarily unable to serve requests. Examples:

- The payment service is restarting or refusing connections.
- An HTTP API returns 503 due to maintenance or overload.
- DNS, connection pool, or network cannot temporarily reach the dependency.
- Downstream gRPC returns `UNAVAILABLE`.
- A circuit breaker is open because the dependency failed repeatedly.

In these situations, `UNAVAILABLE` accurately expresses that **the service cannot currently fulfill the request because a dependency is unavailable**. The client can retry after a backoff if the operation is safe and time budget remains.

Not every exception occurring while calling a dependency is `UNAVAILABLE`. A business error returned by the dependency, such as an account not existing, still needs to be mapped according to its business meaning. Validation, permission, quota, deadline, and internal bug errors also have their own statuses.

## 2. Distinguishing UNAVAILABLE from related statuses

| Situation | Typical appropriate status | Why |
| --- | --- | --- |
| Dependency temporarily refuses connections, connection reset, HTTP 503 | `UNAVAILABLE` | Dependency is unavailable at the time of the call |
| Downstream gRPC returns `UNAVAILABLE` | Usually mapped to `UNAVAILABLE` in current API | Dependency availability failure becomes service availability failure |
| Total deadline of the current RPC has expired | `DEADLINE_EXCEEDED` | Call's time budget is exhausted |
| Dependency-specific timeout while caller deadline remains | Per contract; usually `UNAVAILABLE` if dependency did not respond in time | Do not confuse internal timeout with inbound deadline |
| Dependency or tenant quota exceeded | `RESOURCE_EXHAUSTED` | Resource/quota limit was hit |
| Bad request or input rule violation | `INVALID_ARGUMENT` | Client must fix the request |
| Domain resource does not exist | `NOT_FOUND` | Not an availability outage |
| Dependency rejects due to business state | `FAILED_PRECONDITION` or matching domain status | Dependency is running but rejects the operation |
| Transaction/optimistic lock conflict | `ABORTED` | Need to re-read and retry the workflow/transaction |
| Bug or broken internal invariant | `INTERNAL` | Implementation bug must not be disguised as a network issue |

**Do not use `UNAVAILABLE` as the default status for every exception from a dependency.** Classify by root cause and the meaning the client needs to know.

## 3. Identifying errors from different dependency types

### Downstream gRPC

gRPC Java clients typically receive errors in a `StatusRuntimeException` or `StatusException`. Use `Status.fromThrowable(error)` to obtain the status code, without parsing the description:

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

try {
    return paymentStub.authorize(request);
} catch (StatusRuntimeException error) {
    Status downstream = Status.fromThrowable(error);
    switch (downstream.getCode()) {
        case UNAVAILABLE -> throw new DependencyUnavailableException(
                "Payment service unavailable", error);
        case RESOURCE_EXHAUSTED -> throw new DependencyQuotaException(
                "Payment service quota exceeded", error);
        case NOT_FOUND -> throw new PaymentMethodNotFoundException();
        default -> throw error;
    }
}
```

This snippet shows that downstream status meaning should be preserved. Do not turn `NOT_FOUND` into `UNAVAILABLE` just because it came from another service. For other statuses, decide whether to preserve them or map them to the current API's domain statuses according to the public contract; avoid blindly forwarding internal descriptions or trailers.

### HTTP dependencies

An HTTP client can distinguish:

- HTTP 503: service temporarily unavailable, usually mapped to `UNAVAILABLE`.
- HTTP 429: rate limit/quota, usually mapped to `RESOURCE_EXHAUSTED`; honor `Retry-After` if present and trusted.
- HTTP 400/422: the request the current service sent to the dependency is invalid; usually an integration bug or internal mapping issue, not automatically blamed on the gRPC client.
- HTTP 401/403: credentials or permissions between the two services; distinguish service-to-service configuration/identity failure from the external caller's permissions.
- HTTP 404: dependency resource does not exist; map by the current API's semantics, which may be `NOT_FOUND` or a dependency error if it is a misconfigured required endpoint.

Do not catch every `RestClientException` or `WebClientException` broadly and return `UNAVAILABLE`: broad exception hierarchies can include request errors, decoding errors, business statuses, and serialization bugs.

### Database and broker

- Connection refused, connection reset, or a temporarily exhausted pool can be transient dependency errors.
- Unique constraints, foreign keys, or schema violations are not `UNAVAILABLE` by default; classify them into domain errors, conflicts, or internal errors.
- Broker rejection due to quota may suit `RESOURCE_EXHAUSTED`; an unreachable broker may suit `UNAVAILABLE`.
- Query timeouts must be distinguished from the inbound RPC's deadline and query-policy timeouts.

Convert library errors into semantic application exceptions at the dependency adapter. This keeps the gRPC layer independent of specific HTTP/database client exception classes.

## 4. Normalizing dependency errors before mapping

A few application exceptions can express classified causes:

```java
public class DependencyUnavailableException extends RuntimeException {
    public DependencyUnavailableException(String dependency, Throwable cause) {
        super(dependency, cause);
    }
}

public class DependencyQuotaException extends RuntimeException {
    public DependencyQuotaException(String dependency, Throwable cause) {
        super(dependency, cause);
    }
}

public class DependencyTimeoutException extends RuntimeException {
    public DependencyTimeoutException(String dependency, Throwable cause) {
        super(dependency, cause);
    }
}
```

HTTP, gRPC, or database adapters convert recognized exceptions into these types. Do not create a `DependencyUnavailableException` for an unclassified error just to avoid handling it.

A mapper at the gRPC boundary can map known error types:

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Component;

@Component
public class DependencyStatusMapper {

    public StatusRuntimeException map(Throwable error) {
        if (error instanceof DependencyUnavailableException) {
            return Status.UNAVAILABLE
                    .withDescription(
                            "A required service is temporarily unavailable")
                    .asRuntimeException();
        }
        if (error instanceof DependencyQuotaException) {
            return Status.RESOURCE_EXHAUSTED
                    .withDescription("A dependency quota has been exceeded")
                    .asRuntimeException();
        }
        if (error instanceof DependencyTimeoutException) {
            return Status.UNAVAILABLE
                    .withDescription("A required service did not respond in time")
                    .asRuntimeException();
        }

        // Unrecognized errors should be handled by a general mapper
        // or routed to an INTERNAL fallback with internal logging.
        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }
}
```

The example maps a dependency timeout to `UNAVAILABLE` when that timeout belongs to the dependency's own budget and the inbound RPC still has time remaining. If the current RPC's deadline has expired, gRPC terminates the call with `DEADLINE_EXCEEDED`; do not override the caller's deadline semantics with another status.

In a real application, the dependency mapper should be integrated into the overall mapper so domain exceptions, existing `StatusException`s, or security errors are not accidentally turned into `INTERNAL`. Intentionally created statuses may be preserved if they fit the API contract; downstream descriptions/trailers should be vetted before exposure.

## 5. Returning UNAVAILABLE from a Spring gRPC adapter

The adapter calls the application service and converts classified dependency errors into statuses:

```java
@GrpcService
public class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderApplicationService applicationService;
    private final DependencyStatusMapper statusMapper;

    public OrderGrpcService(
            OrderApplicationService applicationService,
            DependencyStatusMapper statusMapper) {
        this.applicationService = applicationService;
        this.statusMapper = statusMapper;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<Order> responseObserver) {
        try {
            Order order = applicationService.getOrder(request.getOrderId());
            responseObserver.onNext(toProto(order));
            responseObserver.onCompleted();
        } catch (DependencyUnavailableException
                | DependencyQuotaException
                | DependencyTimeoutException dependencyError) {
            responseObserver.onError(statusMapper.map(dependencyError));
        } catch (OrderNotFoundException missing) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Order not found")
                            .asRuntimeException());
        }
    }
}
```

This example illustrates only known errors. Include a safe fallback for unexpected exceptions, log internally, and return a generic `INTERNAL`. Do not put exception messages or internal dependency hostnames into the description.

With streaming RPCs, if a dependency fails while processing a message or finalizing a batch, the server must terminate the response exactly once with an appropriate status. After `responseObserver.onError(...)`, do not send more response messages or call `onCompleted()`. If the inbound call was already cancelled, prioritize stopping work and cleaning up rather than trying to send a status on a terminated call.

## 6. Deadlines must propagate down to dependencies

An inbound RPC with a 2-second deadline cannot allow each dependency call to run for 5 seconds on its own. Without bounding downstream duration, requests can continue consuming threads/connections after the client has already received `DEADLINE_EXCEEDED`.

Obtain the remaining budget from gRPC `Context`:

```java
import io.grpc.Context;
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

long dependencyBudgetNanos(
        long configuredMaximumNanos,
        long cleanupReserveNanos) {

    Deadline deadline = Context.current().getDeadline();
    if (deadline == null) {
        return configuredMaximumNanos;
    }

    long remaining = deadline.timeRemaining(TimeUnit.NANOSECONDS);
    long usable = remaining - cleanupReserveNanos;
    if (usable <= 0) {
        throw Status.DEADLINE_EXCEEDED
                .withDescription("Request deadline exceeded")
                .asRuntimeException();
    }
    return Math.min(usable, configuredMaximumNanos);
}
```

For downstream gRPC, apply this budget to the stub:

```java
long budget = dependencyBudget(
        TimeUnit.SECONDS.toNanos(1),
        TimeUnit.MILLISECONDS.toNanos(50));

PaymentServiceGrpc.PaymentServiceBlockingStub bounded =
        paymentStub.withDeadlineAfter(budget, TimeUnit.NANOSECONDS);

return bounded.authorize(request);
```

Even if the call has no deadline, still configure a separate maximum timeout for the dependency. If the application switches Context onto an executor or uses an HTTP/database client, pass the remaining budget as that client's timeout; do not assume non-gRPC libraries automatically understand `io.grpc.Context`.

## 7. Retries, circuit breakers, and bulkheads

`UNAVAILABLE` can be a transient error, but retries are not always safe. A dependency may have executed the operation and then lost the response; resending a write command can produce duplicate side effects.

### Retry rules

- Only retry when the operation is idempotent or carries an idempotency key.
- Use exponential backoff with jitter; avoid thundering-herd retries when the dependency recovers.
- Cap attempt count and total retry duration within the remaining deadline.
- Do not retry `INVALID_ARGUMENT`, `PERMISSION_DENIED`, or non-recoverable domain errors.
- Respect quotas and wait hints published by the dependency.
- Avoid retrying at multiple layers simultaneously; retries in client, gateway, and service all at once can amplify load.

Example bounded backoff schedule:

```text
Attempt 1: immediate
Attempt 2: 100 ms + jitter
Attempt 3: 200 ms + jitter
Attempt 4: 400 ms + jitter
Afterward: stop if retry budget or deadline is exhausted
```

These values are illustrative only; production policy must be based on the system's SLAs, load, and retry budget.

### Circuit breaker

When a dependency fails repeatedly, a circuit breaker can open to fail fast instead of continuing to call an overloaded system. Circuit-open failures can usually return `UNAVAILABLE` because the dependency is currently not serving requests. Clients should not retry immediately; the circuit breaker needs recovery time and transitions to half-open per policy.

### Bulkhead

A bulkhead limits concurrent calls or queue depth to a dependency. When internal limits are full, you can return `RESOURCE_EXHAUSTED` if it represents a caller or system quota/capacity limit. If policy treats it as a temporarily unavailable dependency, `UNAVAILABLE` can be used; keep the contract consistent so clients know whether to shed load or wait.

## 8. Fallbacks must not pretend to succeed

Some read operations can serve cached or stale data when a dependency is temporarily disconnected. If doing so:

- Clearly define how stale the data is allowed to be.
- Mark the source or freshness in the response if the client needs to know.
- Do not use fallbacks for write operations or business logic requiring strong consistency without proper design.
- Do not return a default response as if the dependency had confirmed success.

If no valid fallback exists, return `UNAVAILABLE` clearly. An explicit error lets the client apply retries or report failure better than a fake success result.

## 9. Testing dependency errors

Test the mapper independently:

```java
import io.grpc.Status;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DependencyStatusMapperTest {

    private final DependencyStatusMapper mapper =
            new DependencyStatusMapper();

    @Test
    void temporaryDependencyFailureMapsToUnavailable() {
        var error = mapper.map(
                new DependencyUnavailableException("payment", null));

        assertEquals(Status.Code.UNAVAILABLE,
                error.getStatus().getCode());
    }

    @Test
    void quotaFailureDoesNotBecomeUnavailable() {
        var error = mapper.map(
                new DependencyQuotaException("payment", null));

        assertEquals(Status.Code.RESOURCE_EXHAUSTED,
                error.getStatus().getCode());
    }

    @Test
    void unknownFailureUsesSafeInternalFallback() {
        var error = mapper.map(new IllegalStateException("unexpected"));

        assertEquals(Status.Code.INTERNAL,
                error.getStatus().getCode());
        assertEquals("Internal server error",
                error.getStatus().getDescription());
    }
}
```

Integration tests via in-process gRPC should use fake dependencies to simulate:

| Case | Expected |
| --- | --- |
| Downstream gRPC returns `UNAVAILABLE` | Current API returns `UNAVAILABLE` per contract |
| HTTP dependency returns 503 | Maps to `UNAVAILABLE` |
| HTTP dependency returns 429 | Maps to quota, usually `RESOURCE_EXHAUSTED` |
| Dependency returns business error `NOT_FOUND` | Preserves `NOT_FOUND` meaning, does not turn into `UNAVAILABLE` |
| Circuit breaker open | Fails fast without calling dependency |
| Caller deadline expires before downstream | Client receives `DEADLINE_EXCEEDED`; downstream is stopped when possible |
| Dependency times out while caller still has budget | Status per published dependency policy |
| Retrying write operation | Same idempotency key, no duplicate side effects |

Tests should verify both the status code and the dependency call count. A test that only checks `UNAVAILABLE` without checking retry counts can miss excessive retry loops.

## 10. Observability and operations

Record metrics per dependency and operation:

- Call count, latency, and timeouts.
- Error count by status code and dependency type.
- Retry count, circuit breaker open/half-open transitions, and bulkhead rejections.
- Requests cancelled due to deadlines and remaining time when calling downstream.
- Fallback rate and staleness of fallback data.

Logs should include dependency name, operation, gRPC method, status, and correlation ID. Do not log bearer tokens, payloads, SQL containing customer data, or uncontrolled exception messages. Descriptions returned to clients should be generic and must not expose hostnames, topology, or internal addresses.

If `UNAVAILABLE` rises across multiple dependencies simultaneously, there may be a network issue or shared overload. If only one dependency spikes, focus investigation on that dependency's endpoints, connection pool, DNS, quota, and health.

## 11. Self-practice

1. A downstream HTTP API returns 503. Why is `UNAVAILABLE` more appropriate than `INTERNAL` if the outage is identified as temporary?
2. Downstream returns 404 because the customer does not exist. Why shouldn't that status be changed to `UNAVAILABLE`?
3. The inbound RPC has 300 ms remaining, while the HTTP client's default timeout is 3 seconds. How should you propagate the budget?
4. A payment command receives `UNAVAILABLE` after downstream may already have committed. How should idempotency and state lookup be used before retrying?
5. Both an open circuit breaker and a full bulkhead reject requests. Choose a status for each case per an API contract and explain the client reaction.

**Remember:** Use `UNAVAILABLE` when a dependency is genuinely temporarily unavailable; distinguish it from expired deadlines, quotas, domain errors, and internal bugs. Normalize exceptions by cause, propagate remaining deadlines downstream, retry with backoff only when safe, and combine circuit breakers/bulkheads to contain cascading failures.
