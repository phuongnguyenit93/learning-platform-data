# Testing INVALID_ARGUMENT from Invalid Requests

A gRPC service needs to validate requests right at the API boundary before calling a repository or downstream service. When input data violates the method contract, the server should return the **INVALID_ARGUMENT** status with a stable description sufficient to help the caller fix the request. This lesson uses CreatePayment in Spring gRPC to demonstrate how to validate Protobuf requests and test the status using a generated blocking stub.

INVALID_ARGUMENT indicates that a request is invalid regardless of the current state of the system. It differs from business precondition errors that depend on resource state, such as FAILED_PRECONDITION, and differs from conflict errors that require the caller to retry a transaction, such as ABORTED. Tests should verify both the returned status and that the server rejects the request before producing any side effects.

## 1. Define the Request Contract to Validate

Suppose the service receives a request to create a payment:

~~~proto
syntax = "proto3";

package acme.payment.v1;

option java_multiple_files = true;
option java_package = "com.acme.payment.v1";

service PaymentService {
  rpc CreatePayment(CreatePaymentRequest)
      returns (CreatePaymentResponse);
}

message CreatePaymentRequest {
  string customer_id = 1;
  int64 amount_minor = 2;
  string currency = 3;
}

message CreatePaymentResponse {
  string payment_id = 1;
}
~~~

With proto3, unset scalar fields typically receive their default values. For example, customer_id and currency can be empty strings; amount_minor can be 0. Therefore, the server must validate the input business rules rather than assuming fields are always present.

| Field | Example Rule | Invalid Request |
| --- | --- | --- |
| customer_id | Must not be empty or whitespace-only | Empty string or whitespace-only |
| amount_minor | Must be greater than 0; unit is the smallest currency unit | 0 or negative number |
| currency | Must belong to the list of currencies supported by the service | Empty or unsupported code |

These rules represent the API contract for the example. In a real system, the currency list and amount limits must come from a clearly versioned business policy.

## 2. Validate Before Performing Side Effects

Placing validation at the service boundary ensures every gRPC caller receives the same handling, regardless of which Spring application the request comes from. Do not call the repository first and only discover later that the request is invalid.

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.Set;

public final class PaymentGrpcService
        extends PaymentServiceGrpc.PaymentServiceImplBase {

    private static final Set<String> SUPPORTED_CURRENCIES =
        Set.of("USD", "EUR");

    private final PaymentRepository repository;

    public PaymentGrpcService(PaymentRepository repository) {
        this.repository = repository;
    }

    @Override
    public void createPayment(
            CreatePaymentRequest request,
            StreamObserver<CreatePaymentResponse> responseObserver) {

        String invalidReason = validate(request);
        if (invalidReason != null) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription(invalidReason)
                    .asRuntimeException());
            return;
        }

        CreatePaymentResponse response = repository.create(request);
        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }

    private String validate(CreatePaymentRequest request) {
        if (request.getCustomerId().isBlank()) {
            return "customer_id must not be blank";
        }
        if (request.getAmountMinor() <= 0) {
            return "amount_minor must be greater than zero";
        }
        if (!SUPPORTED_CURRENCIES.contains(request.getCurrency())) {
            return "currency is not supported";
        }
        return null;
    }
}
~~~

PaymentRepository is the storage-layer abstraction, for example:

~~~java
public interface PaymentRepository {
    CreatePaymentResponse create(CreatePaymentRequest request);
}
~~~

When validation fails, the server sends onError exactly once and exits the handler. Do not call onNext or onCompleted after onError. Do not include raw requests, secrets, or database details in the status description; the description should be stable and safe for callers to display or log.

## 3. Choose the Right gRPC Status for the Error Type

Do not use INVALID_ARGUMENT for every failure case:

| Status | Use When | Example |
| --- | --- | --- |
| INVALID_ARGUMENT | Request value is invalid independently of system state | Negative amount, malformed or unsupported currency |
| FAILED_PRECONDITION | System is not in the required state to execute the request | Account is locked, verification step not completed |
| OUT_OF_RANGE | Value is type-valid but exceeds the contract's allowed range | Requested page exceeds the published maximum limit |
| NOT_FOUND | Referenced resource does not exist | Customer ID is validly formatted but not found |
| ABORTED | Operation was aborted due to a conflict; caller may need to retry the transaction | Optimistic locking conflict |
| UNAVAILABLE | Service is temporarily unable to serve requests | Downstream or server temporarily disconnected |

