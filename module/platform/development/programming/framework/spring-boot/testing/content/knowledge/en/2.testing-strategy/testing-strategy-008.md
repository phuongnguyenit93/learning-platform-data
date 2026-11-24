# The TDD Loop and Choosing Entry Points in Spring Boot

**Test-Driven Development (TDD)** is a way of developing software in tight feedback loops: **write a test describing a desired behavior, watch it fail because that behavior is not yet satisfied, write the minimum code to make the test pass, and refine the design while tests stay green**. In a Spring Boot project, the key decision is not just whether to use TDD, but **which boundary to start at**: plain logic, service, HTTP, persistence, or an integration flow.

TDD is a design and feedback strategy. It does not automatically guarantee requirements are right, replace code reviews, or prove external components outside the application work. TDD's value comes from giving developers a verifiable behavioral example *before* implementation and continuously using tests to catch drift.

## 1. Red – Green – Refactor Is a Loop, Not Three Big Phases

| Phase | What to Do | Signal to Advance |
| --- | --- | --- |
| **Red** | Pick **one next behavior**; write a test with concrete inputs and observable outcome; run it | The test compiles/runs and **fails for the right reason**: the target behavior is missing or wrong |
| **Green** | Make the smallest change needed so the new test and related tests pass | New test is green and existing related tests stay green |
| **Refactor** | Remove duplication, improve names, clarify responsibilities or structure **without changing behavior** | Suite stays green; design is clearer |

One cycle may take a few minutes; there is no need to force every cycle to sixty seconds. The right pace is whatever lets you tell precisely **which change** flipped a test between red and green.

### Red Must Fail “Meaningfully”

- First, the test must describe a **public outcome**: return value, exception, persisted state, HTTP status/body, event, or outbound dependency call.
- Failing because the expected assertion does not match actual behavior is the clearest signal. While shaping an API, a brief compile error can appear; bring the code to a compilable skeleton so you verify the test genuinely detects the missing behavior.
- If a test fails because a container is down, a secret is missing, a hostname is wrong, the DB is unseeded, or another test polluted state, that is an environment/setup error; **do not count it as a valid Red**.
- You may intentionally tweak an expected value temporarily to confirm an assertion is sensitive, but never leave a test altered and green for the wrong reason.

### Keep Green Deliberately Minimal

During Green, returning a constant or adding a simple condition is often completely reasonable. A single test usually justifies only one case. The **next test** drives generalization. Do not pre-implement multiple untested branches to “save cycles,” because doing so forfeits step-by-step feedback.

### Refactor Without Adding New Behavior

Refactoring happens while green: rename variables, extract constants, clarify dependency boundaries, or remove duplication. If you want to change outcomes for a new input, write a new **Red** test first. Avoid mixing major business-rule changes with refactoring so you always know why a failure occurred.

**One complete cycle:**

```text
Pick a small behavior
       ↓
Write a new test → RED (fails for the right reason)
       ↓
Write minimal code → GREEN (related tests pass)
       ↓
Refactor → re-run tests (still GREEN)
       ↓
Pick the next behavior
```

TDD differs from implementing everything first and adding tests at the end to boost coverage: tests written afterward remain useful, yet they miss providing API and design feedback *before* the code solidifies.

## 2. Pick a Small Behavior Before Picking a Test Annotation

Before each cycle, answer briefly:

1. **Behavior:** “When [condition], the system must [observable outcome].”
2. **Boundary:** which logic must run for real to substantiate the outcome?
3. **Red signal:** specifically how will the test fail before the behavior exists?
4. **Execution cost:** do we need a Spring context, HTTP, database, broker, or external system?
5. **Smallest step:** which condition/edge case suffices for **one** cycle?

For example, for shipping fees: “When the subtotal is 500,000 VND or more, shipping fee is 0 VND.” This is a calculation rule, so start with a real Java class and plain JUnit. There is no reason yet to boot a web server or touch a database.

Conversely, “When a user sends malformed JSON, the endpoint returns 400 with the standard error body” is an HTTP contract. Testing a Java method directly skips Spring's parsing, binding, validation, and exception mapping. That behavior belongs in a matching web slice or integration test.

