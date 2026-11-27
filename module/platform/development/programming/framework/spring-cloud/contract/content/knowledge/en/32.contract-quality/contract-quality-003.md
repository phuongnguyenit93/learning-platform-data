# Overly Broad Matchers Let Breaking Changes Slip Through

## 1. The problem: green tests while real communication is already broken

**Spring Cloud Contract (SCC)** is a contract testing tool between a **producer** (a service providing an HTTP API or emitting messages) and a **consumer** (a service calling the API or processing messages). Teams describe behavior using the **Groovy/YAML contract DSL**, then use **Contract Verifier** to generate producer tests, package stub artifacts, and use **Stub Runner** to test consumers in CI.

A decisive factor in contract quality is the **matcher**: the condition the tool uses to accept a request, response, or message as “matching.” Matchers can express exact values, regular expressions, data types, JSONPath, element counts, or custom verification rules.

If a matcher is written **too broadly**, tests can **PASS even though the producer introduced incompatible behavior** or **the consumer sent a non-conforming request**. This is *false assurance*—a false safety signal.

A simple example:

~~~text
Commitment to Checkout:
  GET /api/inventory/SKU-123
  -> {"available":true,"quantity":12}

Buggy producer later returns:
  -> {"available":false,"quantity":12}

Overly broad matcher:
  $.available: byType()       # only requires a boolean

Observed result:
  producer generated test: PASS
  Checkout business flow: FAIL because ordering is blocked
~~~

`byType()` still has value when flexibility is intended; it is simply insufficient if **the value `true` or the `available` rule** is part of the commitment.

This lesson belongs to the **Contract Quality** chapter and focuses on **“Overly Broad Matchers Let Breaking Changes Slip Through.”** The goal is not to recommend exact matching for every value, but to guide you in choosing matchers **strict enough to catch breaking changes, yet flexible enough for genuinely variable data**.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish matchers on the **request side** (stub matching) and the **response side** (producer test assertions).
2. Evaluate when `byType()`, regex, JSONPath, custom matchers, or equality are appropriate.
3. Spot common mistakes: `.*`, overly permissive optional fields, missing boundary checks, ignored arrays/statuses/headers, and loose request matchers.
4. Write HTTP contract examples in Groovy/YAML and inspect how they translate into generated producer tests and WireMock mappings.
5. Design negative tests and mutation tests to **force matchers to fail** when a change would break consumers.
6. Avoid both extremes: **overly broad** matchers letting regressions slip through and **overly strict** matchers causing flakiness or locking random data.
7. Integrate contract quality checks into code reviews and CI, rather than relying solely on `BUILD SUCCESS`.
8. Collaborate across producer and consumer teams to confirm field business semantics and compatibility boundaries.

## 2. What is a matcher and where does it appear?

In SCC, an HTTP contract typically contains:

~~~text
Contract
  request
    method / url / queryParameters / headers / body
    request matcher(s)
  response
    status / headers / body
    response matcher(s)
~~~

Conceptually:

- **Request side:** when generating stubs, the tool must decide whether a consumer request **matches** a given contract.
- **Response side:** when generating producer tests, the tool must decide whether the real producer response **satisfies the commitment**.
- **Message side:** it may need to match the trigger/input, output destination, headers, and emitted payload.
- **Dynamic data:** IDs, timestamps, and tokens may not have fixed values, requiring predicates stricter than `equals` on a sample.

**Important:** the same matcher name does not mean both sides are checked identically. SCC can use **different data sides** when generating producer tests vs. consumer stubs. Therefore, always inspect **generated Java tests and WireMock mappings** rather than looking only at Groovy/YAML sources.

## 3. Two distinct leakage patterns: loose responses and loose requests

| Overly broad location | Consequence | Example |
|---|---|---|
| **Response matcher in producer tests** | Accepts invalid responses the consumer cannot handle | `available=false` passes because only boolean type is checked |
| **Request matcher in consumer stubs** | Returns expected response for an invalid request | Client sends `quantity:"2"` instead of number `2` and still gets 201 |
| **Header/path/query matcher** | Fails to detect wrong version or routing condition | Ignores `Accept` or required header |
| **Message payload matcher** | Accepts events missing fields or with wrong semantics | `eventType: "Unknown"` passes because “it is a string” |
| **Array matcher** | Accepts empty lists, missing elements, or wrong critical ordering | Fails to detect a missing line item |
| **Error matcher** | Accepts wrong error status or body | Every HTTP 404 is treated as `SKU_NOT_FOUND` |

A system can suffer from both flaws simultaneously. For example, producer response matchers get loosened while consumer stubs also have loose request matchers: both pipelines stay green even though the two real services cannot communicate safely.

## 4. A mental model: the set of acceptable outcomes

Suppose the business contract only permits a response with `available=true` when SKU-123 has quantity 12.

The **acceptable behavior set** must reflect these constraints:

~~~text
A = {
  response.status = 200,
  response.body.sku = "SKU-123",
  response.body.available = true,
  response.body.quantity = 12
}
~~~

An overly broad type-only matcher might check:

~~~text
M = {
  response.status = 200,
  sku is any string,
  available is any boolean,
  quantity is any number
}
~~~

Whenever `M` admits a response that `A` forbids, the test produces a **false negative** in the sense of *failing to detect a regression* (even though the runner reports PASS).

Conversely, if the contract allows `requestId` to vary and a matcher forces `requestId="req-1001"`, it can reject a valid response. That is a **false failure** caused by an overly strict matcher.

Design principle:

> **Matchers must be strict on what the consumer depends on, and flexible on data that does not affect the public contract.**

A good predicate is not simply a “complex regex”; it must express **the right rule**.

## 5. Clearly define what the consumer actually needs

Before picking a matcher, answer with the consumer owner:

| Field/behavior | What needs protection | Suggested matcher |
|---|---|---|
| `sku` | Exact SKU requested | Equality or request–response correlation |
| `available` | Accurate inventory availability state | Equality in a concrete scenario |
| `quantity` | Exact quantity matching fixture | Equality for concrete scenario, plus boundary scenarios |
| `requestId` | Valid ID that changes each call | Format-constraining regex, not hardcoded |
| `updatedAt` | Standard parseable timestamp | Timestamp/format matcher + semantic checks if needed |
| `status` | Enum value recognized by consumer | Case equality or whitelist |
| `price.amount` | Non-negative, accurate scale/currency | Numeric type + range/custom predicate |
| `items` | Non-empty in scenarios with items | Matcher constraining element shape and count |
| HTTP status | 200/404/503 carry distinct semantics | Assert **exact** status |
| Error code | `SKU_NOT_FOUND`, `INVENTORY_UNAVAILABLE` | Equality, not an arbitrary regex |

