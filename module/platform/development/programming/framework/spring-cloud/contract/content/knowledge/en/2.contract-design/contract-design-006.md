# Distinguishing Required, Optional, and Ignored Fields

## 1. Why Must Fields Be Classified When Designing a Contract?

In a multi-service system, an API may return dozens of fields while a consumer only needs a subset of them. If a contract checks every field and every value, the producer struggles to change even data that does not affect the consumer. Conversely, if a contract is too loose, the producer might delete or change the type of an important field while tests still pass.

With **Spring Cloud Contract**, development teams define HTTP or messaging interactions using Groovy/YAML DSL, generate verification tests on the producer side, publish stubs for consumers, and run these tests in CI. To ensure tests protect the right interface, you must first answer: **which fields must always exist, which fields may be absent, and which fields do not need assertions?**

After this lesson, learners can:

- Distinguish **required**, **optional**, and **ignored** from the perspective of a specific consumer.
- Recognize the difference between an **absent** field, a field with a `null` value, and a field with an empty value.
- Choose appropriate matching rules in Groovy/YAML contracts, avoiding overly strict or overly loose constraints.
- Design test cases for producer and consumer, using stubs to catch incompatible API changes.

## 2. One API, Three Different Commitment Levels

Suppose **Order Service** calls **Payment Service** via `GET /api/payments/42`. Payment Service might return:

```json
{
  "paymentId": 42,
  "status": "PAID",
  "receiptUrl": "https://example.test/receipts/42",
  "traceId": "c31e84a0"
}
```

Order Service needs `paymentId` and `status` to correlate the transaction and determine the order status. It displays a receipt link if `receiptUrl` is present, yet still operates normally when no link is provided. The `traceId` field serves system observability; Order Service does not read it to make decisions.

| Group | Example field | Commitment to verify | When the field is absent |
| --- | --- | --- | --- |
| **Required** | `paymentId`, `status` | Must be present, match the type, and satisfy agreed constraints | **Violates** the contract |
| **Optional** | `receiptUrl` | Allowed to be absent; **if present**, must match agreed type/format | **Valid** |
| **Ignored** | `traceId` | Consumer does not depend on the presence, value, or format of this field | **No impact** on this consumer's contract |

These three concepts represent a **compatibility policy between parties**, not merely three labels in JSON. A field being “ignored” does not mean it is useless across the whole system: `traceId` may still be critical to logging infrastructure, yet outside the business commitment to Order Service.

### 2.1. Required fields

A required field must be present in the message/response for the described scenario. Conditions typically include:

1. **Present:** the required JSON path, key, or header exists.
2. **Non-`null`:** if the contract requires an actual value.
3. **Correct type:** for example `paymentId` is an integer, `status` is a string.
4. **Valid value domain:** `status` belongs to `PAID`, `PENDING`, `FAILED` if those are the agreed statuses.

For example, `{"paymentId":42}` does not satisfy the contract if `status` is required. Similarly, `{"paymentId":"42","status":"PAID"}` is invalid if the consumer requires `paymentId` as a number.

### 2.2. Optional fields

An optional field **may be omitted**. However, “optional” does not mean “if present, any value goes”. For `receiptUrl`, both responses below may be valid:

```json
{"paymentId":42,"status":"PAID"}
```

```json
{"paymentId":42,"status":"PAID","receiptUrl":"https://example.test/receipts/42"}
```

If the contract specifies `receiptUrl` must be a URL string when present, then `"receiptUrl": 17` is invalid. Be explicit about **whether `null` is allowed**, because absent and `null` are not the same state.

A field can be **conditionally required**, such as `failureReason` being required only when `status = FAILED`. Such cases should be described via separate contracts/scenarios and matching business assertions; do not slap a generic “optional” label on it and ignore the condition.

### 2.3. Ignored fields

An ignored field is one on which the consumer **places no test expectations** regarding existence or value. For example, if Order Service does not use `traceId`, the contract for Order Service does not need to assert that `traceId` exists, matches a particular string, or stays preserved across versions.

“Ignored” can carry two distinct meanings that must be separated:

- **Ignoring extra fields in responses:** the producer is allowed to add `traceId` or a new field, and the consumer still reads what it needs. The consumer's deserializer/comparator must tolerate unknown JSON fields.
- **Ignoring value while still requiring the field:** if the consumer needs `traceId` present without caring about its exact value, that field **is still required to exist**; only the value should use a flexible matcher. This is not “completely ignored”.

This distinction matters because a type or regex matcher is still **checking** the field, whereas a truly irrelevant field does not need to appear in the contract's assertions at all.

## 3. Absent, `null`, Empty, and Default Values Are Four Different Cases

