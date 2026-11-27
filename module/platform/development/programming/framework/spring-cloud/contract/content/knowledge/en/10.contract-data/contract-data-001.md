# Designing Simple, Deterministic, and Consumer-Relevant Fixtures

## Learning Objectives

In **Spring Cloud Contract**, the **producer** is the service that provides an API or emits messages, while the **consumer** is the party that consumes that API or receives those messages. Contracts are described using the **Groovy/YAML DSL** to generate behavior tests on the producer side, while also generating stubs for the consumer to use via **Stub Runner**.

In the **Contract Data** chapter, this lesson focuses on a practical question: **how should you choose sample data (fixtures) so that tests are meaningful, reproducible, and independent of random environment details?**

After this lesson, you will be able to:

- Distinguish between a fixture, a contract, producer test data, and consumer-side stub responses.
- Choose a **small yet representative** fixture set for the consumer's actual decisions.
- Avoid unstable data caused by time, UUIDs, ordering, external data sources, or shared state.
- Know when to use **fixed values**, when to use **matchers**, and producer/consumer value pairs.
- Organize fixtures for Groovy/YAML DSL, generated tests, Stub Runner, and CI pipelines.
- Evaluate whether a fixture accurately reflects the API semantics that the consumer depends on.

## 1. What is a fixture and what role does it play?

A **fixture** is intentional sample data used to set up or verify a test scenario. In contract testing, fixtures can appear in multiple places:

| Location | Example | Function |
|---|---|---|
| Request in contract | `GET /api/inventory/SKU-101` | Identifies the interaction being verified |
| Expected response in contract | `{"sku":"SKU-101","available":true,"quantity":8}` | Commits the behavior the producer must satisfy |
| Producer test background data | Inventory record `SKU-101` with quantity `8` | Enables the real producer to return results matching the contract |
| Stub generated from contract | Deterministic JSON response for matching requests | Helps the consumer verify API-calling logic and response handling |
| Consumer assertion data | “If `available=true`, allow proceeding with the order” | Confirms the consumer actually understands and uses the contract |

These layers of data are **related, but not automatically identical**. For example, `SKU-101` in the contract will not automatically create inventory in the producer's database. The producer team must set up the appropriate test state; otherwise, the generated test may return `404` instead of `200` even if the DSL is valid.

Simple diagram:

~~~mermaid
flowchart TD
    C["Groovy/YAML contract<br/>request and expected response"] --> P["Generated producer test"]
    C --> S["Stub artifact"]
    D["Producer test data<br/>SKU-101, quantity=8"] --> P
    P --> A["Producer implementation"]
    S --> R["Stub Runner"]
    R --> U["Consumer test<br/>real client and logic"]
    A --> V{"Satisfies contract?"}
    U --> W{"Consumer handles correctly?"}
~~~

The **contract** states what behavior both sides have committed to; the **fixture** provides concrete examples to verify that commitment; the **stub** simulates the producer from the contract. Even if the stub returns the right result, generated tests against the real producer are still required. Even if producer tests are green, the consumer still needs to test how it uses the stub.

## 2. What does “simple, deterministic, consumer-relevant” mean?

A useful fixture must satisfy three properties at the same time.

### Simple (minimal)

Include only the fields and scenarios needed for the behavior under test. A JSON payload with 50 dummy fields makes it hard for reviewers to see which fields actually matter. A short fixture is usually easier to maintain as long as it still captures the necessary business conditions.

For example, Checkout only needs:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

Do not arbitrarily add `warehouseManager`, `lastMaintenanceAt`, `supplierInternalCode`, and similar fields if they are not part of the interface the producer has committed to.

**Minimal does not mean omitting required fields.** If the API contract requires `currency` to interpret `price`, keep both; dropping `currency` just to make the fixture shorter will lose semantics.

### Deterministic (stable)

When running the same contract revision and the same test configuration, the data must lead to **predictable results**, independent of timezone, execution date, randomness, a teammate's data, or external network services.

