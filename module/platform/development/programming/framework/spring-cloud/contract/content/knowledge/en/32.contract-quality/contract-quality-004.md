# Overly Strict Matchers Break Tests on Harmless Changes

A high-quality API contract must catch **breaking changes**, yet must not fail just because the implementation changes a detail the consumer **was never promised**. In practice, a producer might add an optional JSON field, generate a new `traceId`, change `createdAt`, reorder keys in a JSON object, or append a valid `charset` parameter to `Content-Type`. If tests require the entire response to match a sample string byte-for-byte, harmless changes like these can turn the pipeline red even though consumers still work properly.

That is the problem of **overly strict matchers**: tests guard incidental details instead of guarding only the **critical commitments of the API**. Conversely, loosening matchers too far—such as checking only HTTP 200 and any `status` string—can let tests stay green even when the producer changed the currency type, returned the wrong order, or dropped security checks.

This lesson belongs to the **Contract Quality** chapter of the **SPRING_CLOUD_CONTRACT** module. Spring Cloud Contract helps producers and consumers agree on HTTP or messaging behavior using **Groovy/YAML DSL**, generates **producer verification tests**, publishes `stubs` JARs, uses **Stub Runner** to test consumers, and enforces quality gates in CI/CD. The focus is designing matchers **strict enough to protect meaning, yet flexible enough to avoid false alarms**, then verifying them with generated tests and real consumer tests.

## 1. Symptoms of an overly strict matcher

Suppose **Order Service** exposes `GET /api/orders/42` and **Billing Service** reads order details. On the first call, the producer returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000,
  "currency": "VND",
  "createdAt": "2026-11-24T04:12:13Z",
  "traceId": "trace-abc123"
}
~~~

Another valid call returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json;charset=UTF-8

{
  "traceId": "trace-def456",
  "currency": "VND",
  "amountMinor": 125000,
  "status": "PAID",
  "id": 42,
  "createdAt": "2026-11-24T04:12:15Z",
  "links": {
    "self": "/api/orders/42"
  }
}
~~~

Under this example's **contract assumptions**: Billing needs `id`, `status`, `amountMinor`, `currency`; `createdAt` is a valid timestamp that may change; `traceId` is observability data; `links` is an optional extension field; and JSON object key ordering is not significant.

If a test fails because `createdAt` shifted by two seconds, `traceId` changed, JSON whitespace changed, or `links` was added, **the test is likely checking details outside the contract**. If the producer changes `amountMinor` from a JSON number to a string, returns `id=43`, or returns `currency=USD` in a fixture expecting VND, that **is likely a real contract bug**.

| Change | Should it fail tests? | Why |
| --- | --- | --- |
| JSON object key order changes | **No**, unless canonical representation is required | JSON objects do not promise key order. |
| JSON pretty-printing changes | **No** | Whitespace does not change parsed JSON data. |
| `traceId` changes per request | **No** if only format/presence is required | It is a dynamic operational value. |
| `createdAt` changes to another valid timestamp | **No** if the contract does not promise a fixed instant | Validate format or time relationships instead. |
| Optional `links` field added | **Usually no**, depending on unknown-fields policy | Legacy clients might use a strict deserializer. |
| `amountMinor` changes from number to string | **Yes** if number is promised | Consumers may parse or calculate incorrectly. |
| `id=42` changes to `id=43` on a request for order 42 | **Yes** | Violates request–response correlation. |
| `status=PAID` changes to `CANCELLED` in a paid-order fixture | **Yes** | Alters business semantics. |
| 401 becomes 200 when token is missing | **Yes** | Breaks security constraints. |

**Opening rule:** every assertion must answer: *which consumer depends on this behavior and what happens if it changes?* Without an answer, revisit the strictness rather than asserting every byte by default.

## 2. “Strict” and “lenient” are not two fixed global levels

A good matcher is designed **per attribute**, rather than setting an entire contract to “strict” or “lenient”:

| Constraint type | Meaning | Example |
| --- | --- | --- |
| **Equality** | Value must match exactly. | HTTP `200`, `status=PAID`, fixture `id=42`. |
| **Type** | Value has the right data type without locking sample value. | `amountMinor` is a JSON number; `traceId` is a string. |
| **Pattern** | Value fits a valid format domain. | `traceId` has required prefix/charset; timestamp is ISO-8601. |
| **Range** | Value lies within promised numeric bounds. | `quantity` must be positive, if required by business rules. |
| **Presence / optionality** | Field must exist, may be absent, or may be null. | `id` required; `description` optional. |
| **Structure** | Object/array and required elements exist. | `amount.minor` is numeric, `amount.currency` is a currency code. |
| **Cross-field invariant** | Fields have a business relationship. | `totalMinor = sum(lineTotalMinor)`. |
| **Ordering** | Element position is or is not significant. | Timeline list is ordered; tag set is unordered. |
| **Security/negative behavior** | Invalid requests must be rejected properly. | Missing permission → 403, missing auth → 401. |

Choose strictness based on **real commitments**, not just what the matcher library supports. `byType()` is convenient, but if a `PAID` order turns into `CANCELLED`, it is still a valid string; checking type alone **will miss the bug**.

## 3. Three verification loops that must not be confused

In Spring Cloud Contract, matchers play different roles in different places:

