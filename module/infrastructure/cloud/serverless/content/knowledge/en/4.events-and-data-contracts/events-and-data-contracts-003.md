# Designing JSON Schemas and Input Data Validation Rules

In serverless systems, data entering a function from an HTTP request, queue, or event source is typically produced by another component. The sender and receiver may be deployed, scaled, or updated independently. Therefore, both sides must agree on a **data contract**: what structure the data has, which fields are required, which values are valid, and how to handle contract violations.

JSON is a common interchange format, yet a payload that parses as valid JSON is not necessarily valid for the business domain. For example, an empty string is still a valid JSON value; an order with a quantity of 0 may be syntactically valid JSON while violating business rules. Schema design and validation rules help catch these cases right at the system boundary.

This lesson focuses on three tasks: describing structure with JSON Schema, validating data in Java, and applying the same contract across HTTP, messages, and events.

## 1. What Is a Data Contract?

A data contract is an agreement between the data producer and the data consumer. At a minimum, the contract must describe:

- **Structure:** which fields an object contains, the data type of each field, and nested relationships.
- **Requiredness:** which fields must be present, and which may be omitted or take a null value.
- **Value domain:** string lengths, numeric ranges, allowed value sets, date-time formats, and array item counts.
- **Semantics:** what each field represents, the units of measure, and the timezone used to interpret timestamps.
- **Evolution rules:** how sender and receiver stay compatible when fields are added, removed, or changed.
- **Error behavior:** how invalid requests are rejected, and whether malformed messages are retried or routed to a dead-letter queue.

A contract is more than just a schema file. It also encompasses naming conventions, business semantics, validation rules, versioning, and error-handling policies.

### Example: Create Order Request

A client sends data to create an order:

```json
{
  "customerId": "cus_123",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    }
  ],
  "currency": "VND",
  "requestedAt": "2026-11-17T10:15:30Z"
}
```

The contract might specify:

- customerId is an identifier string and cannot be blank.
- items is an array with at least one element and an upper bound on line items.
- Each line item must have sku and quantity.
- quantity is a positive integer within an allowed range.
- currency is a currency code following an agreed convention.
- requestedAt is a timestamp in a timezone-aware date-time format.

These rules must be documented clearly so the client, API Gateway, function, and messaging system do not make conflicting assumptions.

## 2. Distinguishing JSON Syntax, Schema, and Business Rules

Validation should be organized into multiple layers because each layer catches a different class of errors.

| Validation Layer | Question to Answer | Example Errors |
|---|---|---|
| Syntax and parsing | Is the payload valid, readable JSON? | Missing quotation marks, misplaced commas |
| Structure/schema | Does the JSON match the contract's types and structure? | quantity is a string, missing customerId, items is an object instead of an array |
| Data constraints | Are values within declared bounds? | quantity equals 0, sku exceeds max length |
| Business rules | Is the data valid in the current system context? | Customer is suspended, SKU does not exist, quantity exceeds available stock |
| Access control | Is the caller authorized to perform this action on this data? | User modifying an order belonging to another account |

JSON Schema describes structure and many data constraints. Bean Validation in Java validates objects after deserialization. Business rules and access control typically require application logic or querying current state.

Never treat passing schema validation as proof that a request is safe or authorized. For example, a well-formed customerId does not prove the caller has permission to place an order for that customer.

## 3. Designing a JSON Schema

JSON Schema is a language for describing the structure and constraints of JSON documents. A schema can be used in testing, API documentation, message verification, or payload validation prior to invoking business logic.

The following example uses JSON Schema Draft 2020-12:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/create-order-v1.json",
  "title": "CreateOrderRequest",
  "type": "object",
  "additionalProperties": false,
  "required": ["customerId", "items", "currency"],
  "properties": {
    "customerId": {
      "type": "string",
      "minLength": 1,
      "maxLength": 64,
      "pattern": "^[A-Za-z0-9_-]+$"
    },
    "items": {
      "type": "array",
      "minItems": 1,
      "maxItems": 50,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["sku", "quantity"],
        "properties": {
          "sku": {
            "type": "string",
            "minLength": 1,
            "maxLength": 40
          },
          "quantity": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000
          }
        }
      }
    },
    "currency": {
      "type": "string",
      "pattern": "^[A-Z]{3}$"
    },
    "requestedAt": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

