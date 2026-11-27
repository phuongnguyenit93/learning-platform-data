# Mapping Domain Errors to Status

In **SPRING_GRPC**, the service adapter is the boundary between the Protocol Buffers contract and the application/domain layer. The adapter receives a protobuf request, converts it into a business command, invokes the application service, and converts the result back into a protobuf response. When business logic fails, the adapter must translate domain errors into an appropriate gRPC `Status` so the client understands the cause and decides how to react.

Do not let the domain model depend on `io.grpc.Status` or `StatusRuntimeException`. The domain describes what went wrong in business terms; the adapter decides how to represent that error over the gRPC protocol. This lesson focuses on mapping rules, implementation for unary/streaming RPCs, safe error details, and testing statuses.

## 1. Distinguishing Domain Errors from gRPC Status

A domain error represents a violation of a business rule or state, for example:

- An inventory stock item is not found.
- The requested reserve quantity exceeds available quantity.
- The data version no longer matches during an update.
- An SKU code is invalid.
- An order already exists.

gRPC `Status` is how the protocol represents an RPC outcome. It consists of a status code, an optional description, and optionally metadata/trailers or structured details.

| Layer | Responsibility | Example |
| --- | --- | --- |
| Domain | Expresses failures in business language | `StockNotFoundException` |
| Application service | Coordinates use cases and enforces business rules | `reserveStock()` |
| gRPC service adapter | Converts requests/responses and maps domain errors | `StockGrpcService` |
| gRPC transport | Delivers status to the client | `NOT_FOUND` |

If the domain throws `StatusRuntimeException` directly, business code becomes coupled to gRPC. When the same use case is invoked from REST, a message queue, or a batch job, other adapters would have to understand an exception tied to gRPC transport.

Keep domain exceptions protocol-independent. Only the adapter or gRPC integration layer needs to import `io.grpc.Status`.

## 2. Choosing Status Codes by Business Semantics

A status code is more than an error message. Clients, retry policies, monitoring, and API consumers can rely on the code to decide on actions.

| Domain condition | gRPC Status | When to use |
| --- | --- | --- |
| Malformed request or invalid parameters | `INVALID_ARGUMENT` | Error determinable from the request regardless of system state |
| Resource does not exist | `NOT_FOUND` | Referenced SKU or order is missing |
| Creating a resource that already exists | `ALREADY_EXISTS` | Duplicate identifier or unique key |
| Current state does not allow the operation | `FAILED_PRECONDITION` | Insufficient stock to reserve, order not yet in payable state |
| Concurrent update conflict | `ABORTED` | Optimistic locking or transaction conflict |
| Value outside valid domain bounds | `OUT_OF_RANGE` | Index/cursor out of bounds or measured value outside defined range |
| Quota or limited resource exhausted | `RESOURCE_EXHAUSTED` | Rate/quota limit, storage, or capacity depleted |
| Caller is unauthenticated | `UNAUTHENTICATED` | Missing, invalid, or expired token |
| Caller is authenticated but lacks permission | `PERMISSION_DENIED` | Principal lacks authority for the RPC |
| Dependency temporarily unavailable | `UNAVAILABLE` | Downstream service or transport temporarily down |
| RPC deadline expired | `DEADLINE_EXCEEDED` | Execution exceeded the deadline |
| Caller cancelled the RPC | `CANCELLED` | Client cancelled the call |
| Unexpected server error | `INTERNAL` | Internal failure outside defined cases |

Key distinctions:

- `INVALID_ARGUMENT` describes a bad request regardless of what state the system is in.
- `FAILED_PRECONDITION` describes a potentially valid request whose execution is disallowed by current state.
- `ABORTED` fits conflicts where a higher-level sequence of operations should be retried.
- `RESOURCE_EXHAUSTED` is for genuine quota/capacity limits, not a catch-all for business errors.
- `UNAVAILABLE` can fit transient failures, but does not mean every request is safe to retry.
- `INTERNAL` is for unexpected errors; never put stack traces or infrastructure details in the description returned to clients.

## 3. Creating Protocol-Independent Domain Exceptions

Inventory domain example:

```java
public abstract class StockDomainException extends RuntimeException {
    protected StockDomainException(String message) {
        super(message);
    }
}

public final class StockNotFoundException
        extends StockDomainException {
    public StockNotFoundException(String sku) {
        super("Stock item not found: " + sku);
    }
}

public final class InsufficientStockException
        extends StockDomainException {
    public InsufficientStockException(String sku) {
        super("Insufficient stock for: " + sku);
    }
}

public final class StockVersionConflictException
        extends StockDomainException {
    public StockVersionConflictException() {
        super("Stock version changed");
    }
}
```

