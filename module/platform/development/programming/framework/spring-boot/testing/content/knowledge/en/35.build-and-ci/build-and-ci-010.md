# Mutation Testing to Evaluate Defect-Detection Strength

## 1. Passing Tests Do Not Guarantee Catching Small Bugs

A Spring Boot service may have 100% line coverage with every JUnit test passing, yet changing `subtotal >= 10_000` to `subtotal > 10_000` causes an order of exactly 10,000 cents to be charged shipping wrongly. If existing tests only try 9,000 and 12,000, zero tests fail. Coverage shows which code **executed**; it never guarantees assertions notice wrong values.

**Mutation testing** deliberately injects small changes (*mutants*) into compiled production code and re-runs tests to check whether the test suite detects them. In the example above, a mutation operator changes `>=` to `>`. If a JUnit test at the exact 10,000 boundary fails, the mutant is **KILLED**. If all tests covering the mutant still pass, it **SURVIVED**. This measures **fault-detection capability**, not just line traversal.

This article belongs to **Build and CI**, focusing on test design, configuring PIT (PITest) for Java/Spring Boot, reading reports, strengthening assertions, and integrating mutation testing into CI practically.

### Learning Objectives

After this lesson, you will be able to:

- Explain original code, mutation operators, mutants, covering tests, and mutant statuses.
- Distinguish `KILLED`, `SURVIVED`, `NO_COVERAGE`, `TIMED_OUT`, `NON_VIABLE`, `RUN_ERROR`, and `MEMORY_ERROR`.
- Distinguish line/branch coverage from mutation coverage and test strength.
- Identify surviving mutants caused by missing boundary cases, weak assertions, or overly broad test doubles.
- Recognize *equivalent mutants* and explain why forcing 100% everywhere is counterproductive.
- Configure the Gradle PIT plugin with JUnit Jupiter, targeting `targetClasses` and `targetTests` accurately.
- Run `./gradlew test` and `./gradlew pitest`, and inspect HTML/XML reports.
- Design unit tests for business rules before expanding to Spring MVC or full contexts.
- Establish a baseline, track trends, and pick a grounded `mutationThreshold`.
- Avoid slow or flaky CI caused by PIT repeatedly rebooting Spring contexts, DBs, or Testcontainers.
- Apply a **Java 17+, Spring Boot 3.5.16, PIT Gradle plugin 1.19.0** example with **17 JUnit Jupiter methods** across three layers.

**Version scope:** the example uses Java 17+, Spring Boot **3.5.16**, Gradle Groovy DSL, JUnit Jupiter, Mockito, and PIT. The sample pins `pitestVersion='1.22.1'` and `junit5PluginVersion='1.2.3'` as a concrete working pair: the JUnit 5 plugin 1.2.3 requires PIT >= 1.19.4, and Gradle PIT plugin 1.19.0 docs show PIT engine 1.22.1. This is **not a claim that these are the absolute latest releases**; check compatibility with Gradle, JUnit Platform, and active plugins before upgrading.

## 2. At What Layer Does Mutation Testing Operate?

PIT mutates **Java bytecode** after compilation rather than editing repository source files like a developer committing bugs. Typically, PIT:

1. Analyzes selected production and test classes.
2. Runs baseline coverage and timing analysis to see which tests reach which code.
3. Applies a mutation operator at a bytecode instruction to generate a mutant.
4. Executes relevant covering tests against the mutated bytecode.
5. Records whether tests failed, still passed, lacked coverage, or hit runtime errors/timeouts.
6. Repeats across other mutants and writes reports.

```text
         Source code + JUnit tests
                    |
                javac/Gradle
                    |
                  .class
                    |
              PIT baseline scan
             coverage + test timing
                    |
         +----------+-----------+
         |          |           |
      Mutant A   Mutant B    Mutant C
        >=→>     return→0   if→inverted
         |          |           |
         v          v           v
       tests      tests       tests
         |          |           |
        FAIL       PASS       NO_COVERAGE
         |          |           |
       KILLED    SURVIVED    NO_COVERAGE
                    |
                    v
             HTML/XML report
                    |
                 Reviewer
          add assertion / test / triage
```

The diagram is conceptual; PIT generates and schedules mutants/tests according to its engine, test plugin, enabled mutators, and actual bytecode. **Do not** assume a fixed mutant count per Java source line; compiler output and mutation filters influence the exact count.

### 2.1. Example of a Tiny Change

Original code:

```java
boolean freeShipping(int subtotalCents) {
    return subtotalCents >= 10_000;
}
```

Mutant:

```java
boolean freeShipping(int subtotalCents) {
    return subtotalCents > 10_000;
}
```

A test calling only `freeShipping(20_000)` and expecting true passes on both original and mutant. A test right on the boundary:

```java
assertThat(freeShipping(10_000)).isTrue();
```

fails on the mutant. These are **standalone illustrative snippets**, not the runnable production files below.

### 2.2. Typical Mutation Operators

PIT offers various bytecode mutators, such as:

| Mutation Kind | Conceptual Change | Risk Highlighted |
|---|---|---|
| Conditional boundary | `>=` → `>` | Off-by-one at threshold |
| Negate conditional | Invert `if` branch | Missing allow/deny case |
| Return value | Return altered/default value | Missing result assertion |
| Math operation | Swap arithmetic operator | Unchecked total calculation |
| Remove void call | Drop void invocation | Unchecked side effects |
| Increments | Alter step increment/decrement | Unchecked loop or counter |

**Exact operator names and sets depend on the PIT version and mutator group.** The Java examples in the table are conceptual; because PIT mutates bytecode, source-line mapping can occasionally look non-obvious. Start with `mutators=['DEFAULTS']` instead of enabling every operator; PIT docs discourage enabling `ALL` indiscriminately due to noise, runtime cost, and equivalent mutants.

## 3. Interpreting Each Mutant Status Accurately

| Status | Meaning | Action |
|---|---|---|
| `KILLED` | At least one test failed on the mutant, detecting the change | Keep the assertion/fixture; nothing to "fix" on the mutant |
| `SURVIVED` | Covered by tests, yet none detected the change | Inspect test inputs, assertions, mocks, or equivalence |
| `NO_COVERAGE` | No test executed that location per PIT's analysis | Add a test reaching the code if in scope |
| `TIMED_OUT` | Test exceeded timeout on the mutant (e.g., infinite loop or slowness) | Check mutant/runtime; do not blindly trust every timeout |
| `NON_VIABLE` | Mutated bytecode failed to load/run validly | Tool/operator artifact; do not count as catching a business bug |
| `RUN_ERROR` | Engine/test runtime errored executing the mutant | Investigate environment, classpath, or flakiness |
| `MEMORY_ERROR` | Resource/memory failure while running the mutant | Check heap, fork settings, tests, and mutation config |

