# Balancing Test Speed with Confidence

## Lesson Objectives

**Spring Cloud Contract** helps producers and consumers agree on HTTP or messaging behavior using **Groovy/YAML DSL**. Contract Verifier generates producer-side tests; stub artifacts allow consumers to test code against described producer behavior via **Stub Runner**; these checks can run in CI to catch incompatible API changes.

A system can have hundreds of contracts, many consumers, multiple brokers, and multiple environments. Running every type of test after every change makes pipelines slow and resource-heavy. Running only a few unit tests or a single consumer stub test may keep the pipeline green while missing bugs in serialization, message routing, transactions, or real integrations.

This lesson **“Balancing Test Speed with Confidence”** belongs to the **Strategy Selection** chapter. Its goal is to design a **risk-based test portfolio**: each test type answers a clear question, runs at the right stage, and states the boundaries of its evidence explicitly.

After this lesson, you will be able to:

- Distinguish the confidence provided by unit, producer contract, consumer Stub Runner, broker integration, and end-to-end tests.
- Select the minimum test set required on pull requests, nightly runs, and before release.
- Decide which tests to run when changing contracts, DTOs, serializers, bindings, brokers, or business logic.
- Optimize speed with deterministic fixtures, test isolation, parallelism, and safe caching.
- Reduce flaky tests without masking failures behind unconditional retries.
- Use negative tests, mutation checks, and consumer compatibility matrices to evaluate assertion quality.
- Measure pipeline duration, failure rates, flakiness, and feedback times without sacrificing critical evidence.
- Design CI gates for producers and consumers with stub artifact provenance.

**Core principle:** speed and confidence are not mutually exclusive. Run cheap, deterministic, early-catching checks frequently; run costlier integration checks for changes carrying matching risks; and always maintain a release gate with sufficient evidence for the supported scope.

## 1. Why is a testing strategy needed?

Suppose a system has:

- Order Service emitting `ORDER_PAID` events.
- Shipping Service consuming the event and creating shipments.
- Billing Service updating payment ledgers.
- Notification Service sending alerts.
- Multiple HTTP consumers calling the Order API.

Each producer contract can spawn multiple scenarios; each consumer has its own tests; some flows require a broker, database, or integrated environment. Standing up a full production-like environment for every PR slows down feedback. Testing only with internal mocks lets message schema changes break consumers undetected.

A sound strategy answers four questions:

1. **What can break?** For example, schemas, serialization, destinations, ordering, idempotency, or business logic.
2. **Which test catches that failure mode?**
3. **How long does that test take and what resources does it need?**
4. **When must its result arrive before merging or releasing?**

### Two ways strategies fail

| Strategy | Consequence |
| --- | --- |
| Running everything on every PR | Slow feedback, high cost; developers ignore or try to skip tests |
| Running only unit tests and mocks | Misses many contract, serialization, binding, and integration bugs |
| Running E2E for every change | Flaky, hard to diagnose root cause, heavy environments |
| Running only Stub Runner | Does not prove the real producer emits the right responses/messages |
| Running only producer contract tests | Does not prove consumers handle new stubs properly |
| Running tests without checking reports | A green build may hide 0 tests or skipped tests |

The goal is **putting the right test at the right gate**, not maximizing test count.

## 2. Evidence provided by each test layer

~~~mermaid
flowchart TD
    A["Unit tests"] --> B["Producer contract verification"]
    B --> C["Consumer Stub Runner tests"]
    C --> D["Component / broker integration"]
    D --> E["End-to-end / deployment verification"]
    A -.-> X["Fast, isolated"]
    B -.-> Y["Does the producer satisfy the contract?"]
    C -.-> Z["Does the consumer handle stub contracts?"]
    D -.-> U["Do adapters/brokers/transactions work?"]
    E -.-> V["Do deployed components collaborate?"]
~~~

This diagram shows a **scope-based test portfolio**, not a rigid pyramid every project must follow. Some consumer contract tests can be faster than many integration tests; some producer contract tests actually boot a Spring context and sit in component-test territory.

| Layer | Core question | Relative speed | Confidence / limitations |
| --- | --- | --- | --- |
| Unit test | Is domain/helper logic correct? | Very fast | Does not prove HTTP/message wiring |
| Producer contract test | Does the real producer satisfy the contract? | Fast to medium | Depends on base test, adapter, and test mode |
| Consumer Stub Runner test | Does the consumer handle producer behavior described by stubs? | Fast to medium | Does not prove production broker semantics |
| Component/integration test | Do adapters, serializers, DB, and broker collaborate properly? | Medium to slow | Reliable only for the tested config/resources |
| End-to-end test | Do deployed flows across multiple services work? | Slow, many dependencies | Covers few scenarios, hard to isolate failures |

No layer completely replaces another. For instance, passing generated producer tests does not prove the Billing consumer can parse the payload; passing Stub Runner consumer tests does not prove production Kafka ACLs, partition assignments, or retry policies.

## 3. Distinguish producer verification from consumer verification

Spring Cloud Contract produces two vital pieces of evidence.

### Producer side

Contracts describe request/response or message outputs. Contract Verifier generates tests that trigger the producer and check actual behavior.

For message contracts, `input.triggeredBy` invokes a method in the base test to trigger producer logic; the verifier observes emitted messages and compares destination, headers, and body.

