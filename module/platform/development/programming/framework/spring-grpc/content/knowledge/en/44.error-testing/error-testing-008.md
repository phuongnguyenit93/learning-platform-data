# Testing INTERNAL Without Leaking Details

In **SPRING_GRPC**, when an unexpected error occurs in an application use case or infrastructure, the gRPC adapter typically must return `INTERNAL` to the client. This status indicates that the server could not complete the RPC due to an internal error. It should not reveal SQL, table names, stack traces, file paths, hostnames, tokens, secrets, or technical messages from exceptions.

A safe error response still needs to help clients and operations teams look up incidents. The right approach is to return status `INTERNAL` with a stable description, accompanied by a non-sensitive error ID via metadata trailers; on the server side, record the error ID and diagnostic details according to the logging policy. This lesson presents how to design that contract and test it from the mapper and adapter to the client's perspective.

## 1. Define What May Be Exposed to the Client

An internal exception may contain information that does not belong in the public API:

```text
org.postgresql.util.PSQLException:
  ERROR: duplicate key value violates unique constraint
  Detail: Key (email)=(alice@example.test) already exists.
  SQL: INSERT INTO customer ...
  Connection: jdbc:postgresql://db-prod-03.internal:5432/customer
```

If the adapter returns `exception.getMessage()` or a stack trace directly in the Status, clients can learn database structure, user data, internal hostnames, or server implementation details.

Define the public error contract clearly:

| Component | Return to Client? | Rule |
| --- | --- | --- |
| gRPC code `INTERNAL` | Yes | Stable, client can categorize it |
| Description `Internal server error` | Yes | Generic message, independent of exception |
| Error ID | Yes | Random/unique value for lookup |
| Exception class | Not needed | Keep in internal telemetry/logs if allowed |
| Exception message | No | May contain SQL, data, or secrets |
| Stack trace | No | For controlled internal diagnostics only |
| SQL, hostname, file path | No | Internal implementation details |
| Token, password, key | No | Secrets must never enter responses |

Clients need to know at what level the RPC failed and provide an error ID when reporting an incident. Clients do not need to know which database the server uses, which SQL query failed, or which line of code threw the exception.

## 2. Keep Known Error Mapping Separate from Unexpected Errors

Not every error is `INTERNAL`. Errors with public, well-defined meaning must preserve their corresponding status:

- Invalid request: `INVALID_ARGUMENT`.
- Resource does not exist: `NOT_FOUND`.
- Unauthenticated caller: `UNAUTHENTICATED`.
- Caller lacks permission: `PERMISSION_DENIED`.
- Business state conflict: `FAILED_PRECONDITION` or `ABORTED` per semantics.
- Unexpected server error: `INTERNAL`.

Do not turn known business errors into `INTERNAL` just to hide exception messages. Map known errors to the appropriate public status with a safe description. This lesson's rules apply to unexpected errors that the client cannot handle via a specific business contract.

## 3. Generate an Error ID and Metadata Trailer

The error ID should be a random code or unique identifier that does not contain user IDs, emails, tenant names, SQL keys, or business data. A UUID is a simple choice.

Declare a metadata key:

```java
import io.grpc.Metadata;

public final class GrpcErrorMetadata {

    private GrpcErrorMetadata() {
    }

    public static final Metadata.Key<String> ERROR_ID =
            Metadata.Key.of(
                    "x-error-id",
                    Metadata.ASCII_STRING_MARSHALLER);
}
```

Create a mapper solely responsible for building the public response:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Component;

@Component
public class GrpcInternalErrorMapper {

    public StatusRuntimeException toInternal(String errorId) {
        Metadata trailers = new Metadata();
        trailers.put(GrpcErrorMetadata.ERROR_ID, errorId);

        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException(trailers);
    }
}
```

The mapper does not accept an exception message to prevent accidentally putting that message into the description or trailers. The error ID is generated in the adapter/error handler, then shared between logs and the response.

Do not attach `DebugInfo`, stack traces, or `google.rpc.ErrorInfo` containing implementation details to a public `INTERNAL` error. If the API needs a machine-readable error category, send only approved, stable reason codes; the error ID remains the way to look up a specific incident.

## 4. Log Internal Errors in a Controlled Manner

The adapter generates an error ID, logs diagnostics, and returns the generic response:

```java
private static final Logger log =
        LoggerFactory.getLogger(CatalogGrpcService.class);

