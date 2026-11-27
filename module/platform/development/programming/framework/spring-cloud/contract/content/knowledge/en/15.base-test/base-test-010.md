# Controlling Time, Identifiers, and Dynamic Data Sources

## Lesson objectives

In **Spring Cloud Contract**, **Groovy DSL** or **YAML DSL** contracts describe the HTTP/messaging behavior a **producer** promises a **consumer**. The tool generates producer-side tests and packages stubs for consumers to run with **Stub Runner**, and these steps are commonly integrated into CI to detect breaking API changes.

A practical challenge is that producers can depend on **current time**, **auto-generated identifiers**, **database state**, **randomness**, **external service data**, or queue state. If generated tests fail to control those sources, the same contract can PASS today and FAIL tomorrow even when the producer did not change. Conversely, updating the contract to match fresh values on every run risks turning the commitment into a meaningless check.

Most of the solution lives in the **base test class**, test configuration, and intentionally controlled fixtures; production data or random logic should never be stuffed into contract files.

After this lesson, you will be able to:

- Distinguish **public behavior to commit to** from **dynamic data sources used to construct that behavior**.
- Use `java.time.Clock` and an ID-generation abstraction to stabilize tests without changing production APIs.
- Prepare and clean up fixtures, avoiding tests that depend on execution order or leftover data from prior runs.
- Write Groovy/YAML contracts with deterministic examples while knowing when to use matchers for dynamic values.
- Test expiration boundaries, timezones, timestamp precision, and identifiers generated across multiple calls.
- Understand the limits of producer tests, stubs, and consumer tests when asserting compatibility.

## 1. Identifying dynamic data before writing contracts

Suppose Checkout calls POST /api/orders and the producer returns:

~~~json
{
  "orderId": "ORD-9001",
  "status": "CREATED",
  "createdAt": "2026-01-15T08:00:00Z"
}
~~~

`orderId` and `createdAt` can change on the next call:

- IDs may come from an ID generator, UUID, or database sequence.
- Timestamps may come from the system clock.
- Status may depend on fixtures or an external payment system.
- Response fields may depend on another service, message broker, or cache.

Using the current response verbatim as a strict expectation without controlling data sources makes generated tests flaky.

| Source of variation | Common symptom | Control tool / strategy |
| --- | --- | --- |
| `Instant.now()`, `LocalDateTime.now()` | Timestamp differs on every run | Inject `Clock` or a time abstraction |
| `UUID.randomUUID()`, DB auto-increment | Different IDs, frequent fixture collisions | Inject ID generator; use test sequences/fixtures |
| Randomness and synthetic data | Passes once, fails next time | Controlled seeds, fixed fixtures; limit randomness in contracts |
| Shared database | Tests depend on state and ordering | Per-test transactions/cleanup/seeding |
| External HTTP service / broker | Network, latency, and environment data coupling | Test doubles at boundaries or isolated integration environments |
| Caches and in-process state | Passes alone, fails in full suite | Reset or use dedicated contexts/namespaces |
| Timezone, locale, formatting | Time/currency comparison fails on CI | Pin zone/locale explicitly and standardize serialization |

**Principle:** if a value changes solely because the test ran at a different time or on a different machine, fix how fixtures/expectations are constructed. However, if the interface genuinely permits values to vary, the contract should not force the producer to return an uncommitted constant either.

## 2. Separation of responsibilities: contract, base test, and producer

Three components must stay separated:

| Component | Responsibility |
| --- | --- |
| **Contract DSL** | Declares requests/responses or messages, status codes, types, rules, and observable example values |
| **Base test class / test configuration** | Initializes the test client, sets up Clock/ID generator, creates and cleans up fixtures, mocks dependencies at appropriate boundaries |
| **Producer implementation** | Actually processes inputs and builds outputs; must be verified by generated tests |

Execution flow:

~~~mermaid
flowchart TD
    A["Contract Groovy/YAML<br/>behavioral commitment"] --> B["Spring Cloud Contract"]
    B --> C["Generated producer tests"]
    B --> D["Stub/mapping"]
    E["Base test class<br/>Clock, ID generator, fixtures"] --> C
    C --> F["Call producer under test"]
    F --> G["Assert response/message"]
    D --> H["Consumer runs Stub Runner"]
    H --> I["Test consumer logic"]
