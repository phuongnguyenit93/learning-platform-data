# Determinism of Fixtures and Generated Tests

## Learning objectives

In **Spring Cloud Contract**, producers and consumers rely on **Groovy/YAML DSL contracts** to agree on HTTP or messaging behavior. From these contracts, the tool generates **producer tests**, builds **stubs** consumed via **Stub Runner**, and integrates with **CI** to detect incompatible API changes.

A contract suite is trustworthy only if test outcomes are **deterministic**: the same code version, contract, fixture, and test conditions produce consistent results. If tests occasionally pass and occasionally fail due to clocks, UUIDs, element order, leftover data, brokers, or runner configuration, CI struggles to tell **real API changes** apart from **environmental noise**.

This lesson belongs to the **Contract Quality** chapter and helps you:

- Understand determinism across **fixtures**, **generated producer tests**, **stub mappings**, and **consumer tests**.
- Design fixed, readable sample data that still reflects the constraints consumers need.
- Use **concrete values** where producer tests must send requests, and **intentional matchers** where valid data is allowed to vary.
- Control clocks, timezones, UUIDs, database records, element ordering, stub state, and message delivery.
- Inspect generated tests and actual mappings rather than reading only the source DSL.
- Spot false passes caused by overly broad matchers, default 404 responses, or wrong stub artifact versions.
- Build CI quality gates, flakiness reproduction steps, and contract review checklists.

> **Principle:** determinism does not mean “hardcode every field.” It means **inputs, state, and acceptance criteria are controlled**, while legitimately variable values are verified with appropriate matchers.

## 1. What is determinism in contract testing?

Consider a verification run:

~~~text
Result = verify(
    producer_code,
    contract_DSL,
    fixture,
    runtime_configuration,
    dependency_versions,
    external_state
)
~~~

A reliable test must yield **behaviorally equivalent** outcomes whenever the inputs above remain unchanged. That **does not require** identical log bytes, JSON object key ordering, or millisecond-identical execution times.

For example:

- A producer returning a new UUID on each call is valid **if the contract only requires a properly formatted UUID**.
- A producer returning different stock quantities because another test decremented inventory is **non-deterministic** when the scenario requires fixed stock.
- JSON object key reordering normally leaves JSON semantics unchanged; byte-string assertions can cause pointless flakiness.
- JSON array element reordering **can be a contract bug** if the consumer depends on ordering; never delete ordering checks just to make tests green.
- A messaging test timing out because a shared broker or another consumer stole the event indicates unisolated fixtures/infrastructure.

Determinism can be broken into five layers:

| Layer | Question to answer | Examples to control |
|---|---|---|
| **Inputs** | What exact request does the producer test send? | Method, URL, body, headers, IDs |
| **State** | What baseline data does the producer hold when tests run? | DB rows, mock returns, queue contents |
| **Time and randomness** | How are variable-value sources handled? | `Clock`, UUID supplier, timezone |
| **Acceptance criteria** | Which exact interface invariants does the test verify? | Status, JSON types, regex, ordering |
| **Toolchain/artifacts** | From which versions were tests and stubs generated? | Plugin, JDK, contract commit, stub digest |

Determinism is **a property of the entire chain**, not just a single JSON fixture file.

## 2. Why flakiness in contract tests is especially dangerous

Spring Cloud Contract has two verification endpoints:

~~~mermaid
flowchart TD
    A["Groovy/YAML contract"] --> B["Generated producer test"]
    A --> C["Generated stub mappings"]
    B --> D["Producer implementation"]
    D --> E{"Producer test PASS?"}
    E -->|No| X["Do not publish verified stub"]
    E -->|Yes| F["Versioned :stubs artifact"]
    C --> F
    F --> G["Stub Runner"]
    G --> H["Consumer client/handler test"]
    H --> I{"Consumer PASS?"}
    I -->|Yes| J["Compatibility evidence"]
    I -->|No| K["Investigate contract/client/mapping"]
~~~

If producer tests fail intermittently, teams tend to rerun until green and ignore the report. If consumer tests pass due to stale stubs or overly loose matchers, CI can **miss a breaking change**.

A solid quality gate must distinguish:

1. **Contract error:** consumer requirement not yet accepted by producer or misstated in DSL.
2. **Implementation error:** producer code fails to satisfy the agreed contract.
3. **Fixture error:** test data was improperly prepared or not reset.
4. **Generated assertion error:** DSL/matchers produce overly weak or overly tight conditions.
5. **Infrastructure error:** time, broker, ports, repositories, concurrency, artifact versions.

Do not “fix” issues simply by setting huge timeouts or passing `--rerun-tasks` until one run passes.

## 3. Running scenario: Inventory serving Checkout

Suppose the Inventory producer exposes:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

When tests start with seeded data:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8,
  "checkedAt": "2026-01-15T10:00:00Z"
}
~~~

Checkout consumer uses `sku`, `available`, and `quantity`, and displays `checkedAt`.

There are three kinds of expectations:

- `sku` must match **SKU-101** so the response matches the requested item.
- `available` must be **boolean** and `quantity` must be **number**; `8` may need to be exact in a concrete stock-check scenario.
- `checkedAt` may be the **current valid time** in production; in fixtures, use a fixed instant or a format/time matcher appropriate to the API's responsibility.

Teams should not build fixtures by reading arbitrary rows from a dev database or calling `new Date()` inside the DSL.

### A Groovy contract with a fully fixed fixture

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'SKU-101 has deterministic stock'

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
            quantity: 8,
            checkedAt: '2026-01-15T10:00:00Z'
        )
    }
}
~~~

This is an easy-to-understand baseline: generated tests verify a fixed response, and Stub Runner provides a stable sample body. However, it works only if the producer test setup **actually controls** `checkedAt` and stock. If the producer intentionally uses the live clock, requiring equality with a fixed instant will cause unintended test failures.

### Equivalent YAML DSL

~~~yaml
description: 'SKU-101 has deterministic stock'
request:
  method: GET
  url: /api/inventory/SKU-101
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-101
    available: true
    quantity: 8
    checkedAt: '2026-01-15T10:00:00Z'
~~~

Pick only one of these two files for the same real scenario if they share overlapping request matchers. **Quote timestamps in YAML** so parsers in different environments do not auto-coerce their data types.

## 4. What criteria must a good fixture satisfy?

A fixture is sample input data or state establishing preconditions for a test scenario: stock snapshot, database rows, JSON request, message payload, mock return, or external file.

### Five design criteria

1. **Clear identity:** `SKU-101`, `customer-test-001`, `order-001` instead of “the first row in the DB.”
2. **Sufficient for the use case:** includes required fields and business relationships without stuffing the entire schema.
3. **Predictable outcomes:** same setup produces the same status, body, and side effects.
4. **Independent of other tests:** passes whether run alone or in reversed order.
5. **Free of secrets and real user data:** synthetic data safe to publish inside a stub JAR.

A small fixture example:

~~~json
{
  "sku": "SKU-101",
  "stockOnHand": 10,
  "reserved": 2,
  "availableToSell": 8
}
~~~

From this follows the business invariant:

~~~text
availableToSell = stockOnHand - reserved = 10 - 2 = 8
~~~

A producer test could mock the service to return `8` directly, but if the goal is to verify the calculation in the domain service, **run the real service in the test and seed 10 and 2**, rather than mocking the exact result you want to verify.

### Trade-off table

| Fixture approach | Strengths | Risks |
|---|---|---|
| Fixed literal JSON/POJO | Readable, easy to reproduce | May be too strict for dynamic fields |
| Parameterized test data builder | Reusable, meaningful field names | Hidden defaults or auto-random values cause confusion |
| Seeded deterministic factory | Controlled intentional randomness | Still call-order dependent if sharing an RNG |
| SQL seed / transactional test | Exercises real persistence | Cleanup, sequences, parallel tests need care |
| Live dev/staging database | Looks realistic | Unisolated, non-reproducible, sensitive data |
| `now()`/`randomUUID()` per setup | Looks realistic | Easily fails tests with fixed expectations |
| Stateful stub server | Supports multi-step flows | Can depend on test/request execution order |

**Fixing data does not mean omitting edge cases.** Create distinct fixtures for out-of-stock, missing SKU, zero quantity, authorization, and temporary failures, with **controlled inputs for each case**.

## 5. Common sources of non-determinism

| Source | Symptom | Primary mitigation |
|---|---|---|
| System clock | Passes before midnight, fails after midnight | Inject `Clock` or use time matchers |
| Timezone/locale | Timestamp and number formats differ across machines | Fixed UTC/locale in tests; contract specifies format |
| UUID/randomness | Different ID each run | Inject generator or use type/format matchers |
| Shared database | Stock altered by another test | Isolated DB, rollback/cleanup, ordered seeding |
| Auto-increment/sequence | ID 1 on dev machine, ID 42 on CI | Do not assert sequence IDs unless contracted |
| Undefined collection order | Array order shifts across queries/hash iteration | Sort in producer or assert order-independent if API allows |
| Asynchronous messaging | Arrival timing varies | Correlation ID, isolated queue, bounded await |
| External network | Timeouts, changing upstream data | Mock boundary, testcontainers, or separate network tests |
| Random port | Consumer calls wrong port | Read Stub Runner port at runtime |
| Mutable artifact version | Consumer runs against old stub | Pin version/commit/digest |
| Parallel test execution | State cross-contamination | Namespaces, resource locks, isolation |
| File encoding/newlines | Text/binary bodies differ | UTF-8, explicit encoding, canonical fixtures |

This table is a checklist of areas to investigate, not advice to “mock everything.” Choose the **boundary** matching what the contract test is genuinely responsible for proving.

## 6. Concrete values vs. matchers: asymmetry across the two sides

Spring Cloud Contract provides **dynamic properties** so a single contract can produce:

- **An appropriate request matcher for the stub** called by the consumer.
- **A concrete request** that generated producer tests can send.
- **A concrete response** returned by the stub to the consumer.
- **A response matcher** letting generated producer tests accept valid dynamic producer data.

Official documentation explains this asymmetry in [How to Provide Dynamic Values](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-provide-dynamic-values.html).

| Message part | In generated producer tests | In consumer Stub Runner |
|---|---|---|
| **Request** | Needs a **concrete** value to send to the real producer | Can use a **matcher** to accept multiple valid requests |
| **Response** | Can use a **matcher** to check the real producer returns valid values | Usually returns a **concrete sample value** for consumer tests |
| **Goal** | Prove implementation satisfies contract | Prove consumer handles the described interface |
| **Risk if misdesigned** | Flaky tests or overly loose assertions | Stub fails to match real requests or returns meaningless fixtures |

A common point of confusion is `consumer(...)` vs. `producer(...)`. In Groovy DSL, `consumer`/`client`/`stub` relate to the stub/consumer side; `producer`/`server`/`test` relate to producer verification. **Exact meaning also depends on whether the value sits in `request` or `response`**, so inspect generated artifacts rather than guessing from method names alone.

## 7. Good example: dynamic request, reproducible producer test

Checkout sends a reservation request:

~~~http
POST /api/inventory/reservations HTTP/1.1
Content-Type: application/json

{
  "sku": "SKU-101",
  "quantity": 2,
  "clientRequestId": "c6f90433-e8a0-496b-a1b8-d47ff73e6421"
}
~~~

In production, `clientRequestId` changes on every request. If the stub matches only **one fixed UUID**, many valid consumer tests will receive a WireMock unmatched response.

In Groovy DSL, the request body can hold a **concrete example** while attaching a request matcher:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Create reservation with UUID clientRequestId'

    request {
        method 'POST'
        url '/api/inventory/reservations'
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            quantity: 2,
            clientRequestId: 'c6f90433-e8a0-496b-a1b8-d47ff73e6421'
        )
        bodyMatchers {
            jsonPath('$.clientRequestId',
                byRegex('[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'))
        }
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: 'RSV-1001',
            sku: 'SKU-101',
            reservedQuantity: 2,
            status: 'ACTIVE'
        )
    }
}
~~~

**Expected generator output:**

- Producer tests send the exact literal `clientRequestId=c6f90433-...` and seed fixtures for that request.
- Stub mapping includes a matcher for `$.clientRequestId`, allowing consumers to send other UUIDs in the same format.
- `sku` and `quantity` remain constrained to the example, rather than accepting arbitrary SKUs or quantities undefined by the contract.
- Stub returns sample response `RSV-1001`, giving the consumer deterministic data to assert on.

`bodyMatchers` and `jsonPath(..., byRegex(...))` are documented in [Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html).

**Note:** this is a single sample request contract. It does not prove idempotency, concurrency, or accurate stock deduction after reservation. Those guarantees require separate contract cases and/or integration tests.

## 8. Dynamic ID in response: assert the right invariant

Suppose the producer generates a new reservation ID on every call:

~~~json
{
  "reservationId": "RSV-4821",
  "sku": "SKU-101",
  "reservedQuantity": 2,
  "status": "ACTIVE"
}
~~~

If the response DSL hardcodes `RSV-1001` with equality, generated tests fail even though the producer honors the interface “ID starts with RSV- followed by four digits.”

You can keep a **concrete sample response** for the stub while using a **response matcher** in producer tests:

~~~groovy
response {
    status 201
    headers {
        contentType(applicationJson())
    }
    body(
        reservationId: 'RSV-1001',
        sku: 'SKU-101',
        reservedQuantity: 2,
        status: 'ACTIVE'
    )
    bodyMatchers {
        jsonPath('$.reservationId', byRegex('RSV-[0-9]{4}'))
    }
}
~~~

This snippet is the **response block** of a complete `Contract.make`, not a standalone DSL file.

When artifacts are generated:

- **Consumer stub response:** can return `RSV-1001`.
- **Generated producer test:** validates `reservationId` by regex rather than forcing `RSV-1001`.
- `sku`, `reservedQuantity`, and `status` remain checked per DSL requirements.
- A producer returning `reservationId="oops"` fails the matcher.
- If the real ID must be a UUID, use the agreed **UUID matcher/format**, not `RSV-...` as a generic rule.

