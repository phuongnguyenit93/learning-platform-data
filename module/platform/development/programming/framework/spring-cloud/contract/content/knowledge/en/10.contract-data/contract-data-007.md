# Boundary Data: Empty, Missing, Null, and Limit Values

## 1. Why Must Contracts Test Boundary Data?

An API may work fine with sample requests yet break the consumer when encountering a missing field, a `null` value, an empty string, or a number right outside the allowed range. That is **public communication behavior**: the consumer must know what to send and which status code, response body, and error code to expect.

In **Spring Cloud Contract (SCC)**, producer and consumer agree on HTTP or messaging behavior using **Groovy DSL/YAML DSL**. SCC generates tests to verify the producer implementation and builds stubs for the consumer to use with **Stub Runner**. Adding those checks to CI catches incompatible API changes before release.

Boundary data requires answering very specific questions:

- Is a **missing** field treated the same as a field present with `null`?
- Are `""`, whitespace-only strings, `[]` arrays, and `{}` objects valid?
- Are `0` and `false` valid values, or will they be mistaken for “absent”?
- Are exact min/max values accepted or rejected?
- When input is invalid, does the consumer receive `400`, `422`, what error shape, and what error code?

This lesson shows how to design a **scenario matrix**, express it in contracts, verify both sides, and work around matcher/stub limitations. The running example is a product quote calculation API.

### Learning Outcomes

You will be able to:

1. Classify **missing**, `null`, empty, blank, and boundary-adjacent values.
2. Author HTTP contracts for both **success** and **error** boundary cases.
3. Write Groovy/YAML DSL for JSON requests/responses, including absent fields and explicit null fields.
4. Understand the limitations of JSONPath matchers, Bean Validation, and serializers.
5. Run generated producer tests, inspect stub mappings, and test consumers against candidate stubs.
6. Apply the same mindset to arrays, messages, and PATCH APIs.

## 2. Six States to Distinguish

Suppose a request has a `couponCode` property. The following forms are **not equivalent**:

~~~json
{"sku":"SKU-123","quantity":1}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":null}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":""}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":"   "}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":"SAVE10"}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":123}
~~~

| State | Characteristics | Possible API rule |
|---|---|---|
| **Missing (absent)** | JSON omits key `couponCode` | Accept and apply default |
| **Explicit null** | Key is present with JSON `null` | Reject because client sent null |
| **Empty string** | `""`, length 0 | Reject |
| **Blank string** | `"   "`, has characters but no meaningful content | Reject |
| **Non-blank string** | `"SAVE10"` | Accept after validation |
| **Wrong type** | `123` is a JSON number | Reject because contract requires string |

Other easily confused pairs:

| Value | Differs from | Why |
|---|---|---|
| `0` | `null` and absent | Zero is still a number |
| `false` | absent | Boolean false carries business meaning |
| `[]` | `null` | Array exists with zero elements |
| `{}` | `null` | Object exists with zero properties |
| `"0"` | `0` | String differs from JSON number |
| `"null"` | `null` | Four-character string differs from JSON null |
| `" "` | `""` | Whitespace string differs from empty string |

**There is no universal rule** forcing every API to treat absent and null the same or differently. What matters is an agreed policy captured in contracts and protected by tests.

## 3. Context: Quote Calculation API

**Pricing Service** is the producer of the endpoint:

~~~http
POST /api/quotes HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "sku": "SKU-123",
  "quantity": 1,
  "couponCode": "SAVE10"
}
~~~

**Checkout Service** is the consumer calling this endpoint.

We **assume** the following business rules for this exercise:

| Property | Rule |
|---|---|
| `sku` | Required, must be a non-blank string |
| `quantity` | Required, must be a JSON integer from **1 to 100**, inclusive |
| Missing `couponCode` | Valid; no discount applied |
| `couponCode: null` | `400` error, code `COUPON_NULL` |
| `couponCode: ""` or blank | `400` error, code `COUPON_BLANK` |
| Valid `couponCode` | String code accepted by the system |
| Missing `quantity` | `400` error, code `QUANTITY_REQUIRED` |
| `quantity: null` | `400` error, code `QUANTITY_NULL` |
| `quantity` out of range | `400` error, code `QUANTITY_OUT_OF_RANGE` |
| `quantity` wrong type | `400` error, code `QUANTITY_INVALID_TYPE` |