Consider `receiptUrl` in the following responses:

| JSON | Interpretation | Valid if the rule is “may be absent; if present must be a non-empty URL”? |
| --- | --- | --- |
| Key `receiptUrl` omitted | **Absent**: field does not exist | Yes |
| `"receiptUrl": null` | Field exists with value `null` | No, unless `null` is explicitly permitted |
| `"receiptUrl": ""` | Field exists, empty string | No |
| `"receiptUrl": "https://example.test/r/42"` | Field has a valid URL value | Yes |
| `"receiptUrl": 42` | Field has numeric type | No |

The same applies to `0`, `false`, empty arrays, and empty objects: they are **actual values**, not automatically equivalent to “field absent”. During serialization/deserialization, some libraries default to omitting `null` fields or assigning defaults when keys are missing. Therefore, test with actual JSON payloads rather than relying solely on Java field types.

When a field can be absent, answer further: what default value will the consumer use, will it log a warning, and is `null` handled differently from an omitted key?

## 4. Classify by **Communication Direction**, Not Field Name

A field can carry different requirement levels depending on the consumer, endpoint, and context:

| Interaction | Required | Optional | Ignored |
| --- | --- | --- | --- |
| **HTTP request** from Order Service | `orderId` in JSON; auth header if required by API | `X-Correlation-Id` header if producer generates one when missing | `User-Agent` header if producer doesn't use it in processing |
| **HTTP response** from Payment Service | `paymentId`, `status` | `receiptUrl` | `traceId` for Order Service |
| **Message** `PaymentCompleted` | `eventType`, `paymentId`, `orderId` | `receiptUrl` if consumer can process event without it | Diagnostic metadata unused by consumer |

For example: Payment Service may treat `traceId` as required for telemetry collection, while Order Service does not need it. **Contracts must be scoped per producer–consumer pair and per specific interaction**, rather than creating one monolithic required-field list for all parties.

For public APIs serving multiple consumers, you can define minimal shared requirements and then verify consumer-specific constraints separately. This reduces the risk of one consumer inadvertently blocking changes meant only for another consumer.

## 5. Expressing Expectations in Spring Cloud Contract Groovy DSL

The following example describes **required** fields in the response from Payment Service:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Returns minimal information for a payment"

    request {
        method GET()
        url "/api/payments/42"
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            paymentId: 42,
            status: "PAID"
        )
        bodyMatchers {
            jsonPath('$.paymentId', byType())
            jsonPath('$.status', byRegex('PAID|PENDING|FAILED'))
        }
    }
}
```

Meaning of the contract:

- `request` specifies the consumer calls `GET /api/payments/42`.
- `response.status` requires a `200 OK` response.
- `body` describes `paymentId` and `status`; these are the fields the contract protects.
- `byType()` checks the data type rather than locking to every specific sample value.
- `byRegex(...)` restricts `status` to an accepted value domain.

**Key point:** `byType()` or `byRegex()` only relax how **values are matched**; they do not automatically turn a required field into an optional field. The two questions “must it exist?” and “if it exists, what must its value look like?” must be designed separately.

`receiptUrl` and `traceId` do not appear in the example because this is a **minimal contract**. Not naming them does not automatically prove that both presence and absence of `receiptUrl` are tested, or that an arbitrary JSON comparison framework ignores every extra field. To ensure full compatibility policy coverage, add appropriate test cases and matching configuration.

### Equivalent contract in YAML DSL

```yaml
description: Look up minimal payment information
request:
  method: GET
  url: /api/payments/42
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    paymentId: 42
    status: PAID
  matchers:
    body:
      - path: $.paymentId
        type: by_type
      - path: $.status
        type: by_regex
        value: 'PAID|PENDING|FAILED'
```

Both Groovy and YAML DSLs can express requests/status codes/bodies alongside matchers. However, **syntax for optional fields/matchers and support capabilities can vary across Spring Cloud Contract versions and between request vs. response sections**. When describing optional fields directly in the DSL, consult the documentation for your exact version; avoid adding an `optional: true` flag to YAML unless you have confirmed tool support in that section.

## 6. Testing Optional Fields Without Accidentally Locking the API

Suppose `receiptUrl` may be absent, but if present must be a valid URL. You must test **both branches**:

**Branch A — Without receipt:**

```http
GET /api/payments/43

HTTP/1.1 200 OK
Content-Type: application/json

{"paymentId":43,"status":"PENDING"}
```

**Branch B — With receipt:**

```http
GET /api/payments/42

HTTP/1.1 200 OK
Content-Type: application/json