~~~

The base test **does not replace the producer**. It creates controllable state and inputs so tests genuinely invoke the interface under verification. If the base test simply returns a mocked response identical to the contract without traversing the target logic, a PASS proves nothing about producer behavior.

## 3. Why avoid calling static clocks everywhere?

Example of a service reading time directly:

~~~java
public final class OrderService {
    public OrderReceipt createOrder(CreateOrderCommand command) {
        String id = java.util.UUID.randomUUID().toString();
        java.time.Instant time = java.time.Instant.now();
        // Save the order and return receipt...
        return new OrderReceipt(id, time, "CREATED");
    }
}
~~~

This is a **sketch** showing the problem, not a complete service. Tests cannot easily predict `id` and `time`; mocking the system clock globally can also interfere with other tests.

A more testable design promotes sources of variation into **dependencies**:

~~~java
import java.time.Clock;
import java.time.Instant;

public interface OrderIdGenerator {
    String nextId();
}

public final class OrderService {
    private final Clock clock;
    private final OrderIdGenerator ids;

    public OrderService(Clock clock, OrderIdGenerator ids) {
        this.clock = clock;
        this.ids = ids;
    }

    public OrderReceipt createOrder(CreateOrderCommand command) {
        String newId = ids.nextId();
        Instant createdAt = Instant.now(clock);
        // Validate command, save data, and publish result...
        return new OrderReceipt(newId, createdAt, "CREATED");
    }
}
~~~

`OrderIdGenerator` is an **application-designed interface**, not a class provided by Spring Cloud Contract. `OrderReceipt` and `CreateOrderCommand` are illustrative domain types.

Key points:

- `Instant.now(clock)` reads time via the injected Clock.
- `ids.nextId()` obtains IDs through an interface whose implementation can be swapped in tests.
- Production can still use a real clock and an ID generator meeting security/uniqueness requirements.
- Generated producer tests can run with deterministic test dependencies.

**Never downgrade production logic to predictable IDs just to make tests easier to write.** Abstractions let tests swap data sources without weakening real-system security guarantees.

## 4. Choosing a fixed Clock for a contract scenario

In Java:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock testClock = Clock.fixed(
    Instant.parse("2026-01-15T08:00:00Z"),
    ZoneOffset.UTC
);

Instant createdAt = Instant.now(testClock);
// createdAt is always 2026-01-15T08:00:00Z
~~~

`Clock.fixed` makes the same request produce the same timestamp across test runs. It fits scenarios requiring **fixed time state**.

Compared to calling `Instant.now()` directly:

| Usage | Testing consequence |
| --- | --- |
| `Instant.now()` | Depends on system clock; hard to compare against fixed expectations |
| `Instant.now(clock)` with `Clock.systemUTC()` | Still real time, but provides a dependency seam |
| `Instant.now(clock)` with `Clock.fixed(...)` | Deterministic output; fits fixtures/tests with fixed timestamps |
| Adjustable Clock in tests | Lets tests check before/after deadlines, but must reset and avoid shared state |

A fixed clock does not solve every case automatically. When a scenario requires **time advancing**, such as an order expiring after 15 minutes, a permanently fixed Clock cannot show state transitions unless the test swaps Clocks or uses a controllable clock.

## 5. Configuring Clock and ID generator in the base test class

For a Spring Boot producer, deterministic dependencies can live in a **test configuration**, while the base test class initializes the HTTP test client.

Example **reference setup skeleton** (domain class names are illustrative and must match your real project):

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import(OrderContractBase.DeterministicTestBeans.class)
public abstract class OrderContractBase {

    @Autowired
    private MockMvc mockMvc;

    @BeforeEach
    void prepare() {
        RestAssuredMockMvc.mockMvc(mockMvc);
        // Seed synthetic data in the test database,
        // reset cache / dependent state if needed.
    }

    @TestConfiguration
    static class DeterministicTestBeans {