private final Supplier<String> errorIdSupplier;
private final GrpcInternalErrorMapper internalErrors;

private void reportUnexpected(
        RuntimeException cause,
        StreamObserver<?> observer) {

    String errorId = errorIdSupplier.get();

    // Log only approved fields; do not log messages or payloads.
    log.error(
            "Unexpected gRPC failure: errorId={}, exceptionType={}",
            errorId,
            cause.getClass().getName());

    observer.onError(internalErrors.toInternal(errorId));
}
```

This logging approach avoids writing `cause.getMessage()` or stack traces that may contain sensitive data into general application logs. If stack traces are needed for investigation, send them to a restricted-access diagnostic sink with appropriate redaction mechanisms. Do not enable logging of full protobuf requests or raw metadata to find root causes.

In a service method:

```java
@Override
public void getItem(
        GetItemRequest request,
        StreamObserver<GetItemReply> observer) {
    try {
        ItemView item = getItemUseCase.execute(
                new GetItemQuery(request.getItemId()));

        observer.onNext(mapper.toProto(item));
        observer.onCompleted();
    } catch (ItemNotFoundException error) {
        observer.onError(Status.NOT_FOUND
                .withDescription("Item not found")
                .asRuntimeException());
    } catch (RuntimeException error) {
        reportUnexpected(error, observer);
    }
}
```

The example maps one known domain error and routes unexpected errors into a single handling path. In larger applications, this logic can be placed in a shared error handler/interceptor so adapters do not duplicate code.

Do not catch `Throwable` to map everything to `INTERNAL`. Serious JVM errors such as `OutOfMemoryError` should not be handled like a normal RPC error.

## 5. Common Places Where Exception Details Leak

Check the entire error path, not just `Status.withDescription`:

1. **Status description**: do not use `exception.getMessage()`, `toString()`, or stack traces.
2. **Metadata trailers**: include only the error ID or explicitly allowed public keys.
3. **Rich error details**: do not pack `DebugInfo`, SQL details, or exception objects.
4. **Application logs**: do not log raw tokens, request payloads, or unredacted messages.
5. **Tracing attributes**: do not attach exception messages, SQL parameters, or personal data to span tags.
6. **Metrics labels**: do not use error IDs, user IDs, or exception messages as high-cardinality labels.
7. **Gateway/proxy**: confirm intermediaries do not replace the status with a body containing exception details.

The error ID should appear in logs and trailers with the exact same value. Clients send this ID to support teams; operators search logs by ID to investigate. Do not use the error ID as an authorization credential or allow anyone holding the ID to read logs directly.

## 6. Unit Test for the Error Mapper

Unit tests verify the code, description, trailers, and absence of internal data:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class GrpcInternalErrorMapperTest {

    private final GrpcInternalErrorMapper mapper =
            new GrpcInternalErrorMapper();

    @Test
    void returnsGenericInternalWithOnlyErrorIdTrailer() {
        String errorId = "err-test-42";
        StatusRuntimeException result = mapper.toInternal(errorId);

        Status status = Status.fromThrowable(result);
        Metadata trailers = Status.trailersFromThrowable(result);

        assertEquals(Status.Code.INTERNAL, status.getCode());
        assertEquals("Internal server error", status.getDescription());
        assertNotNull(trailers);
        assertEquals(
                errorId,
                trailers.get(GrpcErrorMetadata.ERROR_ID));
        assertEquals(
                Set.of("x-error-id"),
                trailers.keys());
        assertNull(result.getCause());
    }
}
```

