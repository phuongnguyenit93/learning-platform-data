# INVALID_ARGUMENT

In gRPC, **`INVALID_ARGUMENT` is status code `3`**, used when a request contains arguments that are invalid according to the method's contract. This error stems from the data or how the client invoked the method: malformed formats, values out of allowed bounds, conventionally required fields missing, or conflicting field combinations. If the client resends the exact same request without fixing the data, the call will usually continue to fail.

In **SPRING_GRPC**, the server receives a decoded Protobuf message before validating input rules in the handler or application layer. Protobuf defines data types and wire structure, but does not by itself express every business rule. Therefore, you need to determine where validation lives, which errors map to `INVALID_ARGUMENT`, how to return field details safely, and how the client should fix the request.

## 1. Meaning of INVALID_ARGUMENT

`INVALID_ARGUMENT` has the numeric value **3**. This status applies when one or more arguments provided by the client are invalid **regardless of the current state of the system**.

For example:

- `quantity` must be greater than 0, but the client sends 0 or a negative number.
- `email` does not match the format accepted by the contract.
- An identifier string is empty or syntactically malformed.
- A time range has `start_time` after `end_time`.
- A conflicting combination of fields, such as selecting payment type `CARD` without providing a card token as required by the contract.
- An enum value is unsupported by the API or outside the set of values allowed by the method.

| Perspective | Meaning |
| --- | --- |
| Client | The request needs to be corrected before resending |
| Server | Should not execute business logic with input that violates the contract |
| gRPC runtime | Terminates the RPC with status `INVALID_ARGUMENT` |
| Business | The request did not pass input validation; makes no claim about whether the system has or lacks a resource |

`INVALID_ARGUMENT` is neither a connectivity error nor an identity authentication error. It indicates that the method's input data is invalid.

## 2. Protobuf defines structure; the application defines many validation rules

Example stock check contract:

```protobuf
syntax = "proto3";

package commerce.inventory.v1;

message CheckStockRequest {
  string sku = 1;
  int32 quantity = 2;
}

message CheckStockReply {
  bool available = 1;
  int32 remaining = 2;
}

service InventoryService {
  rpc CheckStock(CheckStockRequest) returns (CheckStockReply);
}
```

The schema states that `sku` is a string and `quantity` is a 32-bit integer. However, the schema alone does not express that:

- `sku` must not be blank.
- `sku` must follow the system's identifier format.
- `quantity` must be greater than 0.
- A single request may only request up to a certain maximum quantity.

Those constraints belong to the application-level contract and must be checked explicitly.

### 2.1. Watch out for proto3 default values

For regular scalar fields in proto3, if the client omits a field, the server can receive the default value, such as an empty string or 0. Because of that, the server cannot always distinguish between "the client did not send the field" and "the client sent the default value".

If you need to distinguish those two cases, consider `optional`, `oneof`, or a wrapper type suited to your schema. For example:

```protobuf
message UpdateProfileRequest {
  string user_id = 1;
  optional string display_name = 2;
}
```

With field presence enabled, the server can check `hasDisplayName()` to distinguish omitting the field from providing an empty string. Whether you use presence or not, you still need to define clear semantics in the contract.

### 2.2. Do not confuse parse errors with validation errors

The Protobuf parser checks wire format and message decodability. If the byte stream is malformed, an error may occur before the handler ever receives the request. `INVALID_ARGUMENT` is typically used for messages that are structurally valid but contain values or field combinations that violate the method's rules.

In other words:

- **Parse/transport failure:** the data cannot be decoded or the transport stream failed.
- **Validation failure:** the server received the request message, but values inside the message violate input rules.

## 3. Distinguishing INVALID_ARGUMENT from easily confused statuses

Choosing the right status helps clients know whether to fix the request, check resource state, or verify permissions.