**`SURVIVED` does not mean "definite production bug".** It means the test suite did not distinguish original from mutated code. A survivor might expose a real missing boundary check, be an equivalent mutant over valid inputs, or mutate code outside the tested contract. Reviewers must triage.

**`NO_COVERAGE` differs from `SURVIVED`.** If zero tests reach a branch, first check test reachability and scope ownership. If covering tests ran yet the mutant survived, you usually need a boundary input or stronger assertion.

**`TIMED_OUT` should not inflate scores artificially.** A mutant causing an infinite loop is commonly counted as killed in several reporting modes, yet timing-sensitive tests, CPU starvation, and CI contention can trigger unstable timeouts too.

## 4. High Line Coverage Can Still Have Low Mutation Score

### 4.1. What Question Does Line Coverage Answer?

Line coverage asks: **During the original test run, which bytecode/source lines were executed?**

Example:

```java
Quote q = pricing.quote(9_999, 2, false);
assertThat(q).isNotNull();
```

This test enters the service and boosts line coverage, yet never checks the 500 shipping fee or 10,499 total. If a mutant changes shipping fee to 0 while still returning a `Quote`, the test stays green.

### 4.2. What Question Does Mutation Coverage Answer?

Mutation testing asks: **If a faulty change is introduced in the targeted code, do tests fail?** It adds visibility into **assertion strength and test input quality**.

Illustrative table (**not actual PIT run output**):

| Illustrative Metric | Value |
|---|---:|
| Total eligible mutants in example | 25 |
| Killed | 18 |
| Survived | 2 |
| No coverage | 5 |
| Hypothetical mutation score | 18 / 25 = 72% |
| Hypothetical test strength (covered only) | 18 / (18 + 2) = 90% |

Per PIT docs, `mutationThreshold` gates on killed mutations over total mutations. `testStrengthThreshold` measures the killed ratio among covered mutations (`killed / (killed + survived)`, excluding `NO_COVERAGE`). Exact counting of `TIMED_OUT`, filtered/nonviable mutants, and denominators varies by tool/version/report—verify against real run reports and **never pass off illustrative figures as tool output**.

### 4.3. Never Treat Mutation Score as the Sole Safety Metric

- 95% score on a utility class does not prove JWT authorization, SQL transactions, or security filters work.
- 70% on core financial logic may warrant stricter review than 90% on generated mappers.
- Different mutator sets yield non-comparable scores.
- Changing `targetClasses`/`targetTests` alters the denominator.
- Equivalent mutants cap the realistic maximum score.
- Flaky or time-dependent tests make statuses unreliable.
- Test coverage must still include integration contracts and non-functional checks outside mutation operators.

Mutation score is **one signal of defect-detection strength inside the mutated scope**, not a certificate of bug-free or secure software.

## 5. Equivalent Mutants and Theoretical Limits

An **equivalent mutant** has different bytecode yet identical observable behavior across all valid inputs. The following is a **conceptual snippet**, not built into the demo project:

```java
// Original:
if (count >= 1) {
    return "valid";
}

// Mutant:
if (count > 0) {
    return "valid";
}
```

For integers, both conditions are equivalent. No `int` test input can make original and mutant return different values for that branch. Writing tests solely to kill such mutants adds pure noise.

**How to handle them:**

1. Read the original condition and exact PIT operator applied.
2. Determine the valid domain/range of inputs (nulls, negatives, overflow, invalid inputs).
3. Prove why mutated behavior is equivalent or outside required contracts.
4. Record the rationale in review/issue notes; apply tightly scoped filters if warranted.
5. Never invent fake assertions or distort valid production code just to raise scores.

**Do not dismiss a mutant as equivalent just because it looks hard to kill.** First test boundaries, negative paths, state changes, and verify mocks are not bypassing production code.

## 6. Building a Mutation Testing Policy for Spring Boot

A repo holds controllers, services, repositories, configs, generated code, DTOs, and external adapters. You do not have to mutate everything with every JUnit test on day one.

An operable strategy:

1. Target **business-critical deterministic code** first: pricing, eligibility, authorization rules, domain state transitions, retry calculations, and validation helpers.
2. Run **pure unit tests** as the primary mutant killers for rapid feedback without rebooting Spring contexts per mutant.
3. Mutate service classes with real branching rather than generated DTOs/records/mappers by default.
4. Keep MVC slices, repositories, security, and full-context tests protecting Spring/DB/HTTP contracts separately.
5. Expand mutation scope to more modules gradually once baselines stabilize.
6. Collect HTML reports for developers and XML for CI tracking/trends.
7. Set fail-build thresholds from measured baselines instead of imposing an arbitrary "90%" externally.
8. Triage high-risk survivors before chasing total score maximization.
9. Keep CI viable: run targeted mutations on PR/merge and broader scopes on a schedule.
10. Whenever mutators, `targetClasses`, or plugin versions change, mark a **metric-series break**.

### 6.1. Why Spring Contexts Make PIT Very Slow

PIT runs tests repeatedly against mutated bytecode. A `@SpringBootTest` pulling DataSource, JPA, security, Testcontainers, and HTTP clients incurs heavy startup overhead. Spring TestContext caches contexts within one JVM for matching keys, yet PIT spawns and manages worker JVMs across mutations, giving **no guarantee** that cached contexts from `./gradlew test` carry over into `./gradlew pitest`.

Mutants can also trigger startup failures, alter bean lifecycles, or time out external dependencies. Split deliberately:

- **Unit PIT task** for pure functions / service policies where unit evidence applies.
- **Integration suites** verifying Spring wiring and real boundaries.
- **Broader scheduled mutation runs** per module when ROI makes sense.

Never drop integration tests to inflate PIT scores, and never throw every `@SpringBootTest` into PIT and wonder why CI stalls.

## 7. Complete Example: Shipping Fees for a Spring Boot API

We build a small Spring Boot app with a fee policy:

- `subtotalCents` is order subtotal (smallest currency unit), must be ≥ 0.
- `itemCount` is item count, must be > 0.
- **Premium** customers get free shipping.
- Orders with subtotal **≥ 10,000** also get free shipping.
- Otherwise, **3 or more items** pay **350**.
- Otherwise, fewer than 3 items pay **500**.
- Total payable = subtotal + shipping.
- No database, network, clock, or randomness, making the policy ideal for plain-JUnit mutation testing.

### 7.1. Boundary Cases to Detect