The application service throws business-specific errors:

```java
public Stock reserve(String sku, long quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    Stock stock = repository.findBySku(sku)
            .orElseThrow(() -> new StockNotFoundException(sku));

    if (stock.available() < quantity) {
        throw new InsufficientStockException(sku);
    }

    return repository.reserve(
            sku, quantity, stock.version());
}
```

In a real application, you can use a shared `DomainException` hierarchy with stable error keys, or specific exceptions. What matters is that the application/domain layer does not need to know gRPC status codes.

Avoid using `IllegalArgumentException` for all business errors. Distinguish adapter-validated request errors from domain errors like insufficient stock or version conflicts. When needed, define distinct exceptions so the mapper never has to guess from message strings.

## 4. Writing a Centralized Mapper in the gRPC Adapter

A centralized mapper ensures all RPCs follow the same rules and prevents individual methods from choosing different statuses for the same error.

Example:

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Component;

@Component
public class GrpcStatusMapper {

    public StatusRuntimeException map(Throwable error) {
        if (error instanceof StockNotFoundException) {
            return Status.NOT_FOUND
                    .withDescription("Stock item not found")
                    .asRuntimeException();
        }

        if (error instanceof InsufficientStockException) {
            return Status.FAILED_PRECONDITION
                    .withDescription("Insufficient stock")
                    .asRuntimeException();
        }

        if (error instanceof StockVersionConflictException) {
            return Status.ABORTED
                    .withDescription("Stock was modified concurrently")
                    .asRuntimeException();
        }

        if (error instanceof IllegalArgumentException) {
            return Status.INVALID_ARGUMENT
                    .withDescription("Request contains an invalid value")
                    .asRuntimeException();
        }

        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }
}
```

The mapper returns safe, stable descriptions that do not rely on internal exception messages. Never include SQL, table names, stack traces, file paths, tokens, or secrets in status descriptions.

You can add exceptions such as `OrderAlreadyExistsException` → `ALREADY_EXISTS`, `QuotaExceededException` → `RESOURCE_EXHAUSTED`, or `AccessDeniedException` → `PERMISSION_DENIED`. Do not map unrecognized exceptions to `INVALID_ARGUMENT`; those are usually not the client's fault.

### 4.1. Keeping the Root Cause for Logs, Not Sending It to Clients

The mapper should not log the full exception only to have another interceptor log the same error, causing duplicates. Choose a single place responsible for logging with a request ID/correlation ID.

For unexpected errors, log the full exception on the server:

```java
log.error("Unexpected error while handling GetStock, requestId={}",
        requestId, error);
```

Clients receive only `INTERNAL` with a generic description. For known domain errors, log at an appropriate level (typically `DEBUG` or `INFO` depending on frequency) to avoid turning normal business rejections into system alerts.

## 5. Applying Mapping in a Unary Service Adapter

The generated server base class provides methods receiving the request and a `StreamObserver` for the response. The adapter invokes the application service, maps the result, and completes the observer exactly once.

```java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class StockGrpcService
        extends StockServiceGrpc.StockServiceImplBase {

    private final StockApplicationService applicationService;
    private final GrpcStatusMapper statusMapper;

    public StockGrpcService(
            StockApplicationService applicationService,
            GrpcStatusMapper statusMapper) {
        this.applicationService = applicationService;
        this.statusMapper = statusMapper;
    }

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> observer) {

        try {
            Stock stock = applicationService.find(request.getSku());
            observer.onNext(toReply(stock));
            observer.onCompleted();
        } catch (StockDomainException
                 | IllegalArgumentException error) {
            observer.onError(statusMapper.map(error));
        } catch (RuntimeException error) {
            log.error("Unexpected GetStock failure", error);
            observer.onError(Status.INTERNAL
                    .withDescription("Internal server error")
                    .asRuntimeException());
        }
    }

    private StockReply toReply(Stock stock) {
        return StockReply.newBuilder()
                .setSku(stock.sku())
                .setAvailable(stock.available())
                .build();
    }
}
```

This is a condensed example; `log` must be declared using the application's logging framework. Unexpected error handling can be moved into the mapper if you want a single place managing both status and logging policy.

Rules to preserve:

- Only call `onNext` once a valid response is ready.
- Call `onCompleted` after a successful response.
- Call `onError` on failure; never call `onCompleted` after `onError`.
- Do not catch `Throwable` indiscriminately because it can swallow critical JVM errors.
- Do not return raw exception messages from the domain to clients if they could contain sensitive data.

If a request is already invalid at the adapter, validate before calling the application service and return `INVALID_ARGUMENT`. Deeper business rules should still be enforced in the application/domain layer so other entry points remain protected.

## 6. Mapping for Streaming RPCs

For server-streaming or bidirectional streaming, an error may occur after some messages have already been sent. When that happens, the server cannot retroactively replace already sent messages with an error response; it terminates the stream with `onError`.

Server-streaming example:

```java
@Override
public void watchStock(
        StockRequest request,
        StreamObserver<StockReply> observer) {

    try {
        for (Stock stock : applicationService.watch(request.getSku())) {
            observer.onNext(toReply(stock));
        }
        observer.onCompleted();
    } catch (StockDomainException error) {
        observer.onError(statusMapper.map(error));
    } catch (RuntimeException error) {
        log.error("Unexpected WatchStock failure", error);
        observer.onError(Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException());
    }
}
```

In production code, also account for cancellation, backpressure, and publisher/stream lifecycle. If the client cancels the RPC, stop emitting data and release resources. Never continue calling `onNext` after a terminal signal.

For client-streaming/bidirectional streaming, errors can arise in `onNext`, `onCompleted`, or asynchronous processing. Forward errors to the response observer and guarantee only one terminal signal. Do not rely on a `try/catch` around observer creation to catch exceptions thrown later on callbacks/other threads.

## 7. Returning Structured Error Details When Needed

Status codes and descriptions are usually enough for simple errors. For multi-field validation or errors needing machine-readable metadata, you can use Google RPC standard error details (`google.rpc.Status`, `BadRequest`, `ErrorInfo`, `RetryInfo`).

Example returning field validation details:

```java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import io.grpc.StatusRuntimeException;
import io.grpc.protobuf.StatusProto;