Some key keywords:

| Keyword | Meaning | Example Usage |
|---|---|---|
| type | Accepted JSON type | object, array, string, integer, number, boolean, null |
| properties | Schema for each object property | customerId, items |
| required | List of fields that must be present | customerId and items |
| additionalProperties | Whether undeclared fields are allowed | false to reject extra fields |
| minLength, maxLength | String length bounds | SKU at most 40 characters |
| minimum, maximum | Numeric value bounds | quantity from 1 to 1000 |
| minItems, maxItems | Array element count bounds | Order has 1 to 50 line items |
| enum, const | Allowed value set or a fixed constant | Status within an allowed set |
| pattern | Regular expression constraint | Identifier matching a pattern |
| format | Specialized format hint or check | date-time, email, uri |

A schema can reference other schemas with $ref to reuse structures such as Address or Money. As schemas evolve, name and version them explicitly rather than duplicating the same structure across multiple places.

### Required Fields, Optional Fields, and Null

These three states are distinct:

1. The field is absent from the JSON.
2. The field is present with a value of null.
3. The field is present with a concrete value.

For example, if middleName is optional and does not allow null, the client may omit the field entirely when no data exists. If the contract allows null, a Draft 2020-12 schema can declare the type as follows:

```json
{
  "type": ["string", "null"]
}
```

Whether a field appears in required is a separate rule. A field can be required to appear while permitting null; conversely, a field can be optional to include, yet if present it must be a string.

Clarify the semantics of empty strings, whitespace-only strings, and null. For a user's name, a whitespace-only string usually holds no value; for a note field, an empty string may be acceptable depending on business rules. Schemas have minLength, but trimming leading/trailing whitespace often requires additional application-layer rules.

### Choosing Data Types and Units

- Use integer for counts such as quantity, retryCount, or item count.
- Use number for numeric values with fractional parts when the contract genuinely needs a JSON numeric type.
- For money, consider representing amounts as integers in the minor unit (e.g., dong or cents) or decimal strings with clear rules. In Java, use BigDecimal for monetary calculations; avoid float or double for financial arithmetic.
- Use string for identifiers, phone numbers, postal codes, and values with leading zeros or no arithmetic meaning.
- Use boolean for true/false flags, rather than the string "true" or numbers 0/1 if the contract specifies boolean.
- Use ISO 8601 timestamps with an offset or UTC. Standardize interpretation and precision; do not send local times without a timezone if the system needs an unambiguous instant.

JSON Schema includes the format keyword, but how validators enforce format depends on the library and configuration. In some Draft 2020-12 implementations, format may be treated merely as an annotation unless format assertion is enabled. Always verify validator configuration and add explicit checks when a format is mandatory.

### Should Undeclared Fields Be Rejected?

additionalProperties: false helps catch typos and prevents clients from sending fields outside the contract. It is useful for commands or requests requiring strict control. However, if a producer adds a new field, older consumers using a strict schema may reject the payload even when the new field does not affect them.

Choose a policy based on contract type:

- For incoming commands requiring tight control, rejecting unknown fields prevents errors and reduces mass assignment risks.
- For events consumed independently by many consumers, allowing or ignoring unknown fields generally enables more compatible evolution.
- Whichever policy you choose, test how Java parsers and mappers behave when encountering new fields.

Never silently ignore fields that carry security significance or affect business logic. If unknown fields are ignored, log sufficient diagnostics to detect when producer and consumer contracts drift.

## 4. Naming Conventions and Payload Design

A good schema must be consistent and clear to every participant.

**Field names.** Pick one convention such as camelCase and apply it consistently. Avoid mixing customer_id in one place and customerId in another for the same concept. Names should reflect business semantics rather than internal implementation details.

**Units of measure.** Specify units in the field name or documentation. For example, timeoutMillis is clearer than timeout when the value is in milliseconds. For sizes, specify bytes, KB, or MiB.

**Identifiers.** Choose a stable format. Do not use display names as reference keys if names can change. When uniqueness across multiple systems is required, use IDs with a clearly defined uniqueness scope.

