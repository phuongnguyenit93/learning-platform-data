# Code Coverage, Assertion Strength, and the Limits of Numbers

In a Spring Boot testing strategy, **code coverage** tells you which code executed when tests ran; **assertions** tell you what the tests verified about observable outcomes; and **test suite confidence** also depends on whether critical scenarios, business rules, and failure modes were actually tested. These three dimensions are related, yet none is directly interchangeable with another.

A project with 90% line coverage can still miscalculate money. A test with 100% branch coverage can still miss a broken HTTP response. Conversely, a small suite targeting exact boundary conditions and critical business contracts can catch defects far more effectively than a large suite executing many lines with weak assertions.

## 1. Three Questions You Must Keep Separate

| Question | Kind of Evidence | Example | What Cannot Be Inferred |
| --- | --- | --- | --- |
| **Which code executed?** | Coverage: line, instruction, branch, method… | JaCoCo records 40/50 executable lines reached | Those 40 lines calculate correctly |
| **Which outcomes were verified?** | Assertions: values, exceptions, state, side effects, HTTP contracts | `assertEquals(0, fee(200_000))` | Every other input combination is right |
| **Do tests catch real-world critical bugs?** | Scenario quality, oracle strength, mutation testing, integration tests, boundary checks | Changing free shipping to 5,000 turns the test red | Every future bug will be caught |

A **test oracle** is the reference determining pass/fail: business requirements, API contracts, invariants, or independently computed results. An assertion is only strong when **its expected value is right** and tied to what needs protection. Writing `assertEquals(actual, actual)` always passes while verifying nothing; copying the production formula into expected values simply duplicates the same bugs.

## 2. What Does Coverage Measure?

Coverage is collected by recording executed code while running one or more tests. For Java/Spring Boot projects using Gradle, **JaCoCo** is the standard tool for measuring executed bytecode and generating reports by class, package, and source line.

| Metric | Practical Meaning | Limitations |
| --- | --- | --- |
| **Instruction coverage** | Percentage of bytecode instructions executed | Easy to inflate via constructors/setup; says nothing about expected results |
| **Line coverage** | Percentage of source lines containing executable instructions touched per bytecode data | A single line with multiple expressions/branches may only be partially covered |
| **Branch coverage** | Percentage of compiler-recognized decision branches executed (such as `if`, `switch`) | Not equivalent to all execution paths, boolean combinations, or data states |
| **Method/class coverage** | Which methods/classes had instructions executed | “Invoked” does not mean behavior is right or outputs were checked |
| **Complexity / missed complexity** | Signals logical decisions lacking test paths | Not a business-quality score |

The general formula for a single metric is:

```text
coverage (%) = covered units / total measurable units × 100
```

For example, if 18 branches are counted and tests hit 15, branch coverage = 15 / 18 × 100% ≈ 83.33%. When citing percentages, state the **metric unit, code scope, and test suite** that produced the data. Never compare 80% branch coverage with 80% line coverage as though they mean the same thing.

**Important JaCoCo detail:** line coverage is derived from bytecode instructions mapped back to source lines; a line can be marked “partially covered.” Branch counters primarily reflect compiler-generated conditional jumps and `switch` statements; **exception handling is not counted as branches by JaCoCo**. Failing calls, `catch` blocks, transaction rollbacks, and environment-specific paths still require deliberate tests.

### Why 100% Line or Branch Coverage Is Still Not Enough

Consider:

```java
if (premiumUser && cartTotal >= 500_000) {
    return 0;
}
return 30_000;
```

Even when reports show branches were executed, you still need combinations like `premiumUser=false`, `cartTotal=500_000`; `premiumUser=true`, `cartTotal=499_999`; and `premiumUser=true`, `cartTotal=500_000`. Because of short-circuiting, these combinations and thresholds can behave differently even when landing on the same final branch. Branch coverage never guarantees you tested every boolean combination, every path across multiple decisions, every boundary value, or external conditions.

Nor does coverage measure **assertion quality**: executing code once does not force a test to check the result of that execution.

## 3. Counterexample: All Branches Executed, Weak Assertions