| Case | subtotal | count | premium | shipping | total |
|---|---:|---:|:---:|---:|---:|
| 1 item | 2,000 | 1 | false | 500 | 2,500 |
| 2 items | 2,000 | 2 | false | 500 | 2,500 |
| 3 items | 2,000 | 3 | false | 350 | 2,350 |
| 4 items | 2,000 | 4 | false | 350 | 2,350 |
| Just below free | 9,999 | 2 | false | 500 | 10,499 |
| Exact free threshold | 10,000 | 2 | false | 0 | 10,000 |
| Just above threshold | 10,001 | 2 | false | 0 | 10,001 |
| Tiny premium order | 1 | 1 | true | 0 | 1 |
| Zero subtotal, valid | 0 | 1 | false | 500 | 500 |
| Negative subtotal | -1 | 1 | false | Reject | — |
| Zero count | 1,000 | 0 | false | Reject | — |
| Negative count | 1,000 | -1 | false | Reject | — |

**Important:** this is a **demo** business policy, not real enterprise shipping logic. Production systems must address currencies, rounding, promotions, delivery zones, taxes, max quantities, idempotency, and overflow.

### 7.2. File Layout

```text
mutation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/mutation/
    │   ├── MutationDemoApplication.java
    │   ├── ShippingQuote.java
    │   ├── ShippingQuoteService.java
    │   └── ShippingQuoteController.java
    └── test/java/com/example/mutation/
        ├── ShippingQuoteServiceTest.java
        ├── ShippingQuoteControllerWebMvcTest.java
        └── ShippingQuoteFlowSpringBootTest.java
```

The sample contains **17 JUnit Jupiter methods**: 12 unit tests, 3 MVC slice tests, and 2 full-context smoke tests. PIT is configured to **mutate only `ShippingQuoteService` and run `ShippingQuoteServiceTest`**, measuring business logic without repeatedly booting Spring contexts. MVC and full-context tests still run in Gradle `test`, guarding HTTP mapping and real bean wiring; they are intentionally **excluded** from the targeted PIT run below.

## 8. Gradle and PIT Configuration (Groovy DSL)

**File `settings.gradle`:**

```groovy
rootProject.name = 'mutation-demo'
```

**File `build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'info.solidsoft.pitest' version '1.19.0'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

pitest {
    // Chosen, pinned example versions; not a claim of newest versions.
    pitestVersion = '1.22.1'
    junit5PluginVersion = '1.2.3'

    // Scope the mutation to production policy code only.
    targetClasses = ['com.example.mutation.ShippingQuoteService']
    targetTests = ['com.example.mutation.ShippingQuoteServiceTest']

    mutators = ['DEFAULTS']
    threads = 2
    outputFormats = ['HTML', 'XML']
    timestampedReports = false

    // First run: measure real baseline; do not set an invented gate.
    mutationThreshold = 0
}
```

### 8.1. Why This Configuration?

- `info.solidsoft.pitest` is the third-party Gradle plugin for PIT; 1.19.0 is published on the Gradle Plugin Portal.
- `pitestVersion` pins a specific engine rather than tracking the plugin's default implicitly.
- `junit5PluginVersion` adds `org.pitest:pitest-junit5-plugin` to the **PIT tool classpath**, not just the app's `testImplementation`, and enables the JUnit 5 test plugin.
- `targetClasses` selects production bytecode to mutate; **never mutate test code**.
- `targetTests` picks which test classes can kill mutants; changing scope shifts the mutation score.
- `mutators=['DEFAULTS']` uses a practical default operator set before considering stronger mutators.
- `threads=2` keeps concurrency modest; increase only when CI has CPU/RAM headroom and tests are thread-safe.
- `outputFormats=['HTML','XML']` produces both human-readable and machine-parseable results.
- `timestampedReports=false` keeps report paths predictable for CI uploads.
- `mutationThreshold=0` **does not fail the build on low scores yet**. This is the baseline-discovery step, not a long-term gate policy.

Gradle plugin docs place reports under `build/reports/pitest` by default. When upgrading the plugin, check task names, report paths, Gradle API compatibility, and JUnit Platform versions.

### 8.2. Choosing Versions and Dependencies Responsibly

At writing time, the Gradle PIT plugin was at 1.19.0; the JUnit 5 plugin 1.2.3 requires PIT engine 1.19.4+. PIT engine 1.22.1 satisfies that floor. Newer PIT releases may exist and shift mutator sets or reporting. Never write `latest` in a reproducible CI build.

Spring Boot 3.5.16 is a 2026 release on the 3.5.x line; for long-lived production apps, track support windows for Boot/Gradle/PIT. Re-run tests and PIT and check API compatibility on every major Boot or JUnit upgrade.

### 8.3. Do Not Substitute JaCoCo for PIT

JaCoCo measures line/branch execution; PIT performs mutation analysis. The two tools **complement** rather than replace each other. Run JaCoCo first to spot uncovered paths, then use PIT on covered lines with weak assertions. Never fail PRs on one isolated percentage without understanding denominator and scope.

## 9. Production Code: Application, DTO, and Service

### 9.1. Spring Boot Entrypoint

**File `src/main/java/com/example/mutation/MutationDemoApplication.java`:**

```java
package com.example.mutation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MutationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MutationDemoApplication.class, args);
    }
}
```

### 9.2. Immutable Record DTO

**File `src/main/java/com/example/mutation/ShippingQuote.java`:**

```java
package com.example.mutation;

public record ShippingQuote(
        int subtotalCents,
        int shippingCents,
        int totalCents
) {}
```

This record represents the API response. Because PIT targets only `ShippingQuoteService`, compiler-generated methods on the record are **excluded** from the mutation target. That narrow scope is intentional for the lesson and does not imply DTO serialization is untested; MVC slice tests cover that.

### 9.3. Service Containing Business Branches

**File `src/main/java/com/example/mutation/ShippingQuoteService.java`:**

```java
package com.example.mutation;

import org.springframework.stereotype.Service;

@Service
public class ShippingQuoteService {

    public ShippingQuote quote(
            int subtotalCents, int itemCount, boolean premium) {

        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                    "subtotalCents must be nonnegative");
        }

        if (itemCount <= 0) {
            throw new IllegalArgumentException(
                    "itemCount must be positive");
        }

        int shippingCents;

        if (premium || subtotalCents >= 10_000) {
            shippingCents = 0;
        }
        else if (itemCount >= 3) {
            shippingCents = 350;
        }
        else {
            shippingCents = 500;
        }

        return new ShippingQuote(
                subtotalCents,
                shippingCents,
                Math.addExact(subtotalCents, shippingCents));
    }
}
```

**Why is this a strong mutation testing target?**

- `subtotalCents < 0` should be caught if inverted or shifted at the boundary.
- `itemCount <= 0` requires testing both 0 and negative values.
- `premium || subtotalCents >= 10_000` requires testing both a low-value premium order and the non-premium threshold.
- `itemCount >= 3` requires testing 2, 3, and 4.
- Fees of 350/500 and the total must be asserted by exact values, not just non-null.