**You cannot infer the full policy from JSON types alone.** A boolean only has two values, yet a consumer may depend heavily on the exact value. A string can represent an enum, ID, timestamp, or error code—those value domains are not interchangeable.

## 6. Running example: Inventory Service and Checkout

Checkout calls Inventory:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Defined fixture state:

~~~text
SKU-123:
  quantity = 12
  available = true
~~~

Producer commits to returning:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","available":true,"quantity":12}
~~~

A buggy producer version returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-999","available":false,"quantity":12}
~~~

There are at least two regressions:

1. `sku` no longer corresponds to the request.
2. `available` contradicts the fixture/quantity.

If the test only asserts that the body has string `sku`, boolean `available`, and number `quantity`, the wrong response can still pass. You need a **sufficiently strict concrete scenario**, alongside matchers for dynamic fields.

## 7. Groovy contract with fixed commitments

Illustrative contract file:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout reads seeded inventory for SKU-123'

    request {
        method GET()
        url '/api/inventory/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

In this contract, the **example body** describes the exact fixture without intentionally loosening required fields with dynamic matchers. When the SCC generator/test is properly configured, the generated producer test verifies the actual response against the commitment. If the team uses explicit matchers, critical fields can use **equality**, while variable fields use appropriate matchers.

**Do not assume the example body is strictly asserted across every attribute in every plugin version or configuration.** Read the generated test to see which JSONPaths it asserts, which body equality mode it uses, and whether any field is skipped.

## 8. Anti-pattern: response `bodyMatchers` checking only types

Suppose the same contract configures response matchers as:

~~~groovy
response {
    status OK()
    body(
        sku: 'SKU-123',
        available: true,
        quantity: 12
    )

    bodyMatchers {
        jsonPath('$.sku', byType())
        jsonPath('$.available', byType())
        jsonPath('$.quantity', byType())
    }
}
~~~

Conceptually, these matchers check each field's **type**, not the specific values `SKU-123`/`true`/`12`. They may fit when values are free to vary, but are **unsuitable** for fixtures where the consumer expects consistency.

A response like:

~~~json
{"sku":"SKU-999","available":false,"quantity":12}
~~~

still has string, boolean, and number types. **Never rely on type-only generated assertions** to protect business semantics.

### When is `byType()` a good choice?

- The field value can change while its **data type** must remain stable.
- Other scenarios or custom assertions verify **value domains and relationships**.
- The API does not guarantee an exact value, e.g., a counter updated concurrently by other activity.
- The team explicitly accepts that this test **does not check concrete content** and adds appropriate verification elsewhere.

If you need to verify `available=true` for a specific fixture, use equality in that scenario.

## 9. Regex `.*` and overly permissive expressions

A matcher like:

~~~groovy
bodyMatchers {
    jsonPath('$.sku', byRegex('.*'))
}
~~~

or:

~~~groovy
bodyMatchers {
    jsonPath('$.reservationId', byRegex('.+'))
}
~~~

can fail to protect either format or meaning:

- `.*` can allow an empty string depending on semantics.
- `.+` only says at least one character exists, not that it is a valid ID.
- `[A-Za-z0-9]+` can accept `ERROR` where `SKU-123` is expected.
- A regex does not verify correlation with the requested URL, e.g., whether the SKU in the response matches **the request**.

A tighter matcher might be:

~~~groovy
bodyMatchers {
    jsonPath('$.reservationId',
        byRegex('R-[0-9]{4,}'))
}
~~~

Even so, regex `R-[0-9]{4,}` only checks the **structure** of the reservation ID; it still does not prove the ID belongs to the newly created transaction or exists in the database.

**Note:** regex engines may use full-string matching or partial search depending on the adapter/matcher. Inspect the generated code and WireMock mapping and test inputs with invalid prefixes/suffixes; when needed, use `^...$` anchors for whole-string intent, then verify your version's supported syntax.

## 10. Numeric regex is not numeric semantic checking

A common anti-pattern is forcing all dynamic data into regexes:

~~~text
"quantity": "12"
Regex: [0-9]+
~~~

If the real contract requires a JSON number:

~~~json
{"quantity":12}
~~~

then JSON string `"12"` and JSON number `12` have **different types**. A regex evaluated over a string representation can accidentally mask a type change if the test framework or converter coerces values before matching.

How to protect against this:

1. Specify the promised **JSON type**: number, string, boolean, object, array, or null.
2. Write a fixed scenario with equality when quantity is seeded.
3. If the value varies, verify both numeric type **and valid range** per rules.
4. Add negative tests with `"12"`, `-1`, `0`, `12.5`, `null` as required.
5. Check the generated test to confirm it genuinely distinguishes types rather than comparing strings.
6. Check consumer DTOs and Jackson coercion settings in case the consumer silently coerces types.

**Regex alone cannot replace type, range, and semantic assertions.**

## 11. Optional, null, empty, and missing are four distinct states

Consider a JSON object:

~~~json
{"note": null}
~~~

It differs from:

~~~json
{}
~~~

and differs from:

~~~json
{"note": ""}
~~~

And differs from a whitespace-only value:

~~~json
{"note":"   "}
~~~

If the consumer distinguishes “field omitted” from “null sent” (especially in PATCH/merge-patch), a matcher that only checks `note` is a string when present can miss **presence semantics bugs**.

Summary table:

| State | JSON form | Possible meaning |
|---|---|---|
| Missing | `{}` | Leave value unchanged or use default |
| Null | `{"note":null}` | Clear/remove or unknown |
| Empty | `{"note":""}` | Empty string explicitly present |
| Blank | `{"note":"  "}` | Characters present, whitespace only |

When a contract requires a **mandatory** field, verify that the **field exists** and is **non-null** per rules. When a field is optional, still include **separate cases** for absent vs. valid value if the consumer must handle both.

A JSONPath predicate checking merely “path exists” may not distinguish null/empty or enforce type constraints. Verify the JSONPath semantics in your generated test and WireMock version.

## 12. Broad enum matchers can break consumers even when JSON type stays unchanged

Suppose Checkout only understands:

~~~json
{"status":"RESERVED"}
~~~

or:

~~~json
{"status":"REJECTED"}
~~~

A new producer returns:

~~~json
{"status":"PENDING_MANUAL_REVIEW"}
~~~

If the matcher is:

~~~groovy
bodyMatchers {
    jsonPath('$.status', byRegex('[A-Z_]+'))
}
~~~

then all three values share the same type and structure, and the test can **fail to notice** that the consumer lacks a handler for the new state.

Options:

- **Scenario equality**, e.g., the success case must be `RESERVED`.
- **Whitelist** if the contract intentionally permits multiple published states.
- **Consumer tests** across all supported enum values, especially unknown-enum fallback if required by policy.
- **Versioning review** when adding enum values, because “adding a value” can be a breaking change for exhaustive switches.

A regex-based whitelist matcher must be written carefully:

~~~text
^(RESERVED|REJECTED)$
~~~

Even then, a regex only guards the enum domain; it does not ensure business logic picked the right value for a given input. For fixed-fixture cases, equality is usually clearer.

## 13. Broad request matchers: stubs accept invalid client bodies

The reverse of loose responses: the consumer sends a malformed request yet Stub Runner still returns the contract response.

Producer expects:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-123","quantity":2}
~~~

Buggy consumer code might send:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json

{"productCode":"SKU-123","quantity":"2"}
~~~

If the stub only matches method/path, it still returns HTTP 201 and keeps the consumer test green. Against the real producer, the request may be rejected with 400/422 or deserialized incorrectly.

**Distinction:** generated producer tests verify a sample request from the contract; they do not prove every consumer serializes requests properly. Consumer Stub Runner tests must enforce that via **strict request matchers**.

## 14. Overly broad vs. constrained WireMock mappings

An overly broad mapping:

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

WireMock only checks method and path. Without Content-Type or JSON body conditions, invalid requests still receive 201.

A tighter **illustrative** mapping:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {
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

This is an **illustrative WireMock mapping**, not a guarantee that SCC generates this exact JSON from a given DSL. Inspect the actual output to see whether matchers use `equalToJson`, `matchesJsonPath`, regex, or another rule.

When business logic allows varying `sku` values, you do not have to hardcode `SKU-123`. Use appropriate JSONPath/range constraints, **while keeping `quantity` as a schema-valid number**, enforcing the published `sku` format, and matching required fields.

## 15. Headers and HTTP status are also part of the contract

Bugs easily missed when focusing only on the body:

- Producer changes 201 Created to 200 OK on a create API while the consumer relies on 201.
- Producer drops `Content-Type: application/json`, preventing the client from decoding the response.
- Consumer omits `Accept` needed by the producer for content negotiation.
- Request omits `Idempotency-Key`, creating duplicate reservations on retry.
- Producer changes `Retry-After`/rate-limit headers that the consumer's retry policy depends on.
- Message header `eventType` changes while the payload still parses.

If response matchers only check body fields, or tests skip status/header checks, the pipeline can miss breaking changes. Verify **critical statuses and headers** using appropriate equality or predicates.

**Avoid asserting auto-generated server headers** such as `Date` or `Server` unless they are explicit public commitments; doing so invites false failures. Constrain only what matters to the consumer.

## 16. Arrays: right type, wrong count or content

Consider an API returning reservation line items:

~~~json
{
  "reservationId": "R-1001",
  "items": [
    {"sku":"SKU-123","quantity":2},
    {"sku":"SKU-456","quantity":1}
  ]
}
~~~

The consumer requires at least one item, forbids negative quantities, and may rely on preserving request order. A matcher checking only that `items` is an array admits:

~~~json
{"reservationId":"R-1001","items":[]}
~~~

or:

~~~json
{
  "reservationId":"R-1001",
  "items":[{"sku":"SKU-999","quantity":-5}]
}
~~~

If the consumer depends on line count, total amount, or order, this is a severe defect despite valid JSON.

In Groovy SCC, some versions support **element count** constraints via `byType` with `minOccurrence/maxOccurrence`:

~~~groovy
response {
    status OK()
    body(
        items: [
            [sku: 'SKU-123', quantity: 2]
        ]
    )

    bodyMatchers {
        jsonPath('$.items', byType {
            minOccurrence(1)
            maxOccurrence(20)
        })
    }
}
~~~

This is an example of a **cardinality constraint**, not a check of all business invariants. Verify `minOccurrence/maxOccurrence` syntax and placement against your SCC version and inspect generated tests.

To protect item contents, use **separate contracts for empty/single/multiple elements**, per-path matchers, or custom assertions. For unordered lists, do not assert order unless promised; verify **the set of elements and identifiers** per rules.

## 17. Decimals, money, and precision: “number” is not enough

A payment field may look like:

~~~json
{"amount":125000,"currency":"VND"}
~~~

The actual contract may specify integer VND, non-negative amount, and a supported currency. A numeric type matcher cannot catch:

~~~json
{"amount":-1,"currency":"UNKNOWN"}
~~~

or a type-valid response with the wrong unit:

~~~json
{"amount":125000.75,"currency":"VND"}
~~~

Clarify:

- JSON number or string?
- Minor units (cents/dong) or decimal major units?
- Are fractional decimals allowed?
- What are the minimum/maximum bounds?
- Is currency an ISO code, internal enum, or whitelist?
- What precision and rounding rules apply?

Matchers can guard type/range/regex; **business tests still need to assert exact values on fixed cases**. For cross-field invariants like amount/currency/tax, use contract fixtures paired with custom or integration assertions that inspect all relevant fields; do not expect isolated `byType()` checks to prove consistency.

## 18. Timestamps and UUIDs: neither hardcoded nor `.*`

Commonly dynamic fields:

~~~json
{
  "requestId": "a38cf5f0-2d46-45ac-8b6b-5ef9299142a9",
  "createdAt": "2026-11-24T05:30:00Z"
}
~~~

Hardcoding these two strings causes flaky tests. Yet `.+` also admits:

~~~json
{"requestId":"NOT_A_UUID","createdAt":"yesterday"}
~~~

How to protect them:

1. Identify the published format: UUID/ULID, ISO-8601, epoch millis, etc.
2. Use the corresponding DSL `byRegex`/`byTimestamp`/`byDate`.
3. Verify timezone/offset if the consumer depends on it; pattern matching alone does not guarantee semantics.
4. If `createdAt` must fall within a time window, use a custom/integration assertion with a controlled clock.
5. If `requestId` must echo a request header, verify the relationship with the request rather than just format.
6. Test negative values with invalid formats or wrong correlation.

A properly formatted UUID regex does not prove the request ID is unique or traceable. Distinguish **format contracts** from **business invariants**.

## 19. Groovy: equality for fixed fixtures, tight matchers for dynamic data

A GET contract with a dynamic `requestId`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Inventory for SKU-123 must be in stock'

    request {
        method GET()
        url '/api/inventory/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12,
            requestId: 'a38cf5f0-2d46-45ac-8b6b-5ef9299142a9'
        )
        bodyMatchers {
            jsonPath('$.sku', byEquality())
            jsonPath('$.available', byEquality())
            jsonPath('$.quantity', byEquality())
            jsonPath('$.requestId', byRegex(
                '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
            ))
        }
    }
}
~~~

