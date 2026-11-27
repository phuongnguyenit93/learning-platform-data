# Wrong Content-Type, Serialization, or Body Data

## Lesson Objectives

In **Spring Cloud Contract**, producer and consumer agree on HTTP or messaging behavior via **Groovy/YAML DSL**. Contract Verifier uses the contracts to generate producer tests; mappings are packaged into a stub artifact for the consumer to use via **Stub Runner**. A very common failure group in this workflow is **wrong `Content-Type`, data serialized/deserialized differently than expected, or an actual body that fails to match the contract**.

On the surface these errors look alike: generated producer tests FAIL, consumer tests receive HTTP 400/404/415/406, Jackson throws an exception, WireMock finds no matching mapping, or an assertion reports a diff between two JSON payloads. However, **the root cause and fix in each case differ completely**. Rushing to alter the DSL or relax matchers before identifying the failing layer can turn CI green while stripping away API compatibility protection.

This lesson, **“Wrong Content-Type, Serialization, or Body Data”**, in the **Troubleshooting** chapter helps you:

1. Distinguish **`Content-Type`** from **`Accept`**, request/response headers, content negotiation failures, and body parsing errors.
2. Diagnose HTTP 400, 404, 406, 415, 422, and 500 errors using **evidence**, rather than guessing from status codes alone.
3. Understand the impact of YAML/Groovy DSL, HTTP message converters, Jackson, JSON numbers/nulls/arrays/strings, and charsets.
4. Separate failures in **generated producer tests**, **stub mappings/WireMock**, and **consumer deserialization**.
5. Build a workflow comparing **actual request**, **contract**, **mapping**, **actual response**, logs, and test reports.
6. Review message contracts and payload formats across brokers/binders.
7. Fix the root cause, keep matchers strict enough, and add tests to prevent regressions.

## 1. Opening Scenario: One API, Three Different Failures

Suppose Order Service exposes:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":"CUS-1001","amount":125000}
~~~

Expected response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":"ORD-1001","status":"CREATED"}
~~~

Several scenarios:

- The consumer sends `Content-Type: text/plain` while the body still looks like JSON: the producer may return **415 Unsupported Media Type**.
- The consumer sends `Content-Type: application/json` while the body is `"{\"customerId\":\"CUS-1001\"}"` — a **JSON string containing JSON text** rather than a JSON object: the producer may return **400 Bad Request** because its DTO expects an object.
- The consumer sends a valid request yet Stub Runner returns **404**: WireMock may **find no matching mapping** due to URL, header, or body mismatch; this is not the same as a business 404 `ORDER_NOT_FOUND`.
- The producer returns `Content-Type: application/json` while the actual body is non-JSON text: generated tests or the consumer may fail **JSON parsing** even though status 201 is right.

Thus, the first step is to **determine what was actually transmitted on the wire**, rather than looking at a single `AssertionError` line.

## 2. Four Layers to Separate During Diagnosis

~~~mermaid
flowchart TD
    A["Contract Groovy/YAML"] --> B["Generated producer test"]
    B --> C["Producer HTTP/message implementation"]
    A --> D["Converted stub mapping"]
    D --> E["WireMock / Stub Runner"]
    F["Consumer request/client"] --> E
    E --> G["Stub response"]
    G --> H["Consumer deserializer + assertions"]
    C --> I["Producer response + generated assertions"]
    I --> J{"Where did the mismatch occur?"}
    H --> J
~~~

| Layer | Question | Evidence |
| --- | --- | --- |
| **Contract source** | What method, headers, body, types, and response does the DSL require? | Groovy/YAML at the exact revision |
| **Producer verification** | What request did the generated test send, and what did the producer return? | Generated source, producer logs, test reports |
| **Stub runtime** | Does the generated mapping match the consumer's request? | Stub JAR, WireMock mappings, and request journal |
| **Consumer runtime** | What bytes/headers did the client send/receive, and how did it deserialize and handle them? | HTTP client logs, exceptions, assertions |

Never conclude “Contract Verifier is broken” just because **a consumer test failed**. Producer tests may PASS and mappings may be right, while the consumer sent `text/plain` or picked the wrong stub artifact.

Conversely, a stub returning a sample response accurately does not prove the **producer implementation** serializes per the contract. You must inspect generated producer tests.

## 3. How Does `Content-Type` Differ from `Accept`?

This is the most fundamental rule:

- **`Content-Type`** describes the **media type of the body being sent**.
- **`Accept`** describes the **media types the requester wants to receive in the response**.

Example:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":"CUS-1001","amount":125000}
~~~

`Content-Type: application/json` states the request body is JSON. `Accept: application/json` states the consumer wants a JSON response.

Response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":"ORD-1001","status":"CREATED"}
~~~

Response `Content-Type` is chosen and declared by the producer. Do not confuse it with request `Accept`.

### Scenario Table

| Request Content-Type | Request Accept | What to Check |
| --- | --- | --- |
| `application/json` | `application/json` | JSON request and JSON response per contract |
| `text/plain` | `application/json` | Does the producer accept plain-text requests? Likely 415 |
| `application/json` | `application/xml` | Can the producer emit XML? Likely 406 if not |
| Omitted (bodyless request) | `application/json` | Is a request body actually needed? |
| `application/json;charset=UTF-8` | `application/json` | Are media-type parameters and charset handled properly? |
| `application/vnd.example.order+json` | `application/json` | Do producer/message converters support the vendor media type? |

**HTTP header names are case-insensitive**; however, media-type values must be parsed according to media-type syntax rather than arbitrary string equality. An exact string matcher in tests can be overly strict when only a `charset` parameter differs.

