# JaCoCo: Line Coverage, Branch Coverage, and Assertion Quality

In the **Build and CI** group of the **Spring Boot - testing** module, JaCoCo helps answer **which Java code was executed when tests ran**, rather than directly answering **whether the code's result is correct**. If a test invokes a method and ignores its return value, JaCoCo can still paint the executed lines and branches green. Therefore, the right strategy combines **LINE coverage**, **BRANCH coverage**, and **strong assertions / business condition checks**.

This lesson covers everything thoroughly: how JaCoCo instruments bytecode, counter definitions, short-circuit `&&`/`||` semantics, boundary matrix for a business policy, a **Java 17 + Spring Boot 3.5 + Gradle + JUnit Jupiter** sample project, JaCoCo HTML/XML and a coverage threshold gate in `check`, 12 unit tests with strong assertions, 5 MockMvc tests, a standalone Java SE demo with exact stdout, reading reports/CI integration, mutation testing, exclusion/multi-module pitfalls, and a review checklist.

**Core principle:** 100% line or branch coverage is a **signal of executed paths**, not a bug-free certificate, not MC/DC, and not a substitute for contract/integration/security tests. Coverage thresholds should act as a regression guardrail, never a vanity KPI that pushes authors to execute code without asserting anything.

## 1. Where Does JaCoCo Measure?

```text
Java source (src/main/java)
      |
      v
javac / Gradle compileJava
      |
      v
*.class (bytecode)
      |
      v
Gradle test (JaCoCo agent instruments code)
      |
      +-- JUnit Jupiter tests
      +-- MockMvc tests
      |
      v
build/jacoco/test.exec
      |
      +-- jacocoTestReport
      |      +-- HTML report for reviewers
      |      +-- XML report for CI analyzers
      |
      +-- jacocoTestCoverageVerification
             +-- checks threshold
             +-- PASS or FAIL Gradle task
                    |
                    v
                Gradle check
           [if dependsOn is configured]
```

Three distinct activities:

1. **Test execution:** the agent records instruction/branch probes. Production code must actually run inside the instrumented JVM, not merely compile.
2. **Report:** `jacocoTestReport` combines execution data with class files and source line debug metadata to produce reports.
3. **Verification:** `jacocoTestCoverageVerification` compares counters against thresholds. It fails if any rule is violated; it does not automatically replace reporting or validate assertions.

**Gradle does not automatically wire verification into the `check` lifecycle.** Moreover, Gradle docs explicitly note that `jacocoTestReport` does not automatically depend on the `test` task. The build file in the hands-on section wires `dependsOn` and `finalizedBy` explicitly to avoid a false-green CI `check` that skipped coverage evaluation.

## 2. JaCoCo Counters and Their Meanings

| Counter | What It Measures | What Not to Infer |
| --- | --- | --- |
| `INSTRUCTION` (C0) | Bytecode instructions executed or missed | "Assertions are correct" |
| `LINE` | Source lines mapped to instructions (requires debug line info) | "Both outcomes on the `if` line ran" |
| `BRANCH` (C1) | Bytecode branches of `if`/`switch` | "Every Boolean condition was independently verified" |
| `COMPLEXITY` | Cyclomatic complexity of methods | "N methods are enough to test properly" |
| `METHOD` | Methods with at least one executed instruction | "Entire body/all branches of the method ran" |
| `CLASS` | Classes with at least one executed method | "The class works properly" |

**LINE:** A source line counts as executed if **at least one bytecode instruction** mapped to that line ran. When a source line compiles to multiple instructions, JaCoCo HTML can mark it **partial/yellow** even though the line was touched; green/full means instructions on the line were covered, not that the outcome was right.

**BRANCH:** JaCoCo counts `if` and `switch` decisions at the bytecode level. It does not count `if` keywords in Java source; short-circuit expressions emit multiple jumps and the compiler can emit synthetic instructions. **Exception handling is not counted as `BRANCH`** under C1, so 100% BRANCH coverage does not prove `catch` blocks, rollbacks, or timeout paths ran.

**COMPLEXITY:** Useful for spotting methods with many control paths; it does not choose test inputs or oracles. A low-complexity method can still harbor a business flaw if its condition is wrong.

**Method/Class:** Constructors and static initializers also contribute counters. In Spring Boot, booting the context to instantiate beans can inflate method/line coverage without verifying business logic.

## 3. Reading Covered/Missed Ratios

For any counter with a positive denominator:

```text
coveredRatio = covered / (covered + missed)
percentage   = 100 * covered / (covered + missed)
```

**Hypothetical example** (not observed output from running this project):

| Counter | Covered | Missed | Ratio |
| --- | ---: | ---: | ---: |
| LINE | 18 | 2 | 90% |
| BRANCH | 9 | 3 | 75% |