~~~mermaid
flowchart TD
    A["Groovy/YAML Contract DSL"] --> B["Generated producer verification tests"]
    A --> C["Generated stub mappings"]
    B --> D["Compare sample request against real producer response"]
    C --> E["Stub Runner / WireMock"]
    E --> F["Consumer HTTP client sends request"]
    F --> G["Consumer test asserts decoding/behavior outcome"]
    D --> H["CI blocks producer regressions"]
    G --> I["CI blocks consumer incompatibilities"]
~~~

| Layer | What is being verified? | Which matcher usually drives it |
| --- | --- | --- |
| **Producer verification** | Real producer code returns a contract-compliant response for the sample request. | **Response** matchers in the DSL control many generated assertions. |
| **Stub request matching** | The consumer's request qualifies for the stub to return the defined response. | **Request** matchers in the DSL become stub request conditions. |
| **Consumer assertions** | Real HTTP client/listener code understands the data and handles business logic. | Assertions written by the consumer team—not automatically present just because the stub returned 200. |

**This is a crucial asymmetry:** loosening a **response matcher** helps producer tests avoid depending on dynamic values, whereas loosening a **request matcher** too much can make **the stub accept invalid requests** from the consumer. Conversely, a stub returning a fixed sample response does not prove the real producer always returns that value; generated producer tests must check the implementation.

Never fix both sides with a blanket “switch everything to `byType()`.” Identify whether the failure is in **request matching, producer assertions, or consumer logic** before choosing a fix.

## 4. Groovy DSL contracts overly coupled to sample values

An initial contract might state:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID',
            amountMinor: 125000,
            currency: 'VND',
            createdAt: '2026-11-24T04:12:13Z',
            traceId: 'trace-abc123'
        )
    }
}
~~~

Without declaring matchers for dynamic fields, **generated producer tests may emit assertions tied to those sample values**. When the producer generates a fresh `createdAt` and `traceId` per request, tests fail even though those values are **valid under the API**.

Key points to understand:

1. Values inside `body(...)` both supply the **contract/stub sample** and can help define **generated assertions**.
2. For **fixed fields or business invariants**, exact comparison may be appropriate.
3. For **per-request variable fields**, use an appropriate matcher or meaningful custom test.
4. Exact mechanics depend on the **Contract Verifier version and matcher type**: after editing the DSL, inspect the **generated test code** to confirm the library checks what you intend.

**Do not assume every JSON mismatch happens because Contract Verifier performs whole-string comparison.** Many generators translate bodies into JSONPath assertions or specific matchers. The issue is the **assertion condition**, not necessarily text comparison.

## 5. Using `bodyMatchers` to relax only dynamic fields

Keep business values **strict**, and replace constraints only for `createdAt` and `traceId`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID',
            amountMinor: 125000,
            currency: 'VND',
            createdAt: '2026-11-24T04:12:13Z',
            traceId: 'trace-abc123'
        )
        bodyMatchers {
            jsonPath('$.createdAt', byRegex(
                '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'
            ))
            jsonPath('$.traceId', byRegex('trace-[A-Za-z0-9-]+'))
        }
    }
}
~~~

Here:

- `id=42` remains the expected value for the order 42 request. Returning 43 must fail.
- `status=PAID`, `amountMinor=125000`, and `currency=VND` remain the fixture's business constraints.
- `createdAt` is checked against the illustrative **format**, without locking one timestamp.
- `traceId` is checked as a string matching the prefix/character domain, without locking a single ID.
- **Stubs can still return the sample values from `body(...)`**; response matchers govern **producer response verification**, and do not mean Stub Runner automatically generates random trace IDs.

**Limitation of the example timestamp regex:** regex only checks **string shape**, so it could accept month 99 or day 32. If the consumer relies on calendar-valid timestamps, add an `Instant.parse(...)` check or an appropriate validator. The example regex also only permits UTC ending in `Z`; if the API allows offsets like `+07:00`, widen the rule intentionally so the matcher does not reject valid responses.

### 5.1. Why not use `byType()` for everything?

If you write:

~~~groovy
bodyMatchers {
    jsonPath('$.id', byType())
    jsonPath('$.status', byType())
    jsonPath('$.amountMinor', byType())
    jsonPath('$.currency', byType())
    jsonPath('$.createdAt', byType())
    jsonPath('$.traceId', byType())
}
~~~

then breaking changes like `id=999` or `status=CANCELLED` **risk passing type-only assertions** even though consumers depend on those specific values. `byType()` is useful for **fields whose value varies while type must stay fixed**, not as a blanket fix for every failing test.

**Principle:** relax only **what causes false alarms**, keep **what consumers depend on** strict, and inspect generated assertions to ensure everything else stays protected.

## 6. YAML DSL: equivalent matchers when using YAML

A producer using YAML DSL can express the same dynamic fields:

~~~yaml
description: Return paid order with dynamic metadata
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
    amountMinor: 125000
    currency: VND
    createdAt: "2026-11-24T04:12:13Z"
    traceId: trace-abc123
matchers:
  body:
    - path: $.createdAt
      type: by_regex
      value: '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'
    - path: $.traceId
      type: by_regex
      value: 'trace-[A-Za-z0-9-]+'
~~~

This is an **alternative to the Groovy DSL in section 5**, not a second file to load simultaneously. `matchers.body` specifies the JSONPath and matcher type. Verify the exact syntax against your **Spring Cloud Contract version** and compare the **generated tests and mappings**.

