# Validating Protobuf Requests at the Boundary

**Chapter:** Spring service adapter  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and servers/clients for unary or streaming RPCs. This lesson focuses on validating requests right at the service adapter boundary: determining which protobuf data is valid according to the API contract, returning structured errors, and preventing invalid requests from reaching the application use case.

## 1. What Problem Does Boundary Validation Solve?

A generated request is a Java message created by the gRPC runtime after decoding the protobuf payload. That object has explicit types and getters, but that **does not prove the request content is valid under API business rules**.

For example, a transfer creation request may decode successfully yet still contain:

- An empty account ID.
- A zero or negative amount.
- A malformed currency code.
- An empty or overly long list of transfer lines.
- Two fields with an invalid relationship.
- A numeric enum value that this server version does not recognize.

If the adapter passes that request directly into the application service, inner layers have to defend themselves against bad input data. This scatters validation and can cause side effects before the error is detected.

Boundary validation places a clear gate:

```text
HTTP/2 + protobuf bytes
          |
          v
    gRPC protobuf parser
          |
          v
   Generated request object
          |
          v
  Spring gRPC service adapter
          |
          +--> Validate request structure and constraints
          |          |
          |          +--> Invalid: INVALID_ARGUMENT
          |
          v
   Map to application command
          |
          v
   Application use case
          |
          v
   Map result to protobuf response
```

The goal is to reject non-conforming requests early, return consistent errors, and invoke the use case only after the request passes validation.

## 2. Distinguishing Protobuf Parsing from Semantic Validation

These two steps happen at two different layers:

| Layer | Check | Failure examples |
| --- | --- | --- |
| Protobuf parsing | Whether the wire format can decode into a message per schema | Wrong tag/wire type, truncated payload, incomplete length-delimited field |
| Boundary validation | Whether decoded values satisfy the API's request rules | Empty ID, negative amount, missing required field, invalid field combination |
| Domain/application | Whether the operation is valid given current system state | Locked account, insufficient balance, already shipped order |

The service method only receives the generated request after the gRPC runtime has successfully parsed the payload. Parse errors typically occur before the handler is invoked; how the transport turns marshalling errors into a specific status depends on the runtime and configuration. Do not rely on the parser to perform business validation.

Boundary validation should focus on what can be decided solely from the request and the API contract. For example, "amount must be greater than 0" is boundary validation; "whether the account has enough balance" depends on system state and belongs to domain/application.

## 3. Designing Protobuf So Validation Can Distinguish Presence

Contract example:

```proto
syntax = "proto3";

import "google/protobuf/timestamp.proto";

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
  repeated TransferTag tags = 5;
  oneof schedule {
    google.protobuf.Timestamp execute_at = 6;
    bool execute_immediately = 7;
  }
}

message TransferTag {
  string key = 1;
  string value = 2;
}

message CreateTransferResponse {
  string transfer_id = 1;
}
```

With regular proto3 scalars, getters return the default value if the field is absent. If you need to distinguish "not sent" from "sent with value 0", use `optional`:

```java
if (!request.hasAmountMinorUnits()) {
    // Field is missing.
} else if (request.getAmountMinorUnits() <= 0) {
    // Field is present, but the value is invalid.
}
```

Message fields have their own presence; `oneof` provides a case enum; repeated fields can be empty and require element count checks. Choose a schema that expresses what the API needs to know, because the validator cannot recover presence information that the schema discarded.

## 4. Rule Categories to Check at the Boundary

A validator typically checks the following categories:

| Category | Example | Check |
| --- | --- | --- |
| Required/presence | `amount_minor_units` | `hasAmountMinorUnits()` |
| String format | Account ID, currency | Non-empty, length, regex or dedicated parser |
| Numeric range | Amount, quantity | Min/max per contract |
| Collection | Repeated tags | Min/max element count, duplicate keys |
| Nested message | Each transfer tag | Check child fields and produce specific paths |
| Cross-field | Source and destination | Two IDs must not be equal |
| oneof | Execution schedule | Must have a valid branch if required by API |
| Enum | Transaction type | Reject `UNRECOGNIZED` or unsupported values |
| Payload size | Strings, bytes, message count | Contract limits and transport limits |

Validation must have bounded cost. Do not iterate over a huge collection or run complex regexes before applying appropriate size limits. Transport message limits and business element-count limits are two complementary layers of protection.

## 5. Producing Per-Field Validation Results

