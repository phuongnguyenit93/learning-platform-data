# Arrange–Act–Assert and Given–When–Then: Describing Behavior When Testing Spring Boot

## Objectives

After this lesson, you will be able to turn a requirement into a testable scenario with concrete inputs and observable outcomes; structure JUnit code using **Arrange–Act–Assert (AAA)**; write **Given–When–Then (GWT)** descriptions so readers understand business behavior; and choose the right thing to verify at the unit test, web slice test, or integration test level.

The two styles complement each other: **GWT states what the system must do in a given situation; AAA structures the test code to prove it.** Neither replaces clarifying requirements, selecting boundary data, or writing proper assertions.

## 1. The Two Models and How They Map

| AAA – Test Code Structure | GWT – Behavioral Language | Question to Answer |
| --- | --- | --- |
| **Arrange** | **Given** | What are the initial state, data, objects, dependencies, and preconditions? |
| **Act** | **When** | What action does the user or system perform? |
| **Assert** | **Then** | What observable outcome and rule must hold? |

**Arrange** builds the exact context of the scenario: the system under test (SUT), input data, test doubles only where genuinely needed, database state, or HTTP request. Set up only what relates to the expected outcome; do not hide critical inputs inside a bloated shared fixture.

**Act** invokes the behavior being tested, usually **a single logical action** (one method call, one HTTP request, one command, or one state transition). If the behavior is inherently a multi-step workflow, multiple operations may appear, but keep the chain of conditions and outcomes clear; never mix unrelated behaviors into one test.

**Assert** checks the outcome promised to the caller: return value, contractual exception, HTTP status/body/headers, persisted state, emitted event, or observable side effect. Assertions must fail when the rule is violated. Verifying mock invocation counts is only helpful when that interaction itself is the contract to protect.

In GWT, **Given** expresses preconditions in domain language; **When** expresses the triggering event; **Then** states the verifiable outcome. You can use **And/But** to add conditions or outcomes while keeping one coherent behavioral intent.

### How Do AAA and GWT Differ?

- AAA is a **code layout pattern** inside a test method. You can use AAA with JUnit 5, Mockito, MockMvc, database tests, or plain Java tests.
- GWT is a **way to describe behavioral examples** so developers, testers, and domain experts can align. GWT can be written in prose, test names, comments, or Gherkin.
- Writing three `Given/When/Then` comments does not automatically make a test BDD. BDD (Behavior-Driven Development) emphasizes shared agreement on examples and acceptance criteria across roles; tools like Cucumber are just one automation option.
- Gherkin (`Feature/Scenario/Given/When/Then`) is a human-readable specification. Executing it automatically through Cucumber requires configuring a runner and step definitions; writing a standalone `.feature` file is not enough.

## 2. From Business Requirement to Verifiable Scenario

Suppose the rule is: **VIP customers receive a 10% discount on a valid subtotal, regular customers receive no discount; the final amount has two decimal places with HALF_UP rounding; negative subtotals are rejected**.

Do not start by guessing method names or repository call counts. Write clear, checkable examples:

~~~gherkin
Feature: Calculate final amount

  Scenario: VIP customer receives a 10% discount
    Given the subtotal before discount is 100.00
    And the customer is a VIP
    When the system calculates the final amount
    Then the final amount is 90.00

  Scenario: Negative subtotal is invalid
    Given the subtotal before discount is -1.00
    When the system calculates the final amount
    Then the request is rejected because the subtotal is invalid
~~~

In the first scenario, **Given** specifies `100.00` and `VIP`, **When** is calculating the amount, and **Then** is `90.00`. The second scenario describes a failure outcome without dictating technical details like exception class names while writing business specifications. When implementing the Java test, you map that rejection rule to the designed exception type.

A set of examples should cover both normal paths and boundary cases: regular customer, subtotal of 0, fractional rounding, and invalid input. Every scenario must specify **concrete inputs and concrete expected outcomes**, rather than writing “the system works correctly.”

## 3. Complete JUnit 5 Example: One Behavior, Two Ways to Read It

In a Spring Boot application using Java 17+ with `spring-boot-starter-test`, place these two files at their exact paths. This is a **unit test of the pricing rule**: it instantiates the service directly without starting a Spring `ApplicationContext` or web server.

