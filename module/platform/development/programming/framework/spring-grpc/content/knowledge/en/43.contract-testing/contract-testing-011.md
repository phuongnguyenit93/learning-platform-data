# Error Detail Contracts

gRPC communicates errors using a status code and message in response trailers. When an API needs to describe structured errors so clients can handle them accurately, Google's **rich error model** can be used: a `google.rpc.Status` message containing a code, a message, and a list of `google.protobuf.Any` details. In Java, grpc-java's `StatusProto` converts between rich statuses and `StatusRuntimeException`.

An error detail contract specifies which detail types clients can rely on, which fields are required, what each value means, and how to behave when encountering unknown details. A good contract helps clients display validation errors, make retry decisions, assist operators, and stay compatible when the server introduces new detail types.

## 1. Rich Error Structure

A rich error consists of:

- **gRPC status code:** a stable code every client can handle at a coarse level, such as `INVALID_ARGUMENT`, `NOT_FOUND`, or `RESOURCE_EXHAUSTED`.
- **Message:** a brief description for humans or logs; should not be data parsed for client logic.
- **Details:** a list of `Any` containing typed Protobuf messages, such as `google.rpc.BadRequest` or `google.rpc.ErrorInfo`.

On the wire, rich status is sent in the binary trailer metadata `grpc-status-details-bin`. The basic gRPC status code and message are still present; rich status supplements them with structured information. Proxies or gateways must preserve this trailer if clients are expected to receive details.

Example of a validation error:

~~~text
google.rpc.Status
  code: INVALID_ARGUMENT
  message: "request validation failed"
  details:
    - google.rpc.BadRequest
        field_violations:
          - field: "email"
            description: "must be a valid email address"
~~~

Clients can rely on the detail type and field path to display errors next to the corresponding field instead of parsing message strings.

## 2. Choosing Detail Types by Meaning

Google provides common detail types in the `google.rpc` package:

| Detail type | Purpose | Example Usage |
| --- | --- | --- |
| `BadRequest` | Lists fields violating validation | Missing or malformed required field |
| `ErrorInfo` | Stable error code and classification metadata | `reason`, `domain`, non-sensitive metadata |
| `RetryInfo` | Suggested wait time before retrying | Rate limiting or temporarily overloaded dependency |
| `ResourceInfo` | Describes the resource related to the error | Resource type, name, and owner |
| `PreconditionFailure` | Lists unmet preconditions | Version/state no longer suitable |
| `QuotaFailure` | Lists quota violations | Tenant exceeded storage quota |

Choose details by semantics rather than creating a single catch-all message covering every case. The status code remains the high-level signal; details explain the cause and appropriate action. For example, validation typically uses `INVALID_ARGUMENT` with `BadRequest`; quotas can use `RESOURCE_EXHAUSTED` with `QuotaFailure`.

## 3. Adding Java Libraries

Java applications need grpc protobuf integration and Google common protos message definitions. Maven dependency example; versions must be managed consistently with the project's BOM or dependency management:

~~~xml
<dependency>
  <groupId>io.grpc</groupId>
  <artifactId>grpc-protobuf</artifactId>
</dependency>
<dependency>
  <groupId>com.google.api.grpc</groupId>
  <artifactId>proto-google-common-protos</artifactId>
</dependency>
~~~

`StatusProto` resides in grpc protobuf integration; classes such as `com.google.rpc.Status`, `BadRequest`, and `ErrorInfo` are generated from Google common protos. Avoid declaring incompatible Protobuf runtime versions in the same dependency graph.

## 4. Server Producing Structured Error Details

Example service validating a request and returning `BadRequest` when the email is invalid:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import io.grpc.Status;
import io.grpc.protobuf.StatusProto;
import io.grpc.stub.StreamObserver;

public final class RegistrationGrpcService
        extends RegistrationServiceGrpc.RegistrationServiceImplBase {

    @Override
    public void register(
            RegisterRequest request,
            StreamObserver<RegisterResponse> observer) {

        if (!request.getEmail().contains("@")) {
            BadRequest detail = BadRequest.newBuilder()
                .addFieldViolations(
                    BadRequest.FieldViolation.newBuilder()
                        .setField("email")
                        .setDescription("must be a valid email address")
                        .build())
                .build();

            com.google.rpc.Status richStatus =
                com.google.rpc.Status.newBuilder()
                    .setCode(Status.Code.INVALID_ARGUMENT.value())
                    .setMessage("request validation failed")
                    .addDetails(Any.pack(detail))
                    .build();

            observer.onError(
                StatusProto.toStatusRuntimeException(richStatus));
            return;
        }

        observer.onNext(RegisterResponse.newBuilder()
            .setRegistrationId("reg-123")
            .build());
        observer.onCompleted();
    }
}
~~~

