# Do not expose stack traces or sensitive data

**Chapter:** Error handling  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers, generated Java code, and unary or streaming RPCs. This lesson focuses on **keeping internal diagnostic information on the server while returning only safe statuses and error information to the client**.

## 1. Error responses are also a security boundary

When an RPC fails, the server typically terminates with `responseObserver.onError(...)`. Everything the server puts in the gRPC status description, trailers, or error details can reach the client. The client may be a legitimate application, or it may be an older version, a third-party integration, or a caller attempting to probe internal information.

Unsafe example:

```java
catch (Exception error) {
    responseObserver.onError(
            Status.INTERNAL
                    .withDescription(error.getMessage())
                    .asRuntimeException());
}
```

`error.getMessage()` may contain SQL statements, table names, file paths, internal hostnames, access tokens, emails, phone numbers, or request data. Passing it verbatim into the description turns internal diagnostic information into public API data.

Stack traces can also reveal internal packages, class names, library versions, deployment paths, and system structure. **Do not send stack traces, causes, or raw exception messages in statuses, trailers, or protobuf responses.**

The information boundary should be designed as follows:

```text
Internal exception / failure
        |
        +----> Controlled internal log/diagnostics
        |        - exception class
        |        - stack trace when permitted
        |        - trace/support reference
        |        - redacted data
        |
        +----> Public gRPC response
                 - appropriate status code
                 - generic, safe description
                 - stable error code if needed
                 - non-sensitive support reference
```

## 2. Data that should not be returned to the client

| Data | Why it is sensitive | How to handle |
| --- | --- | --- |
| Stack trace | Reveals code structure, libraries, and internal paths | Keep only in controlled internal diagnostic systems |
| SQL/queries and table names | Reveals schema, data access logic, and sometimes input values | Return a generic status; log filtered diagnostics |
| Passwords, API keys, access/refresh tokens | Can allow unauthorized access | Do not log or send in error metadata |
| PII such as emails, phone numbers, addresses | Can be leaked through logs or responses | Use minimized identifiers only; mask or remove |
| Protobuf payload | May contain secrets or customer data | Do not serialize full requests into error logs |
| File paths, hostnames, internal IPs | Exposes infrastructure and data locations | Use generic messages and internal lookup references |
| Raw exception message | Has no safety or stability guarantees | Map by error type; use controlled descriptions |

Even when a value is not an authentication secret, concatenating it into a description or log can still create privacy risks. Expose only the information the client needs to handle the error.

## 3. Designing safe error responses

An error response should typically include:

1. **gRPC status code:** machine-readable classification, such as `NOT_FOUND`, `INVALID_ARGUMENT`, `UNAVAILABLE`, or `INTERNAL`.
2. **Short, controlled description:** explains enough for the client without implementation details.
3. **Optional application error code:** a stable code such as `CUSTOMER_NOT_FOUND` or `VALIDATION_FAILED`.
4. **Optional support reference:** a lookup token for operations teams to find internal logs, containing no tokens or PII.

Example:

```text
Status: INTERNAL
Description: Internal server error
Trailers:
  error-code: INTERNAL_FAILURE
  support-reference: 7f1a9c2e
```

The client can display a generic message and give the support reference to customer support. The server uses the reference to locate detailed diagnostics in a protected logging system.

Do not use a generic status code to hide every error type. If an error is known, keep the status aligned with the API semantics; the security rule only requires that **descriptions and metadata do not leak sensitive details**.

## 4. Mapping exceptions without exposing raw messages