**`src/main/java/com/example/testing/DiscountCalculator.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Service;

@Service
public class DiscountCalculator {

    public BigDecimal finalAmount(BigDecimal subtotal, boolean vip) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be non-negative");
        }

        BigDecimal multiplier = vip
                ? new BigDecimal("0.90")
                : BigDecimal.ONE;

        return subtotal.multiply(multiplier)
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

`BigDecimal` keeps monetary math in base-10 decimals, avoiding `double` for money comparisons. Multiplying by `0.90` retains 90% after discount; `setScale(2, HALF_UP)` makes the rounding policy explicit. The `@Service` annotation lets Spring manage the class in the real application without forcing the unit test below to boot a Spring context.

**`src/test/java/com/example/testing/DiscountCalculatorTest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DiscountCalculatorTest {

    @Test
    void givenVip_whenCalculatingFinalAmount_thenAppliesTenPercentDiscount() {
        // Arrange / Given
        DiscountCalculator calculator = new DiscountCalculator();
        BigDecimal subtotal = new BigDecimal("100.00");

        // Act / When
        BigDecimal actual = calculator.finalAmount(subtotal, true);

        // Assert / Then
        assertEquals(new BigDecimal("90.00"), actual);
    }

    @ParameterizedTest
    @CsvSource({
        "100.00, false, 100.00",
        "0.00, true, 0.00",
        "50.00, true, 45.00"
    })
    void givenValidSubtotal_whenCalculating_thenReturnsExpectedAmount(
            String subtotal, boolean vip, String expected) {
        // Arrange / Given
        DiscountCalculator calculator = new DiscountCalculator();

        // Act / When
        BigDecimal actual = calculator.finalAmount(
                new BigDecimal(subtotal), vip);

        // Assert / Then
        assertEquals(new BigDecimal(expected), actual);
    }

    @Test
    void givenFractionalSubtotal_whenCalculating_thenRoundsHalfUp() {
        // Arrange / Given
        DiscountCalculator calculator = new DiscountCalculator();

        // Act / When
        BigDecimal actual = calculator.finalAmount(
                new BigDecimal("10.05"), true);

        // Assert / Then: 10.05 * 0.90 = 9.045 -> 9.05
        assertEquals(new BigDecimal("9.05"), actual);
    }

    @Test
    void givenNegativeSubtotal_whenCalculating_thenRejectsInput() {
        // Arrange / Given
        DiscountCalculator calculator = new DiscountCalculator();
        BigDecimal invalidSubtotal = new BigDecimal("-1.00");

        // Act + Assert / When + Then
        assertThrows(IllegalArgumentException.class,
                () -> calculator.finalAmount(invalidSubtotal, false));
    }
}
~~~

**Analyzing the VIP test:** the `calculator` instance and `100.00` subtotal are Arrange/Given; the `finalAmount(…, true)` call is Act/When; comparing strictly against `90.00` is Assert/Then. Readers grasp the tested rule from the method name, inputs, and assertion without needing to inspect the discount algorithm.

**Analyzing the error test:** `assertThrows` wraps the action expected to throw an exception, so Act and Assert appear in one expression. This is standard practice when **an exception is the expected outcome**, not a violation of AAA. Never use `try/catch` and swallow exceptions: such a test can “pass” even when no exception is thrown.

**Note on BigDecimal:** `assertEquals` uses `equals`, so `90.0` and `90.00` are not equal despite having the same numeric value. Here the service always calls `setScale(2)`, and the expected values have two decimal places, making the comparison exact and consistent. If the contract does not mandate scale, intentionally choose numeric comparison (e.g., `compareTo`) instead of tweaking expected values arbitrarily to make tests “green.”

In a Spring Boot project with test dependencies declared, Gradle Groovy typically includes:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run from the Gradle project directory containing the tests (or target the right subproject in a multi-project build):

~~~bash
./gradlew test
~~~

On Windows PowerShell, use `.\gradlew.bat test`. Passing tests are reported as passed by the runner; **these test methods print no stdout themselves**. Do not assume tests ran just because `@Test` is present: JUnit Platform configuration and test dependencies must be in place. The sample suite has three runs of the parameterized test plus three `@Test` methods, totaling **6 test executions** when running the whole class.