The server should construct details from standardized validation results or domain errors. Never put stack traces, SQL, tokens, secrets, credential contents, or unnecessary personal data into messages/details. Messages should be stable enough to aid diagnostics; clients must not rely on message text for branching logic.

## 5. Client Reading Details While Keeping Status Fallback

Clients check the status code first, then unpack detail types they understand:

~~~java
import com.google.rpc.BadRequest;
import com.google.rpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.protobuf.StatusProto;

try {
    RegisterResponse response = stub.register(request);
    // Handle successful response.
} catch (StatusRuntimeException error) {
    Status richStatus = StatusProto.fromThrowable(error);

    if (error.getStatus().getCode()
            == io.grpc.Status.Code.INVALID_ARGUMENT
            && richStatus != null) {
        for (com.google.protobuf.Any detail : richStatus.getDetailsList()) {
            if (detail.is(BadRequest.class)) {
                BadRequest badRequest = detail.unpack(BadRequest.class);
                badRequest.getFieldViolationsList().forEach(violation ->
                    showFieldError(
                        violation.getField(),
                        violation.getDescription()));
            }
        }
    } else {
        handleGrpcStatus(error.getStatus().getCode());
    }
}
~~~

`StatusProto.fromThrowable` may not find a rich status in the throwable, for example if the server/proxy only sent a basic status. Therefore the client must always have a fallback branch based on the gRPC status code. If no details are received or an unsupported detail is encountered, the client still handles the coarse error gracefully instead of crashing.

When unpacking, check the type using `Any.is(Class)` before `unpack(Class)`. Do not assume the first detail is always the type you need; the list can contain multiple details and order should not imply priority unless the contract specifies it.

## 6. Contract Tests for Status Codes and Details

Contract tests must verify both layers:

1. **Status semantics:** the gRPC code matches the error category.
2. **Detail schema:** the expected detail type and required contract fields are present.

The in-process test below calls a generated blocking stub and verifies `INVALID_ARGUMENT` together with `BadRequest`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.rpc.BadRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.protobuf.StatusProto;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class RegistrationErrorContractTest {

    private Server server;
    private ManagedChannel channel;
    private RegistrationServiceGrpc.RegistrationServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new RegistrationGrpcService())
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = RegistrationServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);
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
    void invalidEmailReturnsInvalidArgumentWithBadRequestDetail() {
        RegisterRequest request = RegisterRequest.newBuilder()
            .setEmail("not-an-email")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.register(request));

        assertEquals(
            Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());

        com.google.rpc.Status richStatus =
            StatusProto.fromThrowable(error);
        assertNotNull(richStatus);
        assertEquals(
            Status.Code.INVALID_ARGUMENT.value(),
            richStatus.getCode());

        BadRequest detail = richStatus.getDetailsList().stream()
            .filter(any -> any.is(BadRequest.class))
            .map(any -> {
                try {
                    return any.unpack(BadRequest.class);
                } catch (com.google.protobuf.InvalidProtocolBufferException ex) {
                    throw new AssertionError(ex);
                }
            })
            .findFirst()
            .orElseThrow();

        assertEquals(1, detail.getFieldViolationsCount());
        assertEquals("email", detail.getFieldViolations(0).getField());
        assertEquals(
            "must be a valid email address",
            detail.getFieldViolations(0).getDescription());
    }
}
~~~

In-process transport tests the service, generated stub, and rich status within the same JVM. Add integration tests across real transports/proxies if gateways, ingresses, or load balancers might strip trailer metadata. The contract must be verified along the exact path production clients use.

## 7. Compatibility When Adding or Encountering New Detail Types

`Any` carries a type URL and Protobuf payload. Older clients may encounter a detail type added by a newer server for which the client lacks the class or does not yet know how to interpret. Compatible design must follow these rules:

- Clients ignore unknown detail types and continue relying on the basic status code.
- Servers preserve meaningful fallback status codes and messages even when clients cannot read details.
- Add new details additively; never alter the meaning of existing detail types.
- Never change or reuse field numbers in Protobuf detail messages.
- If semantics change, introduce a new reason/version or new detail type instead of silently mutating the old contract.
- Clients do not depend on detail ordering unless the contract explicitly specifies it.

A server can send multiple details in the same rich status, such as `ErrorInfo` to classify the error and `BadRequest` to pinpoint offending fields. Clients only process the types they understand.

## 8. Using ErrorInfo for Stable Error Codes