BadRequest details = BadRequest.newBuilder()
        .addFieldViolations(
                BadRequest.FieldViolation.newBuilder()
                        .setField("quantity")
                        .setDescription("must be greater than zero"))
        .build();

com.google.rpc.Status status =
        com.google.rpc.Status.newBuilder()
                .setCode(io.grpc.Status.Code.INVALID_ARGUMENT.value())
                .setMessage("Request validation failed")
                .addDetails(Any.pack(details))
                .build();

StatusRuntimeException error =
        StatusProto.toStatusRuntimeException(status);
```

Clients can use `StatusProto.fromThrowable(error)` to read structured details and handle them by type. Dependencies typically include `io.grpc:grpc-protobuf` and `com.google.api.grpc:proto-google-common-protos` at versions managed by an appropriate BOM.

Include only data the client needs in details. Do not send stack traces, database contents, credentials, or unnecessary personal data. Clients that do not understand rich details must still be able to handle the basic status code.

## 8. Metadata Trailers and Error Contracts

gRPC can attach metadata trailers alongside the final status. Trailers suit short technical data such as an error identifier or correlation ID, but should not become a channel for large error payloads.

Example attaching an error ID:

```java
Metadata trailers = new Metadata();
Metadata.Key<String> errorIdKey =
        Metadata.Key.of("error-id", Metadata.ASCII_STRING_MARSHALLER);

trailers.put(errorIdKey, errorId);

observer.onError(Status.INTERNAL
        .withDescription("Internal server error")
        .asRuntimeException(trailers));