The error codes in this table are an **illustrative design**, not the default behavior of Spring MVC or Spring Cloud Contract. Real projects may choose `422` or group errors under one public code; the contract must reflect that actual decision.

Success response without a coupon:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "quantity": 1,
  "discountApplied": false,
  "totalVnd": 150000
}
~~~

Error response for explicit null:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "COUPON_NULL",
  "message": "couponCode must not be null"
}
~~~

For the consumer, **HTTP status and a stable error code** usually matter far more than prose message text, which may change or be localized.

## 4. Boundary Matrix for Quantity 1..100

A typical scenario set:

| `quantity` value | Test group | Expectation |
|---|---|---|
| Key omitted | Missing required | `400 QUANTITY_REQUIRED` |
| `null` | Explicit null | `400 QUANTITY_NULL` |
| `"1"` | Wrong type: string | `400 QUANTITY_INVALID_TYPE` |
| `1.5` | Decimal instead of integer | `400 QUANTITY_INVALID_TYPE` |
| `-1` | Negative value | `400 QUANTITY_OUT_OF_RANGE` |
| `0` | **min − 1** | `400 QUANTITY_OUT_OF_RANGE` |
| `1` | **min** | `200` |
| `2` | **min + 1** | `200` |
| `99` | **max − 1** | `200` |
| `100` | **max** | `200` |
| `101` | **max + 1** | `400 QUANTITY_OUT_OF_RANGE` |
| `2147483648` | Exceeds 32-bit signed Java integer | `400 QUANTITY_INVALID_TYPE` per example convention |

The **min−1, min, min+1, max−1, max, max+1** pattern catches `<` vs. `<=` or `>` vs. `>=` comparison bugs. There is no need to test every integer from 1 to 100; focus on **equivalence classes** and boundaries where decisions flip.

Beyond quantity, also consider: overly long coupon codes, whitespace-only SKUs, arrays with 0 or too many items, negative prices, wrong boolean types, Unicode characters, and numbers exceeding data-type limits.

## 5. YAML DSL: How Is a Missing Field Written?

YAML contracts use `request.body` to represent the payload. In YAML, **omitting a key** means the field is absent in the sample body; writing `key: null` or `key: ~` means null, and `key: ''` means an empty string.

Example file `src/test/resources/contracts/quotes/quote-without-coupon.yml`:

~~~yaml
description: Omitting couponCode calculates quote without discount
name: quote_without_coupon

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 1

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 1
    discountApplied: false
    totalVnd: 150000
~~~

Note: `request.body` **does not contain** `couponCode`. This is the “no coupon code sent” case, distinct from sending `couponCode: null`.

Fields that YAML could infer as non-strings—such as all-digit strings or boolean-like keywords—should be quoted when the API requires a **string**. By contrast, `quantity: 1` is intentionally a JSON number.

## 6. YAML DSL: Explicit Null, Empty, and Blank

### 6.1. Explicit null

Dedicated contract file:

~~~yaml
description: Reject explicit null couponCode
name: reject_null_coupon

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 1
    couponCode: null

response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: COUPON_NULL
    message: couponCode must not be null
~~~

### 6.2. Empty string

~~~yaml
description: Reject empty string couponCode
name: reject_empty_coupon

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 1
    couponCode: ''

response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: COUPON_BLANK
~~~

### 6.3. Whitespace-only string

~~~yaml
description: Reject whitespace-only couponCode
name: reject_blank_coupon

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 1
    couponCode: '   '

response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: COUPON_BLANK
~~~

The quotes in `couponCode: ''` and `couponCode: '   '` are critical. Writing `couponCode:` with nothing after the colon is typically parsed as **null** by YAML parsers.

All three contracts describe the **same URL and method**, differing only in request body and outcome. When generating stubs, verify that the mappings distinguish each case cleanly—especially **absent** vs. **null**. Do not assume every WireMock JSON matching mode automatically distinguishes them strictly.

## 7. YAML DSL: At-Limit and Over-Limit Values

**At max** case, still valid:

~~~yaml
description: quantity equal to 100 is still accepted
name: quote_at_max_quantity

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 100

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 100
    discountApplied: false
    totalVnd: 15000000
~~~

**Max + 1** case, rejected:

~~~yaml
description: quantity 101 exceeds limit
name: reject_quantity_101

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 101

response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: QUANTITY_OUT_OF_RANGE
~~~

Similarly, include `quantity: 0` (error) and `quantity: 1` (success). The monetary amounts in these examples assume a unit price of 150,000 VND; if prices are computed dynamically, write assertions around committed behavior rather than hardcoding unstable totals.

**A single contract with `quantity: 50` does not verify whether 1 and 100 are inclusive bounds.**

## 8. Groovy DSL: Comparing Missing, Null, and Empty

The Groovy DSL uses maps to represent JSON bodies. Explicit null example:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Reject null couponCode'

    request {
        method POST()
        url '/api/quotes'
        headers {
            contentType(applicationJson())
        }
        body([
            sku: 'SKU-123',
            quantity: 1,
            couponCode: null
        ])
    }

    response {
        status BAD_REQUEST()
        headers {
            contentType(applicationJson())
        }
        body(code: 'COUPON_NULL')
    }
}
~~~

Correspondingly, when a field is **missing**, omit the key from the map:

~~~groovy
body([
    sku: 'SKU-123',
    quantity: 1
    // No couponCode key
])
~~~

Present but empty values:

~~~groovy
body([
    sku: 'SKU-123',
    quantity: 1,
    couponCode: '',   // Empty string
    tags: [],         // Empty array
    metadata: [:]     // Empty object
])
~~~

These are **mutually independent illustrative snippets**, not a recommendation to cram contradictory cases into one contract. When translating between Groovy and YAML, re-run generated tests and inspect stub mappings, because conceptually similar syntax does not guarantee identical matcher semantics across versions.

## 9. A Missing Field Differs from a Missing HTTP Body

Two situations often get conflated:

~~~http
POST /api/quotes HTTP/1.1
Content-Type: application/json

{"sku":"SKU-123","quantity":1}
~~~

The request above **has a JSON body**; it merely omits the `couponCode` field.

By contrast:

~~~http
POST /api/quotes HTTP/1.1
Content-Length: 0
~~~

The second request **has no body at all**. Another case is a body containing the JSON literal `null`:

~~~http
POST /api/quotes HTTP/1.1
Content-Type: application/json

null
~~~

Spring MVC may handle these at different layers: reading the HTTP body, converting JSON, binding the DTO, and then running field validation. If the API expects a JSON object, define the public responses for an absent body, JSON `null`, and an object missing fields; do not assume one contract covers all three.

## 10. Java DTOs Can Lose Absent/Null Distinction

Consider this DTO:

~~~java
public record QuoteRequest(
        String sku,
        Integer quantity,
        String couponCode) {
}
~~~

With standard Jackson settings, **both** of the following bodies can yield `couponCode() == null`:

~~~json
{"sku":"SKU-123","quantity":1}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":null}
~~~

If the contract specifies two different outcomes, inspecting the DTO alone is insufficient. You must track **field presence** before or during deserialization.

One illustrative approach using `JsonNode`:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

public String classifyCoupon(JsonNode body) {
    if (!body.has("couponCode")) {
        return "ABSENT";
    }

    JsonNode coupon = body.get("couponCode");

    if (coupon.isNull()) {
        return "NULL";
    }
    if (!coupon.isTextual()) {
        return "WRONG_TYPE";
    }
    if (coupon.asText().isEmpty()) {
        return "EMPTY";
    }
    if (coupon.asText().isBlank()) {
        return "BLANK";
    }

    return "PRESENT";
}
~~~

In Jackson, `has("couponCode")` checks whether the key exists even if its value is JSON null; `hasNonNull(...)` requires both presence and a non-null value. Depending on data types and binding, you can use custom deserializers or state wrappers, though avoid complicating DTOs if the contract does not need to distinguish absent from null.

## 11. Bean Validation and Its Limitations

Jakarta Bean Validation is widely used in Spring Boot:

| Constraint | Primary check |
|---|---|
| `@NotNull` | Value is not null |
| `@NotEmpty` | String, collection, map, or array is non-null and non-empty |
| `@NotBlank` | String has non-whitespace content per validator rules |
| `@Size(min, max)` | Length or element count bounds |
| `@Min(1)` / `@Max(100)` | Numeric bounds |
| `@DecimalMin` / `@DecimalMax` | Decimal bounds, inclusive/exclusive |
| `@Digits` | Maximum integral and fractional digits |

