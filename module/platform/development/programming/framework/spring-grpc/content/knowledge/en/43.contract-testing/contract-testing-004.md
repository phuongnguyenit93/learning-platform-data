# Verifying Status Code Contracts

In Spring gRPC, the status code is the RPC outcome that clients use to decide how to handle errors: fix the request, re-authenticate, report a missing resource, retry, or stop. Two server versions can both return structurally valid protobuf responses yet remain incompatible if one version changes `NOT_FOUND` to `INTERNAL` for the same business condition. Status code contract tests verify that each method returns the right code for its published outcomes.

Status is part of the public API, not just information for logs. This lesson explains how to define status contracts per method, map exceptions consistently, test unary and streaming calls with generated stubs, verify trailers when needed, and evaluate the impact of statuses on retries and cancellation.

## 1. Status Codes Belong to Each RPC's Contract

A method can have multiple valid outcomes:

| Method / Condition | Contract Status | Meaning for Client |
| --- | --- | --- |
| `GetProduct` with valid ID and existing product | `OK` | Receive `Product` response |
| `GetProduct` with non-existent ID | `NOT_FOUND` | Resource does not exist |
| `CreateProduct` with invalid required field | `INVALID_ARGUMENT` | Fix the request before resending |
| `CreateProduct` with an already-used ID | `ALREADY_EXISTS` | Choose another ID or read the existing resource |
| RPC requires credentials but credentials are missing/invalid | `UNAUTHENTICATED` | Supply valid credentials |
| Caller is authenticated but lacks permission | `PERMISSION_DENIED` | Not permitted to perform the action |
| Current state precondition is not met | `FAILED_PRECONDITION` | Fix the state before calling again |
| Concurrency conflict requiring full transaction retry | `ABORTED` | Can rerun the transaction according to policy |
| Quota or resource limit exceeded | `RESOURCE_EXHAUSTED` | Reduce load / wait for quota replenishment |
| Backend temporarily unavailable | `UNAVAILABLE` | Can retry if the operation is safe |

Do not define a single generic status for all errors. Statuses must reflect what the client can do next. The same Java exception may require different statuses depending on the use case; therefore mapping must be based on semantics and not merely class names.

## 2. Meaning of Canonical gRPC Statuses

gRPC defines standard status codes. Common groups in application APIs:

| Code | Used When |
| --- | --- |
| `OK` | RPC completed successfully |
| `CANCELLED` | Call cancelled by caller or operation cancelled |
| `UNKNOWN` | Error whose specific cause cannot be determined; should not replace known mappings |
| `INVALID_ARGUMENT` | Request is invalid regardless of system state |
| `DEADLINE_EXCEEDED` | Deadline expired before RPC completed; server operation may have completed while response arrived late |
| `NOT_FOUND` | Requested resource does not exist |
| `ALREADY_EXISTS` | Resource being created already exists |
| `PERMISSION_DENIED` | Caller lacks permission, even though authenticated |
| `RESOURCE_EXHAUSTED` | Quota, limit, or resource exhausted |
| `FAILED_PRECONDITION` | System must be brought into a valid state before retrying |
| `ABORTED` | Operation aborted due to conflict; retry typically happens at transaction/workflow level |
| `OUT_OF_RANGE` | Value is outside the valid range, e.g., reading past the end of a range |
| `UNAUTHENTICATED` | Valid credentials are absent |
| `UNAVAILABLE` | Service/backend is temporarily unavailable |
| `DATA_LOSS` | Severe data loss or corruption |
| `UNIMPLEMENTED` | Method or feature is not supported |
| `INTERNAL` | Unexpected internal server error |

Distinguish closely related codes:

- `INVALID_ARGUMENT`: request is invalid regardless of system state, e.g., negative quantity.
- `FAILED_PRECONDITION`: request may be valid, but current state does not allow it, e.g., product is locked.
- `ABORTED`: conflict requiring the transaction to be retried from the beginning.
- `OUT_OF_RANGE`: value has a valid type but exceeds the supported domain/boundary.
- `UNAUTHENTICATED` vs. `PERMISSION_DENIED`: identity unverified vs. verified but lacking authorization.

