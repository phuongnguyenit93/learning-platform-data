# Structure of request, response, and matchers in YAML

## 1. Lesson Objectives

**Spring Cloud Contract (SCC)** allows describing communication behavior between a providing service (**producer**) and a consuming service (**consumer**) using verifiable contracts. For HTTP, a contract specifies which requests are accepted, which responses must be returned, and which values need to match. For asynchronous communication, SCC can also describe messages emitted or received.

SCC supports multiple DSLs such as **Groovy, YAML, Java, and Kotlin**. In this lesson, we focus on the **YAML DSL**: how to organize the `request` and `response` blocks and the `matchers` blocks inside them. YAML is suitable when a team wants a declarative data format that is easy to diff and review without writing Groovy closures.

Getting contract syntax right is only the first step. When the SCC plugin processes YAML, it can **generate tests for the producer** and **generate stubs for the consumer to use via Stub Runner**. Using a matcher on the wrong side can make tests too strict, too permissive, or misrepresent the consumer's requirements. This lesson therefore explains both the syntax **and its verification meaning**.

After this lesson, you will be able to:

1. Read and write a complete HTTP YAML contract with `request`, `response`, and `matchers`.
2. Distinguish matchers applied to requests on the **stub** from matchers verifying responses in **generated producer tests**.
3. Use JSONPath, regex, type checks, date/time checks, null checks, headers, and query parameters.
4. Avoid common mistakes with YAML indentation, data types, regexes, and JSONPath expressions.
5. Verify contracts using generated tests, stub artifacts, Stub Runner, and CI steps.

## 2. Visualizing the Flow Before Examining Syntax

Suppose **Checkout Service** needs to ask **Inventory Service** whether a product is in stock. The contract defines the valid request and the response the consumer needs to read.

~~~mermaid
flowchart TD
    A["YAML contract file"] --> B["Spring Cloud Contract"]
    B --> C["Generated tests on producer"]
    B --> D["Stub / WireMock mapping"]
    C --> E["Run against real Inventory app"]
    D --> F["Stub Runner in Checkout tests"]
    E --> G{"Does producer satisfy contract?"}
    F --> H{"Does consumer handle stub properly?"}
    G -- "No" --> I["Block change / fix contract or code"]
    H -- "No" --> I
    G -- "Yes" --> J["Aggregate CI results"]
    H -- "Yes" --> J
~~~

There are two sides to remember:

- **In `request`:** matchers describe conditions that **the request sent by the consumer to the stub** must satisfy for the stub to pick the matching response. When generating producer tests, SCC also constructs a concrete request to call the real producer.
- **In `response`:** matchers describe conditions that **the response returned by the real producer** must satisfy in generated tests. Consumer-side stubs normally return the sample response corresponding to `body`, optionally via templating when configured.

A passing pair of producer and consumer tests is only meaningful for the scenarios actually described by the contract and the **matching candidate stub version**. Contracts do not automatically replace security, database, timeout, or full end-to-end tests.

## 3. HTTP YAML Contract Skeleton

YAML files can be placed under the contract directory configured by the plugin, for example with Maven:

~~~text
inventory-service/
└── src/
    └── test/
        └── resources/
            └── contracts/
                └── inventory/
                    └── stock-available.yml
~~~

Minimal example:

~~~yaml
description: Return inventory for a SKU
name: stock_available

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
~~~

Key fields:

| Location | Field | Role |
|---|---|---|
| Root level | `description` | Explains the business scenario for readers |
| Root level | `name` | Names the contract, useful for identifying tests/mappings |
| `request` | `method` | HTTP method, e.g. `GET`, `POST`, `PUT`, `DELETE` |
| `request` | `url` or `urlPath` | Target address or path segment, depending on how the request is described |
| `request` | `headers` | Headers sent by the consumer, such as `Accept` |
| `request` | `body` | Request payload, if the method has a body |
| `request` | `matchers` | Request matching rules so the stub recognizes the right scenario |
| `response` | `status` | HTTP status as an integer, e.g. `200` or `201` |
| `response` | `headers` | Headers returned by the producer, e.g. `Content-Type` |
| `response` | `body` | Payload the producer must return and the stub illustrates |
| `response` | `matchers` | Rules verifying the producer's response in generated tests |

**Specifically:** `matchers` is a block **inside** `request` or `response`, not an arbitrary set of rules at the root level. The same key `matchers` carries different meanings depending on the side of the interaction.