The boundary between INVALID_ARGUMENT and OUT_OF_RANGE depends on the API contract. The key is to keep semantics consistent: callers should not retry an invalid request, and instead must fix the data first.

## 4. Test Using an In-Process gRPC Server

In-process transport allows running the real service inside the JVM without opening a TCP port. It is well-suited for testing validation logic, status mapping, and ensuring the repository is not called when a request is invalid.

JUnit 5 example using a generated blocking stub:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PaymentGrpcServiceTest {

    private Server server;
    private ManagedChannel channel;
    private PaymentServiceGrpc.PaymentServiceBlockingStub stub;
    private AtomicInteger repositoryCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        repositoryCalls = new AtomicInteger();

        PaymentRepository repository = request -> {
            repositoryCalls.incrementAndGet();
            return CreatePaymentResponse.newBuilder()
                .setPaymentId("payment-123")
                .build();
        };

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new PaymentGrpcService(repository))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = PaymentServiceGrpc.newBlockingStub(channel)
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
    void blankCustomerIdReturnsInvalidArgument() {
        CreatePaymentRequest request = validRequest()
            .setCustomerId("   ")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.createPayment(request));

        assertEquals(
            Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
        assertEquals(
            "customer_id must not be blank",
            error.getStatus().getDescription());
        assertEquals(0, repositoryCalls.get());
    }

    @Test
    void nonPositiveAmountReturnsInvalidArgument() {
        CreatePaymentRequest request = validRequest()
            .setAmountMinor(0)
            .build();

        assertInvalidArgument(request);
        assertEquals(0, repositoryCalls.get());
    }

    @Test
    void unsupportedCurrencyReturnsInvalidArgument() {
        CreatePaymentRequest request = validRequest()
            .setCurrency("XYZ")
            .build();

        assertInvalidArgument(request);
        assertEquals(0, repositoryCalls.get());
    }

    @Test
    void validRequestCallsRepositoryAndReturnsResponse() {
        CreatePaymentResponse response =
            stub.createPayment(validRequest().build());

        assertEquals("payment-123", response.getPaymentId());
        assertEquals(1, repositoryCalls.get());
    }

    private void assertInvalidArgument(CreatePaymentRequest request) {
        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.createPayment(request));

        assertEquals(
            Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
        assertNotNull(error.getStatus().getDescription());
    }

    private CreatePaymentRequest.Builder validRequest() {
        return CreatePaymentRequest.newBuilder()
            .setCustomerId("customer-42")
            .setAmountMinor(2500)
            .setCurrency("USD");
    }
}
~~~

The test uses directExecutor() because the validation handler is short and non-blocking. If the service performs I/O or waits on a latch, use an appropriate executor so it does not block the test thread or dispatch thread. grpc-inprocess must match the version of the remaining gRPC Java artifacts.

## 5. Verify Status, Description, and Side Effects

A good test should verify three things:

1. **Status code:** the client receives the exact INVALID_ARGUMENT code.
2. **Public description:** the message is clear enough to fix the request without leaking internals.
3. **No side effects:** the repository, payment gateway, or downstream service is not called.

Simply checking that an exception was thrown is not enough. If the service already persisted data before returning the error, the API could leave state inconsistent. A counter or mock verification helps prove that validation occurs before business operations.

With a blocking stub, errors are thrown as StatusRuntimeException. With an async stub, errors pass through StreamObserver.onError; you can retrieve the status via Status.fromThrowable(error). In both cases, assert Status.Code.INVALID_ARGUMENT rather than only comparing message strings.

## 6. Test Boundary Cases and Protobuf Defaults

Beyond a typical invalid request, test values near boundaries:

| Case | Expected Result |
| --- | --- |
| customer_id is not set | INVALID_ARGUMENT because the proto3 value is an empty string |
| customer_id contains only whitespace | INVALID_ARGUMENT |
| amount_minor = 0 | INVALID_ARGUMENT |
| amount_minor < 0 | INVALID_ARGUMENT |
| amount_minor = 1 | Valid if allowed by policy |
| currency is empty or unsupported | INVALID_ARGUMENT |
| All fields valid | Repository is called exactly once |

If the schema uses optional, wrappers, or oneof to distinguish between unset and sending a default value, tests must also check presence semantics. Do not check only the getter, because a proto3 scalar getter returns the default value even when the field is absent.

## 7. Do Not Retry INVALID_ARGUMENT Requests

INVALID_ARGUMENT is a request error; resending the same payload will not make the error disappear. The client should display or return the validation error to the caller, allowing them to fix the input and create a new request.

Automatic retry policies should not list INVALID_ARGUMENT in retryableStatusCodes. If there is a shared retry layer in the application, exclude this status from the retry list. Uncontrolled retries only increase load and mask client data errors.

Distinguish this error from UNAVAILABLE, which can be retried according to policy if the operation is safe and sufficient deadline remains. For commands with side effects, retrying errors with unknown outcomes still requires an idempotency key.

## 8. Test Through the Spring Application Context

In-process tests verify the service implementation and status mapping, but do not prove that the Spring starter has properly registered the service, interceptors, or server configuration. You should add integration tests that boot the application context and call the gRPC endpoint over a real transport or test port:

- Verify PaymentGrpcService is registered under the correct service name.
- Verify interceptors do not transform validation errors into another status.
- Verify metadata/trailers are preserved properly.
- Verify TLS or proxy layers if production uses them.
- Verify invalid requests do not touch the real repository bean.

In Spring Boot, you can use SpringBootTest alongside the test server configuration of the starter in use. The property name for selecting the port or how the channel is obtained depends on the starter/version; use your project's actual integration point rather than assuming a single property common to every Spring gRPC library.

## 9. Secure Error Information

The status description is data sent back to the client and may be logged across multiple layers. Do not include in the description:

- SQL statements, table names, or connection strings.
- Stack traces or internal class names.
- Tokens, secrets, payment data, or personal data.
- Full request contents when they might contain sensitive information.

You can use a stable message like amount_minor must be greater than zero, while logging internally with a request ID and standardized error code. If the API needs multiple field errors in a single response, consider google.rpc.BadRequest in the rich error model and ensure clients/proxies support the corresponding trailers.

## 10. Recommended Test Matrix

| Category | Input/Scenario | Assertion |
| --- | --- | --- |
| Required field | Empty customer_id | INVALID_ARGUMENT; repository not called |
| Whitespace | ID with whitespace only | INVALID_ARGUMENT |
| Numeric boundary | Amount equal to 0 or negative | INVALID_ARGUMENT |
| Enum/domain | Unsupported currency | INVALID_ARGUMENT |
| Valid boundary | Minimum valid amount | Succeeds per contract |
| Side effect | Invalid request | No data written, no downstream call |
| Error mapping | Blocking/async client | Both observe the exact status code |
| Spring wiring | Real application context | Service/interceptor registered properly |
| Security | Invalid request containing sensitive data | Description does not leak data |

Keep tests independent and use fixtures/fake repositories. Do not depend on a real database to test a pure validation rule.

## 11. Takeaways and Self-Check

**Testing INVALID_ARGUMENT from invalid requests** requires verifying validation at the service boundary, the exact gRPC status, and the absence of side effects. Use generated request builders to construct invalid data, an in-process server to quickly test service logic, and add Spring integration tests to verify real wiring. INVALID_ARGUMENT requires the caller to fix the payload; do not retry the same request.

Self-check:

1. Why do unset string fields in proto3 typically need to be checked as empty strings?
2. When should you use INVALID_ARGUMENT instead of FAILED_PRECONDITION?
3. Why must tests verify that the repository is not called when a request is invalid?
4. How do blocking stubs and async stubs represent INVALID_ARGUMENT errors differently?
5. Why should this status not be included in a retry policy?
6. Which parts of a Spring gRPC deployment can an in-process test not verify?

Proper validation testing ensures Spring gRPC rejects invalid requests consistently, prevents partial data writes, and provides feedback clear enough for callers to fix their input.