{"paymentId":42,"status":"PAID","receiptUrl":"https://example.test/r/42"}
```

An easy-to-control approach is creating **separate interaction scenarios/contracts** for payloads without and with `receiptUrl`, then testing the consumer against the corresponding stubs. If the contract DSL supports optionality directly in matchers, confirm the exact behavior of your DSL version. If only one contract exists showing a sample with `receiptUrl`, you cannot conclude the consumer handles responses missing that field.

To verify **valid values when the field is present**, you can use consumer assertions:

```java
JsonNode payment = objectMapper.readTree(responseBody);

assertTrue(payment.path("paymentId").isIntegralNumber());
assertTrue(payment.path("status").isTextual());

// receiptUrl may be absent, but if present it must be a URL string.
if (payment.has("receiptUrl")) {
    assertTrue(payment.get("receiptUrl").isTextual());
    assertTrue(payment.get("receiptUrl").asText().startsWith("https://"));
}

// Do not check traceId because the consumer does not depend on this field.
```

This is an **illustrative assertion snippet**, assuming `objectMapper`, `responseBody`, and appropriate JUnit/Jackson imports already exist. In production code, use a proper URI parser and domain/URL format rules rather than checking only the `https://` prefix.

The test above deliberately **disallows `receiptUrl: null`**: if the key appears with `null`, `isTextual()` returns `false`. If business rules allow `null`, the condition must be updated explicitly with a corresponding test case.

### Be careful with stubs

A stub generated from a contract usually returns the sample payloads described. If stubs only return branch B, the consumer never exercises branch A. Therefore, to thoroughly test optional behavior, prepare data/contracts for each branch or configure stubs accordingly. At the same time, the producer must verify that the real application satisfies the interactions published in the stubs.

## 7. How to Ignore Extra Fields Safely?

Suppose a new version of Payment Service adds:

```json
{
  "paymentId": 42,
  "status": "PAID",
  "traceId": "c31e84a0",
  "diagnostics": {
    "region": "ap-southeast-1"
  }
}
```

If Order Service only depends on `paymentId` and `status`, the two new fields should not break Order Service's contract. However, **ignoring them in the contract alone is not enough**: consumer code must also tolerate undeclared fields.