| Status | When it fits | Example |
| --- | --- | --- |
| `INVALID_ARGUMENT` | Arguments are invalid regardless of system state | `quantity = 0` in a method requiring a positive quantity |
| `FAILED_PRECONDITION` | System is not in the required state to execute the operation | Account is locked so withdrawal is not possible |
| `OUT_OF_RANGE` | Value is generally valid but outside the valid range for the current operation | Reading past the final offset of a finite dataset |
| `NOT_FOUND` | The requested resource does not exist | No product matches the valid SKU that was sent |
| `PERMISSION_DENIED` | The caller does not have permission to execute the operation | User is not allowed to view another user's order |
| `UNAUTHENTICATED` | The caller's identity cannot be verified | Token is missing or expired |
| `ALREADY_EXISTS` | Creating a resource that duplicates an existing one | Creating a user with an already-registered email |

### 3.1. INVALID_ARGUMENT and FAILED_PRECONDITION

This is an important distinction:

- `INVALID_ARGUMENT`: the request is wrong regardless of what state the system is in.
- `FAILED_PRECONDITION`: the request may be valid, but the current state of the system does not allow execution.

For example, `quantity = -2` is always wrong for an order placement operation, so use `INVALID_ARGUMENT`. Meanwhile, `quantity = 2` is valid, but if the warehouse is closed for stocktaking, you can use `FAILED_PRECONDITION` if the contract defines that state as blocking the operation.

### 3.2. INVALID_ARGUMENT and OUT_OF_RANGE

`OUT_OF_RANGE` fits when a value falls outside the allowed range for an operation, especially in APIs with range or cursor concepts. If a field has the wrong format or violates general input rules, `INVALID_ARGUMENT` is usually clearer. Choose according to the method's semantics, not merely based on a Java exception name.

### 3.3. INVALID_ARGUMENT and NOT_FOUND

A properly formatted SKU that does not exist can be `NOT_FOUND`. A SKU containing forbidden characters or an invalid structure is `INVALID_ARGUMENT`. Whether "not found" is an error or a normal outcome also depends on the method's contract.

## 4. Where should validation happen in Spring gRPC?

A processing flow typically has these boundaries:

```text
gRPC runtime
    |
    v
Parsed Protobuf request
    |
    v
gRPC handler / adapter
    |  Validate structure and API rules
    v
Spring application service
    |  Validate invariants and business rules
    v
Repository / database
```

Validation can be divided into three groups:

| Group | Example | Appropriate place |
| --- | --- | --- |
| API structural rules | Contract-required fields, length, format, positive quantity | Handler/adapter or dedicated request validator |
| Business domain rules | Total quantity within order limits, valid relationships across fields | Spring application/domain service |
| Durable data constraints | Unique constraints, foreign keys, record state under concurrent updates | Database and application service; translate errors to appropriate statuses |

Client-side validation provides early feedback and improves UX, but **the server must still validate again**. Clients may be outdated, buggy, or intentionally sending invalid data.

Do not put every rule into an interceptor. Interceptors fit cross-cutting logic such as authentication, metadata, tracing, or cross-method policies. Validation that depends on each method's schema and semantics should normally live in the corresponding adapter/validator or business layer.

## 5. Example of mapping validation to INVALID_ARGUMENT

A handler can validate the request before calling the business service:

```java
@Override
public void checkStock(
        CheckStockRequest request,
        StreamObserver<CheckStockReply> observer) {

    if (request.getSku().isBlank()) {
        observer.onError(Status.INVALID_ARGUMENT
            .withDescription("sku must not be blank")
            .asRuntimeException());
        return;
    }

    if (request.getQuantity() <= 0) {
        observer.onError(Status.INVALID_ARGUMENT
            .withDescription("quantity must be greater than 0")
            .asRuntimeException());
        return;
    }

    int remaining = inventoryQuery.remaining(request.getSku());
    CheckStockReply reply = CheckStockReply.newBuilder()
        .setAvailable(remaining >= request.getQuantity())
        .setRemaining(remaining)
        .build();

    observer.onNext(reply);
    observer.onCompleted();
}
```

This example assumes `inventoryQuery` is an injected Spring bean. When the request is invalid, the handler calls `onError(...)` and `return`; it does not proceed to call business logic or emit a response. When the request is valid, an outcome of `available = false` can still be returned with status `OK`.