### Consumer side

Consumer tests load the producer's stub artifact using Stub Runner. For HTTP, consumers call the stub endpoint. For messaging, `StubTrigger` can trigger message stubs by label, and the consumer's binding/handler processes them.

~~~mermaid
flowchart LR
    A["Contract source"] --> B["Producer generated test"]
    B --> C["Producer implementation"]
    C --> D["Actual response/message"]
    D --> E["Producer assertions"]
    A --> F["Stub artifact"]
    F --> G["Consumer Stub Runner"]
    G --> H["Consumer code"]
    H --> I["Consumer business assertions"]
~~~

**Producer tests** answer: “Does this producer implement the contract?”

**Consumer stub tests** answer: “Does this consumer handle the simulated contract behavior?”

Both are required to control two-sided compatibility. Neither suite automatically proves the other side.

## 4. Confidence is not synonymous with production likeness

A test can boot heavy frameworks and still miss critical behavior. For example:

- A Spring context using a test binder does not verify real Kafka serialization.
- A WireMock stub test does not verify TLS between services.
- An in-memory test database does not prove production database transaction isolation.
- An E2E test going through an API gateway that only checks status 200 misses business payload errors.
- A unit test mocking a publisher can PASS even when the publisher binds the wrong destination.

Therefore, evaluate tests by **observed behavior and covered failure modes**, not merely by how many dependencies are booted.

| Test setup | Tests well | Should not be inferred |
| --- | --- | --- |
| Unit + mock publisher | Domain decision invokes publish call | Broker received message |
| Producer verifier + test binder | Producer triggers output per contract in adapter test | Production broker ACL/partition/retry |
| Consumer + StubTrigger/test binder | Consumer handler processes message stub | Production broker delivery guarantees |
| Consumer + WireMock | HTTP client and business code handle response | Real producer implementation |
| Broker container integration | Serializer, broker protocol, binding, and real consumer | Full deployed network/security if untested |
| E2E deployed environment | One real coordinated flow in the deployed environment | All data edge cases and all consumers |

**Test fidelity** is how closely the environment resembles the real system. **Test confidence** is how much evidence the test provides for a specific question. High fidelity does not automatically mean high confidence if assertions are weak.

## 5. Selecting tests by change risk

Not every change needs the same test suite.

| Change | Primary risk | Priority tests |
| --- | --- | --- |
| Modify internal fee calculation algorithm | Business calculation | Unit + outcome-relevant producer/consumer tests |
| Change response field/type | Schema compatibility | Producer contract + consumer matrix |
| Change HTTP path/headers | Routing/content negotiation | Producer contract + consumer Stub Runner |
| Change message destination | Binding/routing | Producer message contract + consumer binding + broker integration |
| Change serializer/Jackson config | Wire representation | Producer contract + consumer tests + serialization integration |
| Change retry/acknowledgement | Delivery semantics | Unit/policy tests + broker integration |
| Change transaction/outbox | Atomicity/duplicate events | Integration with appropriate DB/broker |
| Change TLS/ACL/credentials | Security/connectivity | Environment integration/security tests |
| Behavior-preserving refactor | Logic regression | Unit + scoped relevant contract suite |
| Upgrade SCC/Boot/WireMock | Tool compatibility | Build/generation + producer verification + Stub Runner compatibility |

### A risk-based decision

Consider:

- **Impact:** if it breaks, how many consumers or transactions are affected?
- **Likelihood:** does the change touch serialization, routing, or shared code?
- **Detectability:** is the bug easy to spot in cheap tests?
- **Recovery cost:** is rolling back or migrating data/events hard?
- **Blast radius:** is one service or multiple domains/consumers impacted?

A small change in a shared event schema can carry higher risk than changing many lines in an internal helper.

## 6. Splitting pipelines into PR, nightly, and release gates

A commonly helpful tiering:

<box>
  <title>PR gate</title>
  <text color="secondary" size="sm">Fast feedback for every change</text>
  - Compile/static checks and unit tests.
  - Producer contract tests of affected modules.
  - Consumer Stub Runner tests of affected consumers.
  - Verify generated test counts and test reports.
  <divider color="subtle"/>
  <title>Nightly / scheduled gate</title>
  <text color="secondary" size="sm">Broader coverage and interaction discovery</text>
  - Broader consumer compatibility matrix.
  - Broker/database integration in isolated environments.
  - Retry, duplicate, ordering, and error scenarios.
  - Selected E2E tests and flakiness tracking.
  <divider color="subtle"/>
  <title>Pre-release gate</title>
  <text color="secondary" size="sm">Evidence for the exact artifact about to release</text>
  - Producer verification on final commit/revision.
  - Immutable stub artifact and provenance.
  - Required consumers verified against the exact stub.
  - Migration/deprecation gates and deployment smoke tests.
</box>

This is a **baseline proposal**; adjust it to your organization's criticality and feedback times. If a change directly impacts payments, access control, or unrecoverable data, certain integration/security tests must run pre-merge instead of waiting for nightly.

### Do not push all expensive tests to nightly

If a contract change could prevent a primary consumer from deserializing payloads, the corresponding consumer compatibility test must run **before merge**. Nightly only expands scope to less frequent or more resource-intensive combinations.

## 7. Minimum PR gate for producers

For a Spring Cloud Contract producer:

1. Compile application and test code.
2. Run unit tests for business logic/serialization helpers.
3. Discover contracts and generate tests.
4. Run all affected producer contract scenarios.
5. Verify generated tests actually executed and were not skipped.
6. Package the stub artifact if the pipeline needs immediate consumer validation.
7. Record contract revision and producer commit.

A common Maven command:

~~~bash
./mvnw clean verify
~~~

Yet this command is only meaningful when plugin goals are bound/configured and test reports prove generated tests ran. **Never rely on exit code 0 alone.**

### Selecting test scope

If a change only touches one domain contract and the build supports reliable test selection, running only the affected suite on PRs can speed things up. However:

- Changes to shared contracts/base classes can affect many scenarios.
- Changes to plugin/DSL config require running all related generated tests.
- CI must know exactly which tests were skipped and why.
- Nightly or pre-release still needs the full required suite.

Never use test filtering to hide a FAILing test.

## 8. Minimum PR gate for consumers

Consumers must test against stubs of **the producer version/revision targeted by the PR**.

HTTP consumer test example:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:2.5.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired
    private OrderClient orderClient;

    @Test
    void readsPaidOrder() {
        OrderView order = orderClient.getOrder("ORD-1001");

        assertThat(order.status()).isEqualTo("PAID");
        assertThat(order.id()).isEqualTo("ORD-1001");
    }
}
~~~

This example assumes artifact `2.5.0` is installed in the local repository and the client is configured to call the matching stub port. In CI, use pipeline-managed artifacts/repositories and ports.

The consumer gate must verify:

- Stub Runner resolves the exact GAV/classifier/version.
- HTTP requests actually match mappings.
- Response bodies deserialize cleanly.
- Consumer business logic yields expected results.
- Important fields/headers are processed.
- Tests do not merely assert that Stub Runner booted.

For message consumers, use `StubTrigger` to trigger message stubs by label, then verify the handler and business state.

## 9. What should run nightly?

Nightly suits time-consuming or wide-scope combinations:

- Consumer matrix across multiple still-supported producer versions.
- Older consumers against newer producer stubs during active schema evolution.
- Broker integration with Kafka/RabbitMQ or the system's real broker.
- Retry, redelivery, duplicate, ordering, and dead-letter scenarios.
- Database transaction/outbox consistency.
- Multi-partition/consumer-group tests when required.
- E2E flows across gateways and multiple services.
- Runtime compatibility checks after JDK/framework upgrades.
- Flakiness scans and test duration statistics.

Nightly must produce **traceable artifacts and reports**. If a nightly producer build uses a different commit or different stub bytes than a PR, never substitute those results as evidence for the candidate about to release.

## 10. Pre-release gate: verifying the exact artifact to release

Before releasing, verify the final producer commit and contract revision:

~~~mermaid
flowchart TD
    A["Release candidate commit"] --> B["Producer contract verification"]
    B --> C{"All required scenarios PASS?"}
    C -->|No| X["BLOCK release"]
    C -->|Yes| D["Package immutable stub JAR"]
    D --> E["Record GAV + SHA-256 + contract revision"]
    E --> F["Run required consumer tests"]
    F --> G{"Consumer matrix PASS?"}
    G -->|No| X
    G -->|Yes| H["Deployment smoke / release checks"]
    H --> I["Release decision"]
~~~

**Artifact identity matters more than visible coordinates.** With SNAPSHOTs or overwritable repositories, the same GAV can return different bytes. Use immutable release artifacts or record checksums and verify consumers fetched the exact bytes.

The pre-release gate should check:

- Generated producer tests PASS.
- No required tests are skipped.
- Stub artifact contains the right mappings/resources.
- Required consumer versions PASS against the new stub.
- Compatibility/deprecation decisions are approved.
- Test reports tie to the source commit and artifact checksum.

## 11. The test pyramid is not a fixed formula

A common visualization is many unit tests, fewer integration tests, very few E2E tests. With Spring Cloud Contract, think in terms of **cost and scope**, not rigid percentages.

~~~mermaid
flowchart TD
    E["E2E / deployed workflows"] --> I["Broker / DB / HTTP integration"]
    I --> C["Producer + consumer contract tests"]
    C --> U["Unit tests"]
    style U fill:#d9f2e6,stroke:#3d8b67,color:#173d2d
    style C fill:#e5efff,stroke:#5077b5,color:#1e3558
    style I fill:#fff0d9,stroke:#b88736,color:#503b18
    style E fill:#f5e5f2,stroke:#a66a9a,color:#4b2944
~~~

- Unit tests are usually cheap and plentiful.
- Producer contract tests may boot a Spring context, so they are not always ultra-cheap.
- Consumer Stub Runner tests are usually faster than broker integration yet may still need an application context.
- Broker integration tests cost more, yet are indispensable for delivery semantics.
- E2E tests are few, yet protect selected business-critical flows.

**Do not set “E2E under 5%” as a universal rule.** The right count depends on domain, architecture, and isolation capability.

## 12. A contract test does not replace business logic unit tests

Fee calculation service example:

~~~java
public BigDecimal calculateShippingFee(
        BigDecimal orderAmount,
        String region) {
    // Business rules
}
~~~

Unit tests are ideal for verifying:

- Boundary amounts.
- Regional rules.
- Free shipping thresholds.
- Rounding and currency.
- Invalid inputs.