Assumed business rules for shipping fees:

- Orders with negative values must be rejected with `IllegalArgumentException`.
- Orders of **200,000 or more** qualify for free shipping (`0`).
- Valid orders **under 200,000** have a flat fee of `30,000`.
- Amounts are whole currency units; no taxes, exchange rates, vouchers, or other promotions apply in this example.

Correct implementation:

```java
public int fee(int orderValue) {
    if (orderValue < 0) {
        throw new IllegalArgumentException("orderValue must be non-negative");
    }
    if (orderValue >= 200_000) {
        return 0;
    }
    return 30_000;
}
```

A weak test might exercise all three paths yet only check “fee is non-negative”:

```java
assertTrue(service.fee(199_999) >= 0);
assertTrue(service.fee(200_000) >= 0);
assertThrows(IllegalArgumentException.class, () -> service.fee(-1));
```

For this method, every instruction and both directions of every `if` execute. A JaCoCo report can show **100% line and branch coverage** for the containing class. Yet if a developer accidentally changes the free-shipping branch from `return 0;` to `return 5_000;`, all assertions above **still stay green**: 5,000 is non-negative too.

The test has strong coverage of “executed” but an oracle too weak for “correct.” To block the bug, assert exact results from independent rules:

```java
assertEquals(30_000, service.fee(199_999));
assertEquals(0, service.fee(200_000));
```

Boundary-adjacent pairs also catch changing `>= 200_000` to `> 200_000` — a bug that slips past tests using only 100,000 and 300,000.

## 4. Runnable Example with Java 17+, Spring Boot, JUnit, and JaCoCo

This is a **standalone sample project** using Spring Boot 3.3.x, Gradle Groovy DSL, and Java 17+. Place the files below into a Gradle project with a Java 17-compatible Wrapper. All classes share package `com.example.coverage`; the unit tests instantiate the service directly without starting a Spring context.

Structure:

```text
settings.gradle
build.gradle
src/main/java/com/example/coverage/CoverageApplication.java
src/main/java/com/example/coverage/ShippingFeeService.java
src/test/java/com/example/coverage/ShippingFeeWeakTest.java
src/test/java/com/example/coverage/ShippingFeeStrongTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'coverage-evidence'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'jacoco'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('jacocoTestReport') {
    dependsOn(tasks.named('test'))
    reports {
        html.required = true
        xml.required = true
    }
}
```

The `jacoco` plugin attaches coverage collection to the `test` task. `jacocoTestReport` generates reports from test execution data, and `dependsOn(test)` ensures tests run before reporting. No verification threshold is configured: **coverage percentages are observations**, not business-rule verification.

**`src/main/java/com/example/coverage/CoverageApplication.java`**

```java
package com.example.coverage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CoverageApplication {
    public static void main(String[] args) {
        SpringApplication.run(CoverageApplication.class, args);
    }
}
```

**`src/main/java/com/example/coverage/ShippingFeeService.java`**

```java
package com.example.coverage;

import org.springframework.stereotype.Service;

@Service
public class ShippingFeeService {
    public int fee(int orderValue) {
        if (orderValue < 0) {
            throw new IllegalArgumentException(
                    "orderValue must be non-negative");
        }
        if (orderValue >= 200_000) {
            return 0;
        }
        return 30_000;
    }
}
```

**`src/test/java/com/example/coverage/ShippingFeeWeakTest.java`**

```java
package com.example.coverage;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShippingFeeWeakTest {
    private final ShippingFeeService service = new ShippingFeeService();

    @Test
    void visitsAllOutcomesButChecksLittle() {
        assertTrue(service.fee(199_999) >= 0);
        assertTrue(service.fee(200_000) >= 0);
        assertThrows(IllegalArgumentException.class,
                () -> service.fee(-1));
    }
}
```

**`src/test/java/com/example/coverage/ShippingFeeStrongTest.java`**