**Timestamps.** Standardize on UTC or ISO 8601 with offset, such as 2026-11-17T10:15:30Z. Distinguish occurrence time (occurredAt) from system receipt or processing time (receivedAt, processedAt).

**Derived data.** Avoid letting clients dictate values that the server can compute reliably. For example, the server should calculate the total amount from verified prices and quantities rather than trusting a client-supplied totalAmount.

**Payload size.** Set limits on body size, object nesting depth, array element count, string length, and individual message size. Limits must align with API Gateway, queue, event source, and runtime constraints used by the system.

**Sensitive data.** Do not include passwords, access tokens, or unnecessary secrets in events. Events are often persisted, retried, copied, and routed across multiple services; emit only the minimum data required by consumers.

## 5. Validating Input Data in Java

In Java, a common workflow is to parse JSON into a DTO, validate constraints, and then enforce business rules. Jackson is typically used to deserialize JSON; Jakarta Bean Validation provides annotations and an API for object validation.

Example DTO using records and Bean Validation:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreateOrderRequest(
        @NotBlank
        @Size(max = 64)
        @Pattern(regexp = "^[A-Za-z0-9_-]+$")
        String customerId,

        @NotEmpty
        @Size(max = 50)
        List<@Valid OrderItemRequest> items,

        @NotBlank
        @Pattern(regexp = "^[A-Z]{3}$")
        String currency
) {}

public record OrderItemRequest(
        @NotBlank
        @Size(max = 40)
        String sku,

        @Positive
        int quantity
) {}
```

Meaning of the annotations:

- @NotBlank requires a non-null string containing at least one non-whitespace character.
- @NotEmpty requires a non-null, non-empty collection or string.
- @Size bounds length or element count.
- @Pattern validates a string against a regular expression.
- @Positive requires a number strictly greater than 0.
- @Valid instructs the validator to recursively validate nested objects or collection elements.

Bean Validation checks only the declared constraints. To check whether the currency is supported by the system or whether the SKU exists, invoke a domain service after DTO validation.

### Invoking the Validator

A Validator initialized at application startup can be reused across invocations. The example below illustrates validation after the request has been deserialized:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;

public class OrderRequestValidator {

    private final Validator validator;

    public OrderRequestValidator(Validator validator) {
        this.validator = validator;
    }

    public void validate(CreateOrderRequest request) {
        Set<ConstraintViolation<CreateOrderRequest>> violations =
                validator.validate(request);

        if (!violations.isEmpty()) {
            throw new InvalidRequestException(violations);
        }
    }
}
```

In production applications, dependency injection can provide the Validator. If creating a ValidatorFactory manually, initialize it at startup, reuse the Validator, and close the factory when the application shuts down. Avoid creating a ValidatorFactory per request, as it incurs unnecessary overhead.

When translating validation errors into a response, return the field name, error code, and an actionable message. Do not expose stack traces, secret values, or the entire payload in the response.

### Distinguishing Parse Errors from Validation Errors

Deserialization may fail before Bean Validation runs. For example, quantity receives the string "two" when the DTO expects an int. Handle these distinctly:

- Malformed JSON or type conversion failure: parse/deserialization error.
- Valid JSON syntax with missing fields or constraint violations: validation error.
- Structurally valid data violating current business state: business error.
- Caller lacks permission: authentication or authorization error.

Making this distinction helps clients fix the right issue and helps systems decide whether a message should be retried.

## 6. Applying Validation to HTTP Requests

HTTP functions typically receive events from an API Gateway or HTTP adapter. Never assume the body has already been thoroughly validated merely because the request passed through a gateway. A gateway may check certain limits or schemas if configured, but the handler still needs to verify data at its own trust boundary.

A typical pipeline:

1. Check body size limits and required headers.
2. Parse JSON using a safe parser configuration.
3. Validate the schema or deserialize into a structured DTO.
4. Run Bean Validation.
5. Authenticate identity and check permissions on the target resources.
6. Validate business rules and current state.
7. Execute the operation within an appropriate transaction and return the response.

The order of authentication and detailed validation may vary according to security design. For instance, an API may validate the token before deeply parsing the body to prevent unauthenticated callers from consuming resources. Regardless, never use input data to make authorization decisions before authenticating identity.