### Common Fixing Mistake

Do not alter a response contract from `application/json` to `text/plain` just because the producer currently emits the wrong header. Identify the **agreed interface** and fix the producer/serializer if the contract is right.

## 4. Read HTTP Statuses Purposefully, Do Not Guess Causes

| Status or Symptom | Common Meaning | Next Thing to Investigate |
| --- | --- | --- |
| **400 Bad Request** | Unparseable body, failed validation, or invalid request | Raw bytes, JSON syntax, DTO binding, validation/error body |
| **404 Not Found** | Missing route, missing resource, or WireMock unmatched | Producer route vs stub mapping vs business 404 |
| **406 Not Acceptable** | Cannot produce a response matching `Accept`/negotiation | Response converters, `produces`, client `Accept` |
| **415 Unsupported Media Type** | Server does not support request `Content-Type` | `consumes`, request converter, actual media type |
| **422 Unprocessable Content** | App may use this status for semantic errors | API conventions, validation, and error schema |
| **500 Internal Server Error** | Producer exception or processing failure | Stack trace, serializer, mapper, exception handler |
| **200/201 yet test FAILS** | Wrong body/header or overly strict matcher | Actual response, JSONPath, types, property names |
| **Stub Runner returns 404** | No mapping matched or scenario/resource defined to return 404 | Request journal and mapping, separate unmatched |
| **Consumer parse exception** | Body incompatible with consumer DTO/schema | Raw response + `Content-Type` + DTO/`ObjectMapper` settings |

Statuses are clues, **not one-to-one rules**. For instance, a producer might map a deserialization failure to 422 instead of 400. Check the application's actual error handling and contracts.

## 5. A Consistent HTTP YAML Contract for Headers and Body

Example **HTTP contract** for creating an order:

~~~yaml
description: "Create an order from a JSON request"
name: create_order
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    customerId: CUS-1001
    amount: 125000
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: CREATED
~~~

In this example:

- `request.headers.Content-Type` requires a JSON request body.
- `request.headers.Accept` describes the response media type requested by the client.
- `request.body` is a **JSON object** with string `customerId` and numeric `amount`.
- `response.headers.Content-Type` declares a JSON response.
- `response.body` is an object with two fields.

This shows **syntax for a common SCC feature set**; configuring matchers, optional headers, or serialization for a specific version must be checked against your plugin release.

### Do Not Put Everything in a String

Wrong approach if you want a JSON object:

~~~yaml
request:
  body: '{"customerId":"CUS-1001","amount":125000}'
~~~

Depending on context and how the parser reads the DSL, this can be interpreted as **a string containing JSON text**, unlike the YAML mapping in the standard example. Under some configs, the plugin can parse raw JSON strings; the key point is to **verify generated output** rather than assuming from appearance.

To avoid ambiguity when learning, use **YAML mappings/sequences** for JSON objects/arrays, then inspect generated tests and stub mappings.

## 6. How Does Serialization Differ from Deserialization?

**Serialization** converts objects/domain data into bytes/strings for transmission. **Deserialization** reads JSON/XML/text from requests/responses back into objects.

~~~mermaid
flowchart LR
    A["Consumer DTO"] --> B["Serialize request JSON"]
    B --> C["HTTP bytes + Content-Type"]
    C --> D["Producer deserialize DTO"]
    D --> E["Producer business logic"]
    E --> F["Serialize response JSON"]
    F --> G["HTTP response bytes + Content-Type"]
    G --> H["Consumer deserialize DTO"]
    H --> I["Consumer business assertions"]
~~~

Errors can occur at **any arrow**. For example:

- Consumer `StringHttpMessageConverter` writes plain text instead of Jackson serializing a DTO.
- Producer `@RequestBody` cannot deserialize a string into a Java bean.
- Producer DTO getters expose different property names than the contract.
- Jackson uses `snake_case` while the contract expects `camelCase`.
- Consumer enum rejects a new value.

**Matching status 200 is not enough**: if the body fails to parse, the consumer still breaks. In contract tests, matching data types and headers must reflect what the consumer truly uses.

## 7. The “JSON Object Encoded as a JSON String” Bug

Two payloads look similar yet are completely different:

**JSON object:**

~~~json
{
  "customerId": "CUS-1001",
  "amount": 125000
}
~~~

**JSON string containing JSON text:**

~~~json
"{\"customerId\":\"CUS-1001\",\"amount\":125000}"
~~~

