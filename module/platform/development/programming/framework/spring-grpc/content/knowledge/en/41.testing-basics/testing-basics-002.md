# Unit testing validation and status mapping

**Chapter:** Testing basics  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs. This lesson focuses on unit testing two responsibilities at the service boundary: validating generated requests and mapping exceptions to gRPC statuses. Tests must prove that invalid requests are rejected predictably, status codes/details conform to the contract, existing gRPC statuses are preserved, and internal errors are not leaked to clients.

## 1. Why test validation and status mapping separately?

A protobuf request can parse successfully yet still be invalid according to the API. For example, the amount is missing, the currency is malformed, or two account IDs are identical. The service adapter must validate the request before calling the use case.

When validation fails, the adapter must turn the violations into a consistent gRPC outcome, usually `INVALID_ARGUMENT`. When the use case throws an error, the exception mapper must choose an appropriate status such as `NOT_FOUND`, `FAILED_PRECONDITION`, `PERMISSION_DENIED`, or `UNAVAILABLE`. Unexpected errors must be mapped to `INTERNAL` with a safe description.

Without testing the two components separately:

- The validator might miss field presence or accept bad data.
- The exception mapper might mistakenly turn a domain error into `INTERNAL`.
- An existing `StatusRuntimeException` carrying trailers might be overwritten and lose metadata.
- Clients might receive stack traces, SQL, tokens, or internal exception messages.
- Changing description wording might accidentally break clients if clients parse text instead of reading status/details.

Unit tests for the validator and mapper lock down these rules without starting a Spring context or gRPC server.

## 2. Separating responsibilities before writing tests

| Component | Responsibility | Should not do |
| --- | --- | --- |
| Request validator | Check presence, format, range, collections, and field relationships | Query the database or decide account state |
| Application/domain | Enforce invariants and current state | Depend on gRPC generated exceptions |
| Exception mapper | Convert typed exceptions into gRPC status/details | Return arbitrary exception messages to clients |
| Service adapter | Call validator, map request, invoke use case, and complete the RPC | Repeat status mapping logic in every method |

Boundary validation returns a structured list of violations. The exception mapper accepts typed exceptions and decides the status. Separating these two responsibilities helps tests pinpoint whether a failure lies in validation or status mapping.

## 3. Example protobuf request

Suppose a service creates a payment order:

~~~proto
syntax = "proto3";

package payments.v1;
option java_package = "com.example.payments.grpc";
option java_multiple_files = true;

service PaymentService {
  rpc CreatePayment(CreatePaymentRequest)
      returns (CreatePaymentResponse);
}

message CreatePaymentRequest {
  string source_account_id = 1;
  string destination_account_id = 2;
  optional int64 amount_minor_units = 3;
  string currency = 4;
  repeated string tags = 5;
}

message CreatePaymentResponse {
  string payment_id = 1;
}
~~~

The `amount_minor_units` field is `optional`, so the generated request has `hasAmountMinorUnits()`. The validator can distinguish a missing field from a sent field with value 0. Messages are constructed with generated builders so tests exercise real protobuf semantics.

## 4. Representing validation violations

A violation should indicate the field path and a short description. Do not include sensitive request values in the error:

~~~java
public record FieldViolation(
        String field,
        String description) {}
~~~

Exception holding an immutable list of violations:

~~~java
import java.util.List;

public final class RequestValidationException
        extends RuntimeException {

    private final List<FieldViolation> violations;

    public RequestValidationException(
            List<FieldViolation> violations) {
        super("Request validation failed");
        this.violations = List.copyOf(violations);
    }

    public List<FieldViolation> violations() {
        return violations;
    }
}
~~~

Using `List.copyOf()` prevents callers from mutating the list after the exception is created. The exception message is generic; field-specific details are kept in `violations`.

## 5. Writing the request validator

The validator checks conditions that can be determined solely from the request:

~~~java
import com.example.payments.grpc.CreatePaymentRequest;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class PaymentRequestValidator {

    private static final long MAX_AMOUNT = 10_000_000_000L;
    private static final int MAX_TAGS = 10;

    public List<FieldViolation> validate(
            CreatePaymentRequest request) {
        List<FieldViolation> violations = new ArrayList<>();

        if (request.getSourceAccountId().isBlank()) {
            violations.add(new FieldViolation(
                    "source_account_id", "must not be blank"));
        }
        if (request.getDestinationAccountId().isBlank()) {
            violations.add(new FieldViolation(
                    "destination_account_id", "must not be blank"));
        }
        if (!request.getSourceAccountId().isBlank()
                && request.getSourceAccountId().equals(
                        request.getDestinationAccountId())) {
            violations.add(new FieldViolation(
                    "destination_account_id",
                    "must differ from source_account_id"));
        }

        if (!request.hasAmountMinorUnits()) {
            violations.add(new FieldViolation(
                    "amount_minor_units", "is required"));
        } else if (request.getAmountMinorUnits() <= 0) {
            violations.add(new FieldViolation(
                    "amount_minor_units", "must be greater than zero"));
        } else if (request.getAmountMinorUnits() > MAX_AMOUNT) {
            violations.add(new FieldViolation(
                    "amount_minor_units", "exceeds the API limit"));
        }

        if (!request.getCurrency().matches("[A-Z]{3}")) {
            violations.add(new FieldViolation(
                    "currency", "must be a three-letter uppercase code"));
        }
        if (request.getTagsCount() > MAX_TAGS) {
            violations.add(new FieldViolation(
                    "tags", "contains too many elements"));
        }

        return List.copyOf(violations);
    }
}
~~~

The validator does not check whether the account exists or has sufficient balance; those conditions require system state and belong to the application/domain layer. The validator must also perform no side effects.

## 6. Unit tests for the request validator

Tests use real generated requests. One test checks a valid request, while another checks multiple violations at once:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.payments.grpc.CreatePaymentRequest;
import java.util.List;
import org.junit.jupiter.api.Test;

class PaymentRequestValidatorTest {

    private final PaymentRequestValidator validator =
            new PaymentRequestValidator();

    @Test
    void acceptsValidRequest() {
        CreatePaymentRequest request =
                CreatePaymentRequest.newBuilder()
                        .setSourceAccountId("account-A")
                        .setDestinationAccountId("account-B")
                        .setAmountMinorUnits(25_000)
                        .setCurrency("USD")
                        .addTags("invoice")
                        .build();

        assertTrue(validator.validate(request).isEmpty());
    }

    @Test
    void reportsMissingAndInvalidFields() {
        CreatePaymentRequest request =
                CreatePaymentRequest.newBuilder()
                        .setSourceAccountId("account-A")
                        .setDestinationAccountId("account-A")
                        .setAmountMinorUnits(-1)
                        .setCurrency("usd")
                        .build();

        List<FieldViolation> violations = validator.validate(request);

        assertEquals(3, violations.size());
        assertEquals(
                List.of(
                        "destination_account_id",
                        "amount_minor_units",
                        "currency"),
                violations.stream().map(FieldViolation::field).toList());
    }

    @Test
    void distinguishesAbsentAmountFromZeroAmount() {
        CreatePaymentRequest absent =
                CreatePaymentRequest.newBuilder()
                        .setSourceAccountId("account-A")
                        .setDestinationAccountId("account-B")
                        .setCurrency("USD")
                        .build();
        CreatePaymentRequest zero =
                absent.toBuilder()
                        .setAmountMinorUnits(0)
                        .build();

        List<FieldViolation> absentErrors = validator.validate(absent);
        List<FieldViolation> zeroErrors = validator.validate(zero);

        assertEquals(
                "is required",
                violationFor(absentErrors, "amount_minor_units")
                        .description());
        assertEquals(
                "must be greater than zero",
                violationFor(zeroErrors, "amount_minor_units")
                        .description());
    }

    private FieldViolation violationFor(
            List<FieldViolation> violations,
            String field) {
        return violations.stream()
                .filter(violation -> violation.field().equals(field))
                .findFirst()
                .orElseThrow();
    }
}
~~~

The `reportsMissingAndInvalidFields` test also verifies that violation ordering stays stable according to the order in which the validator adds errors. Ordering is not necessarily part of the gRPC contract, but deterministic output makes tests easier to read and avoids flakiness.

Add cases for amounts exceeding the limit and too many tags. There is no need to test every numeric value; focus on boundaries: missing, below min, at min, at max, and above max.

## 7. Converting violations to INVALID_ARGUMENT