**A common misconception:** response `matchers.body` in YAML guides how producer verification checks responses; it is not a **global JSON Schema** forcing every consumer to behave identically. Consumers need their own assertions in their own code and tests.

## 7. JSON objects: key order and whitespace are not the contract

These two JSON objects contain the exact same data:

~~~json
{"id":42,"status":"PAID","currency":"VND"}
~~~

~~~json
{
  "currency": "VND",
  "status": "PAID",
  "id": 42
}
~~~

If a test does:

~~~java
assertThat(actualJson).isEqualTo(
    "{\"id\":42,\"status\":\"PAID\",\"currency\":\"VND\"}"
);
~~~

formatting or key-order changes will fail the test. That approach is only justified if the **protocol truly mandates a canonical byte representation**, such as signed or hashed payloads following a specific convention.

For normal JSON APIs, parse first and assert **values, types, and fields**:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import static org.assertj.core.api.Assertions.assertThat;

ObjectMapper mapper = new ObjectMapper();
JsonNode root = mapper.readTree(actualJson);

assertThat(root.path("id").isIntegralNumber()).isTrue();
assertThat(root.path("id").asLong()).isEqualTo(42L);
assertThat(root.path("status").asText()).isEqualTo("PAID");
assertThat(root.path("currency").asText()).isEqualTo("VND");
~~~

With `JsonNode`, pay attention to **missing paths**, **null**, and **real values** when those distinctions are part of the commitment. In this snippet, `path("status").asText()` on a missing field returns an empty string so the value assertion fails; for larger APIs, assert presence explicitly for clearer error messages.

### 7.1. JSONAssert `STRICT`/`LENIENT` is not an “API-wide strict toggle”

Some teams use JSONAssert:

~~~java
JSONAssert.assertEquals(
    expectedJson,
    actualJson,
    JSONCompareMode.LENIENT
);
~~~

**LENIENT** allows extra object fields and compares arrays without requiring order. That option **can be too loose** when an array carries ordering semantics. **STRICT** checks extra fields and array order more tightly, yet still does not require **object key order** to match.

Do not switch an entire test suite to LENIENT just to silence errors when the producer adds `traceId`. Assert **per JSONPath** and give lists explicit ordering semantics.

## 8. New fields: is adding a field always compatible?

Producer adds:

~~~json
{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000,
  "currency": "VND",
  "links": {
    "self": "/api/orders/42"
  }
}
~~~

If the API policy **permits adding optional response fields**, older clients should normally ignore `links` if unused. In that case, a producer test asserting “the response must have **exactly four keys**” triggers false alarms.

However, some consumers may:

- Configure their JSON deserializer to **fail on unknown properties**.
- Sign or checksum canonical payloads.
- Enforce a JSON Schema with `additionalProperties: false` per protocol agreement.
- Decode into structures that reject extensions.

Thus, **additive changes are not automatically compatible with every consumer**. Before relaxing matchers, confirm the **schema extension policy** and run compatibility tests for all supported consumer versions.

**Design approach:** producer contract assertions should focus on required fields and semantics, while consumer tests verify **real client code still decodes** responses carrying valid extra fields. If a consumer is intentionally strict, treat the API change as a migration/versioning decision rather than merely tweaking tests.

## 9. Missing, null, empty, and optional: never conflate them

These four responses can mean different things:

~~~json
{"description": "Order has been delivered"}
~~~

~~~json
{"description": ""}
~~~

~~~json
{"description": null}
~~~

~~~json
{}
~~~

If the contract says `description` is **optional** and **must not be null when present**, an assertion checking only “string or anything” misses violations. If `description` is required, allowing missing or null is also too loose.

With Jackson:

~~~java
JsonNode response = mapper.readTree(actualJson);

boolean hasDescription = response.has("description");
if (hasDescription) {
    assertThat(response.get("description").isTextual()).isTrue();
}
~~~

If the API permits `null`, the condition changes:

~~~java
if (response.has("description")) {
    JsonNode value = response.get("description");
    assertThat(value.isNull() || value.isTextual()).isTrue();
}
~~~

**Never use `byType()` as a substitute for a presence/optionality/nullability policy.** In PATCH requests especially, distinguishing an omitted field (“no change”), a `null` field (“clear value”), and an empty string is critical.

## 10. JSON arrays: strictness must match ordering semantics

JSON objects generally have unordered keys, whereas **arrays have element order**. The question is: *is that order part of the business contract?*

Example **state history list**:

~~~json
{
  "history": [
    {"state": "CREATED"},
    {"state": "PAID"},
    {"state": "SHIPPED"}
  ]
}
~~~

If the API guarantees ascending chronological order, swapping `PAID` and `CREATED` is a **contract violation**. A matcher that ignores order would be too loose.

Conversely, **warehouse tags list**:

~~~json
{"tags": ["east", "fragile", "insured"]}
~~~

If the API defines `tags` as an unordered set, two arrays with the same elements in different order should be considered equivalent.

Example with AssertJ:

~~~java
assertThat(historyStates)
    .containsExactly("CREATED", "PAID", "SHIPPED");

assertThat(tags)
    .containsExactlyInAnyOrder("east", "fragile", "insured");
~~~

**Do not use `containsAll(...)` in place of multiset equality** when element counts must be preserved: an array with duplicate tags still satisfies `containsAll`. `containsExactlyInAnyOrder` verifies multiplicity and ignores only order.

