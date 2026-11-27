# Trailers carrying error information

**Chapter:** Error handling  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers, generated Java code, and unary or streaming RPCs. This lesson focuses on **trailing metadata**: how the server attaches business error codes or handling support information to a failed response, and how the client reads those values.

## 1. What are trailers?

A gRPC response can have metadata at the start of the response (*headers*) and metadata at the end of the response (*trailers*). Trailers are sent when the RPC finishes, along with the final status of the call. When the server returns an error, trailers are the right place to send small structured information that helps the client understand the specific error.

For example, the server returns the general status `FAILED_PRECONDITION`, while also sending `error-code = ACCOUNT_SUSPENDED`. The client can rely on the status code for general error classification and rely on `error-code` to choose the corresponding message or business action.

```text
gRPC response completes
    |
    +-- gRPC status
    |     +-- code: FAILED_PRECONDITION
    |     +-- description: optional explanatory message
    |
    +-- trailing metadata
          +-- error-code: ACCOUNT_SUSPENDED
          +-- support-reference: req-8f31
```

Trailers differ from:

- **Protobuf response body:** the business data of a successful response. When an RPC ends in failure, the client usually does not receive a success response body.
- **Initial metadata/headers:** metadata sent at the start of the response, before or together with response data. Trailers exist only at the end of the RPC.
- **Status description:** an explanatory string inside the gRPC status; custom trailers are separate metadata pairs with a key and marshaller type.
- **Java cause/exception:** internal server-side causes are not automatically transmitted as Java objects to the client.

Trailers are useful when the client needs a machine-readable error code without parsing description wording. They do not replace the status code and should not become a place to carry large business payloads.

## 2. Declaring metadata keys in gRPC Java

gRPC Java uses `io.grpc.Metadata` to represent headers and trailers. Each key requires a marshaller that defines how to convert the Java value into bytes on the wire and back.

### ASCII string values

```java
import io.grpc.Metadata;

public final class ErrorTrailerKeys {
    private ErrorTrailerKeys() {}

    public static final Metadata.Key<String> ERROR_CODE =
            Metadata.Key.of(
                    "error-code",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> SUPPORT_REFERENCE =
            Metadata.Key.of(
                    "support-reference",
                    Metadata.ASCII_STRING_MARSHALLER);
}
```

Metadata key names must be lowercase according to gRPC rules. Do not use the `grpc-` prefix for application-defined keys because that namespace is reserved for the protocol. Text keys use `ASCII_STRING_MARSHALLER`; if binary data needs to be transmitted, the key must have the `-bin` suffix and use a binary marshaller.

### Byte values

```java
public static final Metadata.Key<byte[]> ERROR_CONTEXT =
        Metadata.Key.of(
                "error-context-bin",
                Metadata.BINARY_BYTE_MARSHALLER);
```

Only use a binary trailer when small binary data is truly needed. Do not invent an unversioned byte format without decoding rules; if error data has a complex structure, consider the standardized protobuf error model in section 6.

## 3. Spring gRPC server attaching trailers on error

The server creates a `Metadata`, puts values into it, and passes it into the exception created from `Status`. With gRPC callbacks, the server terminates the RPC using `responseObserver.onError(...)`.

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

private static final Metadata.Key<String> ERROR_CODE =
        Metadata.Key.of(
                "error-code",
                Metadata.ASCII_STRING_MARSHALLER);

private static final Metadata.Key<String> SUPPORT_REFERENCE =
        Metadata.Key.of(
                "support-reference",
                Metadata.ASCII_STRING_MARSHALLER);