### Error Response Conventions

An API might define:

| HTTP Status | Typical Cases |
|---|---|
| 400 Bad Request | Malformed JSON, missing fields, or invalid request structure |
| 401 Unauthorized | Missing or invalid authentication credentials |
| 403 Forbidden | Authenticated but lacks permission |
| 404 Not Found | Resource does not exist or its existence must not be disclosed |
| 409 Conflict | Conflict with current state or improper reuse of an idempotency key |
| 422 Unprocessable Content | Syntactically valid JSON that violates content/business rules |

Whether to use 400 or 422 for validation errors depends on API conventions. What matters is documenting it and staying consistent. An error response might contain a code, message, and list of field-level errors; avoid leaking internal details or stack traces.

## 7. Applying Validation to Messages and Events

Messages and events are usually processed asynchronously. There is no waiting HTTP client able to correct the data immediately, so error policies must tie into retries, message acknowledgment, and dead-letter queues.

### Designing the Event Envelope

An event typically has two parts:

- **Envelope:** routing and identification metadata such as ID, source, event type, timestamp, and version.
- **Data payload:** business data consumers need for processing.

CloudEvents can serve as a standard envelope convention. Example:

```json
{
  "specversion": "1.0",
  "id": "evt-8d3f",
  "source": "/orders/service",
  "type": "com.example.orders.created.v1",
  "subject": "orders/ord-123",
  "time": "2026-11-17T10:15:30Z",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "ord-123",
    "customerId": "cus_123",
    "currency": "VND",
    "items": [
      {
        "sku": "BOOK-01",
        "quantity": 2
      }
    ]
  }
}
```

The envelope lets consumers determine where the event came from, what type it is, and which ID can be used for deduplication. Data schemas must be managed per event type and version. Do not confuse event ID with order ID: a single order can emit many different events.

### Message Processing Flow

A consumer can follow these steps:

1. Validate the envelope: spec version, ID, source, type, and content type.
2. Select the matching schema by event type and version.
3. Parse data and run schema and DTO validation.
4. Check necessary business conditions.
5. Use the event ID or an appropriate business key to ensure idempotency.
6. Persist the result durably before acknowledging the message per platform semantics.

Distinguish recoverable errors from permanent data errors:

- **Transient errors:** database timeouts, overloaded downstream dependencies, or network errors. Can be retried with backoff and an attempt limit.
- **Contract errors:** malformed JSON, missing required fields, wrong data types, or unsupported event versions. Retrying the same payload rarely helps; log the error and route to a dead-letter queue or quarantine stream.
- **Business errors:** schema-valid data that cannot be applied in the current state. Decide per business policy: retry later, ignore, require manual intervention, or route to DLQ.

For batched messages, understand whether the platform acknowledges the whole batch or supports partial batch responses. If only one item fails, an improper acknowledgment mechanism can cause the entire batch to be reprocessed. Consumers must remain idempotent because retries can occur even after partial side effects have taken place.

### Maintaining Compatibility Between Producer and Consumer

Producers and consumers may be deployed at different times. Therefore, event contracts should prioritize compatible evolution:

- Adding optional fields is usually more compatible than adding required fields.
- Consumers should ignore unknown fields if the contract permits.
- Do not change the data type or semantics of an active field.
- Do not remove a field while consumers still depend on it.
- For incompatible changes, create a new schema version or event type and establish a consumer migration plan.
- If enums can expand, consumers must handle unknown values under a safe policy.

Adding a new field can still break consumers if they use schemas with additionalProperties: false or DTO mappers configured to fail on unknown properties. Therefore, compatibility must be tested across the schema validator, JSON deserializer, and business code.

## 8. Safety When Accepting Untrusted Data

Validation is one layer of defense; it does not replace other security controls.

**Resource limits.** Enforce body size limits before parsing; bound JSON nesting depth, string length, array item count, and execution time. Very large or deeply nested payloads can spike memory and CPU, impacting serverless costs.

**Use allow-lists.** Map only supported fields. Avoid automatically binding raw JSON directly into database entities containing sensitive fields such as role, ownerId, or balance. If clients can supply such fields, mass assignment vulnerabilities may allow unintended data modification.