In a large application, avoid repeating validation blocks across many handlers. You can create validators per request type or application command so rules stay consistent and easy to unit test.

### 5.1. Separating Protobuf requests from business commands

One way to organize this is to convert the Protobuf message into an internal command and then validate the command:

```java
public record CheckStockCommand(String sku, int quantity) {}

public CheckStockCommand toCommand(CheckStockRequest request) {
    return new CheckStockCommand(request.getSku(), request.getQuantity());
}
```

Then the application service can use Bean Validation or a domain validator. The example below illustrates the idea, not annotations to place directly on generated Protobuf classes:

```java
public record ReserveStockCommand(
    @NotBlank String sku,
    @Positive int quantity
) {}
```

If using Jakarta Bean Validation, the application invokes the validator or integrates validation at the application boundary, then translates constraint violations into status `INVALID_ARGUMENT`. Do not modify Java files generated from proto to add annotations, because code generation can overwrite them and generated messages have their own semantics.

## 6. Returning field error details to the client

A generic description such as "Invalid request" may not tell the client which field needs fixing. For systems that need to report multiple errors at once, you can use Google RPC's **richer error model**, such as `google.rpc.BadRequest` containing a list of `FieldViolation` entries.

Example of the logical content:

```text
grpc-status: INVALID_ARGUMENT
grpc-message: Invalid request

BadRequest:
  field_violations:
    - field: "sku"
      description: "must not be blank"
    - field: "quantity"
      description: "must be greater than 0"
```

This is an illustrative representation; sending error details in Java requires using the corresponding protobuf types/libraries and packing the details into the status per the API in use.

When returning validation details:

- Use contract field names, not database column names or internal class names.
- Do not echo back sensitive values sent by the client.
- Return multiple field errors in a single response when possible so the client can fix them together.
- Keep messages stable and machine-readable; do not rely on clients parsing free-form prose sentences.
- If the system supports localization, consider stable error codes and let the client render text in the target language.

For simple errors, `Status.INVALID_ARGUMENT.withDescription(...)` may be sufficient. Richer error details are only needed when clients genuinely require field-level feedback or machine-readable validation.

## 7. How should the client handle INVALID_ARGUMENT?

With a blocking stub, the client can catch `StatusRuntimeException`:

```java
try {
    CheckStockReply reply = inventoryStub.checkStock(request);
    // Process the business result.
} catch (StatusRuntimeException ex) {
    if (ex.getStatus().getCode() == Status.Code.INVALID_ARGUMENT) {
        // Display or log the input error; do not retry the same request.
    } else {
        // Handle other statuses according to policy.
    }
}
```

The client should:

1. Identify which method and request were rejected.
2. Read the status and error details if present.
3. Map errors to form fields or source data.
4. Fix the input before resending.
5. Avoid automatically retrying the exact unchanged request.

Do not display every `grpc-message` directly to end users. Messages may be written for developers or contain phrasing unsuitable for UI. Use the error codes/field violations defined in the contract and map them to appropriate messages.

### 7.1. INVALID_ARGUMENT should normally not be retried

Unlike `UNAVAILABLE`, `INVALID_ARGUMENT` is usually not a transient error. Retrying the same payload normally returns the same error and only increases load. Retrying only makes sense after the data is fixed or the client changes the request based on the validation feedback.

## 8. Cases where INVALID_ARGUMENT should not be used

| Scenario | More appropriate status or representation |
| --- | --- |
| Missing or invalid token | `UNAUTHENTICATED` |
| Valid identity but lacks permission | `PERMISSION_DENIED` |
| Well-formed SKU that does not exist | `NOT_FOUND` or response per contract |
| Account is locked so funds cannot be transferred | `FAILED_PRECONDITION` |
| Cursor has valid type but exceeds end of result set | Possibly `OUT_OF_RANGE` |
| Concurrent update conflict | `ABORTED` |
| Database temporarily unreachable | `UNAVAILABLE` if semantics match |
| Unexpected error in server | `INTERNAL` or another status based on cause |