The test confirms the mapper takes no exception and attaches no cause to the exception sent to the client. If the contract allows additional trailers, replace the key-set assertion with an explicit allowlist and verify each value.

## 7. Test the Adapter When a Use Case Throws an Error Containing a Secret

An important test must use an exception message intentionally containing simulated sensitive data, then verify that data does not appear in the observer error:

```java
@Test
void unexpectedFailureDoesNotExposeExceptionMessage() {
    String secret = "db-password=not-for-client";
    RuntimeException failure =
            new IllegalStateException(secret);

    when(getItem.execute(new GetItemQuery("item-42")))
            .thenThrow(failure);

    List<GetItemReply> values = new ArrayList<>();
    AtomicReference<Throwable> receivedError = new AtomicReference<>();
    AtomicBoolean completed = new AtomicBoolean();

    StreamObserver<GetItemReply> observer = new StreamObserver<>() {
        @Override
        public void onNext(GetItemReply value) {
            values.add(value);
        }

        @Override
        public void onError(Throwable error) {
            receivedError.set(error);
        }

        @Override
        public void onCompleted() {
            completed.set(true);
        }
    };

    service.getItem(
            GetItemRequest.newBuilder()
                    .setItemId("item-42")
                    .build(),
            observer);

    Throwable rpcFailure = receivedError.get();
    Status status = Status.fromThrowable(rpcFailure);
    Metadata trailers = Status.trailersFromThrowable(rpcFailure);

    assertEquals(Status.Code.INTERNAL, status.getCode());
    assertEquals("Internal server error", status.getDescription());
    assertFalse(status.getDescription().contains(secret));
    assertNotNull(trailers);
    assertEquals(Set.of("x-error-id"), trailers.keys());
    assertFalse(trailers.toString().contains(secret));
    assertFalse(completed.get());
    assertTrue(values.isEmpty());
}
```

To make tests deterministic, inject `Supplier<String>` into the adapter; production can use `() -> UUID.randomUUID().toString()`, while tests return a fixed ID. Do not rely on random UUIDs to assert a specific value. Tests should also verify the unexpected-error mapper is called exactly once and no successful response is emitted before the error. Required imports for the example include `List`, `ArrayList`, `AtomicReference`, `AtomicBoolean`, and `StreamObserver`.

## 8. Test from the gRPC Client Perspective Using In-Process Transport

Direct adapter tests verify observer callbacks. In-process gRPC tests go one step further: the generated client stub receives status and trailers through the gRPC call pipeline without opening a TCP port.

Test scope requires a `grpc-inprocess` dependency compatible with the grpc-java version in use. Test skeleton:

```java
String serverName = InProcessServerBuilder.generateName();

Server server = InProcessServerBuilder
        .forName(serverName)
        .directExecutor()
        .addService(service)
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();

try {
    CatalogServiceGrpc.CatalogServiceBlockingStub client =
            CatalogServiceGrpc.newBlockingStub(channel);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> client.getItem(
                    GetItemRequest.newBuilder()
                            .setItemId("item-42")
                            .build()));

    Status status = Status.fromThrowable(error);
    Metadata trailers = Status.trailersFromThrowable(error);

    assertEquals(Status.Code.INTERNAL, status.getCode());
    assertEquals("Internal server error", status.getDescription());
    assertEquals("err-test-42",
            trailers.get(GrpcErrorMetadata.ERROR_ID));
    assertEquals(Set.of("x-error-id"), trailers.keys());
} finally {
    channel.shutdownNow();
    server.shutdownNow();
    channel.awaitTermination(5, TimeUnit.SECONDS);
    server.awaitTermination(5, TimeUnit.SECONDS);
}
```

In this test, the adapter uses an error ID supplier returning `err-test-42`. In-process transport verifies the status/trailers seen by the generated client through the gRPC runtime. It does not test TLS, HTTP/2 sockets, proxies, or load balancers; those behaviors require separate network integration tests.

## 9. Test Streaming Errors

With server-streaming, the server may have already sent several messages before an unexpected error occurs. The adapter must terminate the stream with a generic `INTERNAL` status and emit no messages after the terminal signal.