```java
package com.example.coverage;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeeStrongTest {
    private final ShippingFeeService service = new ShippingFeeService();

    @Test
    void paysTheFixedFeeBelowTheBoundary() {
        assertEquals(30_000, service.fee(0));
        assertEquals(30_000, service.fee(199_999));
    }

    @Test
    void isFreeAtAndAboveTheBoundary() {
        assertEquals(0, service.fee(200_000));
        assertEquals(0, service.fee(200_001));
    }

    @Test
    void rejectsNegativeOrderValues() {
        assertThrows(IllegalArgumentException.class,
                () -> service.fee(-1));
    }
}
```

Expected values are derived from the contract stated before the code. The strong tests care not just about “throws an exception” or “returns a non-negative integer,” but protect exact values and the `200_000` threshold.

### 4.1. Running Tests and Reading Coverage Reports

From the project directory with Gradle Wrapper:

```bash
./gradlew clean test --tests com.example.coverage.ShippingFeeWeakTest jacocoTestReport
```

On Windows, replace `./gradlew` with `gradlew.bat`. Open the HTML report:

```text
build/reports/jacoco/test/html/index.html
```

Navigate into package `com.example.coverage` and select `ShippingFeeService`. With unmodified code, the weak test hits every path in the service, so the class can show very high coverage—even 100% line and branch coverage. **Do not mistake the project-wide total percentage for the service's percentage:** `CoverageApplication.main` has not run, so project totals differ from the service's numbers.

Next, run the full suite:

```bash
./gradlew clean test jacocoTestReport
```

The sample suite is expected to pass against the original code. The XML report is normally written to:

```text
build/reports/jacoco/test/jacocoTestReport.xml
```

To verify assertion weakness yourself, **in a temporary experiment**, change only `return 0;` in the free branch to `return 5_000;`, then run the weak and strong tests separately:

```bash
./gradlew test --tests com.example.coverage.ShippingFeeWeakTest
./gradlew test --tests com.example.coverage.ShippingFeeStrongTest
```

Logical expectation: the weak test still PASSES because `5_000 >= 0`; the strong test FAILS at `assertEquals(0, service.fee(200_000))`. Revert `return 0;` afterward. This is a **prediction from the sample code**, not a quoted actual run log. To measure directly, run the tests with the corresponding toolchain and dependencies.

## 5. Reading Coverage Reports Properly in Spring Boot Apps

JaCoCo reports show covered vs. missed instructions/lines/branches, typically broken down by package/class/method; green denotes covered, red denotes uncovered, and yellow usually denotes partial coverage. Use the HTML view to spot high-risk gaps such as:

- `if` branches checking access control, eligibility, inventory, pricing, or transaction limits.
- Error returns, retries, timeouts, fallbacks, rollbacks, duplicate handling, and invalid-data paths.
- Boundary conditions `<`, `<=`, `>=`, `>` and multi-state combinations.
- Code paths governing persisted data accuracy or API responses.

**Green lines do not guarantee adequate assertions.** A line executed while Spring constructs beans, invokes constructors, or gets called by an assertion-free test still counts toward coverage. In Spring Boot, `@SpringBootTest` can instantiate many beans and boost startup coverage; you **cannot infer** from that that APIs or transactions were verified.

Coverage also depends on observation scope:

1. **Which test task ran?** Unit tests, a separate `integrationTest` task, profile-specific tests, or excluded tests yield different data. A report for `test` alone will not include a separate `integrationTest` task unless execution data is merged.
2. **Which code is counted?** Excluded classes, generated code, Lombok, adapters, or differing instrumentation configs alter the denominator. Keep measurement rules identical when comparing runs.
3. **Where and under which config did it run?** H2 vs. Testcontainers, mocks vs. real dependencies, `test` vs. `prod` profiles dictate which code paths execute.
4. **Which runtime mechanics were exercised?** Unit tests can cover service logic while completely skipping JSON serialization, the Spring Security filter chain, transactions, SQL, and message brokers.
5. **What if tests fail?** Coverage from executed instructions never substitutes for a PASS status. A build with high coverage and a failing assertion is still a failed correctness build.

Read reports by asking concrete questions: which lines/branches never ran, what defect could hide there, which test scenario triggers them, and once executed, are there assertions checking the expected behavior?