### 10.1. For arrays of objects

If the Order API returns `items` as a collection of order lines:

1. Identify the **item identifier** field (`sku`, `lineId`).
2. Match items by **identifier**, not by fragile array index.
3. Verify **each item** has valid `quantity`/`price` types and business values.
4. Decide whether **duplicate items** are allowed or forbidden.
5. Enforce ordering only if the producer actually promises a sort order.

An overly loose matcher like “`items` is any array” is equally dangerous: it can miss dropped line items or wrong totals.

## 11. HTTP headers: compare semantic values rather than byte-by-byte

In HTTP, header names are **case-insensitive**. A JSON `Content-Type` may carry a `charset` parameter depending on framework configuration. A test comparing exact strings:

~~~text
Content-Type == "application/json"
~~~

can fail on:

~~~text
Content-Type: application/json;charset=UTF-8
~~~

even though the consumer receives valid JSON. If the contract only requires JSON media type, validate the **parsed media type** per HTTP semantics rather than naive string matching.

Example in a Spring test:

~~~java
import org.springframework.http.MediaType;

MediaType parsed = MediaType.parseMediaType(contentTypeHeader);
assertThat(parsed.isCompatibleWith(MediaType.APPLICATION_JSON))
    .isTrue();
~~~

This is a **consumer/helper test example**, not Spring Cloud Contract DSL syntax. In the DSL, you can use `contentType(applicationJson())` for contract responses; if a valid producer adds a charset and generated tests fail, inspect the **generated matcher and tool version** and pick an appropriate header matcher. Never drop `Content-Type` checks completely just to make CI green.

**Certain headers must be checked strictly**: `WWW-Authenticate`, `Location` after resource creation, idempotency/correlation headers, ETag/If-Match per contract, and cache/security headers. Distinguish insignificant parameters from details the consumer genuinely uses.

## 12. Request side: loosening matchers can let stubs accept invalid calls

A consumer request to create an order:

~~~http
POST /api/orders
Content-Type: application/json

{
  "customerId": "C-42",
  "quantity": 2,
  "clientRequestId": "req-1001"
}
~~~

Because `clientRequestId` changes on every request, a WireMock mapping comparing the **entire JSON request against a fixed sample** can reject completely valid requests. You can relax **only the dynamic field**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldAcceptValidOrderRequest'

    request {
        method 'POST'
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: 'C-42',
            quantity: 2,
            clientRequestId: 'req-1001'
        )
        bodyMatchers {
            jsonPath('$.clientRequestId',
                byRegex('req-[A-Za-z0-9-]+'))
        }
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(id: 42, status: 'CREATED')
    }
}
~~~

Important details:

- `clientRequestId` may vary **as long as it matches the format** accepted by the contract.
- `customerId=C-42` and `quantity=2` in this scenario remain constrained as defined.
- `method=POST`, `url=/api/orders`, and status `201` are not loosened.
- A stub accepting `quantity=-999` because a matcher only checks **type number** can produce a **false pass in consumer tests**, even though the real producer returns 400.

**Request matchers in contracts do not replace application input validation.** Verify negative/positive limits, enums, auth, and required fields with negative contracts or integration tests. Relaxing request matchers should prevent WireMock **false 404 no-match errors**, not make every request count as “valid.”

## 13. Choosing matchers by data type and risk

| Data | Recommended matcher | Why |
| --- | --- | --- |
| Fixed HTTP method/path | **Exact** | Calling the wrong endpoint must never be masked. |
| Status `200/201/401/403/404` | **Exact per scenario** | Consumers branch on status codes. |
| `id` matching request ID | Exact in fixture or invariant | Must not return the wrong resource. |
| Scenario enum `status` | Equality / defined allowed enum | `PAID` differs from `CANCELLED`. |
| `amountMinor` / `quantity` | Type + range + business assertions | Type alone is insufficient if money or counts are wrong. |
| Fixture `currency` | Equality or defined enum/schema | Changing currency can corrupt calculations. |
| Dynamic `createdAt` | Pattern + parse validity + time relation if needed | Avoid locking a single timestamp. |
| `traceId` | Presence + appropriate regex | Enforce format without pinning one fixed ID. |
| Optional additive object field | Assert only if present or per version policy | Supports extensible schemas when agreed. |
| Paginated `items` | Shape + item invariants + page constraints | Do not loosen so much that missing data passes. |
| Ordered timeline | Assert explicit order | Ordering is part of semantics. |
| Unordered tags | Assert multiset, drop order requirement | Avoid failures from harmless sorting differences. |
| JWT/Authorization | Appropriate header & status/scopes | Never weaken security just to pass tests. |

**There is not always a built-in DSL matcher for every invariant.** Relationships like `sum(lineTotalMinor) = totalMinor` may need a **consumer business test** or fixture-backed custom assertion; do not pretend `byRegex` on numbers checks arithmetic.

## 14. Comparing `byEquality`, `byType`, and `byRegex` by intent

In Spring Cloud Contract response body matchers, common options include:

~~~groovy
bodyMatchers {
    jsonPath('$.status', byEquality())
    jsonPath('$.createdAt', byRegex(
        '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'))
    jsonPath('$.traceId', byRegex('trace-[A-Za-z0-9-]+'))
}
~~~