`Math.addExact` catches integer overflow if it ever occurs. In this illustrative policy, orders ≥ 10,000 already have 0 shipping, so normal valid inputs do not overflow; **do not claim existing tests verify overflow handling for arbitrary pricing designs**.

### 9.4. Thin HTTP Controller

**File `src/main/java/com/example/mutation/ShippingQuoteController.java`:**

```java
package com.example.mutation;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ShippingQuoteController {

    private final ShippingQuoteService service;

    public ShippingQuoteController(ShippingQuoteService service) {
        this.service = service;
    }

    @GetMapping("/quotes")
    public ShippingQuote quote(
            @RequestParam int subtotalCents,
            @RequestParam int itemCount,
            @RequestParam(defaultValue = "false") boolean premium) {

        return service.quote(subtotalCents, itemCount, premium);
    }
}
```

The controller uses Spring MVC to bind query parameters and serialize `ShippingQuote` to JSON. The app **omits Spring Security** to keep the focus on mutation testing—never treat a 200 GET as proof of authentication/authorization.

For invalid domain inputs like a negative subtotal, the service throws `IllegalArgumentException`; the demo **does not configure a 400 mapping** for that domain exception. If a clear API contract for invalid domain inputs is required, add `@ControllerAdvice`/`@ExceptionHandler` and test it explicitly rather than assuming every `IllegalArgumentException` becomes 400.

## 10. Pure JUnit Unit Tests: 12 Methods to Catch Mutants

**File `src/test/java/com/example/mutation/ShippingQuoteServiceTest.java`:**

```java
package com.example.mutation;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ShippingQuoteServiceTest {

    private final ShippingQuoteService service =
            new ShippingQuoteService();

    @Test
    void rejectsNegativeSubtotal() {
        assertThatThrownBy(() ->
                service.quote(-1, 1, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("subtotalCents");
    }

    @Test
    void rejectsZeroItemCount() {
        assertThatThrownBy(() ->
                service.quote(1_000, 0, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("itemCount");
    }

    @Test
    void rejectsNegativeItemCount() {
        assertThatThrownBy(() ->
                service.quote(1_000, -1, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("itemCount");
    }

    @Test
    void oneRegularItemPaysFullShipping() {
        assertThat(service.quote(2_000, 1, false))
                .isEqualTo(
                        new ShippingQuote(2_000, 500, 2_500));
    }

    @Test
    void twoRegularItemsStillPayFullShipping() {
        assertThat(service.quote(2_000, 2, false))
                .isEqualTo(
                        new ShippingQuote(2_000, 500, 2_500));
    }

    @Test
    void threeRegularItemsGetReducedShipping() {
        assertThat(service.quote(2_000, 3, false))
                .isEqualTo(
                        new ShippingQuote(2_000, 350, 2_350));
    }

    @Test
    void fourRegularItemsKeepReducedShipping() {
        assertThat(service.quote(2_000, 4, false))
                .isEqualTo(
                        new ShippingQuote(2_000, 350, 2_350));
    }

    @Test
    void justBelowFreeShippingThresholdStillPays() {
        assertThat(service.quote(9_999, 2, false))
                .isEqualTo(
                        new ShippingQuote(9_999, 500, 10_499));
    }

    @Test
    void exactlyAtFreeShippingThresholdIsFree() {
        assertThat(service.quote(10_000, 2, false))
                .isEqualTo(
                        new ShippingQuote(10_000, 0, 10_000));
    }

    @Test
    void aboveFreeShippingThresholdRemainsFree() {
        assertThat(service.quote(10_001, 2, false))
                .isEqualTo(
                        new ShippingQuote(10_001, 0, 10_001));
    }

    @Test
    void premiumCustomerGetsFreeShippingEvenForTinyOrder() {
        assertThat(service.quote(1, 1, true))
                .isEqualTo(
                        new ShippingQuote(1, 0, 1));
    }

    @Test
    void zeroSubtotalIsValidButStillPaysShipping() {
        assertThat(service.quote(0, 1, false))
                .isEqualTo(
                        new ShippingQuote(0, 500, 500));
    }
}
```

### 10.1. Why Full Object Equality Helps

The Java record `ShippingQuote` gives value-based equality for free. Comparing against `new ShippingQuote(subtotal, shipping, total)` asserts **all three fields at once**. If a mutant changes shipping from 500 to 0 or miscomputes the total, the test fails.

Not every mutant will be killed. PIT may generate mutants a test didn't target, filter certain operators, or encounter equivalent mutants. **Never claim a specific PIT score without actually running it.**

### 10.2. Four Crucial Boundaries

- Subtotal -1 / 0: detects inversion of `subtotalCents < 0`.
- ItemCount 0 / 1: detects boundary/inversion of `itemCount <= 0`.
- Count 2 / 3 / 4: detects `itemCount >= 3`.
- Subtotal 9,999 / 10,000 / 10,001: detects `subtotalCents >= 10_000`.

If a mutator turns `>=` into `>`, only the exact 10,000 test distinguishes the two implementations. If `premium` is inverted, the tiny-order premium test fails. If adding shipping to total is dropped, all non-free cases fail.

### 10.3. An Anti-Test That Leaves Mutants Alive

**The following only illustrates a weak test and is not in the runnable class:**

```java
@Test
void weakAssertion() {
    ShippingQuote result =
            service.quote(9_999, 2, false);
    assertThat(result).isNotNull();
}
```

The method can return completely wrong fees while the test stays green. Replace with assertions on `shippingCents=500` and `totalCents=10499`; verify the real contract rather than piling up pointless assertions just to "kill" mutants.

## 11. MVC Slice Tests: 3 Methods for the HTTP Contract

**File `src/test/java/com/example/mutation/ShippingQuoteControllerWebMvcTest.java`:**

```java
package com.example.mutation;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(ShippingQuoteController.class)
class ShippingQuoteControllerWebMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ShippingQuoteService service;

    @Test
    void successfulRequestBindsParametersAndSerializesQuote()
            throws Exception {
        when(service.quote(9_999, 2, false))
                .thenReturn(new ShippingQuote(
                        9_999, 500, 10_499));

        mvc.perform(get("/quotes")
                .param("subtotalCents", "9999")
                .param("itemCount", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subtotalCents")
                        .value(9_999))
                .andExpect(jsonPath("$.shippingCents")
                        .value(500))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_499));

        verify(service).quote(9_999, 2, false);
    }

    @Test
    void missingItemCountIsBadRequestBeforeService()
            throws Exception {
        mvc.perform(get("/quotes")
                .param("subtotalCents", "2000"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void invalidIntegerParameterIsRejectedBeforeService()
            throws Exception {
        mvc.perform(get("/quotes")
                .param("subtotalCents", "banana")
                .param("itemCount", "1"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
```