## 4. Choosing the Observation Boundary in Spring Boot

AAA and GWT are not tied to a single annotation. The same business story can be checked at multiple layers; the **Assert/Then** target changes with each layer's contract:

| Test Boundary | Arrange/Given | Act/When | Assert/Then |
| --- | --- | --- | --- |
| **Unit test** of service/domain | Objects, data, genuinely needed mocks | Call method | Return value, exception, state, or meaningful interaction |
| **Web slice test** with `@WebMvcTest`, `MockMvc` | Request, controller setup, test double dependencies | Send simulated HTTP request | HTTP status, JSON, headers, validation/error response |
| **Integration test** with `@SpringBootTest` and real/test infra | Spring context, initial DB records, test config | Run flow across multiple beans/layers | Cross-layer behavior, persisted data, transactions, response, or observable events |

**Illustrative HTTP-layer example** (not a standalone class): suppose the application exposes `GET /api/quotes?subtotal=100.00&vip=true` returning JSON `{"total":"90.00"}`. Inside a test already configured with `MockMvc`, one scenario could look like:

~~~java
@Test
void givenVipQuote_whenRequestingQuote_thenReturnsDiscountedTotal()
        throws Exception {
    // Given: endpoint and dependencies are configured in the test fixture

    // When + Then: perform the request and verify the response
    mockMvc.perform(get("/api/quotes")
            .param("subtotal", "100.00")
            .param("vip", "true"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.total").value("90.00"));
}
~~~

This snippet **assumes** a matching controller, API route, `mockMvc` field, JUnit/MockMvc imports, and dependency setup exist; it demonstrates how to express AAA/GWT at the web layer, **not a standalone runnable program**. `mockMvc.perform(…)` is Act; the `andExpect(…)` calls are Assert. If the service is mocked in a web slice, configure the mock result in Arrange. The test then verifies how the controller maps requests/responses, **not the real discount algorithm**, which already has dedicated unit tests.

Use `@SpringBootTest` only when you need to verify real collaboration among multiple beans, configuration, the database, or transactions. Integration tests need independent data state and proper cleanup; AAA/GWT helps surface those preconditions. Never boot an entire Spring context just to check a pure Java calculation.

## 5. Writing Readable Tests That Actually Catch Defects

**Start with Then.** Before coding, answer: “If this feature breaks, which assertion will flip from pass to fail?” For the VIP rule, `actual = 90.00` must be compared against an independently derived example figure; never compute expected values using the same formula under test, as both could share the same bug.

**Keep one primary behavior per test.** One test may contain multiple assertions serving a single outcome, such as HTTP `201 Created`, `Location`, and response body for a resource creation. However, a test should not verify registration, login, password change, and user deletion together if those are separate contracts. For an indivisible multi-step workflow, name the test to reflect the whole sequence.

**Name tests by condition – action – outcome.** For instance, `givenNegativeSubtotal_whenCalculating_thenRejectsInput` is far more informative than `testCalculate1` or `shouldWork`. You do not have to use those exact three English keywords; what matters is stating the condition, behavior, and expectation. Names tied solely to implementation (`callsRepositoryTwice`) obscure business meaning unless the call count itself is the rule being tested.

**Keep Arrange small and explicit.** Inputs that determine the outcome should be visible right in the test. Use `@BeforeEach` only for genuinely identical setup, and factories/test builders for complex objects, while avoiding hidden helpers that alter scenarios silently. Give variables meaningful names: `invalidSubtotal`, `vipCustomer`, `existingOrder` instead of `x`, `a1`.

**Match assertions to the contract.** A pricing service returns money, so check exact money; a controller exposes HTTP, so check the HTTP contract; a repository persists data, so check saved/queried state; an event publisher emits events, so check the event when that is the promise. `verify(mock).save(…)` does not prove data landed in a real database; conversely, hitting a real database in a mock-based unit test violates the boundary.

**Keep tests independent and deterministic.** Avoid depending on test execution order, system clock, unseeded randomness, live networks, or another test's data. If behavior depends on time, inject a controllable `Clock`; if it depends on external systems, pick fakes/mocks or stable integration infrastructure. For async work, wait on a condition with an explicit timeout instead of a fixed `Thread.sleep` guess.

## 6. Cases That Must Be Designed Explicitly

| Scenario | Given / Arrange | When / Act | Then / Assert |
| --- | --- | --- | --- |
| Main path | VIP, subtotal 100.00 | Calculate amount | 90.00 |
| Alternate branch | Non-VIP, subtotal 100.00 | Calculate amount | 100.00 |
| Zero boundary | VIP, subtotal 0.00 | Calculate amount | 0.00 |
| Rounding policy | VIP, subtotal 10.05 | Calculate amount | 9.05 per HALF_UP |
| Invalid data | Subtotal -1.00 | Calculate amount | `IllegalArgumentException` per service design |

Use `@ParameterizedTest` for **the same rule across multiple datasets**, like the VIP/non-VIP and zero-boundary cases above. Use separate `@Test` methods when behavior or outcome type differs substantially, such as returning a value versus throwing an exception. Never cram all conditions into one long method with `if` branches, as failures become hard to pinpoint.

At a Spring Boot endpoint, a “Then the request is rejected” step might map to HTTP `400 Bad Request` if specified by the API contract, while the unit test verifies the service's `IllegalArgumentException`. **Never assume every service exception automatically becomes HTTP 400**: validation or exception handling must be explicitly designed at the web layer.

## 7. Common Mistakes and Fixes

| Mistake | Why It Hurts | Fix |
| --- | --- | --- |
| AAA has labels/comments but no real assertions | Misses broken behavior | Write Then assertions with observable outcomes |
| Expected value computed with SUT's own algorithm | Shared bug in expected and actual still passes | Use independent, agreed input–output examples |
| Arrange has excessive mocks, fixtures, and state | Masks failure causes, couples to implementation | Prepare only essential preconditions |
| Act triggers multiple unrelated behaviors | Unclear which step failed | One main behavior or one clearly named workflow per test |
| Asserting only `not null` when business needs exact values | Test passes with wrong answers | Assert exact values, state, or contracts |
| Verifying only internal calls when contract is output | Harmless refactoring breaks tests | Prefer output assertions; verify interactions when required |
| Tests depend on ordering, clock, or shared data | Intermittent failures in CI / parallel runs | Isolate fixtures, control dependencies, rollback/cleanup |
| GWT describes code internals instead of behavior | Non-authors cannot understand scenarios | Write Given/When/Then in business domain terms |
| Treating Gherkin as runnable without step definitions | Specs exist without automated verification | Distinguish GWT docs, JUnit tests, and Cucumber runners |

A useful self-check for test value is **mentally introducing a deliberate bug**: change the VIP rate from 10% to 5%, or remove the negative check. The corresponding test must fail. If it stays green, your Then/assertions or test boundary are missing part of the requirement.

## 8. Workflow for Applying This at Work

1. **Pick one concrete rule** from requirements (e.g., 10% discount for VIP); identify the externally observable output.
2. **Write Given–When–Then with concrete values**, then list normal, boundary, and error cases. If any outcome is vague, clarify requirements before automating.
3. **Choose the right test level**: unit for logic; web slice for HTTP mapping; integration for real collaboration and persistence.
4. **Write code following AAA** and name methods by behavior. In Arrange prepare minimal context; in Act trigger the behavior; in Assert verify the independently defined result.
5. **Run the test, watch it fail if possible, and verify reliability**. Ensure tests fail when the rule breaks and pass when code is right; keep data isolated for repeatable CI runs.

### Practice Exercise

Extend the sample requirement with the rule **only VIP customers receive a discount and a `null` subtotal is rejected**. Write one GWT statement for each behavior, then add JUnit tests following AAA. For `subtotal = null`, `finalAmount` in the example must throw `IllegalArgumentException`; for a regular customer with subtotal `100.00`, the result must be `100.00`. Then temporarily alter the VIP multiplier in code to confirm the VIP test catches the discrepancy, and revert your change.

**Key takeaway:** GWT turns rules into clear scenarios; AAA turns scenarios into structured verification. A test's value lies in **contract-accurate Then/Assertions capable of catching defects**, not in having three comment labels.