void rejectSuspendedAccount(
        StreamObserver<TransferResponse> responseObserver,
        String requestReference) {

    Metadata trailers = new Metadata();
    trailers.put(ERROR_CODE, "ACCOUNT_SUSPENDED");
    trailers.put(SUPPORT_REFERENCE, requestReference);

    responseObserver.onError(
            Status.FAILED_PRECONDITION
                    .withDescription("Account cannot perform this transaction yet")
                    .asRuntimeException(trailers));
}
```

Here:

- `FAILED_PRECONDITION` is the standard status code, used to classify a state that does not allow the operation.
- `withDescription(...)` provides human-readable explanatory information; sensitive details should not be included here.
- `error-code` is a stable business code for client handling.
- `support-reference` helps correlate the request with internal logs/traces, and is not an authentication token.

After `responseObserver.onError(...)`, the response observer is terminated. Do not call `onNext()` or `onCompleted()` on the same observer.

### Using in a service implementation

```java
@GrpcService
public class TransferGrpcService
        extends TransferServiceGrpc.TransferServiceImplBase {

    private final TransferApplicationService service;

    public TransferGrpcService(TransferApplicationService service) {
        this.service = service;
    }

    @Override
    public void transfer(
            TransferRequest request,
            StreamObserver<TransferResponse> responseObserver) {
        try {
            TransferResponse response = service.transfer(request);
            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (AccountSuspendedException error) {
            Metadata trailers = new Metadata();
            trailers.put(ErrorTrailerKeys.ERROR_CODE, "ACCOUNT_SUSPENDED");
            trailers.put(ErrorTrailerKeys.SUPPORT_REFERENCE,
                    error.requestReference());

            responseObserver.onError(
                    Status.FAILED_PRECONDITION
                            .withDescription(
                                    "Account cannot perform this transaction yet")
                            .asRuntimeException(trailers));
        } catch (RuntimeException unexpected) {
            // Log exception details on the server, do not send stack trace to the client.
            log.error("Unexpected transfer failure", unexpected);
            responseObserver.onError(
                    Status.INTERNAL
                            .withDescription("Internal server error")
                            .asRuntimeException());
        }
    }
}
```

This snippet illustrates where business errors are mapped. In a real application, use a consistent logger and correlation ID; avoid catching every `RuntimeException` and accidentally masking serious unrecoverable errors. Status/trailer mapping can be placed in a shared helper or exception mapper.

## 4. Client reading trailers from RPC errors

With a blocking stub, the client typically catches `StatusRuntimeException`. With an async stub, the `onError(Throwable)` callback receives the exception when the RPC ends in failure. Both cases can use `Status.trailersFromThrowable(...)`.

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

try {
    TransferResponse response = blockingStub.transfer(request);
    handleSuccess(response);
} catch (StatusRuntimeException error) {
    Status status = Status.fromThrowable(error);
    Metadata trailers = Status.trailersFromThrowable(error);

    String errorCode = trailers == null
            ? null
            : trailers.get(ErrorTrailerKeys.ERROR_CODE);

    String supportReference = trailers == null
            ? null
            : trailers.get(ErrorTrailerKeys.SUPPORT_REFERENCE);

    if (status.getCode() == Status.Code.FAILED_PRECONDITION
            && "ACCOUNT_SUSPENDED".equals(errorCode)) {
        showAccountSuspended();
    } else {
        showGenericRpcFailure(status.getCode(), supportReference);
    }
}
```

Always handle the case where `trailers == null` or the key has no value. Not every error is intentionally created by the server with custom trailers: deadlines, cancellations, connection errors, or proxies can cause the client not to receive expected application keys.

### In an async callback

```java
StreamObserver<TransferResponse> responseObserver = new StreamObserver<>() {
    @Override
    public void onNext(TransferResponse response) {
        handleSuccess(response);
    }

    @Override
    public void onError(Throwable error) {
        Status status = Status.fromThrowable(error);
        Metadata trailers = Status.trailersFromThrowable(error);
        String code = trailers == null
                ? null
                : trailers.get(ErrorTrailerKeys.ERROR_CODE);

        handleFailure(status.getCode(), code);
    }

    @Override
    public void onCompleted() {
        finishCall();
    }
};
```

Do not parse `status.getDescription()` looking for the string `ACCOUNT_SUSPENDED`. The description is for human readers; custom trailers have dedicated keys for direct retrieval by the client. Also do not assume the `onError` callback always receives the exact exception class created by the server: the RPC boundary transfers status and metadata, not server-side Java objects.

## 5. Trailers and status codes have different roles

The status code must be sufficient for the client to handle general error categories even when custom trailers are absent. Trailers add business detail and should not be the sole condition for understanding the error.

| Status code | Trailer `error-code` | Meaning and handling |
| --- | --- | --- |
| `INVALID_ARGUMENT` | `INVALID_ACCOUNT_ID` | Invalid request; client fixes data |
| `NOT_FOUND` | `CUSTOMER_NOT_FOUND` | Resource not found |
| `FAILED_PRECONDITION` | `ACCOUNT_SUSPENDED` | Business state does not allow it |
| `RESOURCE_EXHAUSTED` | `TENANT_QUOTA_EXCEEDED` | Quota exceeded; wait or shed load per policy |
| `UNAVAILABLE` | May be absent | Temporary service/transport error; retry only if operation is safe |
| `INTERNAL` | Usually no internal details sent | Server error; use support reference if investigation is needed |

If the status is `FAILED_PRECONDITION` but the trailer is missing, the client must still handle it as a general precondition failure. If the trailer contains a code unknown to the client (because the server deployed a new version), the client should fall back based on the status code rather than failing during parsing.

Do not use trailers to replace standard statuses. For example, do not return `UNKNOWN` and require every client to read `error-code` to understand the error; choose the appropriate status code first.

## 6. Design conventions and versioning

Custom trailers are key/value metadata without a strong protobuf schema. Therefore, conventions must be published:

- **Stable key names:** e.g., `error-code`, `support-reference`; use lowercase and do not use the reserved `grpc-` prefix.
- **Stable values:** codes like `ACCOUNT_SUSPENDED` do not depend on language or description wording.
- **Version compatibility:** clients must ignore unknown keys; the server must not change the meaning of an existing code without a versioning plan.
- **Optional values:** clients always have a fallback when a trailer is missing, stripped, or not sent.
- **Small size:** only send codes, references, or short metrics. Do not put large error lists, business objects, or file payloads into trailers.

If rich structure, multiple nested fields, or a list of error details is needed, consider the standard `google.rpc.Status` error model with `google.rpc.ErrorInfo`, `BadRequest`, `RetryInfo`, or appropriate protobuf details. These details are typically packed into the `grpc-status-details-bin` binary metadata by gRPC ecosystem convention; corresponding client/server dependencies and support are required. Do not use protocol-reserved keys on your own to hold custom formats.

## 7. Security and metadata limits

Trailers travel along the same RPC path and can be logged by proxies, gateways, or instrumentation. Treat them as data observable by clients and intermediary infrastructure.

- Do not send passwords, access tokens, session cookies, secret keys, or unnecessary personal information.
- Do not send SQL, stack traces, table names, internal file paths, or server topology details.
- Use a random/hard-to-guess support reference or a trace ID that carries no sensitive data; look up detailed logs on the server side only.
- Keep metadata small to avoid gRPC, HTTP/2, and proxy header/trailer limits.
- Do not put large payloads into an ASCII value; binary metadata is also subject to size limits.
- Only send trailers once the final status is determined; do not treat trailers as a channel for exchanging messages while a stream is running.

If an error might contain sensitive data, only send a generic status code and support reference. The server stores controlled details in internal logs.

## 8. Testing server sending and client reading trailers

Unit tests can verify keys and marshallers, but RPC tests are needed to verify that metadata actually reaches the client. The example below uses in-process gRPC, JUnit 5, and a minimal service:

```java
@GrpcService
class TrailerTestService extends TransferServiceGrpc.TransferServiceImplBase {
    @Override
    public void transfer(
            TransferRequest request,
            StreamObserver<TransferResponse> responseObserver) {
        Metadata trailers = new Metadata();
        trailers.put(ErrorTrailerKeys.ERROR_CODE, "ACCOUNT_SUSPENDED");
        trailers.put(ErrorTrailerKeys.SUPPORT_REFERENCE, "test-ref-17");

        responseObserver.onError(
                Status.FAILED_PRECONDITION
                        .withDescription("Operation is not allowed")
                        .asRuntimeException(trailers));
    }
}
```

The client test invokes the stub and asserts the status along with custom metadata:

```java
@Test
void receivesCustomErrorTrailers() throws Exception {
    // in-process server/channel initialized in @BeforeEach.
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> TransferServiceGrpc.newBlockingStub(channel)
                    .transfer(TransferRequest.getDefaultInstance()));

    assertEquals(Status.Code.FAILED_PRECONDITION,
            Status.fromThrowable(error).getCode());

    Metadata trailers = Status.trailersFromThrowable(error);
    assertNotNull(trailers);
    assertEquals("ACCOUNT_SUSPENDED",
            trailers.get(ErrorTrailerKeys.ERROR_CODE));
    assertEquals("test-ref-17",
            trailers.get(ErrorTrailerKeys.SUPPORT_REFERENCE));
}
```

Tests require the `grpc-inprocess` dependency, JUnit 5, and the generated protobuf/gRPC classes. If testing a real Spring service, initialize the Spring context or register the service implementation with the in-process server according to the test configuration.

Additional cases to cover:

| Case | What to verify |
| --- | --- |
| Server returns status without custom trailers | Client has no null error; still handles by status code |
| Trailer has key unknown to client | Client ignores unknown key |
| Status has description but lacks `error-code` | Client falls back by status |
| Trailer has binary key `-bin` | Client uses matching binary marshaller to read it |
| RPC hits deadline or is cancelled | Client accepts that trailers may not exist |
| Trailer has support reference | Value contains no tokens or secret data |

## 9. Self-practice

1. Create an ASCII `retry-after-ms` key and send it with status `RESOURCE_EXHAUSTED`. How should the client handle a missing or malformed value?
2. Why should the client check the status code first before interpreting a custom trailer?
3. Design a backward-compatible business error code when the server adds a new code that older clients do not yet recognize.
4. When needing to send a list of multiple validation error fields, why is a custom-formatted string trailer not a good choice?
5. Write an integration test verifying the server sends `FAILED_PRECONDITION`, a description, and two custom trailers; also test the case where the server sends no trailers.

**Remember:** Trailers are **end-of-RPC metadata**, suited for sending small business error codes or support references alongside a status. The server builds `Metadata` and passes it to `Status.asRuntimeException(trailers)` for `responseObserver.onError()`; the client reads them with `Status.trailersFromThrowable()`, always handles missing keys, and uses the status code as the foundation for error classification. Do not put secrets or large payloads into trailers.