        @Bean
        @Primary
        Clock contractClock() {
            return Clock.fixed(
                Instant.parse("2026-01-15T08:00:00Z"),
                ZoneOffset.UTC
            );
        }

        @Bean
        @Primary
        OrderIdGenerator contractOrderIds() {
            return () -> "ORD-TEST-9001";
        }
    }
}
~~~

This example conveys the **configuration concept**, not a complete buildable project. It assumes the application already defines `OrderIdGenerator`, required dependencies, and verifier configuration pointing generated tests to this base class. Method/annotation names, clock injection, test modes, and dependencies must match your Spring Boot/Spring Cloud Contract versions.

Practical notes:

1. `@Primary` only works when dependency injection actually pulls that bean type. If a service calls `Instant.now()` directly or instantiates an ID generator with `new`, test beans cannot control it.
2. If production beans are injected via `@Qualifier` or conditional config, design matching test overrides; do not assume `@Primary` overrides every selection rule.
3. A fake `OrderIdGenerator` that **always returns one fixed ID** only works for single-record scenarios. Creating multiple records in one test causes primary-key collisions and requires a resettable sequence.
4. Ensure the HTTP framework used by Verifier-generated tests matches your base class setup. The example uses Rest Assured MockMvc; tests generated for WebTestClient or other modes need matching setup.
5. `@TestConfiguration` and test fixtures must never enter production runtime artifacts.

## 6. Preparing and cleaning up data before each generated test

Clock and ID generators address only two sources of variation. Generated tests also depend on background data:

~~~text
Before test:
  - Clean or isolated test database
  - Synthetic customer CUS-TEST-1001 exists
  - Required sample pricing/tax rules exist
  - Clock = 2026-01-15T08:00:00Z
  - ID generator configured per scenario rules

Test:
  POST /api/orders
  Expect 201 with defined orderId and createdAt

After test:
  - Clean up data / roll back as appropriate
  - Reset caches, sequences, message state
~~~

For `GET /api/orders/ORD-TEST-9001`, fixtures should insert the record before the request runs. For `POST` order-creation tests, fixtures typically prepare background customers/products while the producer **executes the order creation itself** so the test proves real behavior.

Available techniques:

- **Transaction/rollback** for synchronous tests executing within the same transaction. Note that requests over a real HTTP server or separate threads **may not participate** in the test method's transaction.
- **Dedicated test database**, such as a pipeline-provisioned database container.
- **Repository or SQL cleanup** scoped to test data boundaries, followed by seeding required state.
- **Dedicated namespaces/keys** for Redis, caches, or external resources.
- **Reset methods** for fake clocks, fake ID generators, and fake publishers if they hold state.

Never use a production database as a fixture source. Contracts and stubs may be committed to repositories or distributed in artifacts, so use **synthetic** IDs, emails, and payloads.

## 7. Groovy DSL contract paired with deterministic fixtures

Suppose `POST /api/orders` on Order Service receives a sample order and returns an ID/timestamp produced from controlled dependencies.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Create order with stable timestamp and ID data"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: "CUS-TEST-1001",
            items: [
                [sku: "SKU-TEST-BOOK", quantity: 2]
            ]
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: "ORD-TEST-9001",
            status: "CREATED",
            createdAt: "2026-01-15T08:00:00Z"
        )
    }
}
~~~

How the three pieces connect:

- **Contract** defines desired inputs and outputs.
- **Base test** configures the Clock, ID generator, and test data so the producer can execute the scenario.
- **Generated producer test** dispatches the request and verifies the real response.

If the test FAILS because of a wrong timestamp, do not update the contract to match current wall-clock time. First check whether the producer reads time from the injected Clock, formats in UTC, and resets fixtures properly.

### YAML DSL for the same scenario

~~~yaml
description: "Create order with stable timestamp and ID data"
name: create_order_with_fixed_clock
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customerId: "CUS-TEST-1001"
    items:
      - sku: "SKU-TEST-BOOK"
        quantity: 2
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-TEST-9001"
    status: CREATED
    createdAt: "2026-01-15T08:00:00Z"