If policy requires 90% LINE and 80% BRANCH, this sample **passes LINE and fails BRANCH**. When a class has zero bytecode decision branches recognized by JaCoCo, BRANCH displays `n/a` because the denominator is 0; never coerce `n/a` to 0 or 100 by assumption.

Project-wide ratios should never be computed as an unweighted average of per-class percentages across differently sized classes. Sum `covered` and `missed` counters across the target scope; keep `CLASS`/`PACKAGE`/`BUNDLE` scopes clear.

## 4. Why Line Coverage Does Not Prove True and False

```java
String tier(int total) {
    if (total >= 100) {
        return "FREE";
    }
    return "STANDARD";
}
```

This is a snippet, not a runnable class. A test calling only `tier(100)` hits the `if` and `FREE` branch while missing `return "STANDARD"`. You need `tier(99)` as well, with explicit assertions on both. Boundary testing at **100** catches a mutant changing `>= 100` to `> 100`; testing only 1200 misses that bug.

Running every line in a method still does not guarantee both true and false branches passed. Conversely, running both branches without asserting the return value can still yield green JaCoCo counters with zero verification value.

## 5. Short-Circuit Evaluation: Multiple Reasons for One Branch

Consider a rule:

```java
if (subtotal >= 1000 || (vip && subtotal >= 500)) {
    return Tier.FREE;
}
```

Let A=`subtotal>=1000`, B=`vip`, and C=`subtotal>=500`. Java short-circuits: if A is true, B and C are skipped; if A is false and B is false, C is skipped; only when A=false and B=true is C evaluated.

| subtotal | vip | A | B | Is C Actually Evaluated? | Expected |
| --- | --- | --- | --- | --- | --- |
| 1000 | false | true | Skipped | No | FREE |
| 999 | false | false | false | No | Not FREE |
| 500 | true | false | true | Yes, true | FREE |
| 499 | true | false | true | Yes, false | Not FREE |
| 500 | false | false | false | No | Not FREE |

A test achieving `FREE` via `subtotal=1000` **does not** prove the VIP path works. Even getting one true and one false result for the whole expression does not necessarily prove independent effects of A, B, and C. Bytecode `BRANCH` highlights missing paths; **MC/DC** is a stricter condition/decision criterion requiring proof of each condition's independent effect when requirements demand it.

## 6. Simulated Business Policy for the Runnable Project

`ShippingPolicy` defines:

1. Negative subtotal → throw `IllegalArgumentException`.
2. `subtotal >= 1000` **or** `vip && subtotal >= 500` → free shipping, `FREE`.
3. If not FREE, coupon `SAVE10` and `subtotal >= 200` → `DISCOUNTED`.
4. Otherwise → `STANDARD`.

Free shipping takes **higher priority** than the coupon discount. Real monetary values require currency, minor units, and rounding specs; here an `int` subtotal makes boundary errors easy to observe.

```text
subtotal < 0 ?  yes -> IllegalArgumentException
        |
        no
        v
>= 1000 OR (vip AND >= 500) ? yes -> FREE
        |
        no
        v
coupon == "SAVE10" AND >= 200 ? yes -> DISCOUNTED
        |
        no
        v
      STANDARD
```

`>=`, `&&`, `||`, null checks, and rule precedence all require dedicated tests. This is an intentionally simple demo for studying coverage/branch quality, not a real company's shipping policy.

## 7. Project Layout

```text
shipping-coverage/
├── build.gradle
└── src/
    ├── main/java/example/coverage/
    │   ├── CoverageApplication.java
    │   ├── ShippingPolicy.java
    │   ├── PolicyConfiguration.java
    │   ├── ShippingController.java
    │   ├── ApiErrorAdvice.java
    │   └── ShippingPolicyDemo.java
    └── test/java/example/coverage/
        ├── ShippingPolicyTest.java
        └── ShippingControllerTest.java
```

The project uses Java 17, Spring Boot 3.5.x, JUnit Jupiter, MockMvc, and the JaCoCo Gradle plugin. Policy unit tests use **plain Java without opening a Spring context**. MVC tests build a web slice containing the real policy bean. The Java SE demo has no Spring dependency so it can run standalone via `javac`/`java`.

## 8. build.gradle: Real Reporting and Coverage Gate

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'jacoco'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

jacoco {
    toolVersion = '0.8.13'
}

tasks.named('test') {
    useJUnitPlatform()
    finalizedBy tasks.named('jacocoTestReport')
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')

    reports {
        html.required = true
        xml.required = true
        csv.required = false
    }
}

