# Verifying Serialization, Deserialization, and Error Mapping

## 1. Why Must Consumer Tests Check All Three Stages?

In **Spring Cloud Contract (SCC)**, a Groovy DSL or YAML DSL contract describes the request a **consumer** must send and the response a **producer** commits to returning. SCC generates **generated tests** to verify the producer implementation, while also generating **HTTP stubs** so consumers can test independently of the producer using **Stub Runner**. When properly integrated into CI, these two verification paths help catch incompatible API changes early.

However, a client can still fail even when the stub returns valid JSON, because the HTTP boundary is more than Java objects:

- **Serialization (request encoding):** the client must turn Java objects into the **exact HTTP method, path, query, headers, and JSON bytes** expected by the producer.
- **Deserialization (response decoding):** the client must convert the HTTP response into the right DTO/data types without dropping required fields or silently changing data semantics.
- **Error mapping:** the client must interpret status codes and error bodies per the contract, translating them into appropriate business outcomes or exceptions instead of treating every `404`, `409`, or `503` as the same error.

For example, the producer commits to `quantity` as a JSON number, but the consumer DTO stores it as a `String`; in some cases the library silently coerces it, masking the bug. Or the producer returns a structured error `{"code":"SKU_NOT_FOUND"}`, while the consumer catches every HTTP 404 and treats it as "SKU does not exist"—even when the 404 came from **WireMock failing to match the request**.

This lesson belongs to the **Consumer Testing** chapter and focuses directly on **verifying serialization, deserialization, and error mapping**. The examples use **Checkout Service** as the consumer and **Inventory Service** as the producer, with Spring Framework `RestClient`, Jackson, and SCC Stub Runner.

### Learning Outcomes

After this lesson, you will be able to:

1. Explain the three data boundaries of an HTTP consumer and why they must be tested with the real client.
2. Write Groovy/YAML contracts for JSON requests, success responses, and error responses.
3. Verify serialization for method, URL, `Content-Type`, `Accept`, field names, and numeric/boolean types.
4. Design Jackson DTOs that handle missing fields, `null`, unknown fields, enums, dates/times, and currency explicitly.
5. Write clients that map `404 SKU_NOT_FOUND`, `503 INVENTORY_UNAVAILABLE`, and transport/protocol errors into distinct outcomes.
6. Distinguish a **business 404** from an **unmatched WireMock 404**.
7. Create consumer contract tests with Stub Runner and negative tests proving defects are caught.
8. Wire producer tests, candidate stubs, and consumer tests into CI to detect breaking changes.

## 2. Real Data Flow Across the HTTP Boundary

~~~mermaid
sequenceDiagram
    participant A as Checkout Application
    participant C as InventoryClient
    participant W as WireMock via Stub Runner
    A->>C: reserve(SKU-123, 2)
    Note over C: Serialize Java request -> HTTP
    C->>W: POST /api/reservations + JSON body
    W-->>C: HTTP 201 + JSON response
    Note over C: Deserialize JSON -> Java DTO
    C-->>A: ReservationResponse
    A->>C: getStock(SKU-404)
    C->>W: GET /api/inventory/SKU-404
    W-->>C: HTTP 404 + ApiError JSON
    Note over C: Map HTTP error -> domain exception
    C-->>A: InventoryNotFoundException
~~~

In this diagram, Stub Runner acts as the **contract-simulated producer**, while `InventoryClient` is **Checkout's real client**. This distinction matters: never mock `InventoryClient` itself and return a hardcoded `StockResponse`, because doing so bypasses serialization and deserialization completely.

| Boundary to Protect | Input | Output | Defect Types Caught |
|---|---|---|---|
| Serialization | Java DTO + method call | HTTP method/path/query/headers/body | Renamed fields, wrong types, wrong content type, malformed URL encoding |
| Stub request matching | Real HTTP request | Selected mapping | Missing headers, wrong URL, mismatched JSON |
| Deserialization | HTTP 2xx + JSON | Java DTO | Missing fields, wrong types, property name drift, null data |
| Error mapping | HTTP 4xx/5xx + error body | Domain exception/result | Confused 404s, ignored error codes, treating 503 as not found |
| Consumer business logic | DTO or domain error | Checkout behavior | Wrong price/stock calculation, inappropriate fallback |

**Core principle:** tests must go through **real production HTTP client calls**, not merely invoke the JSON library directly or assert a hardcoded sample response body.

## 3. Defining the Committed API Scenarios

We use three primary behaviors of Inventory Service:

| Scenario | Request | Committed Response |
|---|---|---|
| Stock available | `GET /api/inventory/SKU-123` | `200`, `StockResponse` JSON |
| SKU does not exist | `GET /api/inventory/SKU-404` | `404`, `ApiError(code=SKU_NOT_FOUND)` |
| Inventory backend temporarily failing | `GET /api/inventory/SKU-503` | `503`, `ApiError(code=INVENTORY_UNAVAILABLE)` |

Success response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Not-found response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "SKU_NOT_FOUND",
  "message": "SKU does not exist",
  "traceId": "trace-demo-404"
}
~~~

Service-unavailable response:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "code": "INVENTORY_UNAVAILABLE",
  "message": "Try again later",
  "traceId": "trace-demo-503"
}
~~~

To test **request body serialization**, we also use:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json
Accept: application/json

{"sku":"SKU-123","quantity":2}
~~~

The producer commits to returning:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"reservationId":"R-1001","status":"RESERVED"}
~~~

This is an **illustrative API used for this lesson**, not default paths or statuses of Spring Cloud Contract. Crucially, the three GET scenarios and one POST scenario thoroughly test the request serializer, success deserializer, and error translator.

## 4. What Is Serialization and What Should Be Asserted?

Serialization turns in-process consumer data into wire protocol structures. With Spring HTTP clients and Jackson, a Java record can be converted to JSON, yet the exact output still depends on ObjectMapper settings, HTTP message converters, and client configuration.

Example:

~~~java
public record ReservationRequest(String sku, int quantity) {}
~~~

Target payload:

~~~json
{"sku":"SKU-123","quantity":2}
~~~

Mismatches that can break the contract:

| What the Consumer Actually Sends | Issue | Why the Stub/Producer May Reject It |
|---|---|---|
| `{"sku":"SKU-123","quantity":2}` | Valid | Matches field names and types |
| `{"productId":"SKU-123","quantity":2}` | Renamed `sku` | Producer does not recognize `productId` |
| `{"sku":"SKU-123","quantity":"2"}` | Quantity is a string | Contract requires a JSON number |
| `{"sku":"SKU-123","quantity":null}` | Quantity is null | May violate validation |
| `{"sku":"SKU-123"}` | Missing quantity | May be rejected or defaulted incorrectly |
| `{"sku":"SKU-123","quantity":2,"debug":true}` | Extra field | Depends on producer and schema policy; not always breaking |
| JSON body with `Content-Type: text/plain` | Wrong header | Producer or stub matcher may reject it |
| POST to wrong path or query | Wrong routing | Mapping does not match |

**Do not blindly compare JSON by byte string equality** if the contract does not require specific property ordering or whitespace. A WireMock `equalToJson` or JSONPath matcher checks JSON semantics much better; when byte ordering or HMAC signatures genuinely matter, test them separately at the byte level.

