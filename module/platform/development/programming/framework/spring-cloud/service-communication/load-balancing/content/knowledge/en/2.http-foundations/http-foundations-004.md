# JSON Serialization, Data Types, and Exchange Contracts

In inter-service communication, both sides must agree on how data is represented over HTTP. The application sends a Java object, the client serializes that object into JSON bytes, and the receiving service deserializes the JSON into its own data types, processes it, and returns a result. If the two sides interpret field names, data types, null values, or timestamp formats differently, requests can fail even when both services are healthy.

This lesson belongs to the **HTTP Foundations** chapter of the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module. In this module, you learn about Spring Cloud LoadBalancer's client-side load balancing mechanism: selecting a `ServiceInstance` by service ID, service discovery, health checks, and routing policies; and you practice integrating `RestClient`, `WebClient`, `OpenFeign`, configuring retries/timeouts, and observing errors to make inter-service communication reliable. Those mechanisms decide which instance receives the request. The JSON contract decides how the instance receives and returns data. All instances serving the same service ID must understand this contract compatibly with one another.

After this lesson, you will be able to:

- Explain the JSON serialization and deserialization flow in an HTTP request/response.
- Choose Java types suited to JSON data types and clearly define the meaning of missing fields, `null`, and default values.
- Design DTOs and stable request/response contracts between services.
- Recognize data compatibility errors that can appear when LoadBalancer distributes requests across multiple service versions.
- Inspect headers, payloads, and Jackson configuration when a client fails to read a response.

## 1. Where Does JSON Fit in the Inter-Service Communication Flow?

JSON is a data representation format. It neither selects the target address nor performs load balancing. In Spring, HTTP clients and message converters/codecs handle converting Java objects to JSON and vice versa. Spring Cloud LoadBalancer handles resolving a service ID to a specific instance.

High-level flow when one service calls another:

```mermaid
flowchart LR
    A["DTO object on client"] --> B["HTTP client"]
    B --> C["Jackson serialization"]
    C --> D["HTTP request containing JSON"]
    D --> E["Spring Cloud LoadBalancer"]
    E --> F["Selected ServiceInstance"]
    F --> G["Jackson deserialization"]
    G --> H["DTO object on server"]
    H --> I["Business processing"]
    I --> J["JSON response"]
    J --> K["Client deserializes response"]
```

For example, the client calls the logical address `http://reservation-service/api/reservations`. LoadBalancer selects an available instance of `reservation-service`, such as `10.0.2.15:8080`. The JSON body must still follow the same API contract regardless of which instance receives the request.

This has an important consequence: if three instances register under the service ID `reservation-service` but each instance uses a different response structure, failures can appear inconsistently. One request succeeds, the next fails because LoadBalancer picked an instance with an incompatible version. Keep the exchange contract compatible across instances throughout deployments.

## 2. What Does a JSON Exchange Contract Include?

An API contract describes how two parties exchange data. A sufficiently clear contract specifies:

- HTTP method and endpoint, for example `POST /api/reservations`.
- Accepted and returned headers, especially `Content-Type` and `Accept`.
- JSON field names, data types, required fields, and optional fields.
- Meaning of `null`, omitted fields, and default values.
- Date/time formats, time zones, units of measurement, and status code conventions.
- Success response structure and error response structure.
- Compatibility rules when adding, renaming, or removing fields.

Suppose a service receives a reservation creation request. The client sends:

```json
{
  "sku": "SKU-RED-01",
  "quantity": 2,
  "requestedAt": "2026-11-17T10:15:30Z",
  "note": "Deliver in the morning"
}
```

The service may return:

```json
{
  "id": "res-8421",
  "sku": "SKU-RED-01",
  "quantity": 2,
  "status": "ACCEPTED",
  "createdAt": "2026-11-17T10:15:31Z"
}
```

These two payloads are part of the contract. Both sides must agree that `quantity` is a positive integer, `requestedAt` is an ISO 8601 timestamp in UTC, `status` is an agreed status code, and `id` is transmitted as a string.

Field names are also part of the contract. If the server renames `createdAt` to `created_at` without preserving backward compatibility or notifying clients, clients may fail to read the expected value. The fact that both field names mean "creation timestamp" does not make them automatically equivalent during deserialization.

## 3. JSON Data Types and Java Types

JSON has only a few basic data types: string, number, boolean, object, array, and null. JSON has no dedicated date/time, enum, UUID, or decimal types. Those values are typically represented as strings or numbers according to API conventions.