**`byEquality()`** is used when the response value must equal the contract sample; **`byType()`** when only the type needs checking; **`byRegex(...)`** when a format is published. Never pick among these merely based on “which passes more often.”

Comparison:

| Assumed field | New value | Equality | Type | Format regex |
| --- | --- | --- | --- | --- |
| `status=PAID` | `CANCELLED` | **Fail** | May pass (both strings) | Depends on regex; overly broad regex may pass. |
| `traceId=trace-abc` | `trace-def` | Fail | Pass | Passes if format matches. |
| `traceId=trace-abc` | `"oops"` | Fail | Pass | Fails if regex is strict enough. |
| `createdAt` ISO UTC | `not-a-time` | Fail | Pass (string) | Fails if regex is strict; add parsing for calendar validity. |
| `amountMinor=125000` | `"125000"` | Fails if type is enforced | May fail when type matcher checks number | Regex on string can mask type bugs if misapplied. |

Some DSL versions also offer **command/custom predicate** matchers, date/time helpers, or occurrence constraints. Use them when clearly needed, but **read generated code and actual tests** rather than guessing protection levels from the DSL alone.

## 15. Calculations and cross-field invariants: check more than shape

Suppose the response is:

~~~json
{
  "items": [
    {"sku": "SKU-42", "quantity": 2, "unitMinor": 50000},
    {"sku": "SKU-99", "quantity": 1, "unitMinor": 25000}
  ],
  "totalMinor": 125000,
  "currency": "VND"
}
~~~

A matcher checking only:

~~~text
items is array
totalMinor is number
currency is string
~~~

still passes if the producer returns `totalMinor=1`. That is **far too loose** for Billing because totals are critical business data.

In an integration or consumer test with proper DTOs, you can verify:

~~~java
long calculatedTotal = order.items().stream()
    .mapToLong(i -> i.quantity() * i.unitMinor())
    .sum();

assertThat(order.totalMinor()).isEqualTo(calculatedTotal);
assertThat(order.currency()).isEqualTo("VND");
~~~

**Avoid unnecessary duplication**: Contract DSL should capture interactions parties depend on, while complex arithmetic can live in producer domain or integration tests. Keep enough concrete cases so “relaxing a matcher” never drops a critical business invariant.

## 16. Error schemas and security: never loosen arbitrarily

A quality contract suite covers more than happy paths:

| Scenario | Expectation | Risk if matcher is too loose |
| --- | --- | --- |
| Missing bearer token | `401` per published auth scheme | Test bypasses security filter and still returns 200. |
| Token present, missing scope | `403` | Access unintentionally left open. |
| Non-existent order ID | `404` and business error code if promised | Accepting WireMock no-match 404 and thinking it tested error handling. |
| Negative quantity | `400` with appropriate validation contract | Stub accepts any number; consumer never exercises errors. |
| Conflict/idempotency | `409` or designed behavior | Consumer mishandles duplicate orders. |
| Temporary system error | `5xx` + retry contract if published | Test asserts only “no exception,” ignoring response semantics. |

**Never loosen a status matcher** from `401` to “any 2xx/4xx” just because a newer Spring Security version behaves differently. Understand why it changed and agree on an updated contract if policy changed.

In Spring Boot tests, applying `@WithMockUser` globally or disabling security filters can stop generated producer tests for 401/403 from testing real behavior. Review test/fixture setup and DSL assertions together.

### 16.1. Avoiding fake 404s from unmatched requests

WireMock returns `404` when no mapping matches. A consumer test asserting only `status=404` can **pass when the client calls the wrong path**:

~~~text
Expected: GET /api/orders/99 -> HTTP 404 ORDER_NOT_FOUND
Actual:   GET /api/order/99  -> WireMock no-match HTTP 404
~~~

Define error contracts with concrete error bodies/codes and inspect the **request journal and matched mapping**. Stripping request matchers so WireMock “returns some response” is the wrong fix.

## 17. Matcher quality under API versioning and deprecation

A producer supporting v1 and v2 may expose:

~~~text
GET /api/v1/orders/42 -> v1 body
GET /api/v2/orders/42 -> v2 body
~~~

Do not “solve” versioning by making v1 matchers overly loose:

~~~text
response must be any JSON object
~~~

If v1 promises `amountMinor` as a number and the producer changes v1 to `amount: {minor, currency}`, generated v1 producer tests must fail. The proper approach is usually:

1. **Keep v1 contracts and v1 tests** while the producer still commits to supporting v1.
2. **Add independent v2 contracts** for the new schema.
3. **Run consumer tests** across all supported consumer groups.
4. Retire v1 tests only after the **EOL process** confirms no commitments remain.

Relaxing matchers to prevent false positives **does not mean relaxing backward-compatibility policies**. A test that stays green easily while failing to catch breaking changes fails Contract Verifier's purpose.

## 18. Messaging contracts: dynamic metadata and message semantics

In messaging, dynamic metadata is even more common than in HTTP responses. For instance, Order Service publishes `OrderCreated`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'

    input {
        triggeredBy('publishOrderCreated()')
    }

    outputMessage {
        sentTo('orders.created')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-123',
            orderId: 'ORD-42',
            amountMinor: 125000,
            publishedAt: '2026-11-24T04:12:13Z'
        )
    }
}
~~~

**What should be checked strictly:**