## 6. Assertion Strength: Verifying What the System Must Guarantee

A valuable assertion requires four elements:

1. **Deterministic scenario:** inputs, initial state, conditions, and key dependencies.
2. **Independent expected outcome:** derived from requirements, decision tables, API contracts, or approved invariants.
3. **Appropriate observation:** return value, HTTP status/body, DB changes, emitted events, documented exceptions, or other important side effects.
4. **Ability to separate right from wrong:** if a plausible defect is introduced, the test has a chance to turn red.

Comparing assertion types:

| Assertion | Strength in Pricing Scenario | Issue / What Is Protected |
| --- | --- | --- |
| `assertNotNull(service)` | Low | Only proves a non-null reference; invokes no business logic |
| `assertDoesNotThrow(() -> service.fee(200_000))` | Low | Code could return 5,000 or 30,000 and still pass |
| `assertTrue(service.fee(200_000) >= 0)` | Low | Does not distinguish free shipping from wrong non-zero fees |
| `assertEquals(0, service.fee(200_000))` | Strong for the specific rule | Protects zero fee at the exact boundary |
| `assertThrows(IllegalArgumentException.class, () -> service.fee(-1))` | Strong for required exception type | Does not check message or HTTP 400 mapping if the API specifies them |
| `assertEquals(expectedSavedState, repository.findById(id))` | Strong for persistence if setup is right | Must compare against independent expected state, not just `isPresent()` |

For HTTP APIs, assert what clients depend on: status codes, schema/body, important headers, and side effects. With Spring MVC you can use `MockMvc`; with a real web server you can use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with an HTTP client. `MockMvc` typically tests the MVC layer without starting an actual HTTP server; random-port tests additionally exercise the HTTP transport layer in that test environment.

For repositories and transactions, assert **before/after state** or failure invariants; checking only `verify(repository).save(...)` merely proves a mock interaction, not that real data committed. In asynchronous code, await a condition with a bounded timeout and assert after the condition holds; avoid arbitrary `Thread.sleep` calls or asserting before events finish.

**Caution:** A “strong” assertion with an expected value **violating requirements** turns a bug into a green test. Test reviews must inspect both **inputs and expected values**, not just count assertions.

## 7. Mutation Testing: Measuring How Well Tests Catch Faulty Changes

**Mutation testing** deliberately introduces small changes (mutants) into production code — such as changing `>=` to `>`, replacing `0` with another number, inverting conditions, or swapping operators — and re-runs tests to see whether the tests catch the alteration.

Each mutant is typically classified as:

- **Killed:** relevant tests fail when the mutant is active; this indicates the suite can detect that change.
- **Survived:** tests remain green; check for missing scenarios, weak assertions, or equivalent mutants with identical observable behavior.
- **No coverage:** the mutant sits in code never reached by any test.
- **Timeout / non-viable / other error:** inspect the tool's classification rules; never lump these indiscriminately into “strong tests.”

In Java, look at **PIT (PITest)** to automate mutation testing. On `ShippingFeeService`, a mutant changing `return 0;` to `return 5_000;` survives `ShippingFeeWeakTest` but gets killed by `ShippingFeeStrongTest`. This explains why two test suites with nearly identical coverage can differ drastically in defect detection.

Mutation score is usually reported as the percentage of killed mutants out of the counted mutant set; **read the denominator definition in the tool report carefully** (survived, no-coverage, timed-out, or excluded mutants may be treated differently). Never directly compare mutation scores from two runs with different mutant operators, configurations, filters, or scopes.

Mutation testing costs more CPU time than regular test runs and produces **equivalent mutants**: syntactic changes yielding no observable behavioral difference under the contract. Therefore, the goal is not “100% at all costs.” Prioritize critical domain rules, focus on inspecting actionable survived mutants, and strengthen assertions or scenarios when real gaps emerge.

## 8. When Numbers Hide Risk: Myths to Avoid