`ErrorInfo` provides `reason`, `domain`, and metadata. Example:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.ErrorInfo;
import io.grpc.Status;
import io.grpc.protobuf.StatusProto;

ErrorInfo errorInfo = ErrorInfo.newBuilder()
    .setReason("EMAIL_ALREADY_REGISTERED")
    .setDomain("registration.acme.example")
    .putMetadata("field", "email")
    .build();

com.google.rpc.Status richStatus = com.google.rpc.Status.newBuilder()
    .setCode(Status.Code.ALREADY_EXISTS.value())
    .setMessage("registration already exists")
    .addDetails(Any.pack(errorInfo))
    .build();
~~~

Clients can handle the stable `reason` without parsing messages. `domain` helps disambiguate error namespaces. Metadata should only hold non-sensitive values published in the contract; never stuff tokens, full email addresses, or private data there if clients do not need them.

Do not generate `reason` values arbitrarily from exception class names or messages. Maintain a controlled list of reasons, documenting the corresponding status codes and allowed client actions.

## 9. RetryInfo and Retry Contracts

For errors retryable after a wait interval, the server can attach `google.rpc.RetryInfo`. Clients must combine retry delay with overall deadlines, attempt limits, and idempotency:

~~~java
import com.google.protobuf.Any;
import com.google.protobuf.Duration;
import com.google.rpc.RetryInfo;

RetryInfo retryInfo = RetryInfo.newBuilder()
    .setRetryDelay(Duration.newBuilder()
        .setSeconds(2)
        .build())
    .build();

com.google.rpc.Status richStatus = com.google.rpc.Status.newBuilder()
    .setCode(io.grpc.Status.Code.RESOURCE_EXHAUSTED.value())
    .setMessage("request rate limit exceeded")
    .addDetails(Any.pack(retryInfo))
    .build();
~~~

The detail is only a contract-level hint; the client must still check whether the status is retryable and whether the operation is safe to repeat. Never retry `INVALID_ARGUMENT`, `UNAUTHENTICATED`, or `PERMISSION_DENIED` merely because a detail is present. For commands with side effects, keep the same idempotency key across attempts.

## 10. Size Limits and Security of Error Details

Rich details travel in trailers, so they also consume HTTP/2, proxy, and client metadata/trailer limits. Never send stack traces, entire request objects, unbounded error lists, or file contents in details.

Principles:

- Send only fields needed for the client to fix the request or select an action.
- Cap the number of field violations and length of messages/metadata.
- Never put secrets, access tokens, internal hostnames, SQL, or stack traces into details.
- Never use details to leak resources or tenants the caller is unauthorized to know about.
- Ensure gateways/proxies preserve `grpc-status-details-bin`; if stripped, basic status codes must still suffice for fallback.
- Log internal details on the server with a correlation ID, without returning raw logs to the client.

## 11. Suggested Contract Test Matrix

| Case | Assertion |
| --- | --- |
| Invalid validation | `INVALID_ARGUMENT` + `BadRequest` with field violations |
| Resource already exists | `ALREADY_EXISTS` + `ErrorInfo` with stable reason |
| Quota exceeded | `RESOURCE_EXHAUSTED` + `QuotaFailure` or `RetryInfo` per contract |
| Dependency unavailable | `UNAVAILABLE`; details if any do not alter semantics |
| Client does not understand detail type | Ignores unknown detail, still handles status code |
| Proxy strips rich trailer | Client falls back to basic status code/message |
| Detail contains sensitive data | Test rejects forbidden fields/metadata |
| New detail added | Older client still handles coarse error |

Contract tests should verify the type URL/type class, required fields, and code meanings; avoid comparing entire message strings since messages are often refined for readability.

## 12. Takeaways and Self-Check

**Error detail contracts** define how servers express structured errors using `google.rpc.Status` and `Any`, while the gRPC status code remains the stable fallback. In Java, the server builds rich statuses via `StatusProto.toStatusRuntimeException`, and clients read them via `StatusProto.fromThrowable`, unpacking only detail types they understand. Contract tests must verify status semantics, detail schemas, tolerance for unknown new types, trailers across proxies, and limits on sensitive data and size.

Self-Check:

1. How do rich error details differ from basic status codes/messages?
2. Why must the client check the `Any` type before unpacking?
3. If an older client encounters a new detail type, what should compatible behavior be?
4. Why should the message string not be used as a logic key?
5. Does `RetryInfo` automatically authorize retrying every RPC?
6. What must be verified if a proxy strips rich error trailers?

Clear error detail contracts help Spring gRPC clients handle errors consistently, provide controlled guidance for fixes/retries, and preserve compatibility as the server evolves its API.
