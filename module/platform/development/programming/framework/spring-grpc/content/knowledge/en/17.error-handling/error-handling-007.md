# Validation errors and INVALID_ARGUMENT

**Chapter:** Error handling  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and unary or streaming RPCs. This lesson focuses on validating requests at the API boundary and returning the `INVALID_ARGUMENT` gRPC status when client-sent data fails to meet the contract.

## 1. When to use INVALID_ARGUMENT?

`INVALID_ARGUMENT` is appropriate when **the request itself is invalid**, regardless of the current system state. The client can fix the data and resend it.

Examples:

- Missing source or destination account ID.
- Amount less than or equal to 0.
- Source and destination accounts are the same.
- Malformed currency code.
- A required field is not provided.
- An element in a repeated request field fails formatting rules.

Not every failed operation is a validation error:

| Situation | Typical appropriate status | Reason |
| --- | --- | --- |
| `amount_minor_units = 0` | `INVALID_ARGUMENT` | Invalid request value |
| Empty `source_account_id` | `INVALID_ARGUMENT` | Missing input data |
| Syntactically valid account that does not exist | `NOT_FOUND` | Referenced resource does not exist |
| Account is locked so transfer cannot proceed | `FAILED_PRECONDITION` | Business state does not allow it |
| Caller lacks permission to access account | `PERMISSION_DENIED` | Authorization issue |
| Optimistic locking conflict | `ABORTED` | Concurrency conflict; may need to rerun transaction |
| Amount exceeds current account limit | Usually `FAILED_PRECONDITION` or `RESOURCE_EXHAUSTED` per contract | Data may be valid, but current conditions/limits do not allow it |

This distinction tells the client whether to fix the request, check the resource, change preconditions, or retry later.

## 2. Where should validation happen?

Validation has multiple layers; each layer is responsible for a class of errors:

1. **Protocol/transport:** gRPC and protobuf decode the wire format. Malformed wire messages can be rejected before the service is called.
2. **API validation:** checks required fields, format, length, numeric ranges, and cross-field consistency. This is where `INVALID_ARGUMENT` is usually produced.
3. **Domain validation:** checks business rules and current state. Errors here can be `FAILED_PRECONDITION`, `NOT_FOUND`, `ALREADY_EXISTS`, or another status.
4. **Authorization:** determines whether the caller has permission to perform the action; typically returns `PERMISSION_DENIED` or `UNAUTHENTICATED`.

Do not push every check into the domain model or rely entirely on the client. Client validation improves user experience, but the server must still validate because requests can come from older versions, other integrations, or untrusted clients.

## 3. Deliberate protobuf design for field presence

Example transfer creation API:

```proto
syntax = "proto3";

package payments.v1;
option java_package = "com.example.payments.grpc";
option java_multiple_files = true;

service TransferService {
  rpc CreateTransfer(CreateTransferRequest)
      returns (CreateTransferResponse);
}

message CreateTransferRequest {
  string source_account_id = 1;
  string destination_account_id = 2;
  optional int64 amount_minor_units = 3;
  string currency = 4;
  string idempotency_key = 5;
}

message CreateTransferResponse {
  string transfer_id = 1;
  string status = 2;
}
```

The `amount_minor_units` field uses `optional int64` so the generated Java message can distinguish:

- Client omitted the field: `hasAmountMinorUnits() == false`.
- Client sent the value 0: `hasAmountMinorUnits() == true`, `getAmountMinorUnits() == 0`.

With a proto3 scalar lacking presence, default values like 0 or an empty string cannot tell whether the client omitted the field or intentionally sent the default value. Use `optional`, `oneof`, or nested message design when that distinction matters to the contract.

Do not declare `required` fields in proto3. Express presence appropriately and validate on the server.

## 4. Collecting errors per field instead of reporting only the first error

For requests with multiple fields, returning a list of field violations lets the client fix multiple errors at once. A violation should include:

- The field name by protobuf path, e.g., `source_account_id`.
- A short, safe description, e.g., `must not be blank`.
- Optionally a stable reason/code if the contract requires fine-grained classification.

Do not include field values in the error description. For example, do not return `account_id=123456789 does not exist` if the ID could be sensitive; an "invalid field" error suffices for syntactic validation. Resource-not-found errors should be classified separately according to the API's security policy.

A simple validator:

```java
import java.util.ArrayList;
import java.util.List;

public record FieldViolation(String field, String description) {}

public class TransferRequestValidator {

    private static final long MAX_AMOUNT_MINOR_UNITS = 10_000_000_000L;

    public List<FieldViolation> validate(CreateTransferRequest request) {
        List<FieldViolation> errors = new ArrayList<>();

        if (request.getSourceAccountId().isBlank()) {
            errors.add(new FieldViolation(
                    "source_account_id", "must not be blank"));
        }
        if (request.getDestinationAccountId().isBlank()) {
            errors.add(new FieldViolation(
                    "destination_account_id", "must not be blank"));
        }
        if (request.getSourceAccountId().equals(
                request.getDestinationAccountId())
                && !request.getSourceAccountId().isBlank()) {
            errors.add(new FieldViolation(
                    "destination_account_id",
                    "must differ from source_account_id"));
        }

        if (!request.hasAmountMinorUnits()) {
            errors.add(new FieldViolation(
                    "amount_minor_units", "is required"));
        } else if (request.getAmountMinorUnits() <= 0) {
            errors.add(new FieldViolation(
                    "amount_minor_units", "must be greater than zero"));
        } else if (request.getAmountMinorUnits() > MAX_AMOUNT_MINOR_UNITS) {
            errors.add(new FieldViolation(
                    "amount_minor_units", "exceeds the API limit"));
        }

        if (!request.getCurrency().matches("[A-Z]{3}")) {
            errors.add(new FieldViolation(
                    "currency", "must be a three-letter uppercase code"));
        }
        if (request.getIdempotencyKey().isBlank()) {
            errors.add(new FieldViolation(
                    "idempotency_key", "must not be blank"));
        }

        return List.copyOf(errors);
    }
}
```

This is API-level validation: checking presence, format, and published technical limits. Whether the currency code is supported, whether the accounts exist, or whether the balance is sufficient must be checked in the application/domain layer, because those results depend on data and system state.

## 5. Returning INVALID_ARGUMENT with field violations

The gRPC status code indicates the error category. If you want the client to know exactly which fields are invalid, you can use the standard `google.rpc.BadRequest` error details instead of concatenating a list into the description.

With the corresponding protobuf dependencies for Google API common protos and gRPC protobuf, the server can pack `BadRequest` into `google.rpc.Status`:

```java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import io.grpc.Status;
import io.grpc.protobuf.StatusProto;
import java.util.List;

public class ValidationStatusFactory {

    public RuntimeException invalidArgument(
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
```

`google.rpc.BadRequest` is a structured error detail. Clients can unpack the detail and display per-field errors without parsing the description string. If the project does not yet use rich error details, it can return `Status.INVALID_ARGUMENT.withDescription("Invalid request").asRuntimeException()`; in that case, the client only knows the general error category.

Do not put the entire request, field values, or exception messages into `BadRequest.FieldViolation.description`. Details are still transmitted to the client and must follow the same security rules as status descriptions and trailers.

## 6. Calling the validator in the Spring gRPC adapter

The adapter validates the request before invoking business logic:

```java
@GrpcService
public class TransferGrpcService
        extends TransferServiceGrpc.TransferServiceImplBase {

    private final TransferRequestValidator validator;
    private final ValidationStatusFactory statusFactory;
    private final TransferApplicationService applicationService;

    public TransferGrpcService(
            TransferRequestValidator validator,
            ValidationStatusFactory statusFactory,
            TransferApplicationService applicationService) {
        this.validator = validator;
        this.statusFactory = statusFactory;
        this.applicationService = applicationService;
    }

    @Override
    public void createTransfer(
            CreateTransferRequest request,
            StreamObserver<CreateTransferResponse> responseObserver) {

        var violations = validator.validate(request);
        if (!violations.isEmpty()) {
            responseObserver.onError(
                    statusFactory.invalidArgument(violations));
            return;
        }

        try {
            var result = applicationService.create(request);
            responseObserver.onNext(toProto(result));
            responseObserver.onCompleted();
        } catch (AccountNotFoundException error) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Account not found")
                            .asRuntimeException());
        } catch (AccountStateException error) {
            responseObserver.onError(
                    Status.FAILED_PRECONDITION
                            .withDescription(
                                    "Account state does not allow this operation")
                            .asRuntimeException());
        }
    }
}
```

Validation runs before calling the application service, avoiding queries or data mutations for syntactically invalid requests. Domain errors are still mapped separately; do not turn a non-existent account into a validation error simply because the client passed that ID.

In a real application, include a safe fallback for unexpected errors and internal logging. Do not send stack traces or raw messages to the client. For known errors, call only one terminal callback: `onError` or the pair `onNext` + `onCompleted`.

## 7. Validation in streaming RPCs

With client streaming, each message can be validated upon receiving `onNext()`, while conditions involving the entire batch can only be determined once the full stream or manifest has been received:

- **Per-message validation:** required fields, format, per-message size, sequence.
- **Batch validation:** item count, total bytes, uniqueness, hash, or manifest.
- **Domain validation:** resource state, business quota, permissions, and consistency with existing data.

If a single message is invalid, the server can terminate early with `INVALID_ARGUMENT`. If all individual messages are valid but the batch is missing items compared to the manifest, the status can be `FAILED_PRECONDITION`: the precondition to complete the batch was not met, not that a request field was invalid.