In the second payload, the root is a **string**, not an object. If the producer receives:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<OrderCreated> create(
        @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

deserialization will fail because `CreateOrderRequest` expects a JSON object.

### Common Client Cause

A client manually calls `objectMapper.writeValueAsString(data)` and passes the resulting string into an API that **serializes again**, creating double encoding.

**How to fix:** pick one clear serialization boundary:

- Either the HTTP client accepts a **DTO object** and serializes it to JSON itself.
- Or the HTTP client accepts **raw JSON bytes/strings** per its defined API and does not re-encode.

Never combine both unintentionally.

### Inspect Actual Wire Bytes

Do not rely solely on logs like `CreateOrderRequest(customerId=...)`. Logging a Java object does not prove the client sent a JSON object. Inspect the **wire-level request body** and `Content-Type` using safe/redacted logging.

## 8. JSON Number, String, Boolean, and Null Are Not Equivalent

A YAML mapping distinguishes:

~~~yaml
body:
  amount: 125000
  active: true
  status: PAID
  discount: null
~~~

Corresponding JSON response:

~~~json
{
  "amount": 125000,
  "active": true,
  "status": "PAID",
  "discount": null
}
~~~

Clear mismatch:

~~~json
{
  "amount": "125000",
  "active": "true",
  "status": "PAID",
  "discount": "null"
}
~~~

In the second JSON, `amount`, `active`, and `discount` are all strings. Jackson can **coerce** certain values depending on settings, but never rely on coercion to mask a breaking schema change.

| Field | Expected JSON | Common Wrong Data |
| --- | --- | --- |
| `amount` | number | string `"125000"` |
| `active` | boolean | string `"true"` |
| `discount` | JSON null | string `"null"` |
| `items` | array | object or string containing JSON |
| `customer` | object | array or escaped JSON string |

### YAML Traps with Data Types

Certain values in YAML carry special syntax depending on parser/schema. To be explicit:

- Quote **IDs** that look numeric, e.g., `"00123"`.
- Quote values containing `:` or special characters that might be parsed as syntax.
- Leave numbers unquoted when you want a JSON number.
- Leave `true`/`false` unquoted when you want a boolean.
- Leave `null` unquoted when you want JSON null.
- Check your parser version/YAML schema for special forms (dates, leading zeros, boolean-like words).

**Rule:** the DSL description must produce the **exact data types the consumer actually needs**, not merely look clean on disk.

## 9. Null, Missing Field, and Empty Value Differ

A consumer may distinguish:

~~~json
{"middleName":null}
~~~

from:

~~~json
{}
~~~

and:

~~~json
{"middleName":""}
~~~

These three responses express three distinct states:

1. Field exists with value **null**.
2. Field **does not exist**.
3. Field exists with an **empty** string.

For JSON arrays, also distinguish:

~~~json
{"items":[]}
~~~

from:

~~~json
{"items":null}
~~~

and:

~~~json
{}
~~~

In Java, Jackson settings like `@JsonInclude(Include.NON_NULL)` or `NON_EMPTY` can omit fields from output. If the contract or consumer requires the field to be present, review annotations, serialization policy, and generated assertions.

**Do not replace `null` with missing** just to make tests PASS; that can change semantics the consumer uses to tell “unknown” apart from “not applicable.”

## 10. JSON Object Order, Array Order, and Whitespace

For JSON objects, property ordering generally **carries no JSON data meaning**, whereas **array** element ordering does. For example:

~~~json
{"id":"ORD-1001","status":"PAID"}
~~~

and:

~~~json
{"status":"PAID","id":"ORD-1001"}
~~~

represent the same two-field object structure even though the raw strings differ.

By contrast, two arrays:

~~~json
{"items":["A","B"]}
~~~

and:

~~~json
{"items":["B","A"]}
~~~

are not automatically equivalent if the API guarantees ordering.

### Choosing the Right Comparison

- When checking **JSON semantics**, prefer parsed JSON/JSONPath/structural assertions.
- When the API guarantees array ordering, retain ordering assertions.
- If the API does not guarantee array order, use appropriate matchers/assertions to avoid flaky tests.
- Compare **raw bytes** only when the contract requires exact bytes/text (such as canonical JSON signatures or binary payloads).
- Whitespace, indentation, and property order should not cause false breaking changes when not part of the interface.

An `assertEquals(expectedJsonString, actualJsonString)` test can FAIL due to formatting alone. Do not “fix” it by deleting all matchers; compare at the right semantic level.

## 11. `Content-Type` with Charset Parameters and Vendor Media Types

Some HTTP responses include:

~~~http
Content-Type: application/json;charset=UTF-8
~~~

instead of:

~~~http
Content-Type: application/json
~~~

Both have media type `application/json`, yet the raw header strings differ. A test using exact string equality can FAIL even when the client parses JSON fine.

**How to investigate:**

1. Determine whether the contract truly commits to an **exact header string** or just the media type.
2. Inspect raw response headers.
3. Check the producer's response converters and `produces`.
4. Use media-type-aware matchers/APIs if the consumer simply needs JSON.
5. If a specific charset is required, write an explicit criterion and test it.

For vendor types:

~~~http
Content-Type: application/vnd.example.order+json
~~~

do not assume every framework parses it like `application/json`. Many converters support `+json` suffixes, yet exact behavior depends on client/server libraries and config. Verify with the real consumer.

### Watch Character Encoding

A body with Vietnamese text:

~~~json
{"message":"Đơn hàng đã được tạo"}
~~~

If UTF-8 bytes are decoded with another encoding, output becomes garbled. Check:

- Request/response bytes.
- Charset/media-type metadata.
- HTTP client/server encoding settings.
- Source file and resource encoding in the build.
- Presence of a BOM or double encoding/decoding.

Never alter a contract to match garbled text just to turn CI green.

## 12. Spring MVC and HTTP Message Converters

In Spring MVC, a controller may declare:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<OrderCreated> create(
        @RequestBody CreateOrderRequest body) {

    OrderCreated created = service.create(body);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Conceptually:

- `consumes` controls which request media types the endpoint accepts.
- `produces` controls which response media type the endpoint can emit.
- `@RequestBody` needs a matching `HttpMessageConverter` to deserialize the body into the DTO.
- Jackson JSON converters are normally auto-configured by Spring Boot when proper dependencies are present.
- Exception handlers can translate parse/validation errors into conventional error responses.

### A Real-World Pitfall

The contract sends:

~~~http
Content-Type: application/json
~~~

yet the test client or application context lacks a matching converter. Generated tests can FAIL differently from running the full app due to different dependencies/configuration.

**Investigate:** effective Spring test context, MVC/WebFlux stack, converter registration, DTO getters/setters/constructors, Jackson modules, and test mode.

Do not assume “adding a Jackson dependency” is always the fix; sometimes the producer response genuinely emitted the wrong media type or the contract specified the wrong format.

## 13. DTO Serialization: Field Names, Enums, Dates, and `BigDecimal`

A Java DTO may look like:

~~~java
public record OrderResponse(
    String id,
    String paymentStatus,
    BigDecimal amount
) {}
~~~

By default in JSON, the field becomes `paymentStatus`. Yet Jackson settings or annotations can change it:

~~~java
public record OrderResponse(
    String id,
    @JsonProperty("payment_status") String paymentStatus,
    BigDecimal amount
) {}
~~~

Now the response contains `payment_status` instead of `paymentStatus`. If the contract requires `camelCase`, generated producer tests will FAIL.

### Sources of Divergence to Review

| Source of Divergence | Example | Impact |
| --- | --- | --- |
| `@JsonProperty` | `payment_status` | Field name changes |
| Global naming strategy | `snake_case` vs `camelCase` | Multiple fields change at once |
| `@JsonIgnore` | Field omitted | Consumer never sees data |
| `@JsonInclude` | Null/empty omitted | Missing instead of null |
| Enum representation | `"PAID"` vs `"paid"` | Consumer enum parsing fails |
| Date formatting | ISO string vs numeric timestamp | Type/format compatibility |
| Timezone | UTC vs local timezone | Wrong time semantics |
| Decimal representation | number vs string, scale | Different parsing/math |
| Default values | Injects default for missing field | Masks contract drift |
| Custom serializer | Output differs from standard DTO fields | Can break schema unexpectedly |

For monetary values, prioritize checking **data type, unit, precision/rounding, and value** per agreement. Do not treat `125000.00` vs `125000` as breaking if the API only guarantees numeric value; conversely, if scale is part of the published format, test it accurately.

## 14. Groovy DSL Contracts: Is Body an Object or a String?

Groovy HTTP contract example:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Create order with JSON body"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }
        body(
            customerId: "CUS-1001",
            amount: 125000
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(
            id: "ORD-1001",
            status: "CREATED"
        )
    }
}
~~~

In Groovy DSL, a map-style body expresses JSON structure. However:

- Do not confuse `body(...)` with a Java method serializing a DTO.
- Do not put quotes around numbers when the contract requires a JSON number.
- Avoid unintentional string interpolation that causes Groovy to substitute values while parsing the DSL.
- Do not write arbitrary Groovy code to synthesize production data or call external services during builds.
- When using `bodyFromFile(...)`, verify file encoding, location, and request/response content type per plugin version.

**Groovy DSL and YAML DSL are not guaranteed to serialize identically if you inadvertently describe two different types.** Compare generated mappings/tests, not just source file appearance.

## 15. Request Matchers and Response Matchers Must Be Understood Separately

Spring Cloud Contract builds two branches of evidence:

- **Generated producer test:** sends the request to the producer and checks the response against the contract.
- **Consumer stub mapping:** WireMock matches an incoming request against rules and returns the stub response.

A request matcher can require:

- Exact HTTP method.
- Matching URL path/query.
- Matching `Content-Type` or `Accept` header.
- JSON body with matching fields/values.
- Cookies or other declared constraints.

If the consumer sends **semantically identical JSON** while a matcher uses **raw body equality**, differing whitespace or key ordering can cause WireMock not to match. For JSON, prefer JSON structural matching when appropriate.

### Sign of Unmatched Request vs. Wrong Response

If WireMock finds no matching mapping, it returns an unmatched 404. In that case, do not edit the response body contract yet. Investigate **request matching** first.

If the request matches properly and WireMock returns an unexpected response, inspect the **mapping artifact/version**, response files, headers, and scenario state.

## 16. WireMock 404 Differs from Business 404

Suppose the producer has a business contract:

~~~yaml
description: "Order not found"
name: get_missing_order
request:
  method: GET
  url: /api/orders/ORD-NOT-FOUND
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: ORDER_NOT_FOUND
    message: "Order does not exist"
~~~

A **business 404** must return the agreed error code/body. Yet if the consumer mistakenly calls `/api/order/ORD-NOT-FOUND` (missing `s`), WireMock returns an **unmatched** 404 without that schema.

Investigate:

1. Read the actual request URL/method sent by the consumer.
2. Check which stub mappings are loaded.
3. If WireMock admin API/request journal is enabled and accessible in tests, inspect **unmatched requests**.
4. Compare headers and body matchers.
5. Verify Stub Runner is running the right artifact version.

**Never conclude a 404 contract PASSES** solely because the consumer received HTTP status 404. Verify both **body and matched mapping**.

## 17. Reproducible Request Debugging with cURL

Sample request:

~~~bash
curl --verbose \
  --request POST \
  "http://localhost:8090/api/orders" \
  --header "Content-Type: application/json" \
  --header "Accept: application/json" \
  --data-binary '{"customerId":"CUS-1001","amount":125000}'
~~~

Observe:

- Did it connect to the right host/port?
- Are request method and path right?
- Which `Content-Type` and `Accept` headers were sent?
- Is the body root an object or a string?
- What are the response status and `Content-Type`?
- Does the response body parse as valid JSON?

**Use synthetic data**; never put real authorization tokens into terminal history or logs. For complex payloads, place the body in a test file and use `--data-binary @request.json` so shell quoting does not alter bytes.

### Controlled A/B Comparison Test

Send two requests differing by only one variable:

**A — valid request:**

~~~http
Content-Type: application/json

{"customerId":"CUS-1001","amount":125000}
~~~

**B — wrong media type request:**

~~~http
Content-Type: text/plain

{"customerId":"CUS-1001","amount":125000}
~~~

If A matches the stub/producer while B does not, content type is a key variable. If neither matches, inspect URL, body matchers, and artifact rather than blaming the header immediately.

**Changing one variable at a time** isolates failures far better than editing path, headers, body, and DTO all at once and not knowing what made the test pass.

## 18. Inspect Raw Body and Parsed JSON

Many bugs become obvious only when viewing both the **raw representation** and the **parsed structure**.

Example raw body:

~~~text
"{\"id\":\"ORD-1001\",\"status\":\"PAID\"}"
~~~

At a glance, seeing `id` and `status` makes it look like a JSON object. Yet a JSON parser reveals the root type is a string.

Helpful check:

~~~bash
# On a sample response file containing no secrets:
python -m json.tool response.json
~~~

This command **only illustrates syntax checking**—it is not a requirement to run Python in your current workflow. It also accepts valid JSON strings, so check the root type rather than parse success alone.

When using a JSON viewer, check:

- Whether root is object, array, string, number, boolean, or null.
- Whether field names have exact casing.
- Whether null/omitted fields diverge from the contract.
- Whether arrays preserve expected order.
- Whether numeric values were converted to strings.

**Never paste real responses containing PII into public JSON formatters** just for debugging. Prefer local/approved tooling.

## 19. Generated Producer Test FAILS: Read the Error at the Exact Failure Point

A generated test can fail at several points:

~~~mermaid
flowchart TD
    A["Generated producer test"] --> B{"HTTP/message test client setup OK?"}
    B -->|No| X["Base class / test mode / context"]
    B -->|Yes| C{"Did the producer receive the request?"}
    C -->|No| Y["Method/path/Content-Type/Accept"]
    C -->|Yes| D{"Did the body deserialize?"}
    D -->|No| Z["JSON syntax/types/DTO/converter"]
    D -->|Yes| E{"Did business logic complete?"}
    E -->|No| W["Fixture/validation/dependency"]
    E -->|Yes| F{"Was the response serialized properly?"}
    F -->|No| V["Jackson/headers/DTO/date/enum"]
    F -->|Yes| G{"Do assertions match contract?"}
    G -->|No| U["Contract semantics/matcher"]
    G -->|Yes| H["Producer contract test PASS"]
~~~

### Practical Investigation Steps

1. Read the **first failure** in the test report, not just the final summary.
2. Confirm whether the request reached the producer.
3. Record actual status, response headers, and body **after redacting sensitive data**.
4. Determine whether the error is request parsing, response serialization, or matcher mismatch.
5. Inspect the test base class, Spring MVC/WebFlux test mode, and dependencies.
6. Compare the contract against the public behavior you intend to preserve.
7. Fix the producer or agreed contract, then rerun tests.

**Do not mechanically update contracts to match current output.** If producer output breaks consumers, the contract FAILURE is the signal protecting you.

## 20. MockMvc, WebTestClient, and Live HTTP Can Behave Differently

Spring Cloud Contract supports multiple HTTP test modes depending on producer stack and plugin settings. Test layers include:

- **MockMvc/RestAssuredMockMvc** for Spring MVC.
- **WebTestClient/RestAssuredWebTestClient** for WebFlux.
- **Live HTTP server/RestAssured** against an open port.

Mechanisms can differ in:

- Configured message converters/codecs.
- Active filter/security chains.
- Handler routing and exception handling.
- Content negotiation.
- Encoding.
- Serialization of streaming responses.

For example, **WebFlux** may use different codecs or streaming `Flux`. A test mocking a static JSON object does not prove a real server handles SSE/NDJSON/chunked streaming properly in all cases.

### Do Not Mix Test Modes

If generated tests use RestAssuredMockMvc while the base class configures only WebTestClient, tests can fail before body parsing even begins. That is a **test wiring error**, not a producer response body bug.

Read generated sources, plugin test mode, and base class to verify client setup.

## 21. Using `bodyFromFile` or External Response Files

Contracts with large JSON payloads may extract the body into a file:

~~~text
src/test/resources/contracts/
  orders/
    get_paid_order.groovy
    get_paid_order_response.json
~~~

JSON file contents:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID",
  "items": [
    {"sku": "SKU-1", "quantity": 2}
  ]
}
~~~