This group checks Spring MVC routing, `@RequestParam` binding, default `premium=false`, JSON serialization, and 400 responses for missing or malformed parameters.

**Because the service is a `@MockitoBean`, these tests do not execute real service business logic.** PIT's `targetTests` intentionally picks only `ShippingQuoteServiceTest`, so MVC tests are not used by PIT to evaluate service mutants. That layering is deliberate, not a scope oversight.

In apps with real Spring Security, web slices may load security config differently from the full context; add dedicated security tests rather than disabling filters just to get 200s.

## 12. Full-Context Seam Tests: 2 Methods for Real Bean Wiring

**File `src/test/java/com/example/mutation/ShippingQuoteFlowSpringBootTest.java`:**

```java
package com.example.mutation;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(classes = MutationDemoApplication.class)
@AutoConfigureMockMvc
class ShippingQuoteFlowSpringBootTest {

    @Autowired
    MockMvc mvc;

    @Test
    void webToRealServiceAppliesShippingPolicy()
            throws Exception {
        mvc.perform(get("/quotes")
                .param("subtotalCents", "9999")
                .param("itemCount", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.shippingCents")
                        .value(500))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_499));
    }

    @Test
    void webToRealServiceHonorsExactFreeThreshold()
            throws Exception {
        mvc.perform(get("/quotes")
                .param("subtotalCents", "10000")
                .param("itemCount", "2")
                .param("premium", "false"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.shippingCents")
                        .value(0))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_000));
    }
}
```

This group uses the **full Spring application context** with the real controller and service. However, `MockMvc` runs in-process; `@SpringBootTest` does not open a real HTTP socket just because MockMvc is used. To verify the embedded servlet container, TLS, sockets, or real HTTP flows, add a `@SpringBootTest(webEnvironment=RANDOM_PORT)` suite with an HTTP client.

**Why exclude seam tests from PIT's `targetTests` in the sample?** They prove Spring wiring well, yet running a full context per mutant can be slow while JUnit unit tests already verify the domain policy. Once unit mutation scores are healthy, you can target specific integration mutants if bugs only surface across Spring proxies or configuration.

## 13. Running the Example in the Right Order

### 13.1. Run the Baseline JUnit Suite First

On Linux/macOS with the Gradle Wrapper present:

```bash
./gradlew clean test
```

On Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

**Design expectation:** **17 JUnit tests** (12 + 3 + 2) pass when JDK/Gradle/dependencies are compatible. This is the **code's expected outcome**, not stdout copied from an actual run. Never claim JUnit passed if `test` reported `UP-TO-DATE`/`FROM-CACHE` without inspecting reports.

### 13.2. Run PIT After Baseline Tests Pass

Linux/macOS:

```bash
./gradlew pitest
```

Windows PowerShell:

```powershell
.\gradlew.bat pitest
```

PIT applies the configured mutation targets and JUnit 5 plugin. If build/plugin/test engine versions conflict, fix that **before** evaluating mutation scores. Messages like `No mutations found` or `No tests found` are not test-quality success; inspect target globs, compiled classes, and plugin classpath.

### 13.3. Reports

With the Gradle PIT plugin, reports typically land at:

```text
build/reports/pitest/
    index.html
    mutations.xml
    ... per-class/package HTML files
```

Actual folder layouts/filenames can vary across PIT versions and report settings; verify actual artifacts rather than linking to unverified paths.

Open the HTML report and inspect `ShippingQuoteService`. Review surviving mutants by operator, method, line, and covering tests. XML suits CI artifact storage, per-job/module aggregation, and baseline comparisons. **Never edit report files directly**; update code/tests and re-run.

### 13.4. Narrow Scope When Debugging

If a weak test only asserts status or non-null, run just that JUnit test and PIT targeted at the service class for rapid feedback. Expand mutation scope only once a baseline exists; never start by mutating the entire codebase against the full Spring integration suite while learning PIT semantics.

## 14. Lab Exercise: Intentionally Weaken a Test, Then Strengthen It

This is a **practice exercise on a copy/demo repo, never on real production code**.

### 14.1. Weak Case

Suppose a test only checks:

```java
ShippingQuote q = service.quote(9_999, 2, false);
assertThat(q).isNotNull();
```

PIT can generate a mutant changing shipping from 500 to 0; the test still passes because `Quote` is non-null. Its status may be `SURVIVED` depending on mutator/coverage.

### 14.2. Adding Contract-Accurate Assertions

```java
ShippingQuote q = service.quote(9_999, 2, false);
assertThat(q.shippingCents()).isEqualTo(500);
assertThat(q.totalCents()).isEqualTo(10_499);
```

If a mutant zeroes shipping or corrupts total, assertions can fail. **Add assertions only for mandatory business behavior**, never just to "pad points" for a specific operator.

### 14.3. Boundary Case

A bug swaps `subtotalCents >= 10_000` for `subtotalCents > 10_000`:

- Test at 9,999: both implementations charge shipping.
- Test at 10,001: both give free shipping.
- **Test at 10,000:** original gives free shipping; mutant charges shipping.

This is the core value of mutation testing: it points directly to **inputs that distinguish two behaviors**.

### 14.4. Side-Effect Case

If a production service executes:

```java
inventory.reserve(orderId);
payment.capture(orderId);
```

a mutator removing void calls creates a mutant that still passes if tests only assert the response DTO. When reserve/capture is part of the contract, verify side effects via an appropriate repository/fake/spy/integration check; for external services, verify real behavior at the right layer instead of relying solely on Mockito `verify` over heavily stubbed unit tests.

This is a standalone snippet; the shipping-fee demo has **no** inventory/payment methods, and the demo PIT target produces no mutations for it.

## 15. Triage Workflow for a SURVIVED Mutant

When PIT flags `SURVIVED`, do not mechanically slap on an assertion to kill it. Follow this sequence:

1. Identify the mutated **production class/method/line**, operator, and mutated behavior.
2. Check which covering tests ran and with what inputs.
3. Write down the difference between original and mutant in clear behavioral terms.
4. Look for a **distinguishing input**: boundary, null/empty, zero, negative, overflow, different role, retry failure, business transition.
5. Check whether assertions verify real outputs/side effects or merely `notNull`/status 200.
6. Check whether mocking bypassed the very production method being mutated.
7. Check whether the mutant is actually **reachable** in the declared input domain.
8. If a real gap exists, add the minimal test aligned with requirements and keep it in the suite.
9. If equivalent, document the proof from specs and consider a narrow filter.
10. If the tool reports `RUN_ERROR`/`TIMED_OUT`, diagnose the environment before drawing conclusions.
11. Re-run baseline JUnit, then PIT, confirming the mutant status changed.
12. Review whether the new test is a meaningful regression guard or mere operator-pleasing noise.

**Never alter valid production logic solely to raise a mutation score.** The goal is verifying whether tests catch real bugs, not writing code tailored to a mutation engine.