```

Define metadata keys consistently between server and client. Do not place tokens, secrets, or raw exception messages in trailers. When structured, multilingual errors are needed, prefer versioned detail schemas over parsing description text.

## 9. How Status Codes Affect Retries

Incorrect status mapping can cause clients to retry business errors or ignore transient failures.

| Status | Typical handling |
| --- | --- |
| `INVALID_ARGUMENT` | Fix the request; do not retry as-is |
| `NOT_FOUND` | Check resource/key; usually do not retry immediately |
| `ALREADY_EXISTS` | Read existing resource or change key |
| `FAILED_PRECONDITION` | Change business state before calling again |
| `ABORTED` | Can retry the whole transaction/use case at a higher level |
| `RESOURCE_EXHAUSTED` | Respect quota and retry delay if provided by server |
| `UNAVAILABLE` | Can retry with backoff if operation is safe and deadline remains |
| `DEADLINE_EXCEEDED` | Outcome may be unknown; check idempotency before retrying |
| `UNAUTHENTICATED` | Refresh credentials if possible, then retry within limits |
| `PERMISSION_DENIED` | Fix permissions; do not retry repeatedly |
| `INTERNAL` | Investigate server; do not default to infinite retries |

Some operations may have completed on the server even though the client receives `DEADLINE_EXCEEDED` due to a late response. For commands creating orders, payments, or reserving resources, use idempotency keys to avoid duplicate execution when clients retry.

Do not map database timeout errors to `INVALID_ARGUMENT`. If the error is truly transient, `UNAVAILABLE` may fit; if transaction state is unknown, choose the code and retry policy based on use case semantics.

## 10. Testing Mapping and the RPC Contract

### 10.1. Unit tests for the mapper

Verify that domain exceptions convert into the expected codes:

```java
import io.grpc.Status;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GrpcStatusMapperTest {

    private final GrpcStatusMapper mapper = new GrpcStatusMapper();

    @Test
    void mapsMissingStockToNotFound() {
        var error = mapper.map(new StockNotFoundException("BOOK-101"));

        assertEquals(
                Status.Code.NOT_FOUND,
                Status.fromThrowable(error).getCode());
    }

    @Test
    void mapsInsufficientStockToFailedPrecondition() {
        var error = mapper.map(
                new InsufficientStockException("BOOK-101"));

        assertEquals(
                Status.Code.FAILED_PRECONDITION,
                Status.fromThrowable(error).getCode());
    }
}
```

Unit tests focus on mapping rules without starting a gRPC server.

### 10.2. Integration tests for the service adapter

Invoke the generated stub to verify the actual status reaching the client:

```java
@Test
void missingStockReturnsNotFoundToGrpcClient() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> blockingStub.getStock(
                    StockRequest.newBuilder()
                            .setSku("MISSING")
                            .build()));

    assertEquals(
            Status.Code.NOT_FOUND,
            Status.fromThrowable(error).getCode());
}
```

This integration test confirms the adapter calls `onError` with the right status and the transport delivers it to the client. Add tests for `INVALID_ARGUMENT`, `FAILED_PRECONDITION`, unexpected `INTERNAL` errors, and streaming terminal errors.

If using rich details, inspect `StatusProto.fromThrowable(error)` and unpack the expected detail type. Avoid asserting only description text because descriptions may change or be localized.

## 11. Common Mapping Mistakes

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Mapping all exceptions to `INTERNAL` | Clients cannot distinguish business errors | Map specific domain exceptions |
| Mapping all errors to `INVALID_ARGUMENT` | Skewed retry/monitoring and blaming the client | Choose codes by root cause |
| Returning `exception.getMessage()` verbatim | May leak SQL, data, or internal details | Use safe descriptions |
| Domain throwing `StatusRuntimeException` | Domain couples to gRPC | Keep domain exceptions pure |
| Calling `onError` then continuing `onNext` | Violates stream terminal semantics | Stop processing after terminal signal |
| Catching errors only at stream creation | Misses async callback errors | Handle errors across stream lifecycle |
| Using `UNAVAILABLE` for permanent business errors | Clients retry fruitlessly | Use status reflecting actual condition |
| Retrying non-idempotent commands after timeout | Can cause duplicate side effects | Design idempotency and deadlines |

## 12. Practice Exercises

1. Create `StockNotFoundException`, `InsufficientStockException`, and `StockVersionConflictException` in the domain layer.
2. Write `GrpcStatusMapper` mapping them to `NOT_FOUND`, `FAILED_PRECONDITION`, and `ABORTED` respectively.
3. Add request validation returning `INVALID_ARGUMENT` for blank SKU or invalid quantity.
4. Use a service adapter extending the generated `StockServiceGrpc.StockServiceImplBase` and calling `observer.onError` when the application service throws a domain exception.
5. Write unit tests for each mapper branch and the `INTERNAL` fallback branch.
6. Write an integration test calling the generated stub and asserting the received status code.
7. Add `google.rpc.BadRequest` for multi-field validation and verify client-side detail unpacking.
8. Write a server-streaming test where an error occurs after several messages; verify the stream ends with one terminal error.
9. Test retries with `UNAVAILABLE` and `ABORTED`; confirm non-idempotent requests are not retried without an idempotency key.
10. Review logs/trailers to ensure no stack traces, tokens, secrets, or sensitive data leak.

### Key takeaway

**Domain errors describe business failures; gRPC Status is how the service adapter publishes those failures over RPC.** Keep domain exceptions independent of gRPC, map by semantics rather than arbitrary exception names, terminate the observer exactly once, and send only safe descriptions. Test both the mapper and the client-visible status; if a status may trigger retries, account for deadlines and operation idempotency.

## References

- [gRPC — Status Codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC — Error Handling](https://grpc.io/docs/guides/error/)
- [gRPC Java — Status](https://grpc.github.io/grpc-java/javadoc/io/grpc/Status.html)
- [gRPC Java — StatusRuntimeException](https://grpc.github.io/grpc-java/javadoc/io/grpc/StatusRuntimeException.html)
- [Google API — Error Model](https://cloud.google.com/apis/design/errors)