- `sku/available/quantity` are critical to the known fixture, so they use equality.
- `requestId` is matched by format instead of a fixed value.
- The `requestId` sample in `body` still supplies realistic sample data for generated stub responses.
- The regex above only checks `8-4-4-4-12` structure; standard UUID v4 also defines version/variant bits.
- If the response allows extra optional fields, define an explicit unknown-fields policy.

**Important:** how SCC combines `body` with `bodyMatchers`, compiles regexes, and generates assertions depends on the plugin version. After generation, read the **Java producer test** and **WireMock mapping**; never trust contract sources blindly.

## 20. YAML DSL: expressing response matchers intentionally

~~~yaml
description: Inventory returns stock for SKU-123
name: get_stock_sku123

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
    requestId: a38cf5f0-2d46-45ac-8b6b-5ef9299142a9
  matchers:
    body:
      - path: $.sku
        type: by_equality
      - path: $.available
        type: by_equality
      - path: $.quantity
        type: by_equality
      - path: $.requestId
        type: by_regex
        value: '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
~~~

The central idea is **never using `type: by_type` for fields where the consumer requires a specific value**.

SCC matcher types and YAML structure depend on plugin version; confirm the contract parses cleanly and inspect generated assertions and mappings. If your plugin version does not support the exact syntax shown, adapt it to your version's reference docs—**never drop an important matcher just to make the build green**.

