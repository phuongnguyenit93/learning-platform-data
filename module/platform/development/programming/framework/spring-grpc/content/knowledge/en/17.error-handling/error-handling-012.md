# Testing error status and metadata

**Chapter:** Error handling  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and unary or streaming RPCs. This lesson focuses on testing failed RPC outcomes: status codes, status descriptions, and accompanying metadata, especially trailing metadata sent by the server with errors.

## 1. What should an RPC error test verify?

Checking only that the client throws `StatusRuntimeException` is not enough. A useful test should verify:

1. **Status code:** the client receives the right standard code, such as `NOT_FOUND`, `INVALID_ARGUMENT`, or `PERMISSION_DENIED`.
2. **Description:** if the API commits to a description, the client receives the expected description; if the description is optional, the client still works when it is absent.
3. **Trailers:** whether custom end-of-RPC metadata has the right keys and values.
4. **No fake success data:** an RPC ending in failure must not be mistaken for returning a successful response.
5. **Fallback:** the client works when trailers are missing, keys are unknown, or the error comes from the transport without custom metadata.

Status codes and metadata are part of the API contract. Tests should verify that contract through real gRPC stubs/channels, not just by calling a mapper directly.

## 2. Distinguishing request metadata, response headers, and trailers

gRPC uses `Metadata` for key/value pairs in three places:

| Type | Direction | Timing | How observed on the client |
| --- | --- | --- | --- |
| Request metadata | Client → server | At RPC start | Server interceptor reads the `headers` parameter |
| Initial response headers | Server → client | When response starts | `ClientCall.Listener.onHeaders()` |
| Trailers | Server → client | When RPC completes | `ClientCall.Listener.onClose(status, trailers)`; for blocking errors, `Status.trailersFromThrowable()` can be used |

For RPC errors, the status code and trailers together define the final outcome. Initial response headers do not replace trailers; request metadata is not response metadata either.

Example custom error trailers:

```text
Status:
  code: FAILED_PRECONDITION
  description: Operation is not permitted

Trailers:
  error-code: ACCOUNT_SUSPENDED
  support-reference: req-7f31
  diagnostic-tag-bin: <binary bytes>
```

The client uses the status code for general classification, then reads custom trailers if present. Do not parse the description to look for error codes.

## 3. Declaring metadata keys consistently

Each metadata key needs a name and a marshaller. Text keys use `ASCII_STRING_MARSHALLER`; binary keys must have the `-bin` suffix and use `BINARY_BYTE_MARSHALLER`.

```java
import io.grpc.Metadata;

public final class ErrorMetadata {
    private ErrorMetadata() {}

    public static final Metadata.Key<String> ERROR_CODE =
            Metadata.Key.of(
                    "error-code",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> SUPPORT_REFERENCE =
            Metadata.Key.of(
                    "support-reference",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<byte[]> DIAGNOSTIC_TAG =
            Metadata.Key.of(
                    "diagnostic-tag-bin",
                    Metadata.BINARY_BYTE_MARSHALLER);
}
```

Keys must be defined consistently between server and client. Key names use lowercase; do not use the reserved `grpc-` prefix. Do not declare a key with the same name using different marshallers across application components.

## 4. Server returning status and trailers intentionally

Example service terminating the RPC with `NOT_FOUND` and attaching three trailers:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public class CatalogGrpcService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void getItem(
            GetItemRequest request,
            StreamObserver<GetItemResponse> responseObserver) {

        Metadata trailers = new Metadata();
        trailers.put(ErrorMetadata.ERROR_CODE, "ITEM_NOT_FOUND");
        trailers.put(ErrorMetadata.SUPPORT_REFERENCE, "req-7f31");
        trailers.put(
                ErrorMetadata.DIAGNOSTIC_TAG,
                new byte[] {0x01, 0x02, 0x03});

        responseObserver.onError(
                Status.NOT_FOUND
                        .withDescription("Item not found")
                        .asRuntimeException(trailers));
    }
}
```

In Spring gRPC, real services are usually registered via starter annotations/configuration. Tests can register the implementation directly with an in-process server as in the next example. Trailers contain only non-sensitive codes and references; do not send payloads, tokens, stack traces, or exception messages.

## 5. Testing via in-process gRPC

The in-process transport lets tests invoke generated stubs over a gRPC channel without opening network ports. It still goes through the gRPC call lifecycle, status handling, and internal transport metadata serialization.

Example using JUnit 5, `grpc-inprocess`, and generated protobuf/gRPC classes:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ErrorMetadataIntegrationTest {

    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void setUp() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new CatalogGrpcService())
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
    }

    @AfterEach
    void tearDown() {
        if (channel != null) {
            channel.shutdownNow();
        }
        if (server != null) {
            server.shutdownNow();
        }
    }

    @Test
    void receivesStatusAndCustomTrailers() {
        CatalogServiceGrpc.CatalogServiceBlockingStub stub =
                CatalogServiceGrpc.newBlockingStub(channel);

        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getItem(
                        GetItemRequest.newBuilder()
                                .setItemId("missing-item")
                                .build()));

        Status status = Status.fromThrowable(error);
        assertEquals(Status.Code.NOT_FOUND, status.getCode());
        assertEquals("Item not found", status.getDescription());

        Metadata trailers = Status.trailersFromThrowable(error);
        assertNotNull(trailers);
        assertEquals(
                "ITEM_NOT_FOUND",
                trailers.get(ErrorMetadata.ERROR_CODE));
        assertEquals(
                "req-7f31",
                trailers.get(ErrorMetadata.SUPPORT_REFERENCE));
        assertArrayEquals(
                new byte[] {0x01, 0x02, 0x03},
                trailers.get(ErrorMetadata.DIAGNOSTIC_TAG));
    }
}
```