A contract may omit `body` if the response is just `204 No Content`, or omit the request body for `GET`. Only describe characteristics that truly belong to the contract.

## 4. Understanding `request`: method, URL, and query parameters

### 4.1. `url` and `urlPath`

A request usually specifies `method` and one of two URL representations:

~~~yaml
request:
  method: GET
  url: /api/inventory/SKU-123
~~~

When query parameters are a notable part of the contract, they can be expressed separately:

~~~yaml
request:
  method: GET
  urlPath: /api/inventory/SKU-123
  queryParameters:
    includeWarehouses: "true"
    locale: vi
~~~

Separating `urlPath` from `queryParameters` makes it clear to readers what data the consumer is requesting. HTTP query parameters are URL data, so `"true"` in the example is treated as a **string** rather than a JSON boolean.

Do not include `?` and query parameters inside `urlPath` if you already describe them under `queryParameters`. Pick one clear, consistent representation to avoid accidentally defining the same condition twice.

### 4.2. Request headers

~~~yaml
request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json
    X-Channel: checkout
~~~

Headers in `request` define metadata sent by the consumer. Some systems also require `Authorization`, a version header, or a correlation ID. Never put real tokens in contracts; use dummy values or appropriate matchers.

### 4.3. Request body

For a POST creating a reservation:

~~~yaml
request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 2
    customerRef: CUST-DEMO
~~~

A YAML map in `body` is interpreted as the data structure sent as JSON. This sample data both lets SCC generate a concrete request for producer tests and supplies values that can serve as matching conditions for the stub.

Avoid writing `quantity: "2"` if the API expects JSON number `2`: mismatched data types can make tests run with the wrong semantics.

## 5. Understanding `response`: status, header, and body

The response is the behavior the producer promises to execute when receiving a matching request:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: application/json
    Cache-Control: no-store
  body:
    sku: SKU-123
    available: true
    quantity: 12
    warehouses:
      - code: HCM-01
        quantity: 7
      - code: HN-02
        quantity: 5
~~~

Where:

- `status: 200` is an **integer** HTTP status.
- `Content-Type: application/json` specifies the returned media type; it also affects how the client deserializes the data.
- `available: true` is a boolean, not the string `"true"`.
- `warehouses` is an array of objects. YAML uses `-` to start each array element.
- Field names such as `available`, `quantity`, and their semantics are part of the behavior the consumer can depend on.

Example response with no body:

~~~yaml
response:
  status: 204
~~~

Do not fabricate a dummy body for a `204` case, as doing so can make the contract contradict the HTTP protocol.

## 6. Why Do Matchers Matter?

Without matchers, a fixed value in the contract can become an overly rigid expectation. Suppose the producer generates reservation ID `RSV-1001` on one run and `RSV-1002` on the next. The consumer only needs a valid code formatted as `RSV-<number>`; forcing the response to always equal `RSV-1001` would cause producer tests to fail even when the application follows business logic.

Conversely, if the stub accepts **any** request without checking `sku`, `quantity`, or headers, consumer tests could pass even when the client sends malformed data.

Matchers address both needs:

| Placement | Primary purpose | Question |
|---|---|---|
| `request.matchers` | Describes conditions a request must satisfy for the **stub** to recognize the consumer's request | Is the consumer calling the API with the right format, headers, query, and body? |
| `response.matchers` | Describes how **generated tests** verify the real producer's response | Is the producer returning data with the committed types, formats, and values? |

SCC uses the sample values in `body` as the basis for the other side of the verification flow. For instance, a matcher on the response does not mean the stub automatically generates a different random response each time: the stub may still return the **sample values** from the contract. Clearly distinguish **data returned by the stub** from **rules verifying the producer**.

## 7. General Syntax of Body Matchers

In the YAML DSL, body matchers are typically a **list** under:

~~~yaml
request:
  body:
    sku: SKU-123
  matchers:
    body:
      - path: $.sku
        type: by_regex
        value: '^SKU-[A-Z0-9-]+$'
~~~

Each item describes a rule:

| Property | Meaning |
|---|---|
| `path` | JSONPath pointing to a value in the payload, e.g. `$.sku` |
| `type` | Matching strategy such as `by_regex`, `by_equality`, `by_type` |
| `value` | Value or regex used with the corresponding matcher |
| `predefined` | Built-in SCC regex, e.g. `uuid` or `non_empty` |
| `regexType` | Declares the target type for the regex, e.g. `as_integer`, `as_boolean` |
| `minOccurrence` / `maxOccurrence` | Element count bounds for certain type/collection matchers |