Producer contract tests are ideal for verifying:

- HTTP responses contain the right fee field/type.
- Status/headers/body adhere to the contract.
- The producer endpoint calls logic and serializes results properly.

With only a contract test using fixture `amount=125000`, many fee branches go untested. With only unit tests, a response DTO could be renamed without unit tests noticing.

The two test types **complement each other**.

## 13. Consumer Stub Runner tests do not replace broker integration

Stub Runner is useful for testing consumers against packaged producer behavior. Yet it does not prove all broker semantics.

| What to protect | Stub Runner/test binder | Broker integration |
| --- | --- | --- |
| Consumer parses message schema | Testable | Testable |
| Handler business logic | Yes | Yes |
| Destination/label per contract | Yes, within adapter scope | Yes |
| Kafka partition assignment | No | Yes |
| Broker ACL/authentication | No if test does not connect to broker | Yes |
| Consumer group rebalancing | No | Yes |
| Real retry/DLQ | Only if explicitly simulated; does not prove broker policy | Yes |
| Transactional publish/outbox atomicity | Insufficient | Requires appropriate DB/broker integration |
| Network/TLS between services | No | Requires matching environment test |

If the system depends on ordering or redelivery, dedicate broker integration tests to those behaviors. Do not force every PR to boot a broker when changes do not affect it; equally, never skip the integration suite when changing adapters/retries/partitions.

## 14. Choosing test depth by change type

### Contract file changed

Run:

- Generated producer tests for the contract.
- Related producer scenarios.
- Consumers using that contract.
- Compatibility matrix if changing fields/types/requiredness.
- Stub packaging/provenance if artifacts are published.

### DTO or serializer changed

Run:

- Unit tests for mapping/serialization.
- Producer contract tests.
- Consumer tests with stubs.
- If serializer/framework config changed broadly, run component integration.

### Binding/destination changed

Run:

- Producer message verification.
- Consumer StubTrigger/binding tests.
- Broker integration for real destination/routing.
- Related consumers.

### Retry/acknowledgement/transaction changed

Run:

- Unit tests for retry policy/idempotency.
- Consumer handler tests.
- Broker/DB integration with redelivery and failure injection.
- Selective E2E if cross-service transactions changed.

### Build plugin/toolchain changed

Run:

- Plugin resolution and dependency graph checks.
- Contract discovery/generation.
- Compilation of generated sources.
- Producer tests.
- Stub packaging and consumer Stub Runner tests.
- Do not run application unit tests alone.

## 15. Consumer compatibility matrix: which consumers to test?

Not all consumers share the same priority.

Example inventory:

| Consumer | Criticality | Deploy frequency | Strategy |
| --- | --- | --- | --- |
| Checkout | Critical | Daily | Mandatory PR gate |
| Billing | Critical | Weekly | PR gate with new stub |
| Analytics | Medium | Monthly | Nightly + pre-release |
| Legacy Export | Low but still supported | Infrequent | Scheduled/deprecation compatibility suite |

This is sample data. Organizations must identify **which consumers remain supported** and their real impact levels.

### How to reduce combinations

- Run all critical consumers on PRs when breaking-risk contract changes occur.
- Run all supported consumers nightly or pre-release.
- Run older versions likely to use strict deserialization during migrations.
- Skip unrelated combinations only when reliable impact analysis exists.
- Maintain periodic checks for rarely deployed yet still supported consumers.

**Infrequently deployed consumers are not low risk**; on the contrary, older consumers are often the most vulnerable to breaking changes.

## 16. Impact analysis to run only relevant tests

You can maintain a dependency map:

~~~text
order-service contract
  ├── checkout-service
  ├── billing-service
  ├── shipping-service
  └── analytics-service
~~~

When the Order contract changes:

- Checkout and Billing may need immediate runs because they are critical.
- Shipping must run if related message schemas changed.
- Analytics can run nightly if not on the release path, yet must not be forgotten before release if still supported.

Impact analysis must rely on **consumer inventory/contract ownership**, not just grepping artifact names in source code. A consumer might pull stubs via a dependency version catalog or repository config.

If unsure the impact map is complete, run more broadly rather than missing a consumer.

## 17. Deterministic tests: foundation of fast pipelines

Fast but unstable tests erode trust. Suites commonly flake due to:

- Shared data.
- Current wall-clock time/timezones.
- Unfixed random IDs.
- Async messages not yet arriving when assertions run.
- Port or resource conflicts under parallel execution.
- Test ordering depending on state from prior tests.
- External APIs/networks.
- Retries or schedulers continuing to run after a test ends.

### Rules for making tests deterministic

- Synthetic fixtures with unique IDs.
- Injected or fixed Clocks when testing time.
- Dedicated test DB/broker namespaces.
- No shared mutable static state.
- Async assertions with finite timeouts and clear conditions.
- Cleanup deletes only resources owned by the test.
- External dependencies stubbed or run in isolated test environments.
- No dependence on test execution order.

### Example with Clock

~~~java
@Service
public class InvoiceService {
    private final Clock clock;

    public InvoiceService(Clock clock) {
        this.clock = clock;
    }

    public Instant createdAt() {
        return Instant.now(clock);
    }
}
~~~

In tests, inject `Clock.fixed(...)` so time is deterministic. Consequently response timestamps stay consistent across runs, making producer contract tests far easier to reproduce.