- Published destination/topic, e.g., `orders.created`.
- `eventType=OrderCreated` and `schemaVersion=1`.
- Required payload field names/types, amount/currency, and business invariants.
- Consumer's ability to decode the event under the actual schema and version.

**What can be checked flexibly:**

- `eventId` when only a valid ID is required rather than a fixed sample value.
- `publishedAt` when it varies with real execution time.
- JSON key ordering in the payload after parsing.
- Broker/binder-added headers that are not part of the promised contract.

Do not **ignore message delivery ordering** by default. If business logic relies on ordered state transitions, producer/consumer tests must verify ordering or ordering guarantees. Conversely, do not force tests to expect an arbitrary order when the broker makes no ordering guarantee.

**Contract message tests and Stub Runner do not prove real-broker serialization.** If consumers rely on Avro/Protobuf, header mappings, partition keys, or a schema registry, add corresponding integration tests; JSON matchers in the DSL do not cover every transport property.

## 19. Consumer tests with Stub Runner: avoiding false passes

Suppose Order Service published:

~~~text
com.acme:order-service:1.4.2:stubs
~~~

Billing uses Stub Runner:

~~~java
import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingContractTest {

    @Autowired
    StubFinder stubFinder;

    @Test
    void readsOrderAndCalculatesAmount() {
        URL stubUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service")
        );

        OrderClient client = new OrderClient(
            stubUrl.toExternalForm()
        );
        OrderClient.OrderDto order = client.getOrder(42L);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
        assertThat(order.amountMinor()).isEqualTo(125000L);
        assertThat(order.currency()).isEqualTo("VND");
    }
}
~~~

This example assumes **`OrderClient` and `OrderDto` are Billing's real production classes**. The `stubs` artifact must exist in local Maven storage for `LOCAL`; in distributed CI, use `REMOTE` with appropriate repository URL and credentials. `StubFinder` returns **the running WireMock stub URL**, not the Maven repository URL.

**Consumer tests must not assert only “called without throwing” or HTTP 200.** They must verify the DTO and business logic the client depends on. At the same time, there is no need to assert `traceId` always equals sample `trace-abc123` if Billing ignores it.

### 19.1. Verifying the real request when matchers are relaxed

When a WireMock request matcher permits dynamic fields, verify the consumer **actually sends the right method, path, headers, and essential body parts**. With WireMock's Java API in a test holding a server instance:

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlEqualTo("/api/orders/42"))
        .withHeader("Accept", containing("application/json"))
);
~~~

When using Stub Runner without direct access to `WireMockServer`, inspect the **Admin API request journal** at the discovered stub URL. Verify critical values while avoiding printing full tokens or auth headers into CI logs.

**An overly broad request mapping can hide URL or header bugs** even when consumer tests stay green. Verifying actual requests complements disciplined request-matcher design.

## 20. Generated producer tests prove how much is truly protected

An important review question: *after editing the DSL, what does the generated test actually assert?*

Workflow:

1. Edit the Groovy/YAML contract; **never edit generated Java/Groovy test files directly**.
2. Run the test-generation phase/task for your configured Maven/Gradle plugin.
3. Inspect the generated test source: which JSONPaths assert equality, type, or regex? Are any required fields missing?
4. Run producer verification against the real implementation or proper test context.
5. Introduce a confirmed **harmless** change and verify tests still pass.
6. Introduce an intentional **contract-breaking** change and verify tests fail.
7. Revert the test mutation and record the outcome in the PR or CI report.

A compact mutation matrix is very helpful:

| Trial mutation | Expected result |
| --- | --- |
| Change `traceId` to another valid value | PASS. |
| Change `createdAt` to another valid timestamp | PASS. |
| Reorder JSON object keys | PASS if no canonical-order contract exists. |
| Add optional `links` field | PASS if contract allows extension. |
| Change `id=42` to `id=43` | **FAIL**. |
| Change `status=PAID` to `CANCELLED` | **FAIL**. |
| Change `amountMinor` from number to string | **FAIL**. |
| Omit required `currency` | **FAIL**. |
| Change HTTP `200` to `500` | **FAIL**. |
| Remove auth check so missing token returns 200 | **FAIL** on negative/security contract test. |

**These are trial mutations learners run on a test branch**, without adding “fault-injection” logic to production code. Only after proving both PASS and FAIL directions can a matcher reasonably be considered “strict enough.”

## 21. Matcher strictness and library versions

Spring Cloud Contract, WireMock, JSONPath, Rest Assured, JUnit/Spock, and Spring Boot can evolve behavior across versions. Therefore:

- **Pin compatible plugin/DSL/starter versions** in Maven/Gradle and the Spring Cloud BOM.
- Never copy matcher syntax blindly from another version without inspecting generated tests.
- When upgrading libraries, diff **generated sources and mappings** for a representative set of contracts.
- Verify matchers still catch core regressions using mutation tests.
- Distinguish **API test failures** from parser, plugin, or JSONPath dependency errors.
- Never switch from equality to type matching merely to work around an unverified **generator bug**.

A common source of confusion is that the same DSL field has opposite data directions in **stub request matching** vs. **producer response verification**. Inspect **both generated producer tests and WireMock mappings**, not just one side.

## 22. CI: fail at the right time without ignoring real bugs