**Do not use `.*` for every dynamic field.** It permits empty strings and malformed values, producing false positives. Relax only the genuinely dynamic field, and only within contract boundaries.

## 9. YAML DSL: dynamic matchers without embedded Groovy

In YAML, the `matchers` section can express equivalent rules without embedding Groovy expressions inside the body.

Example with dynamic request ID and format-checked response ID:

~~~yaml
description: 'Create reservation, ID validated by format'
request:
  method: POST
  url: /api/inventory/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-101
    quantity: 2
    clientRequestId: c6f90433-e8a0-496b-a1b8-d47ff73e6421
  matchers:
    body:
      - path: $.clientRequestId
        type: by_regex
        value: '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: RSV-1001
    sku: SKU-101
    reservedQuantity: 2
    status: ACTIVE
  matchers:
    body:
      - path: $.reservationId
        type: by_regex
        value: 'RSV-[0-9]{4}'
~~~

**This is a replacement for the Groovy file—do not keep both with the same request matcher.** The `by_regex` name and `matchers.body` structure are documented in [Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html) and [YAML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html).

Some matchers and options vary across Spring Cloud Contract versions. Check the schema docs for your pinned plugin version and inspect the actually generated tests and mappings.

**Do not confuse YAML with plain JSON:** scalars like `true`, `8`, `null`, and timestamps must be declared/quoted properly so the parser preserves the right types.


## 10. Matchers: flexible enough, yet never “swallow” bugs

Determinism requires both **stability** and **discrepancy detection**. Overly strict matchers turn tests red on valid dynamic data; overly broad matchers leave tests green when the API is broken.

| Data | Matcher/check to consider | Avoid |
|---|---|---|
| HTTP status | Equality with `200`, `201`, `404`, etc. per case | “Any status” |
| `sku` from request | Equality with `SKU-101` | Regex `.*` if consumer needs the exact SKU |
| `quantity` | Concrete value per case or number + invariant | Accepting strings when schema requires number |
| Generated `reservationId` | UUID/ID regex or type/format matcher | Hardcoding an uncontrolled ID |
| `checkedAt` | ISO-8601 format + time milestone/relation if needed | Byte-string comparison coupled to timezone |
| API-ordered list | Assert exact order | Dropping order when it is a business requirement |
| Unordered list | Assert element set and identity | Relying on arbitrary database query order |
| Nullable field | Check presence/null per contract | Allowing both missing and null if consumer distinguishes them |
| Error body | Assert specific code + schema | Asserting only 404 (may be an unmatched stub) |
| Required header | Assert name/value and semantics | Deleting header matchers to avoid failures |

### When to use `byType`?

Example where `quantity` varies across a test group and the consumer only requires a number:

~~~groovy
response {
    status 200
    body(
        sku: 'SKU-101',
        quantity: 8,
        available: true
    )
    bodyMatchers {
        jsonPath('$.quantity', byType())
        jsonPath('$.available', byType())
    }
}
~~~

`byType()` avoids hardcoding numeric/boolean values, yet **does not prove** `quantity` is non-negative, `available` reflects `quantity`, or stock equals `8` per fixture. If those constraints matter to the consumer, add appropriate matchers/commands or supplementary integration tests.

### Reading a matcher as a contract statement

- “`reservationId` has format `RSV-####`” is a verifiable interface constraint.
- “`reservationId` is any string, including empty” may be insufficient for a consumer canceling a reservation.
- “`quantity` has number type” does not prove stock is available.
- “`availableToSell` equals `stockOnHand - reserved`” is a business constraint that may need service/domain-layer testing.

Never add a matcher solely to make tests PASS; explain **what the consumer depends on and why variation is allowed**.

## 11. Clocks: control `Instant` instead of freezing the entire JVM

A common source of flakiness:

~~~java
Instant checkedAt = Instant.now();
~~~

If the response contract expects a fixed timestamp, producer tests fail whenever the real clock advances. Good Java design is to **inject `java.time.Clock`**.

### Illustrative producer code

~~~java
package com.example.inventory;

import java.time.Clock;
import java.time.Instant;

public class StockTimestampService {
    private final Clock clock;

    public StockTimestampService(Clock clock) {
        this.clock = clock;
    }

    public Instant currentCheckTime() {
        return Instant.now(clock);
    }
}
~~~

In production, provide a `Clock.systemUTC()` bean:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ClockConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

In tests, supply a `Clock.fixed`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

When producer code uses `Instant.now(fixedClock)`, output is stable. In Spring Boot integration tests, override the `Clock` bean via `@TestConfiguration`/`@Primary` or the test-bean override supported by your Spring Boot version.

**Benefit:** you avoid mutating a JVM-wide clock, which leaks across tests and is especially dangerous under parallel execution.

### When should you not fake the clock?

If the contract only requires “return a validly formatted check timestamp,” use a timestamp matcher and verify time invariants in another test. Never force production APIs to return a constant instant just for tests, as that makes contracts unrealistic.

**Rule:** control the clock in tests when exact timestamps belong to the scenario, or use meaningful matchers when time naturally varies.

## 12. Timezone, locale, and precision are also part of fixtures

These strings can represent the exact same instant:

~~~text
2026-01-15T10:00:00Z
2026-01-15T17:00:00+07:00
2026-01-15T10:00:00.000Z
~~~

If the contract requires a **specific UTC format**, they are not byte-equivalent; if the contract only requires **the same Instant**, compare parsed timestamps rather than raw strings.

Checklist:

| Attribute | Decision required |
|---|---|
| **Timezone** | Mandatory UTC or any offset permitted? |
| **Format** | ISO-8601 string or epoch millis? |
| **Precision** | Seconds, milliseconds, or nanoseconds? |
| **Nullability** | Required, optional, or nullable? |
| **Semantics** | Event time, processing time, or reservation expiration? |
| **Monotonicity** | Must `expiresAt > createdAt` be verified? |

**Never call `TimeZone.setDefault(...)` globally for the JVM** when tests run in parallel or libraries depend on global timezone state. Prefer injecting clocks, configuring `ObjectMapper`, and comparing `Instant`/`OffsetDateTime` per contract.

### Locale-induced bugs example

If a service formats `quantity` as a string:

~~~text
1,234  // one thousand two hundred thirty-four in one locale
1.234  // may mean the same in another locale
~~~

then fixtures or CI runners using different locales produce different outputs. In JSON APIs, **prefer numeric `1234`** over locale-formatted strings unless the contract explicitly mandates display-formatted text.

In YAML, wrap timestamp strings in quotes so parsers do not auto-convert their type:

~~~yaml
checkedAt: '2026-01-15T10:00:00Z'
~~~

## 13. UUIDs, auto-increment IDs, and random values

IDs serve two distinct roles:

1. **ID as a controllable input:** generated producer tests need a specific literal to send.
2. **ID as producer-generated output:** response matchers need to verify validity without hardcoding an unguaranteed value.

### Anti-pattern: generating a UUID when the DSL is loaded

~~~groovy
// Do not use for reproducible contract data.
def generatedId = java.util.UUID.randomUUID().toString()
~~~