When clients need to display field-level errors, you can use standard `google.rpc.BadRequest` rich error details. The mapper creates a detail containing multiple `FieldViolation` entries:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.protobuf.StatusProto;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class ValidationStatusFactory {

    public StatusRuntimeException invalidArgument(
            List<FieldViolation> violations) {
        BadRequest.Builder badRequest = BadRequest.newBuilder();
        for (FieldViolation violation : violations) {
            badRequest.addFieldViolations(
                    BadRequest.FieldViolation.newBuilder()
                            .setField(violation.field())
                            .setDescription(violation.description()));
        }

        com.google.rpc.Status richStatus =
                com.google.rpc.Status.newBuilder()
                        .setCode(Status.Code.INVALID_ARGUMENT.value())
                        .setMessage("Request validation failed")
                        .addDetails(Any.pack(badRequest.build()))
                        .build();

        return StatusProto.toStatusRuntimeException(richStatus);
    }
}
~~~

Clients read the status code to classify the error and unpack `google.rpc.BadRequest` to identify which fields are invalid. Clients do not need to parse a free-form description sentence. The project needs compatible dependencies for `grpc-protobuf` and Google API common protos.

If rich details are not used, you can return `Status.INVALID_ARGUMENT.withDescription("Request validation failed").asRuntimeException()`; in that case, clients only receive a generic error. Either way, the description must be stable and free of sensitive data.

## 8. Unit tests for validation status mapping

Tests verify both the gRPC status and the rich detail:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.rpc.BadRequest;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.protobuf.StatusProto;
import java.util.List;
import org.junit.jupiter.api.Test;

class ValidationStatusFactoryTest {

    private final ValidationStatusFactory factory =
            new ValidationStatusFactory();

    @Test
    void mapsViolationsToInvalidArgumentAndBadRequestDetails()
            throws Exception {
        StatusRuntimeException error = factory.invalidArgument(
                List.of(
                        new FieldViolation(
                                "amount_minor_units",
                                "must be greater than zero"),
                        new FieldViolation(
                                "currency",
                                "must be a three-letter uppercase code")));

        assertEquals(
                Status.Code.INVALID_ARGUMENT,
                Status.fromThrowable(error).getCode());

        com.google.rpc.Status richStatus =
                StatusProto.fromThrowable(error);
        assertNotNull(richStatus);
        assertEquals(
                Status.Code.INVALID_ARGUMENT.value(),
                richStatus.getCode());

        BadRequest details =
                richStatus.getDetails(0).unpack(BadRequest.class);
        assertEquals(2, details.getFieldViolationsCount());
        assertEquals(
                "amount_minor_units",
                details.getFieldViolations(0).getField());
        assertEquals(
                "currency",
                details.getFieldViolations(1).getField());
    }
}
~~~

This test catches common bugs where the status code is right but details are missing, field paths are wrong, or only the first violation is returned. If clients rely on `BadRequest`, test the detail structure rather than checking only the description.

## 9. Designing the exception mapper

The exception mapper translates application errors into gRPC statuses. Rules should be based on typed exceptions:

| Exception | gRPC status | Reason |
| --- | --- | --- |
| `RequestValidationException` | `INVALID_ARGUMENT` | Request violates the contract |
| `AccountNotFoundException` | `NOT_FOUND` | Resource does not exist |
| `InsufficientFundsException` | `FAILED_PRECONDITION` | Current state does not allow the operation |
| `AuthorizationDeniedException` | `PERMISSION_DENIED` | Caller lacks permission |
| `DependencyUnavailableException` | `UNAVAILABLE` | Dependency is temporarily unavailable |
| Unexpected error | `INTERNAL` | Server error whose details must not be exposed |
| Existing `StatusRuntimeException` | Preserve status/trailers | Error is already represented in gRPC |

Do not map every `IllegalArgumentException` to `INVALID_ARGUMENT` if that exception could originate from an internal bug. Use a dedicated typed validation exception to avoid turning programming errors into client errors.

## 10. Example exception mapper

The following example preserves existing gRPC statuses, even when the exception is wrapped inside another exception:

~~~java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class GrpcExceptionMapper {

    private final ValidationStatusFactory validationStatusFactory;

    public GrpcExceptionMapper(
            ValidationStatusFactory validationStatusFactory) {
        this.validationStatusFactory = validationStatusFactory;
    }

    public StatusRuntimeException map(Throwable failure) {
        Throwable grpcFailure = findGrpcFailure(failure);
        if (grpcFailure instanceof StatusRuntimeException runtime) {
            return runtime;
        }
        if (grpcFailure instanceof StatusException checked) {
            Metadata trailers = Status.trailersFromThrowable(checked);
            return Status.fromThrowable(checked)
                    .asRuntimeException(trailers);
        }

        if (failure instanceof RequestValidationException invalid) {
            return validationStatusFactory.invalidArgument(
                    invalid.violations());
        }
        if (failure instanceof AccountNotFoundException) {
            return Status.NOT_FOUND
                    .withDescription("Account not found")
                    .asRuntimeException();
        }
        if (failure instanceof InsufficientFundsException) {
            return Status.FAILED_PRECONDITION
                    .withDescription("Insufficient funds")
                    .asRuntimeException();
        }
        if (failure instanceof AuthorizationDeniedException) {
            return Status.PERMISSION_DENIED
                    .withDescription("Operation is not permitted")
                    .asRuntimeException();
        }
        if (failure instanceof DependencyUnavailableException) {
            return Status.UNAVAILABLE
                    .withDescription("A required dependency is unavailable")
                    .asRuntimeException();
        }

        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }

    private Throwable findGrpcFailure(Throwable failure) {
        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());
        Throwable current = failure;
        while (current != null && visited.add(current)) {
            if (current instanceof StatusRuntimeException
                    || current instanceof StatusException) {
                return current;
            }
            current = current.getCause();
        }
        return null;
    }
}
~~~

The illustrative code assumes domain exceptions are separate classes and the mapper is Spring-managed. Using an identity set guards against unusual cycles in the cause chain. If a gRPC exception already exists, the mapper preserves it or reconstructs the status with its trailers; it never turns an `UNAVAILABLE` with retry metadata into `INTERNAL`.

Never return `failure.getMessage()` to the client in the default branch. Internal exceptions can contain SQL, table names, connection strings, tokens, or user data. Diagnostic details should be logged on the server via logging/interceptors with redaction and a correlation ID.

## 11. Unit tests for exception-to-status mapping

Test each exception group to lock down its status code and public description:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.List;
import org.junit.jupiter.api.Test;

class GrpcExceptionMapperTest {

    private final GrpcExceptionMapper mapper =
            new GrpcExceptionMapper(new ValidationStatusFactory());

    @Test
    void mapsDomainExceptionsToExpectedStatuses() {
        assertEquals(
                Status.Code.NOT_FOUND,
                Status.fromThrowable(
                        mapper.map(new AccountNotFoundException()))
                        .getCode());
        assertEquals(
                Status.Code.FAILED_PRECONDITION,
                Status.fromThrowable(
                        mapper.map(new InsufficientFundsException()))
                        .getCode());
        assertEquals(
                Status.Code.PERMISSION_DENIED,
                Status.fromThrowable(
                        mapper.map(new AuthorizationDeniedException()))
                        .getCode());
        assertEquals(
                Status.Code.UNAVAILABLE,
                Status.fromThrowable(
                        mapper.map(new DependencyUnavailableException()))
                        .getCode());
    }

    @Test
    void mapsValidationExceptionToInvalidArgument() {
        StatusRuntimeException mapped = mapper.map(
                new RequestValidationException(
                        List.of(new FieldViolation(
                                "amount_minor_units",
                                "must be greater than zero"))));

        assertEquals(
                Status.Code.INVALID_ARGUMENT,
                Status.fromThrowable(mapped).getCode());
    }

    @Test
    void mapsUnexpectedFailureToSafeInternalStatus() {
        StatusRuntimeException mapped = mapper.map(
                new IllegalStateException("database password=secret"));

        Status status = Status.fromThrowable(mapped);
        assertEquals(Status.Code.INTERNAL, status.getCode());
        assertEquals("Internal server error", status.getDescription());
        assertFalse(status.getDescription().contains("secret"));
    }
}
~~~

The domain exceptions in the example are dedicated application classes. Tests do not need to mock a gRPC server because they verify pure mapper logic. If the mapper has a logger, log redaction can be verified in a separate test; status mapping unit tests should not depend on an external logging system.

## 12. Preserving existing statuses and trailers