Example DTO:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record SimpleQuoteRequest(
        @NotBlank String sku,
        @NotNull @Min(1) @Max(100) Integer quantity,
        String couponCode) {
}
~~~

Key caveats:

- `@NotNull` **does not distinguish absent from explicit null** once both map to Java null.
- `@NotEmpty` accepts `"   "` because its length is non-zero; for text content, `@NotBlank` is usually intended.
- `@Size` and many other constraints generally accept null by default, so required fields need explicit null constraints.
- Spring MVC validation must be triggered via `@Valid`/`@Validated` in the right place with the validation dependency present.
- `@Min` and `@Max` do not handle JSON parse errors, integer overflow, or wrong types that fail before Bean Validation runs.

Using `Integer` for `quantity` distinguishes **`0`** from **`null`**; a primitive `int` can blur default zero with missing values depending on binder settings. Yet `Integer` still does not solve **absent vs. explicit null**.

## 12. Matchers Do Not Automatically Replace Boundary Data

SCC provides `response.matchers` and `request.matchers`. Example response type matcher:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    quantity: 100
    totalVnd: 15000000
  matchers:
    body:
      - path: $.quantity
        type: by_type
      - path: $.totalVnd
        type: by_type
~~~

**`by_type` only checks type**; it does not enforce that `quantity` is within 1..100. A response with `quantity: 101` still passes the type check.

When you need to assert an **exact** value at a boundary, you can write:

~~~yaml
response:
  status: 200
  body:
    status: READY
    quantity: 100
    quoteId: Q-1001
  matchers:
    body:
      - path: $.status
        type: by_equality
      - path: $.quantity
        type: by_equality
      - path: $.quoteId
        type: by_regex
        value: '^Q-[0-9]+$'
~~~

Here `quoteId` is dynamic per regex; status and quantity must equal the sample. However, **response matchers only prove what is returned in the described scenario**. To verify the producer rejects `quantity: 101`, you need a dedicated contract or supplemental test for that request.

Similarly, some stub JSON body matching modes may match partially or allow extra fields. **Do not infer** that a sample request body omitting `couponCode` will automatically reject requests containing `couponCode: null`. Inspect the **generated mappings** and run competing cases directly against Stub Runner.

## 13. Numeric Data: Integers, Decimals, and Overflow

The following JSON payloads may represent the same mathematical number while **differing in type/representation**:

~~~json
{"quantity":1}
~~~

~~~json
{"quantity":1.0}
~~~

~~~json
{"quantity":"1"}
~~~

If the contract specifies a **JSON integer**, a consumer sending `"1"` may be rejected even if the framework supports coercion. Decide explicitly whether **implicit type coercion is permitted or forbidden**.

Very large numbers:

~~~json
{"quantity":2147483648}
~~~

exceed Java's signed 32-bit `int` range. If the parser/mapper throws an exception before entering the controller, the response may differ from a `@Max(100)` validation error. Contracts should specify which **public error code** the consumer receives rather than leaking internal exception class names.

For money, test boundaries such as `0`, negative amounts, payment caps, overly long numbers, and excess decimal digits. In Java, use `BigDecimal` for exact monetary math; contracts should state **units, decimal scale, and rounding rules**.

## 14. Strings and Unicode: “32 Characters” Is Not Always Obvious

Suppose coupon codes must be **1 to 32 characters** long and not solely whitespace.

The matrix should include:

| Input | Purpose |
|---|---|
| `""` | Length 0 |
| `" "` | Whitespace |
| `"A"` | Minimum length |
| Valid 32-character string | At max |
| 33-character string | Max + 1 |
| `" SAVE10 "` | Trimming rule / whether leading or trailing spaces are allowed |
| Vietnamese text or emojis | Verify Unicode length convention |
| String with newline or tab | Verify control-character handling |

Note: Java's `String.length()` counts **UTF-16 code units**, which is not necessarily the number of Unicode code points or user-perceived characters. An accented character can be represented as a single precomposed code point or a combining sequence. If the API promises a count of **UTF-8 bytes**, **code points**, or **grapheme clusters**, specify the measurement unit and test that exact boundary.