If similar code runs when the generator parses the DSL to construct request/response bodies, two generation runs produce different outputs. This complicates debugging and artifact comparison and risks coupling generated tests to mappings.

**Better approach:** keep a fixed exemplar request in the DSL and use a request matcher when valid consumers may send different UUIDs.

### When producer logic generates IDs

Inject a generator interface into the service and provide a deterministic test implementation:

~~~java
import java.util.UUID;
import java.util.function.Supplier;

Supplier<UUID> fixedIds = () ->
    UUID.fromString("c6f90433-e8a0-496b-a1b8-d47ff73e6421");
~~~

Production uses a fresh UUID supplier. Producer contract tests use a deterministic fixture/generator when a specific ID must be verified; otherwise let the real generator run and use a **UUID response matcher** when no specific ID value is mandated.

### Database auto-increment IDs

Do not assert `id=1` simply because a fresh database normally starts at 1. Earlier tests, migrations, sequence caches, or retries can shift the ID.

If the consumer only needs a valid, consistent ID across a workflow, assert **format, presence, non-emptiness, and cross-response correlation**. If a specific ID is part of the contract test, ensure fixtures/sequences truly control it.

## 14. Building a producer base test with reproducible fixtures

In `MockMvc` mode, Spring Cloud Contract generated tests usually extend a base class configured via `baseClassForTests` or `baseClassMappings`.

Assuming the producer defines `InventoryController`, `InventoryService`, and `StockResponse` with matching constructors/methods:

~~~java
package com.example.inventory.contracts;

import com.example.inventory.InventoryController;
import com.example.inventory.InventoryService;
import com.example.inventory.StockResponse;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public abstract class InventoryContractBase {

    @BeforeEach
    protected void prepareFixture() {
        InventoryService service = mock(InventoryService.class);

        when(service.findBySku("SKU-101"))
            .thenReturn(
                new StockResponse(
                    "SKU-101",
                    true,
                    8,
                    "2026-01-15T10:00:00Z"
                )
            );

        RestAssuredMockMvc.standaloneSetup(
            new InventoryController(service)
        );
    }
}
~~~

### What does this snippet establish?

- Generated producer tests invoke the **real `InventoryController`**.
- The service dependency is mocked to return the exact fixture for that SKU.
- Same request produces the same body, independent of any dev database.
- JUnit 5 `@BeforeEach` rebuilds the fixture before each test.
- No `Instant.now()` or `randomUUID()` appears in test setup.

**This snippet is a skeleton**: `InventoryController`, `InventoryService`, and `StockResponse` must be defined by your project with compatible constructors. If the REST controller relies on bean validation, security, global exception handlers, or custom serialization, `standaloneSetup` may not exercise the full web stack.

### Warning on false positives from mocking too deep

If stock calculation lives inside `InventoryService`, mocking `service.findBySku` to return `8` does not verify the real stock formula. Distinguish:

- **HTTP contract tests:** verify controller, status, fixture-matched JSON schema/fields, and routing.
- **Service/domain tests:** verify stock math, reservation semantics, and concurrency.
- **Full integration tests:** verify database, security, serialization, and behavior over real HTTP.

**A deterministic test that verifies the wrong boundary is still a low-quality test.**

## 15. Database fixtures: seeding, resetting, and isolation

If producer contract tests run against a full Spring Boot application context and real database (such as Testcontainers), baseline data must be controlled.

### Seeding principles

Example test table:

~~~text
inventory_items
+---------+----------+----------+
| sku     | on_hand  | reserved |
+---------+----------+----------+
| SKU-101 |       10 |        2 |
| SKU-404 |   absent |   absent |
+---------+----------+----------+
~~~

For `GET /api/inventory/SKU-101`, the producer must return `availableToSell=8`. For `SKU-404`, write a dedicated contract for `404` and its business error code.

Good setup steps:

1. Create the schema from official migrations or a structurally identical test schema.
2. Seed **only the minimal rows** needed for the scenario.
3. Clean/reset stateful data within the test scope **before** running.
4. Avoid hardcoding sequence IDs unless part of the contract.
5. Isolate databases, schemas, or namespaces across parallel suites.
6. Never use dev/staging databases holding mutable or real user data.

### Why `@Transactional` may not suffice

When tests call controllers in the same transaction via MockMvc, rollback isolates some changes. However, with `RANDOM_PORT`/real HTTP tests, requests run inside server thread transactions; the test method's transaction **does not automatically roll back commits made by the server**.

Over real HTTP, design cleanup/fixtures at the database/test-environment level: explicit transaction management, per-case truncate/reset, or isolated database containers.

**Never run destructive cleanup against shared staging or production environments.**

### Under parallel execution

If two tests update `SKU-101` simultaneously, you may observe:

~~~text
Test A expects quantity 8
Test B reserves 3 units
Test A receives quantity 5
~~~

That is a **test isolation** failure, not proof that the Inventory API is broken. You can:

- Assign distinct SKUs per test.
- Give each suite its own database or container.
- Reset state deterministically per test lifecycle.
- Disable parallelism for suites that cannot isolate, or use resource locks.

Never make contracts “stable” by relaxing `quantity` to match any number when the business case requires exactly `8`.

## 16. Inspect generated producer tests, not just the DSL

A common mistake is reading the source contract and assuming the generator checks everything intended.

Inspect **generated Java tests**, test reports, and executed counts.

### Checklist when reading generated tests

1. Was it generated from the right contract file and version?
2. Does it extend the expected `InventoryContractBase`?
3. Are request method, path, headers, and body sent **concretely** as expected?
4. Is the HTTP status code asserted?
5. Were any JSON body fields coerced in type or stripped of matchers?
6. Is `reservationId` asserted by regex or equality as designed?
7. Is `quantity` asserted as a number or loose enough to accept a string?
8. Does the test run through the producer's real controller/HTTP handler?
9. How many tests actually executed—were any skipped or filtered out?
10. Does any datum depend on clocks, DB state, randomness, or other tests?

Generated test locations vary by Maven/Gradle/plugin version; common conventions include:

~~~text
Maven:
  target/generated-test-sources/contracts/...

Gradle:
  build/generated-test-sources/contractTest/...
~~~

These paths are common conventions, **not guaranteed across all versions**. Check your plugin configuration and build logs.

### Never edit generated tests directly

If generated tests have wrong assertions, fix the **DSL/matchers or base test class**, then regenerate. Edits to generated Java under `target`/`build` are overwritten on the next run and mask source issues.

### Test reports are also a quality artifact

A CI job reporting `BUILD SUCCESS` with `0 generated producer tests` executed is not valid evidence. Check **test counts, skipped tests, failed tests**, and verify the artifact matches the right revision.

## 17. Inspect generated stub mappings and response fixtures

On the consumer side, Stub Runner runs a stub artifact holding WireMock HTTP mappings or message definitions. **Mappings are generated translations of the DSL**, not guaranteed 1:1 copies of source files.

Check:

- Which method/URL/header/body request matchers were emitted?
- Did dynamic fields translate into the intended regex/`bodyPatterns`?
- Do multiple mappings match the same request with conflicting responses?
- Is WireMock's default 404 being mistaken for a business 404 contract?
- Is the response body a proper JSON object or an escaped JSON string?
- Are `__files` referenced by `bodyFileName` present?
- Does the stub JAR have the right classifier and version?
- Do stub fixtures stay identical across two consecutive generations?

