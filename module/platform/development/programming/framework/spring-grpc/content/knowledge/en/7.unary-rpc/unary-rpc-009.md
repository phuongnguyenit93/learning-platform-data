# Status Errors in Unary Calls

## 1. Status Is the Terminal Outcome of an RPC

A **unary RPC** sends one request and receives one response on success. At the gRPC layer, every call ends with a **status**:

- `OK`: the server completed successfully; the client receives exactly one protobuf response.
- Non-`OK` status: the call ended in failure; the client receives no successful business response.

A status consists of a standard code, an optional description, and optional metadata in trailers. In gRPC Java, common types are `io.grpc.Status`, `StatusRuntimeException`, and `StatusException`.

A status is not an `error` field inside the response message. When the server invokes `responseObserver.onError(...)`, the client receives an RPC error; the server must not send a dummy response and complete with `OK`. This distinction lets clients handle errors consistently whether the server is written in Java, Go, Python, or another language.

## 2. Choosing a Status Code Based on Failure Semantics

gRPC defines a shared set of status codes. Choosing the right code matters more than writing a long description, because clients should branch on the **code**.

| Status code | When to use | Example in a unary RPC |
| --- | --- | --- |
| `INVALID_ARGUMENT` | Request data is invalid regardless of current system state. | Empty `product_id` or negative quantity. |
| `NOT_FOUND` | The requested resource does not exist. | No product matches the supplied ID. |
| `ALREADY_EXISTS` | Creating a resource failed due to duplicate or ID conflict. | Order ID is already taken. |
| `UNAUTHENTICATED` | Caller is unauthenticated or credentials are invalid. | Missing, expired, or invalid token. |
| `PERMISSION_DENIED` | Caller is authenticated but lacks permission for the action. | User cannot view another tenant's order. |
| `FAILED_PRECONDITION` | System is not in a state allowing the operation. | Cannot cancel an already shipped order. |
| `ABORTED` | Operation aborted due to a transaction or concurrency conflict. | Optimistic lock conflict on update. |
| `OUT_OF_RANGE` | Value falls outside the valid operational range. | Page or offset exceeds supported bounds. |
| `RESOURCE_EXHAUSTED` | Quota or allocated resources exhausted. | Request rate or capacity limit exceeded. |
| `UNAVAILABLE` | Service or dependency is temporarily unavailable. | Service starting up or lost dependency connection. |
| `DEADLINE_EXCEEDED` | Call deadline expired. | Client did not receive a result within the deadline. |
| `CANCELLED` | Call was cancelled by the caller or parent context. | User cancelled an in-flight action. |
| `UNIMPLEMENTED` | Method or feature is not implemented. | Client invokes an RPC the server does not support yet. |
| `INTERNAL` | Unexpected internal server error. | Unhandled processing failure. |
| `DATA_LOSS` | Unrecoverable data loss or corruption. | Detected unreadable record due to corruption. |
| `UNKNOWN` | Error could not be classified specifically. | An intermediate layer failed to preserve the original status. |

Three easily confused groups:

- `INVALID_ARGUMENT`: the request is bad regardless of resource state.
- `FAILED_PRECONDITION`: the request may be valid, but current state forbids executing it.
- `ABORTED`: a conflict requires coordinating or retrying at a higher level.

For example: `quantity = -1` is `INVALID_ARGUMENT`; cancelling a delivered order is `FAILED_PRECONDITION`; a failed update due to an optimistic lock conflict can be `ABORTED`.

Never use `INTERNAL` for every business error. Likewise, never return `OK` with a response carrying an `"error"` string when the contract models failures via gRPC statuses.

## 3. Mapping Business Errors to Statuses in a Spring gRPC Server

The server should translate errors at the RPC boundary: known business errors to matching statuses, and unexpected errors to `INTERNAL`.

Example unary contract:

```proto
syntax = "proto3";

package catalog.v1;

option java_package = "com.example.catalog.grpc";
option java_multiple_files = true;

service ProductQueryService {
  rpc GetProduct (GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string name = 2;
}
```

Example implementation with Spring gRPC:

```java
package com.example.catalog.server;

import com.example.catalog.grpc.GetProductRequest;
import com.example.catalog.grpc.GetProductResponse;
import com.example.catalog.grpc.ProductQueryServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.grpc.server.service.GrpcService;

import java.util.Optional;

@GrpcService
public class ProductQueryGrpcService
        extends ProductQueryServiceGrpc.ProductQueryServiceImplBase {

    private static final Logger log =
            LoggerFactory.getLogger(ProductQueryGrpcService.class);

    private final ProductCatalog catalog;

    public ProductQueryGrpcService(ProductCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<GetProductResponse> observer) {

        String productId = request.getProductId().trim();

        if (productId.isEmpty()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("product_id must not be empty")
                    .asRuntimeException());
            return;
        }

        try {
            Optional<Product> found = catalog.findById(productId);

            if (found.isEmpty()) {
                observer.onError(Status.NOT_FOUND
                        .withDescription("Product not found")
                        .asRuntimeException());
                return;
            }

            Product product = found.get();
            observer.onNext(GetProductResponse.newBuilder()
                    .setProductId(product.id())
                    .setName(product.name())
                    .build());
            observer.onCompleted();

        } catch (SecurityException denied) {
            observer.onError(Status.PERMISSION_DENIED
                    .withDescription("Not authorized to view product")
                    .asRuntimeException());

        } catch (RuntimeException unexpected) {
            // Log the full exception on the server; never send stack traces to the client.
            log.error("Unexpected error in ProductQueryService/GetProduct",
                    unexpected);
            observer.onError(Status.INTERNAL
                    .withDescription("Unable to process request")
                    .asRuntimeException());
        }
    }
}
```

`ProductCatalog` and `Product` are illustrative application types. Observer terminal lifecycle rules:

- Success: call `onNext(response)` once, then `onCompleted()`.
- Failure: call `onError(status.asRuntimeException())` and exit the handler branch.
- After `onError`, never call `onNext` or `onCompleted`.
- Never emit more than one terminal signal for the same RPC.

`Status.INVALID_ARGUMENT`, `Status.NOT_FOUND`, and similar constants are standard statuses. `withDescription(...)` attaches a concise diagnostic message; descriptions are not machine-readable codes and must never include SQL, stack traces, tokens, personal data, or internal details.

### Do not collapse every exception into one status

When the business layer throws well-defined exceptions, the gRPC adapter should map them according to the contract:

| Application exception | Suggested status |
| --- | --- |
| `ProductNotFoundException` | `NOT_FOUND` |
| `InvalidProductQueryException` | `INVALID_ARGUMENT` |
| `ProductAccessDeniedException` | `PERMISSION_DENIED` |
| `ProductStateConflictException` | `FAILED_PRECONDITION` or `ABORTED`, depending on cause |
| Unexpected failure | `INTERNAL` |

Mapping logic can live in a shared helper or component if multiple handlers share the same rules. Interceptors are well suited for logging, metrics, tracing, and cross-cutting concerns; avoid using an interceptor to guess the semantics of every business exception without method context.

## 4. Receiving and Handling Statuses in a Blocking Client

When a unary RPC ends with anything other than `OK`, the blocking stub throws `StatusRuntimeException`. The client should inspect `getStatus().getCode()` to translate it into an application error:

```java
package com.example.catalog.client;

import com.example.catalog.grpc.GetProductRequest;
import com.example.catalog.grpc.GetProductResponse;
import com.example.catalog.grpc.ProductQueryServiceGrpc;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryClient {

    private final ProductQueryServiceGrpc.ProductQueryServiceBlockingStub stub;

    public ProductQueryClient(
            ProductQueryServiceGrpc.ProductQueryServiceBlockingStub stub) {
        this.stub = stub;
    }

    public GetProductResponse getProduct(String productId) {
        try {
            return stub.getProduct(GetProductRequest.newBuilder()
                    .setProductId(productId)
                    .build());

        } catch (StatusRuntimeException failure) {
            Status.Code code = failure.getStatus().getCode();

            switch (code) {
                case NOT_FOUND ->
                        throw new ProductNotFoundException(productId, failure);
                case INVALID_ARGUMENT ->
                        throw new IllegalArgumentException(
                                "Invalid product information", failure);
                case UNAUTHENTICATED ->
                        throw new RemoteAuthenticationException(failure);
                case PERMISSION_DENIED ->
                        throw new ProductAccessDeniedException(failure);
                case FAILED_PRECONDITION, ABORTED ->
                        throw new ProductStateConflictException(failure);
                case DEADLINE_EXCEEDED ->
                        throw new RemoteCallTimeoutException(failure);
                case UNAVAILABLE, RESOURCE_EXHAUSTED ->
                        throw new RemoteServiceUnavailableException(failure);
                default ->
                        throw new RemoteGrpcException(
                                "ProductQueryService call failed", failure);
            }
        }
    }
}
```