For fixed body fields, explicit equality matchers can be omitted if the generator's **default assertions** already protect that exact path and value. Base that decision on inspecting the generated code.

## 21. YAML request matchers: controlled flexibility

Sample POST YAML contract:

~~~yaml
description: Create reservation for a valid SKU
name: create_reservation

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 2
  matchers:
    body:
      - path: $.sku
        type: by_regex
        value: 'SKU-[0-9]{3}'
      - path: $.quantity
        type: by_equality

response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: R-1001
    status: RESERVED
~~~

- `sku` varies within a narrow format.
- `quantity` in this scenario must equal `2`.
- `Content-Type` header must be sent accurately.
- Response status is strictly `201`.

This example does not yet guard the full positive integer range of `quantity`. To enforce range 1–100, add boundary scenarios or matchers/custom validation supported by your plugin version.

**Never judge request matcher strictness from YAML sources alone**: open the real WireMock mapping and send a request with a wrong field or type to verify it is rejected.

## 22. JSONPath selects a field; it does not automatically validate its value

Common JSONPaths:

~~~text
$.sku
$.available
$.items[0].sku
$.error.code
~~~

A predicate stating only that `$.error.code` exists admits:

~~~json
{"error":{"code":"UNEXPECTED_FAILURE"}}
~~~

when the consumer only understands:

~~~json
{"error":{"code":"SKU_NOT_FOUND"}}
~~~

Constrain **the value** with equality or a regex whitelist, not merely path existence.

Also distinguish missing paths, null values, empty strings, and wrong types. JSONPath implementations can differ in how they evaluate missing vs. null; write **negative cases** and inspect generated tests and WireMock mappings to verify semantics.

## 23. Cross-field relationships: individual type checks do not prove invariants

Response:

~~~json
{"quantity":0,"available":true}
~~~

Both fields have valid types, yet if the rule is `available = (quantity > 0)`, the response is **wrong**.

How to protect it:

1. Use a `quantity=0` fixture and assert `available=false`.
2. Use a `quantity>0` fixture and assert `available=true`.
3. Add boundary scenarios.
4. If values vary dynamically, use a custom assertion or producer integration test reading **both fields**.
5. Never place two independent `byType()` matchers and conclude the relationship is proved.

A `byCommand` matcher typically receives **the value at that path**. When an invariant spans multiple fields, pass sufficient data or add an integration assertion; never assume a single-field method inspects the whole JSON object.

## 24. Custom assertions: when regex and type checks fall short

Some rules—such as `quantity` being a non-negative integer within limits—need more meaningful assertions than arbitrary regexes. Groovy DSL can invoke a method on the base test:

~~~groovy
response {
    status OK()
    body(
        sku: 'SKU-123',
        quantity: 12
    )
    bodyMatchers {
        jsonPath('$.quantity',
            byCommand('assertValidQuantity($it)'))
    }
}
~~~

An illustrative Java helper:

~~~java
import java.math.BigDecimal;

public void assertValidQuantity(Object value) {
    if (!(value instanceof Number)) {
        throw new AssertionError(
            "quantity must be a JSON number");
    }

    BigDecimal quantity = new BigDecimal(value.toString());

    if (quantity.signum() < 0) {
        throw new AssertionError("quantity cannot be negative");
    }

    if (quantity.stripTrailingZeros().scale() > 0) {
        throw new AssertionError("quantity must be an integer");
    }

    if (quantity.compareTo(new BigDecimal("1000")) > 0) {
        throw new AssertionError("quantity exceeds limit");
    }
}
~~~

**Version note:** the runtime type returned by JSONPath and how generated tests pass `$it` can vary; check the generated Java code to choose the right method signature. If a scenario requires **exact `quantity=12`**, a “0–1000” custom assertion is still **too broad**; fixture equality is what makes it tight enough.

