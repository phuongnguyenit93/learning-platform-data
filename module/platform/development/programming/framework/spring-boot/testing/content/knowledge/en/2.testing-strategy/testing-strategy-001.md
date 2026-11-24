# Choosing Test Levels by Risk and Scope of Evidence

A system with many tests can still fail severely if those tests only prove things that are easy to check. When choosing a test level, start by asking: **If the feature is wrong, what causes damage and which boundary must we observe to prove it is right?** Only then choose between unit, slice, integration, contract, or end-to-end (E2E).

This lesson applies to Spring Boot applications, though the scoping principles work for most Java applications.

## 1. Two Decision Axes: Risk and Evidence

**Risk** is the likelihood of a defect occurring combined with the consequence if it happens. You can score probability and impact separately on a 1–5 scale for *relative prioritization*, without treating the product of the scores as an exact statistical probability. Impact should consider money, security, data, user experience, compliance, and recoverability.

**Scope of evidence** is the part of the system that must actually run to detect the type of bug you are worried about:

- If you worry about an incorrect discount formula, you need to run the **business rules**.
- If you worry about wrong HTTP status codes, JSON, or validation, you need to run the **web/MVC layer**.
- If you worry about broken queries, JPA mappings, constraints, or transactions, you need to run the **application against a production-compatible database**.
- If you worry about two services interpreting messages differently, you need to verify the **API/event contract** between both sides.
- If you worry about a user journey failing to complete after deployment, you need to run the **path across the relevant components**.

A test is only as strong as what it actually observes. For example, a unit test with a mocked repository does not prove that SQL runs correctly; an HTTP test with a mocked service does not prove that data was committed.

## 2. Common Test Levels in Spring Boot

| Level / Type | Execution and Isolation | What It Proves Well | Common Limitations |
|---|---|---|---|
| **Unit** | A single function/class or small group of objects; no Spring context started, replacing I/O with stubs/fakes/mocks as needed | Logic branches, calculations, state, boundary conditions, error handling | Does not prove bean wiring, serialization, transactions, or a real DB |
| **Web slice** | Only an MVC slice with **@WebMvcTest**, usually using **MockMvc** and mocking underlying services | Routing, request/response, validation, exception mapping, and security filters loaded in the slice | Does not prove real services/repositories or full application configuration |
| **Persistence slice** | **@DataJpaTest** with entities, repositories, and related JPA components; can connect to a real DB via Testcontainers | Mappings, queries, constraints, lazy loading, JPA interactions within the slice | Does not by itself prove the full HTTP flow or cross-layer logic |
| **Integration** | Multiple real beans/components, usually with **@SpringBootTest**, with explicitly configured DB/message broker/HTTP stubs | Wiring, transactions, configuration, cross-layer interaction, migrations, boundary error handling | Slower, environment-dependent, harder to pinpoint root cause if scope is too broad |
| **Contract** | Verifies schemas, requests and responses, consumer/provider compatibility, or events | Both sides share expectations for fields, data types, error codes, and versions | Does not prove the provider is available or that the full product journey succeeds |
| **E2E** | Traverses multiple components like a real user or out-of-process API client, potentially including a browser | Critical end-to-end journeys, deployment configuration, and real connectivity in a test environment | Expensive, slow, prone to noise; one happy path does not cover all logic branches |

**Note:** “Slice” describes *how much of the Spring context is loaded*, whereas “integration” describes *the interaction boundary being verified*. A **@DataJpaTest** running against real PostgreSQL is an integration test at the persistence boundary even though it only loads a slice. Therefore, you cannot place every Spring Boot annotation onto a rigid single ladder.

**Smoke**, regression, security, performance, resilience, and load tests describe the *purpose* of testing, not a fixed level. For instance, a security test can live at the unit level (policy), web slice (401/403), or E2E (system-wide login and authorization).

## 3. A Process for Choosing Test Levels per Change

### Step 1 — Write the Statement to Prove

Avoid vague statements like “the API works.” Write observable conditions and outcomes: “For a cart of exactly 500,000 VND, the shipping fee is 0”; “POST with a payload missing a required field returns 400”; “When payment fails, the order is not marked as paid.”