**Important rule:** JSONPath must reference an element that **actually exists in the sample `body`**. For example, `path: $.id` is wrong if the fixture only has `reservationId`. A syntactically valid JSONPath pointing to a nonexistent value will cause test generation or verification to behave unexpectedly.

Start with simple matchers, run generated tests/stubs, and only broaden matchers when dynamic data genuinely needs to be accepted.

## 8. Common Matchers on `response`

Suppose the producer returns reservation creation data:

~~~yaml
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: RSV-1001
    status: CREATED
    acceptedQuantity: 2
    expiresAt: "2026-11-24T11:30:00"
    note: null
  matchers:
    body:
      - path: $.reservationId
        type: by_regex
        value: '^RSV-[0-9]+$'
      - path: $.status
        type: by_equality
      - path: $.acceptedQuantity
        type: by_type
      - path: $.expiresAt
        type: by_timestamp
      - path: $.note
        type: by_null
~~~

The rules here carry distinct meanings:

- **`by_regex`** on `reservationId`: accepts strings matching the pattern, such as `RSV-2002`, instead of requiring `RSV-1001`.
- **`by_equality`** on `status`: expects the exact value `CREATED` specified in `body`.
- **`by_type`** on `acceptedQuantity`: verifies the data type matches the sample `2`; it does **not** mean the value must equal 2.
- **`by_timestamp`** on `expiresAt`: verifies timestamp formatting according to SCC rules; it does **not** replace business checks like "must be at least 15 minutes in the future".
- **`by_null`** on `note`: verifies the value is `null`, which differs from the field being completely absent.

If the consumer needs to confirm that `acceptedQuantity` equals the exact requested quantity, using `by_type` alone is insufficient; you need an appropriate matcher or business verification check to express that relationship.

### Matcher types to remember

| `type` | When to use | Verification behavior |
|---|---|---|
| `by_equality` | Value must be fixed | Compares against the sample in `body` |
| `by_regex` | Strings or numbers following a format | Matches against a regular expression |
| `by_type` | Value can change but type must match | Compares type against the sample value |
| `by_date` | Dates | Verifies date format |
| `by_time` | Times | Verifies time format |
| `by_timestamp` | Date-times | Verifies timestamp format |
| `by_null` | Value must explicitly be null | Verifies JSON `null` |
| `by_command` | Custom rule in producer tests | Calls a verification method in the test base |

`by_command` only works when the corresponding Java/Groovy method is properly provided in the test base or an appropriate import. Do not use a custom matcher just to replace a built-in comparison.

## 9. Regex and `regexType`: Controlling Flexibility

A regex should usually be written as a **single-quoted YAML string** to minimize the need for escaping backslashes:

~~~yaml
response:
  body:
    reservationId: RSV-1001
    referenceNumber: 120045
  matchers:
    body:
      - path: $.reservationId
        type: by_regex
        value: '^RSV-[0-9]{4}$'
      - path: $.referenceNumber
        type: by_regex
        value: '^[0-9]{6}$'
        regexType: as_integer
~~~

For string `reservationId`, the regex defines the ID format. For `referenceNumber`, which is a **JSON number**, `regexType: as_integer` expresses the desired type for the regex rather than treating it solely as a string.

Some `regexType` values available in the DSL include:

- `as_string`
- `as_integer`
- `as_long`
- `as_double`
- `as_float`
- `as_short`
- `as_boolean`

Both the **pattern** and the **type** must align. For example, `referenceNumber: "120045"` in the body is a JSON string, unlike `referenceNumber: 120045`, which is a number. Do not use a regex to mask a data model with the wrong type.

### Predefined regexes

Instead of writing regexes from scratch, YAML matchers can use `predefined`:

~~~yaml
response:
  body:
    requestId: "550e8400-e29b-41d4-a716-446655440000"
    email: "customer@example.test"
  matchers:
    body:
      - path: $.requestId
        type: by_regex
        predefined: uuid
      - path: $.email
        type: by_regex
        predefined: email
~~~

Common predefined patterns include: `uuid`, `email`, `number`, `any_boolean`, `iso_date`, `iso_date_time`, `iso_time`, `non_empty`, `non_blank`. Check the exact list and type conversion behavior against the documentation for the **specific SCC version** used by your project.