Choosing the wrong code causes clients to retry incorrectly, display wrong messages, or mishandle security.

## 3. Writing Centralized Status Mapping

Do not let each endpoint choose statuses ad hoc. A centralized mapper keeps semantics consistent across services:

```java
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;

public final class GrpcStatusMapper {

    public StatusRuntimeException toRuntimeException(Throwable error) {
        if (error instanceof StatusRuntimeException statusError) {
            return statusError;
        }
        if (error instanceof StatusException statusError) {
            return statusError.getStatus()
                    .asRuntimeException(statusError.getTrailers());
        }
        if (error instanceof ProductNotFoundException) {
            return Status.NOT_FOUND
                    .withDescription("Product not found")
                    .asRuntimeException();
        }
        if (error instanceof InvalidProductRequestException) {
            return Status.INVALID_ARGUMENT
                    .withDescription("Invalid product request")
                    .asRuntimeException();
        }
        if (error instanceof DuplicateProductException) {
            return Status.ALREADY_EXISTS
                    .withDescription("Product already exists")
                    .asRuntimeException();
        }
        if (error instanceof ProductLockedException) {
            return Status.FAILED_PRECONDITION
                    .withDescription("Product cannot be changed in its current state")
                    .asRuntimeException();
        }
        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }
}
```

The mapper preserves deliberately created `StatusRuntimeException` instances or the status/trailers of `StatusException`. Business exceptions are mapped explicitly; unrecognized errors become `INTERNAL` with a safe description. In production, log the full exception on the server with a trace/correlation ID and scrub sensitive data.

Do not use `Status.fromThrowable(error)` as the sole policy. It is useful for locating a status in a cause chain, but ordinary Java exceptions can turn into `UNKNOWN`. The mapper should handle known business errors before passing errors to the transport.

## 4. Choosing Statuses Based on Use-Case Behavior

Unary handler example:

```java
@GrpcService
public class CatalogGrpcService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    private final CatalogUseCase catalog;
    private final GrpcStatusMapper statusMapper;

    public CatalogGrpcService(
            CatalogUseCase catalog,
            GrpcStatusMapper statusMapper) {
        this.catalog = catalog;
        this.statusMapper = statusMapper;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<Product> observer) {
        try {
            Product product = catalog.getProduct(request.getProductId());
            observer.onNext(product);
            observer.onCompleted();
        } catch (RuntimeException error) {
            observer.onError(statusMapper.toRuntimeException(error));
        }
    }
}
```

After calling `onError`, do not call `onCompleted`. Each RPC has only one terminal outcome. If the service processes asynchronously, exceptions must be mapped in the callback/future completion where the error actually occurs; a synchronous interceptor cannot catch exceptions thrown after the callback has returned.

A mapping table should be reviewed with the application owner:

| Business Scenario | Suggested Status | Reason |
| --- | --- | --- |
| Blank/malformed Product ID | `INVALID_ARGUMENT` | Client fixes the request |
| Product does not exist | `NOT_FOUND` | Resource is absent |
| Product already exists on create | `ALREADY_EXISTS` | Identifier conflict |
| Product is locked and cannot be edited | `FAILED_PRECONDITION` | State must change first |
| Optimistic lock conflict requiring transaction retry | `ABORTED` | Retry workflow at a higher level |
| Caller is not logged in | `UNAUTHENTICATED` | Missing/invalid credentials |
| Caller does not belong to an authorized tenant | `PERMISSION_DENIED` | Valid identity but lacks permission |
| Dependency temporarily unavailable | `UNAVAILABLE` | May recover later |

This is an illustrative semantic mapping; each specific domain should decide the right contract and keep it stable across versions.

## 5. Checking Statuses with Generated Stubs

With a blocking stub, error statuses are thrown as `StatusRuntimeException`. Tests must assert `Status.Code`, not merely check that an exception was thrown:

```java
@Test
void missingProductReturnsNotFound() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getProduct(
                    GetProductRequest.newBuilder()
                            .setProductId("missing")
                            .build()));

    assertEquals(Status.Code.NOT_FOUND,
            error.getStatus().getCode());
}

@Test
void invalidProductIdReturnsInvalidArgument() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getProduct(
                    GetProductRequest.newBuilder()
                            .setProductId("")
                            .build()));

    assertEquals(Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
}
```

For a successful RPC, the blocking stub returns the response normally; that confirms the final status is `OK`. For an async stub, success is represented by `onCompleted`; errors arrive via `onError`. Clients can use `Status.fromThrowable(error)` to extract the status in the callback.

Do not assert the full description if it is not part of the contract. Descriptions may be refined for clarity; assert the stable code and only assert descriptions/trailers when clients actually depend on them.

## 6. Provider Contract Testing with an In-Process Server

An in-process server lets you invoke the service implementation using a generated stub without opening a TCP port:

```java
class CatalogStatusContractTest {
    private Server server;
    private ManagedChannel channel;
    private CatalogServiceGrpc.CatalogServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String name = InProcessServerBuilder.generateName();
        server = InProcessServerBuilder.forName(name)
                .addService(new CatalogGrpcService(
                        testCatalogUseCase(), new GrpcStatusMapper()))
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(name).build();
        stub = CatalogServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        channel.shutdownNow();
        server.shutdownNow();
        channel.awaitTermination(1, TimeUnit.SECONDS);
        server.awaitTermination(1, TimeUnit.SECONDS);
    }

    @Test
    void missingProductUsesPublishedStatus() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getProduct(
                        GetProductRequest.newBuilder()
                                .setProductId("missing")
                                .build()));

        assertEquals(Status.Code.NOT_FOUND,
                error.getStatus().getCode());
    }
}
```

The fixture `testCatalogUseCase()` represents a controllable use case. You should have tests for each important status branch and a test for unexpected errors to verify the server does not leak internal exceptions. In-process tests verify service behavior through the gRPC runtime; Spring integration tests additionally verify beans, interceptors, security, and the status mapper are registered properly in the application context.

## 7. Checking Trailers and Error Details When Part of the Contract

The status code is the primary part of an error result. Trailers can carry additional metadata clients need, but only include them in the contract when there is a clear use case. For example:

```java
private static final Metadata.Key<String> ERROR_REASON =
        Metadata.Key.of(
                "error-reason",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata trailers = new Metadata();
trailers.put(ERROR_REASON, "PRODUCT_LOCKED");

throw Status.FAILED_PRECONDITION
        .withDescription("Product cannot be changed")
        .asRuntimeException(trailers);
```

A client test can verify the trailer:

```java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.updateProduct(request));

assertEquals(Status.Code.FAILED_PRECONDITION,
        error.getStatus().getCode());
assertEquals("PRODUCT_LOCKED",
        error.getTrailers().get(ERROR_REASON));
```

If using structured error details such as `google.rpc.Status` and detail messages, the version/type of the detail is also a contract to manage. Do not send stack traces, SQL, file paths, internal hostnames, tokens, or personal data via descriptions/trailers. Do not log entire trailers if they could contain credentials.

## 8. How Do Statuses Affect Retries?

Status codes help clients classify retries, though they do not automatically guarantee a retry is safe:

| Status | Typical Consideration |
| --- | --- |
| `UNAVAILABLE` | Retry with backoff if the operation is idempotent or has an idempotency key |
| `ABORTED` | Can retry the transaction/workflow from the beginning |
| `RESOURCE_EXHAUSTED` | Wait for quota/backoff per policy; do not retry aggressively |
| `DEADLINE_EXCEEDED` | Retry only if time budget remains and the operation is known to be safe |
| `CANCELLED` | Typically respect that the caller cancelled |
| `INVALID_ARGUMENT` | Do not retry the same request; input must be fixed |
| `FAILED_PRECONDITION` | Fix system state before calling again |
| `UNAUTHENTICATED` | Refresh/supply credentials first |
| `PERMISSION_DENIED` | Do not retry unless permissions change |