In particular, do not use `INVALID_ARGUMENT` to mask authorization errors. A client lacking permission to view a resource is an identity/authorization issue, not invalid request data.

## 9. Testing INVALID_ARGUMENT

A test suite should cover both the API boundary and business boundary:

| Scenario | What to verify |
| --- | --- |
| Blank `sku` | Client receives `INVALID_ARGUMENT`; business service is not called |
| `quantity = 0` or negative | Correct status and appropriate description/field details |
| Malformed `sku` | Validator returns a stable error |
| Valid request but insufficient stock | Response `available = false`, status `OK` |
| Valid SKU that does not exist | Status/response per contract, not confused with invalid syntax |
| Missing token | `UNAUTHENTICATED`, not `INVALID_ARGUMENT` |
| Unauthorized user | `PERMISSION_DENIED` |
| Multiple invalid fields | Client receives complete field violations if supported by the contract |
| Generated code is regenerated | Validation continues to work after code generation without modifying generated source |

Unit testing validators allows fast verification of individual rules. Integration tests via a gRPC client/server verify that statuses and error details actually reach the client. With Spring, you can test the handler together with the application service in a test context or using an appropriate test server.

## 10. Observing validation errors

`INVALID_ARGUMENT` can reflect client bugs, outdated SDKs, unclear contracts, or traffic intentionally sending bad data. Monitor:

- Count and rate of `INVALID_ARGUMENT` by service/method.
- Which fields are commonly violated, if recordable without storing sensitive values.
- Client/SDK version or application class causing the errors.
- Changes in error rates after releasing a new contract or UI.
- Ratio of request validation failures to total RPCs.

Do not put `sku` values, emails, tokens, or request contents into metric labels. Use normalized field names and violation types; when investigating a specific request, use trace/correlation IDs and controlled logs.

A sudden spike in `INVALID_ARGUMENT` may indicate clients using an incompatible schema/SDK or misleading contract documentation. Do not automatically treat it as a server availability outage; accurate classification tells the responsible team whether to fix the client, the contract, or validation.

## 11. Validation design checklist for a gRPC method

Before publishing a method, determine:

1. **Which fields are required by business logic?** Distinguish from proto3 default values.
2. **What are the valid formats and value domains?** Specify length, ranges, patterns, and cross-field relationships.
3. **Which layer owns each validation?** API adapter, domain/application service, or database constraint.
4. **Which errors are truly INVALID_ARGUMENT?** Separate from not found, permission, and failed precondition.
5. **How much detail does the client need?** A single description or structured field violations?
6. **Is any sensitive data exposed?** Never echo back tokens or private payloads.
7. **How does the client fix errors?** Are there field mappings and stable error codes?
8. **Is retrying reasonable?** Never retry an unchanged request.
9. **Are there tests distinguishing nearby statuses?** Ensure errors are not grouped into the wrong code.

## 12. Takeaways

`INVALID_ARGUMENT` is gRPC status code `3`, used when request arguments are invalid under the method's contract. It fits malformed formats, conventionally missing fields, out-of-domain values, or conflicting field combinations. It differs from `FAILED_PRECONDITION` (system state does not permit the operation), `OUT_OF_RANGE` (exceeds operational bounds), `NOT_FOUND` (resource missing), and authentication/authorization statuses.

In Spring gRPC, Protobuf defines message structure; handlers/validators and application services perform validation; the gRPC runtime returns the status to the client. Return clear yet safe field errors, keep generated sources untouched, and test statuses across a real client/server. Clients should fix the request rather than retrying the same payload. Well-designed validation makes APIs easier to integrate, reduces repeated errors, and protects downstream business layers.

### References

- [gRPC – Status codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC – Error handling](https://grpc.io/docs/guides/error/)
- [Protocol Buffers – Proto3 language guide](https://protobuf.dev/programming-guides/proto3/)
- [Google API – Error model](https://cloud.google.com/apis/design/errors)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