Predefined regexes verify **format**, not business logic such as whether an email exists, whether a UUID is in the database, or whether a timestamp falls within a processing window.

## 10. Matchers for Request Bodies: Ensuring Producer Receives Valid Patterns

For a reservation creation API, the request may carry a reference code that varies per consumer:

~~~yaml
description: Checkout creates a valid reservation
name: create_reservation

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    clientRequestId: REQ-1001
    sku: SKU-123
    quantity: 2
  matchers:
    body:
      - path: $.clientRequestId
        type: by_regex
        value: '^REQ-[0-9]{4}$'
      - path: $.sku
        type: by_regex
        value: '^SKU-[A-Z0-9-]+$'
      - path: $.quantity
        type: by_regex
        value: '^[1-9][0-9]*$'
        regexType: as_integer

response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: RSV-1001
    status: CREATED
~~~

When Stub Runner uses the generated stub, incoming requests must satisfy the required conditions to match the reservation-creation scenario. For example, `quantity` must be a positive integer matching the chosen pattern. Generated producer tests can use the **sample data** `REQ-1001`, `SKU-123`, `2` to invoke the real producer code.

If business rules restrict `quantity` from 1 to 100, the regex `^[1-9][0-9]*$` still allows 101 and larger numbers; you need an appropriate rule or a separate error-case contract. A syntactically valid matcher is not necessarily tight enough for business rules.

## 11. Matchers for URL, Headers, and Query Parameters

The body is not the only part that needs matching. Some APIs depend heavily on the path, headers, or query parameters. The YAML DSL provides corresponding matchers under `request.matchers`.

### 11.1. Matching the URL

~~~yaml
request:
  method: GET
  urlPath: /api/inventory/SKU-123
  matchers:
    url:
      regex: '/api/inventory/SKU-[A-Z0-9-]+'
~~~

The sample path remains in `urlPath`; the matcher allows the stub to accept paths matching the regex when the mapping is generated from the contract. Verify the exact plugin behavior with your project's URL and query parameter configuration.

### 11.2. Matching headers

~~~yaml
request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json
    X-Channel: checkout
  matchers:
    headers:
      - key: Accept
        regex: 'application/json.*'
      - key: X-Channel
        regex: 'checkout|mobile'
~~~

Header matchers use `key` and a matching rule such as `regex`; they do not use `path` like body matchers. When using regexes, understand the match scope and avoid overly broad patterns on headers used for routing access.

### 11.3. Matching query parameters

~~~yaml
request:
  method: GET
  urlPath: /api/inventory/SKU-123
  queryParameters:
    locale: vi
    includeWarehouses: "true"
  matchers:
    queryParameters:
      - key: locale
        type: matching
        value: 'vi|en'
      - key: includeWarehouses
        type: equal_to
        value: "true"
~~~

For **query parameters**, `type` has its own values such as `equal_to`, `containing`, `matching`, `not_matching`, `absent`. Do **not** use body matcher's `by_regex` to describe a query parameter.

| Location | Sample syntax |
|---|---|
| JSON body | `- path: $.sku` and `type: by_regex` |
| Header | `- key: Accept` and `regex: application/json.*` |
| Query parameter | `- key: locale`, `type: matching`, `value: 'vi|en'` |
| URL | `matchers.url.regex: '/api/...'` |

These are **distinct branches** of the YAML schema. You cannot port a body matcher straight to headers or query parameters merely by renaming fields.

## 12. Response Header Matchers

The response side can also include header matchers so producer tests verify the format of a dynamic header:

~~~yaml
response:
  status: 201
  headers:
    Content-Type: application/json
    X-Request-Id: req-1001
  body:
    status: CREATED
  matchers:
    headers:
      - key: Content-Type
        regex: 'application/json.*'
      - key: X-Request-Id
        regex: 'req-[0-9]+'
~~~

These matchers apply to **response headers**, unlike `request.matchers.headers` which checks headers sent by the consumer. If a header is required, the contract should express that clearly; if the client does not rely on a header, there is no need to assert every auxiliary header added automatically by the framework.

Some header matchers support `command` for custom verification logic. Only use this when the team has a test base providing the corresponding method and a clear technical reason.

## 13. JSONPath: Pointing to the Exact Field to Verify