For example, with Jackson, a DTO can explicitly allow unknown JSON fields:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PaymentResponse(long paymentId, String status) {}
```

With this, `traceId` and `diagnostics` are ignored when mapping into `PaymentResponse`. Use the real DTO/client inside consumer tests to verify this behavior; do not rely solely on stubs returning cleanly shaped data as expected.

**Do not confuse “ignoring a field” with “skipping security validation”.** If unknown fields come from user input, the producer still needs to validate and sanitize security/business data. A consumer ignoring a field in a response simply means that field is not part of this consumer's communication expectations.

## 8. Test Matrix: Which Cases Must Pass or Fail?

Assuming Order Service's rules:

- `paymentId`: required, integer.
- `status`: required, one of `PAID`, `PENDING`, `FAILED`.
- `receiptUrl`: may be absent; if present must be a non-empty HTTPS URL string; `null` is not accepted.
- `traceId`: outside consumer expectations; unknown JSON fields are allowed.

| Producer response | Expected result | Reason |
| --- | --- | --- |
| `{"paymentId":42,"status":"PAID"}` | **PASS** | All required fields present, optional field absent |
| `{"paymentId":42,"status":"PAID","receiptUrl":"https://example.test/r/42"}` | **PASS** | Optional field present and valid |
| `{"paymentId":42,"status":"PAID","traceId":"x"}` | **PASS** | Fields outside consumer needs are ignored |
| `{"paymentId":42}` | **FAIL** | Missing required `status` |
| `{"paymentId":"42","status":"PAID"}` | **FAIL** | Wrong type for `paymentId` |
| `{"paymentId":42,"status":null}` | **FAIL** | `status` lacks a valid value |
| `{"paymentId":42,"status":"PAID","receiptUrl":99}` | **FAIL** | Optional field present with wrong type |
| `{"paymentId":42,"status":"PAID","receiptUrl":null}` | **FAIL** | Policy specifies `null` is invalid |
| `{"paymentId":42,"status":"REFUNDED"}` | **FAIL** | `status` value outside contract domain |

This is a **target behavior matrix**, not a claim that the single minimal DSL contract in section 5 automatically generates all of these test cases. You must add appropriate contracts, matchers, consumer tests, or schema checks to enforce every rule above.

## 9. Applying the Same Principles to Messaging Contracts

In an asynchronous system, Payment Service might emit an event:

```json
{
  "eventType": "PaymentCompleted",
  "paymentId": 42,
  "orderId": 301,
  "receiptUrl": "https://example.test/r/42",
  "traceId": "c31e84a0"
}
```

For the shipping service:

- `eventType`, `paymentId`, and `orderId` may be **required** to identify the event type and order.
- `receiptUrl` may be **optional** if the service still processes fulfillment without a receipt yet.
- `traceId` may be **ignored** in business logic; the service may still forward it to logging systems.

The event needs to be tested with messages both containing and omitting `receiptUrl`, while the producer must be verified to emit payloads meeting the required fields. Contract testing verifies committed message contents, but does not replace broker testing, event ordering, duplicate handling, and retry mechanisms.

## 10. Common Mistakes in Contract Design

### Mistake 1: Putting every response field into the contract with hardcoded values

If `traceId` changes on every request while the contract locks it to `"c31e84a0"`, producer tests can fail even though the consumer is unaffected. Fix: only check fields the consumer uses; if `traceId` is required but dynamic, check **presence and format**, not exact string equality.

### Mistake 2: Confusing a flexible matcher with an optional field

The rule `jsonPath('$.paymentId', byType())` checks the data type of `paymentId`; it does not mean `paymentId` may be absent. Valid absence rules must be designed explicitly.

### Mistake 3: Treating `null` as equivalent to “absent”

JSON libraries and DTOs may distinguish these two states. If the consumer does not support `null`, explicitly specify and test that `null` is rejected.

### Mistake 4: Running only producer tests or only consumer tests

Producer tests verify the producer implementation complies with the contract; consumer tests using **stubs generated from verified contracts** verify the consumer uses that interface properly. Both sides protect two halves of the interaction; both are needed in a multi-service workflow.

### Mistake 5: Deleting a field because “the current consumer doesn't use it”

A field ignored by Order Service may still be required by another consumer. Before removing or renaming a field, check contracts maintained across **all relevant consumers** and the API versioning compatibility policy.

## 11. Designing Tests and CI to Protect All Three Field Groups

A practical workflow with Spring Cloud Contract:

1. **Inspect how the consumer actually uses the data.** Identify fields used for decisions, fields only for display, fields for logging, and conditional dependencies between fields.
2. **Document clear classification rules.** For required: presence/type/value domain; for optional: is absence valid, is `null` accepted, what format when present; for ignored: does the consumer tolerate extra JSON fields.
3. **Write Groovy/YAML contracts for primary interactions.** Use suitable matchers for required fields with dynamic values, and add response cases needed for branches with/without optional data.
4. **Generate and run tests on the producer.** Implementation changes that omit or corrupt required fields must fail producer verification.
5. **Publish versioned stubs after producer tests pass.** Consumers use Stub Runner to load the right stub version and verify normal branches, missing optional field branches, and extra-field tolerance.
6. **Integrate tests into CI.** Run whenever contracts or APIs change; review impact on non-upgraded consumers before deleting any published field.

Pre-merge contract review checklist:

- Are required fields checked for presence, type, and necessary constraints?
- Do optional fields have tests for both **absence** and **presence**, including `null` rules?
- Are ignored fields truly irrelevant to the consumer, and does the parser accept extra fields?
- Are there conditionally required fields that need dedicated contracts/tests?
- Do stubs and consumer test suites use the exact contract version verified by the producer?
- Does modifying a field impact other consumers or active API versions?

## 12. Self-Check Practice Exercise

An `Inventory Service` returns:

```json
{
  "sku": "SKU-001",
  "available": true,
  "quantity": 15,
  "restockDate": null,
  "requestId": "req-8d2"
}
```

Consumer `Checkout Service` always needs `sku`, `available`, and `quantity` to decide whether to allow ordering. When out of stock, it can display `restockDate` if the producer provides a restock date; the system does not use `requestId` in business logic.

Answer for yourself:

1. Which fields are required, optional, and ignored from Checkout Service's perspective?
2. If `restockDate` has `null`, is that an allowed value or must the key be omitted entirely? What must be agreed in the contract?
3. If `quantity` changes from a number to the string `"15"`, which tests should fail?
4. If the producer adds `warehouseCode`, should Checkout Service be forced to update as well?

**Suggested answers:** `sku`, `available`, and `quantity` are required fields; `restockDate` is optional, but `null` rules and date format when present must be explicitly agreed upon; `requestId` is ignored for this consumer's business needs. Changing `quantity` to a string must be caught if the contract requires a numeric type. Adding `warehouseCode` should not break Checkout Service when it doesn't use it and its deserializer allows unknown JSON fields.

**Remember:** **Required** means absence is an error. **Optional** means absence is allowed, yet presence must satisfy rules. **Ignored** means outside the expectations of the consumer in question. Proper classification is the foundation enabling Spring Cloud Contract agreements to catch truly dangerous API changes while letting the producer evolve interfaces safely.