## 5. Groovy DSL Contract for a POST Request Body

Suppose the producer stores contracts at:

~~~text
src/test/resources/contracts/reservations/create-reservation.groovy
~~~

Illustrative content:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout creates reservation via JSON request'

    request {
        method POST()
        url '/api/reservations'

        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }

        body(
            sku: 'SKU-123',
            quantity: 2
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: 'R-1001',
            status: 'RESERVED'
        )
    }
}
~~~

Significance for consumer testing:

1. `method POST()` and `url` become request-matching conditions.
2. `Content-Type` and `Accept` are communication headers the client must send properly.
3. `request.body` serves as the valid request sample for producer tests and generates the WireMock matcher.
4. `response.status CREATED()` corresponds to HTTP 201.
5. `response.body` is the data the stub returns to the consumer when the request matches.
6. The generated producer test uses the contract to verify the **real producer implementation**, not just WireMock.

If you want to allow dynamic SKUs, use appropriate matchers (regex/JSONPath) instead of hard-coding every value. However, the **actual sample sent in the producer test** must still be valid, and matchers must not be so loose that they accept wrongly typed JSON.

## 6. Equivalent Form in YAML DSL

If the project chooses YAML:

~~~yaml
description: Checkout creates reservation via JSON request
name: create_reservation

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    sku: SKU-123
    quantity: 2

response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: R-1001
    status: RESERVED
~~~

Notes on YAML:

- `quantity: 2` is a **number**; `quantity: '2'` is a **string**.
- `available: true` is a boolean; `available: 'true'` is a string.
- `null`, empty string `''`, and a **missing field** are distinct states.
- Misindenting `request`/`response` or `headers` can cause DSL errors or wrong semantics.
- You can use `request.matchers.body` if your SCC version supports the needed matcher types.

The Groovy and YAML examples are **two alternative choices** for one contract. Do not place both in the same folder if doing so creates duplicate tests/stubs.

## 7. How Does WireMock Matching Protect Client Serialization?

SCC compiles the contract's request section into **WireMock request predicates**. A conceptual mapping from the POST above looks like:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {
        "contains": "application/json"
      },
      "Accept": {
        "contains": "application/json"
      }
    },
    "bodyPatterns": [
      {
        "equalToJson": "{\"sku\":\"SKU-123\",\"quantity\":2}"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED"
    }
  }
}
~~~

This is a **WireMock illustration**, not a guarantee that a given SCC version generates these exact properties, matchers, or `jsonBody`. In actual output, SCC may choose `body`, `matchesJsonPath`, different predicates, or its own mapping filenames.

Inspect the generated mapping to verify whether it enforces:

- Exact method and URL;
- Exact Content-Type/Accept when required by the contract;
- Exact field name `sku` and numeric type of `quantity`;
- Not accidentally accepting `quantity:"2"`;
- Not accidentally accepting requests the consumer should never send.

**Warning:** WireMock request matchers may allow equivalent JSON forms or extra fields depending on settings. If strict schema enforcement is required, choose appropriate matchers/settings or add validation tests on the producer. Never assume an `equalToJson` mapping automatically enforces every schema or Bean Validation rule.

## 8. Writing a Consumer HTTP Client That Sends Valid Requests

An example with `RestClient` (Spring Framework 6.1+; choose compatible Spring Boot/Cloud lines):

~~~java
package com.example.checkout;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class ReservationClient {

    private final RestClient client;

    public ReservationClient(RestClient.Builder builder,
            @org.springframework.beans.factory.annotation.Value(
                "${inventory.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    public ReservationResponse reserve(String sku, int quantity) {
        ReservationRequest request =
                new ReservationRequest(sku, quantity);

        ReservationResponse response = client.post()
                .uri("/api/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(ReservationResponse.class);

        if (response == null || response.reservationId() == null) {
            throw new IllegalStateException(
                    "Reservation response is missing required fields");
        }

        return response;
    }

    public record ReservationRequest(String sku, int quantity) {}

    public record ReservationResponse(
            String reservationId, String status) {}
}
~~~

This example assumes a Spring Boot-configured `RestClient.Builder`, Jackson HTTP message converters, and `inventory.base-url` pointing to the Inventory stub in consumer tests.

Key points:

- `.body(request)` uses the client's real JSON serializer.
- `.contentType(application/json)` declares the **request format**.
- `.accept(application/json)` signals the expected response format.
- `.retrieve().body(ReservationResponse.class)` decodes the response rather than using a mock DTO.
- If the stub fails to match due to a wrong path/header/body, the HTTP response may be a WireMock unmatched 404; the test must fail rather than silently choosing a fake response.

This test only proves the semantics of the described scenario. A production client also needs timeouts, retries, authorization, and error-handling policies covered by appropriate tests.

## 9. Stub Runner Test Executing End-to-End Serialization

Once the Inventory producer has generated and packaged the stub, Checkout tests can use `@AutoConfigureStubRunner`.

~~~java
package com.example.checkout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.3.0-rc1:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class ReservationSerializationContractTest {

    @Autowired
    ReservationClient reservationClient;

    @Test
    void sendsValidJsonAndDeserializesCreatedResponse() {
        var result = reservationClient.reserve("SKU-123", 2);

        assertThat(result.reservationId()).isEqualTo("R-1001");
        assertThat(result.status()).isEqualTo("RESERVED");
    }
}
~~~

Explanation:

1. The consumer test uses the **production client** and makes a real HTTP call through WireMock.
2. Stub Runner downloads the artifact with classifier `stubs`.
3. The contract-generated mapping enforces conditions for a **valid JSON POST**.
4. If the request serializes incorrectly and fails to match, the test must fail—that is the signal to investigate.
5. The stub response is decoded through Jackson/message converters into `ReservationResponse`.
6. Assertions verify data **after deserialization**, not just WireMock's status.

Port 18081 is a **fixed** example suitable for illustration. Parallel CI should consider dynamic ports and proper lookup/bean wiring. With `LOCAL`, the stub artifact must be installed into the test environment's local repository; when CI runs across separate machines, use a remote repository or an appropriate artifact-sharing mechanism.

## 10. A Green Test Does Not Prove Request Matching Is Strict Enough

Sometimes a mapping is too broad, for example matching only:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations"
  },
  "response": {
    "status": 201,
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED"
    }
  }
}
~~~

If this is the entire matcher, the client could send a bad body or omit headers and still receive 201. The consumer test passes yet **does not genuinely protect serialization**.

How to catch this:

- Open the generated WireMock mapping and confirm required `bodyPatterns`/headers are present.
- Create a **negative test** or send an HTTP request with a wrong type like `quantity:"2"`; that request must not be accepted as a valid contract match if strict types are required.
- Inspect WireMock's request journal/near misses to see what request actually arrived at the server.
- In producer tests, verify the real service's request validation, since stub matchers do not replace every business constraint.

**Separating responsibilities:** SCC protects declared commitments; if a contract does not constrain a field, a consumer test against that stub cannot infer on its own that the field is mandatory.

## 11. Deserialization: JSON Response to Java Types

A successful GET receives:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