JSONPath specifies a location inside a JSON payload:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "warehouses": [
    {"code": "HCM-01", "quantity": 7},
    {"code": "HN-02", "quantity": 5}
  ],
  "metadata": {
    "source.system": "warehouse-core"
  }
}
~~~

Examples of relevant JSONPaths:

| JSONPath | Meaning |
|---|---|
| `$.sku` | Root-level `sku` field |
| `$.available` | Boolean `available` field |
| `$.warehouses[0].code` | Warehouse code of the first element |
| `$.warehouses[1].quantity` | Quantity in the second element |
| `$['metadata']['source.system']` | Field with a dot inside its **key name** |

For keys containing dots, spaces, or special characters, use bracket notation and quotes inside the JSONPath, and wrap the **entire path** in appropriate YAML quotes:

~~~yaml
response:
  body:
    metadata:
      source.system: warehouse-core
  matchers:
    body:
      - path: "$['metadata']['source.system']"
        type: by_equality
~~~

Do not assume `$.metadata.source.system` points to the same key: dot notation typically denotes **multiple object levels**, whereas `source.system` here is **a single key name**.

If you use a specific index like `[0]`, the matcher may depend on array ordering. When order is not an API commitment, design matchers and consumer tests to avoid unnecessarily hardcoding order.

## 14. Checking Types and Array Element Counts

Numeric, boolean, or array fields can change values across runs. `by_type` lets producer tests verify a value's type against the sample in `body`:

~~~yaml
response:
  status: 200
  body:
    sku: SKU-123
    available: true
    quantity: 12
    warehouses:
      - code: HCM-01
      - code: HN-02
  matchers:
    body:
      - path: $.available
        type: by_type
      - path: $.quantity
        type: by_type
      - path: $.warehouses
        type: by_type
        minOccurrence: 1
        maxOccurrence: 5
~~~

The intent is to confirm `available` stays a boolean, `quantity` stays a number, and the warehouse list falls within an acceptable size range. However, array size checks depend on the **verifier version, configuration, and feature support**. In SCC documentation, JSON array size assertions have been marked as experimental and gated by dedicated options. Therefore, after using `minOccurrence` or `maxOccurrence`, inspect the **actual generated test** to verify a size assertion exists rather than assuming so from the YAML.

If the consumer requires `quantity >= 0` or that the sum of warehouse quantities equals `quantity`, `by_type` does not check those invariants. You must add appropriate business tests or custom checks.

## 15. Using `by_command` When Rules Exceed Built-In Matchers

Some constraints require extra logic, such as verifying a returned code exists in a catalog or two fields are consistent with each other. The **response** side of a YAML contract supports the `by_command` matcher so generated tests call a verification method supplied by the test base.

~~~yaml
response:
  status: 200
  body:
    quantity: 12
  matchers:
    body:
      - path: $.quantity
        type: by_command
        value: 'assertNonNegative($it)'
~~~

Java example illustrating the verification method:

~~~java
// Method must be callable by SCC generated tests per the test base configuration.
public void assertNonNegative(Number value) {
    org.assertj.core.api.Assertions
            .assertThat(value.doubleValue())
            .isGreaterThanOrEqualTo(0);
}
~~~

`$it` is where SCC passes the value extracted via JSONPath into the method. Make sure the method is accessible to generated tests (e.g., present in the test base class with compatible parameter types), then inspect the generated test source to confirm. This is a **producer-side test matcher**, not code executed inside the consumer from the stub.

Do not use `by_command` for conditions that can be expressed cleanly with `by_equality`, `by_regex`, or `by_type`: custom logic makes contracts harder to read and more coupled to test infrastructure.

## 16. A Complete Contract with Request and Response Matchers

Having understood each building block, let's combine them into a realistic scenario: **the consumer requests reservation creation**, and the producer returns a new ID and the accepted quantity.

File `src/test/resources/contracts/reservation/create-reservation.yml`:

~~~yaml
description: Checkout creates a valid reservation
name: create_reservation

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
    X-Channel: checkout
  body:
    clientRequestId: REQ-1001
    sku: SKU-123
    quantity: 2
  matchers:
    headers:
      - key: Content-Type
        regex: 'application/json.*'
    body:
      - path: $.clientRequestId
        type: by_regex
        value: '^REQ-[0-9]{4}$'
      - path: $.sku
        type: by_regex
        value: '^SKU-[A-Z0-9-]+$'
      - path: $.quantity
        type: by_regex
        value: '^[1-9][0-9]*$'
        regexType: as_integer