tasks.named('jacocoTestCoverageVerification') {
    dependsOn tasks.named('test')

    violationRules {
        rule {
            element = 'CLASS'
            includes = ['example.coverage.ShippingPolicy']

            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.90
            }

            limit {
                counter = 'BRANCH'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }
    }
}

tasks.named('check') {
    dependsOn tasks.named('jacocoTestCoverageVerification')
}
```

**Explanation of each section:**

- `id 'jacoco'` is Gradle's Java coverage plugin; it attaches the JaCoCo agent to test tasks.
- `toolVersion='0.8.13'` pins a 0.8.x release compatible with Java 17. When upgrading JDK/classfile versions, check the JaCoCo support matrix rather than keeping an outdated agent.
- `test.finalizedBy jacocoTestReport` generates reports after tests even when tests fail (when Gradle runs the finalizer), aiding failure debugging.
- `jacocoTestReport.dependsOn test` ensures invoking the report task directly runs tests first.
- `xml.required=true` feeds CI/Sonar/coverage dashboards; `html.required=true` serves human reviewers.
- `jacocoTestCoverageVerification.dependsOn test` ensures verification reads fresh execution data.
- `check.dependsOn verification` is critical wiring: **verification is not a default dependency of `check`** in the plugin.
- Scoping the gate via `element='CLASS'` + `includes=['example.coverage.ShippingPolicy']` protects the **critical business class**. Real projects should add package/bundle rules and new-code rules; this illustrative rule does not cover the entire application.
- Minimums `0.90 LINE` and `0.80 BRANCH` are examples requiring baseline measurement and risk justification. Never claim a real project hits exact percentages without running it.

**Warning:** `jacocoTestCoverageVerification` does not generate HTML/XML reports, and `jacocoTestReport` does not fail builds on threshold violations. Pair both in CI.

## 9. ShippingPolicy.java: Pure Java Business Class

Create `src/main/java/example/coverage/ShippingPolicy.java`:

```java
package example.coverage;

public final class ShippingPolicy {

    public enum Tier {
        FREE,
        DISCOUNTED,
        STANDARD
    }