## 18. Async message tests: wait on conditions, not fixed sleeps

Anti-pattern:

~~~java
stubTrigger.trigger("order_paid");
Thread.sleep(3000);
assertThat(repository.findByOrderId("ORD-1001")).isPresent();
~~~

This wastes three seconds when messages process quickly, yet still flakes if CI takes longer than three seconds.

Use polling with a deadline:

~~~java
stubTrigger.trigger("order_paid");

await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(repository.findByOrderId("ORD-1001"))
            .isPresent()
    );
~~~

Requirements:

- Timeouts reflect the test environment SLA.
- Polling condition is observable.
- On timeout, log enough detail for diagnosis.
- Never inflate timeouts indefinitely to hide deadlocks.
- Clean up messages/records between tests.

Awaitility is one option; synchronous APIs or latches work too if suited to the adapter. What matters is waiting for **a concrete condition**, not an arbitrary duration.

## 19. Parallelism and isolation

Running tests in parallel reduces wall-clock time, yet is safe only when test resources are independent.

| Resource | Risk under parallel runs | How to isolate |
| --- | --- | --- |
| HTTP stub ports | Port collisions | Dynamic ports or Stub Runner managed ports |
| Database rows | Deleting/overwriting another test's fixtures | Separate schemas/namespaces/test IDs |
| Message destinations | Tests consume each other's events | Separate destinations/groups or correlation IDs |
| Static HTTP client config | Global state overwritten | Instance-scoped config or disable parallelism for that group |
| Shared filesystem | Same-named files overwritten | Dedicated temp directories |
| Testcontainers | Startup contention | Controlled reuse, clear lifecycle |
| Schedulers/background jobs | Jobs run after tests finish | Disable/scope schedulers in tests |

Do not enable parallel execution just because CI agents have many CPUs. First confirm the test suite **shares no mutable state**.

### Running by group

You can group as follows:

- Unit tests: heavily parallel when stateless.
- Producer contract tests: parallel when Spring contexts and HTTP/message fixtures are safe.
- Stub Runner tests: parallel when ports, artifact caches, and binder resources are isolated.
- Broker integration: cap concurrency according to broker/container resources.

Measure wall-clock time and failure rates after enabling parallelism.

## 20. Caching and environment reuse: fast yet safe

You can optimize:

- Maven/Gradle dependency caches.
- Build caches for deterministic tasks.
- Reusing container image layers.
- Reusing Spring test contexts when configurations match.
- Downloading stub artifacts once per job.
- Running impact-based tests in parallel.

Yet caching can invalidate tests if cache keys omit critical inputs.

**Cache keys should reflect:**

- Build files/lockfiles.
- JDK/toolchain versions.
- Contract revisions.
- Producer artifact versions/checksums.
- Plugin/dependency versions.
- Test configurations affecting generated sources/mappings.

### Stub cache risks

If a consumer uses the same GAV while a repository overwrites artifacts, caches can serve stale stub bytes. Use immutable release artifacts or record checksums. Never assume `2.5.0-SNAPSHOT` today matches yesterday.

### Reusing Spring contexts

Spring Test context caching saves time, provided tests do not mutate shared global beans/configs in ways that leak state. If a test alters properties, mocks beans, or mutates static HTTP config, examine lifecycle and context cache behavior.

## 21. Negative tests: proving assertions can catch bugs

A test that merely PASSes on a valid response does not prove matchers are strong enough.

For example, the contract requires `status = PAID`. You must know whether the test FAILs if the producer returns `PENDING`.

Negative tests can check:

- Missing required fields.
- Wrong JSON types.
- Disallowed field renames.
- Wrong status codes.
- Wrong destinations.
- Wrong content-type headers.
- Duplicate event IDs.
- Consumer receiving unsupported event types.
- Consumer mishandling null/missing fields.

### Example payload type test helper

~~~java
@Test
void rejectsStringAmountWhenNumberIsRequired() {
    String payload =
        "{\"orderId\":\"ORD-1001\",\"amount\":\"125000\"}";

    assertThatThrownBy(() ->
        objectMapper.readValue(payload, OrderPaidEvent.class)
    ).isInstanceOf(Exception.class);
}
~~~

This is an illustrative example; the exact exception depends on DTO/Jackson configuration. If the application allows coercion, tests must verify the chosen semantics instead of assuming the parser always rejects it.

**There is no need to duplicate every contract scenario into a negative test.** Pick key invariants and failure modes at risk of slipping past matchers.

## 22. Mutation testing and contract quality

One way to evaluate test quality is deliberately introducing faulty changes (mutations) and checking whether tests catch them.

Mutation examples:

- Change response `status` from `PAID` to `PENDING`.
- Change `amount` from number to string.
- Drop the `Content-Type` header.
- Change destination `orders.events` to `order.events`.
- Skip publishing the message in the producer.
- Consumer ignores `eventId` and creates duplicate shipments.

If all tests still PASS, likely causes include:

- The test did not run.
- Matchers are too loose.
- Test fixtures mocked out the behavior under verification.
- Consumer assertions only checked the trigger result.
- The mutation was outside the tested code path.

Dedicated mutation testing can be time-consuming. Start with a few **controlled negative cases** on critical contracts; expand where valuable.