response:
  status: 201
  headers:
    Content-Type: application/json
    X-Request-Id: req-1001
  body:
    reservationId: RSV-1001
    status: CREATED
    acceptedQuantity: 2
    expiresAt: "2026-11-24T11:30:00"
  matchers:
    headers:
      - key: X-Request-Id
        regex: 'req-[0-9]+'
    body:
      - path: $.reservationId
        type: by_regex
        value: '^RSV-[0-9]+$'
      - path: $.status
        type: by_equality
      - path: $.acceptedQuantity
        type: by_type
      - path: $.expiresAt
        type: by_timestamp
~~~

### Expected Evidence at Runtime

**Generated producer test** sends the request with the sample data, then verifies that the producer returns `201`, status `CREATED`, and fields/headers matching the matchers. If the actual `reservationId` is `RSV-2002`, the regex still allows the test to pass. If the producer returns `status: REJECTED`, the `by_equality` matcher must catch the discrepancy.

**Consumer-side stub** uses the request conditions to decide whether to return the sample response. If the client sends an invalid `sku` or a mismatched required header, the stub will not match and the consumer test will fail or receive an unexpected response.

**Note:** `acceptedQuantity` in the response is only type-checked. The contract does not yet say `acceptedQuantity` must equal the `quantity` from the request; to commit to that, you must describe/test that relationship explicitly.

## 17. Extracting Large Bodies to Files While Keeping Matchers

When a body is large, the YAML DSL supports referencing a fixture:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: application/json
  bodyFromFile: payloads/stock-available.json
  matchers:
    body:
      - path: $.quantity
        type: by_type
~~~

The file `payloads/stock-available.json` contains the actual JSON body and must be placed where SCC's resource resolution mechanism can find it. Matchers are still written **inside the YAML contract**, and JSONPaths must point to fields that exist in the fixture.

For byte payloads, some DSL versions support `bodyFromFileAsBytes`. Only choose this for binary payloads when your plugin version and pipeline genuinely handle bytes properly.

Do not treat fixture files as minor content that can be changed arbitrarily: changing fields, data types, or structure in a fixture changes generated tests and stubs, which can introduce a **breaking change** for consumers.

## 18. Distinguishing YAML DSL from Groovy DSL

Both Groovy and YAML express contracts, but their matcher syntax differs.

**Groovy DSL:**

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        url '/api/reservations'
        body(sku: 'SKU-123')
        bodyMatchers {
            jsonPath('$.sku', byRegex('^SKU-[A-Z0-9-]+$'))
        }
    }
    response {
        status CREATED()
        body(reservationId: 'RSV-1001')
        bodyMatchers {
            jsonPath('$.reservationId', byRegex('^RSV-[0-9]+$'))
        }
    }
}
~~~

**Conceptually equivalent YAML DSL:**

~~~yaml
request:
  method: POST
  url: /api/reservations
  body:
    sku: SKU-123
  matchers:
    body:
      - path: $.sku
        type: by_regex
        value: '^SKU-[A-Z0-9-]+$'
response:
  status: 201
  body:
    reservationId: RSV-1001
  matchers:
    body:
      - path: $.reservationId
        type: by_regex
        value: '^RSV-[0-9]+$'
~~~

Note:

- Groovy uses `bodyMatchers { jsonPath(..., byRegex(...)) }`.
- YAML uses `matchers: body: - path: ...; type: by_regex`.
- Groovy can express dynamic values using `consumer(...)`/`producer(...)` expressions; YAML focuses on **sample bodies and a separate matchers section**.
- When switching DSLs, re-check generated tests/stubs to confirm semantics did not change. You cannot simply rename the file extension and keep the same syntax.

In addition to Groovy and YAML, SCC also offers Java/Kotlin DSLs. These options suit project preferences and build tooling, but switching DSLs never removes the need to verify both producer and consumer.

## 19. Common YAML and Matcher Mistakes