| JSON Type | Common Java Types | Design notes |
|---|---|---|
| string | `String`, `UUID`, enum | UUIDs, status codes, and timestamps need stable representation conventions. |
| number | `int`, `long`, `BigDecimal` | Choose appropriate value range and precision; avoid `double` for money. |
| boolean | `boolean`, `Boolean` | `Boolean` can also represent an unset state. |
| object | Nested DTO or record | Define a clear structure rather than accepting arbitrary data. |
| array | `List<T>`, `Set<T>` | Agree on element ordering and handling of duplicate elements. |
| null | Nullable reference types | Define what `null` means in the contract. |

### Integers, decimals, and identifiers

JSON represents numbers as a single `number` type, without distinguishing `int`, `long`, or `BigDecimal`. Therefore, server and client must agree on range and precision.

- Use `int` for quantities bounded within the 32-bit range.
- Use `long` when integer values may exceed the range of `int`.
- Use `BigDecimal` for money or decimal numbers requiring exact precision.
- Avoid `float` or `double` for monetary calculations because they represent real numbers using binary floating point.

A note when integrating with JavaScript: the `Number` type only represents integers accurately within the safe range from `-(2^53 - 1)` to `2^53 - 1`. If an API exchanges 64-bit integer IDs that could exceed this limit, consider representing IDs as strings so clients do not round values.

Money also needs clear conventions. Sending only `amount: 120000` is insufficient if parties do not know the currency and decimal rules. You can use a structure such as:

```json
{
  "amount": "120000.50",
  "currency": "USD"
}
```

If using a string for monetary amounts, the API must specify the decimal format and parsing rules. If using a JSON number, the Java side should use `BigDecimal` and other clients must preserve precision.

### Dates, times, and time zones

JSON has no date/time type. Timestamps are usually transmitted as ISO 8601 strings:

```json
{
  "createdAt": "2026-11-17T10:15:31Z",
  "deliveryDate": "2026-11-18"
}
```

In Java:

- `Instant` is suitable for representing an absolute point on the timeline; values are typically exchanged in UTC with a `Z` suffix.
- `OffsetDateTime` preserves both the instant and the timezone offset.
- `LocalDate` suits calendar dates not tied to a time of day, such as a delivery date.
- `LocalDateTime` contains no time zone or offset. Use it only when the contract explicitly establishes the time zone context externally.

For example, `2026-11-17T10:15:30Z` and `2026-11-17T17:15:30+07:00` represent the same instant. If two services interpret timestamp strings using their server default time zones, results can diverge when deployed across different environments. For event timestamps, prefer UTC or an explicit offset.

Avoid locale-dependent date/time formats such as `17/11/2026 10:15` in machine-to-machine APIs. Such strings can be interpreted in multiple day/month orders and carry no time zone information.

### Enums and status codes

Java enums are typically serialized as their constant names, such as `ACCEPTED`. Renaming a constant in code can change the JSON payload and break older clients.

For public API values, treat status codes as part of the contract. Choose stable, documented codes and avoid changing them merely because an internal variable name is refactored. If a user-facing display label is needed, pass it in a separate field; do not use display labels as business codes.

When adding a new enum value, check how older clients handle unknown values. A client that deserializes enums strictly may throw an error upon receiving a new value. You can design clients with a fallback value such as `UNKNOWN` when business logic permits, or deploy in an order ensuring the server does not emit the new value before clients support it.

### Missing, null, and empty fields

The following three cases do not necessarily have the same meaning:

```json
{}
```

```json
{ "note": null }
```

```json
{ "note": "" }
```

- Missing field: the sender did not provide that field.
- `null`: the sender explicitly indicated that the field has no value.
- Empty string: the field is present and its value is an empty string.
- Empty array `[]`: a list is present but currently has no elements.

With some DTOs, Jackson may map both a missing field and a `null` field to Java `null`. If business logic needs to distinguish the two cases—such as in partial update APIs—design the DTO or payload reader to preserve that distinction. Do not rely on default behavior without verifying it.

Primitive types like `int` and `boolean` cannot hold null. When a field may be absent, wrapper types `Integer` or `Boolean` may be more appropriate. Conversely, for required fields, use validation to reject missing or invalid data rather than silently accepting defaults such as `0` or `false`.

## 4. Using DTOs and Jackson to Keep the Contract Clear