### 15.1. A Survivor Is a Signal, Not a Verdict

A mutation in logging, `toString`, generated framework code, an unreachable final branch, or an equivalent condition may need no assertion. By contrast, a survivor in payment amounts, authorization checks, retry stop conditions, or stock decrements is high priority. Triage by **risk × behavior**, not raw survivor counts.

### 15.2. When PIT Reports NO_COVERAGE

Check:

- Is the target class/method production code that ought to be tested?
- Did the JUnit 5 plugin load the tests?
- Did `targetTests` patterns accidentally exclude the relevant test class?
- Did the baseline test run actually reach that code?
- Did an integration context mock a bean so real production code never executed?
- Is the mutated path an edge case missing test inputs?
- Did PIT coverage discovery hit a test engine/classpath error?

If tests genuinely miss a critical branch, add the test. If `NO_COVERAGE` came from misconfigured test selection, fix the scope rather than blaming the JUnit suite.

## 16. Pitest with Spring Boot: Scope and Pitfalls

### 16.1. Spring-Managed Services and Plain Java Unit Tests

A `@Service` can still be instantiated with `new ShippingQuoteService()` when its behavior does not depend on Spring proxies or config injection. That is ideal for **pure Java** mutation targets.

However, if a method relies on `@Transactional`, `@Cacheable`, `@Retryable`, or `@PreAuthorize`, plain unit tests bypass those Spring AOP advices. Keep integration tests invoking the Spring-managed bean or specialized tests to protect those contracts.

### 16.2. MVC Slices May Mock the Very Service Being Mutated

`@WebMvcTest` with `@MockitoBean ShippingQuoteService` tests routing/JSON, yet the real service bean never runs. If PIT mutates the service while only selecting that MVC slice, mutants report `NO_COVERAGE` or go unkilled.

**Never cite an MVC slice with a mocked service as business mutation coverage.** Target plain service tests or full integration tests using the real service.

### 16.3. Transactions, DB, and Testcontainers

The PIT engine runs many mutants; if every mutant boots a database/container or shares external state, speed and isolation collapse. For JPA query/database semantics, pair mutation testing with integration or SQL-specific tests while tightly bounding scope and resources.

Specifically:

- `@Transactional` DB test rollbacks do not reset static, `ThreadLocal`, or Kafka state.
- With `RANDOM_PORT`, test-client and server threads differ; test transactions never roll back server writes.
- Shared Testcontainers lifecycles can fail mutated tests due to stopped containers rather than the mutant.
- Static context caches in one JVM do not automatically carry across PIT's forked JVMs.
- Spring 6.2 enforces a failure threshold; a first startup error can fail later contexts sharing that key quickly.
- Tests relying on fixed ports, wall clocks, or mutable system properties destabilize scores.

### 16.4. @DirtiesContext and Mock Resets

If a suite places `@DirtiesContext` on every method, PIT reloads contexts repeatedly. When `@MockitoBean` resets automatically after each method, there is no need to tear down the entire context just to clear stubs.

Never run Spring tests with shared dirty contexts or mock overrides in parallel without understanding races. Raising PIT `threads` on `@DirtiesContext`/Testcontainers suites often causes infrastructure-driven `KILLED`/`TIMED_OUT` results instead of genuine bug detection.

### 16.5. Kotlin, Lombok, Generated Code, and Records

Compilers emit bytecode developers didn't write directly. PIT mutates bytecode rather than parsing developer intent. When mutants hit generated mappers, records, or `Object` methods, evaluate whether they are meaningful. The sample targets `ShippingQuoteService` specifically so generated DTO methods do not skew the score.

Never filter out an entire critical package just because its score is low. Scopes/filters must be reviewed and documented, or metrics become artificially "pretty" by hiding hard-to-test logic.

## 17. Designing Phased Mutation Gates in CI

### Phase 1 — Baseline, Non-Blocking

- `./gradlew clean test` must pass.
- `./gradlew pitest` runs with locked-in `targetClasses`/`targetTests`.
- Retain HTML/XML reports and version configs.
- Record killed/survived/no-coverage/error counts.
- Inspect critical survivors and add regression tests.
- Never impose an arbitrary 90% gate before understanding equivalent mutants and gaps.
- Verify CI actually executes PIT rather than skipping or soft-failing silently.

### Phase 2 — Grounded Thresholds

Once baselines stabilize and reviewers have triaged major survivors, set a threshold such as:

```groovy
pitest {
    mutationThreshold = 70
}
```

This is purely **an example after measuring a baseline**, not a universal target of 70 for every team. When scores drop below the threshold, PIT fails the task/build per plugin policy. Verify how your plugin version handles rounding, timeouts/errors, and test selection to avoid false failures.

Beyond total scores, teams can enforce:

- Zero unreviewed new `SURVIVED` mutants in payment, authorization, or core financial rules.
- Negative tests required for deny/reject paths.
- Zero `NO_COVERAGE` on modified critical domain branches.
- Explicit notification whenever mutator sets or target scopes change.
- No lowering thresholds or excluding classes merely to force CI green.

### Phase 3 — Cost-Tiered Jobs

Example pipeline:

```text
PR / merge request
      |
      +-- compile + unit + MVC/JPA integration tests
      |
      +-- PIT targeted critical pure/domain classes
      |       -> XML/HTML artifact
      |       -> agreed gate or reviewer action
      |
      +-- security/DB/container contract jobs
              (when relevant to changed code)

Nightly / scheduled
      |
      +-- broader PIT scope by module
      +-- compare trend + investigate survivors
      +-- retain reports for review
```

Whether using GitHub Actions, GitLab CI, Jenkins, or Buildkite, **regular tests must run and pass first**, PIT failures must not be swallowed with unchecked `continue-on-error`, and reports must be saved as artifacts. For incremental/changed-file mutation, verify exact support in your PIT/Gradle extensions or workflows—**never assume the Gradle plugin automatically selects changed PR files**.

### 17.1. Reproducible Infrastructure

Pin plugin/PIT/JUnit versions, use fixed test data, avoid live production APIs, isolate DB/container state, and run on compatible JDK/Gradle versions. On shared CI runners, watch CPU contention and PIT timeouts. Increase `threads` only after measuring.

### 17.2. Platform-Agnostic Pipeline Logic

```bash
./gradlew clean test
./gradlew pitest
# Publish build/reports/pitest as a CI artifact.
```

Never fabricate stdout or job passes in documentation. A build producing a PIT report while failing to load tests or crashing its engine is not a "mutation QA PASS".

## 18. Tracking Trends Without Metric Gaming

Useful metrics:

| Metric | What It Answers | Misinterpretation Risk |
|---|---|---|
| Killed mutants | How many changes tests caught | Ignores severity and business criticality |
| Survived mutants | Uncaught changes | Not every survivor is a production bug |
| No-coverage mutants | Mutated areas unreached by tests | May stem from `targetTests`/engine config |
| Mutation score | Overall ratio within PIT scope/denominator | Changing scope/mutators breaks comparability |
| Test strength | Detection rate within covered code | Ignores uncovered critical paths |
| Runtime duration | CI feedback cost | Does not reflect test effectiveness |
| Error/timeout rate | Stability of PIT execution | Counting spurious timeouts as killed |
| Escaped critical mutants | Unprotected domain risks | Must triage by severity |
| Coverage trend | Code execution reach | High line coverage can still hide weak assertions |

To compare runs fairly, hold project scope, `targetTests`, mutator sets, tool versions, and environment assumptions steady. Whenever one changes, annotate a new baseline. A score jump from 70 to 85 could come from stronger tests **or** from dropping hard-to-mutate classes from targets.

### 18.1. Do Not Game Scores by Disabling Operators Indiscriminately

If PIT flags many survivors in tricky branches, check whether they represent realistic faults first. Disabling operators solely to raise scores hollows out the metric. Exclusions are valid for generated code, logging, or proven equivalent areas when narrowly scoped and documented.

### 18.2. Do Not Force One Mutation Threshold Across Every Module

A deterministic math/pricing module can run fast and hit high scores; a Spring Boot configuration/adapter module full of generated boilerplate may yield noisy mutants or require heavy integration setups. Set scopes/thresholds per module based on domain risk and cost, documented clearly—while never using that flexibility to skip critical authorization or validation checks.

## 19. Troubleshooting PIT and JUnit 5 on Spring Boot

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `pitest` task missing | Gradle PIT plugin not applied | Check `plugins` block and Gradle sync |
| JUnit tests not found | Missing `pitest-junit5-plugin` or wrong `targetTests` | Check `junit5PluginVersion`, runner classpath, test discovery |
| `No mutations found` | `targetClasses` doesn't match production bytecode | Verify FQN packages and compiled classes |
| Widespread `NO_COVERAGE` | Filtered tests, mocked target, or unreachable code | Inspect `targetTests` and JUnit discovery |
| PIT fails while baseline JUnit passes | JUnit Platform / PIT plugin conflict | Pin/align versions, read root stack trace |
| `NoSuchMethodError` in JUnit | Incompatible JUnit Platform/plugin | Align PIT / JUnit 5 plugin / Boot BOM |
| Score 0 despite green tests | Class lacks assertions or wrong tests selected | Inspect generated mutants and test selection |
| Many `SURVIVED` on boundaries | Missing exact threshold input | Test 9,999 / 10,000 / 10,001 |
| Many `SURVIVED` on returns | Only asserting `notNull` or ignoring fields | Assert business outcomes |
| `TIMED_OUT` spikes when raising threads | CPU contention / slow test startup | Lower threads / adjust infra after measuring |
| `RUN_ERROR` | Invalid classpath, environment, or engine | Read root logs; never count as detection |
| `MEMORY_ERROR` | PIT fork/heap/resource pressure | Limit threads, tune JVM heap if needed |
| PIT very slow on `@SpringBootTest` | Repeated full context/DB/Testcontainers boots | Target pure logic first; scope integration deliberately |
| Testcontainers stops mid-run | Lifecycle / test worker / fork mismatch | Ensure stable container ownership/isolation |
| CI task `UP-TO-DATE`, no fresh report | Build caching / stale artifact path | Check task execution and report timestamps |
| XML report fails to parse | Format/version/schema mismatch | Validate actual XML; never regex HTML |
| Fluctuating scores | Timings, flaky tests, dynamic state, tool versions | Fix deterministic fixtures, pin versions |
| Mutation threshold blocks merges prematurely | Un-triaged baseline / equivalent mutants | Run baseline/learning phase first |
| All mutants filtered out | Overly broad exclusions/scope | Review `targetClasses`/`mutators` |
| `@Transactional` service untested | Plain `new Service` skips proxy | Keep Spring-managed integration tests |
| MVC slice passes yet service mutants live | Service replaced by `@MockitoBean` | Select real service tests or unit target |
| Order-dependent tests cause flaky score | Shared mutable state | Independent tests, cleanup, no global mutation |
| Coverage rose yet score stayed flat | New tests touch lines with weak assertions | Mutant-level triage and stronger assertions |

## 20. Practice Exercises with Solutions

### A. 100% Line Coverage Only

A service has 100% line coverage yet a 42% mutation score. Does that prove the service is buggy?

**No.** It shows many mutants in scope went undetected by tests. Inspect top survivors/no-coverage items, examine inputs and expected outputs, and triage equivalent mutants and criticality.

### B. Mutant Changing >= to >

A free-shipping policy checks `subtotal >= 10,000`. Which test distinguishes original from mutant?

**Exactly 10,000.** Both 9,999 and 10,001 can return identical results in both versions.

### C. SURVIVED Yet Line Covered

Should you add another test simply calling that line again?

**Not necessarily.** Inspect inputs and assertions first. A covering test already ran, possibly only asserting `notNull`. Adding a boundary or negative outcome assertion beats repeating the same call.

### D. NO_COVERAGE on Payment Method

Is that a PIT bug or missing tests?

It could be either. Inspect `targetTests` and discovery; if the right tests ran and none exercised the payment path, it is a real gap.

### E. Equivalent Mutant

Original `count >= 1` and mutant `count > 0` for integers. Can any test kill it?

**No, if that is the entire observable semantics.** Document equivalence instead of adding contrived assertions.

### F. @WebMvcTest with Mocked Service

PIT mutates the real service while JUnit runs only `@MockitoBean` service tests. Why aren't mutants killed?

Because the controller calls the mock instead of the real service implementation. Use plain JUnit tests for the policy or full integration tests with the real service.

### G. PIT Takes Minutes on SpringBootTest

Is bumping `threads` from 2 to 16 the default fix?

**No.** When startup/DB/fork/resource contention is the bottleneck, raising concurrency makes things worse. Start by narrowing `targetClasses`/`targetTests` and measuring CPU/RAM/timeouts.

### H. Do 72% and 90% Contradict?

**Not necessarily.** In the example with 18 killed, 2 survived, and 5 no coverage: overall mutation score is 18/25 = 72%, while covered test strength is 18/(18+2) = 90%.

### I. mutationThreshold = 0

Does that mean tests are good enough?

**No.** It only disables build failure while collecting a baseline. Reviewers must still inspect reports and critical mutants.

### J. All Mutants KILLED

Does that prove JWT auth, security filters, PostgreSQL, and TLS work?

**No.** Test those boundaries separately. PIT scores apply only to the mutation target and selected tests.