| Symptom | Common cause | Resolution |
|---|---|---|
| Contract fails to parse | Wrong indentation, tabs, or misplaced `:` | Use spaces, validate structure with a YAML parser and run SCC generation |
| Test returns unexpected `status` or wrong body types | YAML infers `true`, numbers, strings, or null automatically | Explicitly quote values meant to be strings; keep booleans/numbers unquoted |
| Matcher has no effect | `matchers` placed at wrong level or nonexistent JSONPath | Place matcher under the right `request`/`response`, pointing to an actual sample field |
| Stub accepts invalid requests | Request matcher too broad or missing required headers/query params | Add conditions that truly belong to the API contract; test negative cases |
| Producer test fails on dynamic IDs | Using equality on dynamically generated fields | Use `by_regex`/`by_type` per actual constraints |
| Producer test passes despite invalid business data | Using `by_type` instead of required value/relationship constraints | Add equality, tighter regexes, or business assertions |
| Regex behaves unexpectedly | YAML escaping or unanchored regex | Quote regexes with single quotes, add `^`/`$` where needed, test edge inputs |
| JSONPath queries wrong key | Key contains dots or wrong nesting depth | Use appropriate bracket notation `$['key.with.dot']` |
| Array matcher fails to check size | Verifier array-size limitations or options | Inspect generated tests and configuration supporting `minOccurrence`/`maxOccurrence` |
| `by_command` causes test compilation error | Missing method in test base or incompatible parameter type | Provide method with matching signature; inspect generated source |
| Consumer test passes when producer changed API | Consumer still running against an older stub version | Pin the candidate commit's stub artifact; verify version in logs |
| Valid YAML contract generates no tests | Misconfigured plugin/contracts not found | Check contracts directory, plugin version, and build lifecycle/tasks |

The most common mistake is equating **valid YAML parsing** with an **accurate contract**. A YAML parser only checks document format; SCC interprets `matchers` and generates tests; producer/consumer tests verify communication correctness.

## 20. Checking Contracts from Local Dev to CI

### 20.1. Minimum verification on the producer

For a Maven project configured with the Spring Cloud Contract Maven plugin and test base:

~~~bash
# Generate tests, execute tests, and verify build lifecycle.
./mvnw clean verify
~~~

With Gradle configured with the Contract plugin:

~~~bash
# Run required test tasks and verify generated tests execute.
./gradlew clean test
~~~

Task names, generated test locations, and stub packaging can vary by plugin version; inspect actual logs instead of assuming all setups use identical paths. On Windows use the `mvnw.cmd` or `gradlew.bat` wrapper.

When reviewing results, verify that:

1. The YAML contract is discovered in the configured directory.
2. The sample request from the contract is sent by the generated test to real producer code.
3. Assertions based on `response.matchers` are actually generated and executed.
4. The response stub is generated from the intended contract and sample data.
5. No matcher was silently skipped due to bad syntax or missing support.

### 20.2. Verification on the consumer

The consumer uses **Stub Runner** to download and run the producer's stub. The test should use the consumer's **real HTTP client**, send a request matching `request.matchers`, and assert that the response is handled properly—for example, that the returned reservation ID is parsed successfully.

Tests should point to the candidate stub artifact with explicit group, artifact, version, and classifier. If the API renames `reservationId` to `id`, producer tests may pass after updating the contract; **consumer tests against the new stub** must catch that the old client can no longer read the expected field.

### 20.3. CI gates

~~~mermaid
flowchart LR
    A["YAML contract or code change"] --> B["Validate and generate producer tests"]
    B --> C{"Producer tests pass?"}
    C -- "No" --> X["Block PR/release"]
    C -- "Yes" --> D["Package candidate stub"]
    D --> E["Consumer tests using Stub Runner"]
    E --> F{"Consumer tests pass?"}
    F -- "No" --> X
    F -- "Yes" --> G["Proceed to pre-release checks"]
~~~

A reliable pipeline records the commit, Spring Cloud Contract version, generated tests executed, stub coordinates, and consumer results. Do not conclude compatibility from a green producer build alone or from consumer tests running against an outdated stub.

## 21. Three-Round Hands-On Lab

**Context:** Inventory Service is the producer; Checkout Service is the consumer. Checkout needs to query inventory and create reservations using JSON.

### Round A — Write a Basic Contract

1. Create a YAML contract for `GET /api/inventory/SKU-123`.
2. Declare `request.method`, `request.url`, and the `Accept` header; in `response`, declare `status: 200`, `Content-Type`, `sku`, `available`, and `quantity`.
3. Generate the producer test and confirm it invokes the endpoint.
4. Inspect the stub mapping or stub artifact to see the sample response the consumer will receive.

**Points to explain:** which fields are strings, booleans, and numbers; why you should not put `response.matchers` on every field when dynamic data is unnecessary.