Custom assertions can also be flawed: a helper doing only `assert value != null` is no substitute for business validation. Test mutations with negative numbers, decimals, out-of-bounds values, and non-numeric types to prove detection works.

## 25. Messaging contracts can also suffer from overly broad matchers

A message producer emits an event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        headers {
            header('eventType', 'InventoryChanged')
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

If tests only check “a message arrived,” “body is JSON,” or “`eventType` header is a string,” they can miss:

- Changing `eventType` to a name unknown to the consumer dispatcher;
- Renaming `sku` to `productCode`;
- Changing `quantity` from number to string;
- Sending `available=false` even when `quantity > 0`;
- Publishing to a different destination or route;
- Missing critical schema version or correlation headers;
- Changing the event envelope structure.

Generated messaging tests must trigger the **production use case** and observe real output via an appropriate test binder or message verifier. If the base test **manually sends a sample payload** instead of running application code, the test can pass falsely.

Contract tests do not automatically protect broker partitioning, ordering, at-least-once delivery, retries, or DLQs. If the consumer relies on them, add dedicated **broker integration tests**.

## 26. Overly broad vs. overly strict matchers: two extremes to avoid

| Issue | Example | Consequence |
|---|---|---|
| **Too broad** | Regex `.*` for error code | Breaking changes slip through |
| **Too strict** | Asserting timestamp equals one hardcoded value | Valid responses fail tests |
| Request too broad | Checking only POST path, ignoring body | Mis-serialized client requests pass |
| Request too strict | Matching one exact random request ID | Valid requests are rejected by stub |
| Response too broad | `byType()` for an enum | Unhandled new enum values go undetected |
| Response too strict | Rejecting any extra field despite open API | Blocks valid additive changes |
| Array too broad | Checking only array type | Empty list passes |
| Array too strict | Enforcing order when contract makes no ordering promise | Flaky tests on valid responses |

**High quality does not mean having the most assertions.** Good matchers protect the exact behavior the consumer depends on without locking incidental details.

Evaluate a matcher with two questions:

1. **What change could genuinely break the consumer while this matcher still PASSES?**
2. **What API-permitted change could cause this matcher to FAIL needlessly?**

If either question has an answer, refine the matcher or split test scenarios.

## 27. Not every added field should be rejected

Many APIs allow optional new fields in JSON responses, and consumers ignore unknown properties. In that case, requiring bodies to contain **the exact current field set** causes false failures.

However, some consumers enforce strict JSON schemas or Jackson settings that reject unknown fields. Agree explicitly on:

- Does the consumer allow unknown fields?
- Is the schema **open** or **closed**?
- Could any sensitive fields leak in responses?
- Do new fields alter semantics even when old fields remain present?
- Is there a message schema registry policy for backward/forward compatibility?

When the API supports extensibility, assert **required public fields and invariants**, allowing compatible additions. When the schema is closed, enforce schema validation or strict structure matching per contract.

Never turn on ignore-extra-elements just to turn a build green without understanding **consumers' compatibility policies**.

## 28. WireMock unmatched HTTP 404 is not a business 404 error

WireMock can return HTTP 404 when a request **matches no mapping**. That is a communication or test-setup failure, unlike a contracted business error:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"SKU_NOT_FOUND","message":"SKU does not exist"}
~~~

A weak client test asserting only status 404 can be fooled if it sends the wrong URL and Stub Runner returns an **unmatched 404**. An insufficiently strict consumer mapper:

~~~java
// Anti-pattern: treats every 404 as SKU not found.
if (status == 404) {
    throw new InventoryNotFoundException();
}
~~~

Checklist to verify:

1. Does a dedicated **business 404** mapping exist in the stubs artifact?
2. Does the client request match the exact method, path, query, headers, and body?
3. Does the response include the contract's **error code/body**?
4. Does the test assert the business error code, not just HTTP status?
5. When suspecting a mismatch, inspect WireMock's request journal and near misses.

Never let an unmatched 404 pass a business error test. If a request does not match, that usually signals you must **fix the client or contract matcher**, not interpret it as a missing SKU.

## 29. Stale stubs or fake producers can nullify a tightened matcher

A matcher in source control may have been tightened while the pipeline still consumes an old artifact:

~~~text
Producer candidate B:
  new contract requires error.code == SKU_NOT_FOUND

Consumer Stub Runner:
  downloads old stubs JAR A (loose matcher)

Consumer result:
  PASS, yet unrelated to candidate B
~~~

Required evidence:

1. Which commit/revision do the reviewed contract sources belong to?
2. Does the generated producer Java test contain the updated assertion?
3. Did the test actually run against the producer implementation?
4. Was the stubs JAR built from that exact contract candidate?
5. Which version/timestamp/digest did Stub Runner resolve?
6. Did WireMock load mappings from the new JAR?
7. Did the consumer test run the real HTTP client or message handler?
8. Did negative tests prove the new matcher catches invalid inputs?

**Do not rely solely on a `-SNAPSHOT` version string.** Maven/Gradle/repository proxies or Stub Runner caches can serve contents differing from the candidate. Reliable options include **unique commit-tagged candidate versions** and digests, or recording the resolved timestamped snapshot with provenance.

## 30. Tests asserting only HTTP status do not protect the body schema

A consumer test:

~~~java
assertThat(response.statusCode()).isEqualTo(200);
~~~

is useful for one HTTP check, but verifies neither body, field types, error mapping, nor business outcomes.

Generated producer tests can likewise be weak if they only check:

~~~text
expect status == 200
expect Content-Type == application/json
~~~

A broken body:

~~~json
{"sku":"WRONG","available":false,"quantity":-1}
~~~

still has the expected status and header.

Build a **commitment → executed assertion → detected negative mutation table**, rather than counting tests or regex matchers. Never treat `Tests run: 100` as proof that critical behaviors are protected.

## 31. Negative tests prove request matchers can reject

For the POST `/api/reservations` contract, test at least several cases that **must not match**:

| Probe request | Expectation with proper stub matching |
|---|---|
| `{"sku":"SKU-123","quantity":2}` | Matches valid scenario |
| `{"productCode":"SKU-123","quantity":2}` | Does not match because `sku` is missing |
| `{"sku":"SKU-123","quantity":"2"}` | Does not match when contract requires a number |
| `{"sku":"SKU-123","quantity":-5}` | Does not match if contract requires positive quantity |
| `{"sku":"","quantity":2}` | Does not match if SKU must be non-empty |
| Wrong `Content-Type` header | Does not match if content negotiation is required |
| Wrong URL `/api/reservation` | Does not match expected path |
| Wrong/missing required query param | Does not match query-requiring scenario |