## 23. Flaky tests and retries: do not mask bugs with reruns

Retrying a flaky test can help distinguish transient infrastructure failures, yet unconditionally retrying every test can mask race conditions or real bugs.

A sound policy:

- Record the **first-run** result.
- If retried, mark the test as flaky/quarantined under an explicit policy.
- Track retry counts and flakiness rates.
- Assign an owner and resolution deadline.
- Never equate “PASS on retry” with “stable PASS.”
- For release-critical contracts, investigate flaky tests before releasing.

### Classifying failures

| Type | Example | Action |
| --- | --- | --- |
| Product regression | Contract assertion fails consistently | Block and fix |
| Toolchain regression | Generated test fails to compile after upgrade | Block, check compatibility |
| Test flakiness | Race condition occurring intermittently | Record, isolate, and fix |
| Infrastructure outage | Maven repository/broker unreachable | Controlled retry; do not mark product PASS |
| Test misconfiguration | 0 tests, wrong profile | Block verification |

**An infrastructure failure is not a product PASS.** Pipelines should separate statuses so release decisions remain unambiguous.

## 24. Test data management and cleanup

Contract tests should use synthetic data:

~~~json
{
  "orderId": "ORD-CONTRACT-1001",
  "customerId": "CUS-CONTRACT-1001",
  "amount": 125000,
  "currency": "VND"
}
~~~

Rules:

- Never copy production data into test fixtures.
- Use namespaced IDs to prevent collisions.
- Clean up only rows/events created by the test.
- Never wipe shared topics/tables during parallel runs.
- Ensure cleanup does not mask an earlier failure.
- For event replays, use dedicated event IDs.
- Never log secrets/PII in failure reports.

### Transaction rollback is not universal cleanup

`@Transactional` in tests does not automatically roll back:

- HTTP requests running on separate server threads/transactions.
- Messages already published.
- External service calls.
- Files written to a shared filesystem.
- Async jobs running after the test finishes.

Choose cleanup strategies per resource and verify them with integration tests.

## 25. Measuring pipeline speed and reliability

Do not measure total build time alone. Helpful metrics include:

| Metric | Question |
| --- | --- |
| PR feedback time | How soon do developers receive results? |
| Test duration p50/p95 | Which test groups are slow or volatile? |
| Failure rate by suite | Which suites catch the most defects? |
| Flaky rate | How many tests fail then pass on rerun? |
| Generated tests executed | How many producer scenarios actually ran? |
| Consumer matrix coverage | How many required consumer versions were tested? |
| Stub provenance coverage | How many consumer jobs used exact artifact/checksums? |
| Escaped contract defects | Which contract bugs slipped past CI to later environments? |
| Mean time to diagnose | How long does it take to pinpoint the failing layer? |

### Do not optimize by test count alone

A suite of 500 tests all using the same weak fixtures/matchers can be less trustworthy than 80 tests covering critical failure modes.

Measure both **contract/consumer coverage** and **defect detection capability**. Test count is a signal, not a goal.

## 26. Accounting for a gate's cost

A gate can evaluate:

- Mean and p95 runtime.
- CPU/memory/container usage.
- Broker/database test costs.
- Rerun rates.
- Rate of relevant tests skipped.
- Artifact/repository wait times.
- Triage time on failures.

If a broker integration suite takes 20 minutes, it may not run on unrelated PRs. Yet if destination/retry/ack semantics change, that suite may need to run immediately.

### Allocation by change

| Change | PR | Nightly | Release |
| --- | --- | --- | --- |
| Domain calculation | Unit + relevant contracts | Full regression | Critical flows |
| Response schema | Producer + affected consumers | Full consumer matrix | Required consumers |
| Message schema | Producer messages + consumers | Broker integration + matrix | Producer + required consumers |
| Broker configuration | Relevant integration | Full broker suite | Deployment smoke |
| Toolchain/plugin | Generate + compile + producer + consumer | Full suite | Immutable artifact check |
| Retry/ordering | Unit + related broker tests | Failure injection | Release-critical integration |

This is a starting matrix. Criticality may force a suite to run earlier.

## 27. Practical staged pipeline example

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Compile + static checks"]
    B --> C["Unit tests"]
    C --> D["Producer Contract Verifier"]
    D --> E["Build immutable stub artifact"]
    E --> F["Affected consumer Stub Runner tests"]
    F --> G{"PR gates PASS?"}
    G -->|No| X["Block merge"]
    G -->|Yes| H["Merge / publish candidate"]
    H --> I["Nightly: full consumer matrix"]
    I --> J["Broker + DB integration"]
    J --> K["E2E critical flows"]
    K --> L["Pre-release artifact provenance + required consumers"]
    L --> M["Release decision"]
~~~

### Neutral stage declaration template

~~~yaml
# CI pseudocode, not the syntax of any specific CI provider.
stages:
  pull_request:
    - compile
    - unit_tests
    - producer_contract_tests
    - package_stub
    - affected_consumer_stub_tests

  nightly:
    - full_consumer_matrix
    - broker_integration
    - database_integration
    - critical_e2e
    - flakiness_report

  pre_release:
    - producer_verification_on_release_commit
    - immutable_stub_checksum
    - required_consumer_matrix
    - deployment_smoke
~~~

Specific CI providers must translate these stages into corresponding workflows/jobs/dependencies. Do not paste YAML pseudocode into GitHub Actions/Jenkins expecting it to run.