| Data prone to instability | More deterministic alternative |
|---|---|
| `LocalDateTime.now()` | Fixed test timestamp or format matcher |
| New UUID on every run | Fixed sample ID in stub and matcher on producer if real ID varies |
| Calling `findFirst()` on an unordered set | Define a sort rule if the consumer relies on order |
| Database shared across tests | Seed isolated data, clean up, and isolate state |
| Live external API | Fake/mock at dependency boundary or controlled test environment |
| Exchange rate/product price fetched directly from live API | Fixed values in test dataset with an explicit update rule |

Determinism **does not require the real producer to always return the same UUID/timestamp in production**. The contract can use a representative value on the stub side for easy consumer testing, while using a matcher on the producer side to accept valid varying values.

### Consumer-relevant

Each fixture should correspond to **a decision branch** in the consumer:

- `available=true`, `quantity > 0` → allow the user to proceed.
- `available=false`, `quantity=0` → display an out-of-stock message.
- Product does not exist → handle `404` and error code `SKU_NOT_FOUND`.
- Malformed request → handle `400` with a validation error code.

If two fixtures differ only by product code, and the consumer handles them identically with no business difference, there is usually no need to keep both.

## 3. Running Example: Checkout and Inventory

**Inventory Service** is the producer of the endpoint:

~~~http
GET /api/inventory/{sku}
Accept: application/json
~~~

**Checkout Service** is the consumer. The Checkout team raises the questions that need verification:

1. If the item is in stock, can the flow proceed to order confirmation?
2. If the quantity is 0, is an out-of-stock state displayed instead of reporting a network error?
3. If the SKU does not exist, can `404` be distinguished from an empty list?
4. If the SKU is malformed, is the `400` input error recognized?

We propose a **small fixture matrix**:

| Scenario code | Request | HTTP status | Key response | Consumer branch |
|---|---|---|---|---|
| `stock-available` | `GET /api/inventory/SKU-101` | `200` | `available: true`, `quantity: 8` | Allow proceeding |
| `stock-empty` | `GET /api/inventory/SKU-EMPTY` | `200` | `available: false`, `quantity: 0` | Report out of stock |
| `sku-not-found` | `GET /api/inventory/SKU-404` | `404` | `code: SKU_NOT_FOUND` | Handle not found |
| `invalid-sku` | `GET /api/inventory/INVALID!` | `400` | `code: INVALID_SKU` | Handle invalid input code |

The SKU codes, quantities, and validation rules above are **illustrative conventions** agreed upon by both teams. Those rules must be agreed on upfront; Spring Cloud Contract does not automatically decide which products are “in stock”.

### Fixture for “in stock”

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

We choose `8` to illustrate a positive quantity. If the consumer only needs the boolean `available` and does not depend on the exact quantity, you should not write test logic asserting “must be exactly 8” everywhere. Conversely, if Checkout must enforce not buying more than `quantity`, the consumer test should use that exact `8` to test the boundary—for example, ordering `9` items must be blocked at the application layer.

### Fixture for “out of stock”

~~~json
{
  "sku": "SKU-EMPTY",
  "available": false,
  "quantity": 0
}
~~~

**Do not** use a contradictory fixture such as `available: true` with `quantity: 0` if the API defines `available` based on quantity > 0. Inconsistent fixtures cause tests to pass or fail for the wrong behavior.

### Fixture for errors

~~~json
{
  "code": "SKU_NOT_FOUND",
  "message": "SKU does not exist"
}
~~~

The consumer should branch on **status** and a **stable error code** (`SKU_NOT_FOUND`), not on the entire `message` sentence. If the message can be localized or changed, use an appropriate matcher/structural check; do not turn prose wording into a commitment unless necessary.

## 4. Writing a Fixture as a Simple Groovy Contract