**You do not have to start TDD at the controller** simply because users call the app over REST. Start wherever the target behavior can be observed with the narrowest boundary and fastest reliable feedback.

## 3. Complete TDD Example: Shipping Fee Policy

**Agreed business requirements for the example:**

- Non-negative subtotal below `500_000` VND: fee is `30_000` VND.
- Subtotal of `500_000` VND or more: free shipping (`0` VND).
- Negative subtotal: rejected with `IllegalArgumentException`.

We isolate this calculation into `ShippingFeePolicy`, using `long` for whole VND amounts to avoid floating-point rounding issues in the example. These rules require no database, HTTP, Spring beans, or Mockito.

Assume a Spring Boot project configured with Gradle and Java 17+. Files:

```text
src/
├── main/java/example/testing/shipping/ShippingFeePolicy.java
└── test/java/example/testing/shipping/ShippingFeePolicyTest.java
```

In a Gradle Spring Boot project with plugins and dependency versions already configured, tests need JUnit Jupiter via `spring-boot-starter-test`. The relevant excerpt in `build.gradle` (Groovy DSL) is:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This configuration snippet is an **excerpt** added to a Spring Boot project that already configures plugins and dependency management/BOM; it is not a standalone `build.gradle`.

### Cycle 1: Free at Threshold

**Red — write one test first:**

Create `src/test/java/example/testing/shipping/ShippingFeePolicyTest.java`:

```java
package example.testing.shipping;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ShippingFeePolicyTest {
    @Test
    void subtotalAtThresholdHasFreeShipping() {
        ShippingFeePolicy policy = new ShippingFeePolicy();
        assertEquals(0L, policy.feeFor(500_000L));
    }
}
```

To observe an assertion failure rather than stopping at a missing-class compile error, create a minimal skeleton at `src/main/java/example/testing/shipping/ShippingFeePolicy.java`:

```java
package example.testing.shipping;

public final class ShippingFeePolicy {
    public long feeFor(long subtotalVnd) {
        return -1L; // Policy not implemented yet
    }
}
```

Run:

```bash
./gradlew test --tests example.testing.shipping.ShippingFeePolicyTest
```

The test goes Red because `expected: 0` and `actual: -1`; free shipping at the threshold is not implemented yet. You do not need to read the entire stack trace to recognize the exact cause.

**Green — change only what is missing:**

```java
public long feeFor(long subtotalVnd) {
    return 0L;
}
```

Re-run the test: this case passes. Returning a constant is **not the full policy yet**, but it satisfies the single case currently specified. Resist adding extra pricing logic before the next cycle.

### Cycle 2: Below Threshold Charges Standard Fee

**Red — add one test** to the test class:

```java
@Test
void subtotalJustBelowThresholdHasStandardFee() {
    ShippingFeePolicy policy = new ShippingFeePolicy();
    assertEquals(30_000L, policy.feeFor(499_999L));
}
```

The new test fails because the previous Green version always returns `0`. Testing `499_999` is especially valuable for catching `>` vs `>=` boundary mistakes.

**Green — generalize for both cases:**

```java
public long feeFor(long subtotalVnd) {
    return subtotalVnd >= 500_000L ? 0L : 30_000L;
}
```

Run both tests; if green, the threshold condition is now verified from both sides.

### Cycle 3: Negative Input Is Invalid

**Red — add a test**:

```java
@Test
void negativeSubtotalIsRejected() {
    ShippingFeePolicy policy = new ShippingFeePolicy();

    assertThrows(
            IllegalArgumentException.class,
            () -> policy.feeFor(-1L)
    );
}
```

With the current code, the method returns `30_000` instead of throwing; the new test fails because no `IllegalArgumentException` occurs. Add static import `org.junit.jupiter.api.Assertions.assertThrows` to the test class.

**Green — add input validation:**

```java
public long feeFor(long subtotalVnd) {
    if (subtotalVnd < 0L) {
        throw new IllegalArgumentException("subtotalVnd must be >= 0");
    }
    return subtotalVnd >= 500_000L ? 0L : 30_000L;
}
```

Run all tests created so far. Previous cases must stay green, because rejecting negative numbers must not alter valid-input behavior.

### Refactor While Green