**Caution:** a “does not match stub” check should not rely solely on HTTP 404, since another fallback mapping or intentional business 404 may exist. When needed, inspect the request journal, matched stub ID, and mapping priority. If a **catch-all mapping** is present, categorize and test it explicitly so it does not mask unmatched requests.

Some invalid requests like `quantity=-5` may **intentionally match** a stub describing **business validation 422**; what matters is that they **never mistakenly match the happy-path 201 stub**. Negative test matrices should state the expected scenario, not merely “all bad inputs must return 404.”

## 32. Mutation tests: turning a contract into a provable quality check

**Mutation testing** here means intentionally breaking a critical producer or consumer behavior on a test branch and verifying the contract suite turns **red**.

Example in the Inventory producer:

~~~java
// Correct logic for fixture SKU-123 quantity=12:
return new StockResponse("SKU-123", true, 12);
~~~

Mutation trial:

~~~java
// Intentionally broken on a test branch, DO NOT merge:
return new StockResponse("SKU-123", false, 12);
~~~

If the matcher for `$.available` is only `byType()`, the test may still PASS; if equality requires `true`, the test must FAIL.

Suggested mutation matrix:

| Intentional mutation | Weak matcher that might miss it | Matcher/test that must catch it |
|---|---|---|
| `available:true` → `false` | `byType()` | Scenario equality |
| `sku:SKU-123` → `SKU-999` | `byRegex('SKU-.*')` | Equality / request correlation |
| `quantity:12` → `-1` | `byType()` | Equality or non-negative invariant |
| JSON number → string | Regex over string representation | Strict JSON type / negative test |
| `status:RESERVED` → `UNKNOWN` | `[A-Z_]+` | Whitelist / equality |
| `items` 2 elements → empty | Array `byType()` | Cardinality & scenario assertions |
| `error.code` changed | Status 404 only | Error code equality |
| POST body `sku` → `productCode` | Method/path-only request matcher | Required JSONPath + body matching |
| `Content-Type` dropped | Body-only matcher | Header assertion |
| Response timestamp invalid format | `.+` | Date/timestamp validation |

### Mutation testing steps

1. Start at a commit with mutually agreed contracts.
2. Run generated producer tests against the correct implementation; record test names and executed count.
3. Introduce **one mutation at a time** so failures map clearly to fields.
4. Re-run tests; expect a relevant assertion to **FAIL**.
5. If tests still PASS, inspect generated Java code: does the matcher actually assert that field?
6. If tests did not execute, fix the test runner/generation first without changing the contract.
7. Revert the mutation and confirm tests PASS again.
8. Record “mutation detected/escaped” with root cause and contract/test updates.

**This experiment differs from overall Content QA**: it is a matcher-quality verification technique learners apply on a sandbox project; it does not require modifying files in this repository outside your assigned scope.

## 33. Boundary scenarios beat one generic regex

A `quantity is number` matcher does not test thresholds:

~~~text
quantity = -1    -> invalid
quantity = 0     -> out of stock
quantity = 1     -> available
quantity = 12    -> available
quantity = 1000  -> potentially within limit
quantity = 1001  -> invalid or different limit
~~~

A scenario-based contract suite can protect:

| Fixture | Expected response | Rule protected |
|---|---|---|
| SKU-000, quantity=0 | `available=false` | Zero boundary |
| SKU-001, quantity=1 | `available=true` | One boundary |
| SKU-123, quantity=12 | `available=true` | Positive quantity |
| SKU-404, absent | 404 + `SKU_NOT_FOUND` | Business error |
| Malformed SKU | 400/422 per API | Input validation |
| Inventory unavailable | 503 + error code | Error/retry policy |

Each contract has clear request/response values or producer state preconditions. **You do not need to cram every value into a single regex matcher.** Simple, purposeful scenarios are far easier to review and debug than an obscure predicate nobody understands.

When the backend uses a database or state, the base test must seed stable fixtures or establish corresponding state before calling production code. Never use a fake controller returning canned responses, as that defeats producer verification.

## 34. Checking the consumer: bad requests must be rejected by Stub Runner

A consumer compatibility test should invoke the **real HTTP client**, rather than mocking the client itself:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.4.0-rc.pr173:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryConsumerContractTest {

    @Autowired
    InventoryClient inventory;

    @Test
    void usesInventoryProtocol() {
        StockResponse stock = inventory.getStock("SKU-123");

        assertThat(stock.sku()).isEqualTo("SKU-123");
        assertThat(stock.available()).isTrue();
        assertThat(stock.quantity()).isEqualTo(12);
    }
}
~~~

`InventoryClient`/`StockResponse` are **consumer example classes**, not built-in SCC APIs. `LOCAL` assumes the stub is installed in the local repository. In multi-container CI, use `REMOTE` or artifact distribution with provenance.

Control experiment:

1. Change the client to send `/api/stock/SKU-123` instead of `/api/inventory/SKU-123`.
2. If the matcher/request path is right, the request must fail to match the happy-path stub.
3. Change the client to send `{"quantity":"2"}` instead of a number when the contract requires a number.
4. If the matcher is right, the test must catch the protocol mismatch or scenario business error.
5. Restore the valid client and verify the test passes.
6. Check Stub Runner logs and request journal to confirm **the request actually hit the server**.

If the test still PASSES even when the client sends no request, the client may be mocked or the test only inspects a hand-built DTO. In that case, **no matcher in the stubs JAR is exercised at all**.

## 35. Matcher quality also depends on artifact provenance

In producer–consumer CI, the chain of evidence must remain connected:

~~~mermaid
flowchart TD
    A["Contract source with accurate matchers"] --> B["Generate producer tests"]
    B --> C{"Generated tests execute and pass?"}
    C -- "No" --> X["BLOCK"]
    C -- "Yes" --> D["Generate mappings + stubs JAR"]
    D --> E["Publish candidate version + digest"]
    E --> F["Stub Runner resolves exact candidate"]
    F --> G["Real consumer client sends request"]
    G --> H{"Matching and business assertions pass?"}
    H -- "No" --> X
    H -- "Yes" --> I["Record CI evidence + compatibility decision"]