When using a DSL helper like `bodyFromFile(...)` in supporting versions, verify:

1. Does the resolver locate the file relative to the **contract directory** or configured root?
2. Is the file packaged inside the stub artifact?
3. Is `Content-Type` set to `application/json`?
4. Is the encoding UTF-8?
5. Does the file contain a JSON object or an escaped JSON string?
6. Do line endings/BOM alter parser/client behavior?
7. Does it contain any sensitive production data?

For binary bodies, do not disguise raw bytes as a JSON string without specifying encoding. Use the proper file/binary stub mechanism for your payload type and tool version.

## 22. Stub Runner Picking the Wrong Artifact Can Look Like a Body Bug

Suppose producer `2.5.0` returns:

~~~json
{
  "id": "ORD-1001",
  "paymentStatus": "PAID"
}
~~~

while the consumer still references:

~~~text
com.example.orders:order-service:2.4.0:stubs
~~~

The older stub returns:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

Consumer tests may FAIL because the body differs from expectations, or even PASS because they only know the old schema. **Neither proves anything about producer 2.5.0.**

Investigate:

- Stub Runner ID: `groupId:artifactId:version:classifier[:port]`.
- Maven local/remote repositories and caches.
- Which stub JAR was actually downloaded.
- Mappings and response files inside that JAR.
- Artifact checksums/producer verification build when needed.