~~~mermaid
flowchart TD
    A["PR modifies contract or producer code"] --> B["Review semantic contract + compatibility policy"]
    B --> C["Generate producer tests"]
    C --> D["Run producer tests + targeted mutation checks"]
    D --> E{"Assertions meaningful?"}
    E -->|No| F["Fix DSL/matcher, do not skip tests"]
    E -->|Yes| G["Package versioned stubs artifact"]
    G --> H["Consumer Stub Runner tests with real client"]
    H --> I{"Both producer and consumer pass?"}
    I -->|No| J["Block publish/deploy, investigate request/response"]
    I -->|Yes| K["Publish immutable stubs + controlled rollout"]
~~~

Recommended quality gates:

1. **Contracts discovered** and generated tests actually run—never 0 tests or skipped.
2. **Matcher review** documents which fields are exact, type/pattern, or optional.
3. **Producer verification** fails on broken required schemas, semantics, or security.
4. **Consumer Stub Runner tests** invoke the real client, not a self-written mock.
5. **Stub artifact versions are pinned**; avoid uncontrolled `latest` or mutable snapshots during diagnosis.
6. **Never rewrite contracts solely to match a producer bug** while consumers still depend on prior behavior.
7. **Never enable global lenient assertions** across all responses if ordering or error semantics matter.
8. **Inspect the request journal** whenever relaxing request matchers or seeing 404 no-match responses.
9. **Categorize root causes** on failures: assertion too strict, producer breaking change, fixture drift, wrong client request, or tool/version mismatch.

**A pipeline that fails less often is not automatically higher quality.** The true measure is **catching consumer-impacting defects with few false alarms**, not achieving green builds at any cost.

## 23. Diagnosing overly strict matchers in practice

| Symptom | Possible cause | How to investigate / fix |
| --- | --- | --- |
| Fails when `createdAt` shifts a few seconds | Exact value asserted for dynamic data. | Use agreed datetime regex/parsing; do not lock timestamp. |
| Fails when `traceId` changes | Sample ID treated as a business invariant. | Assert format/presence, not equality to one fixed string. |
| Fails solely on JSON pretty-printing | Comparing raw JSON strings instead of parsed structure. | Use structured JSONPath/Jackson assertions. |
| Fails when object key order changes | Matcher compares serialized text. | Compare JSON object semantics. |
| Fails when `links` field is added | Full-object equality / strict extra fields. | Check schema extension policy; allow extra fields if valid. |
| Fails when `charset` is added | Byte-by-byte Content-Type comparison. | Check media type semantics and generated header matcher. |
| Fails when tags reorder | Asserting array order even though API treats it as a set. | Assert multiset with multiplicity, not index order. |
| Timeline order flips yet test passes | Overly loose matcher on ordered array. | Assert business-meaningful ordering. |
| `amountMinor` changes number→string and still passes | Loose string/regex check or missing assertion. | Add JSON type and value/invariant checks. |
| Wrong status `CANCELLED` passes | `byType()` used instead of enum equality. | Restore equality/allowed enum per scenario. |
| Consumer stub accepts request missing required field | Overly broad request matcher. | Check required paths, negative contracts, and journal. |
| Consumer gets 404 despite valid request | Stub matches full body containing exact dynamic field. | Relax only that dynamic field in request matcher. |
| 404 test passes even though client calls wrong path | WireMock returns no-match 404. | Assert error body/matched mapping and request journal. |
| Security test passes without filters | Test setup disables auth or uses global mock identity. | Enable real test context/filters; separate 401/403 scenarios. |
| Generated tests and Stub Runner behave differently | Different request/response matcher directions or tool versions. | Read exact generated test code and WireMock mapping. |
| PR relaxing matcher immediately turns tests green | May hide a real breaking change. | Run mutation tests on required fields and verify consumer impact. |

**Investigation path:** capture actual request/response → read source contract → inspect generated producer assertion or stub mapping → classify change as semantic vs. incidental → adjust the right matcher → re-run both producer and consumer tests.

## 24. Pre-merge matcher review checklist

| Question | Review expectation |
| --- | --- |
| Is this field part of the API commitment? | Justified by contract, docs, or real consumer usage. |
| Is the value fixed by the fixture? | Exact if invariant, pattern/type if legitimately variable. |
| Is the format meaningful? | Tight regex, plus parsing if semantic validity is needed. |
| Must the JSON type be preserved? | Number/string/boolean/null/array/object properly checked. |
| Is the field required or optional? | Missing/null/empty distinguished per policy. |
| Are extra response fields allowed? | Compatible with existing consumers and deserializers. |
| Does array order matter? | Assert exact order or multiset semantics accordingly. |
| Are HTTP status/headers/error schemas protected? | Status/auth/errors not loosened without justification. |
| Is the matcher on request or response? | Understand impact on Stub Runner vs. generated producer tests. |
| Do sample values still produce useful stubs? | Stubs return valid data for consumers to test real logic. |
| Do harmless mutations PASS? | At least one check for common benign changes. |
| Do contract-breaking mutations FAIL? | Key fields and negative cases verified. |
| Were sources and generated outputs inspected? | Real test code/mappings confirm DSL matches intent. |
| Does CI run both producer and consumer tests? | Generated tests not skipped; not relying on stub response alone. |

A review can record a **per-path rule table**:

~~~text
$.id            -> exact 42 (tied to request /42)
$.status        -> exact PAID for this fixture
$.amountMinor   -> number + expected business value
$.currency      -> exact VND for this fixture
$.createdAt     -> ISO-8601 UTC format + parse validity
$.traceId       -> required string, format trace-[A-Za-z0-9-]+
$.links         -> optional extension if consumer policy permits
items order     -> unordered (if API defines set), preserve multiplicity
~~~

This is a **matcher design spec**, not an executable assertion suite. It helps reviewers agree on which parts are **contract** and which are **test implementation details**.

## 25. Hands-on exercise: eliminate false alarms while still catching breaking changes

Practice with Order Service (producer) and Billing Service (consumer):

1. **Define the initial contract** for `GET /api/orders/42` returning `id`, `status`, `amountMinor`, `currency`, `createdAt`, and `traceId`, initially keeping dynamic fields as exact sample values.
2. **Configure Contract Verifier** to generate JUnit 5 producer tests (e.g., Spring MVC MockMvc with a base test seeding Order 42).
3. **Run generated tests** and observe them fail when the producer generates fresh `createdAt` and `traceId` per request.
4. **Replace only those two dynamic fields with `byRegex`** inside `response.bodyMatchers`, keeping business fields exact per the fixture.
5. **Read the generated producer test** to confirm `createdAt`/`traceId` check patterns while business fields stay guarded.
6. **Test benign mutations:** change trace ID, change to another valid timestamp, reorder JSON keys, add optional `links`. Evaluate each against policy and verify tests PASS.
7. **Test breaking mutations:** `id=43`, `status=CANCELLED`, `amountMinor` as string, drop `currency`, change HTTP 200 to 500. Generated producer tests or domain assertions must FAIL.
8. **Create an equivalent YAML contract** and compare generated assertions, without placing both duplicate DSLs in the plugin's scan directory at once.
9. **Test a POST request** with dynamic `clientRequestId`; observe stub no-match with exact body and fix via path-targeted matcher. Do not loosen `quantity`/`customerId` beyond policy.
10. **Test an unordered list**: reorder `tags` and assert multiset equality; add/remove a tag to verify tests still catch changes.
11. **Test an ordered list**: swap order in status history and confirm tests FAIL.
12. **Write a real consumer `OrderClient`**, publish the `stubs` JAR, and use Stub Runner to verify client decoding of critical fields.
13. **Check the request journal** to ensure the client sends the right path/headers and never misinterprets a no-match 404 as a business error.
14. **Add negative contracts** for 401/403/404 with security filters, error bodies, and appropriate fixtures.
15. **Test a message contract** with dynamic `eventId`/`publishedAt` alongside fixed scenario `eventType`/`schemaVersion` and business payload fields; distinguish generated messaging tests from broker integration tests.
16. **Integrate into CI**: producer verification → stub packaging → consumer tests; record one benign mutation that PASSES and one breaking mutation that FAILS.

**Completion criteria:** tests **no longer fail on dynamic metadata, JSON formatting, or permitted extensions**, yet still **fail whenever status, data types, business values, required fields, request paths, or security behaviors break**. Learners can explain **why each matcher is strict enough**, rather than merely showing green tests.

## 26. Self-check questions

1. What is an overly strict matcher? Why does it reduce CI/CD value?
2. Why should the same JSON object with different key order usually be treated as equivalent?
3. Why can switching every matcher to `byType()` mask regressions?
4. For `GET /api/orders/42`, why should `id=42` stay stricter than `traceId`?
5. Does a timestamp regex necessarily prove a date and time are calendar-valid?
6. When a producer adds optional `links`, what conditions decide whether it is a compatible change?
7. What critical detail can JSONAssert `LENIENT` miss when an array has ordering semantics?
8. Why is `containsExactlyInAnyOrder` better than `containsAll` when multiplicity must be preserved?
9. Are missing `description`, `null`, and `""` always equivalent?
10. Does `Content-Type: application/json;charset=UTF-8` necessarily violate an `application/json` contract?
11. How do matchers in `request.bodyMatchers` affect the stub called by the consumer?
12. How do matchers in `response.bodyMatchers` affect producer verification?
13. Why does a stub returning a fixed response not prove the real producer always responds properly?
14. Why is a WireMock no-match 404 not a business 404?
15. When should you use equality, type, regex, range, and cross-field invariants?
16. Why must HTTP 401/403 checks never be loosened just to fix a red test?
17. Does adding schema v2 allow dropping v1 contracts while v1 is still supported?
18. In a message contract, which fields are typically dynamic and which define the interface?
19. Can a generated producer test pass with an overly loose pattern? How do you detect it?
20. What do one passing benign mutation and one failing breaking mutation prove?
21. If a matcher change keeps consumer tests green while producer tests turn red, which layer must you investigate?
22. Why should you never edit generated test sources directly instead of Groovy/YAML DSL?

**Conclusion:** **A good matcher is not one that compares the most bytes, but one that protects the exact behaviors consumers truly depend on.** In Spring Cloud Contract, keep method/path, status, required fields, data types, business values/invariants, and security strict; intentionally relax dynamic values like timestamps/trace IDs or non-contract formatting details. Distinguish **response matchers in generated producer tests** from **request matchers in stubs**, inspect generated code and mappings, and run both producer and consumer tests. Only when harmless changes **PASS** and breaking changes **FAIL** does a team have proof that contracts are both stable and strong enough to stop regressions in CI/CD.