~~~

A matcher tightened in contract source yet never regenerated into producer tests—or bypassed by Stub Runner loading an old stubs JAR—**was never applied** to the executed tests.

Confirm that:

- Generated tests include the updated assertions and are not skipped;
- WireMock mappings contain the intended `bodyPatterns`/header/URL matchers;
- Producer base tests invoke the real implementation;
- The candidate artifact has the exact commit/version/classifier and checksum;
- Consumer Stub Runner loads the right artifact and the test client targets the right port;
- Negative mutations prove wrong fields/paths are caught;
- CI reports record executed counts, artifact identity, and test outcomes.

A single `BUILD SUCCESSFUL` line never proves matchers protected compatibility.

## 36. Matcher review checklist: from semantics to generated code

During contract code reviews, check in order:

1. **Business context:** which exact fields/behaviors does the consumer depend on?
2. **Schema:** is the field required, what type is it, and what is its nullability?
3. **Value:** equality, enum/range, regex format, or dynamic value?
4. **Cross-field invariants:** could matchers admit contradictory states?
5. **Request constraints:** are method/path/query/headers/body sufficiently strict?
6. **Response constraints:** are status/headers/body schema/error codes asserted?
7. **Arrays:** are min/max counts, required items, and ordering part of the contract?
8. **Messages:** how are event type, destination, headers, and payload schema protected?
9. **Compatibility policy:** are unknown fields, enum evolution, and deprecation decided?
10. **Generator semantics:** do generated Java tests emit the right predicates?
11. **Stub semantics:** do generated WireMock mappings enforce the right request matching?
12. **Mutation evidence:** does injecting one invalid value turn the test red?
13. **Artifact freshness:** do consumer tests use the candidate's mappings or an old artifact?
14. **Ownership:** do producer and consumer reviewers agree on what is flexible vs. invariant?

Never approve `.*` regexes or `byType()` merely because “tests are green.” Reviews need a clear answer: **what set of values does this matcher intentionally allow, and why is that set safe for supported consumers?**

## 37. Rules for choosing matchers by field stability

| Field | Variability | Strategy |
|---|---|---|
| HTTP status per scenario | Fixed | Exact equality |
| Business error code | Fixed per case | Exact equality |
| Request SKU echoed in response | Tied to request | Equality / correlation |
| `available` for seeded fixture | Fixed | Equality |
| `quantity` for seeded fixture | Fixed | Equality |
| Generated `requestId` | Dynamic with format | Tight regex, plus correlation if required |
| `createdAt` | Dynamic with semantics | Date/timestamp matcher + time checks as needed |
| `amount` | Dynamic within domain | Type + range + currency/invariant checks |
| Enum `status` | Finite domain | Equality / whitelist + evolution tests |
| `items` | Collection | Type, cardinality, element schema, and scenario checks |
| Optional feature field | Optional per policy | Presence / null / absent scenarios |
| Unknown response property | Depends on compatibility policy | Explicit open/closed schema decision |
| Authentication token | Dynamic and sensitive | Structure / required presence; never hardcode secrets |

The rule is not blindly “exact > regex > type.” Some fields legitimately vary and only need type guarantees; others must appear only in specific states. **The right strictness is the strictness of the commitment**, not matcher syntax complexity.

## 38. “Quick fixes” that degrade quality

| Symptom | Common wrong fix | Right fix |
|---|---|---|
| Test fails because `available=false` | Change `byEquality()` to `byType()` | Determine whether producer has a bug or contract changed |
| Test fails because timestamp differs | Change to regex `.*` | Use an appropriate timestamp/format matcher |
| Consumer stub fails to match request | Remove all `bodyPattern` rules | Compare real request to contract; fix client or matcher intentionally |
| API adds a new enum value | Use `[A-Z_]+` | Review unknown-enum policy and consumer tests |
| Array test fails on empty list | Remove `minOccurrence` | Determine if empty list is valid or a producer regression |
| Business error test mismatches | Assert only HTTP status | Check error code/body and unmatched 404 |
| Generated producer test fails to compile | Disable test/generation | Fix plugin, base test, or DSL syntax |
| Consumer uses old stub | Enable `latest` and hope it refreshes | Pin candidate version/digest and verify loader |
| Test fails due to database fixture | Mock whole service to return canned response | Fix fixture while keeping production behavior |
| Unit test with mocked client passes | Declare consumer compatibility PASS | Add test with real HTTP client + Stub Runner |

A loose matcher introduced to “keep CI green” can **destroy the exact ability to detect breaking changes**. Every matcher relaxation requires review and a clear answer regarding impact on active consumers.

## 39. Lab A — Replace `byType` with a matcher that protects semantics

**Goal:** prove that a boolean `available` with the right type but wrong value must fail producer tests.

1. Build an Inventory controller/service with seeded fixture `SKU-123` `quantity=12`.
2. Write a Groovy contract returning `available:true`.
3. Use `bodyMatchers.jsonPath('$.available', byType())` on a test branch.
4. Generate producer tests and run them against the real implementation.
5. Intentionally change code to return `available:false`.
6. Record whether the test let the mutation escape.
7. Change the matcher to `byEquality()` or remove the overly broad override when default equality suffices.
8. Re-run: with the buggy code, the test must **FAIL**.
9. Restore the valid code; the test **PASSES**.
10. Inspect generated Java assertions to explain the before/after behavior.

**Evidence:** contract diff, generated test assertions, mutation output, and an explanation of why “right type” is not enough.

## 40. Lab B — Tighten request matchers in Stub Runner

**Goal:** a client sending a malformed JSON body must fail to match the happy-path 201 stub.

1. Write a POST `/api/reservations` contract with string `sku` and number `quantity`.
2. Generate the stubs JAR and inspect the WireMock mapping.
3. Run the real consumer HTTP client with a valid body and verify the 201 response.
4. Change the consumer client to send `productCode` instead of `sku`.
5. Change `quantity` from number `2` to string `"2"`.
6. If the test still receives 201, inspect `bodyPatterns` in the mapping and matchers in the DSL.
7. Add schema-strict request matchers.
8. Regenerate the stubs artifact using an exact candidate version.
9. Run negative tests confirming invalid requests **do not mistakenly match the happy-path stub**.
10. Restore the valid client and verify PASS.