### K. Raising Score with excludedClasses

When is it acceptable?

When excluded code is genuinely generated, irrelevant, or equivalent per policy with a verifiable rationale. Never exclude pricing/security code just because mutants are hard to kill.

### L. PR Changes Shipping Policy and Tests Fail

Should you update test expectations or fix production code?

Check the **business requirement** first. If the new policy is intended, update tests to match the approved spec; if the change was an accidental regression, fix production code. Mutation testing does not decide which requirement is right.

### M. TIMED_OUT in CI but Not Locally

What could cause it?

CPU contention, JVM heap pressure, PIT thread count, Testcontainers startup, or test flakiness. Investigate the environment and operator rather than counting it as a reliable "kill".

### N. Enable ALL Mutators Immediately?

**No.** Start with `DEFAULTS`, triage survivors, and strengthen inputs/scores. `STRONGER`/`ALL` raise runtime cost and equivalent-mutant noise, so adopt them deliberately.

### O. Run Mutation Testing on Every Push?

Depends on your feedback budget. Targeted critical mutations can run on PRs; broader modules can run on a schedule. What matters is preventing critical regressions from escaping via skipped suites or unexecuted mutation jobs.

## 21. QA Checklist for Deploying Mutation Testing in CI

- [ ] Baseline JUnit suite executes for real and all critical tests pass.
- [ ] PIT engine, Gradle plugin, JUnit 5 plugin, and exact versions are specified.
- [ ] Java 17+ and Spring Boot/Gradle test toolchains are compatible.
- [ ] No `latest` placeholders instead of pinned artifact versions in CI builds.
- [ ] PIT JUnit 5 plugin sits on the PIT tool classpath, not just `testImplementation`.
- [ ] `targetClasses` points to production code only, never mutating tests.
- [ ] `targetTests` selects real covering tests rather than mocking away targets.
- [ ] Scope and mutator sets are documented in reports/baselines.
- [ ] Started with `DEFAULTS`, not enabling `ALL` without justification.
- [ ] Validation boundaries (0/1, `<` / `=` / `>`) are covered where meaningful.
- [ ] Positive and negative cases assert concrete outcomes.
- [ ] Assertions check real state/outputs/side effects rather than just `notNull`.
- [ ] Status 200 alone is not trusted when payloads/authorization matter.
- [ ] Line coverage is never treated as mutation evidence.
- [ ] `KILLED`, `SURVIVED`, `NO_COVERAGE`, `TIMED_OUT`, and `NON_VIABLE` are distinguished.
- [ ] Equivalent mutants have documented rationales rather than blind dismissal.
- [ ] Critical mutants are triaged by severity and risk.
- [ ] `mutationThreshold` is set after baseline measurement, not guessed.
- [ ] Tool version or scope changes establish a fresh comparison baseline.
- [ ] HTML reports exist for developer triage and XML for CI/machine aggregation.
- [ ] CI runs both `test` and `pitest` tasks per policy.
- [ ] CI artifacts contain actual reports rather than claiming pass on skipped tasks.
- [ ] Mutation runs do not touch real production credentials or live APIs.
- [ ] Shared DBs, Testcontainers, clocks, and randomness are controlled.
- [ ] `@SpringBootTest`/`@WebMvcTest`/`@DataJpaTest` still protect their own contracts.
- [ ] Integration tests keep real Spring AOP, security, and DB behaviors where needed.
- [ ] Mutation threads match CPU/RAM and test isolation limits.
- [ ] `@DirtiesContext` is not scattered everywhere to mask mutation flakiness.
- [ ] Exclusions are not abused to pad scores silently.
- [ ] Build reports clearly surface executed/failed/skipped/error statuses.
- [ ] Exact scores are never claimed before actually running PIT.
- [ ] Team defines `SURVIVED`/`NO_COVERAGE` triage workflow and reviewers.
- [ ] CI feedback stays fast enough that developers do not bypass mutation jobs.
- [ ] Critical regression tests remain protected even when overall scores pass thresholds.

## 22. Conclusion

**Mutation testing does not ask "did tests run over the code?"—it asks "do tests react when the code is changed wrongly?"** PIT mutates bytecode, runs JUnit tests, and highlights which faults are caught or missed.

With Spring Boot:

- Use **unit mutation tests** on pure Java business logic for fast feedback.
- Keep **MVC, JPA, security, and full-context integration tests** for Spring/DB/HTTP contracts.
- Read statuses and triage important survivors rather than idolizing a single percentage.
- Test exact boundaries, failure paths, and side effects instead of weak assertions.
- Start with scoped targets + `DEFAULTS` + pinned PIT/JUnit 5 plugin versions.
- Roll PIT into CI via **baseline → triage → agreed threshold → monitoring**, never guessed gates.
- Manage speed and flakiness with deterministic fixtures, clean scopes, and real report checks.

The runnable example uses Java 17+, Spring Boot 3.5.16, Gradle PIT plugin 1.19.0, PIT 1.22.1, JUnit 5 plugin 1.2.3, and **17 JUnit Jupiter methods** (12 unit / 3 MVC slice / 2 full-context). This is a **designed and spec-reviewed codebase**, not evidence that Gradle, JUnit, or PIT were executed during authoring.

## 23. Official References

- [PIT — Basic Concepts](https://pitest.org/quickstart/basic_concepts/): bytecode mutation, running covering tests, `KILLED`/`SURVIVED`/`NO_COVERAGE`, and other statuses.
- [PIT — Mutation Operators](https://pitest.org/quickstart/mutators/): built-in mutators, default/stronger operator groups.
- [PIT — Maven Quick Start and Parameters](https://pitest.org/quickstart/maven/): `targetClasses`/`targetTests`, `mutationThreshold`, `testStrengthThreshold`, report formats, and Maven goal.
- [PIT — FAQ](https://pitest.org/faq/): equivalent mutants, timeout fluctuations, advice on `ALL` operators.
- [Gradle PIT Plugin — Official Documentation](https://gradle-pitest-plugin.solidsoft.info/): Gradle plugin 1.19.0, `junit5PluginVersion`, `pitestVersion`, `targetClasses`, reports, and test-process options.
- [Gradle Plugin Portal — info.solidsoft.pitest](https://plugins.gradle.org/plugin/info.solidsoft.pitest): plugin version availability.
- [PIT JUnit 5 Plugin — Official Repository](https://github.com/pitest/pitest-junit5-plugin): plugin version 1.2.3, minimum PIT engine requirement, and runtime integration notes.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `SpringBootTest`, `MockMvc`, test slices, and context behavior.
- [Spring Boot 3.5.16 release notes](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/): release and support-lifecycle context.
- [JUnit 5 — User Guide](https://docs.junit.org/5.13.0/user-guide/): JUnit Jupiter, assertions, extensions, and test discovery.