Suppose the producer has integrated Spring Cloud Contract Verifier. We write a representative file for the `stock-available` case at `src/test/resources/contracts/inventory/stockAvailable.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'In stock for SKU-101'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8
        )
    }
}
~~~

Key points to note:

- `method`, `url`, and `Accept` are the conditions the consumer sends.
- `status`, `Content-Type`, and the three body fields are the behavior the producer commits to.
- `quantity: 8` is a **number**, `available: true` is a **boolean**, and `sku` is a **string**.
- This is **one concrete scenario**; it does not cover every SKU or every quantity.

Spring Cloud Contract generates the **producer contract test** from the DSL and builds the matching **stub**. For the generated test to run, the producer must set up a test environment containing `SKU-101`. Adding the Groovy file alone does not seed the database.

### When keeping fixed values makes sense

Keeping response values fixed is a good choice when:

- The fixture is dedicated to a specifically identified scenario, such as `SKU-101`.
- The producer test **controls the state** and must prove the behavior of returning exact quantity `8`.
- The consumer needs a predictable representative response to test its own flow.

If the actual quantity is computed from an uncontrolled source and cannot be reproduced, prefer isolating the dependency or using an appropriate matcher for the varying part. Do not simply replace `8` with `.*`, as doing so can lose data type checks and business rule validation.

## 5. YAML DSL: Same Fixture Without Duplicating Contracts

Spring Cloud Contract also supports the **YAML DSL**. This is an alternative way to write the same scenario, for example `stockAvailable.yml`:

~~~yaml
description: 'In stock for SKU-101'
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
    quantity: 8
~~~

This YAML is equivalent in intent to the Groovy DSL above. **In a real build, choose one of the two formats for that scenario**; do not place both `stockAvailable.groovy` and `stockAvailable.yml` as two independent contracts for the same request just to test syntax, because that can produce duplicate stub mappings and increase maintenance cost.

### Watch out for YAML types that easily corrupt fixtures

~~~yaml
# Correct when quantity is a number and available is a boolean.
body:
  sku: '00123'
  quantity: 8
  available: true
~~~

~~~yaml
# Wrong types if the contract requires number and boolean.
body:
  sku: '00123'
  quantity: '8'
  available: 'true'
~~~

The values in the second snippet **are all strings**. A test that only compares rendered text can easily miss the difference; the contract must protect the data types that the consumer deserializes. For SKU codes with leading zeros, always quote them if you need to preserve the value intact as a string.

### Empty data is not the same as error data

An API returning a **list** may specify `200 OK` and an empty JSON array when there are no results. In that case:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body: []
~~~

`body: []` represents an empty array. It is different from `body: {}` (empty object), `body: null`, the string `'[]'`, and a `204 No Content` response. The fixture must match the exact **shape** that the consumer actually parses; substituting one type for another just because they are “all empty” can break the consumer.

## 6. Fixtures Are Not Just Responses: Preparing Producer Test State

A common source of errors: the contract specifies that `SKU-101` returns `200`, but when the generated test runs, the database is empty so the real producer returns `404`.

You need to design both the **background data** and the **test preconditions**:

| Contract | State the producer must have before the test | Expected result to verify |
|---|---|---|
| `stock-available` | SKU-101 in stock with 8, sellable | `200`, `available=true`, `quantity=8` |
| `stock-empty` | SKU-EMPTY in stock with 0 | `200`, `available=false`, `quantity=0` |
| `sku-not-found` | SKU-404 does **not** exist | `404`, `code=SKU_NOT_FOUND` |
| `invalid-sku` | Validation rejects the `!` character | `400`, `code=INVALID_SKU` |

Depending on the project architecture, you can seed a test database, use a fake repository, or mock the dependency layer. Spring Cloud Contract generates interface tests; it **does not automatically construct the full application state**.

### Illustrating state preparation

Java pseudocode example, **not a complete runnable base class**:

~~~java
// Illustrates the idea in the producer test setup.
@BeforeEach
void setUp() {
    inventoryRepository.clearTestData();
    inventoryRepository.save(
        new StockItem("SKU-101", true, 8)
    );
    inventoryRepository.save(
        new StockItem("SKU-EMPTY", false, 0)
    );
    // Intentionally do not create SKU-404.
}
~~~

In a real application, `clearTestData()` and `StockItem` depend on your repository/domain design. The pseudocode is meant to illustrate the **data preparation sequence**, not to require creating those exact APIs. Use a dedicated test database or fake; never delete data on a database serving real users.

Principles when setting up fixtures:

1. **Isolation:** tests must not depend on execution order or data left behind by other tests.
2. **Reproducibility:** each run receives the same input data and expected state.
3. **Intentionality:** a `404` test must ensure the corresponding SKU does not exist.
4. **Explicitness:** if a test relies on an inventory mock, explicitly document what the mock returns.
5. **Cleanup:** use transaction rollback, reset fakes, reinitialize datasets, or an appropriate mechanism to avoid cross-test pollution.

If tests run in parallel, sharing a single database or mutable fake can cause race conditions. Design an appropriate isolation mechanism; running sequentially is only a temporary workaround until the shared state source is fixed.

## 7. Dynamic Data: Distinguishing Concrete Examples from Rules to Verify

Not every field should be hardcoded in producer tests. For example, a response when creating a reservation:

~~~json
{
  "reservationId": "RSV-1001",
  "accepted": true
}
~~~

`reservationId` is typically system-generated. The producer might generate `RSV-1002` on another run and still satisfy the interface, whereas the consumer needs a **concrete** value to test storing/displaying the ID.

Spring Cloud Contract supports **different values for the consumer and producer sides** in the Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Create valid reservation request'

    request {
        method 'POST'
        url '/api/reservations'
        headers {
            contentType(applicationJson())
        }
        body(
            requestId: $(
                consumer(regex('REQ-[0-9]{4}')),
                producer('REQ-1001')
            ),
            sku: 'SKU-101',
            quantity: 1
        )
    }

    response {
        status 202
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: $(
                consumer('RSV-1001'),
                producer(regex('RSV-[0-9]+'))
            ),
            accepted: true
        )
    }
}
~~~

**How to interpret each side correctly:**

| Field | Consumer/stub side | Producer/generated test side |
|---|---|---|
| `request.requestId` | Stub accepts IDs matching `REQ-[0-9]{4}` | Generated test sends a request with real `REQ-1001` |
| `response.reservationId` | Stub returns the **concrete value** `RSV-1001` for consumer tests to use | Generated test accepts IDs matching `RSV-[0-9]+` |
| `response.accepted` | Stub returns boolean `true` | Producer must return boolean `true` |

The names `consumer(...)` and `producer(...)` here represent **two perspectives on test values**. For the request, the consumer needs a rule so the stub accepts valid IDs; the producer needs a sample value so the generated test actually sends one. For the response, the producer needs a rule to validate dynamic IDs; the consumer needs a concrete result to test against.

**Note:** the `$(consumer(...), producer(...))` value pair and regex syntax above belong to the **Groovy DSL**. In the **YAML DSL**, dynamic values are configured in the `matchers` section according to the YAML schema; do not copy Groovy syntax verbatim into YAML.

### Matchers specific to YAML

If the producer returns a dynamic field but needs to guarantee its format, you can use `response.matchers.body`:

~~~yaml
description: 'Verify reservationId has valid format'
request:
  method: GET
  url: '/api/reservations/RSV-1001'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    reservationId: 'RSV-1001'
    status: 'ACCEPTED'
  matchers:
    body:
      - path: '$.reservationId'
        type: by_regex
        value: 'RSV-[0-9]+'
~~~

The body provides **one valid sample value** that the stub can return to the consumer. The matcher enforces the rule in the generated producer test. Do not put a `.*` matcher on every field: doing so can let invalid types or meaningless data slip through.

### Matchers do not replace all business constraints

Suppose the producer returns:

~~~json
{
  "available": true,
  "quantity": 0
}
~~~

A matcher checking that `quantity` is an integer will still accept `0`, but if the business rule specifies `available=true` only when `quantity > 0`, this data is still **semantically inconsistent**. You need an additional contract or business test to prove that relationship.

## 8. Choosing Fixture Strictness Based on Need

A useful rule of thumb: **fix data that matters to consumer decisions; use matchers for varying parts that still have clear rules**.

| Field | Fixture example | Recommendation | Why |
|---|---|---|---|
| `sku` in an in-stock scenario | `SKU-101` | Fixed | The scenario needs a clear identifier |
| `available` | `true` | Fixed or boolean check with semantics | Consumer branches on this value |
| `quantity` | `8` | Fixed when test data is controlled; add conditional tests if needed | Easy to test quantity boundaries |
| Auto-generated `reservationId` | `RSV-1001` on stub | Producer uses format matcher | Avoids test failures from valid changing IDs |
| `timestamp` | `2026-01-15T08:00:00Z` | Fixed on stub; matcher/test clock on producer | Avoids dependence on execution time |
| Error `message` | `SKU does not exist` | Only fix when the API commits to exact wording | Consumer should handle `code` |
| `correlationId` | `corr-1001` | Format matcher or presence/type check | Value is generated per request |
| `tags` as an array | `["featured"]` | Match exact structure; only assert order if guaranteed | Avoids unintended ordering constraints |

If the author does not know whether the consumer depends on `quantity`, ask explicitly **what the consumer uses it for** before deciding on the fixture and matcher. Avoid assuming any field is “unimportant”.

### Time, UUIDs, and random numbers

Do not put `new Date()`, `UUID.randomUUID()`, or `System.currentTimeMillis()` directly into a contract file intending to get a different result every time. That makes snapshots, tests, and stubs hard to reproduce.

Practical approaches:

- **Freeze the clock** in producer tests if time is part of the behavior you need to prove.
- **Use regex/matchers** for producer-generated IDs/timestamps, while the stub returns a concrete sample value.
- **Specify timezone and format explicitly** (`ISO-8601`, offset, precision) if the consumer depends on them.
- **Use a fixed seed** for randomness if you genuinely need varied dummy data that remains reproducible.
- **Avoid deriving time from the CI environment** in the expected body.

Format-checking regexes alone may not be enough to prove calendar validity or ordering relationships like `createdAt <= expiresAt`. If the consumer relies on those semantics, add supplemental tests.

## 9. Managing Fixtures in External Files When Appropriate

When a JSON/XML body is long or shared across multiple tools, you can extract its content into a fixture file. Spring Cloud Contract provides mechanisms to read bodies from files:

| Data | Groovy DSL | YAML DSL |
|---|---|---|
| Text/JSON/XML file | `body(file('stock-response.json'))` | `bodyFromFile: 'stock-response.json'` |
| Binary file needing byte preservation | `body(fileAsBytes('sample.pdf'))` | `bodyFromFileAsBytes: 'sample.pdf'` |

Example organization on the producer side:

~~~text
src/test/resources/contracts/inventory/
├── stockAvailable.groovy
├── stockEmpty.groovy
├── stockNotFound.yml
└── fixtures/
    ├── stock-available.json
    └── stock-empty.json
~~~

If a Groovy contract in the `inventory` directory references `fixtures/stock-available.json`, for example:

~~~groovy
response {
    status 200
    headers {
        contentType(applicationJson())
    }
    body(file('fixtures/stock-available.json'))
}
~~~

**Alternative** YAML example for the same reference (no need to create two duplicate contracts):

~~~yaml
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  bodyFromFile: 'fixtures/stock-available.json'
~~~

The paths above are examples **for learners to organize their files**, not files generated automatically. Ensure the fixture file actually exists in the build sources, relative paths resolve properly for the plugin, and the file is committed alongside the contract.

### When to inline vs. when to extract to a file?

- **Inline** when the response is short (2–5 fields) and its meaning can be read directly inside the DSL.
- **Extract to a file** when dealing with long XML/JSON payloads, large text content, or binary files.
- **Do not extract files just so every contract has a fixtures folder**; too many tiny files make it hard for reviewers to cross-check requests and expected responses.
- If multiple contracts share one file, changing the shared file can affect **multiple behaviors**. Check all references before editing.
- For binary fixtures, use `fileAsBytes` / `bodyFromFileAsBytes` to preserve bytes; do not convert binary data to a String.

Extracting a fixture to a file does not replace defining status, headers, matchers, and business meaning in the contract.

## 10. Naming and Scenario Organization Principles

Fixture names should express **behavior**, not just a sequence number:

~~~text
Recommended:
  stockAvailable.groovy
  stockEmpty.groovy
  stockNotFound.yml
  invalidSku.yml

Confusing:
  test1.groovy
  contract2.yml
  data-final-new.json
~~~

A good directory structure helps locate contracts by API type or behavior, but you must preserve the **layout that the Spring Cloud Contract plugin is configured to scan**. Do not assume arbitrary folders will automatically be discovered by the plugin.

For each scenario, briefly document:

- Which consumer and which business flow uses it?
- What is the specific request and stub matching condition?
- What state does the producer need to set up?
- Which parts of the response are **committed**, and which fields are just illustrative data?
- If changed, which teams need to be notified and which consumer tests need to run?

This information can live in `description`, PR descriptions, or team docs depending on scale—no need to duplicate it across multiple places.

### Ensuring stub mappings are unambiguous

Two contracts with the **same method, path, headers, and request conditions** that return different responses will create unpredictable stub behavior if they match the same request.

For example, if both `stockAvailable.groovy` and `stockEmpty.groovy` describe `GET /api/inventory/SKU-101` without distinguishing conditions, the stub **cannot know on its own** whether to return `available=true` or `false`.

To avoid overlaps:

1. Differentiate requests using business-meaningful IDs/parameters/headers or appropriate matching conditions.
2. If the same request has state-dependent results, design explicit stub scenarios/states or use separate scenarios for each branch; do not assume the stub “remembers” inventory changes.
3. Review mapping priorities only when supported by the DSL/Stub Runner rules and agreed upon by the team.
4. Verify that consumer tests hit the intended scenario and do not accidentally match another stub.

## 11. How Are Messaging Fixtures Different?

For a `StockChanged` event, the producer might emit the payload:

~~~json
{
  "eventType": "StockChanged",
  "sku": "SKU-101",
  "quantity": 0
}
~~~

A consumer subscribed to this event might update the UI to “out of stock”. A message fixture should describe:

| Aspect | Example | Why it is needed |
|---|---|---|
| Event type | `StockChanged` | Consumer selects the right handler |
| Identifying key | `SKU-101` | Identifies the changed entity |
| New value | `quantity: 0` | Tests the out-of-stock branch |
| Key headers/metadata | Event type, content type, schema version if committed by API | Verifies routing/deserialization |
| Event ID/timestamp | Fixed sample or matcher | Allows dynamic data while preserving testability |

There is no need to generate dozens of random events to prove a handler processes `quantity=0`. However, if the consumer requires **idempotency**, handling **duplicate events**, **out-of-order delivery**, or **replayed events**, there must be dedicated tests for those behaviors.

A single message contract does not prove that the broker provides ordering, retry, or at-least-once delivery guarantees. That belongs to broker configuration and application design, and must be verified independently when business logic depends on it.

## 12. Common Fixture Design Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Picking a random record from the database | Test passes sometimes, returns `404` other times | Seed a fixed SKU or use a test fake/repository |
| Using real wall-clock time in expected responses | Tests fail depending on hour, timezone, or date | Fixed clock or format matcher |
| Overly large fixtures | Reviewers cannot tell which fields matter | Keep data just sufficient for the consumer branch |
| Overly sparse fixtures | Only `status: 200` even though consumer needs `available` | Describe the fields/types/semantics the consumer depends on |
| Business-contradictory fixtures | `available=true` while `quantity=0` | Define invariants and create consistent value sets |
| Mixing errors with empty data | `404` for a valid list query when `200 []` was committed | Separate empty-result branches from missing-resource errors |
| Wrong YAML quoting for types | `quantity: '8'` becomes a string | Keep proper number/boolean/string types |
| Overly broad regex | `.*` for IDs, statuses, values | Matchers that accurately reflect contract rules |
| Mocking the producer without proving HTTP behavior | Tests only confirm the stub matches itself | Run generated tests against a properly configured producer layer |
| Consumer test using a stale stub | Tests pass while the new API still breaks | Pin and synchronize the candidate stub version |
| Sharing mutable fixtures across tests | Tests fail depending on order or parallel execution | Reset/rollback/isolate state |
| Using real customer data | Risk of data exposure, hard to reproduce | Synthetic data with no secrets or personal information |

A fixture with fewer fields that aligns with **consumer decisions** is usually far better than a large snapshot copied randomly from a production database.

## 13. Integrating Fixture Verification into CI

Ideally, every contract change has traceability from sample data to tests on both sides:

~~~mermaid
sequenceDiagram
    participant Dev as Developer / CI
    participant K as Contract + fixture
    participant P as Producer tests
    participant A as Stub artifact
    participant U as Consumer tests
    Dev->>K: Update Groovy/YAML and sample data
    K->>P: Generate tests
    P->>P: Seed state and call producer
    alt Producer tests pass
        P-->>A: Package stub at same revision
        A-->>U: Stub Runner fetches exact version
        U->>U: Test consumer behavior with sample response
    else Producer tests fail
        P-->>Dev: Inspect fixture, contract, or implementation
    end
~~~

Verification gates to include:

1. **DSL check:** Groovy/YAML contracts parse cleanly, matchers reference valid fields, and fixture files exist and are included in the build.
2. **Generated producer tests:** the producer application is bootstrapped with deterministic test state; tests verify status, headers, and body against the contract.
3. **Candidate stub:** the stub is built from the **same contract revision** verified by the producer; the artifact carries a traceable version.
4. **Consumer tests with Stub Runner:** the consumer calls the stub through its real HTTP client and verifies decisions for in-stock, out-of-stock, not-found, and bad-request cases.
5. **Compatibility review:** if data types or semantics change, evaluate which stub/contract versions older consumers are using.

**Warning:** producer tests can pass if both the contract and the implementation change together in a way that breaks older consumers. CI must combine consumer tests, a dependency registry, and stub version management; successful test generation alone does not prove backward compatibility.

A useful build report should clearly record:

- Revision/commit of the contract and fixtures.
- Producer commit and generated test results.
- Stub artifact coordinates/version.
- Consumer commit and tests executed against that stub version.
- Uncovered cases or items requiring migration.

## 14. Practice Exercise: Cleaning Up a Messy Fixture

Problem: Checkout only needs to know which SKUs are in stock, the maximum orderable quantity, and how to handle missing products. A team proposes the following fixture:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8,
  "lastUpdated": "NOW",
  "requestId": "random-each-run",
  "warehouseManager": "Example Person",
  "supplierPhone": "000-000-0000",
  "internalCacheKey": "stock-live-101",
  "supplierCategory": "X",
  "debugFlag": "internal"
}
~~~

**Question 1:** Which fields can be removed from the contract if they are not part of the published API and the consumer does not need them?  
**Hint:** `warehouseManager`, `supplierPhone`, `internalCacheKey`, `supplierCategory`, and `debugFlag` are clear candidates; do not decide to remove fields from the API solely by editing the fixture without aligning with the interface owner.

**Question 2:** How should `lastUpdated` and `requestId` be handled?  
**Hint:** If the consumer needs these fields, use concrete sample values on the stub and matchers/a controlled clock on the producer; if they are not part of the published contract at all, do not add them just to make the fixture “look like production”.

**Question 3:** What additional fixtures are needed?  
**Hint:** At a minimum, `SKU-EMPTY` with `available=false`, `quantity=0`, and `SKU-404` returning `404` with error code `SKU_NOT_FOUND`. If business rules forbid ordering more than available stock, add a consumer test using a positive quantity to verify the over-limit case.

**Question 4:** How do you know the change does not break the consumer?  
**Hint:** Run generated producer tests and consumer tests against the **candidate stub** from the same revision, while also reviewing other consumers and currently deployed versions.

### Self-Check

- How do a fixture, a contract, and a stub differ?
- Why do producer tests need separate background data state even when sample JSON is already in the DSL?
- When should you fix `quantity=8`, and when should you use a matcher?
- Why can a fixture with `available=true` and `quantity=0` create a “green test” illusion while violating business logic?
- Why do matchers in requests and responses play different roles between consumer and producer?
- When is extracting `bodyFromFile` better than an inline body?
- Why can two stub mappings with identical request conditions but different responses cause unpredictable failures?
- Which metadata should be attached in CI to trace stub artifacts?

## 15. References and Takeaways

Official Spring Cloud Contract documentation:

- [How Can I Provide Dynamic Values to a Contract?](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-provide-dynamic-values.html): explains why requests/responses need sample values and matchers on each side.
- [Dynamic properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): `consumer/producer` pairs in Groovy DSL and the `matchers` section for YAML.
- [YML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): structure of YAML contract fields supported by the tooling.

**A good fixture is an intentional example of the behavior the consumer depends on.** Data should be small enough to understand, deterministic enough for reproducible tests, and realistic enough to exercise critical branches. When producer-generated values can vary, Spring Cloud Contract lets you combine **fixed examples on the stub side** with **matchers on the generated test side**. The producer must set up matching state; the consumer must test its logic against the exact stub artifact; and CI must tie both results to the same contract version to catch incompatible API or message changes early.