**Evidence:** before/after mappings, request journal, client HTTP request bytes, and test report.

## 41. Lab C — Enum and error-code compatibility

**Goal:** prevent broad regexes from letting enum or error-schema breaking changes slip through.

1. Write a contract with response status `RESERVED` and error code `SKU_NOT_FOUND`.
2. Simulate an enum matcher `[A-Z_]+` and an error test checking only HTTP 404.
3. Intentionally return `UNKNOWN_STATE` or `ITEM_MISSING`.
4. Check whether tests let the mutation escape.
5. Switch to equality/whitelist covering producer-committed cases.
6. Generate producer tests and confirm the mutation FAILS.
7. Build the candidate stubs artifact; test an older consumer's real enum/error mapper.
8. Distinguish business 404 from WireMock unmatched 404.
9. Document the compatibility decision for adding future enum values.

**Evidence:** test matrix, error-code diff, generated assertions, and consumer behavior.

## 42. Pre-merge matcher quality checklist

- [ ] Every critical field is constrained by **both type and semantics**.
- [ ] `.*`/`.+`/`byType()` are not used for fields requiring exact values or whitelists.
- [ ] Dynamic regexes constrain format strictly and reject meaningless strings.
- [ ] JSON number vs. string vs. boolean and numeric bounds are verified where needed.
- [ ] Missing/null/empty/blank are distinguished per contract.
- [ ] Enums and error codes are not masked by broad regexes hiding breaking changes.
- [ ] Request matching checks required method, URL, query, headers, and body.
- [ ] Response assertions check HTTP status, headers, and required body schema/values.
- [ ] Arrays enforce count, element, and ordering rules when the consumer depends on them.
- [ ] Cross-field invariants have dedicated scenarios or custom assertions.
- [ ] Dynamic IDs/timestamps are neither hardcoded nor loosened to `.*`.
- [ ] Open vs. closed JSON schema behavior is decided intentionally.
- [ ] WireMock unmatched 404 is never confused with a business error response.
- [ ] Message contracts protect destination, event type, and required payload.
- [ ] Producer tests exercise real implementation code, not fake controllers returning sample bodies.
- [ ] Generated Java tests and WireMock mappings were inspected for semantics.
- [ ] Negative/mutation tests prove critical compatibility bugs turn tests red.
- [ ] Test runners do not skip tests; executed contract test count > 0.
- [ ] Stubs JAR corresponds to the exact contract commit/candidate; no stale artifacts used.
- [ ] Consumer tests exercise real clients/handlers without mocking the communication boundary.
- [ ] CI records provenance and blocks if mandatory evidence is missing.
- [ ] Producer and consumer reviewers understand and approve any relaxed matcher.

## 43. Self-check questions

**1. Why can `byType()` on boolean field `available` be too broad?**

Because both `true` and `false` are booleans. If a scenario requires `available=true`, a type-only matcher will not detect if the producer flips it to `false`.

**2. Is `byRegex('.*')` a good way to handle dynamic IDs?**

No. It can accept empty or malformed IDs. Use a regex matching the published structure or an appropriate matcher, plus correlation checks if required by the contract.

**3. How do producer response tests and consumer stub request matching differ?**

Producer tests verify **real implementation responses** satisfy the contract; stub request matching verifies the consumer sends **requests conforming to the contract**. Loose matchers on each side cause different kinds of false verification.

**4. Does verifying a JSONPath path exists guarantee the field has the right value?**

No. Path existence checks neither enum membership, numeric range, equality, nor cross-field relationships. Content predicates are required.

**5. Why should both `quantity=0` and `quantity=1` be tested?**

Because they are boundary scenarios that catch violations of `available = (quantity > 0)` that a type matcher misses.

**6. Why does a consumer test receiving 404 not prove business not-found handling works?**

WireMock returns 404 when a request matches no mapping. Assert the business error code/body and, when needed, inspect the request journal.

**7. Should every timestamp and ID be compared by exact equality to increase strictness?**

No, not if that data is meant to vary. Choose format matchers and verify required relationships/semantics instead of locking random values.

**8. Why can enum regex `[A-Z_]+` let breaking changes slip through?**

Because it accepts new enum values outside the set the consumer currently handles. Equality or whitelists paired with compatibility tests protect consumers better.

**9. What happens if a contract matcher is tightened, yet CI still uses an old stubs JAR?**

Consumer results prove nothing about the new matcher. Generate and publish candidate stubs and verify the resolved version/digest and served mappings.

**10. How do you know a matcher is genuinely effective?**

Run an intentional mutation: alter behavior in a way that would break the consumer, and verify that either the generated producer test or consumer stub matching **FAILS** as expected.

## 44. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): generated producer tests, Groovy/YAML contract DSL, and stub artifacts.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): syntax and principles of request/response matchers.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): requests/responses, headers, and JSON bodies.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): running consumer tests against generated stubs.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): generated producer tests and stubs packaging.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): Gradle plugin, contract generation, and test tasks.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): `equalToJson`, `matchesJsonPath`, headers, request journal, and near misses.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): mappings, response bodies, and stub priority.
- [JsonPath — GitHub](https://github.com/json-path/JsonPath): querying fields in JSON and execution caveats.
- [Martin Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html): principles for producer/consumer collaboration to protect interfaces.

**Version note:** Syntax for `bodyMatchers`, `byEquality`, `byType`, `byRegex`, `byCommand`, YAML `matchers.body`, generated assertions, and WireMock mapping structures can vary by Spring Cloud Contract and plugin version. Examples in this lesson illustrate **technical concepts and verification checkpoints**; consult the reference docs for your exact Spring Boot / Spring Cloud Contract version and **inspect generated Java tests and mappings** before relying on them in CI. Commands and exercises are instructional guides, not build outputs executed during authoring.

---

**Key takeaway:** **Overly broad matchers create a gap between “tests PASS” and “consumers are genuinely compatible.”** Type-only response matchers can miss wrong business values; method/path-only request matchers can accept invalid request schemas. Choose matchers aligned with **real commitments**: equality for fixed fixtures, constrained format/range/whitelists for variable data, and custom assertions for complex invariants. Combine generated producer tests, Stub Runner with exact commit-matched artifacts, negative/mutation tests, and CI gates to prove incompatible changes **actually turn tests red**.