A Java DTO should reflect the **actual types of the API**:

~~~java
package com.example.checkout;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record StockResponse(
        @JsonProperty("sku") String sku,
        @JsonProperty("available") Boolean available,
        @JsonProperty("quantity") Integer quantity) {
}
~~~

Why use `Boolean` and `Integer` instead of `boolean`/`int` in the consumer example?

- With primitive `boolean`, a missing or null field may default to `false` depending on Jackson settings, making it **hard for the consumer to distinguish "missing data" from "genuinely out of stock"**.
- With `Boolean`, you can detect `null` and raise a clear contract/protocol error.
- With `Integer`, you can detect a missing `quantity` field instead of silently defaulting to 0.
- `@JsonProperty` explicitly documents the wire field name.
- `@JsonIgnoreProperties(ignoreUnknown=true)` allows **adding fields without breaking the client** under a chosen forward-compatibility policy.

However, **Jackson does not automatically make record fields required just because `@JsonProperty` is present**. Validating `sku`, `available`, and `quantity` must be done after deserialization or via Bean Validation / appropriate strict settings.

## 12. Validating the DTO After Deserialization

An explicit validator function:

~~~java
package com.example.checkout;

public final class StockResponseValidator {

    private StockResponseValidator() {}

    public static StockResponse requireValid(
            StockResponse response, String requestedSku) {

        if (response == null) {
            throw new UpstreamProtocolException(
                    "Inventory 2xx response body is empty");
        }
        if (response.sku() == null
                || !requestedSku.equals(response.sku())) {
            throw new UpstreamProtocolException(
                    "Inventory sku does not match request");
        }
        if (response.available() == null) {
            throw new UpstreamProtocolException(
                    "Inventory field available is missing or null");
        }
        if (response.quantity() == null
                || response.quantity() < 0) {
            throw new UpstreamProtocolException(
                    "Inventory quantity missing or negative");
        }
        if (response.available() != (response.quantity() > 0)) {
            throw new UpstreamProtocolException(
                    "Inventory available/quantity inconsistent");
        }
        return response;
    }
}
~~~

In this example, `UpstreamProtocolException` is a consumer-side exception defined by the project (illustrated in the error-mapping section). The rule `available == (quantity > 0)` is an **illustrative business rule** for the demo API; in systems with reserved stock or backorders, this relationship may differ and must be defined by the real contract.

Why validate after parsing?

| JSON | Can Jackson Build the DTO? | Why Validation Is Still Needed |
|---|---|---|
| All fields present with right types | Yes | Check cross-field invariants |
| Missing `available` | Possibly, value is null | Must not be treated as out of stock |
| `available:null` | Possibly, null | Must not silently default to false |
| `quantity:-1` | Yes | Business-invalid value |
| `sku:"SKU-OTHER"` | Yes | Response does not match request |
| `quantity:"12"` | May be coerced depending on ObjectMapper | If strict type is required, disable coercion or check raw JSON |
| `null` or empty body | May return null/exception | Do not treat 2xx as valid success |

**Never treat HTTP 200 as proof that the payload is valid.** A 200 with a schema-violating body must result in a clear protocol error rather than turning into valid business data.

## 13. Distinguishing Absent, Null, Empty, and Wrong Types

Four JSON states have distinct meanings:

~~~json
{"sku":"SKU-123","available":false,"quantity":0}
~~~

~~~json
{"sku":"SKU-123","available":null,"quantity":0}
~~~

~~~json
{"sku":"SKU-123","quantity":0}
~~~

~~~json
{"sku":"SKU-123","available":"false","quantity":"0"}
~~~

- **`false`**: a meaningful boolean value; must not be treated as missing.
- **`null`**: the field is present without a value.
- **Absent**: the field does not exist in the payload.
- **String `"false"`/`"0"`**: different from JSON boolean/number.

With a Java record containing only `Boolean available`, **absent** and **explicit null** typically both yield `null`; if the API must distinguish them, inspect `JsonNode.has(...)` and `isNull(...)` or use a custom deserializer/validator.

Example checking the raw tree structure:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

JsonNode root = mapper.readTree(rawJson);

if (!root.has("available")) {
    throw new UpstreamProtocolException(
        "Field available is absent");
}
if (root.get("available").isNull()) {
    throw new UpstreamProtocolException(
        "Field available is explicitly null");
}
if (!root.get("available").isBoolean()) {
    throw new UpstreamProtocolException(
        "Field available must be JSON boolean");
}
~~~

This snippet assumes `mapper` is an ObjectMapper and `rawJson` is the received response string; place it inside a method that handles `JsonProcessingException` appropriately.

Consumer tests should include important **negative payload cases** proving the client **does not silently accept** missing/null/wrongly typed fields when the contract requires strictness. You do not need to put every invalid payload into the producer's standard stub artifact; you can use a dedicated WireMock fixture for resilience/protocol negative tests.

## 14. Jackson Property Naming: Only the Exact Wire Name Matches the Contract

The producer may use snake_case:

~~~json
{"sku":"SKU-123","available":true,"quantity_available":12}
~~~

If the consumer DTO has `quantityAvailable` without an annotation or naming strategy, mapping depends on Jackson configuration. You can declare it explicitly:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record StockWireDto(
        String sku,
        Boolean available,
        @JsonProperty("quantity_available")
        Integer quantityAvailable) {
}
~~~

Rules to align on:

- `quantity_available` differs from `quantityAvailable` in JSON; JSON property names are **case- and character-sensitive**.
- `@JsonProperty` on the DTO explicitly documents the contract wire name.
- A `SNAKE_CASE` naming strategy affects **every field**, so assess its impact during refactors.
- If the producer renames a field, treat it as a **potential breaking change**—do not simply change the DTO to make tests green while ignoring other consumers.
- HTTP headers do not follow the same case-sensitivity rules as JSON properties; do not apply one rule to both.

Testing a DTO with an isolated ObjectMapper is helpful but insufficient: verify **RestClient using the same ObjectMapper/message converters** as the real consumer environment, because isolated test config can hide discrepancies.

## 15. Unknown Fields and Forward Compatibility

A common additive change:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12,
  "warehouse": "HCM-01"
}
~~~

If the consumer **does not need** `warehouse`, ignoring unknown fields can improve compatibility when the producer adds metadata. With the DTO:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record StockResponse(
    String sku, Boolean available, Integer quantity) {}
~~~

the consumer can still decode successfully.

However, there are two sides to weigh:

| Policy | Pros | Risks |
|---|---|---|
| **Ignore unknown fields** | Tolerates most additive field changes | May overlook a new field that carries security/semantic significance |
| **Fail on unknown fields** | Catches unexpected schema changes | Can break consumers over a harmless additive field |
| **Allow unknown + validate required/critical fields** | Balances evolvability with correctness | Requires clear validation and test design |

There is no universal policy for every API. For extensible JSON responses, **allowing unknown fields while strictly validating required fields** is a sensible strategy. For sensitive messages/commands, ignoring fields may be unacceptable.

Do not confuse "ignore unknown" with "ignore missing": these two policies serve different purposes.

## 16. Jackson Coercion Can Mask Type Errors