A DTO (Data Transfer Object) is a data type dedicated to exchange across the HTTP boundary. DTOs give the API precise control over which fields are sent and received, whereas entities may contain relationships, internal fields, or database-coupled structures.

Example using Java records:

```java
public record CreateReservationRequest(
    @NotBlank String sku,
    @Positive int quantity,
    Instant requestedAt,
    String note
) {}

public record ReservationResponse(
    String id,
    String sku,
    int quantity,
    ReservationStatus status,
    Instant createdAt
) {}

public enum ReservationStatus {
    ACCEPTED,
    REJECTED
}
```

The `@NotBlank` and `@Positive` annotations express input constraints. The controller must enable validation, typically with `@Valid`, so constraints are checked before business processing.

```java
@RestController
@RequestMapping("/api/reservations")
class ReservationController {

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<ReservationResponse> create(
            @Valid @RequestBody CreateReservationRequest request) {
        ReservationResponse response = reservationService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

In a Spring Boot application, Jackson is typically integrated via HTTP message converters to read `@RequestBody` and write response objects. With `RestClient`, `WebClient`, and OpenFeign, conversion is handled by the corresponding converter or codec. Use the application-managed mapper configuration so clients and servers follow the same conventions.

If a Java property name differs from the JSON field name, declare it explicitly with `@JsonProperty`:

```java
public record ReservationResponse(
    @JsonProperty("reservation_id") String id,
    String sku,
    int quantity
) {}
```

The JSON will then contain the `reservation_id` field, even though the Java component is named `id`. Apply consistent naming conventions across the entire API and document them in the contract.

Avoid returning entities directly from controllers. Changing an entity or ORM relationship can then accidentally alter the public payload. Map entities to response DTOs to control exposed data and keep the API stable as the persistence model evolves.

## 5. HTTP Headers and Integration with Load-Balanced Clients

Headers specify how to interpret the body and which format the client expects to receive:

- `Content-Type: application/json`: the request body is being sent as JSON.
- `Accept: application/json`: the client wants to receive the response as JSON.
- `Content-Type: application/problem+json`: an error response in Problem Details format.

An example request can be represented as follows:

```http
POST /api/reservations HTTP/1.1
Host: reservation-service
Content-Type: application/json
Accept: application/json

{
  "sku": "SKU-RED-01",
  "quantity": 2,
  "requestedAt": "2026-11-17T10:15:30Z"
}
```

When using a service ID with Spring Cloud LoadBalancer, applications typically declare a client marked with `@LoadBalanced`. Example with `RestClient`:

```java
@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Then the client sends the DTO to the service's logical hostname:

```java
ReservationResponse response = restClient.post()
    .uri("http://reservation-service/api/reservations")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .body(request)
    .retrieve()
    .body(ReservationResponse.class);
```

With `WebClient`, the DTO can be sent using `bodyValue(request)`; with OpenFeign, the DTO is typically declared with `@RequestBody` on a method annotated with `@PostMapping`. All three approaches require a consistent JSON contract. Switching from `RestClient` to `WebClient` or OpenFeign does not automatically fix mismatches in field names, data types, or timestamp formats.

When debugging conversion errors, inspect both the actual headers and body. A server might return JSON while declaring the wrong `Content-Type`; a client might only accept a different media type; or the payload might contain a field that the receiving Java type cannot deserialize. Inspect the response from the actual selected instance, especially when the error occurs only on some requests.

## 6. Standardizing Error Responses

Error responses are also part of the contract. If every service returns errors in a different structure, clients must write many branching handlers and struggle to distinguish business errors from infrastructure errors.

Spring Framework 6 and later support `ProblemDetail` for the Problem Details format. Example error payload:

```json
{
  "type": "about:blank",
  "title": "Reservation rejected",
  "status": 409,
  "detail": "The requested quantity is not available.",
  "instance": "/api/reservations",
  "code": "INSUFFICIENT_STOCK"
}
```

This response typically uses `Content-Type: application/problem+json`. The `status` field describes the HTTP status, while `code` is a stable error code for clients to handle by business logic. The `detail` text aids diagnostics but should not contain stack traces, credentials, or sensitive internal data.

The client must handle both outcome groups:

- Success: deserialize the body into the published response DTO.
- Failure: read the HTTP status and error body according to the contract, then decide whether to display, retry, or propagate the error to the calling layer.