Example handling branch:

```java
@Override
public void onNext(BatchItem item) {
    if (terminated) return;

    List<FieldViolation> violations = itemValidator.validate(item);
    if (!violations.isEmpty()) {
        terminated = true;
        responseObserver.onError(
                validationStatusFactory.invalidArgument(violations));
        return;
    }

    accumulator.accept(item);
}
```

After calling `responseObserver.onError()`, do not send a receipt or call `onCompleted()`. If async processing or cancellation can run on another thread, synchronize terminal state and make cleanup idempotent.

## 8. Client reading validation errors

If the server only returns a generic status, the client checks `INVALID_ARGUMENT`:

```java
try {
    blockingStub.createTransfer(request);
} catch (StatusRuntimeException error) {
    Status status = Status.fromThrowable(error);
    if (status.getCode() == Status.Code.INVALID_ARGUMENT) {
        showValidationFailure();
    } else {
        handleOtherRpcFailure(status.getCode());
    }
}
```

If the server returns rich error details, the client can read `google.rpc.BadRequest`:

```java
import com.google.rpc.BadRequest;
import io.grpc.StatusRuntimeException;
import io.grpc.protobuf.StatusProto;

void showFieldErrors(StatusRuntimeException error) {
    com.google.rpc.Status richStatus = StatusProto.fromThrowable(error);
    if (richStatus == null) {
        showGenericValidationError();
        return;
    }

    for (com.google.protobuf.Any detail : richStatus.getDetailsList()) {
        if (detail.is(BadRequest.class)) {
            try {
                BadRequest badRequest = detail.unpack(BadRequest.class);
                for (BadRequest.FieldViolation violation
                        : badRequest.getFieldViolationsList()) {
                    showFieldError(
                            violation.getField(),
                            violation.getDescription());
                }
            } catch (com.google.protobuf.InvalidProtocolBufferException ignored) {
                showGenericValidationError();
            }
        }
    }
}
```

The client must have a fallback when details are absent, unrecognized, or cannot be decoded. An older client may not know newer details; the status code must still be sufficient for general error handling.

## 9. Testing validation and statuses

Unit tests for the validator verify each rule without starting a server:

```java
class TransferRequestValidatorTest {

    private final TransferRequestValidator validator =
            new TransferRequestValidator();

    @Test
    void reportsMissingIdsAndAmount() {
        var request = CreateTransferRequest.newBuilder()
                .setCurrency("USD")
                .setIdempotencyKey("key-1")
                .build();

        var violations = validator.validate(request);

        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("source_account_id")));
        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("destination_account_id")));
        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("amount_minor_units")));
    }

    @Test
    void acceptsSyntacticallyValidRequest() {
        var request = CreateTransferRequest.newBuilder()
                .setSourceAccountId("account-A")
                .setDestinationAccountId("account-B")
                .setAmountMinorUnits(1250)
                .setCurrency("USD")
                .setIdempotencyKey("key-2")
                .build();

        assertTrue(validator.validate(request).isEmpty());
    }
}
```

Integration tests via in-process gRPC should verify:

| Case | Expected |
| --- | --- |
| Missing account ID | `INVALID_ARGUMENT`, with corresponding field violation |
| Zero or negative amount | `INVALID_ARGUMENT` |
| Malformed currency | `INVALID_ARGUMENT` |
| Syntactically valid request but account does not exist | `NOT_FOUND` |
| Account is locked | `FAILED_PRECONDITION` |
| Unexpected server error | Safe status; no exception message leaked |
| Older client unaware of rich details | Still handles general status code |

Testing statuses at the RPC boundary is important because validator unit tests do not prove the adapter called `responseObserver.onError()` properly or attached the right rich details.

## 10. Self-practice

1. A request has `amount_minor_units = 0`. Why is this `INVALID_ARGUMENT`, whereas a locked account is `FAILED_PRECONDITION`?
2. Why might using `optional int64` be more necessary than plain `int64` when validating required fields?
3. Design three field violations for a request with an empty source ID, negative amount, and malformed currency.
4. Client streaming receives valid individual messages, yet one item is missing compared to the manifest. Why might `FAILED_PRECONDITION` express this more accurately than `INVALID_ARGUMENT`?
5. Write an integration test verifying that the client receives `INVALID_ARGUMENT` and unpacks `google.rpc.BadRequest` without parsing the status description.

**Remember:** Use `INVALID_ARGUMENT` for requests failing presence, format, range, or input consistency checks. Validate at the API boundary before invoking business logic, return structured field violations when needed, and distinguish them from resource, domain state, permission, or concurrency errors. Clients can validate early for better UX, but the server is always the authoritative enforcement point.