Extract domain numbers into constants while preserving API and behavior:

**Final version:** `src/main/java/example/testing/shipping/ShippingFeePolicy.java`

```java
package example.testing.shipping;

public final class ShippingFeePolicy {
    private static final long FREE_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 30_000L;

    public long feeFor(long subtotalVnd) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException(
                    "subtotalVnd must be >= 0");
        }
        return subtotalVnd >= FREE_THRESHOLD_VND
                ? 0L
                : STANDARD_FEE_VND;
    }
}
```

**Complete test suite:** `src/test/java/example/testing/shipping/ShippingFeePolicyTest.java`

```java
package example.testing.shipping;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeePolicyTest {
    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void subtotalAtThresholdHasFreeShipping() {
        assertEquals(0L, policy.feeFor(500_000L));
    }

    @Test
    void subtotalJustBelowThresholdHasStandardFee() {
        assertEquals(30_000L, policy.feeFor(499_999L));
    }

    @Test
    void subtotalAboveThresholdStillHasFreeShipping() {
        assertEquals(0L, policy.feeFor(750_000L));
    }

    @Test
    void negativeSubtotalIsRejected() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> policy.feeFor(-1L));
        assertEquals("subtotalVnd must be >= 0", error.getMessage());
    }
}
```

The final suite has four tests: at threshold, just below threshold, above threshold, and negative input. Run from the directory containing the Gradle wrapper:

```bash
./gradlew test --tests example.testing.shipping.ShippingFeePolicyTest
```

On Windows:

```powershell
.\gradlew.bat test --tests "example.testing.shipping.ShippingFeePolicyTest"
```

**Expected outcome:** all four tests pass in a project with Java and dependencies configured as above. Gradle/JUnit does not have one universal fixed stdout format: how test names, tasks, reports, and summaries render depends on project/runner configuration; check Gradle's test report to verify individual tests.

You can run the **plain Java calculation** via `javac/java` to verify output even without JUnit. Create a file independent of the test suite at `src/main/java/example/testing/shipping/ShippingFeeDemo.java`:

```java
package example.testing.shipping;

public class ShippingFeeDemo {
    public static void main(String[] args) {
        ShippingFeePolicy policy = new ShippingFeePolicy();
        System.out.println(policy.feeFor(499_999L));
        System.out.println(policy.feeFor(500_000L));
    }
}
```

From the project directory:

```bash
javac -d out src/main/java/example/testing/shipping/ShippingFeePolicy.java src/main/java/example/testing/shipping/ShippingFeeDemo.java
java -cp out example.testing.shipping.ShippingFeeDemo
```

Exact stdout:

```text
30000
0
```

A `main` program only demonstrates output and **never replaces JUnit tests** or the Red–Green–Refactor cycle. TDD's primary payoff is that every new requirement becomes a regression-catching test.

### What the Example Proves and Does Not Prove

The example proves the pure fee policy and negative-input handling. It **does not** prove endpoint JSON structure, Spring bean injection, persisting fees to a DB, or transaction rollback. Those contracts require tests at wider boundaries if the application depends on them.

## 4. TDD Entry Points Across Spring Boot Layers

When starting a new feature, place your test at the **narrowest layer that is real enough** to verify the behavior:

| Target Layer | First Red Test Choice | Why It Fits | When to Expand? |
| --- | --- | --- | --- |
| Business rules, calculations, pure parsers | JUnit test on real class, no Spring context | Fast loops, focused errors, clean API design | When invoked via HTTP, persistence, or events |
| Application service / orchestration | Real service with collaborators controlled via stubs/mocks/fakes | Checks decisions and outbound commands without infra dependencies | When wiring, transactions, repositories, or HTTP clients need verification |
| Spring MVC controller | `@WebMvcTest` with `MockMvc` | Checks routing, binding, validation, status, JSON at MVC layer | When real security filters or DB integration are needed |
| Spring WebFlux controller | `@WebFluxTest` with `WebTestClient` | Checks reactive HTTP contract and response codes | When full reactive pipelines, security, network, or broader infra matter |
| Spring Data JPA / repository | `@DataJpaTest` with a test DB | Queries, mappings, constraints must actually execute | When dialect, migrations, or multi-bean transactions matter |
| Spring config, AOP, transactions, method security | Matching Spring context / integration test | Annotations and proxies only take effect when the framework runs | When real HTTP, multiple adapters, or DB/broker matter |
| End-to-end cross-component flow | `@SpringBootTest` and matching test infra | Proves wiring across layers and configuration | When validating full-system / release-environment behavior |