Never silently trim or normalize input if consumers depend on current handling. Whenever normalization changes field semantics, document it in the contract or API specification.

## 15. Arrays, Objects, and False Values

These three bodies represent three distinct states:

~~~json
{"items":[]}
~~~

~~~json
{"items":null}
~~~

~~~json
{}
~~~

For an API requiring at least one item, you might specify:

| State | Illustrative expectation |
|---|---|
| Missing `items` | `400 ITEMS_REQUIRED` |
| `items: null` | `400 ITEMS_NULL` |
| `items: []` | `400 ITEMS_EMPTY` |
| One item | Success |
| At item count limit | Success |
| One item over limit | Out-of-range error |

Likewise, `metadata: {}` is an empty object, distinct from `metadata: null`. In a response, `items: []` is a different commitment from omitting `items`; a consumer can safely iterate an empty list yet crash on null.

For booleans:

~~~json
{"discountApplied":false}
~~~

`false` is a meaningful value; consumers must not confuse it with a missing field. When serializing/deserializing DTOs, check primitive `boolean` vs. wrapper `Boolean`, default values, and null-omission policies.

## 16. Special Meaning of Absent/Null in PATCH

With `application/merge-patch+json` under **RFC 7396**, on an object resource, these two patches carry different meanings:

~~~json
{}
~~~

No keys are requested to change.

~~~json
{"nickname":null}
~~~

Requests **removing the `nickname` property** from the target object per JSON Merge Patch semantics.

Do not generalize this rule to every HTTP PATCH. With `application/json-patch+json` under **RFC 6902**, the request is a list of `add`, `remove`, `replace`, etc. operations, while PATCH using `application/json` may follow custom semantics.

If an API uses Merge Patch, **absence and null are part of the update protocol**: you need contracts for “unchanged”, “delete”, and “set value”, not only routine success requests.

## 17. Testing the Producer When Frameworks Strip Distinctions

SCC-generated tests must be **executed against the real producer**, including controllers, validators, and exception handlers. Special cases like absent vs. null may need supplemental integration tests to verify framework binding and public responses.

Illustrative `MockMvc` example (assuming the controller implements the error codes from Section 3):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteBoundaryTest {
    @Autowired MockMvc mvc;

    @Test
    void absentCouponIsAccepted() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"SKU-123","quantity":1}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.discountApplied").value(false));
    }

    @Test
    void explicitNullIsRejected() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"SKU-123","quantity":1,"couponCode":null}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("COUPON_NULL"));
    }

    @Test
    void zeroQuantityIsRejected() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"SKU-123","quantity":0}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("QUANTITY_OUT_OF_RANGE"));
    }
}
~~~

This is an **illustrative test** for a producer whose controller already implements the chosen semantics. On older Java projects without text blocks, use regular Java strings.

A red generated producer test is a signal to investigate: does the contract reflect the right commitment, is the controller behaving properly, or is the generated test loading the wrong fixture? **A green build where tests were never generated or executed** is not proof of contract compliance.

## 18. Stub Runner: Avoiding Confusion Across Missing, Null, and Empty

Verification flow:

~~~mermaid
flowchart TD
    A["Groovy/YAML contracts for boundary data"] --> B["SCC generates producer tests"]
    A --> C["SCC creates stub mappings"]
    B --> D["Real producer"]
    C --> E["Stub Runner in consumer tests"]
    D --> F{"Producer satisfies cases?"}
    E --> G{"Consumer sends & handles properly?"}
    F -- "No" --> H["Block change and fix"]
    G -- "No" --> H
    F -- "Yes" --> I["Aggregate CI gate"]
    G -- "Yes" --> I
~~~

For each case, consumer tests should use the **real HTTP client and JSON serializer**:

- Omit `couponCode` → receive `200`.
- Send explicit `"couponCode":null` → receive `400 COUPON_NULL`.
- Send `"couponCode":""` → receive `400 COUPON_BLANK`.
- Send `quantity: 100` → receive `200`.
- Send `quantity: 101` → receive `400 QUANTITY_OUT_OF_RANGE`.

**Two important limitations:**

1. Serializers may be configured to **omit null fields** (e.g., `NON_NULL` inclusion policies). When testing explicit null, inspect the **actual outbound body** to verify the key is present.
2. WireMock mappings sharing the same method/path can accidentally **overlap** if generated matchers permit extra fields or partial matches. Inspect mappings inside the stub JAR and run negative tests for each scenario.