The test verifies both status and both metadata types. It does not depend on server-side exception message strings or internal exception classes; it only asserts the status code, published description, and contracted trailer keys.

### Why use Status.fromThrowable?

`Status.fromThrowable(error)` extracts the status from a gRPC exception or its cause chain. This is useful if the error is wrapped in another exception. Do not compare `error.getMessage()` because that string can change or contain information not meant for clients.

### Why use Status.trailersFromThrowable?

`Status.trailersFromThrowable(error)` returns trailing metadata if the exception carries any. The value may be `null`; tests must check before calling `get(key)`. For an optional trailer, the client must also tolerate an absent key.

## 6. Testing errors without custom trailers

Not every error is created by an application mapper. Deadlines, cancellations, connection failures, or transport errors may lack business trailers.

Safe assertion example:

```java
@Test
void handlesStatusWithoutCustomTrailers() {
    StatusRuntimeException error =
            Status.INVALID_ARGUMENT
                    .withDescription("Invalid request")
                    .asRuntimeException();

    Status status = Status.fromThrowable(error);
    assertEquals(Status.Code.INVALID_ARGUMENT, status.getCode());

    Metadata trailers = Status.trailersFromThrowable(error);
    assertTrue(
            trailers == null
                    || trailers.get(ErrorMetadata.ERROR_CODE) == null);
}
```

This test verifies that client logic does not require every status to include custom trailers. The application should fall back based on the status code when trailers are missing:

```java
String errorCode = trailers == null
        ? null
        : trailers.get(ErrorMetadata.ERROR_CODE);

if (status.getCode() == Status.Code.NOT_FOUND
        && "ITEM_NOT_FOUND".equals(errorCode)) {
    showItemNotFound();
} else if (status.getCode() == Status.Code.NOT_FOUND) {
    showGenericNotFound();
} else {
    handleOtherStatus(status.getCode());
}
```

Do not let a missing trailer trigger a `NullPointerException` and obscure the original status.

## 7. Testing initial response headers separately from trailers

If an API sends initial response headers, test them through a client interceptor. `onHeaders()` and `onClose(..., trailers)` are two distinct callbacks:

```java
ClientInterceptor captureMetadata = new ClientInterceptor() {
    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(delegate) {
            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata requestHeaders) {
                super.start(new ForwardingClientCallListener
                        .SimpleForwardingClientCallListener<>(listener) {
                    @Override
                    public void onHeaders(Metadata headers) {
                        // Save initial response headers for separate assertion.
                        captureInitialHeaders(headers);
                        super.onHeaders(headers);
                    }

                    @Override
                    public void onClose(Status status, Metadata trailers) {
                        // Status and trailers are the final result of the RPC.
                        captureFinalStatusAndTrailers(status, trailers);
                        super.onClose(status, trailers);
                    }
                }, requestHeaders);
            }
        };
    }
};
```

This is an illustrative skeleton; `captureInitialHeaders` and `captureFinalStatusAndTrailers` are test-recording functions, typically using `AtomicReference` or a test observer. When asserting on async callbacks, synchronize with a latch/future with a timeout instead of `Thread.sleep()`.

If the server does not explicitly send initial headers before failing, the client may receive no custom headers at all. That does not drop the terminal event's status/trailers. Tests must reflect the exact contract the server actually publishes.

## 8. Testing status and metadata in async clients