One feature can use **multiple entry points**. For example, the shipping policy has JUnit tests for calculations, MVC tests for status/JSON, persistence tests for stored data, and an integration test for the most critical path. Avoid trying to replace every test level with one end-to-end test; failures become hard to diagnose and TDD loops slow down.

### Domain Logic: Usually the Best Starting Point

When behavior involves many boundaries, decisions, condition combinations, or data transformations, TDD in the domain shapes clean interfaces: meaningful inputs, outputs, and exceptions. Prefer constructor injection when services need collaborators; push clocks, randomness, and I/O behind clear boundaries to keep tests deterministic.

A rule like “discount rate varies by customer tier” should be tested first with plain unit tests. You do not need a Spring container to test an `if` branch or calculation function. Clear domain tests ensure switching transport from MVC to messaging does not break domain test suites.

### Service: Right When Behavior Is Coordination

For example, “if inventory reports out of stock, reject the order and issue no save command.” The SUT is the real service; stub the inventory port's response, observe the exception or return value, and verify no save call was made. Subsequent TDD cycles can add success, out-of-stock, timeout, and idempotency cases.

However, `verify(store).save(order)` only confirms the service **requested** a save; it does not prove transaction commits, SQL constraints, or real DB persistence. If the requirement lives in the DB, move the test to the database boundary.

### HTTP Endpoint: When External Contract Is the Target

For example, “`GET /shipping/fee?subtotalVnd=500000` returns HTTP 200 and JSON with `feeVnd=0`.” With Spring MVC, a Red cycle can start from a `MockMvc` request:

```java
mockMvc.perform(get("/shipping/fee")
        .param("subtotalVnd", "500000"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.feeVnd").value(0));
```

This is an **illustrative snippet inside a test method**, not a standalone class. It requires static imports from `MockMvcRequestBuilders.get` and `MockMvcResultMatchers`, appropriate controller/beans, and a Spring-provided `MockMvc`. With `@WebMvcTest`, supply controller collaborators via test config or mock beans matching your Spring Boot version.

In Red, the test may fail because the route is missing or JSON is wrong; verify the test context and mock collaborators work before diagnosing business behavior. Green implements the endpoint, followed by separate cycles for `400` on invalid query params, auth errors, headers, and validation per contract. Calling `controller.getFee(...)` directly skips Spring HTTP binding.

**Important slice boundary:** `@WebMvcTest` focuses on MVC infrastructure and does not verify databases, messaging, or the full service layer. If Spring Security is on the classpath, MVC tests may traverse security filters; provide authentication or test filter config matching the behavior under test. Never disable security just to turn tests green when access control is a requirement.

### Persistence: Use Database Tests When Requirements Concern Persistence

For “query paid orders sorted by ascending timestamp,” Red is a repository test with seeded data and ordering assertions. A `Map`-based fake repository does not verify SQL queries or Spring Data entity mappings.

`@DataJpaTest` is useful for JPA repositories. Pick a database yielding valid evidence: H2 can suffice for standard queries in some projects, but testing JSONB, SQL dialects, indexes, constraints, or PostgreSQL/MySQL-specific migrations calls for the matching DB engine (e.g., Testcontainers). Slice tests typically run inside a transaction rolled back after the test; if you need to prove commits and transaction interactions, use a broader integration test.

### Framework and Infrastructure: Expand Loops Deliberately

Features relying on Spring proxies such as `@Transactional`, `@Cacheable`, and method security are not exercised when instantiating objects directly via `new`. Here, TDD can start with a small integration test at the relevant boundary; Green updates configuration/annotations/application code, then refactors. Loops are slower due to context startup; avoid putting every simple test into `@SpringBootTest` just for tool uniformity.

## 5. Choosing Entry Points for a Real Feature

Consider the requirement: “Place order successfully if stock is available, fee is right, and user is authorized; do not create order if out of stock.”