A consumer receiving `{"quantity":"12"}` may still parse it into an `Integer` depending on Jackson's coercion configuration. If the contract mandates a **JSON number**, do not check only the parsed Java object and assume the raw JSON had the right type.

Solutions:

1. Use **JSONPath/type matchers** in contracts and inspect generated mappings/tests.
2. Configure strict ObjectMapper coercion rules for critical types, such as restricting String→Integer or Float→Integer coercion per your Jackson version.
3. Check `JsonNode.isNumber()`, `isBoolean()`, `isTextual()` when exact wire types must be protected.
4. Write consumer negative tests with `quantity:"12"` and `quantity:12.5` and observe real behavior.

For money, timestamps, and enums, coercion can be even riskier than for plain JSON numbers: an empty string treated as null, an unknown enum becoming null, or a fractional number silently rounded can corrupt business logic. Define **domain-appropriate strictness**, not merely whether the library happens to parse it.

## 17. Enums and New Values from the Producer

Suppose the Reservation API returns:

~~~json
{"reservationId":"R-1001","status":"RESERVED"}
~~~

The consumer uses an enum:

~~~java
public enum ReservationStatus {
    RESERVED,
    CONFIRMED,
    CANCELLED
}
~~~

If the producer later adds `EXPIRED`, Jackson may throw an error when deserializing an unknown enum value, depending on configuration. This can be a **breaking change** for older consumers, even though it was "just adding one value."

Design options:

- If the enum is closed per the contract, add tests ensuring the producer **never emits unsupported values**.
- If the producer needs to expand values, the consumer can use an `UNKNOWN` fallback or read a string and handle unknown values per policy.
- Never configure "unknown enum → null" without validation; a null value can push the consumer down the wrong business branch.
- Java enum names, serialized values, and wire formats must be verified via contracts/DTOs; `@JsonProperty` on a field does not automatically rename enum constants.
- Unknown-status handling must be explicit: reject, ignore with logging, retry, or transition to a safe state.

A consumer contract test against an old stub containing only `RESERVED` **does not prove** the consumer is ready for `EXPIRED`. Create a candidate case or dedicated decoding test whenever the producer wants to extend an enum.

## 18. Currency and Timestamps: Preventing Semantic Loss During Deserialization

Two data types that frequently cause silent bugs:

### 18.1. Currency

For example, the Pricing API returns:

~~~json
{"sku":"SKU-123","price":"150000.50","currency":"VND"}
~~~

If `price` is specified as a **decimal string**, a DTO using `BigDecimal` may be converted by Jackson depending on configuration, yet the contract must still specify the **wire type**. If the API specifies a JSON number, e.g.:

~~~json
{"sku":"SKU-123","price":150000.50,"currency":"VND"}
~~~

verify decimals and precision. Avoid `double` for rounding-sensitive monetary calculations. Use `BigDecimal` or integer minor units along with currency/rounding rules.

### 18.2. Dates and Times

Example:

~~~json
{"lastUpdatedAt":"2026-11-24T04:00:00Z"}
~~~

Choose `Instant` or `OffsetDateTime` according to semantics; ISO-8601 format, offset/timezone, and the Jackson Java Time module must be configured properly. A timestamp without an offset, such as `"2026-11-24T11:00:00"`, may be interpreted in different local timezones across environments.

Test both **format** and **semantics** when the consumer depends on time. Never rely on the system default timezone or casual floating-point equality to verify a contract.

## 19. Error Mapping: Status Alone Is Not Enough to Identify Business Intent

HTTP has many failure modes, and consumers usually need to know the exact **business error category**.

| HTTP Status | Illustrative Error Body | Handling Direction in Checkout |
|---|---|---|
| `400` | `INVALID_REQUEST` | Fix input/validation; do not auto-retry |
| `404` | `SKU_NOT_FOUND` | Return business outcome "product does not exist" |
| `409` | `RESERVATION_CONFLICT` | May require retry per idempotency semantics |
| `422` | `INVALID_QUANTITY` | Report rule-violating input; usually no retry |
| `500` | `INTERNAL_ERROR` | Server error; controlled retry possible per policy |
| `503` | `INVENTORY_UNAVAILABLE` | Retry/backoff or fallback within budget |
| No HTTP response | Connection refused/timeout | Transport error; must not be mapped to business 404 |
| HTTP 200 with invalid JSON schema | Not an HTTP error | Protocol/deserialization error; must not count as success |

Do not collapse every error into `RuntimeException("Inventory failed")`: that prevents Checkout from telling a missing product apart from a temporary outage. Conversely, do not invent a separate exception class for every status if business logic does not need it; the goal is to **preserve the semantics needed to make decisions**.

## 20. Contract for a Business 404 in YAML DSL

A dedicated contract for a non-existent SKU:

~~~yaml
description: Inventory reports SKU does not exist
name: inventory_sku_not_found

request:
  method: GET
  url: /api/inventory/SKU-404
  headers:
    Accept: application/json

response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: SKU_NOT_FOUND
    message: SKU does not exist
    traceId: trace-demo-404
~~~

For the temporarily unavailable upstream case:

~~~yaml
description: Inventory temporarily unavailable
name: inventory_unavailable

request:
  method: GET
  url: /api/inventory/SKU-503
  headers:
    Accept: application/json

response:
  status: 503
  headers:
    Content-Type: application/json
  body:
    code: INVENTORY_UNAVAILABLE
    message: Try again later
    traceId: trace-demo-503
~~~

These are **two separate contracts** so the producer/stub knows when to return each response. Special SKUs serve only as **deterministic demo fixtures**; in real producer tests, the base test must set up corresponding data/conditions so the **real producer implementation** returns 404 or 503, rather than building a fake controller that returns sample responses.

On a real producer, a 503 can be triggered by an unavailable gateway/test adapter while the production error handler builds the exact status/body. If the test base itself returns `503 JSON` matching the contract, producer verification will produce a false green.

## 21. Modeling the Error Body and Domain Exceptions

Before writing the client, define the error DTO:

~~~java
package com.example.checkout;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ApiError(
        String code,
        String message,
        String traceId) {
}
~~~

When an HTTP error arrives, the client needs to check:

- What is the status?
- Is the body valid JSON?
- Is `code` among the values understood by the consumer?
- Should `message` be displayed or only logged? Upstream messages may contain unsafe data.
- Should `traceId` be recorded for investigation, and can it be exposed externally under security policy?
- Is the error a **valid producer response** or an **unmatched 404** from the stub?

Several illustrative domain exceptions:

~~~java
package com.example.checkout;

public class InventoryNotFoundException extends RuntimeException {
    public InventoryNotFoundException(String message) {
        super(message);
    }
}