### Round B — Add Appropriate Matchers

1. Write a `POST /api/reservations` contract with `clientRequestId`, `sku`, and `quantity`.
2. Use `request.matchers.body` to accept regex-matching request IDs and valid quantities.
3. Use `response.matchers.body` to verify `reservationId` matches the expected format, `status` equals `CREATED`, and `acceptedQuantity` is numeric.
4. Test the producer returning `reservationId: "INVALID"`: the generated test must catch the failure.
5. Test the consumer sending a bad `sku`: the stub should not match the success scenario.

**Points to explain:** why request and response matchers act on **two different verification steps**.

### Round C — Test Breaking Changes

1. Change the producer and contract so the response only returns `id` instead of `reservationId`.
2. Observe that producer tests can pass when aligned with the new contract.
3. Build a **new candidate stub** and run the old Checkout consumer tests.
4. Record the failure when the client still reads `reservationId`.
5. Propose a safe upgrade path: serve both the old and new fields during a transition period before removing the old field.

**Submission evidence:** YAML files, generated tests, producer run logs, candidate stub version, consumer test results, and an explanation of which matcher conditions were verified.

## 22. Pre-Merge Checklist for YAML Contracts

- [ ] `request` contains the exact method, URL/path, query, headers, and body sent by the consumer.
- [ ] `response` clearly states the status, headers, body, and semantics the producer must guarantee.
- [ ] YAML fields have the right types, and strings prone to type inference are quoted.
- [ ] `matchers` are on the **right side** and at the right level of the YAML structure.
- [ ] Every JSONPath `path` points to an element that exists in the sample body.
- [ ] Regexes allow only genuinely intended formats; `regexType` is set when needed.
- [ ] Values that must remain fixed still use equality rather than being loosened to `by_type`.
- [ ] Dynamic values are not unnecessarily locked to a single sample value.
- [ ] Request matchers have enough constraints so Stub Runner does not falsely match unrelated requests.
- [ ] Generated producer tests are actually generated, executed, and asserting matchers as expected.
- [ ] Candidate stubs are built from the exact commit/contract and the consumer uses the right version.
- [ ] Potentially breaking field, status, or header changes have been verified by the consumer.

## 23. Self-Check Questions

**1. Why isn't `matchers` placed once at the root level of YAML?**

Because matchers serve two purposes depending on the side of communication. `request.matchers` describes conditions the stub's incoming request must satisfy; `response.matchers` describes how to verify the producer's response. Placing them in the right location lets SCC generate stubs and tests with the intended semantics.

**2. What is the difference between `by_equality` and `by_type`?**

`by_equality` requires the value to equal the sample; `by_type` allows the value to vary as long as its type matches the sample. If business logic requires `status: CREATED`, checking only that it is a string is insufficient.

**3. Why might `by_regex` for `quantity` need `regexType`?**

Because `quantity` is a JSON number; a regex by default may be interpreted as a string check. `regexType: as_integer` tells SCC to match the value as an integer where supported.

**4. Why quote regexes with single quotes in YAML?**

Because regex characters like backslashes can be processed differently by the parser inside double-quoted strings. Using single quotes typically keeps regexes readable and reduces escaping bugs, though you should still test expressions against real inputs.

**5. Does a passing producer test prove older consumers are compatible?**

No. If both the producer and the contract change together for a new version, generated tests can still pass while older consumers fail to deserialize the response. You must run consumer tests against the **candidate stub** to detect breaking changes.

## 24. References

- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): DSL variants and YAML contract structure.
- [Spring Cloud Contract – Dynamic properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): matcher semantics, `type`, `predefined`, `regexType`, and request/response differences.
- [Spring Cloud Contract – YML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): fields and matcher types supported in YAML.

**Version note:** Examples are based on the YAML DSL syntax in current Spring Cloud Contract documentation. Field names, matcher options, and advanced features may vary by the version pinned in your project; always cross-check documentation for your exact plugin version and verify via actual generated tests/stubs.

---

**Key takeaway:** A YAML contract cleanly separates **`request`** (conditions sent by the consumer) and **`response`** (commitments returned by the producer). Matchers in `request` help stubs accept the right payloads; matchers in `response` help generated producer tests enforce constraints. Use tight-enough matchers, accurate JSONPaths, and correctly versioned candidate stubs to catch incompatible API changes before release.