### Illustrative mapping, not mandated verbatim output

A simple WireMock mapping may look like:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-101",
    "headers": {
      "Accept": {
        "contains": "application/json"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "sku": "SKU-101",
      "available": true,
      "quantity": 8,
      "checkedAt": "2026-01-15T10:00:00Z"
    }
  }
}
~~~

This is a **hand-written behaviorally equivalent mapping**, not a claim that the plugin emits this exact format or key order. Inspect the real artifact to see the exact WireMock matchers and responses Stub Runner uses.

### Distinguishing unmatched 404 from business 404

If the consumer sends:

~~~http
GET /api/inventory/SKU-102
~~~

while only a mapping for `SKU-101` exists, WireMock returns a default `404`. That **does not prove** the producer implements the `SKU_NOT_FOUND` error contract.

A meaningful 404 contract should specify a concrete error body, e.g.:

~~~json
{
  "code": "SKU_NOT_FOUND",
  "message": "Product does not exist"
}
~~~

Consumer tests must assert `code` and request matching, not just status. Otherwise a URL typo can make a test “pass.”


## 18. Messaging fixtures: valid payloads can still produce flaky tests

With Spring Cloud Contract **message contracts**, a producer may emit messages over Kafka, RabbitMQ, or a configured messaging abstraction. Generated tests must trigger the producer publisher, observe the emitted message, and assert destination, headers, and payload.

An illustrative Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_changed'

    input {
        triggeredBy('publishStockChanged()')
    }

    outputMessage {
        sentTo('inventory-events')
        headers {
            messagingContentType(applicationJson())
        }
        body(
            eventType: 'StockChanged',
            eventId: 'evt-stock-101',
            sku: 'SKU-101',
            quantity: 8,
            occurredAt: '2026-01-15T10:00:00Z'
        )
    }
}
~~~

Assume the producer base class provides `publishStockChanged()` and an appropriate messaging test environment. This contract illustrates an event with a fixed payload. If the real producer generates `eventId`/`occurredAt`, use dependency injection or meaningful matchers instead of forcing production code to emit `evt-stock-101` at runtime.

### Why are messaging tests prone to non-determinism?

| Source of variation | Symptom | Remediation |
|---|---|---|
| Stale messages in queue/topic | Test receives an earlier event | Isolated destination/consumer group, controlled drain/reset |
| Shared consumer group across tests | Another test consumes the event | Dedicated namespace and consumer group |
| Asynchronous event arrival | Test asserts before listener finishes | Bounded await with finite timeout |
| Missing correlation ID | Test matches an event from another request | Correlate by `eventId`/`sku` or business key |
| Async publish after transaction commit | Test runs before commit completes | Synchronize readiness and transactional semantics |
| Shifting offsets/acks | Passes once, fails next run | Seed/reset offsets, clear broker/test-binder setup |
| Clock/UUID inside event | Payload differs across runs | Inject fixed clock/ID generator or use matchers |
| Serialization schema mismatch | JSON fields/headers differ | Verify converter, Content-Type, and contract |

### Asynchronous assertions with a deadline

If a consumer receives an event and updates a projection, do not assert the projection synchronously if the handler is asynchronous. With Awaitility in tests (assuming dependency added):

~~~java
import static org.awaitility.Awaitility.await;
import static java.util.concurrent.TimeUnit.SECONDS;

await()
    .atMost(10, SECONDS)
    .untilAsserted(() -> {
        var projection = projectionRepository.findBySku("SKU-101");
        org.assertj.core.api.Assertions.assertThat(projection.quantity())
            .isEqualTo(8);
    });
~~~

This snippet illustrates **only the assertion**; prior to it, start the consumer properly, trigger/publish the message, prepare the projection repository, and isolate data. The `10s` timeout is an example—tune it to your test environment SLO.

**Never use `Thread.sleep(10000)` as a readiness condition.** Fixed sleeps slow down suites and still fail to guarantee the message has been processed.

### `StubTrigger` is not producer verification

When a consumer uses Stub Runner's `StubTrigger` to emit an event by label, the consumer test verifies **the consumer handler against a simulated message**. Generated producer contract tests are still required to verify the real publisher emits the right message. Passing on one side does not replace the other.

## 19. Test ordering and shared state

A test may pass reliably in isolation yet fail when the full suite runs:

~~~text
Test A: GET stock SKU-101 -> expects quantity 8
Test B: POST reservation SKU-101 quantity 3
Test A after B: GET stock -> actual quantity 5
~~~

If Tests A and B share a database, queue, or WireMock scenario state without resetting, the suite suffers from **order dependency**.

### Three isolation strategies

**Strategy 1 — Test-specific identity.** Give each test a unique SKU/order ID (explicitly allocated and traceable to the test case). Works well in parallel, though data growth/cleanup still needs management.

**Strategy 2 — Test-specific environment.** Give each suite its own database schema/container, broker namespace, or Stub Runner instance. Stronger isolation, higher resource cost.

**Strategy 3 — Controlled state reset.** Reset and seed data, mappings, and offsets to baseline before each test where supported. Ensure resets never disturb other concurrently running tests.

Never “solve” a test-order bug by letting matchers accept multiple arbitrary quantities. If the contract requires exactly `8` for fixture A, preserve that check.

### Reordering tests to uncover coupling

Run the same suite across modes:

- Run each test case individually.
- Run the full suite in a different order.
- Run once sequentially and once in parallel (if policy allows).
- Repeat multiple times in a clean environment.
- Record seeds and test IDs on failures to enable reproduction.

Determinism **does not** rely on one test running after another to “warm up” caches or create data. If a multi-step business dependency exists, model it as **one explicit scenario** rather than two independent order-coupled tests.

## 20. Stateful stub scenarios and resetting WireMock

WireMock supports stateful scenarios—for instance, a consumer calls reservation once and gets `201`, calls again and gets `409`, or tests a retry sequence.

When using stateful mappings:

1. Declare the **initial state** and transitions explicitly.
2. Keep all steps inside **one scenario test**, rather than scattering them across unordered tests.
3. Reset scenario state before every scenario run.
4. Never let two suites share one stateful WireMock server without isolation.
5. Inspect the matched request journal to trace which request triggered each state transition.
6. Distinguish real retry logic from stubs intentionally changing responses by call count.

A stateful scenario is deterministic if **the same request sequence produces the same response sequence**. It is non-deterministic if outcomes depend on requests sent by an unrelated test.

### Distinguishing “stub fixtures” from real stateful systems

If the real producer involves transactions, race conditions, and reservation expirations, WireMock stateful scenarios only simulate observed transitions. They **do not prove** the producer database guarantees transactional correctness. Add dedicated producer/integration tests for that.

## 21. JSON objects, arrays, and the nature of ordering

JSON objects carry no contractual key order, whereas JSON arrays often have consumer-observed element order. This distinction is vital for determinism.

### JSON objects: avoid raw string comparisons

These two objects are equivalent in keys and values:

~~~json
{"sku":"SKU-101","quantity":8,"available":true}
~~~

~~~json
{"available":true,"quantity":8,"sku":"SKU-101"}
~~~

If a test compares JSON strings byte-for-byte, it can break whenever a serializer reorders keys. Prefer JSONPath/matchers verifying **keys, types, and values**. If key ordering is required by a digital signature protocol, implement dedicated canonicalization rather than relying on incidental `Map` iteration order.

### JSON arrays: decide explicitly whether order is contracted

Example warehouse list API:

~~~json
[
  {"warehouse":"HN","quantity":5},
  {"warehouse":"HCM","quantity":3}
]
~~~

If the contract states “sorted by warehouse ID,” the producer must enforce `ORDER BY` or explicit sorting. If the API states “order is not guaranteed,” consumers should assert by **identity/value set**, rather than assuming HN always precedes HCM.

**Never drop order checks when the UI or consumer truly relies on nearest-warehouse priority.** When order is promised, verify the promised sort order.

### Collection size also carries meaning

For list-returning APIs, `byType()` does not automatically protect collection cardinality. If the consumer expects “exactly two options,” explicitly assert length or occurrence rather than checking only item schema.

## 22. Text, XML, binary payloads, and external fixture files

Not every contract is JSON. For XML, multipart, or binary files, determinism also depends on encoding and fixture paths.

### Text/XML

- Specify explicit encoding (typically UTF-8).
- Prevent unnormalized CRLF/LF differences from altering signatures or hashes.
- Use XPath/XML matchers when attribute order carries no meaning.
- Verify XML namespaces and presence of required elements.
- Keep `Content-Type` header checks when consumers branch on media type.

### Fixture files

An HTTP stub layout may include:

~~~text
mappings/
  stock-found.json
__files/
  stock-found-body.json
  sample-invoice.pdf
~~~

Inside a Spring Cloud Contract stub JAR, actual paths may sit under `META-INF/...`. When building or unpacking to a WireMock filesystem, preserve relative paths for `bodyFileName`.

Verify:

1. Are fixture files packaged into the artifact?
2. Are paths and case-sensitivity accurate on Linux CI?
3. Are encoding and line endings controlled?
4. Do tests avoid reading files from a developer's personal home directory?
5. Do binary files match expected checksums?
6. Do stub mappings reference paths that actually exist?

**Never use fixtures containing real personal data or secrets** in the name of “realism.” Synthetic data is equally valid for contract tests as long as schemas and constraints match.

## 23. Headers and network behavior that can introduce flakiness

Some headers should not be naively hardcoded:

| Header | Should it be strictly asserted? | Approach |
|---|---|---|
| `Content-Type` | Usually **yes** | Check media type + charset when required by contract |
| `Location` on `201` | API-dependent, often **yes** | Assert path/ID structure; avoid locking random hostnames |
| `Date` | Consumer-dependent | Date matcher or controlled clock |
| `X-Request-ID` | Often dynamic | UUID/non-blank regex and correlation |
| `Authorization` request | Often requires scheme/permissions | Test token fixture, never real secrets |
| `Retry-After` | Meaningful for retry logic | Check agreed format or value |
| `Transfer-Encoding` | Usually managed by HTTP stack | Omit unless part of contract |
| `Server` | Proxy/runtime-dependent | Typically omit from contracts |

In MockMvc mode, certain real HTTP proxy/server behaviors are not simulated. When you need to verify status, routing, and JSON through full filter/security chains, consider `WebApplicationContext` or real HTTP server tests. Never bake production network quirks into mandatory fixtures unless the contract requires them.

### Stub Runner random ports

With `@AutoConfigureStubRunner(ids="...:stubs:0")`, `0` requests a dynamic port—it does not mean the consumer calls `http://localhost:0`.

In Spring tests:

~~~java
@StubRunnerPort("inventory-producer")
int inventoryPort;
~~~

Consumers must use the injected port or `StubFinder` to build URLs, avoiding hardcoded ports that another process might occupy.

## 24. Stabilizing tests does not mean ignoring concurrency

A quick way to hide flakiness is disabling all parallel tests. That helps isolate root causes, but does not prove the system handles concurrency safely.

Distinguish:

- **Deterministic contract fixtures:** a representative request/response interaction is reproducible.
- **Concurrency behavior:** concurrent requests preserve promised transactional or idempotency guarantees.
- **Test infrastructure isolation:** parallel tests do not illegally share mutable state.

If two orders compete for the same SKU, a single HTTP contract cannot prove no overselling occurs. Add dedicated concurrency/integration tests designed with **synchronized start barriers**, isolated test data, and final assertions free of non-deterministic races.

**Never mock away concurrency in a contract base class and claim transactional behavior was verified.**

## 25. Toolchain and artifacts must also be reproducible

Stable fixtures are not enough if CI uses different generators or compilers across runs.

Pin these components:

- JDK version/distribution, at least at major compatible version.
- Spring Boot, Spring Cloud Contract plugin, verifier, and Stub Runner versions.
- Maven Wrapper / Gradle Wrapper versions.
- Dependency BOM and artifact repositories.
- Contract DSL source revision.
- Stub artifact version, classifier, and digest.
- Runner locale, timezone, and encoding when they affect serialization.
- Test database/broker image versions and fixture states.
- Gradle/Maven caches keyed by input versions.

### Differences across two generation runs

Not every byte of generated Java or WireMock mappings must be **byte-for-byte identical** across plugin upgrades: generators can change whitespace, import order, or mapping serialization without altering semantics.

Evaluate properly:

1. Under the **same toolchain/version**, generated output must not vary by time, randomness, or environment unexpectedly.
2. When **toolchain versions change**, review generated assertions and mappings semantically rather than merely diffing line counts.
3. When **contract revisions change**, confirm changes are intentional—especially in matchers.
4. When **publishing artifacts**, keep versions/digests immutable and verify the exact candidate tested.

If artifact bytes differ due to JAR metadata timestamps, that pertains to reproducible builds; distinguish **metadata byte differences** from **stub behavioral differences**. When an organization requires byte-for-byte provenance, configure build reproducibility and verify checksums.

## 26. CI quality gates for fixtures and generated tests

A sound pipeline:

~~~mermaid
flowchart TD
    A["Contract source reviewed"] --> B["Resolve pinned toolchain/fixture"]
    B --> C["Generate producer tests"]
    C --> D{"Enough contracts/tests?"}
    D -->|No| X["Fail closed"]
    D -->|Yes| E["Run producer tests"]
    E --> F{"PASS?"}
    F -->|No| X
    F -->|Yes| G["Inspect/package stub artifact"]
    G --> H["Stub Runner + real consumer tests"]
    H --> I{"Consumer PASS?"}
    I -->|No| X
    I -->|Yes| J["Record version/digest/test report"]
    J --> K["Release policy gate"]
~~~

### Layer 1 — Contract discovery

- Were all expected Groovy/YAML files discovered?
- Are `contractsPath`/`contractsDslDir` accurate?
- Are there duplicate DSLs or overlapping request mappings?
- Are fixture files referenced via valid paths?
- Does the source revision/version match the reviewed PR?