~~~

These two versions illustrate **the same contract**; do not place both into the producer's contracts folder at once, or the tool may generate duplicate scenarios.

In a real project, choose one of the two DSLs or have a clear reason for maintaining separate scenarios. Do not treat passing YAML or Groovy tests as proof that production's Clock is wired properly; they are evidence for **the producer under test with that setup**.

## 8. When IDs cannot be fixed: use intentional matchers

Some systems require database-generated IDs or external identity services that are hard to override in tests. Contracts can then specify **output format** rather than a hardcoded value.

Example response using dual-sided values in Groovy DSL:

~~~groovy
response {
    status 201
    headers {
        contentType(applicationJson())
    }
    body(
        orderId: value(
            consumer("ORD-TEST-9001"),
            producer(regex("ORD-[A-Z0-9-]+"))
        ),
        status: "CREATED"
    )
}
~~~

**In the response**:

- Stubs return the sample value `ORD-TEST-9001` to the consumer.
- Generated producer tests verify that the producer-generated ID matches the regex.

However, `ORD-[A-Z0-9-]+` is a relatively loose format rule. It does not check uniqueness, prove persistence succeeded, or guarantee `GET` works immediately after `POST`. If those properties are part of the commitment, verify them separately.

For dynamic timestamps, you can often use ISO-8601 format matchers or bounded time-skew assertions. **Avoid comparing against `Instant.now()` at assertion time without an explicit tolerance**, since scheduling and serialization jitter cause flakiness.

Do not loosen matchers broadly just to turn tests green. A **deterministic Clock** remains the better option whenever you need to verify **exact timestamp logic** in a business scenario.

## 9. Testing expiration deadlines: before, at, and after expiry

Suppose a reservation expires at `2026-01-15T08:15:00Z`. Business rule:

~~~text
ACTIVE  when now < expiresAt
EXPIRED when now >= expiresAt
~~~

Checkpoints to verify:

| Simulated time | Expected result | Purpose |
| --- | --- | --- |
| 08:14:59Z | ACTIVE | Before expiry |
| 08:15:00Z | EXPIRED | Exact boundary |
| 08:15:01Z | EXPIRED | After expiry |

Without controlling Clock, tests running near transition boundaries become non-deterministic. In tests you can define distinct `Clock.fixed(...)` instances:

~~~java
Instant expiry = Instant.parse("2026-01-15T08:15:00Z");

Clock before = Clock.fixed(
    Instant.parse("2026-01-15T08:14:59Z"),
    ZoneOffset.UTC
);

Clock atBoundary = Clock.fixed(expiry, ZoneOffset.UTC);

Clock after = Clock.fixed(
    Instant.parse("2026-01-15T08:15:01Z"),
    ZoneOffset.UTC
);
~~~

For generated contract tests, you can use matching test contexts/fixtures per scenario, or an adjustable clock if testing multiple states in one session. **Never assume one shared `@Bean Clock.fixed` covers all boundary timestamps.**

If using a stateful mutable clock:

- Reset it to the baseline instant before every test.
- Never share a mutable instance across parallel tests without isolation.
- Prevent one test's clock shift from breaking another test.
- Document exact boundary semantics: `>` and `>=` mean different things.

## 10. Timezones, precision, and temporal types

Timestamps remain a common source of bugs even after Clock injection.

| Issue | Common mismatch | How to control |
| --- | --- | --- |
| `Instant` vs. `LocalDateTime` | Drops timezone info, misinterprets instant | Use explicit temporal types per contract |
| UTC vs. system timezone | Same instant serialized with different offset | Pin fixed zone and define API format |
| Milliseconds vs. nanoseconds | String assertion fails due to precision | Standardize unit/truncation per interface |
| DST (daylight saving time) | Local times skipped or repeated in some regions | Use `Instant`/`ZoneId` properly; test edge cases if needed |
| Locale | Different month names, digits, or separators | Avoid default locale; format consistently |
| Calling `now()` multiple times | Two timestamp fields differ by milliseconds | Capture one `Instant` from Clock per operation and reuse it |