Tests should confirm:

- Valid messages sent before the error are preserved.
- Terminal status is `INTERNAL`.
- Description is only the generic message.
- Trailers contain only the allowed error ID.
- No `onCompleted()` follows `onError()`.
- Exception details do not appear in any public message/trailer.

Messages already sent cannot be recalled. Therefore, do not place sensitive data into responses before the operation reaches a safe state for disclosure. For client-streaming/bidirectional streaming, apply the same rules to the response observer and ensure only one terminal signal is sent.

## 10. Check Logging and Observability

A safe response is not enough if logs or traces leak the same information. Define a dedicated policy for each channel:

| Channel | Information to Keep | Information to Remove/Redact |
| --- | --- | --- |
| gRPC response | `INTERNAL`, generic description, error ID | Exception message, stack trace, SQL, secret |
| Application log | Error ID, RPC method, exception type, timestamp | Token, payload, PII, and unredacted messages |
| Restricted diagnostics | Redacted stack trace, if policy allows | Secrets and unnecessary user data |
| Trace/span | RPC method, status code, trace ID | Raw metadata, token, SQL parameters |
| Metrics | Status code, service/method | Error ID, user ID, exception message as labels |

Do not use error ID as a metrics label because each error can generate a new value and cause unbounded cardinality growth. Error IDs belong in logs/trailers; metrics should group by service, method, and status code.

## 11. Common Testing Mistakes

| Mistake | Why It Is Insufficient | How to Fix |
| --- | --- | --- |
| Only asserting code `INTERNAL` | Description or trailers may still leak details | Assert description and trailer allowlist |
| Only testing the mapper | Adapter might bypass mapper and return exception message directly | Test service implementation with an exception containing a secret |
| Only testing the observer directly | Does not verify the client receives trailers | Add an in-process gRPC test |
| Logging full exceptions to general logs | Message/stack may contain sensitive data | Log error ID/type; use a controlled diagnostic sink |
| Putting stack traces in `google.rpc.DebugInfo` | Client receives internal details | Do not send debug details in public INTERNAL |
| Sending an error ID containing user/email | Trailer leaks personal data | Use a random, meaningless ID |
| Asserting `Status.toString()` | Depends on non-contract formatting | Assert code, description, and metadata keys/values |
| Using in-process tests to conclude TLS works | In-process does not use TLS sockets | Have network tests for TLS/mTLS |

## 12. Checklist for a Public INTERNAL Contract

Before releasing an adapter, verify:

- [ ] Unexpected errors return `Status.Code.INTERNAL`.
- [ ] Description is a generic, stable message.
- [ ] No exception cause/message/stack trace appears in the response.
- [ ] Trailers contain only the error ID and allowlisted keys.
- [ ] Error ID contains no personal data or secrets.
- [ ] Logs contain the error ID for lookup without logging raw requests/tokens.
- [ ] Tests use a simulated exception message containing a secret and verify no leak.
- [ ] In-process client tests verify actual status/trailers.
- [ ] Streaming tests verify the terminal signal and no emissions after error.
- [ ] Network/security tests verify gateway, TLS, and logging pipeline where needed.

### Takeaways

**`INTERNAL` must describe a server failure at a public level, not become a broadcast channel for exception details.** Return a generic description, a safe error ID via trailers, and keep diagnostic information inside controlled internal systems. Test the mapper, adapter, and generated client to prove SQL, stack traces, hostnames, tokens, or secrets do not appear in status, details, or metadata received by the client.

## References

- [gRPC — Error Handling](https://grpc.io/docs/guides/error/)
- [gRPC — Status Codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC Java — Status](https://grpc.github.io/grpc-java/javadoc/io/grpc/Status.html)
- [gRPC Java — Metadata](https://grpc.github.io/grpc-java/javadoc/io/grpc/Metadata.html)
- [gRPC Java — InProcessServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/inprocess/InProcessServerBuilder.html)