## 28. Example test selection for a message schema change

Suppose Order Service changes an event from:

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "ORDER_PAID",
  "orderId": "ORD-1001",
  "amount": 125000
}
~~~

to:

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "ORDER_PAID",
  "orderId": "ORD-1001",
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

This is a field/type/semantics change. Strategy:

**PR gate:**

- Producer message contract tests for the new schema and legacy behavior if still supported.
- Consumer Stub Runner tests for Shipping/Billing.
- Unit tests for amount/currency mapping.
- Checks on strict deserializers across consumers.

**Nightly:**

- Full consumer versions matrix.
- Broker integration with real serializers.
- Duplicate/replay tests.
- Retry/DLQ if events flow through a broker.

**Pre-release:**

- Verified producer commit/contract revision.
- Immutable stub artifact.
- Mandatory consumers verified against the exact stub.
- Telemetry/deprecation approvals if removing old fields.

You do not need to run full-system E2E for documentation edits that do not change behavior, yet this schema change must never rely on unit tests alone.

## 29. Example: testing real behavior instead of just the trigger

A weak consumer message test:

~~~java
@Test
void canTriggerOrderPaidStub() {
    assertThat(stubTrigger.trigger("order_paid")).isTrue();
}
~~~

A stronger test:

~~~java
@Test
void createsShipmentFromOrderPaidEvent() {
    assertThat(stubTrigger.trigger("order_paid")).isTrue();

    await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
            assertThat(shipmentRepository.findByOrderId("ORD-1001"))
                .isPresent()
        );

    Shipment shipment =
        shipmentRepository.findByOrderId("ORD-1001").orElseThrow();

    assertThat(shipment.getEventId())
        .isEqualTo("EVT-ORD-1001-PAID");
    assertThat(shipment.getStatus())
        .isEqualTo("READY_FOR_PICKUP");
}
~~~

The second test verifies the **business outcome**. Yet it still does not prove production broker partition/retry semantics—that belongs to separate integration tests.

## 30. When are E2E tests needed?

Use E2E for flows where multiple components collaborate to deliver business-critical value, such as:

- Customer places order → payment succeeds → event emitted → shipping creates shipment.
- Gateway authorization → producer API → downstream service.
- New event schema published and processed together by deployed consumers.

Keep the E2E suite small, deterministic, and backed by clear test data. On failure, logs/correlation IDs must pinpoint the root cause. Do not turn every business edge case into an E2E test; those are usually easier to test at the unit, contract, or component layer.

### E2E does not replace the contract matrix

E2E typically runs one deployed version of each service. It does not necessarily exercise all older still-supported consumer versions. A contract compatibility matrix remains essential for independent version combinations.

## 31. Selecting confidence levels by criticality

| Domain | Example | Recommended gate |
| --- | --- | --- |
| Low impact | Non-critical internal report field | Unit + relevant contracts; nightly consumers |
| Medium impact | Search/catalog API | Producer + affected consumers on PR; nightly matrix |
| High impact | Order/payment event | Producer + all critical consumers on PR; broker integration/nightly; release matrix |
| Safety/security critical | Authorization, payment settlement, data deletion | Contracts + unit + integration/security + release smoke per risk policy |

This table is a guide; organizations must define their own criticality and regulatory/security requirements. Never downgrade testing for a change solely because pipeline runtime is currently long.

## 32. Anti-patterns that create false speed

| Anti-pattern | Why it is dangerous | Replacement |
| --- | --- | --- |
| Skipping generated tests when slow | Loses producer evidence | Transparent impact selection, nightly/full release gates |
| Only asserting StubTrigger returns true | Does not test consumer business logic | Assert state/outcome |
| Using stale stubs due to caching | Tests do not reflect producer candidate | Pin immutable artifacts/checksums |
| Retrying every failure until PASS | Masks flakiness/product regressions | Record first result, classify, and assign owners |
| E2E for every PR | Slow, hard to triage | Risk-layered testing |
| Unit tests only | Misses serialization/contracts | Producer + consumer contract tests |
| Producer tests only | Misses consumers | Stub Runner consumer tests |
| Stub Runner only | Misses broker semantics | Selective broker integration |
| Shared test database/topic | Flaky and cross-test contamination | Dedicated isolation/namespaces |
| Asserting status code alone | Misses body/schema/business outcomes | Assert headers, payloads, and outcomes |
| Test count as a KPI | Encourages weak tests | Measure risk coverage, flakiness, and escaped defects |
| Nightly PASS instead of release commit | Artifacts/sources differ | Pre-release verification on exact commit/artifact |

## 33. Practice exercises

### Exercise A — Choosing tests for a response field rename

The producer renames `name` to `displayName`. There are three consumers, one using a strict parser.

**Prompt:** which tests must run before merge? Which can run nightly?

**Hint:** the strict consumer must run immediately; the full consumer matrix and infrequently deployed versions can run nightly, yet must PASS before release.

### Exercise B — Domain calculation change

Only regional fee rules change, with no schema changes.

**Prompt:** why are unit tests the primary focus? When are producer contract tests still needed?

**Hint:** unit tests cover boundary/business branches; producer contracts verify the API response still represents the outcome properly.

### Exercise C — Changing message destination

The producer switches destination from `orders.events` to `orders.v2.events`.