If generated stub mappings cannot express “field must be completely absent” with the current generator mode, supplement with appropriate request matching configuration or producer integration tests; do not treat similar-looking contracts as independently verified.

## 19. Error Responses Are Also Contracts

A consumer may rely on:

| Component | Example | Alignment point |
|---|---|---|
| HTTP status | `400` | Use 400 or 422 for validation? |
| Error code | `QUANTITY_OUT_OF_RANGE` | Stable across versions? |
| Error field | `quantity` | Which exact field does the client highlight? |
| Message | `quantity must be 1..100` | Can wording or language change? |
| Error list | `errors: []` | Always present or may be omitted? |

Some systems use **Problem Details** with media type `application/problem+json` per **RFC 9457**. Contracts then commit to `type`, `title`, `status`, `detail`, and extension members. Switching from a custom error body to Problem Details can be a **breaking change** if consumers parse the old schema.

JSON parsing errors can happen **before the controller**. If the API promises a consistent schema for all validation errors, test the exception handler as well so default framework error payloads do not leak through.

## 20. Applying This to Message Contracts

SCC also supports message contracts, for example an event:

~~~json
{
  "eventType": "QuoteCalculated",
  "quoteId": "Q-1001",
  "discountApplied": false,
  "couponCode": null,
  "totalVnd": 150000
}
~~~

A consumer on an older version might interpret:

- **Missing** `couponCode`: producer version does not yet supply coupon info.
- `couponCode: null`: producer includes the field, and no coupon was applied.
- `couponCode: ""`: invalid data or legacy representation.
- `discountApplied: false`: explicit decision not to apply a discount, distinct from an absent field.
- `totalVnd: 0`: valid free quote or business error depending on the domain.

For messages, also check schemas/serializers, headers, destinations/topics, how generated message tests are triggered, and real consumer handlers. A valid JSON fixture alone does not prove the broker and production handlers work properly.

## 21. Bringing the Boundary Data Matrix into CI

| Gate | Required evidence | When to block |
|---|---|---|
| Contract parsing | Valid Groovy/YAML and loaded fixtures | Contract fails to parse or generates no tests |
| Producer verification | Generated tests + validation tests on candidate code | Wrong status/body/error on any key scenario |
| Candidate stub | Artifact from the **exact commit** with complete mappings | Missing stub or wrong/overlapping mappings |
| Consumer verification | Real client running against candidate stub | Confuses absent/null or mishandles responses |
| Release gate | Results across supported consumers | Unplanned breaking change without migration plan |

Example commands in an **SCC-configured project**:

~~~bash
# Producer: generate and run contract tests via Maven lifecycle.
./mvnw clean verify

# Consumer: run tests using Stub Runner with the exact candidate stub.
./mvnw test
~~~

For Gradle, use your plugin's tasks and project configuration; on Windows, use `mvnw.cmd` or `gradlew.bat`. Always inspect generated sources, test reports, and stub artifacts rather than relying solely on the build command's exit code.

**Pin the stub version and commit**. If consumer tests continue pulling an old producer stub, newly added boundary cases have not actually been tested.

## 22. Common Mistakes When Testing Boundary Data

| Symptom | Likely cause | Fix |
|---|---|---|
| YAML `couponCode:` turns into null | No value after the colon | Use `couponCode: ''` for an empty string |
| Client intends to send null, field disappears | Serializer skips nulls | Inspect raw JSON and adjust serializer/test config |
| Stub wrongly returns success for null | Absent-case mapping matches too broadly | Inspect WireMock mappings and add negative tests |
| `quantity: "1"` is still accepted | Framework coerces string → integer | Decide whether coercion is allowed; add tests |
| `@NotEmpty` lets `"   "` pass | Empty differs from blank | Use `@NotBlank` when non-blank text is required |
| Missing quantity bypasses `@Min(1)` | Null not rejected or validation not triggered | Add `@NotNull` and verify validation setup |
| `101` passes matcher | `by_type` only checks type | Add boundary contracts or range checks |
| Oversized number returns 500 | Unhandled parser/mapper exception | Add error handling and contract |
| Response `items: null` crashes consumer | Consumer expects array, does not handle null | Lock down and test response schema |
| Producer tests green yet old consumer fails | Updated contract dropped old behavior | Run consumer tests with candidate stub and coordinate migration |