Do not treat every HTTP failure as a JSON error. Timeouts, connection errors, services with no available instances, and deserialization errors are distinct situations that must be observed separately. Retries are appropriate only for certain transient errors and must account for operation idempotency. Retries cannot fix an incompatible JSON contract.

## 7. Keeping Contracts Compatible Across Multiple Instances

Spring Cloud LoadBalancer can distribute consecutive requests across different instances. During a rolling deployment, old and new versions of the same service ID may coexist simultaneously. Therefore, payload changes must account for both running clients and servers.

For example, a new version adds a `warehouseCode` field to the response. If this field is optional and older clients ignore unknown fields, the change is usually easier to roll out. Conversely, changing `quantity` from a number to a string or renaming `createdAt` without supporting the old name can break existing clients immediately once requests are routed to the new instance.

Practical rules:

1. **Prefer additive changes.** Adding optional fields is usually more compatible than removing fields or changing existing field types.
2. **Preserve data semantics.** Do not change units, time zones, rounding rules, or field meanings without a migration plan.
3. **Manage enums carefully.** Clients need a strategy for new values; servers must emit new values in an agreed deployment sequence.
4. **Do not assume all clients ignore unknown fields.** Behavior when encountering undeclared JSON properties depends on deserialization configuration. Verify the application's actual Jackson settings.
5. **Maintain compatibility during rolling deployments.** Instances under the same service ID must support payloads that active clients can send and receive.
6. **Reserve API versioning for breaking changes.** Use versioning in the URL or an agreed versioning mechanism, while maintaining a transition window between clients and servers.

An error appearing at a certain rate can signal that running instances differ in version or Jackson configuration. Compare deployment versions, response bodies, and configurations across individual instances. If a retry makes the next call succeed, that may only show the request landed on a different instance; it does not prove the contract issue is fixed.

## 8. Testing Serialization and Deserialization

Contracts can be tested across multiple layers:

- **DTO tests:** verify validation for required fields, quantity bounds, code formats, and valid values.
- **JSON tests:** use the Spring-configured `ObjectMapper` to serialize DTOs, deserialize them back, and compare key values.
- **HTTP tests:** call endpoints with the right `Content-Type`, `Accept`, valid payloads, and invalid payloads; verify status codes and response bodies.
- **Compatibility tests:** use sample payloads from the previous version to confirm the new version can still read data it must support.
- **Tests through LoadBalancer:** send multiple requests via the service ID and verify all instances return compatible contract structures.

A simple serialization test can use the mapper configured by Spring Boot:

```java
String json = objectMapper.writeValueAsString(request);
CreateReservationRequest restored =
    objectMapper.readValue(json, CreateReservationRequest.class);
```

In applications with date/time types such as `Instant`, verify both the generated JSON format and round-trip parsing. Avoid instantiating a separate `ObjectMapper` with different settings from the mapper used by the HTTP client/server; if the two mappers differ, unit tests can pass while real requests still fail.

When investigating a data exchange error, check in order:

1. Is the client calling the right service ID and endpoint?
2. Does the request have the right `Content-Type` and the response the right `Accept`?
3. Do field names, data types, and date/time formats match the contract?
4. Is a required field missing, `null`, or carrying an out-of-range value?
5. Is the error response handled by the client as an error payload?
6. Are all instances under the same service ID running compatible contracts and configurations?

Logs should include the correlation ID, service ID, the instance or version that handled the request, HTTP status, and relevant conversion error details. Do not log full payloads if they contain personal data, tokens, or business secrets.

## 9. Key Takeaways

- JSON is the exchange format; Jackson converts between JSON and Java types.
- An API contract covers method, endpoint, headers, field names, data types, nullability, timestamp formats, and error structure.
- Use DTOs to control payloads; avoid letting entity changes alter the API unexpectedly.
- Choose `BigDecimal` for decimals requiring precision, time types with clear time zone conventions, and strings where identifiers might require them.
- Distinguish missing fields, `null`, and empty values when they carry different business meanings.
- Spring Cloud LoadBalancer selects instances by service ID; every selected instance must adhere to a compatible contract.
- Inspect actual payloads and Jackson configuration when errors occur only on some requests or some instances.

Once the JSON contract is agreed upon, clients such as `RestClient`, `WebClient`, and OpenFeign can communicate with service IDs consistently, while Spring Cloud LoadBalancer focuses on selecting an eligible instance to deliver requests to their destination.