A downstream gRPC client may throw a `StatusRuntimeException` with trailers, such as a support reference or retry metadata. The exception mapper must not lose them:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CompletionException;
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;

class GrpcExceptionMapperPreservationTest {

    private static final Metadata.Key<String> SUPPORT_REFERENCE =
            Metadata.Key.of(
                    "support-reference",
                    Metadata.ASCII_STRING_MARSHALLER);

    private final GrpcExceptionMapper mapper =
            new GrpcExceptionMapper(new ValidationStatusFactory());

    @Test
    void preservesExistingGrpcStatusAndTrailers() {
        Metadata trailers = new Metadata();
        trailers.put(SUPPORT_REFERENCE, "ref-42");
        StatusRuntimeException original = Status.UNAVAILABLE
                .withDescription("upstream unavailable")
                .asRuntimeException(trailers);

        StatusRuntimeException mapped = mapper.map(original);

        assertSame(original, mapped);
        assertEquals(
                Status.Code.UNAVAILABLE,
                Status.fromThrowable(mapped).getCode());
        assertEquals(
                "ref-42",
                Status.trailersFromThrowable(mapped)
                        .get(SUPPORT_REFERENCE));
    }

    @Test
    void preservesGrpcStatusWrappedByAnotherException() {
        StatusRuntimeException original = Status.DEADLINE_EXCEEDED
                .withDescription("downstream deadline")
                .asRuntimeException();

        StatusRuntimeException mapped =
                mapper.map(new CompletionException(original));

        assertEquals(
                Status.Code.DEADLINE_EXCEEDED,
                Status.fromThrowable(mapped).getCode());
    }

    @Test
    void preservesCheckedGrpcStatusAndTrailers() {
        Metadata trailers = new Metadata();
        trailers.put(SUPPORT_REFERENCE, "checked-ref-7");
        StatusException original = Status.UNAUTHENTICATED
                .withDescription("credentials are invalid")
                .asException(trailers);

        StatusRuntimeException mapped = mapper.map(original);

        assertEquals(
                Status.Code.UNAUTHENTICATED,
                Status.fromThrowable(mapped).getCode());
        assertEquals(
                "checked-ref-7",
                Status.trailersFromThrowable(mapped)
                        .get(SUPPORT_REFERENCE));
    }
}
~~~

If the mapper supports checked `StatusException`, test that branch too and verify that trailers remain intact. Preservation tests are critical when an adapter wraps downstream errors or translates exceptions across layers.

## 13. Adapter must validate before invoking the use case

The adapter receives the generated request, retrieves the list of violations, and terminates the RPC with an error before calling the application use case. Only when the request is valid does the adapter forward processing:

~~~java
import io.grpc.stub.StreamObserver;
import java.util.List;

public class PaymentGrpcService
        extends PaymentServiceGrpc.PaymentServiceImplBase {

    private final PaymentRequestValidator validator;
    private final GrpcExceptionMapper exceptionMapper;
    private final CreatePaymentUseCase useCase;

    public PaymentGrpcService(
            PaymentRequestValidator validator,
            GrpcExceptionMapper exceptionMapper,
            CreatePaymentUseCase useCase) {
        this.validator = validator;
        this.exceptionMapper = exceptionMapper;
        this.useCase = useCase;
    }

    @Override
    public void createPayment(
            CreatePaymentRequest request,
            StreamObserver<CreatePaymentResponse> responseObserver) {
        List<FieldViolation> violations = validator.validate(request);
        if (!violations.isEmpty()) {
            responseObserver.onError(exceptionMapper.map(
                    new RequestValidationException(violations)));
            return;
        }
        try {
            String paymentId = useCase.create(request);
            responseObserver.onNext(
                    CreatePaymentResponse.newBuilder()
                            .setPaymentId(paymentId)
                            .build());
            responseObserver.onCompleted();
        } catch (Exception failure) {
            responseObserver.onError(exceptionMapper.map(failure));
        }
    }
}
~~~

This snippet is a simplified example; in real applications, a valid request is usually mapped to an application command before calling the use case. The point to test here is ordering: when validation fails, the use case is not called and only a single terminal error is emitted.

## 14. Testing that the adapter does not invoke the use case on invalid requests