Exceptions such as `ProductNotFoundException` and `RemoteAuthenticationException` are project-defined application exceptions. This example illustrates **status classification**, not retries. Retry policies must be decided separately per method and idempotency profile.

Never branch on `failure.getStatus().getDescription()`: descriptions can vary across versions or locales. Also avoid catching `Exception` and returning a default response, which hides transport failures and misleads callers into thinking the call succeeded.

### Future stub and async stub

The same status surfaces differently depending on the stub type:

| Client type | Error path |
| --- | --- |
| Blocking stub | Throws `StatusRuntimeException` directly. |
| Future stub | Future fails; calling `get()` may throw `ExecutionException`, with the status in its cause. |
| Async stub | Calls `StreamObserver.onError(Throwable)`. |

With a future or wrapper exception, use `Status.fromThrowable(cause)` to extract the gRPC status:

```java
Status status = Status.fromThrowable(failure);
Status.Code code = status.getCode();

if (code == Status.Code.NOT_FOUND) {
    // Translate into an appropriate application result or exception.
}
```

If no gRPC status is found in the cause chain, `Status.fromThrowable(...)` returns `UNKNOWN`. Never assume every exception originated on the server; errors can also occur inside the client, callbacks, or data mapping code.

## 5. Descriptions, Trailers, and Structured Error Details

Status codes answer **what kind of error occurred**. Descriptions aid diagnostics, while trailers can carry extra metadata when the RPC terminates. For example, the server attaches a stable error identifier for a business error:

```java
private static final Metadata.Key<String> ERROR_ID =
        Metadata.Key.of(
                "x-error-id",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata trailers = new Metadata();
trailers.put(ERROR_ID, "PRODUCT_STATE_LOCKED");

observer.onError(Status.FAILED_PRECONDITION
        .withDescription("Product cannot currently be updated")
        .asRuntimeException(trailers));
```

The client can read trailers from `StatusRuntimeException`:

```java
Metadata trailers = failure.getTrailers();

if (trailers != null) {
    String errorId = trailers.get(ERROR_ID);
    // Use errorId to correlate with logs or error documentation.
}
```

Metadata keys must follow gRPC/HTTP/2 header naming rules; use lowercase and include only small, non-sensitive values. Never send access tokens, stack traces, SQL, or large payloads in trailers. `x-error-id` is a system-defined diagnostic code, not a replacement for the status code.

For systems requiring rich, cross-language structured errors, you can adopt the `google.rpc.Status` model with standard error details such as `BadRequest`, `PreconditionFailure`, `ResourceInfo`, or `RetryInfo`. Clients should only depend on details they understand; standard status codes remain the minimum compatibility signal. Align on detail schemas and protobuf dependencies across services before adopting them.

## 6. Boundary Between gRPC Statuses and HTTP/Application Errors

Do not mechanically map gRPC statuses to HTTP codes by matching numbers or names. A gateway or REST adapter should translate errors according to the external API contract. For example, `NOT_FOUND` may map to HTTP 404 and `INVALID_ARGUMENT` to 400, whereas `UNAVAILABLE` is typically a transient service error; exact HTTP choices depend on the API gateway and application semantics.

Inside the application, keep three layers distinct:

1. **gRPC status:** transport communication outcome between client and server.
2. **Application exception/result:** how the business layer represents classified errors.
3. **HTTP/UI/message response:** how errors are presented to external callers.

Do not let application services depend directly on `StatusRuntimeException` outside the integration layer. The client adapter should translate statuses into application exceptions/results; controllers or message handlers decide how to present them next.

## 7. Testing Statuses for Unary RPCs

Tests should verify both the status code and the observer's terminal behavior. With gRPC Java, use `InProcessServerBuilder` and `InProcessChannelBuilder` to test without opening a TCP port.

Example test verifying the client receives `NOT_FOUND`:

```java
@Test
void returnsNotFoundForMissingProduct() throws Exception {
    String name = InProcessServerBuilder.generateName();

    Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new ProductQueryGrpcService(testCatalog))
            .build()
            .start();

    ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

    try {
        ProductQueryServiceGrpc.ProductQueryServiceBlockingStub stub =
                ProductQueryServiceGrpc.newBlockingStub(channel);

        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getProduct(GetProductRequest.newBuilder()
                        .setProductId("missing")
                        .build()));

        assertEquals(Status.Code.NOT_FOUND,
                error.getStatus().getCode());
    } finally {
        channel.shutdownNow();
        server.shutdownNow();
    }
}
```

`testCatalog` is a test fixture configured to have no product with ID `missing`. The example requires JUnit Jupiter and a `grpc-inprocess` dependency compatible with the project's gRPC Java version.

Minimum test matrix:

| Scenario | Expected status |
| --- | --- |
| Request with empty ID | `INVALID_ARGUMENT` |
| Product does not exist | `NOT_FOUND` |
| Caller lacks permission | `PERMISSION_DENIED` |
| Caller unauthenticated | `UNAUTHENTICATED` |
| Product in a state forbidding updates | `FAILED_PRECONDITION` |
| Unexpected failure | `INTERNAL` with safe description |
| Success | One response and terminal status `OK` |

In addition to client tests, verify that handlers do not emit `onNext` before `onError`, do not emit two terminal signals, and never leak internal exceptions in descriptions. For errors with trailers, verify the client can read the error ID without any sensitive data attached.

In-process tests validate gRPC semantics and status mapping; they do not test TLS, TCP/HTTP/2, load balancing, or real security configuration. Those require integration tests over real transport.

## 8. Observing Statuses in Production

Status codes are a vital signal for tracking reliability. Record:

- RPC counts by service, method, and status code.
- Error rates by client/server and deployment version.
- p50/p95/p99 latency per method and status.
- Spikes in `INTERNAL`, `UNAVAILABLE`, and `RESOURCE_EXHAUSTED` errors.
- Correlation ID or trace ID to connect logs across client and server.

Never use free-form descriptions or request IDs as metric labels due to high cardinality. Never log full requests/responses or credentials. For `INTERNAL`, log the stack trace on the server alongside the trace ID; return only safe information and a correlatable error code to the client.

Interceptors are ideal for measuring latency, counting statuses, attaching trace context, and standardizing logging. Business status selection should remain in handlers or exception translators that have method context.

## 9. Common Mistakes

1. **Using `INTERNAL` for every error.** Clients cannot distinguish bad requests, missing resources, or system failures. Map domain errors to appropriate statuses.
2. **Returning `OK` with a response containing an error string.** Breaks terminal status semantics and forces every client to inspect payloads.
3. **Branching on descriptions.** Descriptions are not stable error codes. Use `Status.Code`.
4. **Sending stack traces or SQL in descriptions.** Risks exposing internal architecture and sensitive data. Log details on the server and return safe messages.
5. **Confusing `FAILED_PRECONDITION` with `INVALID_ARGUMENT`.** One means current system state forbids the action; the other means the request itself is invalid.
6. **Calling `onError` and continuing to send a response.** Each RPC has only one terminal outcome. Exit the handler branch immediately after `onError`.
7. **Catching errors too broadly on the client and returning a default response.** Masks connectivity errors and corrupts business results. Translate statuses into explicit exceptions/results.
8. **Putting business error mapping in a generic interceptor.** Interceptors lacking method context can misclassify errors. Keep domain mapping in handlers or appropriate adapters.

## 10. Practice Exercise

Extend `ProductQueryService` with a unary `UpdateProductName` method. Design statuses for: missing ID in request, product not found, unauthorized caller, product locked, and unexpected storage failure.

Write unit/integration tests proving:

- Each business failure returns the expected status code.
- The client translates statuses into corresponding application exceptions.
- Status descriptions contain no stack traces or sensitive data.
- Errors with an error ID in trailers can be correlated against logs.
- Success sends exactly one response and completes normally.

**Self-check:** For a unary RPC, success is **one response with status `OK`**; failure is **a non-`OK` status**, optionally carrying a description and trailers. Pick codes by failure semantics, map business errors on the server, inspect codes on the client, and keep diagnostics safe so Spring gRPC services handle errors consistently.