### Layer 2 — Generated producer tests

- Were Java tests generated and **actually executed**?
- Is executed test count non-zero for modules requiring contracts?
- Are any tests skipped/ignored outside policy?
- Does the base class invoke real producer code?
- Do assertions for static and dynamic values match the contract?

### Layer 3 — Stub artifact

- Exact `group:artifact:version:stubs`?
- Are mappings and fixtures packaged completely?
- Were matchers relaxed excessively?
- Did the artifact originate from the exact contract/source revision verified by the producer?
- Are checksums/provenance recorded?

### Layer 4 — Consumer tests

- Did Stub Runner load the right candidate artifact?
- Did the consumer client target the right runtime port/URL?
- Do tests cover success, error cases, and relevant JSON types?
- Is an unmatched WireMock 404 ever treated as a fake business 404?
- Are messaging handlers tested with proper correlation and bounded awaits?

### Layer 5 — Flake monitoring

Beyond main gates, run a **periodic stability suite** on clean runners, repeating selected generated producer tests and consumer tests to surface latent flakiness.

Reference commands:

~~~bash
# Modern Gradle plugin, invoked in the appropriate multi-project build:
./gradlew :inventory-producer:contractTest --rerun-tasks --no-build-cache

# Maven producer configured with verifier plugin:
./mvnw -B -ntp clean verify
~~~

These are examples to run in real projects, **not commands executed inside this lesson**. `--rerun-tasks` rules out stale `UP-TO-DATE` task caching, yet does not solve noisy fixture state, clocks, or randomness.

### Never use retries to hide failures

Running a flaky test five times and accepting “one PASS” provides zero compatibility evidence. If policy permits automatic retries for transient infrastructure issues, you must:

1. Record the initial failure.
2. Classify the flaky/infrastructure cause.
3. Enforce a strict retry cap.
4. Preserve logs and artifacts from failed attempts.
5. Assign an owner and goal to eliminate the flakiness.
6. Never ship a breaking API change just because a flaky test happened to pass.


## 27. Diagnosing flaky tests with evidence

When a generated test intermittently PASSES and FAILS, capture full reproduction context:

~~~text
Contract:
  file: inventory/stockAvailable.groovy
  revision: <contract-sha>

Producer:
  source revision: <producer-sha>
  test: InventoryContractTest.shouldReturnStock
  expected status: 200
  actual status: 200
  expected quantity: 8
  actual quantity: 5

Environment:
  JDK: <version>
  SCC plugin: <version>
  timezone: <zone>
  database: <isolated-db-id>
  parallel tests: <on/off>
  fixture revision: <fixture-sha>

Stub:
  artifact: <group:artifact:version:stubs>
  digest: <sha256>
~~~

Values inside `<...>` are placeholders gathered from CI, not metadata emitted automatically by Spring Cloud Contract.

### Investigation sequence

1. **Reproduce the test in isolation** at the exact source/contract revision.
2. **Inspect fixtures** before and after execution, especially mutated records.
3. **Re-run the same test** in a freshly provisioned environment.
4. **Shuffle suite order** or temporarily disable parallelism to expose shared state.
5. **Control clock/timezone/locale** to test time sensitivity.
6. **Read generated Java tests** to verify emitted equality/matcher checks.
7. **Read generated WireMock mappings** to verify stub request/response matching.
8. **Check artifact version/digest**; failures may stem from a stale stub rather than flakiness.
9. **Fix fixture/DSL/base test** at the source, never in generated code.
10. **Add a regression test** and monitor after fixing.

### A seemingly random failure can be a real bug

If two concurrent reservation requests for the same SKU yield inconsistent results, that may be a **real producer concurrency bug**. Never label something “flaky infrastructure” before checking business invariants.

A useful report states what request the producer received, what the initial fixture looked like, which test mutated state, and who owns verification.

## 28. Symptom-based troubleshooting

| Symptom | Common root cause | How to verify |
|---|---|---|
| Fails when CI timezone differs | `checkedAt` compared as unstandardized string | Inject UTC clock / verify time semantics |
| Fails near midnight | `LocalDate.now()` depends on calendar day | Inject `Clock` and `ZoneId` |
| Fails due to different UUID | Response equality against dynamic ID | Format matcher or injected ID generator |
| Passes only after another test runs | Fixture depends on state left by another test | Independent setup/seeding per test |
| Fails only under parallel execution | Shared DB row, queue, or stub state | Isolation, namespaces, resource locks |
| Fails on JSON key order | Raw JSON string comparison | JSONPath / structural matcher |
| Array elements change order | Query lacks sorting or contract omits order | Define sorting and assert proper semantics |
| Consumer receives WireMock 404 | Request fails to match mapping | Inspect method/path/header/body |
| Business 404 test passes on typo | Status-only assertion | Assert error code/body |
| Stub returns stale data | Stale artifact/version | Pin coordinates, verify digest |
| Producer tests stay green despite DSL edits | 0 tests run or tests skipped | Check report, source sets, and plugin |
| Producer red while consumer green | Producer violates DSL | Block verified stub publication |
| Messaging test times out | Broker/listener not ready or wrong destination | Correlation, isolated group, bounded wait |
| Messaging test receives old event | Shared queue/consumer group | Reset/isolate destination |
| Fixture fails to load on Linux | Wrong path casing or encoding | Check path, UTF-8, JAR entries |
| Fails only on newer CI | Different JDK/plugin/dependency version | Pin wrapper/BOM/environment |
| Stateful stub fails after another test | WireMock state not reset | Reset scenario or use isolated instance |
| Test stays green despite wrong field | Overly broad `.*` or `byType()` | Tighten matchers to invariants |
| Passes on repeated reruns | Shared state, race, or time | Investigate root cause; no pass-by-retry |

Defects that prevent CI from **catching breaking changes** (overly broad matchers, skipped tests, stale artifacts, unmatched 404s) deserve equal or higher priority than flaky failures that turn suites red.

## 29. Lab 1: variable timestamps

Real producer returns:

~~~json
{
  "sku": "SKU-101",
  "quantity": 8,
  "checkedAt": "2026-01-15T10:01:02Z"
}
~~~

Current DSL requires:

~~~json
{
  "sku": "SKU-101",
  "quantity": 8,
  "checkedAt": "2026-01-15T10:00:00Z"
}
~~~

Generated producer test fails even though `checkedAt` is designed as the stock-check timestamp and naturally changes.

**Q1. Should `checkedAt` be deleted from the contract?**

Not automatically. If the consumer needs that field, keep it and assert the appropriate requirement. Removing a field is valid only after both teams agree it is outside the interface.

**Q2. How can the test be made deterministic?**

- Inject `Clock.fixed` in producer tests so the response matches the sample instant.
- Use a timestamp matcher if the contract only requires valid format; add separate tests for time relationships if needed.

**Q3. What if the consumer displays time in the user's timezone?**

The API should return an unambiguous format such as ISO-8601 with `Z` or explicit offset. The consumer converts it for display; never hardcode CI runner locale text.

**Q4. Is `byType()` alone enough?**