Example:

~~~java
Instant instant = Instant.parse("2026-01-15T08:00:00Z");

// Same instant represented with different offsets.
String utc = instant.toString();
String plusSeven = instant.atOffset(
    java.time.ZoneOffset.ofHours(7)
).toString();
~~~

`2026-01-15T08:00:00Z` and `2026-01-15T15:00:00+07:00` represent **the same instant** yet are **two different strings**. If the contract promises UTC with a `Z` suffix, the producer must emit that format. If the contract only promises the same instant with a valid offset, matchers/assertions should reflect that rule rather than locking a single representation.

**Important:** swapping `Clock` does not configure JSON serializers. Verify that Jackson/date formatters and DTOs use the exact format expected by consumers.

## 11. Controlling ID generators across multiple requests

A fake generator always returning `ORD-TEST-9001` is easy to follow but breaks when a test creates multiple orders:

~~~text
POST /api/orders -> ORD-TEST-9001
POST /api/orders -> ORD-TEST-9001  (duplicate ID!)
~~~

For scenarios needing multiple IDs, use a **resettable test sequence**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class TestOrderIdGenerator implements OrderIdGenerator {
    private final AtomicInteger next = new AtomicInteger(9001);

    @Override
    public String nextId() {
        return "ORD-TEST-" + next.getAndIncrement();
    }

    public void reset() {
        next.set(9001);
    }
}
~~~

In the base test, `reset()` can run before each generated test if the fake is injected with an appropriate lifecycle. However, **`AtomicInteger` only prevents concurrent counter races**; it does not isolate whole test logic across threads. If parallel tests share a sequence bean, one test can consume an ID expected by another.

Safer strategies:

- Give each test its own fake instance if feasible.
- If a shared fake is unavoidable, disable parallel execution for order-dependent cases or assign separate namespaces.
- Reset the generator and delete created records at test end/start.
- Never tie expected IDs to **execution order across tests**.

For production IDs, global uniqueness, unpredictability, and collision resistance are separate requirements. Fake generators **prove none of those properties**; verify them with dedicated tests/metrics on real production implementations.

## 12. Dynamic data sources beyond time and IDs

A contract test can still flake even when Clock and IDs are deterministic:

### Databases and transactions

If a test reads rows left from an earlier run, outcomes shift with test order. Seed data and clean up within scoped boundaries instead of relying on personal databases.

### Caches

One test updates source data while a cache retains the old value. Clear caches, isolate key namespaces, or test cache behavior explicitly if it is a public commitment.

### External HTTP services

If the producer calls Payment Service to create an order, generated producer tests should not depend on a shifting production Payment Service. Use test doubles at dependency boundaries while still traversing the **producer logic** under verification. If everything is mocked so responses bypass real processing code, the test loses value.

### Message brokers and async processing

A message consumer may receive delayed or duplicate events. Pick test brokers/containers with conditional waiting and drain queues/topics per namespace. **Never replace async synchronization with fixed sleeps** and call the suite stable; short sleeps flake, long sleeps bloat CI.

### Randomness and ordering

If list ordering relies on map/set iteration order, tests may receive varying orders. Enforce deterministic sorting only when consumers genuinely rely on it; if the API does not guarantee order, assertions should not require an artificial order.

### Environment variables

Never let contracts emit different responses solely due to `CI=true` or machine timezone. Any environment setting affecting behavior must be explicit or pinned in controlled test configuration.

## 13. With message contracts, fixtures still need deterministic sources

Groovy DSL example for a post-payment event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Emit payment event with deterministic test data"
    label "order_paid"

    input {
        triggeredBy("publishPaidTestOrder()")
    }

    outputMessage {
        sentTo("order-events")
        body(
            eventType: "ORDER_PAID",
            eventId: "EVT-TEST-0001",
            orderId: "ORD-TEST-9001",
            occurredAt: "2026-01-15T08:00:00Z"
        )
        headers {
            contentType(applicationJson())
        }
    }
}
~~~

Here `publishPaidTestOrder()` is a method provided in the generated producer test context; it must trigger the real producer logic that emits the event. It is **not** a command executed by consumer Stub Runner.