Instead of throwing an exception on the first error, the validator can collect multiple violations so the client can fix them in one pass. Each violation contains:

- A field path using protobuf field names, e.g., `source_account_id` or `tags[2].key`.
- A short, stable, safe description.
- Optionally a reason code if clients need to handle errors by type.

Result model example:

```java
public record FieldViolation(
        String field,
        String description) {}
```

The validator does not depend on gRPC status. It only returns the issues found in the request:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class TransferRequestValidator {

    private static final int MAX_TAGS = 20;
    private static final long MAX_AMOUNT = 10_000_000_000L;

    public List<FieldViolation> validate(
            CreateTransferRequest request) {
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
        Set<String> keys = new HashSet<>();
        for (int index = 0; index < request.getTagsCount()
                && index < MAX_TAGS; index++) {
            TransferTag tag = request.getTags(index);
            if (tag.getKey().isBlank()) {
                violations.add(new FieldViolation(
                        "tags[" + index + "].key", "must not be blank"));
            } else if (!keys.add(tag.getKey())) {
                violations.add(new FieldViolation(
                        "tags[" + index + "].key", "must be unique"));
            }
        }

        if (request.getScheduleCase()
                == CreateTransferRequest.ScheduleCase.SCHEDULE_NOT_SET) {
            violations.add(new FieldViolation(
                    "schedule", "a schedule option is required"));
        }

        return List.copyOf(violations);
    }
}
```

The validator inspects at most `MAX_TAGS` elements after recording the limit-exceeded error. For much larger requests, apply a server message-size limit and collection limits at the boundary to avoid wasting CPU/memory.

The currency regex in the example only checks the three-uppercase-letter shape; it does not prove the currency code is supported by the system. Checking the supported currency catalog may belong to an application policy or domain service depending on the contract.

## 6. Converting Validation Violations into INVALID_ARGUMENT

The gRPC status `INVALID_ARGUMENT` is appropriate when a request fails presence, format, range, or structural checks. To let clients display errors per field without parsing descriptions, you can use the standard `google.rpc.BadRequest` rich error detail.

Factory example:

```java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import io.grpc.Status;
import io.grpc.protobuf.StatusProto;
import java.util.List;

@Component
public class ValidationStatusFactory {