**Do not rush to alter the consumer's serializer** if the body difference comes from loading the wrong old artifact.

## 23. JSONPath Matchers: Avoid Being Too Loose or Too Strict

JSONPath matchers help when responses hold dynamic values:

- `$.id` needs a valid format.
- `$.status` needs enum `PAID`.
- `$.items[0].sku` needs a specific SKU.
- `$.amount` needs numeric type.

Yet there are pitfalls:

| Matcher | Risk |
| --- | --- |
| `byType` on every field | Can miss changed enum semantics |
| `.*` regex | Accepts empty or malformed strings |
| Checking only that body contains `"PAID"` | Can match debug text instead of status |
| Typo in JSONPath never checked | Assertion fails to protect the intended field |
| Exact equality on dynamic timestamps | Flaky unless clock is fixed |
| Raw JSON string equality | Fails on non-contract whitespace/key order |
| Dropping matchers when tests FAIL | Weakens contract, hides regressions |

**Principle:** pin exact values/semantics the consumer genuinely relies on; use bounded flexible matchers for dynamic values that do not need fixed constants.

### Verify with a Negative Case

Create a controlled failure case in tests:

~~~json
{
  "id": "INVALID",
  "status": "PENDING"
}
~~~

If generated producer tests still PASS despite the contract requiring an ID format and `status = PAID`, the matcher may be wrong or the test is not really running. Inspect generated source, test reports, and matcher settings.