If the producer generates dynamic `eventId` or `occurredAt` values, control Clock and ID generators in the base test, or use appropriate matchers on message output if format is the real commitment.

**Do not test merely by sending a pre-formatted message directly from the base class to a fake broker and claiming the producer honors the contract** if real business logic was never triggered. Tests must verify the promised producer interface within scenario scope.

## 14. Stub Runner does not share the producer's Clock and fixtures

When producer contract tests run with `Clock.fixed`, that is a **producer test-environment dependency**—it is not transmitted automatically to consumers or stub servers.

~~~mermaid
sequenceDiagram
    participant P as Producer CI
    participant S as Stub artifact
    participant C as Consumer CI
    P->>P: Inject mocked Clock + ID generator
    P->>P: Run generated producer test
    P->>S: Generate and publish stub from contract
    C->>S: Stub Runner downloads specific version
    C->>S: Send request to stub server
    S-->>C: Return response per stub mapping
~~~

On the consumer side:

- Fixed **sample timestamps/IDs** can be used in stub responses.
- Tests verify consumer logic handling responses (e.g., saving `orderId` and navigating to a detail view).
- If consumers need multiple timestamps or states, design additional explicit contracts/stub scenarios.
- Never assume stubs re-invoke the producer's `Clock` or `OrderIdGenerator` per incoming request.

A stub returning `ORD-TEST-9001` does not prove production always generates that ID. Conversely, producer tests can verify IDs with matchers while stubs return a valid sample ID.

**Compatibility claims** must tie to the exact contract revision, producer build, stub artifact, and tested consumer version. Passing in a fixture environment does not guarantee every production dataset or config is safe.

## 15. Reproducibility and reliability in CI

Before marking builds compatible, CI should verify:

1. **Contracts are build-time deterministic:** no `Instant.now()` or random UUIDs inside Groovy scripts silently altering expected bodies.
2. **Right base test class selected:** generated tests inherit setups with test Clock/ID generators rather than uncontrolled production beans.
3. **Independent fixtures:** every test has clean data, zero order dependency, and no production database access.
4. **Tests actually executed:** not merely generated sources or green builds with skipped contract tests.
5. **Dynamic boundary checks:** contracts/extra tests cover boundary timestamps, invalid inputs, and multi-ID scenarios if consumers depend on them.
6. **Version-aligned stubs:** consumer tests run Stub Runner against the artifact built from the exact contracts verified on the producer.
7. **Traceable reports:** record commit, build ID, contract revision, test reports, stub version, and unverified limits.

Example project-defined evidence record:

~~~yaml
# Illustrative release evidence only, not a default SCC config.
producer: "order-service:2.4.0"
producer_revision: "commit-abc123"
contract_revision: "contracts-def456"
test_clock: "2026-01-15T08:00:00Z"
id_fixture: "ORD-TEST-9001"
fixture_profile: "isolated-test"
generated_producer_tests: PASS
stub_artifact: "com.example:order-service:2.4.0:stubs"
consumer_stub_tests: PASS
notes:
  - "Results cover only executed scenarios"
  - "Does not prove production ID uniqueness"
~~~

**Not every CI job needs one Clock across every test.** When a scenario requires testing a different instant, document that test's Clock explicitly. The goal is **reproducibility and traceability**, not forcing every scenario into a single timestamp.

## 16. Common pitfalls

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Tests FAIL as timestamp changes every run | Producer calls real clock; assertions lock exact value | Inject `Clock` or use a matcher matching the commitment |
| Passes locally, FAILS on CI | Different timezone, locale, or precision | Pin zone/format and align JSON serializer |
| Two tests generate identical IDs | Fake generator always returns one value | Use resettable sequences or per-test fakes |
| Passes alone, FAILS in full suite | Shared DB/cache/fake clock state | Clean/reset fixtures, isolate, or control parallelism |
| Producer test FAILS after mocking Clock | Service ignores injected Clock | Fix time-reading seam in production code |
| Test compares `Instant.now()` to producer timestamp | Scheduling jitter causes drift | Share a Clock or use a bounded-tolerance matcher |
| CI green despite skipping contracts | Tests skipped or wrong contract path | Verify generated and executed test counts |
| Consumer Stub Runner returns fixed timestamp | Stub mappings come from contract, not producer Clock | Design appropriate stub scenarios or matchers |
| Using production data for "realistic" fixtures | Information leakage, external state coupling | Build synthetic data and dedicated test DBs |
| Tests only check ID regex | Does not verify uniqueness/persistence | Add dedicated tests if those properties are required |