    public Tier classify(
            int subtotal,
            boolean vip,
            String coupon) {

        if (subtotal < 0) {
            throw new IllegalArgumentException(
                    "subtotal must not be negative");
        }

        if (subtotal >= 1000
                || (vip && subtotal >= 500)) {
            return Tier.FREE;
        }

        if ("SAVE10".equals(coupon)
                && subtotal >= 200) {
            return Tier.DISCOUNTED;
        }

        return Tier.STANDARD;
    }
}
```

`classify` is a pure function over its inputs (throwing on negative subtotal), needing no Spring, DB, or network. This is the ideal shape for fast boundary and branch testing.

`"SAVE10".equals(coupon)` is **null-safe**: if `coupon == null`, it evaluates to false instead of throwing an NPE. `FREE` is evaluated before coupons. These semantics are contracts to assert explicitly, not merely lines to touch.

## 10. Spring Boot Configuration and Application

Create `src/main/java/example/coverage/PolicyConfiguration.java`:

```java
package example.coverage;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PolicyConfiguration {

    @Bean
    ShippingPolicy shippingPolicy() {
        return new ShippingPolicy();
    }
}
```

Create `src/main/java/example/coverage/CoverageApplication.java`:

```java
package example.coverage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CoverageApplication {
    public static void main(String[] args) {
        SpringApplication.run(CoverageApplication.class, args);
    }
}
```

The business class does not need `@Service`; the configuration exposes it as a bean for the MVC app. Unit tests construct `new ShippingPolicy()` directly, while the MVC test imports `PolicyConfiguration` to wire the real policy rather than mocking it.

## 11. ShippingController.java: HTTP Contract for the Rule

Create `src/main/java/example/coverage/ShippingController.java`:

```java
package example.coverage;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ShippingController {

    private final ShippingPolicy policy;

    public ShippingController(ShippingPolicy policy) {
        this.policy = policy;
    }

    @GetMapping("/shipping/tier")
    public TierResponse tier(
            @RequestParam int subtotal,
            @RequestParam(defaultValue = "false")
            boolean vip,
            @RequestParam(required = false)
            String coupon) {

        ShippingPolicy.Tier result =
                policy.classify(subtotal, vip, coupon);

        return new TierResponse(result.name());
    }

    public record TierResponse(String tier) {
    }
}
```

Create `src/main/java/example/coverage/ApiErrorAdvice.java`:

```java
package example.coverage;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalidSubtotal() {
        return ResponseEntity.badRequest()
                .body(Map.of(
                        "error", "invalid subtotal"));
    }
}
```

Defined HTTP behavior:

- `GET /shipping/tier?subtotal=1000` → 200 + `{"tier":"FREE"}`.
- `GET /shipping/tier?subtotal=500&vip=true` → 200 FREE.
- `GET /shipping/tier?subtotal=200&coupon=SAVE10` → 200 DISCOUNTED.
- `GET /shipping/tier?subtotal=-1` → 400 JSON error.
- Missing required query param `subtotal` → Spring MVC binding returns 400.

This is a demo API with no security, persistence, or money-rounding contracts. MockMvc tests verify mapping, status, and JSON bodies; they do not open TCP sockets or replace unit tests for every condition inside `ShippingPolicy`.

## 12. ShippingPolicyTest.java: 12 Unit Tests with Assertions

Create `src/test/java/example/coverage/ShippingPolicyTest.java`:

```java
package example.coverage;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingPolicyTest {

    private final ShippingPolicy policy =
            new ShippingPolicy();

    @Test
    void rejectsNegativeSubtotal() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> policy.classify(-1, false, null));

        assertEquals(
                "subtotal must not be negative",
                error.getMessage());
    }

    @Test
    void zeroSubtotalIsStandard() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(0, false, null));
    }

    @Test
    void justBelowFreeThresholdIsStandard() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(999, false, null));
    }

    @Test
    void exactlyFreeThresholdIsFree() {
        assertEquals(
                ShippingPolicy.Tier.FREE,
                policy.classify(1000, false, null));
    }

    @Test
    void justBelowVipThresholdIsNotFree() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(499, true, null));
    }

    @Test
    void exactlyVipThresholdIsFree() {
        assertEquals(
                ShippingPolicy.Tier.FREE,
                policy.classify(500, true, null));
    }

    @Test
    void nonVipDoesNotGetVipFreeTier() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(500, false, null));
    }

    @Test
    void couponJustBelowThresholdDoesNotDiscount() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(199, false, "SAVE10"));
    }

    @Test
    void couponAtThresholdDiscounts() {
        assertEquals(
                ShippingPolicy.Tier.DISCOUNTED,
                policy.classify(200, false, "SAVE10"));
    }

    @Test
    void invalidCouponDoesNotDiscount() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(200, false, "WRONG"));
    }

    @Test
    void nullCouponIsSafeAndDoesNotDiscount() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(200, false, null));
    }

    @Test
    void freeTierTakesPriorityOverCoupon() {
        assertEquals(
                ShippingPolicy.Tier.FREE,
                policy.classify(1000, true, "SAVE10"));
    }
}
```

**12 JUnit test methods**, not 12 random calls to bump percentages:

1. Negative input throws `IllegalArgumentException` rather than being swallowed.
2. Subtotal 0 stays on the normal path.
3. Subtotal 999 (just below free threshold) must be `STANDARD`.
4. Subtotal 1000 (exact threshold) must be `FREE`.
5. VIP at subtotal 499 does not get free shipping.
6. VIP at subtotal 500 gets free shipping.
7. Non-VIP at subtotal 500 does not trigger the VIP rule.
8. Valid coupon at subtotal 199 does not discount.
9. Valid coupon at 200 discounts.
10. Invalid coupon at 200 does not discount.
11. Null coupon avoids NPE and does not discount.
12. When both `FREE` and coupon match, `FREE` wins.

**Key takeaway:** Expected values are derived from **business rules**, never read from calling the same implementation. Asserting the exception message also distinguishes expected validation from an unintended NPE.

## 13. ShippingControllerTest.java: 5 MockMvc Methods

Create `src/test/java/example/coverage/ShippingControllerTest.java`:

```java
package example.coverage;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ShippingController.class)
@Import(PolicyConfiguration.class)
class ShippingControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void freeThresholdReturns200() throws Exception {
        mvc.perform(get("/shipping/tier")
                        .param("subtotal", "1000"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tier").value("FREE"));
    }

    @Test
    void vipThresholdReturnsFree() throws Exception {
        mvc.perform(get("/shipping/tier")
                        .param("subtotal", "500")
                        .param("vip", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tier").value("FREE"));
    }

    @Test
    void couponReturnsDiscounted() throws Exception {
        mvc.perform(get("/shipping/tier")
                        .param("subtotal", "200")
                        .param("coupon", "SAVE10"))
                .andExpect(status().isOk())
                .andExpect(
                        jsonPath("$.tier").value("DISCOUNTED"));
    }

    @Test
    void negativeSubtotalReturns400() throws Exception {
        mvc.perform(get("/shipping/tier")
                        .param("subtotal", "-1"))
                .andExpect(status().isBadRequest())
                .andExpect(
                        jsonPath("$.error").value(
                                "invalid subtotal"));
    }

    @Test
    void missingSubtotalFailsBinding() throws Exception {
        mvc.perform(get("/shipping/tier"))
                .andExpect(status().isBadRequest());
    }
}
```

**5 MockMvc JUnit methods.** `@WebMvcTest(ShippingController.class)` creates the MVC slice; `@Import(PolicyConfiguration.class)` supplies the real policy bean. The Spring Boot MVC slice includes MVC components such as `@ControllerAdvice` in the app package, so negative-subtotal error handling is exercised.

MVC tests verify serialization, route/query binding, status codes, and JSON. They do not prove network sockets, app security, DB behavior, or the full Spring Boot context. When a controller test mocks the policy, policy logic coverage does not come from that test; here we wire the real policy to observe end-to-end layer paths clearly.

## 14. Summary of Test Methods and Scope

| Class | Methods | Purpose |
| --- | ---: | --- |
| `ShippingPolicyTest` | 12 | Thresholds, booleans, coupons, null safety, exceptions, precedence |
| `ShippingControllerTest` | 5 | HTTP binding/status/JSON |
| **Total** | **17** | |

**17 methods does not equal 17 branches.** One test method can traverse multiple bytecode branches; a `@ParameterizedTest` can run multiple invocations; constructors and auto-config also add bytecode. Only the JaCoCo report produced after running reveals the true numerators and denominators—never extrapolate coverage percentages from a method-count table.

## 15. ShippingPolicyDemo.java: Runnable Java SE Example

Create `src/main/java/example/coverage/ShippingPolicyDemo.java`:

```java
package example.coverage;

public class ShippingPolicyDemo {
    public static void main(String[] args) {
        ShippingPolicy policy = new ShippingPolicy();

        System.out.println(
                "free=" + policy.classify(
                        1000, false, null));
        System.out.println(
                "vip=" + policy.classify(
                        500, true, null));
        System.out.println(
                "coupon=" + policy.classify(
                        200, false, "SAVE10"));
        System.out.println(
                "normal=" + policy.classify(
                        999, false, null));
    }
}
```

Run with JDK 17+ from the project root without Gradle or Spring:

```bash
javac -d out src/main/java/example/coverage/ShippingPolicy.java src/main/java/example/coverage/ShippingPolicyDemo.java
java -cp out example.coverage.ShippingPolicyDemo
```

**Exact** stdout:

```text
free=FREE
vip=FREE
coupon=DISCOUNTED
normal=STANDARD
```

**Do not confuse this:** this is a plain Java SE demo and does not attach the JaCoCo agent; running `javac`/`java` **does not create `test.exec` or HTML/XML coverage reports**. To measure coverage, run Gradle tests with the JaCoCo plugin.

## 16. Running JaCoCo Tasks with Gradle

Linux/macOS:

```bash
./gradlew clean test jacocoTestReport jacocoTestCoverageVerification
./gradlew clean check
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test jacocoTestReport jacocoTestCoverageVerification
.\gradlew.bat clean check
```

CI invocation:

```bash
./gradlew --no-daemon clean check jacocoTestReport
```

**Expected defaults when tasks succeed in the demo project:**

| Path/Task | Meaning |
| --- | --- |
| `build/jacoco/test.exec` | Binary execution data from JaCoCo test agent |
| `build/reports/jacoco/test/html/index.html` | Human-readable HTML report |
| `build/reports/jacoco/test/jacocoTestReport.xml` | XML report for CI tooling |
| `jacocoTestCoverageVerification` | Fails the build if rules are violated |
| `check` | Lifecycle quality gate, wired via `dependsOn` to verification |
| `test` | JUnit + MockMvc assertions |

**Do not assume fixed Gradle stdout**: console output varies by version, task caching, reporting, and environment. Paths can change if the build sets custom `reportsDirectory` values or uses custom test suites. No Docker, database, or external service is required here.

If `test` fails, `finalizedBy jacocoTestReport` may still run to generate debugging artifacts; **the pipeline must still fail overall**. Generating a report never turns failing tests green.

## 17. How to Read JaCoCo HTML

Open `build/reports/jacoco/test/html/index.html`, select package `example.coverage`, class `ShippingPolicy`, and inspect the source view:

- **Red** lines indicate uncovered paths—e.g., `throw IllegalArgumentException` if negative cases are missing.
- **Yellow** lines indicate partial instruction coverage on the line; on multi-operand `if` conditions, this often flags a missing short-circuit path.
- **Green** lines indicate all instructions on the line executed, **yet do not prove assertions are right**.
- **Red/yellow/green** diamonds next to decisions show branch coverage for `if`/`switch`.

**Workflow from report to test:**

1. Identify which class/package lacks counters and locate high-risk uncovered lines.
2. Read the condition and build a truth table / boundary list.
3. Pick inputs exercising the missing path.
4. Write expected assertions derived from business requirements.
5. Include negative paths and side-effect checks where relevant.
6. Re-run Gradle tests + report and inspect updated counters and test results.
7. Review in code review to verify both higher coverage **and real bug-catching power**.

JaCoCo source highlighting relies on line-number debug info in class files. If classes are compiled without debug line info, instructions/branches may still be recorded while HTML highlighting and `LINE` counters behave unexpectedly.

## 18. XML Reports in CI

An **illustrative** XML snippet (not measured output from executing the project):

```xml
<counter type="LINE" missed="2" covered="18"/>
<counter type="BRANCH" missed="3" covered="9"/>
```

JaCoCo XML includes counters across report/package/class/method scopes. When importing into an analyzer, configure the exact path and ensure reports are generated after test execution. With SonarScanner/SonarQube configured, you can pass:

```properties
sonar.coverage.jacoco.xmlReportPaths=build/reports/jacoco/test/jacocoTestReport.xml
```

**This is an analyzer property**, not read automatically by Spring Boot or the JaCoCo Gradle plugin as app configuration. Multi-module builds must account for relative paths from the module/analyzer working directory, matching class files, and valid execution data.

CI should upload JUnit XML and JaCoCo HTML/XML even when tests/gates fail (using "always upload artifacts"), while **never** swallowing exit codes with `|| true` or enabling `continue-on-error` on required gates.

## 19. Coverage Gates: CLASS, PACKAGE, BUNDLE

A rule with `element='BUNDLE'` checks the whole module known to the report/verification task; it is simple yet lets well-covered legacy code mask a brand-new untested class. A rule with `element='CLASS'` and `includes=['example.coverage.ShippingPolicy']` protects a critical class directly; for larger codebases, combine `PACKAGE`/`CLASS` rules thoughtfully alongside PR diff coverage.

This article's rule:

```groovy
rule {
    element = 'CLASS'
    includes = ['example.coverage.ShippingPolicy']

    limit {
        counter = 'LINE'
        value = 'COVEREDRATIO'
        minimum = 0.90
    }

    limit {
        counter = 'BRANCH'
        value = 'COVEREDRATIO'
        minimum = 0.80
    }
}
```

These thresholds are **examples**, not universal industry mandates. In real projects, measure the baseline first, protect critical paths, add assertion-backed tests, and only then raise thresholds. Never set unenforced gates or overly broad exclusions just to hit pretty numbers.

## 20. Weak Tests vs. Strong Assertions

Anti-pattern:

```java
@Test
void weakTest() {
    ShippingPolicy policy = new ShippingPolicy();
    policy.classify(1000, false, null);
    policy.classify(500, true, null);
    policy.classify(200, false, "SAVE10");
}
```

This is a snippet needing JUnit imports. It executes code without checking any return value. A broken implementation returning `STANDARD` everywhere still passes. JaCoCo does not measure assertion quality.

Strong tests assert concrete outputs:

```java
assertEquals(
        ShippingPolicy.Tier.FREE,
        policy.classify(1000, false, null));
```

Never derive the expected value by calling the same method under test:

```java
ShippingPolicy.Tier expected =
        policy.classify(1000, false, null);
assertEquals(
        expected, policy.classify(1000, false, null));
```

If a bug is consistent, both expected and actual are equally wrong and the test passes. Expected values must come from the business truth table/requirements or an independent oracle, never from the implementation.

`assertDoesNotThrow(...)` checks only the exception contract, **not** whether `FREE`/`DISCOUNTED`/`STANDARD` is right. For threshold rules, assert the exact enum and boundaries; for side effects, verify interactions, errors, and cleanup.

## 21. Mutation Testing: Which Conditions Are Actually Protected?

Mutation testing (e.g., PIT) deliberately alters bytecode/source behavior and re-runs tests to check whether the mutant is "killed" or survives.

| Hypothetical Mutant | Which Test Should Fail? |
| --- | --- |
| `>= 1000` changed to `> 1000` | `exactlyFreeThresholdIsFree()` |
| `>= 500` changed to `> 500` | `exactlyVipThresholdIsFree()` |
| `>= 200` changed to `> 200` | `couponAtThresholdDiscounts()` |
| `vip` condition removed | `nonVipDoesNotGetVipFreeTier()` |
| Coupon check removed | `invalidCouponDoesNotDiscount()` |
| `return FREE` changed to `STANDARD` | The `FREE` assertions |
| `return DISCOUNTED` changed to `STANDARD` | Coupon assertion |
| Negative-subtotal guard removed | `rejectsNegativeSubtotal()` |
| Coupon prioritized over `FREE` | `freeTierTakesPriorityOverCoupon()` |

When a mutant survives, look for missing inputs or weak assertions. Equivalent mutants and tooling limits mean mutation scores are not an absolute guarantee either. **This project does not install PIT**; configure and run it separately when needed rather than claiming mutations were tested here.

The example highlights a crucial point: testing subtotals 900 and 1200 covers both true and false branches, yet a `>= 1000` → `> 1000` mutant still survives unless you test **1000**. Boundary assertions protect requirements far better than chasing branch ratios alone.

## 22. 100% Branch Coverage Can Still Miss Exception Handling

Consider:

```java
try {
    return repository.load(id);
} catch (IOException error) {
    return cachedCopy(id);
}
```

In JaCoCo, `catch` is not counted as a `BRANCH` of `if`/`switch` in the `BRANCH` (C1) counter. Write dedicated tests for:

- `IOException`/HTTP timeouts and 503 mappings.
- Missing object vs. unavailable backend.
- Resource closing in `finally`/`try-with-resources`.
- Transaction rollbacks and side effects.
- Interrupts/cancellation.
- Validation failures and security forbidden/unauthorized paths.
- Stale fallback cache and tenant permission checks.
- Retry idempotency.

A method with 100% `BRANCH` coverage proves none of those contracts. Use unit fault injection, MockMvc assertions, or Testcontainers/protocol integration tests depending on the layer instead of inferring safety from JaCoCo.

## 23. Spring Context Startup Can Create "False Comfort" Coverage

`@SpringBootTest` instantiates many Spring beans, constructors, and config methods. Those instructions show up as covered **even if tests never assert real behavior**. A `@WebMvcTest` builds only the MVC slice; unimported services/repositories may stay uncovered. If a controller test mocks `ShippingPolicy`, it measures zero business branches.

In the demo, `@Import(PolicyConfiguration.class)` wires the real policy bean inside the MVC slice so HTTP tests exercise it, while 12 pure JUnit tests guard every business condition.

| Goal | Appropriate Test Level |
| --- | --- |
| Pure Java rules | JUnit without Spring |
| MVC mapping/binding/error responses | `@WebMvcTest` + MockMvc |
| SQL constraints/queries | `@DataJpaTest`/`@DataJdbcTest` |
| Auto-config conditions | `ApplicationContextRunner` |
| Full Spring bean graph | `@SpringBootTest` |
| External HTTP timeouts/errors | Test HTTP server / WireMock / Testcontainers |

**Coverage should never pressure authors into turning every unit test into a full integration test** just to execute more constructors. Strong tests sit at the right layer, run fast, assert clearly, and catch concrete defects.

## 24. Multi-Module Builds and Multiple Test Suites

Gradle JaCoCo attaches `jacocoTestReport` to the `test` task by default. If a module defines a separate `integrationTest` task, **never assume** the default report automatically merges execution data from it.

- Each JVM `Test` task produces its own execution data file.
- Custom `JacocoReport` tasks can ingest execution data from multiple test tasks; wire `dependsOn` so those tasks actually run beforehand.
- Gradle offers the JaCoCo Report Aggregation plugin for multi-suite / multi-project builds.
- Ensure execution data matches compiled class files; mismatched class versions corrupt or skew reports.
- Out-of-process apps (Docker servers / external Java processes) **are not automatically instrumented by Gradle's test JVM agent**.
- Parallel Gradle forks, test distribution, and build caches need explicit collection planning; avoid stale `.exec` files.
- Do not copy outdated `JacocoMerge` tutorials without checking compatibility with your Gradle version.

**Having an integration test does not mean integration coverage reached the report**; inspect the task graph and report inputs.

## 25. Coverage Exclusions Can Distort Goals

Large projects contain generated code: OpenAPI DTOs, protobufs, and compiler boilerplate. JaCoCo includes built-in filters yet does not automatically recognize every generator. When exclusions are justified, sync `classDirectories`/report scopes across verification and XML consumers, and document why.

Never exclude:

- Services or controllers that feel "hard to test".
- Authorization checks.
- Transaction error handlers.
- Validation branches.
- New code shipped without tests due to time pressure.
- Whole packages just because coverage is low.

Excluding a class from reports while keeping it in verification skews metrics; excluding business code from the gate invalidates the quality gate. Exclusions must reflect reviewed architectural/ownership boundaries, never metric gaming.

## 26. CI Pipeline and Artifacts

```text
checkout + setup JDK17/Gradle
          |
          v
./gradlew --no-daemon clean check jacocoTestReport
          |
          +-- JUnit assertions
          +-- JaCoCo execution data
          +-- Coverage verification (LINE/BRANCH)
          +-- HTML/XML report
          |
          v
success -> review missing branches/new code
failure -> job stays FAILED, collect reports/logs
```

Artifacts should preserve JUnit XML, JaCoCo HTML, JaCoCo XML, and build logs per repository access controls. Upload artifacts on failure with an `always` condition, while **never** masking errors via `./gradlew check || true` or `continue-on-error` on required gates.

CI quality gates must pair with code review. Even when coverage thresholds pass, if auth/pricing/tenant-leak paths lack tests, reviewers must demand tests rather than treating the percentage as an excuse.

## 27. Common Pitfalls

**1. Missing report:** `jacocoTestReport` never ran, `test` never ran, plugin missing, output directory changed, or `.exec` data missing.

**2. `check` never fails:** forgot `check.dependsOn jacocoTestCoverageVerification`, rule `includes` mismatch, or task skipped.

**3. Partial line/branch despite testing true/false:** short-circuit operands lack cases; inspect the report and truth table.

**4. Red `catch` line despite high `BRANCH`:** exception handlers are excluded from `BRANCH`; write failure tests.

**5. Inflated coverage from startup:** `@SpringBootTest` ran constructors without replacing business assertions.

**6. Controller test passes while policy coverage stays 0:** policy was mocked, or the slice did not import the real bean.

**7. XML exists yet Sonar shows 0:** wrong analyzer path/module/scope or missing upload.

**8. Duplicate class names in reports:** aggregated class files across modules/versions overwrite each other.

**9. Agent rejects JDK:** JaCoCo version too old; upgrade compatibly instead of disabling coverage.

**10. Suspiciously high ratio after exclusions:** audit filters to ensure critical code wasn't hidden.

**11. Local differs from CI:** differing JDK/Gradle versions, test filters, skipped tests, forks, cached data, or compiled classes.

**12. Low coverage on an unreachable branch:** check for dead conditions/invariants instead of writing invalid tests to inflate scores.

**13. Report lacks line info:** classes compiled without line-number debug attributes; instructions/branches may still show.

**14. Relying solely on a bundle-level threshold:** risky new services stay untested while well-covered legacy code keeps the bundle passing.

## 28. Final QA Checklist

**Coverage fundamentals:** Distinguish `LINE`, `BRANCH`, `INSTRUCTION`, and `COMPLEXITY`? Understand partial lines? Know `if`/`switch` branches exclude `catch`? Never equate 100% branch coverage with MC/DC or business correctness?

**Business tests:** Tested 999/1000, 499/500 VIP, 500 non-VIP, coupon 199/200, invalid/null coupon, negative subtotal, and `FREE` precedence? Expected values independent of implementation? Every test asserts exact `Tier` or exception?

**Spring MVC:** Controller matches route/params? MVC slice imports the real `ShippingPolicy` bean? HTTP 200/400 and JSON asserted? Never confuse MockMvc with external network tests?

**Gradle/JaCoCo:** `id 'jacoco'`, `useJUnitPlatform`, XML/HTML reports, `jacocoTestReport.dependsOn test`, `jacocoTestCoverageVerification.dependsOn test`, and `check.dependsOn verification` configured? `LINE`/`BRANCH` counters use `COVEREDRATIO`? `includes` target exact classes? Tool version compatible with JDK?

**CI:** Real report paths preserved (JUnit XML, JaCoCo HTML/XML)? Multi-module/integration data aggregated properly when needed? Exclusions documented without hiding critical code? Failing exit codes never swallowed? Boundary tests and mutants reviewed?

**Conclusion:** JaCoCo reveals unexecuted bytecode paths and enforces baseline coverage guardrails in Build/CI. **`LINE`** shows lines with executed code and **`BRANCH`** shows executed bytecode decision outcomes, yet **verification quality** comes from truth tables, boundary cases, assertions, negative paths, and tests capable of catching broken implementations. Use coverage reports to uncover blind spots, never treating a pretty percentage as a correctness guarantee.

## 29. References

- [JaCoCo — Coverage Counters](https://www.jacoco.org/jacoco/trunk/doc/counters.html): `INSTRUCTION`, `LINE`, `BRANCH`, `COMPLEXITY`, and exception limitations.
- [JaCoCo — FAQ](https://www.jacoco.org/jacoco/trunk/doc/faq.html): probes, line-number metadata, class mismatch.
- [Gradle — JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html): report/verification tasks and task dependencies.
- [Gradle — JacocoCoverageVerification](https://docs.gradle.org/current/dsl/org.gradle.testing.jacoco.tasks.JacocoCoverageVerification.html): threshold rules.
- [Gradle — JacocoViolationRule API](https://docs.gradle.org/current/javadoc/org/gradle/testing/jacoco/tasks/rules/JacocoViolationRule.html): scope and `includes`.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): JUnit, MockMvc, `@WebMvcTest`.
- [Spring Boot 3.5 — Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): importing configuration into MVC slices.
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions and test lifecycle.
- [PIT — Mutation Testing](https://pitest.org/): complementary evaluation of test strength.