## 24. Distinguish Request Body Matchers from Response Body Matchers

In CDC, separate two responsibilities:

1. **Stub request matching:** Does the consumer request match the contract so WireMock returns the response?
2. **Producer response assertion:** Does the producer implementation return a response matching the contract?

For example, the consumer sends:

~~~json
{"customerId":"CUS-1001","amount":"125000"}
~~~

while the contract request specifies:

~~~json
{"customerId":"CUS-1001","amount":125000}
~~~

If request body matching checks JSON types, Stub Runner will not match and will return an unmatched 404. The bug is in **consumer request serialization**.

If generated producer tests send a valid request yet the producer emits `amount` as a string in its response, the bug is in **producer response serialization**.

**Never edit a response matcher to fix an unmatched request.** Separate request side and response side first.

## 25. Message Contracts: `Content-Type` Affects Payloads Too

Spring Cloud Contract supports message-based contracts, such as:

~~~yaml
description: "Paid order emits ORDER_PAID"
label: order_paid
input:
  triggeredBy: markTestOrderAsPaid()
outputMessage:
  sentTo: orders.events
  headers:
    contentType: application/json
  body:
    eventType: ORDER_PAID
    orderId: ORD-1001
    amount: 125000
~~~

In this example:

- `triggeredBy` is the method triggering the producer in the test environment.
- `outputMessage.sentTo` describes the logical destination.
- Message `headers.contentType` is a **message header**, not automatically identical to HTTP `Content-Type`.
- Message `body` may be converted into bytes, `String`, or `Map` by the serializer/binder depending on the adapter.

### Common Mismatches

| Mismatch | Symptom |
| --- | --- |
| Header says JSON, payload is Java `toString()` | Consumer cannot parse it |
| Kafka serializer emits bytes differing from JSON contract | Assertions/deserializer fail |
| Event body `amount` is string instead of number | Consumer schema validation fails |
| `contentType` header missing | Consumer converter chooses different handling |
| Producer emits a String containing escaped JSON | Consumer receives a JSON string instead of object |
| Wrong destination/event type | Message never received, mistaken for body bug |

**Do not assume an in-memory test binder and a production broker use the same serializer.** When a contract must verify wire bytes, add integration tests with the real serializer/broker.

### Do Not Equate Message Bodies with HTTP JSON Bodies

A message represented as a `Map` in the test framework may be serialized into bytes when published over Kafka/RabbitMQ. Identify the **conversion layers** of your actual binder, framework, and serializer.

If consumers consume raw bytes, a passing `Map` body in generated producer tests alone does not prove full wire-format compatibility.

## 26. When a Proxy/Gateway Alters Content-Type

When a consumer calls a producer through a gateway:

~~~mermaid
flowchart LR
    C["Consumer"] --> G["Gateway / reverse proxy"]
    G --> P["Producer"]
    P --> G
    G --> C
~~~

A gateway may:

- Rewrite `Content-Type` or `Accept`.
- Add or change `charset`.
- Compress responses with gzip.
- Convert errors into HTML/plain text.
- Rewrite paths so requests hit the wrong endpoint.
- Return a 502/503 proxy error page as `text/html` instead of a JSON API body.

Thus, when a consumer logs `Unexpected character '<'` while parsing JSON, the actual response may be an **HTML error page from a proxy**, not a body produced by the producer's serializer.

**How to investigate:** inspect status, response headers, a safe body prefix, correlation/request IDs, and the client's network path. Do not assume a JSON parse exception automatically means a Jackson bug in the producer.

## 27. Step-by-Step Diagnostic Workflow

A repeatable workflow for any scenario:

~~~mermaid
flowchart TD
    A["Test FAILS / consumer error"] --> B["Identify layer: producer or consumer/stub?"]
    B --> C["Record method, path, request headers, body type"]
    C --> D["Read actual status + response headers/body"]
    D --> E{"Did request reach right listener/mapping?"}
    E -->|No| F["Fix routing/Stub Runner artifact/request matcher"]
    E -->|Yes| G{"Are Content-Type/Accept compatible?"}
    G -->|No| H["Fix client/server media type/negotiation"]
    G -->|Yes| I{"Does body parse to right type?"}
    I -->|No| J["Fix serializer/DTO/codec/encoding"]
    I -->|Yes| K{"Does body match contract semantics?"}
    K -->|No| L["Review producer behavior/contract/matcher"]
    K -->|Yes| M["Check fixtures, test mode, and assertions"]
    F --> N["Rerun producer + consumer tests"]
    H --> N
    J --> N
    L --> N
    M --> N
~~~

### Seven Priority Actions

1. **Freeze evidence:** record producer commit, contract revision, stub GAV/version, and test run.
2. **Classify the error:** 415/406, JSON parser, unmatched mapping, response matcher, or business validation.
3. **Compare raw request/response:** method, URL, headers, body root type, and bytes/encoding.
4. **Inspect generated test/mapping:** did the DSL emit what you expected?
5. **Inspect converters/DTOs:** Spring MVC/WebFlux, Jackson, serializers, annotations, and profiles.
6. **Fix the right layer:** client request, producer response, agreed contract, stub mapping, or infrastructure.
7. **Run regression:** producer generated tests, new artifact, and consumer tests against the new stub.

### Why Not Change Everything at Once?

If you simultaneously change `Content-Type`, the response DTO, JSONPath matchers, and the Stub Runner version, a passing test won't tell you which change fixed it. Better to change **one significant variable at a time**, save minimal inputs/outputs, and use negative tests to validate your hypothesis.

## 28. Minimum Evidence Checklist for a Bug Report

A bug report can follow this template:

~~~text
Producer service/version/commit:
Contract path + revision:
Producer generated test ID + report:
Consumer service/version/commit:
Stub artifact GAV + classifier + checksum:
Stub Runner mode/repository/HTTP port:
Request method and full path:
Request Content-Type:
Request Accept:
Request body JSON root type:
Actual HTTP status:
Actual response Content-Type:
Actual response body (synthetic/redacted):
Expected contract status/body:
Exception/root cause:
Observed unmatched request or mapping ID:
Minimal reproduction:
Fix layer and rerun evidence:
~~~

Not every field applies to message contracts or integration tests that do not use Stub Runner; mark non-applicable fields as `N/A`.

**Never include tokens, cookies, passwords, private keys, PII payloads, or confidential links in bug reports.** Use synthetic data and redacted logs to reproduce failures.

## 29. Symptom and Action Reference Table

| Test Symptom | Priority Hypothesis | Evidence to Collect | Remediation Direction |
| --- | --- | --- | --- |
| Producer returns 415 | Request `Content-Type` not in `consumes` | Actual request header, controller mapping | Fix client/contract or supported media type |
| Producer returns 406 | `Accept` incompatible with `produces` | Actual `Accept`, converter list | Fix content negotiation per API |
| Producer returns 400 on JSON | Bad body syntax/type/DTO binding | Raw request body, Jackson cause | Fix JSON/DTO/serializer |
| Producer returns 500 serializing response | Getter/custom serializer/date module error | Stack trace, DTO config | Fix producer serialization |
| WireMock unmatched 404 | URL/header/body matcher mismatch | Request journal, mapping | Fix request or agreed contract/mapping |
| Consumer sees HTML instead of JSON | Proxy/gateway error body | Status, `Content-Type`, upstream logs | Fix gateway/backend routing or error handling |
| JSONPath `$.status` missing | Field renamed/omitted/null | Actual response JSON + Jackson config | Review breaking change |
| `amount` is string instead of number | Double encoding/type coercion | JSON root/field types | Fix serializer, preserve schema |
| Test FAILS due to object key order | Raw string equality | Parsed JSON semantic diff | Compare JSON structurally |
| Test FAILS due to array order | API may guarantee ordering | Contract + business requirements | Pick matching assertion |
| Message consumer fails to parse | Body converter/serializer/header mismatch | Raw message bytes, headers, binder config | Fix message format and versioning |
| Passes locally, fails in CI | Different profiles/artifacts/encoding/versions | Build metadata, stub checksum | Lock env and artifacts, reproduce |

## 30. Practice Exercises

### Exercise A — Distinguish `Content-Type` from `Accept`

Consumer sends `Content-Type: text/plain`, `Accept: application/json`, and a JSON object body to an endpoint that only accepts JSON.

**Task:** Which error is likely? What should be checked and fixed first?

**Hint:** check 415, actual `consumes`, and request `Content-Type`; do not rush to edit the response contract.

### Exercise B — Double-Encoded JSON

Contract request expects a JSON object, yet the consumer sends:

~~~json
"{\"customerId\":\"CUS-1001\",\"amount\":125000}"
~~~

**Task:** What is the root type? Why can the producer DTO fail to parse it? How do you fix the client?

**Hint:** it is a JSON string; serialize only once at the right HTTP client layer.

### Exercise C — Body Number Changed to String

Producer returns `{"amount":"125000"}` while the contract requires a number.

**Task:** Could this be a breaking change? Why shouldn't you relax the matcher to `any string`?

**Hint:** the consumer schema may require a numeric type; fix serialization/DTO per agreement or run a reviewed migration.

### Exercise D — Business 404 or Unmatched?

Consumer calls `GET /api/order/ORD-NOT-FOUND` (missing `s`) and receives 404; contract specifies `GET /api/orders/ORD-NOT-FOUND` returns JSON code `ORDER_NOT_FOUND`.

**Task:** Does receiving 404 prove the business contract PASSES?

**Hint:** no; inspect the URL and mapping, then verify the matching error body.