The validator and status mapper might be individually correct yet the adapter could still call the use case before checking the request. An adapter unit test using Mockito can verify the order:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.*;

import com.example.payments.grpc.CreatePaymentRequest;
import com.example.payments.grpc.CreatePaymentResponse;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PaymentGrpcServiceTest {

    @Mock
    private CreatePaymentUseCase useCase;

    @Mock
    private StreamObserver<CreatePaymentResponse> responseObserver;

    private PaymentGrpcService service;

    @BeforeEach
    void setUp() {
        PaymentRequestValidator validator =
                new PaymentRequestValidator();
        GrpcExceptionMapper exceptionMapper =
                new GrpcExceptionMapper(new ValidationStatusFactory());
        service = new PaymentGrpcService(
                validator, exceptionMapper, useCase);
    }

    @Test
    void invalidRequestDoesNotInvokeUseCase() {
        CreatePaymentRequest request =
                CreatePaymentRequest.newBuilder()
                        .setSourceAccountId("")
                        .setDestinationAccountId("account-B")
                        .setAmountMinorUnits(-1)
                        .setCurrency("usd")
                        .build();

        service.createPayment(request, responseObserver);

        verifyNoInteractions(useCase);
        verify(responseObserver, times(1)).onError(argThat(error ->
                Status.fromThrowable(error).getCode()
                        == Status.Code.INVALID_ARGUMENT));
        verify(responseObserver, never()).onNext(any());
        verify(responseObserver, never()).onCompleted();
    }
}
~~~

This illustrative example emphasizes that invalid requests must terminate with a single terminal error and must not produce a successful response. When using Mockito, verify only interactions meaningful to the contract.

## 15. Status mapping test matrix

| Input | Expected status | Additional assertions |
| --- | --- | --- |
| Request validation violations | `INVALID_ARGUMENT` | `BadRequest` contains field paths |
| Account does not exist | `NOT_FOUND` | Generic description |
| Insufficient balance | `FAILED_PRECONDITION` | Does not leak internal balance |
| Insufficient permissions | `PERMISSION_DENIED` | Does not leak policy/credentials |
| Dependency temporarily failing | `UNAVAILABLE` | Preserves trailers if gRPC error already exists |
| Downstream deadline | `DEADLINE_EXCEEDED` | Not converted into `INTERNAL` |
| Unexpected exception | `INTERNAL` | Description does not contain exception message |
| Existing StatusException | Preserve code | Preserves trailers |
| Wrapped StatusRuntimeException | Preserve code | Finds the gRPC cause |

Do not test by comparing the entire exception message generated by the gRPC runtime. Assert the status code, public description, and typed details. If the description is not part of the client contract, only verify that it does not leak sensitive data.

## 16. Common anti-patterns

- **Only testing that an exception is thrown:** does not prove the status code or rich details are correct.
- **Mapping every RuntimeException to INVALID_ARGUMENT:** hides server bugs and misclassifies errors.
- **Mapping every error to INTERNAL:** clients cannot distinguish request, domain, and dependency failures.
- **Using exception messages as status descriptions:** can leak internal information.
- **Ignoring trailers:** loses support references or retry metadata from downstream.
- **Not testing unknown/wrapped gRPC exceptions:** errors that already have a status may get turned into INTERNAL.
- **Starting the Spring context for pure mappers:** makes tests slow and hard to isolate.
- **Relying on unstable collection ordering:** causes flaky assertions.
- **Calling the use case before validation:** invalid requests can still trigger side effects.

## 17. Self-practice

1. Why should a request validator return field violations instead of calling `responseObserver.onError()` directly?
2. Write a unit test distinguishing a missing amount from an amount equal to 0.
3. When should you use `INVALID_ARGUMENT` versus `FAILED_PRECONDITION`?
4. Why must the exception mapper preserve trailers from a downstream `StatusRuntimeException`?
5. Design a test proving that an unexpected exception does not leak SQL or tokens in the status description.
6. How do you verify that an adapter does not call the use case when the validator returns violations?

**Remember:** Validation unit tests must verify field violations, presence, and data boundaries; status mapping unit tests must verify accurate gRPC codes, rich details, preservation of statuses/trailers, and safe descriptions. Keep the validator, exception mapper, and service adapter as separate responsibilities, use clearly typed exceptions, and prevent invalid requests from causing side effects.