    public RuntimeException invalidArgument(
            List<FieldViolation> violations) {
        BadRequest.Builder details = BadRequest.newBuilder();
        for (FieldViolation violation : violations) {
            details.addFieldViolations(
                    BadRequest.FieldViolation.newBuilder()
                            .setField(violation.field())
                            .setDescription(violation.description()));
        }

        com.google.rpc.Status richStatus =
                com.google.rpc.Status.newBuilder()
                        .setCode(Status.Code.INVALID_ARGUMENT.value())
                        .setMessage("Request validation failed")
                        .addDetails(Any.pack(details.build()))
                        .build();

        return StatusProto.toStatusRuntimeException(richStatus);
    }
}
```

`google.rpc.BadRequest` is a structured error detail. The client can unpack the detail and show errors on the exact fields. The project needs the corresponding dependencies for Google API common protos and `grpc-protobuf`. If rich details are not used, you can still return `Status.INVALID_ARGUMENT.withDescription("Invalid request").asRuntimeException()`; the client then receives only a general error category.

Do not include sensitive field values in `description`. For instance, never return raw account IDs, tokens, emails, or payloads. Metadata and error details both reach the client, so they must obey the same security principles as status descriptions.

## 7. Running the Validator Before the Application Use Case

The generated service base adapter receives the request, calls the validator, and maps to a command only when there are no violations:

```java
@GrpcService
public class TransferGrpcService
        extends TransferServiceGrpc.TransferServiceImplBase {

    private final TransferRequestValidator validator;
    private final ValidationStatusFactory statusFactory;
    private final CreateTransferUseCase useCase;
    private final TransferRequestMapper requestMapper;
    private final TransferResponseMapper responseMapper;
    private final GrpcExceptionMapper exceptionMapper;

    public TransferGrpcService(
            TransferRequestValidator validator,
            ValidationStatusFactory statusFactory,
            CreateTransferUseCase useCase,
            TransferRequestMapper requestMapper,
            TransferResponseMapper responseMapper,
            GrpcExceptionMapper exceptionMapper) {
        this.validator = validator;
        this.statusFactory = statusFactory;
        this.useCase = useCase;
        this.requestMapper = requestMapper;
        this.responseMapper = responseMapper;
        this.exceptionMapper = exceptionMapper;
    }

    @Override
    public void createTransfer(
            CreateTransferRequest request,
            StreamObserver<CreateTransferResponse> responseObserver) {

        List<FieldViolation> violations = validator.validate(request);
        if (!violations.isEmpty()) {
            responseObserver.onError(
                    statusFactory.invalidArgument(violations));
            return;
        }

        try {
            CreateTransferCommand command =
                    requestMapper.toCommand(request);
            TransferResult result = useCase.execute(command);
            responseObserver.onNext(responseMapper.toProto(result));
            responseObserver.onCompleted();
        } catch (AccountNotFoundException missing) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Account not found")
                            .asRuntimeException());
        } catch (InsufficientBalanceException precondition) {
            responseObserver.onError(
                    Status.FAILED_PRECONDITION
                            .withDescription("Insufficient balance to execute")
                            .asRuntimeException());
        } catch (Exception failure) {
            responseObserver.onError(exceptionMapper.map(failure));
        }
    }
}
```

The example focuses on processing order. In a real application, unexpected errors must be logged on the server via a controlled exception mapper/interceptor; do not expose stack traces or internal messages to the client. Do not catch `Throwable` to mask serious JVM errors.

Running the validator before the use case ensures invalid requests do not start transactions, call downstream services, or trigger side effects. However, the domain must still protect its invariants because state can change between boundary validation and transaction execution.

## 8. Distinguishing Boundary Validation from Domain Errors

Do not turn every failure condition into `INVALID_ARGUMENT`:

| Situation | Typical appropriate status | Deciding layer |
| --- | --- | --- |
| Empty account ID | `INVALID_ARGUMENT` | Boundary |
| Negative amount | `INVALID_ARGUMENT` | Boundary |
| Tags list has duplicate keys | `INVALID_ARGUMENT` if contract forbids duplicates | Boundary |
| Valid account ID that does not exist | `NOT_FOUND` | Application/domain |
| Account is locked | `FAILED_PRECONDITION` | Domain |
| Caller lacks permission to transfer | `PERMISSION_DENIED` | Security/authorization |
| Optimistic locking conflict | `ABORTED` | Persistence/application |
| Dependency temporarily unavailable | `UNAVAILABLE` | Dependency adapter |
| Granted quota exceeded | `RESOURCE_EXHAUSTED` | Policy/capacity |

Practical rule: if looking at the request alone lets you conclude it violates the contract, that is usually boundary validation. If it requires reading current state, checking permissions, or coordinating transactions, the error belongs to the corresponding layer.

## 9. Bean Validation and Protobuf Validation Libraries

Do not assume generated protobuf messages automatically carry Jakarta Bean Validation annotations or that Spring MVC `@Valid` will run automatically on gRPC methods. A gRPC service base does not pass through the MVC controller pipeline.

There are three implementation approaches:

1. **Manual validator:** suitable for small, clear rules; easy to test and independent of code generation plugins.
2. **Protobuf-integrated validation library:** lets you declare constraints in the schema or a separate rule set and validate generated messages in an adapter/interceptor. Verify plugins, runtime dependencies, and version compatibility.
3. **Bean Validation on internal commands:** map the request to an annotated DTO/command and call `Validator.validate()`; this is useful if the application already has validation rules on DTOs.

Whichever approach you choose, you still must define where it runs and how violations map to a gRPC status. Do not let a validation framework decide the status via a default exception without explicit adapter mapping.

## 10. Validation in Streaming RPCs

For client-streaming or bidirectional streaming, the request is not just a single message. Distinguish between:

- **Per-message validation:** each message has properly formatted fields, values within range, and valid size.
- **Stream-level validation:** total message count, sequence order, uniqueness, checksum, or completion criteria.
- **Domain validation:** resource state and permissions when applying the full batch.

Example where each message is validated upon arrival:

```java
return new StreamObserver<UploadLine>() {
    private final AtomicBoolean terminated = new AtomicBoolean(false);
    private int received;

    @Override
    public void onNext(UploadLine line) {
        if (terminated.get()) {
            return;
        }
        List<FieldViolation> violations = lineValidator.validate(line);
        if (!violations.isEmpty()) {
            if (terminated.compareAndSet(false, true)) {
                batch.discard();
                responseObserver.onError(
                        statusFactory.invalidArgument(violations));
            }
            return;
        }
        received++;
        batch.accept(line);
    }

    @Override
    public void onError(Throwable error) {
        terminated.set(true);
        batch.discard();
    }

    @Override
    public void onCompleted() {
        if (!terminated.compareAndSet(false, true)) {
            return;
        }
        try {
            batchValidator.validateComplete(batch, received);
            UploadResult result = uploadUseCase.finish(batch);
            responseObserver.onNext(toProto(result));
            responseObserver.onCompleted();
        } catch (RequestValidationException invalid) {
            responseObserver.onError(
                    statusFactory.invalidArgument(
                            List.of(new FieldViolation(
                                    "items", "stream is incomplete"))));
        } catch (Exception failure) {
            responseObserver.onError(exceptionMapper.map(failure));
        }
    }
};
```

This is an illustrative skeleton; the dependencies `lineValidator`, `batch`, `batchValidator`, and mappers belong to the application. Production code must limit message count and batch size, handle cleanup when the client cancels, and ensure observer callbacks are invoked sequentially. Do not buffer an unbounded stream in memory just to wait for final validation.

If individual messages are valid but the overall stream violates a manifest or is missing elements, the error may be `FAILED_PRECONDITION` depending on the contract; not every stream-level error is a field error on a single request.

## 11. Testing Boundary Validation

Tests should separate the validator, status factory, and adapter:

| Test level | Content |
| --- | --- |
| Validator unit test | Presence, range, format, nested path, repeated limit, duplicate, and cross-field |
| Status factory unit test | Code is `INVALID_ARGUMENT`, `BadRequest` detail contains the exact field violations |
| Adapter test | Invalid request does not call use case; valid request calls use case exactly once |
| In-process gRPC test | Client receives the expected status and can unpack rich error details |
| Streaming test | Invalid message terminates stream exactly once; no success response after terminal error |

Validator unit test example:

```java
class TransferRequestValidatorTest {

