# Mapping Validation to INVALID_ARGUMENT

## 1. Meaning of INVALID_ARGUMENT

In **SPRING_GRPC**, clients send Protobuf requests to the server to perform queries or commands. A request can decode successfully yet still contain invalid data: empty identifiers, negative quantities, strings exceeding limits, unsupported enums, or conflicting fields.

The gRPC **INVALID_ARGUMENT** status indicates that the request contains invalid arguments according to the API contract. The client must fix the input data before resending. This status should not be used for every failure that causes an operation not to succeed.

Important distinctions:

- Invalid input independent of system state: typically INVALID_ARGUMENT.
- Resource exists, but current state does not allow the operation: typically FAILED_PRECONDITION.
- Resource does not exist: NOT_FOUND.
- Value outside the processable domain of an operation/range: may be OUT_OF_RANGE per contract.
- Concurrent update conflict: ABORTED.
- Database/service temporarily unavailable: UNAVAILABLE.

This lesson focuses on validating requests at the gRPC boundary and application service, representing structured violations, mapping exceptions to INVALID_ARGUMENT, distinguishing validation from business preconditions, and testing statuses over gRPC.

## 2. Validation layers in an RPC

Validation should be separated by responsibility rather than lumped into one block inside the adapter:

| Layer | What it checks | Examples |
| --- | --- | --- |
| Decode/protocol | Whether the payload parses per the Protobuf contract | Corrupt wire format, message fails to deserialize |
| Structural validation | Field presence, format, length/value range | Empty ID, negative amount, oversized page_size |
| Cross-field validation | Whether fields within the same request are consistent | start_time must precede end_time |
| Application validation | Input fits the use case/API contract | Disallowing too many items in a single request |
| Domain precondition | Whether current state permits the operation | Order is already SHIPPED so it cannot be CANCELED |

Structural and cross-field validation typically map to INVALID_ARGUMENT. Domain preconditions depending on current data typically map to FAILED_PRECONDITION. Decode errors may be handled by the gRPC runtime before the service method runs; do not assume every deserialization error passes through the application validator.

Layering tells the client whether to fix the request or wait for system state to change.

## 3. Validate early at the boundary, keep business rules in the application layer

The gRPC adapter is where Protobuf requests are converted into internal commands. It can quickly verify structural constraints before calling the application service:

```java
@Override
public void createOrder(
        CreateOrderRequest request,
        StreamObserver<CreateOrderReply> observer) {
    try {
        requestValidator.validate(request);

        CreateOrderResult result =
            orderApplicationService.create(
                toCommand(request)
            );

        observer.onNext(toReply(result));
        observer.onCompleted();
    } catch (RequestValidationException ex) {
        observer.onError(exceptionMapper.toStatus(ex));
    } catch (RuntimeException ex) {
        observer.onError(exceptionMapper.toStatus(ex));
    }
}
```

The adapter should not hold all business logic. The application service must still enforce invariants regardless of whether the use case is invoked from gRPC, REST, a batch job, or a message consumer.

For example, capping the maximum number of items in a single request is an API/application constraint; checking whether current inventory is sufficient is a business rule dependent on database state. The two kinds of errors may require different statuses.

## 4. Representing structured validation violations

Do not merely throw IllegalArgumentException with a generic string if the client needs to know which field is wrong. A violation can include:

- Field path: path to the field in the request, e.g., items[2].quantity.
- Rule/code: stable code such as REQUIRED, OUT_OF_RANGE, or INVALID_FORMAT.
- Safe, concise message for developers/clients.
- Must not contain secrets, tokens, personal data, or the entire payload.

Example internal model:

```java
public record FieldViolation(
    String field,
    String code,
    String description
) {}

public class RequestValidationException
        extends RuntimeException {
    private final List<FieldViolation> violations;

    public RequestValidationException(
            List<FieldViolation> violations) {
        super("Request validation failed");
        this.violations = List.copyOf(violations);
    }

    public List<FieldViolation> getViolations() {
        return violations;
    }
}
```

Error codes should be stable so clients can handle them programmatically; messages may change or be localized. Do not force clients to parse description strings to make logic decisions.

Cap the number of violations returned—for instance, return only up to a small initial limit. A request with thousands of invalid elements should not produce an enormous error response or spike server load.

## 5. Writing a validator for a Protobuf request

Example order creation request:

```proto
syntax = "proto3";

package commerce.orders.v1;

message OrderLineInput {
  string product_id = 1;
  int32 quantity = 2;
}

message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLineInput items = 2;
  string idempotency_key = 3;
}
```

The validator can check structure and database-independent limits:

```java
@Component
public class CreateOrderRequestValidator {

    public void validate(CreateOrderRequest request) {
        List<FieldViolation> errors = new ArrayList<>();

        if (request.getCustomerId().isBlank()) {
            errors.add(new FieldViolation(
                "customer_id", "REQUIRED",
                "customer_id is required"
            ));
        }

        if (request.getItemsCount() == 0) {
            errors.add(new FieldViolation(
                "items", "REQUIRED",
                "At least one item is required"
            ));
        }

        if (request.getItemsCount() > 100) {
            errors.add(new FieldViolation(
                "items", "TOO_MANY",
                "At most 100 items are allowed"
            ));
        }

        for (int i = 0; i < request.getItemsCount(); i++) {
            OrderLineInput item = request.getItems(i);

            if (item.getProductId().isBlank()) {
                errors.add(new FieldViolation(
                    "items[" + i + "].product_id",
                    "REQUIRED",
                    "product_id is required"
                ));
            }

            if (item.getQuantity() <= 0) {
                errors.add(new FieldViolation(
                    "items[" + i + "].quantity",
                    "OUT_OF_RANGE",
                    "quantity must be positive"
                ));
            }

            if (errors.size() >= 20) {
                break;
            }
        }

        if (!errors.isEmpty()) {
            throw new RequestValidationException(errors);
        }
    }
}
```

The validator does not query the database to check whether the product exists. That belongs in the application/domain service because it depends on current state. If the product does not exist, it may return NOT_FOUND; if the product exists but is discontinued, it may return FAILED_PRECONDITION per the contract.

## 6. Proto3 default values and field presence

Proto3 scalar fields typically have implicit presence: getters return a default value if the field was not sent. For int32, the getter returns 0; for bool, false; for string, the empty string.

This affects validation:

- If quantity must be greater than 0, checking quantity <= 0 is sufficient even without distinguishing absent from zero.
- If you need to distinguish an omitted field from an explicit 0, use optional, a suitable wrapper message, or oneof.
- For updates/patches, absent may mean "keep unchanged", whereas a default value may mean "set to 0/false/empty".
- For enums, value 0 should be *_UNSPECIFIED so the server knows the client did not select a specific value.

Explicit presence example:

```proto
message UpdateLimitRequest {
  string account_id = 1;
  optional int64 daily_limit = 2;
}
```

The server can check hasDailyLimit() before validating the value. Never infer an absent field solely from a getter returning 0.

For message fields and oneof, Protobuf provides structural presence; use these semantics consistently in both the validator and command mapping.

## 7. Format validation, normalization, and Unicode

String validation is more than checking length:

- Trim whitespace if the contract defines leading/trailing spaces as insignificant.
- Normalize Unicode when comparing identifiers or names in canonical representation.
- Specify limits clearly in bytes, code points, or visible characters.
- Validate formats using dedicated parsers when available, such as UUID or email parsers.
- Avoid overly complex regexes that can trigger catastrophic backtracking on large inputs.
- Do not silently mutate user data if normalization could alter meaning.

For identifiers, parse into a concrete domain type and use its canonical representation. For free-text fields, bound bytes/code points and enforce an explicit storage policy.

Validation does not replace escaping or parameterized SQL. Even after input is validated, always use prepared statements/repository parameter binding to prevent injection.

## 8. Cross-field validation and oneof

A request may contain individually valid fields that are invalid in combination.

Time range example:

```proto
message SearchRequest {
  google.protobuf.Timestamp from = 1;
  google.protobuf.Timestamp to = 2;
}
```

The rule from <= to is cross-field validation. The validator must verify both fields are present per contract, timestamps are valid, and their chronological order holds. If the time range is too wide due to API limits, return INVALID_ARGUMENT because the request itself exceeds the published limit.

With oneof, Protobuf guarantees at most one member is set in a parsed message. However, the validator still must check whether a required oneof has a member set and whether the selected member's contents are valid.

When there are multiple violations, return exact field paths so the client can fix the right places. Do not return just "request invalid" if the contract needs to support forms or batch clients.

## 9. Distinguishing INVALID_ARGUMENT from FAILED_PRECONDITION

This is the most critical boundary in error mapping:

| Situation | Commonly Used Status | Why |
| --- | --- | --- |
| Negative or zero amount | INVALID_ARGUMENT | Input is wrong regardless of system state |
| page_size exceeds API limit | INVALID_ARGUMENT | Argument is outside the contract |
| from_time is after to_time | INVALID_ARGUMENT | Fields in the request contradict each other |
| Order is SHIPPED so cannot cancel | FAILED_PRECONDITION | Depends on current resource state |
| Account is locked so cannot debit | FAILED_PRECONDITION | Current business condition disallows it |
| Valid Product ID that does not exist | NOT_FOUND | Referenced resource is absent |
| Stale version due to concurrent update | ABORTED | Concurrency conflict |
| Database temporarily unreachable | UNAVAILABLE | Infrastructure failure |

A helpful question: "If database state changed while the request stayed identical, could the request become valid?" If yes, the error is usually state-dependent and FAILED_PRECONDITION should be considered. If no, it usually belongs to INVALID_ARGUMENT.

Do not use INVALID_ARGUMENT to mask missing permissions; that case is normally PERMISSION_DENIED or a documented existence-hiding policy.