## 23. Step-by-Step Practice Exercise

**Part A — Design boundary data:** for `POST /api/quotes`, build a complete table for `couponCode` missing/null/empty/blank/valid and `quantity` missing/null/0/1/100/101/"1"/1.5. Specify request, status, error code, and rationale.

**Part B — Author contracts:** write Groovy or YAML contracts for at least six scenarios: valid missing coupon; null rejected; empty string rejected; quantity 0 rejected; 1 valid; 100 valid; 101 rejected. Keep boundary cases explicit without complex matchers when sample values already express the behavior.

**Part C — Producer verification:** run generated tests, inspect assertions, and add controller/binding tests where missing vs. null could be collapsed by a DTO. Verify parse and validation errors map to contract-compliant HTTP responses.

**Part D — Stub/consumer verification:** package the candidate stub, inspect mappings sharing the URL, send requests for each case, and confirm accurate responses. Run consumer tests with the real client, checking whether the serializer emits explicit nulls.

**Part E — Breaking-change drill:** suppose the producer wants to treat `couponCode:null` as valid just like a missing field. When updating code and contracts, check whether consumers relying on `COUPON_NULL` break; propose a rollout and migration sequence before changing behavior.

**Submission evidence:** the matrix, contracts, producer test report, stub version/commit, consumer test results, and analysis of one failure case.

## 24. Pre-Merge Checklist

- [ ] **Missing, null, empty, and blank** fields are distinguished per API semantics.
- [ ] `0`, `false`, `[]`, and `{}` are not treated as equivalent to absent.
- [ ] min−1, min, min+1, max−1, max, and max+1 are tested for key limits.
- [ ] Number/string/boolean types and coercion behavior are decided.
- [ ] Overflow, currency precision, and Unicode length are addressed where relevant.
- [ ] All important error cases have consistent status codes and response schemas.
- [ ] Groovy/YAML DSL accurately expresses absent, null, or empty string fields.
- [ ] Generated producer tests are actually generated and executed.
- [ ] Matchers do not check only type when value bounds are required.
- [ ] Stub mappings are reviewed to prevent overlaps or misrouting.
- [ ] Consumer tests use real clients/serializers against the exact candidate stub.
- [ ] CI records contract revisions, commits, artifacts, and gate results.

## 25. Self-Check Questions

**1. Is a missing field always identical to explicit null?**

No. An API may allow omitting an optional field while rejecting explicit null. A plain Java DTO can erase that distinction; field-presence tracking is needed if the contract requires it.

**2. Why is `@NotEmpty` insufficient for whitespace-only strings?**

Because a string of three spaces has non-zero length. When business rules require non-whitespace text, use an appropriate blank check.

**3. Why is `by_type` insufficient to enforce quantity 1..100?**

Because `by_type` checks data type; `101` is still a number. You need range constraints or dedicated boundary contracts.

**4. If a sample request body omits `couponCode`, is the stub guaranteed not to match a request containing that key?**

Not necessarily; it depends on the matching rules and WireMock options generated by SCC. Inspect the actual mapping and run negative cases.

**5. Why does `null` in JSON Merge Patch require separate attention?**

Because in `application/merge-patch+json`, null typically instructs removing a property from the object, whereas omitting the field means leaving that field untouched.

**6. Are green producer tests enough to prove older consumers stay compatible?**

No. Both producer and contract can change together. You must run consumer tests against the **candidate producer's stub** to detect older clients that cannot handle new boundary data or schemas.

## 26. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): HTTP/message contracts, Groovy/YAML DSL, generated tests, and Stub Runner.
- [Spring Cloud Contract – Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): matchers, JSONPath, and dynamic data.
- [Spring Framework – Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): validation integration.
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/): constraint definitions and limits.
- [RFC 7396 – JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396): absent/null field semantics in Merge Patch.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standard error response format.

---

**Key takeaway:** **Missing ≠ null ≠ empty**, and **valid type ≠ valid boundary**. Boundary data must be specified using requests and responses with explicit expectations, executed via generated producer tests, and verified against actual stub mappings. Consumers must test against **candidate stubs** so CI catches incompatible API changes before release.