The **Given – When – Then** form helps identify the input data, action, and expected result to verify. In the Then part, use observable state (return values, DB records, events, HTTP status); do not merely verify that a mock method was called unless that interaction itself is the requirement.

### Step 2 — Identify Which Boundary the Defect Can Live At

Ask yourself: if you remove Spring, SQL, the network, or the browser, can you still catch the defect you are trying to prevent? If yes, start at a narrower scope. If the bug depends on a real boundary, that boundary must be in the test. For example, a unit test cannot prove a DB unique constraint; a mocked HTTP call cannot detect real-world JSON incompatibility.

### Step 3 — Prioritize Using Risk

Score **probability** and **impact** for each scenario, then prioritize by consequence and likelihood. Illustrative example, not a mandatory scoring rubric:

| Failure Scenario | Probability (1–5) | Impact (1–5) | Illustrative Priority | Recommended Evidence |
|---|---:|---:|---:|---|
| Miscalculating shipping fee at threshold | 4 | 3 | 12 | Unit tests with multiple boundary values |
| Duplicate payment recorded on client retry | 3 | 5 | 15 | Integration with real DB, idempotency, and duplicate-request scenarios |
| Renaming a JSON field breaks older clients | 3 | 4 | 12 | Contract + web/API tests |
| Admin page missing authorization check | 2 | 5 | 10 | Security web/integration tests + one authorization journey |
| Secondary button misaligned in layout | 3 | 1 | 3 | Targeted UI/component test, or manual check |

High risk **does not mean** “write lots of E2E tests.” High risk usually requires complementary layers of evidence: many fast cases in unit tests, focused integration cases at dangerous boundaries, and a few representative E2E flows.

### Step 4 — Pick the Smallest Test That Can Catch the Defect

| What You Want to Prove | Starting Preference | When to Escalate Scope |
|---|---|---|
| Formulas, rules, numeric boundaries, business decisions | Unit | When the rule also depends on DB/transactions/real config |
| URL mapping, HTTP status, validation, JSON serialization | Web slice with MockMvc | When you need to prove security wiring or real services and DB |
| Custom queries, entity mappings, data constraints | Persistence slice with a production-compatible DB | When you need to prove transactions and multiple services interacting |
| Transactions, retries, idempotency, outbox, migrations | Integration with real DB/broker or Testcontainers | When you need to verify contracts across multiple processes |
| API or event changes that must stay client-compatible | Two-sided contract | When you need to prove deployment and real connectivity |
| User places an order from start to confirmation | E2E for a few critical journeys | Supplement with unit/integration for error branches and edge cases |

### Step 5 — Choose Execution Cadence and Stability Conditions

Fast unit and slice tests can run on every commit. Integration tests with Testcontainers should run in CI for relevant changes; E2E and load tests run according to risk, environment availability, and acceptable feedback time. When tests fail intermittently, control time, test data, transaction cleanup, threads, and dependencies instead of simply adding retries. Do not enforce a rigid unit/integration/E2E percentage target for every system.

## 4. End-to-End Example: Fee Calculation and Order Creation

Suppose an e-commerce system has the following requirements:

1. Orders from **500,000 VND** qualify for free shipping; below that, the fee is **30,000 VND**. Negative subtotals are invalid.
2. The order creation API rejects payloads missing required fields with HTTP 400.
3. Two duplicate payment requests with the same idempotency key must not be recorded twice.
4. An external shipping service may change its payload; the application must still adhere to the agreed schema.
5. Customers can create an order and view its status after the system is deployed.

From this, we have five different questions, so we need five kinds of evidence. Writing a single E2E test to cover all of them makes reproducing each boundary difficult and may miss a rare branch. Conversely, using only unit tests misses SQL, HTTP, and inter-service compatibility.

### 4.1. Unit Test: Protecting Business Rules at Boundaries

The Java 17 + JUnit Jupiter example below consists of **two complete files**, placed in the same package of a Spring Boot project that has the **spring-boot-starter-test** dependency.

File **src/main/java/com/example/orders/ShippingPolicy.java**:

```java
package com.example.orders;

public final class ShippingPolicy {
    public long feeVnd(long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("subtotalVnd must be >= 0");
        }
        return subtotalVnd >= 500_000 ? 0 : 30_000;
    }
}
```

File **src/test/java/com/example/orders/ShippingPolicyTest.java**:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingPolicyTest {
    private final ShippingPolicy policy = new ShippingPolicy();

    @Test
    void justBelowThresholdPaysFee() {
        assertEquals(30_000, policy.feeVnd(499_999));
    }

    @Test
    void atThresholdIsFree() {
        assertEquals(0, policy.feeVnd(500_000));
    }

    @Test
    void aboveThresholdIsFree() {
        assertEquals(0, policy.feeVnd(500_001));
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.feeVnd(-1));
    }
}
```

Run with the Maven Wrapper at the project root:

```bash
./mvnw -Dtest=ShippingPolicyTest test
```

On Windows, use **mvnw.cmd** instead of **./mvnw**. Expected result: four tests pass, with no required business stdout. This part does not start a Spring context and needs no database; it runs fast and verifies all three sides of the threshold plus invalid input.

**What it does not prove yet:** that the controller invokes the right rule, that JSON returns the right field names, or that data is saved successfully. That is the job of other tests.

### 4.2. Web Slice: Proving the HTTP Interface

For an **OrderController** whose DTO uses Jakarta Bean Validation, use **@WebMvcTest(OrderController.class)** and **MockMvc** to verify:

- Missing required field -> HTTP 400 with the committed error structure.
- Valid body -> correct routing, deserialization, validation, and serialization.
- Insufficient token/user permissions -> 401 or 403 according to the active security configuration.

In a slice, services are usually replaced by mocks; newer Spring Framework versions provide **@MockitoBean**, while older Spring Boot projects use **@MockBean**. Annotation names and imports must match your project's Spring Boot version. If Spring Security is loaded, a POST request may also require a CSRF token and an authenticated principal in the test; omitting them can cause the test to return 401/403 before reaching validation.

A web slice checks that “HTTP behaves according to contract” but **does not prove** that the real repository saved the order. Therefore, do not use MockMvc results with a mocked service to conclude that transactions are safe.

### 4.3. Persistence/Integration: Proving Data Consistency

For writing orders or payments, use **@DataJpaTest** connected to a production-like database (such as PostgreSQL via Testcontainers), or **@SpringBootTest** when multiple real services and transactions are needed. Key scenarios:

- A second request with a duplicate idempotency key does not create an extra payment record.
- Two concurrent requests do not violate unique constraints or leave payment state corrupted.
- An error occurring mid-way rolls back the transaction as required.
- Actual migrations/schemas support the queries, indexes, and constraints; do not use H2 to conclude that every PostgreSQL behavior is identical.

Use Testcontainers when logic depends on dialect, transaction isolation, locking, or database engine errors. Tests must create data explicitly, isolate state, and clean up reliably. For race conditions, intentionally coordinate concurrent execution and assert the final state; sequential tests do not prove concurrency safety.

### 4.4. Contract: Proving Cross-System Compatibility

When a shipping service receives JSON, specify required/optional fields, data types, status codes, errors, and version compatibility. Consumer contract tests confirm that the application produces/consumes the exact interactions real clients use; provider verification must run against the provider or corresponding artifact. Merely mocking a “nice” response in a unit test **does not** prove the current provider still honors the contract.

With Kafka/RabbitMQ, contracts also include keys, schemas, versions, business semantics, and duplicate-message handling. Contract tests check compatibility; integration tests check real broker/serialization behavior and retry logic.

### 4.5. E2E: Proving the Product Journey

Keep E2E tests few and focused on critical journeys: a valid user logs in, creates an order, pays via a safe sandbox, and sees the confirmed status. Add an authorization-denial journey if security impact is high. Only claim what the E2E environment actually runs: if the payment gateway is stubbed, the test does not prove real transactions at the provider.

E2E tests need reproducible data, sensible clocks/timeouts, log/tracing observability, and cleanup; avoid test-order dependencies or fixed sleep waits. When an E2E test fails, smaller unit/integration tests help pinpoint where it broke quickly.

## 5. Designing a Test Suite by “Layers of Evidence”

For the duplicate-payment risk, an in-depth test suite might include:

| Layer of Evidence | Concrete Assertion Example | Prerequisites |
|---|---|---|
| Unit | Same idempotency key returns a decision not to create a new charge per rule | No Spring context needed |
| Web/API | Request missing key is rejected per contract, response has proper error code | Appropriate MVC/security/filters |
| DB integration | Writing twice or concurrently yields only one successful transaction and valid state | Real DB, constraints, and real transactions |
| Contract | Client/provider agree on key, status, and error response | Two-sided contract verification |
| Representative E2E | Retry after timeout does not double-charge the user in a supported sandbox | Appropriate deployment/test environment flow |

This table **does not** mean every change needs all five layers. The selection rule is: every serious defect must have at least one test capable of catching it at the right boundary; add another layer when a risk remains unproven or when regressions must be caught on another surface.

## 6. Planning CI Execution

- **During coding / pull requests:** run unit tests and relevant slices for fast feedback; keep tests short, independent, and deterministic.
- **Before merging or in CI:** run integration tests with real DB/broker for modules affecting schemas, transactions, retries, security, and contracts; run contract tests whenever inter-service communication exists.
- **Before or right after deployment:** smoke test core endpoints and journeys in the deployed environment to catch configuration, migration, routing, and dependency failures.
- **On a schedule or for high-risk changes:** run broad E2E, load, security, and resilience tests for their specific goals; failures must have an owner to investigate.

This strategy can adapt to pipeline speed and criticality. For example, a payments application may require integration tests on every pull request; a pure computation library may rely mainly on unit tests. Do not assume a single test pyramid ratio is the universal quality standard.

## 7. Common Test-Level Selection Mistakes

1. **Equating “many tests” with “sufficient evidence.”** Hundreds of unit tests cannot replace one test verifying a transaction or authorization rule.
2. **Mocking at the exact boundary being tested.** If you worry about broken SQL, mocking the repository hides the bug; if you worry about HTTP contracts, mocking HTTP provides no evidence.
3. **Using @SpringBootTest for every simple rule.** A large context slows the suite and complicates diagnosis; use unit tests for pure logic and expand scope only with reason.
4. **Assuming a slice always matches production.** Beans, filters, properties, or the DB may be excluded from a test slice; inspect the actual configuration to know what the test runs.
5. **Using an embedded DB different from production for SQL-dependent features.** H2 can differ from PostgreSQL in syntax, isolation, constraints, and data types; pick the matching DB when that is a source of risk.
6. **Putting too many detailed branches into E2E tests.** This makes them flaky and slow; put rule edge cases in unit tests, database conflicts in integration tests, and reserve E2E for journeys.
7. **Relying solely on code coverage.** Coverage measures executed code, not assertion strength or boundary accuracy; also consider failure modes, mutation testing (when appropriate), and assertion value.
8. **Ignoring timeouts, retries, time zones, and concurrency.** Those bugs often require fake clocks, clear contracts, containers, or controlled concurrency integration tests.
9. **Unclear test responsibility.** When a test fails and nobody knows which feature broke, the name, data, and assertions are not specific enough.

## 8. Pre-Test Checklist for Choosing Test Levels

- [ ] Written a **Given – When – Then** statement of the behavior that must hold, with an observable expected result.
- [ ] Identified the consequence of failure and the boundary where the defect occurs (logic, HTTP, DB, service, deployment).
- [ ] Chosen the smallest scope that can **genuinely detect** this defect.
- [ ] For high-risk boundaries, identified where real dependencies, Testcontainers, contracts, or supplemental E2E are required.
- [ ] Checked that mocks/stubs do not hide the behavior being proven.
- [ ] Verified which beans/filters/configs/DB the test uses and which parts remain unexecuted.
- [ ] Inputs, time, data, dependencies, and cleanup are deterministic enough for reliable repeats.
- [ ] Placed the test at the right CI cadence with clear ownership when it fails.

**Rule of thumb:** choose tests by **the claim to prove and where defects can arise**, then use **risk to decide depth, case count, and execution timing**. A strong test suite can explain precisely what each test protects and what remains unproven.