**Never trust client-computed values.** Prices, totals, ownership, payment statuses, and user roles must be determined or verified from authoritative server-side sources.

**Separate validation from sanitization.** Validation checks whether data satisfies the contract. Sanitization or encoding governs how data is safely used in a specific context. Avoid trying to strip all special characters with a generic filter; use parameterized queries for SQL and context-appropriate output encoding for HTML, URLs, or logs.

**Enforce authorization separately.** A valid ID format does not prove the caller has permission to access that entity. Always verify tenant, owner, or policy before reading or modifying data.

**Protect data in logs.** Log error codes, event IDs, correlation IDs, and violating field names when needed. Avoid logging tokens, passwords, payment data, or full payloads containing personal information. For messages routed to a DLQ, restrict access permissions and retention duration.

## 9. Schema Versioning and Contract Testing

Schemas are part of the interface between components and should be managed like source code.

### Versioning

Versions can be placed in the schema path, event type name, or explicit metadata. For example:

- https://example.com/schemas/create-order-v1.json
- com.example.orders.created.v1

Pick one consistent rule and state clearly which payload a version applies to. Do not merely rename files without giving consumers a way to determine the version from the received message.

### Compatible Changes

| Change | Compatibility Risk | Handling Approach |
|---|---|---|
| Adding an optional field | Usually low if consumers ignore unknown fields | Test older consumers with new payloads |
| Adding a required field | High for older producers | Apply only in a new version or after a transition window |
| Removing a field | High for consumers reading that field | Deprecate first, monitor usage, then remove in a new version |
| Changing a data type | High | Introduce a new field or version and migrate deliberately |
| Narrowing value bounds | Can invalidate older payloads | Check real production data and consumers before applying |
| Adding an enum value | Can cause incomplete handling in consumers | Consumers need a branch for unknown values |
| Changing field semantics | Very high even if data type stays unchanged | Introduce a new field or event type |

### Recommended Tests

- Minimal valid payload and full valid payload.
- Each required field missing individually.
- Wrong types, nulls, empty strings, negative numbers, and out-of-range values.
- Empty arrays, too many items, or malformed items.
- Unknown fields according to the schema's policy.
- Malformed timestamps, wrong offsets, or missing timezones when required by the contract.
- Old and new event versions.
- Duplicate message deliveries.
- Current consumer processing payloads emitted by the next producer version.

Run schema validation in CI to catch incompatible changes before deployment. In systems with multiple producers and consumers, cross-party contract tests catch cases where one side changes before the other is ready.

## 10. Practical Design and Implementation Workflow

When adding a new HTTP function or event consumer, follow this sequence:

1. Identify who produces the payload and who consumes it.
2. Write valid JSON examples, including required, optional, and nested fields.
3. Define the JSON Schema: types, required fields, bounds, enums, formats, and unknown-field policy.
4. Document semantics: units, timezones, IDs, null meaning, and derived values.
5. Map the schema to Java DTOs and declare Bean Validation constraints.
6. Add business rule checks, access control, and idempotency at the appropriate layers.
7. Specify HTTP error responses or error-message handling, retries, and DLQ behavior.
8. Write tests for valid payloads, invalid payloads, and version compatibility.
9. Monitor validation failures by event type, producer, and schema version to identify components violating the contract.

In serverless environments, validation should happen early at the ingestion boundary to avoid invoking databases or external services for payloads that are clearly invalid. However, avoid fetching an entire schema registry or instantiating heavy validators on every invocation. Load schemas and create validators once per execution environment lifecycle when the library is thread-safe and has an appropriate refresh mechanism.

## 11. Key Takeaways

A syntactically valid JSON payload is not guaranteed to be valid for the application. Describe structure and bounds using JSON Schema, map to Java DTOs with validation, and then enforce business rules and access control.

For HTTP requests, return consistent error responses so clients know how to correct their input. For messages and events, distinguish transient errors from contract violations to decide between retrying and routing to a DLQ. Manage versions and run compatibility tests so producers and consumers can evolve independently without breaking processing flows.

A clear data contract makes function input handling predictable, reduces integration bugs, and keeps costs under control from unnecessary retries, malformed payloads, or wasted processing.