Do not automatically retry every `INTERNAL` or `UNKNOWN` error. For write operations, the server may have committed while the response was lost; retrying without idempotency protection can create duplicate data. Contract tests should verify appropriate statuses so clients can apply retry policies without causing duplicate side effects.

## 9. Testing Statuses for Streaming, Deadlines, and Cancellation

With streaming RPCs, the final status only appears when the stream ends. A stream can emit several messages and then terminate with an error; the client must check both received messages and the terminal status:

```java
List<ProductEvent> received = new ArrayList<>();

StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> {
            Iterator<ProductEvent> events =
                    stub.watchProduct(request);
            while (events.hasNext()) {
                received.add(events.next());
            }
        });

assertFalse(received.isEmpty());
assertEquals(Status.Code.RESOURCE_EXHAUSTED,
        error.getStatus().getCode());
```

This example assumes the contract allows emitting several events before terminating due to quota. If the contract requires all-or-nothing, the server must design stream semantics accordingly and tests should not accept partial results.

Deadline tests should set finite timeouts and use latch-controlled fixtures to coordinate when the server completes; avoid relying solely on `Thread.sleep`, which is prone to flakiness. Clients typically observe `DEADLINE_EXCEEDED` when the deadline expires before the result arrives. However, the server operation may already have completed even if the client did not receive the response in time.

When the client actively cancels, the client typically observes `CANCELLED`; the server must observe cancellation via the call context/`ServerCallStreamObserver` and stop the producer. Do not assume both sides always observe the same status in every race between deadline and transport cancellation.

## 10. Status Contract Checklist

- [ ] Each method has a published table of conditions and status codes.
- [ ] `INVALID_ARGUMENT` is used for invalid requests, `NOT_FOUND` for missing resources, and `UNAUTHENTICATED` is distinguished from `PERMISSION_DENIED`.
- [ ] `FAILED_PRECONDITION`, `ABORTED`, and `OUT_OF_RANGE` are properly distinguished.
- [ ] Business exceptions are mapped centrally and consistently.
- [ ] Deliberately constructed statuses/trailers are preserved.
- [ ] Unexpected errors return a safe status without leaking internal details.
- [ ] Provider tests call via generated stubs and assert `Status.Code`.
- [ ] Streaming tests verify terminal status, partial message semantics, and cancellation.
- [ ] Trailers/error details are asserted only when part of the public contract.
- [ ] Retry policies account for status, idempotency, backoff, and deadlines.
- [ ] Deadline tests have finite, controllable timeouts.
- [ ] Spring integration tests verify mappers/interceptors/security are actually registered.

**Self-Check**

**Question 1.** Why should contract tests assert `Status.Code` rather than just asserting an exception was thrown?

*Answer:* Many statuses are represented as exceptions on the client side yet lead to different handling paths. Asserting the code verifies the server preserves the semantics consumers rely on.

**Question 2.** When should `FAILED_PRECONDITION` be used instead of `INVALID_ARGUMENT`?

*Answer:* `INVALID_ARGUMENT` is used when the request itself is invalid; `FAILED_PRECONDITION` is used when the request may be valid, but the current system state does not yet allow execution.

**Question 3.** Why does `UNAVAILABLE` not automatically mean retrying is always safe?

*Answer:* The server-side operation may already have executed while the response failed to reach the client. For write operations, retrying can repeat side effects without an idempotency key or deduplication mechanism.

**Question 4.** Where does an async client receive error statuses?

*Answer:* In the `StreamObserver.onError` callback; use `Status.fromThrowable` to extract the status. Blocking stubs typically throw `StatusRuntimeException`.

**Question 5.** Why must streaming contract tests verify the terminal status in addition to messages?

*Answer:* A stream can emit partial messages and then end with an error. Consumers need to know whether partial results are valid, and the final status determines how to proceed.

Status code contract testing protects how clients interpret RPC outcomes. Define statuses per business condition, map exceptions centrally, test codes via generated stubs, and verify terminal statuses on streaming calls. When status, retry, and idempotency are tested together, Spring gRPC versions can evolve their implementations while keeping error behavior stable for consumers.