When failures happen, avoid updating expected contract values to match each build output. Identify the **source of non-determinism** and resolve it at the right layer.

## 17. Practice exercises

### Exercise A — Replacing system time with Clock

A service calls `LocalDateTime.now()` to compute expiration times. Generated tests expect one timestamp yet FAIL on CI.

**Task:** propose design and base test setup changes.

**Hint:** inject `Clock`, call `Instant.now(clock)` or `LocalDateTime.now(clock)` per interface, configure a fixed Clock and explicit timezone, and ensure JSON serialization preserves the format expected by consumers.

### Exercise B — Multi-call ID generation

A fake ID generator always returns `ORD-TEST-9001`. One scenario creates two orders and verifies both independently.

**Task:** propose a strategy so IDs do not collide while tests stay repeatable.

**Hint:** per-test resettable sequence (e.g., ORD-TEST-9001 and ORD-TEST-9002), plus clear parallel execution policies and data cleanup.

### Exercise C — Expiration boundary cases

A coupon expires when `now >= expiresAt`, with `expiresAt = 2026-01-15T08:15:00Z`.

**Task:** design three scenarios before, at, and after the boundary; explain why a single `Clock.fixed` bean cannot verify all three.

**Hint:** use separate Clocks or reset an adjustable Clock, comparing HTTP status/response across all three cases.

### Exercise D — Producer tests and stubs using different data

Producer tests run with a fixed Clock and sample IDs. Consumer CI runs Stub Runner yet pulls a stub artifact from last month.

**Task:** explain why passing results are insufficient to claim compatibility for the new release.

**Hint:** generate/publish stubs from the exact verified contract revision and producer build, pin the version, and run consumer tests against that exact artifact.

### Exercise E — Spotting over-mocking

The base test mocks the controller or HTTP handler to return JSON copied straight from the contract. Generated producer tests PASS.

**Task:** explain the risk and propose a better mock boundary.

**Hint:** mock external dependencies like payment gateways, but let real controller/service logic process requests and construct responses; if tests only hit a canned stub, there is zero proof of producer behavior.

## 18. Checklist before approving a base test for dynamic data

- [ ] Identified which values are dynamic and which belong to the producer–consumer commitment.
- [ ] Producer reads time through a controllable dependency such as `Clock`.
- [ ] ID generator exposes a testable interface without weakening production IDs.
- [ ] Clock, ID generator, and fixtures reset/isolate properly across lifecycle hooks.
- [ ] Synthetic data never pulls from production or includes secrets.
- [ ] Timezones, precision, timestamp formats, and boundary instants are verified when APIs depend on them.
- [ ] Multi-request scenarios never accidentally receive duplicate IDs or depend on execution order.
- [ ] Mocks sit only at appropriate boundaries; producer logic under test still executes.
- [ ] Groovy/YAML contracts hold meaningful examples or matchers without build-time `now`/random values.
- [ ] Generated producer tests are actually generated, compiled, and executed against the right base class.
- [ ] Stubs trace to the same contract revision and do not assume base test code runs inside Stub Runner.
- [ ] Consumer tests via Stub Runner pin the right stub version and assert consumer logic.
- [ ] CI records verification evidence alongside unverified boundaries.

**Takeaway:** The base test in Spring Cloud Contract **controls execution conditions so producer behavior can be verified repeatably**. Mocked clocks, test ID generators, and isolated fixtures are not tricks to "turn tests green"—they remove external noise from verification. Contracts must still accurately state commitments, and generated producer tests plus stub/consumer tests must share the exact same revision to catch breaking API changes.