**Prompt:** choose tests for PR/nightly/release.

**Hint:** producer message verification and consumer binding tests on PR; broker integration checking real routing; release smoke.

### Exercise D — Retry and redelivery

The consumer adds retries on transient handler errors.

**Prompt:** is a Stub Runner test enough?

**Hint:** unit/policy tests and broker integration are needed to verify redelivery/ack/retry/DLQ semantics.

### Exercise E — 45-minute pipeline

PRs currently run full E2E for 45 minutes even for edits to a pure helper.

**Prompt:** redesign while preserving release confidence.

**Hint:** unit + affected contract tests on PR, full matrix/integration/E2E nightly and pre-release, backed by a trustworthy impact map.

### Exercise F — Test flake

A consumer test intermittently times out waiting for a message; reruns usually PASS.

**Prompt:** what must be measured and checked before raising the timeout?

**Hint:** binder lifecycle, async handler logs, resource contention, shared state, correlation/event IDs, polling condition, and first-failure diagnostics.

### Exercise G — Stub Runner PASSes while producer is untested

The consumer uses a stub artifact from a previous build, and business outcome tests PASS.

**Prompt:** is this sufficient evidence for a new producer release?

**Hint:** no; generated producer tests and stub provenance must tie to the exact commit/revision.

### Exercise H — Producer PASSes while consumers have not run

Producer message contracts PASS and stubs are published.

**Prompt:** can the new event schema be released immediately?

**Hint:** only if release policy permits; critical/supported consumers must verify against the new stub before release.

### Exercise I — Parallel execution

With parallelism enabled, two tests wipe the same table and trigger the same message.

**Prompt:** how to isolate?

**Hint:** namespaces/test IDs, dedicated database schemas, correlation IDs, separate destinations/groups, or limiting parallelism on shared-resource groups.

### Exercise J — Mutation test

Changing contract status from `PAID` to `PENDING` still lets the producer suite PASS.

**Prompt:** list hypotheses.

**Hint:** weak matchers, tests never ran, response fixture mocked out, wrong contract root, or generated tests skipped.

### Exercise K — Criticality

An internal API is used by payment settlement and analytics dashboards.

**Prompt:** choose gates by consumer impact, not API name.

**Hint:** the critical payment consumer needs a PR gate; the dashboard can run nightly if non-release-critical, yet still needs pre-release verification if supported.

### Exercise L — Stale stub cache

Consumer tests run faster after caching, yet still use an old stub checksum.

**Prompt:** how to optimize caching without losing provenance?

**Hint:** cache by immutable artifact identity/checksum, invalidate on GAV/build inputs, log resolved artifacts.

## 34. Test strategy design checklist

### Scope and risk

- [ ] Identified affected producers, consumers, and contracts/events.
- [ ] Classified behavioral impact/criticality.
- [ ] Identified failure modes: schemas, routing, serialization, business logic, brokers, security.
- [ ] Consumer inventory and ownership exist.
- [ ] Do not infer coverage from file names or test counts.

### Producer and consumer evidence

- [ ] Generated producer tests are actually generated and executed.
- [ ] Producer base tests exercise real application behavior.
- [ ] Consumer Stub Runner uses the exact stub version.
- [ ] Consumer tests assert business outcomes, not just triggers/server startup.
- [ ] Producer commit, contract revision, GAV, and checksum are traceable.
- [ ] Required consumers ran at the appropriate gates.

### Integration and E2E

- [ ] Broker integration runs when changing adapters, retries, acks, partitions, or delivery semantics.
- [ ] Database integration runs when changing transaction/outbox/persistence semantics.
- [ ] Security/network tests exist when changing TLS, ACLs, or credentials.
- [ ] E2E focuses on critical flows and supports triage.
- [ ] Limits of test binders/Stub Runner are explicitly documented.

### Speed and stability

- [ ] PR gate delivers feedback within target time.
- [ ] Nightly covers broader combinations.
- [ ] Pre-release runs on the exact commit/artifact.
- [ ] Fixtures are deterministic and use no production data.
- [ ] Async tests wait on conditions with finite timeouts.
- [ ] Parallel tests enforce resource isolation.
- [ ] Retries never mask product failures.
- [ ] Cache keys reflect dependency/toolchain/artifact inputs.
- [ ] Test reports record executed/skipped/failed counts.
- [ ] Flakiness, p95 duration, and escaped defects are tracked.

## Conclusion

Balancing speed with confidence in Spring Cloud Contract means **allocating evidence by risk**. Unit tests verify fine-grained logic; generated producer tests verify the producer implements the contract; consumer Stub Runner tests verify consumers handle agreed behavior; broker/database integration tests verify infrastructure semantics; E2E tests verify a select set of critical deployed flows.

PRs should run fast checks capable of catching regressions directly caused by the change. Nightly runs expand the consumer matrix and infrastructure integration. Pre-release verifies the exact producer commit, contract revision, stub artifact, and mandatory consumers. Keeping pipelines both fast and trustworthy requires deterministic tests, resource isolation, provenance-aware caching, negative tests, and reports proving tests actually executed.

**Key takeaway:** *Do not measure confidence by test count or build duration. Ask which behavior each test protects, which failure modes remain uncovered, and whether the evidence ties directly to the producer/consumer artifacts about to be released.*