A mapper at the gRPC boundary can classify exceptions and build descriptions only from safe constants:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class SafeGrpcErrorMapper {

    private static final Logger log =
            LoggerFactory.getLogger(SafeGrpcErrorMapper.class);

    public static final Metadata.Key<String> ERROR_CODE =
            Metadata.Key.of(
                    "error-code",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> SUPPORT_REFERENCE =
            Metadata.Key.of(
                    "support-reference",
                    Metadata.ASCII_STRING_MARSHALLER);

    public StatusRuntimeException map(Throwable error) {
        String reference = UUID.randomUUID().toString();
        Status status;
        String applicationCode;

        if (error instanceof CustomerNotFoundException) {
            status = Status.NOT_FOUND
                    .withDescription("Resource not found");
            applicationCode = "CUSTOMER_NOT_FOUND";
        } else if (error instanceof RequestValidationException) {
            status = Status.INVALID_ARGUMENT
                    .withDescription("Invalid request data");
            applicationCode = "VALIDATION_FAILED";
        } else {
            status = Status.INTERNAL
                    .withDescription("Internal server error");
            applicationCode = "INTERNAL_FAILURE";

            // Do not write the exception message or payload to regular logs.
            log.error("gRPC request failed: reference={}, exceptionType={}",
                    reference, error.getClass().getName());
            // If a stack trace is needed, route it through a separate diagnostic sink
            // with appropriate access controls, retention, and redaction.
        }

        Metadata trailers = new Metadata();
        trailers.put(ERROR_CODE, applicationCode);
        trailers.put(SUPPORT_REFERENCE, reference);
        return status.asRuntimeException(trailers);
    }
}
```

The example uses a `UUID` as an illustrative reference; systems can use a trace ID or incident ID generated at the gateway. The reference must not contain customer information and must not be usable as a credential. If the request already carries a trace ID from trusted infrastructure, validate/normalize it before using it to correlate logs.

The mapper does not call `error.getMessage()`, does not attach `error` as the cause of the status returned to the client, and does not serialize the exception. If deep diagnostics are required, send the exception to controlled internal diagnostic storage instead of putting it into gRPC metadata.

### Preserving intentionally created status exceptions

A lower layer may already have created a `StatusRuntimeException` with a valid status and trailers. In that case, the adapter can preserve the status/trailers, while still checking whether the description and metadata are safe to expose. Do not assume every exception from a library or downstream service is safe to forward verbatim.

## 5. Using the mapper in a Spring gRPC service

In a unary RPC, the adapter only returns a success response when processing completes; on error, it sends the sanitized status:

```java
@GrpcService
public class CustomerGrpcService
        extends CustomerServiceGrpc.CustomerServiceImplBase {

    private final CustomerApplicationService applicationService;
    private final SafeGrpcErrorMapper errorMapper;

    public CustomerGrpcService(
            CustomerApplicationService applicationService,
            SafeGrpcErrorMapper errorMapper) {
        this.applicationService = applicationService;
        this.errorMapper = errorMapper;
    }

    @Override
    public void findCustomer(
            FindCustomerRequest request,
            StreamObserver<Customer> responseObserver) {
        try {
            Customer customer =
                    applicationService.find(request.getCustomerId());
            responseObserver.onNext(toProto(customer));
            responseObserver.onCompleted();
        } catch (Exception error) {
            responseObserver.onError(errorMapper.map(error));
        }
    }
}
```

This snippet illustrates the adapter boundary. In production code, only catch exceptions that the adapter can map; do not catch `Throwable` and mask serious JVM errors. Request validation, domain exceptions, and infrastructure errors should be clearly classified before falling back to `INTERNAL`.

### Streaming RPC

For client streaming or server streaming, the same principles apply to each terminal path:

- If an error is detected while receiving a message, stop processing and call `responseObserver.onError(safeError)` exactly once.
- If the inbound stream is cancelled by the client, clean up resources; do not try to send a new error response on an already-cancelled call.
- On success, send the final response and then call `onCompleted()`.
- Do not call `onNext()` or `onCompleted()` after `onError()`.

Do not log the entire request stream when an error occurs at the 500th message. Instead, log a controlled batch ID, sequence, message count received, status code, and support reference. If payloads need to be captured for investigation, enforce a dedicated data policy rather than enabling payload logging automatically.

## 6. Internal logs must also protect data

"Do not send stack traces to the client" does not mean server logs can contain everything. Logs are often forwarded to many systems: collectors, dashboards, archives, alerts, and observability vendors. Each destination is a data access surface.

### Structured and minimal logging

An operational error log usually only needs:

- timestamp and severity;
- gRPC service/method;
- gRPC status code and application error code;
- support reference or trace ID;
- exception class (if useful);
- minimized or pseudonymized tenant/user identifier when needed;
- message/byte counts or processing duration, not payloads.

Example:

```java
log.warn(
        "gRPC operation rejected: method={}, status={}, errorCode={}, reference={}",
        "CustomerService/FindCustomer",
        "NOT_FOUND",
        "CUSTOMER_NOT_FOUND",
        supportReference);
```

Avoid:

```java
// Risk: message may contain SQL, tokens, or request data.
log.error("Request failed: request={}, error={}", request, error.getMessage());
```

If a stack trace is needed for unexpected errors, write it to a separate diagnostic sink with restricted access, appropriate retention, and redaction procedures. Inspect exception messages/causes because libraries can embed query parameters or input values into them. Do not automatically route the same detailed logs to every appender.

### Preventing log injection

Do not concatenate client-controlled values verbatim into log messages. Strings containing newlines or control characters can forge multiple log lines. Prefer structured logging; limit length, normalize, or strip control characters for free-form text fields.

## 7. Description, trailers, and TLS do not replace each other

| Component | Readable by client? | Safe usage |
| --- | --- | --- |
| Status description | Yes | Short, generic string without raw exception messages |
| Custom trailers | Yes | Small error codes/references without secrets |
| Protobuf error details | Yes | Only data allowed to be exposed per contract |
| Server logs | Not an RPC response, but accessible to many internal systems | Control permissions, retention, and redaction |
| Internal stack trace/cause | Not transmitted automatically over the wire | Keep in a protected diagnostic channel |

TLS encrypts the transport between endpoints, **but it does not make data inside the response secret from the client receiving that response**. The client is allowed to read the status and trailers sent by the server. Therefore, TLS cannot be used as an excuse to return stack traces or tokens in error metadata.

## 8. Testing to detect information leaks

Tests should check more than just the status code. They must assert that the description and trailers do not contain secrets, exception messages, or stack traces.

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SafeGrpcErrorMapperTest {

    private final SafeGrpcErrorMapper mapper = new SafeGrpcErrorMapper();

    @Test
    void unexpectedFailureDoesNotExposeExceptionMessage() {
        String secret = "Bearer-super-secret-token";
        RuntimeException internal =
                new RuntimeException("SQL failed with token " + secret);

        StatusRuntimeException rpcError = mapper.map(internal);
        Status status = rpcError.getStatus();

        assertEquals(Status.Code.INTERNAL, status.getCode());
        assertEquals("Internal server error", status.getDescription());
        assertFalse(status.getDescription().contains(secret));

        Metadata trailers = Status.trailersFromThrowable(rpcError);
        assertNotNull(trailers);
        assertEquals("INTERNAL_FAILURE",
                trailers.get(SafeGrpcErrorMapper.ERROR_CODE));
        assertFalse(trailers.get(SafeGrpcErrorMapper.SUPPORT_REFERENCE)
                .contains(secret));
    }

    @Test
    void knownDomainErrorKeepsSafePublicMeaning() {
        StatusRuntimeException rpcError = mapper.map(
                new CustomerNotFoundException("customer-private-123"));

        assertEquals(Status.Code.NOT_FOUND,
                rpcError.getStatus().getCode());
        assertEquals("Resource not found",
                rpcError.getStatus().getDescription());
        assertFalse(rpcError.getStatus().getDescription()
                .contains("customer-private-123"));
    }
}
```

In the example, metadata keys are declared `public` or package-private so tests can access them; adjust visibility according to project structure. Additional integration tests via in-process gRPC should verify that the client actually receives the sanitized status/trailers.

### Security test matrix

| Case | Assertion |
| --- | --- |
| Exception message contains a token | Description and trailers do not contain the token |
| Exception message contains SQL or internal path | Does not appear in the RPC response |
| Domain error has a customer ID | Public description does not echo the ID |
| Unexpected error | Status `INTERNAL`, generic description, includes support reference |
| Known error | Specific status code, controlled description |
| No trailers | Client handles missing values |
| Mid-stream error | No success receipt after terminal error |
| Logging | Regular logs do not contain request objects, payloads, credentials, or raw PII |

Log tests should use a test/capture appender to verify logged content, not just check the response. Diagnostic sinks containing stack traces should be verified for access controls and redaction under operational policy.

## 9. Pre-release API checklist

- [ ] Status code accurately reflects the error category; `INTERNAL` is not used as the default for every exception.
- [ ] Description is built from controlled messages, not taken directly from `getMessage()`.
- [ ] Stack traces, causes, SQL, internal paths, or payloads are not sent in status/trailers.
- [ ] Error codes and support references contain no credentials or PII.
- [ ] Clients have fallbacks when descriptions/trailers are missing or contain unknown codes.
- [ ] Regular logs are structured, minimal, and stripped of sensitive data.
- [ ] Diagnostic stack traces reside only where access controls and retention are appropriate.
- [ ] Client-controlled values are bounded/normalized to prevent log injection.
- [ ] Tests verify that neither responses nor logs leak secrets.
- [ ] TLS is configured, without treating TLS as a substitute for data minimization.

## 10. Self-practice

1. A database exception has a message containing SQL and a customer email. Design a safe status description, trailer, and log entry for that error.
2. Why shouldn't you call `log.error("failure", exception)` to every appender if the exception message may contain sensitive data?
3. Design a support reference that clients can provide to support teams without being able to use that reference to access resources.
4. Write an integration test verifying that a streaming error sends no receipt and does not expose the failing message's payload.
5. TLS is already enabled on the channel. Why must the server still omit stack traces and tokens from trailers?

**Remember:** Error responses are public data to the client. Return meaningful status codes, generic descriptions, safe error codes, and safe support references; keep stack traces/causes and exception details in protected internal diagnostics. Never arbitrarily log or send payloads, credentials, PII, and infrastructure data; test both responses and logs for leaks.