Not always: string type does not prove the timestamp parses cleanly. Use a timestamp matcher or parse/compare timestamps in appropriate tests.

## 30. Lab 2: overly loose matchers

Checkout requires:

~~~json
{"reservationId":"RSV-1001","status":"ACTIVE"}
~~~

Buggy producer returns:

~~~json
{"reservationId":"","status":"FAILED"}
~~~

Generated test only uses:

~~~groovy
bodyMatchers {
    jsonPath('$.reservationId', byType())
    jsonPath('$.status', byType())
}
~~~

**Q1. Why can the test still PASS?**

Because both an empty string and `FAILED` are strings. Type matchers do not check business constraints: a **valid ID** and **status ACTIVE**.

**Q2. What is the proper fix?**

- `reservationId`: regex/format or non-blank matcher per specification.
- `status`: equality `ACTIVE` in the happy-path fixture.
- Assert HTTP `201`, Content-Type, and related fields.

Illustrative response block:

~~~groovy
response {
    status 201
    body(
        reservationId: 'RSV-1001',
        status: 'ACTIVE'
    )
    bodyMatchers {
        jsonPath('$.reservationId', byRegex('RSV-[0-9]{4}'))
    }
}
~~~

This snippet must sit inside a complete `Contract.make`.

**Q3. Is `.*` better than `byType()`?**

No. Overly broad regexes still accept empty strings. Relax only where the contract permits variation.

## 31. Lab 3: HTTP and messaging running in parallel

### Scenario

- Test A seeds `SKU-101 quantity=8` then calls GET.
- Test B creates a reservation that decrements quantity.
- Test C consumes `StockChanged` from a shared broker topic.
- Under parallel runs, A occasionally observes `5` and C receives an event from a prior run.

### Sample remediation plan

1. Use **dedicated SKUs/namespaces** per suite or test where possible.
2. Seed DB with explicit cleanup/transactions; never let Test B mutate Test A's row.
3. Isolate test consumer groups/topics or reset offsets deterministically.
4. Correlate messages by event ID or transaction ID instead of matching any arriving event.
5. Use Awaitility / condition-based waits with finite timeouts instead of `sleep`.
6. Do not assert cross-partition Kafka ordering unless guaranteed by protocol.
7. Keep integration tests for real concurrency—**never** delete assertions because parallel tests failed.
8. Use isolated DB/broker/container instances in CI when running multiple suites.

### Self-check questions

- If A passes only when B has not run yet, is that an implementation bug or fixture isolation failure?
- If the API promises quantity decreases after reservation, which test proves it?
- If event ID is a dynamic UUID, should producer tests use equality or a matcher?
- How do you tell a business 404 apart from an unmatched WireMock 404?
- If Stub Runner loads an older version and consumer tests pass, does that prove the new candidate is compatible?

## 32. Review checklist for fixtures and generated tests

### Data and state

- [ ] Every contract has a clear name and business scenario.
- [ ] Sample requests have concrete fields/types/values so producer tests can send them.
- [ ] Test identities do not rely on random database rows.
- [ ] Fixtures contain no secrets or real user data.
- [ ] No `now()`/`UUID.randomUUID()` evaluated at DSL load time unnecessarily.
- [ ] If seeded randomness is used, seeds are recorded and RNGs are not improperly shared across tests.
- [ ] Databases/queues are seeded and reset along clear boundaries.
- [ ] Tests can run individually, in shuffled order, and repeatedly.
- [ ] Parallel tests use proper namespaces, locks, or isolation.

### Matchers and assertions

- [ ] Stub request matchers accept valid requests without being overly broad.
- [ ] Generated producer tests send concrete requests.
- [ ] Stub responses have concrete, usable fixtures for consumers.
- [ ] Producer response matchers relax only legitimately dynamic fields.
- [ ] Status, headers, JSON types, and business values are asserted.
- [ ] IDs/timestamps validate proper formats/invariants or are controlled via injected dependencies.
- [ ] Array ordering and length are checked per contract.
- [ ] `.*`/`byType()` are never used to drop business constraints.
- [ ] Business 404s have error bodies/codes distinct from unmatched stub responses.
- [ ] Null, missing, and empty values are distinguished when consumers depend on them.

### Generated artifacts and runtime

- [ ] Producer base class wires real implementation within the verification scope.
- [ ] `Clock`/timezone/locale/encoding are controlled whenever they affect output.
- [ ] Generated Java tests were inspected to verify requests and assertions.
- [ ] Generated tests **actually execute and PASS**, with valid test counts.
- [ ] Stub mappings define proper method/path/body matchers.
- [ ] `__files` fixtures are packaged completely.
- [ ] Stub Runner resolves the exact version/classifier/digest, never stale cache.
- [ ] Random ports are looked up at runtime, never hardcoded as `localhost:0`.
- [ ] Messaging tests use correlation, isolated groups, and bounded waits.
- [ ] Stateful WireMock scenarios reset cleanly or run in isolated instances.

### CI and team process

- [ ] JDK/Gradle/Maven/Spring Cloud Contract versions are pinned.
- [ ] Contract revision and stub artifact digest are recorded.
- [ ] Verified stubs are never published when producer tests fail, skip, or run 0 tests.
- [ ] Consumer tests use candidate stubs matching the verified producer revision.
- [ ] Error branches and boundary cases have dedicated fixtures.
- [ ] Test retries never erase or hide the initial failure.
- [ ] Ownership is assigned to investigate flakiness.
- [ ] Every matcher change is reviewed for consumer impact.
- [ ] Integration tests protect invariants beyond contract-test scope.
- [ ] “Always green tests” are never treated as proof that tests catch bugs.

## 33. Takeaways and references

A strong Spring Cloud Contract suite must be **both reproducible and rigorous**. Fixed fixtures give generated producer tests deterministic inputs and state. Matchers allow timestamps, UUIDs, and producer-generated values to vary legitimately. Yet use matchers only where consumers allow variation: **never relax business rules that need verification**.

Inspect both ends: **generated producer tests** must send concrete requests and assert real behavior; **stub mappings** must match valid requests and return proper fixture responses. A green CI build is trustworthy only when tests actually execute, artifact versions match, and test state is isolated.

### Official documentation

- [Spring Cloud Contract — Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): `consumer`/`producer` and dynamic values.
- [Spring Cloud Contract — How to Provide Dynamic Values](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-provide-dynamic-values.html): stub request matchers and concrete inputs in producer tests.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL and `bodyMatchers`.
- [Spring Cloud Contract — YAML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): YAML matcher syntax.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): `contractTest`, generated tests, and `verifierStubsJar`.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): producer verification and packaging stubs.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consuming stubs in tests.
- [Java — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html): `Clock.fixed` and testable time.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): mappings, request matchers, and stateful scenarios.
- [Testcontainers — Documentation](https://java.testcontainers.org/): isolating databases, brokers, and test dependencies.

**Practical conclusion:** instead of asking “does the fixture look like production?”, ask **“for the same scenario, does the test consistently verify the right behavior, catch bugs, and produce stubs that consumers use meaningfully?”** Controlling inputs, state, matchers, versions, and CI is what makes contract testing results genuinely reliable.