## 10. Mapping validation exceptions to INVALID_ARGUMENT

A centralized mapper helps all RPCs return consistent statuses:

```java
@Component
public class GrpcExceptionMapper {

    public StatusRuntimeException toStatus(Throwable error) {
        if (error instanceof RequestValidationException ex) {
            return Status.INVALID_ARGUMENT
                .withDescription("Request validation failed")
                .asRuntimeException();
        }

        if (error instanceof ResourceNotFoundException) {
            return Status.NOT_FOUND
                .withDescription("Resource not found")
                .asRuntimeException();
        }

        if (error instanceof BusinessPreconditionException) {
            return Status.FAILED_PRECONDITION
                .withDescription("Operation is not allowed")
                .asRuntimeException();
        }

        return Status.INTERNAL
            .withDescription("Unexpected server error")
            .asRuntimeException();
    }
}
```

In production, you can attach the list of field violations using a rich error model like google.rpc.BadRequest and StatusProto if the system already uses grpc-status-details. When doing so, keep error codes stable, cap violation counts, and omit sensitive input values from details.

Do not send stack traces, SQL, or internal exception messages. Server logs record the cause and correlation ID; the client receives enough information to correct the request.

## 11. Validate before database work

Structural validation should run before acquiring a connection or opening a transaction whenever possible:

1. Decode the request.
2. Validate field presence, format, length, and range.
3. Validate cross-field consistency.
4. Build the internal command.
5. Open a transaction and check domain state/database.
6. Commit and return the response.

This avoids wasted queries for invalid requests and reduces connection pool occupancy. However, database-dependent validation such as "does the customer exist" must live inside the use case/transaction and handle race conditions appropriately.

Do not rely on client-side validation. Clients may be outdated, buggy, or intentionally sending invalid payloads; the server must always revalidate.

## 12. Batch validation and resource limits

For RPCs receiving large lists, validation itself consumes CPU and memory:

- Enforce limits on item count and total payload size before deep traversal.
- Cap the number of violations returned.
- Fail early when a request exceeds severe structural limits.
- Avoid retaining a full normalized copy if items can be validated incrementally.
- For batch imports allowing partial results, the contract must specify which items are accepted and which are rejected.
- For atomic batches, validate everything before starting the write transaction.

If a request exceeds transport size limits or fails to parse, the error may occur before the application validator runs; configure message sizes and the gRPC runtime appropriately. Do not substitute INVALID_ARGUMENT for quota/rate limiting when the real cause is RESOURCE_EXHAUSTED.

## 13. Testing validation mapping

Test the validator, application service, and gRPC statuses:

| Test | What to verify |
| --- | --- |
| Empty required field | Validation violation has exact field path |
| Negative/zero quantity | INVALID_ARGUMENT |
| Page size over limit | INVALID_ARGUMENT |
| Invalid cross-field range | INVALID_ARGUMENT |
| Absent optional field | Presence semantics are correct |
| UNSPECIFIED/unknown enum | Not treated as a valid value |
| Nonexistent resource | NOT_FOUND, not INVALID_ARGUMENT |
| Existing resource in forbidden state | FAILED_PRECONDITION |
| Database outage | Not mapped to INVALID_ARGUMENT |
| Oversized batch | Rejected before database work |
| Error details | Contains no secrets or raw payload |

Example gRPC integration test:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> blockingStub.createOrder(
        CreateOrderRequest.newBuilder()
            .setCustomerId("")
            .build()
    )
);

assertEquals(
    Status.Code.INVALID_ARGUMENT,
    Status.fromThrowable(error).getCode()
);
```

In addition to the status code, verify error details/field paths if the contract provides them. Test through a real server to ensure the adapter or exception interceptor actually converts the exception into the right status.

## 14. Review checklist

- Structural, cross-field, and domain validations are cleanly layered.
- Requests are validated on the server; client validation is never trusted.
- Proto3 presence/default semantics are handled correctly.
- Identifiers, string lengths, numeric ranges, and enums are checked.
- Field paths and error codes are stable; violation counts are bounded.
- Application services enforce invariants even when called from other adapters.
- INVALID_ARGUMENT is used only for invalid input.
- FAILED_PRECONDITION is used when current state does not allow the operation.
- NOT_FOUND, PERMISSION_DENIED, ABORTED, OUT_OF_RANGE, and UNAVAILABLE are not conflated.
- Structural validation runs before database work whenever possible.
- Batches and payloads have resource limits.
- Error details do not leak sensitive or internal data.
- Unit and gRPC integration tests cover status mapping and easily confused cases.

In **SPRING_GRPC**, INVALID_ARGUMENT tells the client the request must be fixed before resending. Validate Protobuf request structure and consistency at the boundary, keep business invariants in the application layer, and map typed validation violations to statuses at the gRPC boundary. Distinguish invalid input from missing resources, business preconditions, permissions, and database failures so clients can take the right corrective action.