**Step 1 — split by observable behavior, not arbitrarily by code class.**

- Shipping fee accurate at thresholds → domain unit TDD.
- Out-of-stock prevents service from requesting order save → service unit TDD.
- Missing request fields map to HTTP 400 → MVC slice TDD.
- Unauthorized user rejected by security chain → security/MVC integration test.
- Order saved properly with transactions/constraints → persistence or integration test.

**Step 2 — pick the fastest feedback loop for the active change.** If editing fee math, run policy tests first. When editing endpoint contracts, run matching MVC tests. When editing transactions, run DB tests. After tight loops, run representative higher-level tests to catch wiring bugs.

**Step 3 — keep one consistent definition of success across boundaries.** Unit tests prove rules, slice tests prove input/output translation, and integration tests prove components work together. Never equate “service tests pass” with “entire REST API works.”

**Step 4 — reuse tests when refactoring.** If you extract `ShippingFeePolicy` from a service, outcomes for the specified cases remain unchanged; re-run tests at both the policy and surrounding boundaries if refactoring altered wiring.

A quick checklist before writing the first test:

| Question | If “Yes” |
| --- | --- |
| Does behavior depend solely on pure inputs and algorithms? | Start with plain JUnit |
| Need controlled collaborator responses without testing the real adapter? | Use real service + test doubles |
| Need to verify `@RequestBody`, `@Valid`, status, JSON, or routing? | Start at web slice |
| Need to verify queries, mappings, or constraints? | Run repository against a test DB |
| Need to verify security filters, proxies, bean wiring, or real transactions? | Use an appropriate Spring context |
| Need to prove flows across services or infrastructure? | Add integration/contract tests, keeping slow loops limited |

## 6. TDD with External Dependencies and Non-Determinism

TDD breaks down if each run depends on live networks, shared databases, system clocks, or test ordering. Separate **application decisions** from **adapter protocol behavior**.

For a payment client:

1. In the service, Red specifies “when payment gateway times out, do not mark order as paid”; intentionally mock/stub the gateway to throw a timeout. Green adds the minimal business handling branch.
2. In the HTTP adapter, Red specifies “HTTP 504 must translate to a gateway timeout error”; use a mock HTTP server or controlled integration test. Green implements accurate HTTP mapping.
3. At integration level, add tests verifying transactions, events, or final state if the system promises them.

Each layer answers its own question. Mocking the exact piece you need to prove (such as mocking `PaymentHttpClient` and claiming client serialization works) produces meaningless green tests.

For time, inject `Clock` and use `Clock.fixed(...)` in unit tests. For async tasks, await observable outcomes via futures, event/test probes, or bounded-timeout utilities; avoid arbitrary `Thread.sleep(...)` durations.

For database integration, isolate data via controlled transactions/cleanup and avoid test-order dependencies. For brokers/caches, consider isolated containers or contract stubs in narrow tests, supplemented by a few broader tests running the real adapter.

## 7. TDD When Modifying Legacy Systems

Not every codebase is structured for easy testing. When changing legacy behavior that has few or no tests, separate two goals:

- **Characterization tests:** record existing behavior to protect what you do not intend to change. Current behavior might be buggy relative to business intent; characterization tests document reality without claiming it is right.
- **New requirement tests:** specify desired behavior *after the change*; these must go Red because old code does not satisfy them yet. Then Green and Refactor.

For instance, a service has a long method that both calculates fees and calls the database. Before altering the formula, add tests observing existing cases to preserve. Once regression protection exists, extract the calculation into a pure class/dependency and start TDD cycles for the new policy. Never refactor transactions, HTTP contracts, and business rules simultaneously without tests separating those concerns.

If the first test can only be written as a slow, heavy `@SpringBootTest`, use a few temporary integration tests as a safety net, then carve out pure logic for fast unit tests. The priority is **not losing proven behavior** while improving testability.

## 8. Choosing the Right Level of TDD and Organizing Feedback

TDD pays off most when requirements have **concrete rules, multiple branches, boundary values, or frequent changes**: pricing, domain authorization, validation, state transitions, idempotency, exception handling, data mapping, and HTTP contracts. When exploring unclear interfaces, trying new frameworks, or running research spikes, a brief prototype helps clarify the API; once behavior is clear, switch to test-first loops for maintainable production code.