| Myth | Reality | What to Do Instead |
| --- | --- | --- |
| “90% coverage means 90% of business logic is right” | Coverage measures executed code, not verified rules | List rules, boundary cases, and failure consequences |
| “100% line coverage means every `if` was tested” | One line can contain multiple branches or compound conditions | Inspect branch reports and write boundary/combination tests |
| “Having assertions means the test is good” | Assertions can be trivial or use wrong expected values | Mentally introduce a plausible bug: does the test turn red? |
| “Green mock tests mean DB/broker works” | Mocks do not represent real protocols, transactions, or infra errors | Add integration tests with real dependencies where needed |
| “Green `@SpringBootTest` means the whole API works” | Context startup does not call or check every endpoint's response | Test endpoints and meaningful HTTP contracts |
| “High mutation score means zero bugs remain” | Tools apply a limited set of syntactic mutations | Combine requirements, boundaries, integration, exploratory testing, and review |
| “Raising the threshold automatically raises quality” | Can incentivize shallow line-touching tests or excluding hard classes | Use thresholds as signals; review specific risks |

Watch out especially for metric gaming: excluding hard-to-test critical classes, writing tests that only construct beans, invoke getters/setters, or assert tautologies. Those inflate numbers without increasing bug-finding power.

## 9. Using Coverage Gates Sensibly in Gradle/CI

If a team wants CI to fail when branch coverage drops below a reference threshold, you can **add** the following example to `build.gradle`:

```groovy
tasks.named('jacocoTestCoverageVerification') {
    dependsOn(tasks.named('test'))
    violationRules {
        rule {
            limit {
                counter = 'BRANCH'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }
    }
}

tasks.named('check') {
    dependsOn(tasks.named('jacocoTestCoverageVerification'))
}
```

Here `0.80` is an **example governance threshold**, not a universal standard. The default rule checks the aggregate report bundle collected by the task, without differentiating risk levels across services. If setting per-package/class limits or merging unit and integration coverage, explicitly configure and verify the task and violation rule scopes.

For new projects or legacy codebases, capture a baseline first, prioritize critical business modules, and prevent accidental coverage drops. Even when CI clears the threshold, PR reviews must still ask: which contract does the new test protect, which boundaries are checked, and would assertions catch typical wrong implementations? Thresholds **never replace** correctness reviews.

A balanced CI flow:

1. Run compilation, unit tests, and critical business assertions; failing tests block changes.
2. Run appropriate integration/API tests with reliable DB/broker/test config when required by architecture.
3. Export coverage reports and locate untested high-risk code paths.
4. Use coverage thresholds as trend signals and to focus reviews on important new or modified code.
5. Run mutation testing selectively, especially on pricing, authorization, transactions, or complex state machines; evaluate survived mutants instead of chasing a raw score.
6. For releases, run smoke tests on the deployed artifact with real configuration; unit test coverage never verifies production operability.

## 10. Self-Check Exercise Before Concluding “Tests Are Good Enough”

Consider these alterations to the shipping fee rule in section 4:

- **Bug A:** `return 0;` changed to `return 5_000;`.
- **Bug B:** `orderValue >= 200_000` changed to `orderValue > 200_000`.
- **Bug C:** `return 30_000;` changed to `return 3_000;`.
- **Bug D:** negative-order check removed.

For each bug, answer: which test must turn red, which assertion triggers, and would the weak test catch it? Based on the sample code: the weak test misses A, B, and C whenever fees remain non-negative; the strong test catches A, B, and C via exact-value `assertEquals` checks. Both may catch D if removing the check eliminates the `IllegalArgumentException` for `-1`. Answers depend on the *actual mutant* and *executed tests*, never solely on prior coverage percentages.

**Checklist before trusting metrics:** Are line/branch coverage definitions and measurement scopes documented? Are there tests for happy paths, boundaries, invalid data, and key side effects? Are expected values derived independently from requirements? Are integration tests in place for behaviors relying on Spring wiring, HTTP, persistence, or security? Do tests turn red when introducing a typical business bug? Has someone reviewed high-risk areas even where the report shows green?

Key takeaway: **coverage helps find unexecuted code; meaningful assertions catch wrong results; scenario selection and oracle quality determine how many critical defects get caught.** Use numbers to guide testing and reviews—never turn numbers into the sole definition of software quality.