With an async stub, errors arrive via `StreamObserver.onError(Throwable)`. Use the same API to read status and trailers:

```java
StreamObserver<GetItemResponse> responseObserver =
        new StreamObserver<>() {
    @Override
    public void onNext(GetItemResponse response) {
        fail("This RPC was expected to terminate with an error");
    }

    @Override
    public void onError(Throwable error) {
        Status status = Status.fromThrowable(error);
        Metadata trailers = Status.trailersFromThrowable(error);

        assertEquals(Status.Code.NOT_FOUND, status.getCode());
        assertNotNull(trailers);
        assertEquals(
                "ITEM_NOT_FOUND",
                trailers.get(ErrorMetadata.ERROR_CODE));
    }

    @Override
    public void onCompleted() {
        fail("Must not complete successfully");
    }
};

CatalogServiceGrpc.newStub(channel).getItem(request, responseObserver);
```

In real tests, do not perform async assertions without propagating assertion failures back to the test thread. Use a `CompletableFuture` completed when `onError` or `onCompleted` runs, then assert on the test thread with a finite timeout.

With client streaming or server streaming, also verify the count of response messages before the terminal error. If the server returned a valid partial response before failing, the contract must clearly state which data the client is allowed to retain; do not assume a terminal error erases already-received messages.

## 9. Error status and metadata test matrix

| Test case | Expected status | Metadata/assertion |
| --- | --- | --- |
| Item not found | `NOT_FOUND` | Has `error-code=ITEM_NOT_FOUND` |
| Invalid request | `INVALID_ARGUMENT` | Trailer may be absent; client still handles it |
| Insufficient permission | `PERMISSION_DENIED` | No tokens or internal policy details sent |
| Invalid credentials | `UNAUTHENTICATED` | Credentials not echoed in description/trailers |
| Dependency temporarily failing | `UNAVAILABLE` | May include support reference; optional |
| Deadline expired | `DEADLINE_EXCEEDED` | Do not assume custom trailers always exist |
| Unexpected internal error | `INTERNAL` | Generic description, no stack trace |
| Binary trailer | Status matching error | Read using `-bin` key and binary marshaller |
| Initial response headers | Final status may be an error | Asserted via `onHeaders()`, separate from trailers |

Tests should verify both present values and missing values. A resilient client does not depend on every server, proxy, or transport sending the exact same set of optional metadata.

## 10. Common testing mistakes

- **Asserting only that an exception was thrown:** does not prove the status code or metadata are right.
- **Parsing description to infer error code:** fragile when wording changes; use status enums and trailer keys.
- **Assuming trailers are always non-null:** transport errors may have no custom metadata.
- **Confusing headers with trailers:** they arrive at different times and in different callbacks.
- **Using an ASCII marshaller for byte arrays:** binary keys must have the `-bin` suffix and a binary marshaller.
- **Failing to shut down test channels/servers:** leaks threads and prevents test suites from terminating cleanly.
- **Using sleep to wait for callbacks:** creates flaky tests; use futures/latches and timeouts.
- **Putting a secret in a fixture and checking only status:** must assert that descriptions/trailers do not echo tokens or sensitive payloads.

## 11. Metadata security and compatibility

Metadata is observable by clients. Do not send access tokens, passwords, PII, SQL, stack traces, or large payloads in trailers. Only send stable error codes, non-sensitive support references, and small details published in the contract.

Clients need to ignore unknown keys and handle missing optional keys. When renaming a key or changing the semantics of an error code, treat it as a contract change: update documentation, compatibility tests, and client/server rollout plans. If rich error structure is needed, consider protobuf error details like `google.rpc.BadRequest` or `google.rpc.ErrorInfo` instead of stuffing large amounts of data into metadata strings.

## 12. Self-practice

1. Write a test verifying that `NOT_FOUND`, a description, and an `error-code` trailer are received accurately by the client over an in-process channel.
2. Why must `Status.trailersFromThrowable()` be handled when it returns `null`?
3. A response has initial headers and terminal trailers. Design two independent assertions for `onHeaders()` and `onClose()`.
4. Write a test for the binary trailer `diagnostic-tag-bin`; why does the key require the `-bin` suffix?
5. A client receives `UNAVAILABLE` without custom trailers. How should it handle this without depending on optional metadata?

**Remember:** Error-handling tests must verify **status code, description, and trailers** over a real gRPC call. Use `Status.fromThrowable()` to read status, `Status.trailersFromThrowable()` to read trailing metadata, handle missing trailers, and verify initial headers separately via `onHeaders()`. Base assertions on stable codes/keys, not by parsing exception message strings.