### Exercise E — Charset and Unicode Text

Response `{"message":"Đơn hàng đã được tạo"}` appears garbled in consumer logs.

**Task:** List where to check encoding.

**Hint:** wire bytes, media-type charset, client decoder, resource encoding, and double encoding; never change the expected body to garbled text.

### Exercise F — JSON `null` or Missing?

Contract requires field `discount: null`, while the producer uses `NON_NULL` and omits the field.

**Task:** Could this be a behavior change? What should be reviewed?

**Hint:** absent differs from `null`; check consumer logic and the contract.

### Exercise G — Strict Deserialization

Producer adds field `paymentStatus` to its response while an older consumer rejects unknown properties.

**Task:** Why can an additive change still break a consumer? Which test must run?

**Hint:** test the older consumer with the new stub and the old parser configuration.

### Exercise H — Wrong Stub Version

Producer 2.5.0 changed the schema, while consumer tests still run against stub 2.4.0 and PASS.

**Task:** Can you conclude the new producer is compatible? What evidence is needed?

**Hint:** no; run the consumer against stub 2.5.0 generated from the producer-verified contract revision.

### Exercise I — Message Header Differs from HTTP Header

A message contract declares `contentType: application/json`, yet the consumer receives bytes produced by a different serializer.

**Task:** Which layers must be checked?

**Hint:** binder/message converter, actual serializer, raw bytes, and consumer deserializer; a message header does not automatically create JSON bytes.

### Exercise J — JSON Object Order

Responses `{"id":"ORD-1001","status":"PAID"}` and `{"status":"PAID","id":"ORD-1001"}` are compared as raw strings and FAIL.

**Task:** Choose a better assertion strategy and state when byte-level equality is required.

**Hint:** structural JSON equality/JSONPath, unless the protocol requires canonical bytes.

### Exercise K — Wrong Producer Test Mode

Generated tests use RestAssuredMockMvc, yet the base class configures only WebTestClient.

**Task:** Is the bug necessarily in `Content-Type`? What must be checked?

**Hint:** check test mode, generated source, and base class wiring first.

### Exercise L — Proxy Returns HTML

Consumer logs show a JSON parse error on leading character `<`; response status is 502 and `Content-Type` is `text/html`.

**Task:** Should you investigate the producer serializer or the proxy/route first?

**Hint:** 502 HTML points to a gateway; check upstream errors before editing JSON mappers.

## 31. Checklist Before Marking Resolved

### Accurate Symptom Identification

- [ ] Distinguished request `Content-Type` from request `Accept`.
- [ ] Read actual response status, `Content-Type`, and body.
- [ ] Pinpointed whether the failure is in producer, stub mapping, or consumer deserialization.
- [ ] Distinguished WireMock unmatched 404 from business 404.
- [ ] Logs use synthetic/redacted data and expose no secrets.

### Body and Serialization

- [ ] Request body is a JSON object/array/string matching the contract type.
- [ ] No double-encoded JSON.
- [ ] JSON numbers, booleans, nulls, and strings preserve semantics.
- [ ] Missing fields, explicit nulls, and empty values reviewed.
- [ ] JSON object order/whitespace is not treated as a false breaking change.
- [ ] Array order is checked per API guarantees.
- [ ] Charset and encoding verified for Unicode data.
- [ ] Jackson DTO/annotations/naming/enum/date/decimal modules aligned.
- [ ] Content negotiation and `consumes`/`produces` match the agreed interface.
- [ ] `bodyFromFile` packaged and read with the right encoding/path.

### Spring Cloud Contract and Stub Runner

- [ ] Groovy/YAML contracts discovered at the exact revision.
- [ ] Generated producer tests contain expected requests and assertions.
- [ ] MockMvc/WebTestClient/live HTTP test mode matches the base class.
- [ ] Generated tests actually run and PASS without unintended skips.
- [ ] Stub JAR contains the right mappings and response files.
- [ ] Stub Runner uses the right GAV/classifier/version and repository.
- [ ] Real consumer requests match the stub on method/path/headers/body.
- [ ] Consumer tests assert business logic and body fields, not just HTTP status.
- [ ] Message serialization/binder/header mismatches checked for message contracts.
- [ ] Contract matchers were not relaxed solely to make CI green.

### Fix Evidence

- [ ] Minimal reproduction captured before fixing.
- [ ] Primary failing layer identified and change made deliberately.
- [ ] Regression test added for the content-type/serialization/body bug.
- [ ] Producer verification and consumer tests ran with the new artifact when applicable.
- [ ] Contract revision, producer commit, stub checksum, and test reports recorded.
- [ ] No compatibility claims made outside tested versions/scenarios.

## Conclusion

When facing a **`Content-Type`, serialization, or body** error, the hardest part is not reading JSON, but **identifying which layer introduced the mismatch**: client sending the wrong request, producer failing to deserialize, producer serializing a response differently from the contract, generated test using an unsuitable matcher, WireMock failing to match the request, or consumer parsing the response with the wrong type.

An effective diagnostic process starts with the **actual method/path/headers/body**, separates `Content-Type` from `Accept`, checks **raw bytes alongside JSON structure**, reads generated producer tests and mappings, and verifies the **stub artifact version** the consumer actually loads. Fixing the right layer and rerunning producer–consumer tests preserves Spring Cloud Contract's ability to catch incompatible API changes.

**Remember:** *A matching HTTP status does not guarantee a valid body; valid JSON does not guarantee the right schema; a WireMock 404 is not necessarily a business 404; and a consumer test PASSING against an old stub proves nothing about a new producer.*