Do not treat test counts or coverage percentages as standalone goals. Coverage shows which lines executed, not **whether assertions are meaningful or boundaries are tested**. One test at `500_000` catches `>`/`>=` bugs better than many tests with arbitrary numbers.

Group test runs by feedback speed:

- **Fast local / commit:** plain JUnit, service unit tests, and web slices related to the change.
- **Integration checks:** repository tests, transaction/security tests, API/adapter contract tests.
- **Full pipeline:** multi-component tests, container DB/broker tests, and key regression checks before merge/release.

This split does not force every team into exactly three CI stages. Keep tests with **similar cost and purpose** together so Red–Green–Refactor stays rapid while releases never miss integration risks.

## 9. Common TDD Mistakes in Spring Boot

**1. Tests are green before writing production code.** Often caused by missing assertions, runner failing to discover the test, or mocks returning expected values by default. Run Red and confirm **the exact new test** fails for the right condition, checking test names and counts in the report.

**2. Test is red due to setup errors instead of behavior.** Context fails to boot from a missing bean, test DB fails to connect, or credentials are wrong. Fix test infrastructure before starting Green; otherwise production edits will not affect outcomes.

**3. Using `@SpringBootTest` for every calculation.** Slow loops and config-coupled failures. Use plain JUnit on real classes when Spring is unnecessary; boot a context only when framework behavior is being proved.

**4. Mocking the SUT or the exact capability under test.** `when(policy.feeFor(...)).thenReturn(0L)` does not test the formula; it tests the stub. Instantiate a real `ShippingFeePolicy` and stub out-of-scope collaborators.

**5. Every test calls `verify` on internal calls.** Such assertions fracture whenever code structure changes without altering results. Verify interactions only when the interaction itself is a critical requirement (e.g., “do not write DB on failure” or “do not charge twice”).

**6. Writing too many tests before reaching Green.** Adding a dozen scenarios in one Red makes it hard to tell which change fixed which case. Pick one representative or boundary case, finish the full loop, then expand.

**7. Refactoring while tests are still red.** Mixing business edits and structural changes makes failure causes hard to isolate. Get back to Green first, then refactor incrementally and re-run tests.

**8. Equating unit tests with integration evidence.** Mocking a repository does not test SQL; calling a controller method directly does not test HTTP; `new`-instantiated objects do not prove `@Transactional` works. Place tests at the exact boundary of your claim.

**9. Making tests pass by removing assertions or disabling security filters.** Green tests obtained this way destroy the contract being protected. Fix the implementation or test setup to reflect real requirements; separate environment bugs from business bugs.

**10. Tests depending on hidden state.** Shared DB rows, system clocks, unseeded randoms, or run ordering cause flakiness. Isolate inputs/infrastructure and place test doubles at proper boundaries.

## 10. Checklist for Every Cycle and Entry Point

Before **Red**:

- Described one behavior with concrete inputs, conditions, and observable outcome?
- Chosen the narrowest boundary that genuinely proves the behavior (domain/service/MVC/repository/integration)?
- Know specifically how the test will fail before the feature exists?
- Runner discovers the test, environment is stable, and external dependencies are controlled?

Before **Green**:

- Observed the test failing for the right reason, not a container, discovery, or setup error?
- Implemented only the minimal change to satisfy the behavior; did not mask bugs by loosening assertions?
- Re-ran the new test and related existing tests?

Before **Refactor** and moving to the next cycle:

- Is the suite green?
- Do renames, extracted classes, or deduplication preserve outputs, exceptions, and side effects?
- Is there a new boundary case worthy of the next Red cycle?
- What remains unproven across HTTP, persistence, transactions, or security that warrants a higher-level test?

**Key takeaway:** TDD is the cycle **Red for a reason → minimal Green → Refactor while green**, iterated one behavior at a time. In Spring Boot, pick your starting point from the **contract to prove**: domain for decisions, MVC for HTTP, repository for data, and integration for wiring/framework mechanics. Fast feedback, meaningful assertions, and accurate boundaries matter far more than piling on annotations or inflating test counts.