public class InventoryUnavailableException extends RuntimeException {
    public InventoryUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class UpstreamProtocolException extends RuntimeException {
    public UpstreamProtocolException(String message) {
        super(message);
    }

    public UpstreamProtocolException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InventoryTransportException extends RuntimeException {
    public InventoryTransportException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InventoryHttpException extends RuntimeException {
    public InventoryHttpException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

These `public class` declarations belong in **separate Java files** when used in practice—do not put multiple public top-level classes in a single file. You may use package-private classes or nested exceptions depending on project conventions.

## 22. RestClient: GET, Deserialization, and Classifying HTTP Errors

A representative implementation in Checkout:

~~~java
package com.example.checkout;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@Component
public class InventoryClient {

    private final RestClient client;
    private final ObjectMapper mapper;

    public InventoryClient(
            RestClient.Builder builder,
            ObjectMapper mapper,
            @Value("${inventory.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
        this.mapper = mapper;
    }

    public StockResponse getStock(String sku) {
        try {
            StockResponse response = client.get()
                    .uri("/api/inventory/{sku}", sku)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(StockResponse.class);

            return StockResponseValidator.requireValid(response, sku);

        } catch (RestClientResponseException exception) {
            // HTTP 4xx/5xx received from the producer/stub.
            throw translateHttpError(exception);

        } catch (ResourceAccessException exception) {
            // No valid HTTP response received (I/O, connection, timeout).
            throw new InventoryTransportException(
                    "Cannot reach Inventory Service", exception);

        } catch (RestClientException exception) {
            // For example: message converter could not decode the response.
            throw new UpstreamProtocolException(
                    "Cannot decode Inventory HTTP response", exception);
        }
    }

    private RuntimeException translateHttpError(
            RestClientResponseException exception) {

        ApiError error;
        try {
            error = mapper.readValue(
                    exception.getResponseBodyAsByteArray(),
                    ApiError.class);
        } catch (JsonProcessingException cause) {
            return new UpstreamProtocolException(
                    "Inventory error body is not valid ApiError JSON",
                    cause);
        }

        if (error == null || error.code() == null
                || error.code().isBlank()) {
            return new UpstreamProtocolException(
                    "Inventory error response has no code");
        }

        int status = exception.getStatusCode().value();

        if (status == 404 && "SKU_NOT_FOUND".equals(error.code())) {
            return new InventoryNotFoundException(
                    "Inventory SKU does not exist");
        }

        if (status == 503
                && "INVENTORY_UNAVAILABLE".equals(error.code())) {
            return new InventoryUnavailableException(
                    "Inventory temporarily unavailable",
                    exception);
        }

        // Do not treat an arbitrary 404 code as SKU_NOT_FOUND.
        if (status == 404) {
            return new UpstreamProtocolException(
                    "Unexpected Inventory 404 code: " + error.code());
        }

        return new InventoryHttpException(
                "Unexpected Inventory status="
                        + status + ", code=" + error.code(),
                exception);
    }
}
~~~

This is an example of **strict error mapping**. With `RestClient.retrieve()`, default behavior for 4xx/5xx is typically to throw `RestClientResponseException`; the catch blocks above illustrate handling that outcome. If your project configures `defaultStatusHandler`/`onStatus`, inspect and adjust it so you **do not double-handle or swallow errors**.

Key principles:

1. **Transport errors** differ from **HTTP 503 responses**: timeouts/connection refused do not carry a full status+error body.
2. **JSON decode errors** differ from **SKU does not exist**.
3. **A 404 with a different error code** does not automatically become `InventoryNotFoundException`.
4. Only map `503 + INVENTORY_UNAVAILABLE` to the committed unavailable state.
5. Success responses are **validated** to prevent `200` with null fields.
6. Never write raw error bodies containing sensitive data straight into public logs/exceptions.
7. Production requires HTTP timeouts and retry/backoff policies verified separately.

If you prefer mapping errors via `RestClient`'s `onStatus` instead of catching exceptions, you can do so, provided you preserve the status + code + body rules and test against the **real configured client**.

## 23. Consumer Contract Tests for Successful GET and Error Mapping

Assume all three GET contracts have been packaged into the same Inventory stubs JAR:

~~~java
package com.example.checkout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.*;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.3.0-rc1:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryConsumerContractTest {

    @Autowired
    InventoryClient inventory;

    @Test
    void decodesSuccessfulJson() {
        StockResponse stock = inventory.getStock("SKU-123");

        assertThat(stock.sku()).isEqualTo("SKU-123");
        assertThat(stock.available()).isTrue();
        assertThat(stock.quantity()).isEqualTo(12);
    }

    @Test
    void mapsBusiness404ToNotFound() {
        assertThatThrownBy(() -> inventory.getStock("SKU-404"))
                .isInstanceOf(InventoryNotFoundException.class);
    }

    @Test
    void maps503ToUnavailable() {
        assertThatThrownBy(() -> inventory.getStock("SKU-503"))
                .isInstanceOf(InventoryUnavailableException.class);
    }
}
~~~

The `InventoryClient` bean, DTOs, validator, and exceptions illustrated above must be present in the test application context. In CI, the `1.3.0-rc1` stubs JAR must exist in `LOCAL` or switch to `REMOTE` with a configured repository.

**Evidence of a passing test:** the real client sends the right GET/Accept, Stub Runner matches the mapping, Jackson decodes the response, the validator checks invariants, and the client translates error status/bodies into the expected domain exceptions.

If a test merely calls `RestClient` against WireMock and asserts status 404, that is not enough to prove **Checkout's error-mapping logic** works.

## 24. Unmatched WireMock 404 Is Not a Business 404

This is an easy bug to miss. Suppose the consumer sends:

~~~http
GET /api/inventory/WRONG-PATH HTTP/1.1
Accept: application/json
~~~

With no matching mapping, WireMock may return HTTP 404 with a default diagnostic body that is **not `ApiError` JSON**.

If the client is written as:

~~~java
// WRONG: treating all HTTP 404s as SKU_NOT_FOUND.
if (status == 404) {
    throw new InventoryNotFoundException("No stock");
}
~~~

then a **client calling the wrong URL** gets masked as "SKU does not exist," producing a false-green consumer test.

The `InventoryClient` in Section 22 avoids this: it requires a JSON error containing `code: SKU_NOT_FOUND`. If an unmatched WireMock 404 has an unparseable body, the client throws `UpstreamProtocolException`. If the response is JSON with a different code, it also refuses to treat it as a business 404.

Illustrative negative test:

~~~java
@Test
void unmatchedRequestIsNotMappedAsBusinessNotFound() {
    assertThatThrownBy(() -> inventory.getStock("SKU-NOT-STUBBED"))
            .isInstanceOf(UpstreamProtocolException.class);
}
~~~

The exact outcome depends on WireMock's response and loaded mappings; if a valid catch-all mapping exists, adjust the test. **Verify in practice** that negative requests are not accidentally caught by an overly broad mapping.

Another valuable test is sending a request missing a header or targeting a different URL through an experimental client configuration to prove the stub rejects it, whenever headers/paths are real contract constraints.

## 25. Error Mapping Must Consider the Code, Not Just the Status

For business errors, the status and body code usually form a meaningful pair.

| Status | `code` | Sensible Outcome |
|---|---|---|
| `404` | `SKU_NOT_FOUND` | `InventoryNotFoundException` |
| `404` | `ORDER_NOT_FOUND` | Protocol/unexpected error for the demo Inventory API |
| `404` | Unmatched WireMock body | Protocol/unexpected error |
| `503` | `INVENTORY_UNAVAILABLE` | `InventoryUnavailableException` |
| `503` | HTML body from gateway | Protocol/transport-layer diagnostic per policy |
| `200` | Body missing `available` | Validation/protocol failure |
| No HTTP response received | N/A | `InventoryTransportException` |

Some APIs have error responses with no JSON body. If that is a **valid commitment**, the client must design a different mapping rather than forcing `ApiError` on every status. Similarly, 204 No Content is an intentional success response for DELETE and must not be forced into DTO parsing.

**The agreed error schema must live in the contract**, not solely in the consumer's Java code. If the producer changes `code` or `Content-Type`, the consumer needs the new candidate stub so tests catch it.

## 26. Request Serialization and Error Handling for POST

`ReservationClient.reserve` in Section 8 uses `retrieve().body(...)`. If the producer returns `400 INVALID_QUANTITY` or `409 RESERVATION_CONFLICT`, map the error according to business policy.

Example payload when quantity is 0:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-123","quantity":0}
~~~

Contract response:

~~~http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{"code":"INVALID_QUANTITY","message":"quantity must be positive"}
~~~

In the producer's YAML contracts, you can describe a dedicated case:

~~~yaml
description: Quantity must be greater than 0 when reserving stock
name: reservation_invalid_quantity

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 0

response:
  status: 422
  headers:
    Content-Type: application/json
  body:
    code: INVALID_QUANTITY
    message: quantity must be positive
~~~

For a production client, the policy might be:

- `400/422` validation: return a domain validation error, **do not retry**.
- `409` conflict: decide whether to retry with idempotency or require user action.
- `503` unavailable: retry/backoff within budget or open circuit breaker.
- `500` unexpected: log/record metrics safely; never turn into "item out of stock."

The `ReservationClient` snippet in Section 8 covers only the **happy path**; production code requires dedicated error translation and consumer tests for meaningful error statuses.

## 27. Content-Type and Encoding Are Also Part of the Contract

Two HTTP responses with identical body text do not necessarily share the same semantics:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"available":true}
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain

{"available":true}
~~~

Depending on message converters and configuration, a consumer may decode incorrectly or reject the content type. In contracts and consumer tests:

- Check that both request and response `Content-Type` match what was committed.
- `Accept` is the client's preference; the producer might not support every `Accept` variant.
- HTTP header names are generally case-insensitive; JSON fields are case-sensitive.
- `application/json;charset=UTF-8` can be media-type compatible with `application/json`; avoid overly strict string equality if charset is not constrained.
- With non-ASCII text, verify proper encoding so data is not corrupted during serialization/deserialization.
- With gzip or binary/file bodies, add tests for bytes/MIME types if the client relies on them.

Do not test only with internal DTOs while ignoring HTTP headers. A DTO mapping cleanly in a unit test does not prove RestClient sent the right Content-Type or used the expected content converter.

## 28. Testing Reactive WebClient: Same Principles

If Checkout uses `WebClient` instead of `RestClient`, the three data boundaries remain the same—only the asynchronous API differs:

~~~java
Mono<StockResponse> getStock(String sku) {
    return webClient.get()
            .uri("/api/inventory/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .onStatus(
                status -> status.value() == 404,
                response -> response.bodyToMono(ApiError.class)
                    .switchIfEmpty(Mono.error(
                        new UpstreamProtocolException(
                            "404 without ApiError body")))
                    .map(error -> {
                        if ("SKU_NOT_FOUND".equals(error.code())) {
                            return new InventoryNotFoundException(
                                "Inventory SKU does not exist");
                        }
                        return new UpstreamProtocolException(
                            "Unexpected Inventory 404 code");
                    })
            )
            .bodyToMono(StockResponse.class)
            .map(response ->
                StockResponseValidator.requireValid(response, sku));
}
~~~

This is an **illustrative method snippet** that belongs inside a class with `webClient`, Reactor imports, and the corresponding DTO/exceptions. The handler above only handles 404; a production client must also handle 503, 5xx, timeouts, and decode errors.

When testing, you must **subscribe** to the Mono (e.g., `StepVerifier`) so the HTTP request actually executes:

~~~java
StepVerifier.create(inventoryClient.getStock("SKU-123"))
    .assertNext(stock -> assertThat(stock.available()).isTrue())
    .verifyComplete();
~~~

Stub Runner still checks the HTTP request/response contract; `StepVerifier` checks the reactive client's outputs/signals. **Never replace the HTTP client with `Mono.just(StockResponse...)`** and call it a consumer contract test.

Note: `Mono.empty()` and an error signal are different. An empty error body inside `onStatus` must never silently turn into success; define an explicit fallback or contract error.

## 29. Consumer Message Contracts Also Have Serialization and Error Handling

Spring Cloud Contract also supports **message** contracts, not just HTTP. Suppose a producer emits:

~~~json
{
  "eventId": "evt-101",
  "eventType": "InventoryChanged",
  "sku": "SKU-123",
  "available": true
}
~~~

The consumer handler must:

1. Decode the message from bytes/JSON into the schema-matching DTO.
2. Read and validate headers such as `contentType`, `correlationId`, and schema version if required by the contract.
3. Handle new/unknown event types according to the forward-compatibility policy.
4. Distinguish **invalid payload**, **business reject**, and **transient handler failure**.
5. Decide acknowledgement/retry/DLQ behavior per broker and idempotency policy.
6. With message stubs, verify that the consumer handler actually receives and processes the event when Stub Runner triggers the label.

**Important difference:** in messaging, deserialization errors may occur before the listener method is even invoked; there are no HTTP 404/503 statuses to map. You need integration tests for message converters/consumer bindings, retries, and DLQs; Stub Runner does not by itself prove broker topology, partition keys, or at-least-once semantics.

## 30. Test Matrix to Cover

| Test Type | Input | What to Assert |
|---|---|---|
| POST serialization happy path | `sku=SKU-123`, `quantity=2` | WireMock matches request JSON and returns 201 |
| POST wrong field name | `productId` instead of `sku` | Fails to match / producer rejects per contract |
| POST wrong type | `quantity="2"` | Caught if strict types are required |
| POST missing header | Missing `Content-Type` | Fails to match if header is in the contract |
| GET success | `200` with valid body | DTO has right types/values; validator passes |
| GET missing field | No `available` | Client throws protocol error |
| GET explicit null | `available:null` | Client does not treat as false |
| GET wrong type | `quantity:"12"` | Reject coercion if strict JSON number |
| GET extra field | Added `warehouse` | Passes or fails per forward-compatibility policy |
| GET unknown enum | `status:"EXPIRED"` | Fallback/error per policy |
| Contract HTTP 404 | `SKU_NOT_FOUND` | Domain not found |
| Unmatched HTTP 404 | No WireMock mapping | Not treated as business not found |
| Contract HTTP 503 | `INVENTORY_UNAVAILABLE` | Domain unavailable / retry policy |
| HTTP 503 wrong body | HTML or different code | Protocol/unexpected error |
| Connect timeout/refused | No HTTP response | Transport error |
| Unparseable error body | Malformed JSON | Protocol error; not masked as 404 |
| New version | Producer adds/changes schema | Consumer test against candidate stub surfaces result |

This matrix does not mean every case belongs in **official producer contracts**. Requests/responses the producer actually commits to belong in contracts; **deliberately invalid** payloads can be tested with separate WireMock fixtures or deserializer unit tests, keeping clear which tests verify **compatibility** and which verify **fault tolerance**.

## 31. Negative Testing: Proving Your Tests Can Catch Bugs

A test that always passes with a standard body does not prove it catches broken serialization.

Try **intentional mutations in a scratch branch**:

### Mutation A — Rename a Request Field

In `ReservationRequest`, temporarily change `sku` to `productId` while keeping the old contract. If the WireMock matcher inspects the body, the stub must **reject** the request or the consumer test must turn red.

If the test stays green, open the mapping to check for missing body matchers, a catch-all mapping, or a mocked HTTP client in the test.

### Mutation B — Rename a Response Field

Candidate producer renames `available` to `inStock`. If the new candidate stub contains that field, the old consumer DTO must catch the missing `available` via the validator. If the client defaults to `false` and silently treats everything as out of stock, you risk masking a breaking change.

### Mutation C — Change an Error Code

Change `SKU_NOT_FOUND` to `ITEM_UNKNOWN` while keeping HTTP 404. With strict mapping, the consumer must not silently throw `InventoryNotFoundException` as before. This illustrates why **status-only mapping** is insufficient.

### Mutation D — Numeric Response Turned into String

Change `quantity:12` to `quantity:"12"` in a test fixture. If policy requires a strict JSON number, the test must catch it even if Jackson might coerce it. Inspect the raw JSON type or ObjectMapper strictness settings.

### Mutation E — Client Calls Wrong URL

Change `/api/inventory/{sku}` to `/api/stock/{sku}`. The consumer test through Stub Runner must fail due to an unmatched request, never "translate" it into a business 404.

**Always revert mutations** after verification. These edits test your suite's defect-detection capability, not production changes to merge.

## 32. When the Producer Changes a Contract: Who Runs Which Tests?

~~~mermaid
flowchart TD
    A["PR changes producer API, DTO, or error schema"] --> B["Generated producer contract tests"]
    B --> C{"Does producer still satisfy contract?"}
    C -- "No" --> X["BLOCK or re-evaluate contract"]
    C -- "Yes" --> D["Build/publish candidate stubs JAR"]
    D --> E["Consumer tests using real HTTP client"]
    E --> F{"Serialization and deserialization pass?"}
    F -- "No" --> Y["Update consumer or plan migration"]
    F -- "Yes" --> G{"Error mapping and negative tests pass?"}
    G -- "No" --> Y
    G -- "Yes" --> H["Proceed to release gates"]
~~~

Both verification layers complement each other:

- Producer tests verify that producer code **genuinely complies with** the published contract.
- Consumer tests verify that the **current consumer client** accepts the candidate artifact's request/response/error schemas.

If the producer updates code and contracts together, generated producer tests can still pass even if old consumers break. Therefore, **consumers must test against the stub built from the exact candidate commit/version**, not an old stable stub.

If there are multiple consumers, run at least the declared supported consumers or an appropriate compatibility matrix. Never test only the newest consumer while ignoring versions still running in production.

## 33. CI/CD: What Must Be Recorded

In a producer Maven project configured with Spring Cloud Contract:

~~~bash
./mvnw clean verify
~~~

With Gradle using the appropriate plugin:

~~~bash
./gradlew clean test
~~~

In the consumer environment, Stub Runner can fetch stubs from `LOCAL` or `REMOTE` repositories; example coordinates:

~~~text
com.example:inventory-service:1.3.0-rc1:stubs
~~~

CI must verify:

1. Producer **contracts are discovered**, and generated producer tests actually run and pass.
2. The stub JAR contains required request/response mappings, is non-empty, and is not missing body files.
3. Coordinates `group/artifact/version/classifier` match the **candidate commit**; never use unresolved `+`/latest versions.
4. Consumer tests point to the **right Stub Runner port/repository**; never call the production producer unintentionally.
5. Tests use the consumer's **real RestClient/WebClient/Feign**, not a fully mocked HTTP client.
6. Happy-path tests verify both request serialization and response deserialization.
7. Error tests verify the combination **status + code + body** and resulting business exceptions/outcomes.
8. Unmatched WireMock 404s are distinguished from business 404s.
9. Negative tests exist for missing/null/wrong types or critical schema evolution cases.
10. Failure logs identify the contract, artifact version, request path, error code, and failure point without printing secrets or raw tokens.
11. If the producer changes error schemas or enums, supported older consumers are verified against the candidate stub.
12. Separate timeout/retry/resilience tests run when needed rather than assuming instant stub responses cover them.

**Never treat a green build as sufficient** if 0 generated tests ran, the stub is empty, or the consumer still points to an old artifact.

## 34. Troubleshooting: Why Is the Test Red?

| Symptom | Common Cause | How to Investigate |
|---|---|---|
| Stub returns 404 even though SKU-123 is in the contract | Request URL/header/body did not match | Check WireMock mappings and request journal |
| Client throws `InventoryNotFoundException` on wrong URL | Overly broad HTTP 404 mapping | Inspect error body `code` before classifying |
| POST always returns 201 even with a wrong body | Stub request matcher is too loose | Check `bodyPatterns` and negative mutations |
| Jackson reports unrecognized property | DTO/config is strict and producer added a field | Confirm forward-compatibility policy |
| `available` missing yet consumer keeps running | Primitive/default value masks missing field | Use wrappers + validation |
| `quantity:"12"` still parses | Jackson coercion | Inspect raw JSON or configure strict coercion |
| Client fails upon receiving a new enum | Value not in Java enum | Align contract/migration/unknown policy |
| 503 treated as SKU does not exist | Catching broad `RestClientException` and mis-mapping | Separate HTTP status, transport, and protocol errors |
| Error JSON body fails to parse | Producer returned HTML/wrong body or converter mismatch | Inspect status, Content-Type, and safe byte preview |
| Passes locally only | Different stub version or ObjectMapper config | Compare classpath, properties, and exact artifact |
| No generated producer tests | Plugin/contract discovery skipped | Check generation phase, tasks, and test reports |
| Consumer test calls real service | Test base URL not injected properly | Log target host/port; inspect client bean |
| Error response from wrong producer stub | Multi-stub port/URL misrouted | Cross-check producer ID, port, and mappings |
| Schema passes yet business behavior fails | Only asserted DTO decoding, not invariants | Add validator and business tests |
| Tests flake over time | Unstable fixtures/clocks/timeouts | Use fixed fixtures/clocks and explicit wait bounds |

An effective diagnostic chain:

~~~text
Contract source
  -> Generated WireMock mapping
  -> Exact stubs JAR version
  -> Stub Runner URL/port
  -> Raw HTTP request from consumer client
  -> HTTP response status/headers/body
  -> Jackson DTO or parse exception
  -> Domain error mapping
  -> Business assertions
~~~

Reading the right layer prevents "editing the contract" when the real root cause is broken client serialization or a stale stub.

## 35. Lab A — Verifying POST Serialization

1. Create the POST `/api/reservations` contract per Section 5 or 6.
2. Have the Inventory producer generate tests/mappings and package the stubs JAR.
3. Call `ReservationClient.reserve("SKU-123", 2)` from Checkout against Stub Runner.
4. Assert that the HTTP response deserializes into `ReservationResponse("R-1001","RESERVED")`.
5. On a scratch branch, rename the Java field `sku` to `productId`.
6. Re-run the consumer test and confirm it no longer matches when the matcher is strict.
7. Open the generated mapping and explain the difference between the valid and invalid requests.
8. Revert the code and re-run tests.

**Evidence:** Groovy/YAML contract, JSON mapping, test source/report, and unmatched-request log/screenshot (if supported by your setup).

## 36. Lab B — Verifying Deserialization and Schema Evolution

1. Write the GET `SKU-123` contract returning `sku`, `available`, and `quantity`.
2. Use wrapper DTO fields `Boolean`/`Integer` and the validator from Sections 11/12.
3. Run the consumer contract test through Stub Runner and confirm the valid response parses.
4. Create negative fixtures missing `available` and with `available:null`.
5. Create a fixture with `quantity:"12"` and verify your chosen strict wire-type policy.
6. Add an extra `warehouse` field to test forward compatibility.
7. Rename `available` to `inStock` in a producer candidate and observe the old consumer.

**Evidence:** pass/fail table for normal, missing, null, wrong type, extra field, and renamed field.

## 37. Lab C — Classifying Business Errors vs. Transport Errors

1. Create two GET contracts: `SKU-404` returning 404 + `SKU_NOT_FOUND`; `SKU-503` returning 503 + `INVENTORY_UNAVAILABLE`.
2. Use `InventoryClient` and the domain exceptions from Sections 21/22.
3. Run consumer tests and confirm two distinct exception types are thrown.
4. Call an **unmapped URL** to confirm a WireMock unmatched 404 is not classified as business not-found.
5. Use a separate test server/fixture returning 503 + HTML to test protocol error handling.
6. Simulate connection refused or read timeout in a resilience test and confirm it maps to a transport error.
7. Verify retries apply only to appropriate errors and do not cause out-of-policy duplicate requests.

**Evidence:** error mapping matrix, client code, and logs/test reports for HTTP 404, 503, unmatched, malformed body, and transport failures.

## 38. Review Checklist for Consumer Contract Tests

- [ ] Uses the consumer's **production HTTP client/handler**, not mocking the entire client side.
- [ ] Stub artifact comes from producer contracts verified by generated tests.
- [ ] Request serialization verifies method/path/query, Content-Type/Accept, and JSON body.
- [ ] Matchers are strict enough to detect renamed fields or changed types on key fields.
- [ ] Consumer DTO matches wire names rather than relying solely on default naming.
- [ ] Required fields are validated after deserialization; null/missing are not masked by defaults.
- [ ] Number/boolean/enum/time/money types preserve domain semantics.
- [ ] Unknown fields follow an explicit forward-compatibility policy rather than arbitrary strict/lenient choices.
- [ ] 2xx responses missing a body or violating the schema are treated as protocol errors when the contract requires data.
- [ ] Error mapping uses **status + code + body**, not status alone.
- [ ] Business 404s and WireMock unmatched 404s are never conflated.
- [ ] Transport timeouts/connection refused are distinct from HTTP 503 with a valid body.
- [ ] Negative tests cover field renames, wrong types, null/absent, malformed JSON, and unknown enums where relevant.
- [ ] Consumer tests cover both happy paths and meaningful business error cases.
- [ ] CI uses the **exact candidate stubs version** and records artifact/commit metadata.
- [ ] Generated producer tests actually run, the stub JAR contains mappings, and consumer tests never point to production.
- [ ] No tokens, PII, or real data appear in fixtures or stub artifacts.
- [ ] Breaking changes have migration/versioning plans and are tested against older consumers.

## 39. Self-Check Questions

**1. Why is a unit test calling `objectMapper.writeValueAsString(request)` not enough to prove consumer serialization is right?**

Because it does not test whether the real HTTP client sends the right method, path, headers, body converters, and active ObjectMapper settings. Stub Runner tests must call the **production client**.

**2. Why can a DTO using `boolean available` be risky?**

Because a missing or null field may deserialize to the primitive default depending on configuration, causing the consumer to mistake "missing data" for `false`. Using `Boolean` plus validation catches it.

**3. Why is HTTP status 404 alone insufficient to throw `InventoryNotFoundException`?**

Because a 404 can also come from an unmatched WireMock request or another upstream error. You must inspect the agreed error schema and `code`, such as `SKU_NOT_FOUND`.

**4. Is a producer adding `warehouse` to JSON always a breaking change?**

Not necessarily. For consumers that ignore unknown fields, it is usually compatible. However, if a client is strict or the new field changes semantics/security, evaluate and test it.

**5. Does Jackson parsing `quantity:"12"` into an Integer prove the wire contract is valid?**

No. That may be the result of coercion; if a JSON number is required, inspect the raw type or configure strictness and add negative tests.

**6. Are HTTP 503 and connection refused the same error?**

No. HTTP 503 is a response carrying a status (and possibly an error body) sent by upstream; connection refused has no valid HTTP response. Clients need distinct retry/diagnostic policies.

**7. Why must CI use candidate stubs instead of a stable artifact?**

Because the producer may have changed its contract (field names, enums, error codes). Only the candidate stub from the new commit reflects changes that older consumers must test against to catch breaking changes.

**8. Why should consumer tests check domain exceptions instead of only inspecting raw responses?**

Because the real requirement is that **consumer code handles errors correctly**, not merely that the network returned a status. Domain exceptions/outcomes are the interface consumed by the rest of Checkout.

## 40. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, stubs, and consumer testing.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML, requests/responses, and matchers.
- [Spring Cloud Contract – Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): loading candidate stubs and starting HTTP mappings.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `WebClient`, response handling.
- [Spring Boot – Jackson Customization](https://docs.spring.io/spring-boot/reference/features/json.html): configuring JSON mappers in Boot applications.
- [Jackson Databind Documentation](https://github.com/FasterXML/jackson-databind): JSON data binding, records, coercion, and unknown properties.
- [WireMock – Request Matching](https://wiremock.org/docs/request-matching/): HTTP methods, headers, queries, JSON body matchers, and the request journal.
- [WireMock – Stubbing](https://wiremock.org/docs/stubbing/): response status/headers/body and unmatched requests.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` for reactive consumers.

**Version note:** `RestClient`, Jackson annotations, Spring Cloud Contract DSL, Stub Runner, WireMock mappings, and coercion/error-handling defaults depend on exact versions. Use a compatible Spring Boot–Spring Cloud Release Train–Spring Cloud Contract combination, consult the corresponding docs, and inspect actual generated mappings and test reports. These code snippets are educational examples; **they have not been compiled or subjected to dedicated Content QA in this authoring step**.

---

**Key takeaway:** Consumer contract testing does not stop at receiving HTTP 200. Tests must exercise the **real production client** to prove **Java DTO → valid HTTP request (serialization)**, **HTTP response → valid DTO (deserialization)**, and **HTTP/transport/protocol errors → proper business handling (error mapping)**. Combining these checks with **producer generated tests** and **exact-commit candidate stubs** in CI establishes a reliable foundation for detecting incompatible API changes.