    private final TransferRequestValidator validator =
            new TransferRequestValidator();

    @Test
    void reportsMissingAmountAndInvalidAccountIds() {
        CreateTransferRequest request =
                CreateTransferRequest.newBuilder()
                        .setCurrency("USD")
                        .build();

        List<FieldViolation> violations = validator.validate(request);

        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("source_account_id")));
        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("destination_account_id")));
        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("amount_minor_units")));
    }

    @Test
    void rejectsSameSourceAndDestination() {
        CreateTransferRequest request =
                CreateTransferRequest.newBuilder()
                        .setSourceAccountId("account-A")
                        .setDestinationAccountId("account-A")
                        .setAmountMinorUnits(500)
                        .setCurrency("USD")
                        .setExecuteImmediately(true)
                        .build();

        List<FieldViolation> violations = validator.validate(request);

        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("destination_account_id")));
    }
}
```

For adapter tests, mock the use case and assert `verifyNoInteractions(useCase)` when the request is invalid. For in-process tests, call the generated blocking stub and check `Status.fromThrowable(error).getCode()`; if using rich details, unpack `google.rpc.BadRequest` and inspect the field paths.

## 12. Security, Compatibility, and Performance

- Do not echo raw sensitive field values into error descriptions.
- Limit string lengths, repeated element counts, and message sizes.
- Do not log entire protobuf requests when validation fails; payloads may contain PII or credentials.
- Do not reject all unknown protobuf fields by default; unknown fields support forward compatibility across differing client/server versions.
- For unknown enum values, handle `UNRECOGNIZED` explicitly if the field affects semantics.
- Keep field paths and error codes stable so clients can handle errors without parsing prose.
- Measure validation time if requests contain large nested collections; avoid validators with uncontrolled complexity.

## 13. Self-Practice

1. Why does successful protobuf parsing not imply the request is valid under the API contract?
2. When must a proto3 scalar be declared `optional` so a validator can distinguish a missing field from a default value?
3. Design field violations for a request with a negative amount and a third element in `tags` having a duplicate key.
4. Why is a well-formatted but non-existent account ID usually not `INVALID_ARGUMENT`?
5. Write an adapter test proving the use case is not called when the validator returns at least one violation.
6. For client streaming, distinguish per-message errors from overall errors when the stream completes.

**Key takeaway:** Validate protobuf requests at the boundary after the gRPC runtime creates the generated message and before calling the application use case. Check presence, format, range, collections, nested fields, and cross-field relationships; return `INVALID_ARGUMENT` with structured field violations when appropriate. Keep resource state, authorization, concurrency, and dependency errors at their proper layers; bound sizes, protect data, and test both the validator and the gRPC adapter.
