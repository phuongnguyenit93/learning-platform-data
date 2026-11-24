# JUnit Tags, Gradle Test Filters, and Group-Based Test Tasks in Spring Boot

## 1. Why Split Tests into Groups?

A Spring Boot project may have pure Java tests running in under a second, Spring context tests needing a few seconds, database/Kafka connection tests requiring real containers, and smoke tests that only check whether an application version can start. If every test sits inside one undifferentiated Gradle `test` task, developers end up waiting on heavy resources when changing small logic; conversely, if CI skips slow tests arbitrarily, integration bugs can slip into the main branch.

**JUnit Jupiter `@Tag`** labels a test class or method. **Gradle `Test.useJUnitPlatform { includeTags/excludeTags }`** selects which labels run in a task. **Gradle `--tests` or `Test.filter.includeTestsMatching`** filters by class/method name, **not by label**. **Gradle `Test` tasks** such as `test`, `integrationTest`, `slowIntegrationTest`, and `smokeTest` create command groups with independent policies for local/PR/nightly/release runs.

Lesson objectives:
1. Apply and explain `@Tag("unit")`, `@Tag("integration")`, `@Tag("slow")`, and `@Tag("smoke")` semantically.
2. Distinguish **tag filtering**, **test name filtering**, **file/class patterns**, **JUnit Platform engines**, and **task selection**.
3. Understand **tag expression** syntax `&`, `|`, `!`, and parentheses, along with class/method tag behavior.
4. Configure Gradle Groovy DSL for test tasks sharing the same test source set with non-overlapping filters.
5. Identify clearly which group `check` runs automatically and which groups **only run when explicitly requested**.
6. Avoid traps where `--tests` cannot override `includeTags`, filtered-out tests are mistaken for passed tests, or untagged tests are forgotten.
7. Design CI matrices, caching, reports, resource isolation, and retry/flake triage for test groups.
8. Build a consistent Java 17+, Spring Boot 3.5.x, Gradle, and JUnit Jupiter project with per-group commands and real assertions.

**Scope:** This article focuses on **organization/selection/execution policy**, without trying to replace full `@SpringBootTest`/Testcontainers coverage or unit testing methodology. The sample uses Spring Boot 3.5.8, Java 17+, Gradle Groovy DSL, JUnit Jupiter, and AssertJ; no Docker or external services are required. The `slow` group illustrates an "extended run" policy without artificial `Thread.sleep` calls.

## 2. Four Layers to Distinguish

```text
                 Developer or CI
                         |
    ./gradlew check / integrationTest / smokeTest
                         |
                         v
                Gradle TASK GRAPH
                  +-----------+
                  | test      |  includeTags("unit")
                  |           |
                  | integrationTest |  includeTags("integration & !slow")
                  |           |
                  | slowIntegrationTest | includeTags("integration & slow")
                  |           |
                  | smokeTest | includeTags("smoke")
                  +-----------+
                         |
                         v
               TEST JVM / JUNIT PLATFORM
                 |              |
           Class/method       Tag expression
           name filters      include/exclude
                 |              |
                 +------ AND ----+
                         |
                         v
                 Selected tests
                         |
                  Executed / failed /
                    skipped / passed
```

The `AND` diagram emphasizes that name filters and tag filters **jointly narrow the set of executed tests**; `--tests` is not a switch to bypass the tag conditions of a defined `Test` task.

### 2.1. Quick Comparison

| Concept | Example | What It Selects | What It Is Not |
|---|---|---|---|
| JUnit tag | `@Tag("integration")` | Metadata on a test container/method | A test execution command |
| JUnit tag expression | `integration & !slow` | Tests with `integration` but not `slow` | A file name filter |
| Gradle JUnit filter | `useJUnitPlatform { includeTags 'unit' }` | Task tests matching the tag | `--tests` |
| Gradle test name filter | `--tests "*CalculatorTest"` | Class/method matching the name | The `unit` label |
| Gradle Test.filter | `includeTestsMatching("*CatalogTest")` | Class/method name (pattern) | A tag expression |
| Gradle class file include | `include '**/*Test.class'` | Test files scanned | Method selection via `@Tag` |
| Gradle task selection | `./gradlew integrationTest` | Task to execute | Implicitly running all tests |
| `check` dependencies | `check.dependsOn integrationTest` | Task wired into verification lifecycle | Auto-including all custom Test tasks |
| `maxParallelForks` | `2` | Max forked test JVMs for the task | Tag count |
| JUnit `@Disabled` | `@Disabled("reason")` | Skips execution of a discovered test | Equivalent to a tag filter |

`@Tag` does not make a test fast or slow, does not change its lifecycle or test engine, and does not indicate that a test passed. It is **metadata for selecting cases according to build policy**.

## 3. JUnit Jupiter @Tag: Where to Apply Labels?

### 3.1. Labeling a Test Class

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("unit")
class MathRulesTest {

    @Test
    void shouldCalculateTax() {
        // A JUnit test belonging to the unit group.
    }
}
```

This is an illustrative fragment; its body lacks assertions and is **not a standalone usable test**. When a class carries `@Tag("unit")`, the test methods discovered inside that class carry that tag in the JUnit Platform discovery/execution model.

In practice, place the tag at the **class** level if the entire class shares one uniform testing level. This helps reviewers quickly see which files are unit/integration/smoke.

### 3.2. Labeling a Method

```java
@Tag("integration")
class CatalogIntegrationTest {

    @Test
    void quickRepositoryContract() {
        // Runs in the integration group.
    }

    @Test
    @Tag("slow")
    void fullValidationMatrix() {
        // Has BOTH "integration" (from class)
        // AND "slow" (from method).
    }
}
```

This fragment illustrates **tag inheritance along the container → method hierarchy**. The method `fullValidationMatrix` carries **both tags**, so:
- `integration & !slow` selects `quickRepositoryContract`.
- `integration & slow` selects `fullValidationMatrix`.
- `slow` also selects `fullValidationMatrix`.
- `unit` selects neither method here.

A method tag **adds to**, rather than "removes", a class tag. Do not put `@Tag("slow")` on the whole class if only one method is slow, unless you want all methods of the class treated as slow.

### 3.3. Multiple Tags on One Class

```java
@Tag("integration")
@Tag("database")
class ProductRepositoryTest {
    // Every test here carries both integration and database tags.
}
```

This is a fragment with no test methods declared yet. `@Tag` is repeatable; multiple annotations can be placed on one class/method. Two axes—`integration` (test level) and `database` (resource/category)—help CI pick the right group conditionally.

**Valuable convention:** Use one clear axis for test type (`unit`, `integration`, `smoke`) and another for traits (`slow`, `database`, `external`, `nightly`). If each team invents `int`, `integ`, `IT`, `integration-test` ad hoc, tag filters will miss tests.

### 3.4. Tags Are Not Arbitrary Strings

JUnit requires tags to be non-empty and free of whitespace, control characters, or characters used in tag expression syntax such as `,`, `(`, `)`, `&`, `|`, `!`. Use:
- `unit`, `integration`, `slow`, `smoke`, `postgres`, `api-v2`.
- Avoid `"integration test"`, `"slow,network"`, `"unit|integration"`.

In a tag expression, `|` means **OR**, `&` means **AND**, and `!` means **NOT**. That is **filtering** syntax, not the content of a single tag.

## 4. Tag Expression Syntax

JUnit Platform's grammar includes:
- `!`: tag negation.
- `&`: intersection/AND.
- `|`: union/OR.
- `(` and `)`: grouping to override precedence.

**Common precedence:** `!` binds tighter than `&`, then `|`. Use parentheses whenever an expression has two or more operators so readers and CI reviewers do not have to guess.

| Tag expression | Meaning |
|---|---|
| `unit` | Selects tests with tag `unit` |
| `integration` | Selects tests with tag `integration` |
| `smoke` | Selects smoke tests |
| `unit | smoke` | Unit **or** smoke |
| `integration & !slow` | Integration **and not slow** |
| `integration & slow` | Both integration and slow |
| `(integration | smoke) & !external` | Integration or smoke, without needing external |
| `!slow` | Tests not tagged `slow` |
| `database & integration` | Integration needing a database |
| `unit & integration` | Tests carrying both tags, usually a classification smell if policy requires mutually exclusive test types |

**The trap of `!slow`:** It can also match **untagged tests** if no other filter excludes them. Hence `includeTags 'unit'` is more precise than `excludeTags 'slow'` when the PR pipeline should only run **tests classified as unit**.

### 4.1. An `includeTags` Entry Can Contain a Tag Expression

Gradle supports this through JUnit Platform:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'integration & !slow'
    }
}
```

This is a Gradle configuration fragment. JUnit Platform parses `integration & !slow` as an expression; it is not a literal tag containing spaces.

For multiple expressions:

```groovy
useJUnitPlatform {
    includeTags 'unit', 'smoke & !external'
}
```

In Gradle/JUnit Platform, multiple include expressions select tests matching any of the expressions. Writing one explicit expression `'unit | (smoke & !external)'` is often easier to review when policy is complex. Use `excludeTags` to drop a set like `slow`, keeping in mind that excluding can drop cases from an included set if they carry multiple tags.

### 4.2. Tag Inheritance Is Not Identical to Java @Inherited Everywhere

JUnit provides tag semantics as classes, nested classes, interfaces, or methods are discovered in the test model. Do not extrapolate full inheritance from general Java annotation syntax. For meta-annotations/composed annotations, read the JUnit docs and test a small sample when the project uses custom annotations. What is guaranteed in the project below: `@Tag("integration")` on the test class and `@Tag("slow")` on a method gives that method both tags during JUnit test selection.

## 5. Gradle --tests Filters by Name, Not by Tag

### 5.1. Gradle CLI --tests for Debugging a Class/Method

```bash
./gradlew test --tests "com.example.groups.PriceCalculatorTest"
./gradlew test --tests "*PriceCalculatorTest.discountTenPercent"
```

`--tests` takes a test class/method name pattern. It is useful when running a failing case from an IDE or CI log without running the entire suite.

**Wrong:** `./gradlew test --tests unit` does not mean "run tests with `@Tag("unit")`". Gradle tries to match **names** against the pattern `unit`, not tags. With `includeTags 'unit'`, run the whole group with `./gradlew test`.

### 5.2. --tests and includeTags Combine by Intersection

Suppose:
- The `test` task only has `includeTags 'unit'`.
- `CatalogServiceIntegrationTest` has `@Tag("integration")`.

Command:

```bash
./gradlew test --tests "com.example.groups.CatalogServiceIntegrationTest"
```

**This does not turn an integration test into a unit test.** The class matches by name but still **does not satisfy the tag** of `test`. Depending on Gradle/JUnit version/filter state, the result may report "No tests found for given includes" or run zero tests. Correct command:

```bash
./gradlew integrationTest --tests "com.example.groups.CatalogServiceIntegrationTest"
```

Even that second command only selects methods matching `integration & !slow` as configured on the task; to run the slow method, invoke `slowIntegrationTest --tests ...`.

**Rule of thumb:** `--tests` **narrows within the group selected by the task**, and cannot override a task's fixed tag filters.

### 5.3. Test.filter and includeTestsMatching

You can place name filters in the build script:

```groovy
tasks.named('test', Test) {
    filter {
        includeTestsMatching '*PriceCalculatorTest'
        excludeTestsMatching '*LegacyFlakyTest'
    }
}
```

This is an optional fragment and is **not** added to the sample build below. `includeTestsMatching` and `excludeTestsMatching` match class/method names. Neither `filter` nor `--tests` parses tag expressions.

**Trap:** If you add a permanent `includeTestsMatching '*PriceCalculatorTest'` to the unit task, other unit classes may never run even if they have `@Tag("unit")`. Use name filters mainly for debugging, transition conventions, or a group genuinely defined by name.

### 5.4. Gradle File Include/Exclude Patterns Differ from TestFilter

```groovy
tasks.named('test', Test) {
    include '**/*Test.class'
}
```

This fragment is for class file patterns (not test methods/tags), governing which files are scanned. Do not use `include '**/*IntegrationTest.class'` as a substitute for JUnit tags unless the project has a strict file naming convention it intends to enforce. Tag expressions are far more flexible for `@ParameterizedTest`, `@Nested`, and multi-trait methods.

### 5.5. JUnit Platform Engine Filtering

```groovy
useJUnitPlatform {
    includeEngines 'junit-jupiter'
}
```

This selects a **test engine**, not a tag or name. It helps if the classpath also carries JUnit Vintage or Spock engines; however, `includeEngines 'junit-jupiter'` does not replace `includeTags 'unit'`. With Spring Boot 3.5 and JUnit Jupiter, the sample project below only needs `useJUnitPlatform`.

## 6. Recommended Test Group Policy

For a small-to-medium Spring Boot project:

| Group | Tag or Expression | Purpose | When Run |
|---|---|---|---|
| Unit | `unit` | Pure Java/logic without Spring context | Local/PR, `test` |
| Fast Integration | `integration & !slow` | Spring DI, lightweight slice/full context | PR, `integrationTest` |
| Extended Integration | `integration & slow` | Large matrices, DB/Testcontainers, out-of-JVM contracts | Nightly/on-demand, `slowIntegrationTest` |
| Smoke | `smoke` | Context startup, minimal liveness path | Release/on-demand, `smokeTest` |

Two points should be clear from the start:
- `slow` here **is a policy label**, not an auto-measured profiler metric. A method goes into the slow lane because the team agrees it does not need to run on every PR, not because it uses `Thread.sleep`.
- `smokeTest` in the demo is an **application context startup smoke test**, not a synthetic HTTP check against an external deployed environment. True post-deploy smoke needs a running endpoint/service and a dedicated suite with explicit environment settings.

### 6.1. Why Not Just Exclude slow from the test Task?

If `test` only does `excludeTags 'slow'`, integration/smoke tests without `slow` can still run whenever a developer runs `./gradlew test`. To keep the unit lane pure, use **positive selection** `includeTags 'unit'`. When organizing multiple test types, every test must be tagged explicitly; **untagged tests will not run in tasks using `includeTags`**—a risk that requires an inventory/naming guard policy.

### 6.2. Rule to Avoid Duplicate Execution

A test carrying both `@Tag("integration")` and `@Tag("smoke")` can be picked up by two tasks if both include matching tags. If you want mutually exclusive groups, define a convention: each class has **one test-level tag** (`unit`/`integration`/`smoke`), while modifiers like `slow` may be added. When an intentionally shared integration-and-smoke test exists, either accept the double run or use transparent exclusion expressions.

In the sample project:
- Unit tests carry only `unit`.
- The integration class carries `integration`; one method adds `slow`.
- The smoke class carries only `smoke`.
- Task `integrationTest` selects `integration & !slow`.
- Task `slowIntegrationTest` selects `integration & slow`.

The sets are designed to be **non-overlapping** in the example.

## 7. Hands-on Java 17+ / Spring Boot 3.5.8 Project

Full structure:

```text
build.gradle
src/main/java/com/example/groups/
    CiGroupsApplication.java
    PriceCalculator.java
    Quote.java
    CatalogService.java
src/test/java/com/example/groups/
    PriceCalculatorTest.java
    CatalogServiceIntegrationTest.java
    ApplicationSmokeTest.java
```

The three test classes contain **8 JUnit Jupiter `@Test` methods** in total:
- 4 unit methods.
- 2 fast-integration methods.
- 1 slow-integration method.
- 1 smoke method.

No `application.properties` file is required, since the project uses no datasource/web/external clients. `@SpringBootTest` starts a non-web application context; no DB, Docker, or fixed ports are needed.

### 7.1. Complete build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

// Main 'test' task: unit tests only.
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'unit'
    }
    maxParallelForks = 2
    testLogging {
        events 'failed', 'skipped'
    }
}

// Custom tasks reuse compiled classes from sourceSets.test.
def integrationTask = tasks.register('integrationTest', Test) {
    description = 'Run integration tests suitable for pull requests'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'integration & !slow'
    }
    maxParallelForks = 1
    mustRunAfter tasks.named('test')
}

def slowTask = tasks.register('slowIntegrationTest', Test) {
    description = 'Run extended integration tests on demand'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'integration & slow'
    }
    maxParallelForks = 1
    mustRunAfter integrationTask
}

def smokeTask = tasks.register('smokeTest', Test) {
    description = 'Run application-context smoke tests'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'smoke'
    }
    maxParallelForks = 1
    mustRunAfter integrationTask
}

// The Gradle Java plugin already makes check depend on test.
// Add integration-fast to the PR verification lifecycle.
tasks.named('check') {
    dependsOn integrationTask
}

// slowTask and smokeTask are registered but NOT added to check:
// Nightly/release CI can invoke them separately.
```

**Breakdown of each decision:**
- `useJUnitPlatform`: tells Gradle to run JUnit Jupiter tests via JUnit Platform.
- `test` only has `includeTags 'unit'`: `./gradlew test` does not run integration/smoke.
- The other tasks are **new** `Test` tasks, but reuse the **same compiled test classes** via `sourceSets.test.output.classesDirs` and the **same runtime classpath**. This is required when defining a custom `Test` task; do not assume every Gradle version assigns the default source set automatically.
- `integrationTest` runs only `integration & !slow`.
- `slowIntegrationTest` runs only `integration & slow`.
- `smokeTest` runs only `smoke`.
- `check` runs **test + integrationTest** via dependencies; slow/smoke are opt-in.
- `mustRunAfter tasks.named('test')` only controls **ordering when both tasks are scheduled**, and does not create a dependency forcing `test` to run when you invoke `integrationTest` alone.
- Gradle creates report directories per task name; e.g., `build/reports/tests/test/`, `build/reports/tests/integrationTest/`, `build/reports/tests/slowIntegrationTest/`, `build/reports/tests/smokeTest/`.

`maxParallelForks` is the number of test **JVM processes**, not JUnit threads, and is bounded by `--max-workers`. It **does not affect tag selection**. For Spring context integration/smoke, keep one fork in the example for simplicity; production can increase it after verifying resource isolation.

### 7.2. CiGroupsApplication.java

File `src/main/java/com/example/groups/CiGroupsApplication.java`:

```java
package com.example.groups;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CiGroupsApplication {

    public static void main(String[] args) {
        SpringApplication.run(CiGroupsApplication.class, args);
    }
}
```

The main class enables `@SpringBootTest` discovery in package `com.example.groups`. Without a web starter, the sample boots a Spring context **without opening an HTTP server**.

### 7.3. PriceCalculator.java: Domain Logic Without Spring

File `src/main/java/com/example/groups/PriceCalculator.java`:

```java
package com.example.groups;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

import org.springframework.stereotype.Component;

@Component
public class PriceCalculator {

    public BigDecimal afterDiscount(
            BigDecimal price, int percent) {

        Objects.requireNonNull(price, "price");

        if (price.signum() < 0) {
            throw new IllegalArgumentException(
                    "price must not be negative");
        }
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                    "percent must be between 0 and 100");
        }

        return price.multiply(
                BigDecimal.valueOf(100 - percent))
            .divide(BigDecimal.valueOf(100),
                2, RoundingMode.HALF_UP);
    }
}
```

The class is annotated with `@Component` so Spring integration tests can inject it, while unit tests still **instantiate it directly via `new PriceCalculator()`**; there is no need to bootstrap `ApplicationContext` just to test a calculation. `BigDecimal` avoids unpredictable floating-point rounding.

### 7.4. Quote.java: Immutable Result

File `src/main/java/com/example/groups/Quote.java`:

```java
package com.example.groups;

import java.math.BigDecimal;

public record Quote(
        String sku,
        BigDecimal payableAmount) {
}
```

Using a Java record makes test assertions straightforward without needing JPA `@Entity` or Jackson serialization. This project focuses on selecting test groups without depending on persistence infrastructure.

### 7.5. CatalogService.java: Spring DI Integration

File `src/main/java/com/example/groups/CatalogService.java`:

```java
package com.example.groups;

import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final PriceCalculator calculator;

    public CatalogService(PriceCalculator calculator) {
        this.calculator =
                Objects.requireNonNull(calculator);
    }

    public Quote quote(String sku,
            BigDecimal listPrice,
            int discountPercent) {

        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }

        BigDecimal amount = calculator.afterDiscount(
                listPrice, discountPercent);

        return new Quote(sku, amount);
    }
}
```

This is a **stateless** service injected by Spring. `@SpringBootTest` verifies Spring bean creation and constructor wiring. Unit tests for `PriceCalculator` do not need Spring; splitting groups lets developers choose the right feedback time.

## 8. Three Complete JUnit Classes

### 8.1. PriceCalculatorTest.java: Four Unit Cases

File `src/test/java/com/example/groups/PriceCalculatorTest.java`:

```java
package com.example.groups;

import java.math.BigDecimal;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Tag("unit")
class PriceCalculatorTest {

    private final PriceCalculator calculator =
            new PriceCalculator();

    @Test
    void discountTenPercent() {
        BigDecimal result = calculator.afterDiscount(
                new BigDecimal("100.00"), 10);

        assertThat(result)
                .isEqualByComparingTo("90.00");
    }

    @Test
    void discountWithHalfUpRounding() {
        BigDecimal result = calculator.afterDiscount(
                new BigDecimal("99.99"), 25);

        assertThat(result)
                .isEqualByComparingTo("74.99");
    }

    @Test
    void rejectsNegativePrice() {
        assertThatThrownBy(() ->
                calculator.afterDiscount(
                    new BigDecimal("-1"), 10))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("price must not be negative");
    }

    @Test
    void rejectsInvalidDiscountRate() {
        assertThatThrownBy(() ->
                calculator.afterDiscount(
                    new BigDecimal("10"), 101))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage(
                "percent must be between 0 and 100");
    }
}
```

Because `@Tag("unit")` is on the **class**, all 4 methods carry the `unit` tag; none belongs to integration or smoke. The tests instantiate a plain Java object with no network, DB, or Spring context. They fit the `test` lane that runs frequently on laptops/PRs.

### 8.2. CatalogServiceIntegrationTest.java: Two Fast Cases, One Slow Case

File `src/test/java/com/example/groups/CatalogServiceIntegrationTest.java`:

```java
package com.example.groups;

import java.math.BigDecimal;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@Tag("integration")
class CatalogServiceIntegrationTest {

    @Autowired
    private CatalogService catalog;

    @Autowired
    private PriceCalculator calculator;

    @Test
    void contextWiresCatalogAndCalculator() {
        assertThat(catalog).isNotNull();
        assertThat(calculator).isNotNull();

        Quote result = catalog.quote(
                "SKU-A", new BigDecimal("100.00"), 10);

        assertThat(result.sku()).isEqualTo("SKU-A");
        assertThat(result.payableAmount())
                .isEqualByComparingTo("90.00");
    }

    @Test
    void serviceRejectsBlankSku() {
        assertThatThrownBy(() ->
                catalog.quote(
                    "   ", new BigDecimal("10.00"), 0))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("sku must not be blank");
    }

    @Test
    @Tag("slow")
    void extendedDiscountMatrix() {
        for (int percent = 0; percent <= 100; percent++) {
            Quote quote = catalog.quote(
                    "SKU-MATRIX",
                    new BigDecimal("100.00"),
                    percent);

            BigDecimal expected =
                    BigDecimal.valueOf(100 - percent)
                        .setScale(2);

            assertThat(quote.payableAmount())
                .as("discount percent = " + percent)
                .isEqualByComparingTo(expected);
        }
    }
}
```

**How JUnit resolves the tags:**
- `contextWiresCatalogAndCalculator`: `integration`.
- `serviceRejectsBlankSku`: `integration`.
- `extendedDiscountMatrix`: `integration` **and** `slow` (method tag adds to the class tag).

Therefore:
- `integrationTest` (`integration & !slow`) runs the **first 2 methods**.
- `slowIntegrationTest` (`integration & slow`) runs the **last 1 method**.
- `test` (`unit`) does not run this class at all.

**Note on the `slow` label:** A loop of 101 calculations is not claimed to be slow on a modern CPU. It serves as an `extended` test to illustrate CI policy; real projects should apply `slow` to costly tests such as Testcontainers, migrations, full matrices, or external adapters. Do not add `Thread.sleep(5000)` to make it "look slow".

### 8.3. ApplicationSmokeTest.java: Context Startup Smoke

File `src/test/java/com/example/groups/ApplicationSmokeTest.java`:

```java
package com.example.groups;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Tag("smoke")
class ApplicationSmokeTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void applicationContextStartsWithRequiredBeans() {
        assertThat(context).isNotNull();
        assertThat(context.getBean(CatalogService.class))
                .isNotNull();
        assertThat(context.getBean(PriceCalculator.class))
                .isNotNull();
    }
}
```

One smoke test verifies that the application context starts and contains the essential beans. It does not open an HTTP port and **does not prove a production deployment endpoint works**. If you want smoke testing over real HTTP responses, add `spring-boot-starter-web` and a separate `@SpringBootTest(webEnvironment=RANDOM_PORT)` test, or a CI post-deploy probe; do not call a context-only test end-to-end release validation.

## 9. Expected Selection Matrix for the Project

| Gradle Command | Task | Unit 4 | Fast Integration 2 | Slow Integration 1 | Smoke 1 | Total |
|---|---|---:|---:|---:|---:|---:|
| `./gradlew test` | `test` | 4 | 0 | 0 | 0 | **4** |
| `./gradlew integrationTest` | `integrationTest` | 0 | 2 | 0 | 0 | **2** |
| `./gradlew slowIntegrationTest` | `slowIntegrationTest` | 0 | 0 | 1 | 0 | **1** |
| `./gradlew smokeTest` | `smokeTest` | 0 | 0 | 0 | 1 | **1** |
| `./gradlew check` | `test` and `integrationTest` | 4 | 2 | 0 | 0 | **6** |
| `./gradlew check slowIntegrationTest smokeTest` | All four Test tasks | 4 | 2 | 1 | 1 | **8** |

**These are the methods written and the expected selection under the sample configuration**, not logs confirming actual execution. If new classes are added, tags change, or CLI `--tests` filters are passed, expected counts also change. Gradle may report tasks as `UP-TO-DATE`/cached; actual executed counts in a real run must be read from task state and XML/HTML reports.

### 9.1. Understanding check and mustRunAfter

The Gradle Java plugin makes the `check` task depend on `test` by lifecycle convention. The example adds `integrationTest` as another dependency. `mustRunAfter test` makes `integrationTest` run after `test` **when both are in the graph**.

`mustRunAfter` does not trigger `integrationTest` when you run `./gradlew test`. Conversely, `./gradlew integrationTest` can run standalone without running unit tests first. This lets developers run the exact group they need.

If you must ensure `integrationTest` **cannot** run when unit tests fail, configure `integrationTest.dependsOn test` to create a hard dependency. However, that causes every `integrationTest` invocation to also run the unit task (or at least evaluate its dependency graph), removing the standalone independence shown in the policy. Choose according to build requirements, and do not confuse ordering with dependency.

### 9.2. A Common Mistake with Custom Test Tasks

When writing:

```groovy
tasks.register('integrationTest', Test) {
    useJUnitPlatform {
        includeTags 'integration'
    }
}
```

This is an **incomplete configuration example**, because a custom `Test` task needs valid `testClassesDirs` and `classpath`. Some older Gradle versions had default behavior that made it appear to work; do not rely on that, especially when upgrading Gradle. The main build explicitly supplies both values from `sourceSets.test`.

## 10. When to Split Source Sets Instead of Only Tags?

Putting every group in `src/test/java` makes starting fast, but integration tests may need heavy dependencies like Testcontainers, Flyway, or external SDKs; thus the **unit suite's compile classpath** still contains those dependencies even though Gradle tags do not run integration tests.

A larger structure:

```text
src/test/java/               unit tests
src/integrationTest/java/    integration tests
src/smokeTest/java/          smoke tests
```

This can be implemented via:
- Gradle `sourceSets { integrationTest { ... } }` and a dedicated `Test` task;
- or the Gradle **JVM Test Suite Plugin** `testing { suites { integrationTest(JvmTestSuite) { ... } } }`.

**Difference:** Source sets separate **compile/runtime classpaths and source directories**, whereas `@Tag` separates **selection logic inside JUnit Platform**. Both can be combined: split out an integration source set to manage dependencies, and still use the `slow` tag to select subsets within the integration suite.

### 10.1. Trade-offs

| Criterion | Single Source Set + Tags | Multiple Source Sets/Suites |
|---|---|---|
| Initial setup | Minimal configuration | More configuration |
| Dependencies | Shared test dependency graph | Can be split per suite |
| Method-level `@Tag` | Convenient | Still usable |
| Risk of missing tag & omission | Yes, if all tasks use `includeTags` | Lower when suite is chosen by directory, though still possible |
| Classpath/compilation isolation | No | Yes |
| Per-task Gradle reports | Yes | Yes |
| CI matrix | Easy | Easy once suites are clear |
| Small project | Very suitable | Can be overly complex |
| Project with many Testcontainers/SDKs | Can bloat build/test classpath | Often easier to manage |

If moving to the JVM Test Suite Plugin, check the exact Gradle version in use and declare suite dependencies explicitly. Additional suites **should not be assumed to inherit all `implementation` dependencies of main sources automatically** just because the built-in `test` suite does. Do not simultaneously define both a custom `Test` task named `integrationTest` and a `JvmTestSuite`-generated task of the same name without migrating the configuration properly.

## 11. PR, Nightly, and Release CI Scenarios

### 11.1. Pull Request: Fast and High-Signal

```bash
./gradlew clean check --max-workers=2
```

In the sample project, `check` includes `test` and fast integration; the target is 4 unit + 2 integration methods. Depending on the organization, `smokeTest` may be added if context startup is cheap; this policy keeps smoke in the release lane for distinction.

**Do not** drop fast integration from PRs just because `@SpringBootTest` takes a few seconds if it guards an important part of the contract. The goal of splitting groups is explicit budgeting, not cutting every Spring test.

### 11.2. Nightly: Extended Suite

```bash
./gradlew check slowIntegrationTest --max-workers=2
```

Task `slowIntegrationTest` selects `integration & slow`; the other cases are already in `check`. If nightly runs verify databases, build containers, and integration data, configure dedicated test environments/credentials/seeded services rather than depending on a production DB.

### 11.3. Release/Local Smoke

```bash
./gradlew smokeTest --max-workers=1
```

The demo smoke test only initializes the context. If an organization needs **deployed smoke** after rollout, create a separate job calling the deployed instance's endpoint with proper timeouts, auth, and routing; do not equate a JUnit context smoke test with a deployment health check.

### 11.4. Debugging a Failing Test

```bash
./gradlew test   --tests "com.example.groups.PriceCalculatorTest.discountTenPercent"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.groups.PriceCalculatorTest.discountTenPercent"
```

To debug fast integration:

```bash
./gradlew integrationTest   --tests "com.example.groups.CatalogServiceIntegrationTest.contextWiresCatalogAndCalculator"
```

To debug slow integration:

```bash
./gradlew slowIntegrationTest   --tests "com.example.groups.CatalogServiceIntegrationTest.extendedDiscountMatrix"
```

If you run `./gradlew test --tests "*CatalogServiceIntegrationTest"`, `@Tag("integration")` does not satisfy `includeTags 'unit'`; do not "fix" it by adding a misleading `unit` tag. Select the **right Gradle task**.

### 11.5. Running One Task Does Not Mean CI Ran All Tests

If CI only runs `./gradlew test`, under the sample policy it **runs only unit tests**. Reviewing pipeline YAML requires checking the exact Gradle commands. Likewise, `./gradlew check` **does not** run `slowIntegrationTest` or `smokeTest` unless dependencies were added. Defining a task in the Gradle build file **does not automatically place it in the `check` lifecycle**.

## 12. @Disabled, @Tag, and @Nested Have Different Roles

### 12.1. @Disabled Is Not a Test Group

```java
@Disabled("Provider contract temporarily unavailable")
@Test
void shouldUseExternalProvider() {
}
```

This is an illustrative fragment; the test is discovered but disabled by a JUnit condition. Adding `@Tag("slow")` does not disable a test—it only takes effect if a Gradle task filters by tag. Consequently, do not slap a `quarantined` tag on a test and forget that every CI group excludes it: tests can be silently ignored forever.

If quarantine is needed, create an explicit task selecting `quarantined` with ownership, expiry/review, and metrics instead of leaving `@Disabled` indefinitely. Tags do not replace a workflow for fixing flaky tests.

### 12.2. @Nested and Tags on the Outer Class

A nested JUnit test class is normally discovered as a child container in the Jupiter model. Tags on the outer container can apply to nested tests. Test your tag expressions when nested classes/methods carry multiple tags, especially when migrating a large suite to tag-based filtering; avoid assuming each nested class spawns a new Gradle JVM fork.

### 12.3. @ParameterizedTest Is One Method with Multiple Invocations

`@ParameterizedTest` can generate many invocations/dynamic test display names, while method-level tags still apply. When reading reports, **invocation** counts can differ from `@Test` source method counts or class file counts. With `--tests` filtering by method, Gradle/JUnit can execute all invocations of that method depending on the filter; do not substitute source method counts for executed counts in CI.

### 12.4. Meta-Annotations for Conventions

A project can define a custom annotation like `@FastUnitTest` meta-annotated with `@Tag("unit")` (and optionally `@Test` for method-level annotations). This reduces repetition. However, once custom annotations are used, add a test/discovery check or policy enforcement to confirm they emit the intended tags on JUnit Platform rather than assuming Gradle recognizes them just from the annotation name.

## 13. Checking Completeness of Test Grouping

**Biggest risk of positive filtering:** a developer adds `NewFeatureTest` and forgets `@Tag`. When all test tasks use `includeTags`, that test might **belong to no task at all**, and `check` still passes.

A process to avoid omissions:
1. Establish a CONTRIBUTING convention: every Jupiter test class has exactly one primary tag: `unit`, `integration`, or `smoke`.
2. Modifiers like `slow`, `database`, `network` may be placed on classes or methods.
3. Enforce the rule in code review.
4. Add a **CI architecture/discovery check** that flags untagged tests, or use a controlled Gradle/JUnit launcher discovery report.
5. During migration, temporarily keep an `allTests` task without tag filters to reconcile discovered test counts against the sum of lanes; use tooling/reports to avoid double-counting multi-tagged tests.
6. Do not rely solely on numbers in the `test` HTML report because that is only a subset.

**Note on duplicate counting:** If one test carries tags from two groups, `unitCount + integrationCount + smokeCount` can exceed the unique test total. If task filters overlap, this is not necessarily a bug, but requires a clear convention and careful coverage interpretation.

### 13.1. An All-Tests Diagnostic Task (Fragment)

If you need a standalone task to audit test discovery:

```groovy
tasks.register('allTestsDiagnostic', Test) {
    group = 'verification'
    description = 'Diagnostic: run all JUnit Platform tests'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform()
}
```

This is **optional** and not in the main `build.gradle` in section 7. This task **may run external/slow tests**, so use it only in safe environments and do not make it the default for every PR. A safer approach is using the JUnit Launcher API/listener to collect discovered tests and tags **without executing** all side effects, or running static architecture checks per team conventions.

### 13.2. Tags Are Not a Test Coverage Metric

If `integrationTest` runs 2 methods, that number does not measure branch coverage of `CatalogService` or integration contract completeness. Use code coverage, mutation testing, contract tests, and review requirements at another layer. Tags are purely an **execution routing mechanism**.

## 14. Gradle Task Ordering, Caching, and Reports

### 14.1. Each Test Task Has Its Own Report

For Gradle `Test` tasks, outputs typically live at:

```text
build/reports/tests/test/index.html
build/reports/tests/integrationTest/index.html
build/reports/tests/slowIntegrationTest/index.html
build/reports/tests/smokeTest/index.html

build/test-results/test/
build/test-results/integrationTest/
build/test-results/slowIntegrationTest/
build/test-results/smokeTest/
```

Independently configured tasks produce their own results/reports. CI should publish report artifacts from all executed tasks, not only `build/reports/tests/test`. If `integrationTest` fails while CI only collects the unit report, diagnostics suffer.

### 14.2. UP-TO-DATE and FROM-CACHE Do Not Mean Tests Executed in This Run

Gradle uses incremental builds, up-to-date checks, and build caching. A `Test` task may skip re-execution when inputs/outputs are considered valid. Therefore:
- `BUILD SUCCESSFUL` is not proof that every `@Test` just re-ran.
- `UP-TO-DATE` and `FROM-CACHE` differ from `executed`.
- When investigating doubts, use `--rerun-tasks` to force re-execution and inspect logs/reports.
- You do not need `--rerun-tasks` on every PR if the build cache is well-managed and trusted.

If a build skips a test task via `onlyIf` or bad filters, `NO-SOURCE` or zero selected tests can occur. Always check console task output and test results.

### 14.3. mustRunAfter Does Not Create a Dependency

Example:
```groovy
integrationTest.mustRunAfter test
```

This only states **if both are in the task graph, `test` runs before `integrationTest`**. It does not require running unit tests when a developer invokes `integrationTest`. By contrast:
```groovy
integrationTest.dependsOn test
```
creates a dependency; `integrationTest` will not run if its dependency fails. Choose based on test group goals. In the main sample, `check` depends on both tasks; the ordering constraint governs sequence.

### 14.4. --parallel and --max-workers Do Not Select Test Groups

```bash
./gradlew check --parallel --max-workers=4
```

These are Gradle scheduler/build concurrency flags. They do not alter `includeTags`; tasks are selected by CLI arguments and task dependencies. In multi-module builds, `--parallel` can run tasks across projects concurrently. A JUnit `@Tag("serial")` is not a distributed lock across projects; if integration groups share a DB, isolate schemas/ports/data or coordinate in CI.

### 14.5. maxParallelForks and JUnit Threads Are Different Layers

`maxParallelForks=2` only caps the task at two JVM test processes. `junit.jupiter.execution.parallel.enabled=true` (when configured) enables JUnit concurrency inside each JVM. Neither determines `@Tag` selection. Increasing forks does not replace unit/integration/smoke policy.

## 15. CI Matrix: Clarifying Test Groups and Resources

A common matrix:

| Stage | Gradle Command | Group | Environment Requirements |
|---|---|---|---|
| PR quick | `./gradlew test` | Unit | Java + dependencies |
| PR verification | `./gradlew check` | Unit + fast integration | App context or mocks |
| Nightly | `./gradlew check slowIntegrationTest` | Adds slow integration | Docker/DB if real suite requires |
| Release smoke | `./gradlew smokeTest` | Startup smoke | Demo needs no deploy |
| Incident reproduction | `./gradlew integrationTest --tests ...` | One matching integration method | Method's test fixture |
| Full diagnostic | `./gradlew allTestsDiagnostic` | All selected by JUnit Platform | Only when safe for external side effects |

CI should never run commands without knowing **which group is selected**. When keeping CI/GitHub Actions/GitLab/Jenkins aligned, document exact Gradle tasks and profiles. If the project uses secrets/test credentials, grant them only to jobs needing external dependencies; unit tasks do not need production tokens.

### 15.1. Controlling Resources Per Group

**Unit tests:** stateless, no DB, can enable multiple forks if beneficial.

**Integration tests:** may use `@SpringBootTest`, `@DataJpaTest`, Testcontainers. Need random ports, unique DB schemas/IDs, proper thread-level cleanup/rollback, and container lifecycles. If two Gradle `Test` tasks share a database, `mustRunAfter` orders them inside one task graph, but **does not lock** another CI job.

**Slow tests:** often involve data migrations, external contract checks, or full input matrices. Apply sensible timeouts, controlled retries, and reporting. Never fabricate "slow tests" by inserting sleeps to fit the label.

**Smoke tests:** verify minimal startup/liveness of the app. When running post-deploy, tests need appropriate retry/backoff/health semantics; do not equate JUnit context smoke with deployment service readiness.

### 15.2. JUnit @Tag Does Not Replace Test Isolation

Even after grouping, tests within the same task may run in parallel depending on Gradle/JUnit config. If two integration methods share a static `Map`, fixed file, or shared H2 database, `@Tag("integration")` does not isolate them. Use `@TempDir`, `@ResourceLock` (within one JUnit execution plan only), transaction/isolation/unique data, or a serial lane at the Gradle task/CI level.

In the demo project, `CatalogService` and `PriceCalculator` are stateless and use no shared DB/files, making them a clean example of group selection.

## 16. Common Pitfalls and Fixes

| Symptom | Common Cause | Fix |
|---|---|---|
| `./gradlew test` does not run integration | `test` only includes `unit` | Invoke `integrationTest` |
| `--tests integration` does not run tags | `--tests` filters by name | Use a task with `includeTags 'integration'` |
| `--tests "*CatalogServiceIntegrationTest"` with `test` finds nothing | Unit task tag filter excludes the class | Run `integrationTest --tests ...` |
| Slow method runs in PR | `integrationTask` includes `integration` without excluding `slow` | Use `integration & !slow` |
| Slow method never runs in nightly | CI does not invoke `slowIntegrationTest` | Add task to nightly command |
| Smoke class accidentally runs in unit | Unit task only excludes `slow`, does not include `unit` | Positive selection `includeTags 'unit'` |
| New test is missed | Missing `@Tag` | Convention + discovery/static check |
| Test runs twice | Two tasks match overlapping tags | Keep expressions disjoint or accept intentionally |
| Custom `Test` task reports `NO-SOURCE` | Missing `testClassesDirs` or `classpath` | Configure from source set or suite |
| `check` does not run integration | Missing `dependsOn integrationTask` | Add verification lifecycle dependency |
| `mustRunAfter` does not run prior task | Ordering is not a dependency | Use `dependsOn` if needed |
| Tag expression does not match | Syntax error or tag misplaced on class/method | Use `&`, `|`, `!`, and parentheses |
| Tag has space/pipe | Invalid tag identifier | Rename to `slow-integration` or two tags |
| Class has `@Tag("slow")` causing all methods to be excluded | Tag applies to every method | Move modifier down to appropriate method |
| `@Disabled` test not counted as pass | Disable is a condition, not a tag | Remove disable after fixing |
| `@ParameterizedTest` count exceeds source methods | Multiple invocations | Read invocation counts in reports |
| Class path filter too narrow | `include '**/*Test.class'` filters out differently named classes | Use JUnit tags / consistent naming policy |
| Gradle `--parallel` does not parallelize JUnit methods | Not Jupiter mode | Configure JUnit concurrency separately |
| Unit + integration share mock bean and flake | Shared Spring context/mock state | Separate contexts, mock ownership, serial lane |
| DB integration fails across multiple forks | Shared schema, fixed IDs, or ports | Unique schemas/data/ports |
| Reports missing integration results | CI uploads only `test` report | Upload reports per Test task |
| IDE runs test but Gradle does not | IDE JUnit launcher ignores Gradle tags | Run matching Gradle task to verify |
| `BUILD SUCCESSFUL` with zero methods | Task cached/skipped/no matching tags | Inspect task state and XML report |
| Tag refactored inconsistently | Tags are strings, not type-safe | Constants/composed annotations/convention tests |
| Nightly CI slow without clear culprit | Mixed unit/integration/slow | Separate tasks and report per-group duration |
| `@Tag("database")` without a DB | Tag does not provision resources | Add real Testcontainers/config when needed |
| Smoke test passes yet HTTP deployment fails | Smoke is only `@SpringBootTest` context | Add post-deploy HTTP smoke |
| CI selects everything via `!slow` | Untagged and smoke still match | Positively include required groups |

### 16.1. Quick Diagnostic Checklist

1. Check the exact **Gradle task** invoked.
2. Check `useJUnitPlatform { includeTags/excludeTags }` for that task.
3. Check `@Tag` on the test class, method, and enclosing/nested classes.
4. Check for `--tests`, `filter.includeTestsMatching`, class file patterns, or engine filters.
5. Verify custom `Test` tasks have valid `testClassesDirs` and `classpath`.
6. Confirm `check` dependencies include the groups you expect to run.
7. Confirm JUnit Jupiter runtime/launcher dependencies match.
8. Read XML/HTML reports under the **exact task name**.
9. When tests are not found, inspect tags/expressions before changing package scans or business code.
10. When green but suspected not to have run, inspect task state (`UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`) and executed test counts.
11. Never swap `@Tag("integration")` for `@Tag("unit")` just to run a test via the wrong task.
12. Never scale Gradle forks/CI resources before resolving shared state.

## 17. Self-Study Exercises

### Exercise A: Tag Inheritance

Given a `@Tag("integration")` class with two methods: `testA()` with no extra tag, and `testB()` with `@Tag("slow")`. Predict:
- `includeTags('integration')` selects both.
- `includeTags('integration & !slow')` selects only A.
- `includeTags('integration & slow')` selects only B.
- `includeTags('slow')` selects only B.
- `includeTags('unit')` selects neither.

This demonstrates **conditions over tag sets**, independent of method ordering or whether tests pass.

### Exercise B: Does --tests Override Tag Filters?

In a `test` task with `includeTags 'unit'`, run:

```bash
./gradlew test --tests "*CatalogServiceIntegrationTest"
```

Expected selection result: **no integration tests run**, because the name filter does not override the tag filter. To run `contextWiresCatalogAndCalculator`, use:

```bash
./gradlew integrationTest   --tests "*CatalogServiceIntegrationTest.contextWiresCatalogAndCalculator"
```

### Exercise C: Untagged Test

Add `UntaggedNewFeatureTest` with `@Test` and no `@Tag`. Run `./gradlew check`. That test is selected by neither `unit` nor `integration & !slow`; `check` succeeding **does not prove** the new test ran. Add the appropriate tag or improve the inventory policy; never treat silent omission as fine.

### Exercise D: Fixing Groups Without Duplicate Runs

Try adding `@Tag("smoke")` at the class level on `CatalogServiceIntegrationTest`. Predict that methods now carry both integration and smoke, and `smokeTest` will run those tests too. If you want non-overlapping groups, move the smoke check to its own class or adjust expressions by ownership. Do not rely on the `*IntegrationTest` filename to assume JUnit will exclude smoke automatically.

### Exercise E: Nightly Group with Timeouts

In a real project, `slowIntegrationTest` using PostgreSQL Testcontainers may require Docker. Configure task timeouts/resource policies and isolated data, then verify CI runs that task only on nightly schedules. Do not add `sleep` to the demo to fake workload; use real dependencies when the goal is testing external systems.

## 18. Verifying JUnit/Gradle in Practice

### 18.1. Running Each Task

Linux/macOS:

```bash
./gradlew test
./gradlew integrationTest
./gradlew slowIntegrationTest
./gradlew smokeTest
./gradlew check
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat integrationTest
.\gradlew.bat slowIntegrationTest
.\gradlew.bat smokeTest
.\gradlew.bat check
```

The sample project provides only `build.gradle` and `src` files; it assumes you already have a compatible **Gradle wrapper** or use an installed `gradle`. `./gradlew` does not exist automatically just from having `build.gradle`. To generate the wrapper from a compatible Gradle installation, run `gradle wrapper` in the project directory.

### 18.2. Checking Reports After Execution

| Task | HTML Report | Expected Selected Methods |
|---|---|---:|
| `test` | `build/reports/tests/test/index.html` | 4 |
| `integrationTest` | `build/reports/tests/integrationTest/index.html` | 2 |
| `slowIntegrationTest` | `build/reports/tests/slowIntegrationTest/index.html` | 1 |
| `smokeTest` | `build/reports/tests/smokeTest/index.html` | 1 |

These numbers are **based on the source design and task filters**, **not actual execution results** in the current environment. This article does not claim the build/tests have PASSED. After running, reconcile counts in XML/HTML reports, skipped/failed statuses, and CLI filters. If tests were cached and not re-executed, understand the task state before reporting "all ran".

### 18.3. Risk of Mixing JUnit Versions

Spring Boot 3.5 manages JUnit Jupiter/Platform via its dependency BOM. Gradle requires a matching test runtime launcher. If you force a JUnit API version different from the JUnit Engine/Platform version, test discovery can fail or throw `NoSuchMethodError`. Keep versions aligned via the Spring Boot BOM, and avoid copying dependencies from a JUnit 6 guide into an un-upgraded Spring Boot 3.5 project.

### 18.4. Plain javac/java Is Not Suitable for This Project

`PriceCalculator` uses Spring's `@Component` annotation and tests use JUnit/AssertJ, so building/testing through Gradle or Maven with dependency management is the sensible path. Standalone `javac` without Spring/JUnit JARs on the classpath will not compile the full project. If you want to study `BigDecimal` math alone, you can extract a plain Java class without annotations, though that will not test JUnit/Gradle tag filtering.

## 19. Pre-CI Adoption Checklist

- [ ] Consistent primary tag catalog exists: `unit`, `integration`, `smoke`.
- [ ] `slow` and feature/resource tags are used as modifiers without replacing the primary type.
- [ ] Every JUnit test class/method is assigned to at least one regularly executed group.
- [ ] Understood that class tags apply to test methods; method tags add to rather than remove class tags.
- [ ] Tag identifiers are valid, with no whitespace or expression operators.
- [ ] Gradle tasks use `useJUnitPlatform` with explicit `includeTags`.
- [ ] `--tests` is not confused with a tag filter.
- [ ] `filter.includeTestsMatching` and file include patterns are not confused with tags.
- [ ] When passing `--tests`, the name selection lies **within the group** permitted by the task.
- [ ] Custom `Test` tasks have explicit `testClassesDirs` and `classpath`.
- [ ] `check` depends on the exact tasks required for PRs, without assuming every task is auto-included.
- [ ] Nightly/release commands invoke slow/smoke tasks explicitly when policy requires.
- [ ] Tag expressions `integration & !slow` and `integration & slow` are non-overlapping in the example.
- [ ] Process exists to detect untagged tests, and full coverage is never claimed from the `test` report alone.
- [ ] Separate source sets considered if integration needs heavy dependencies.
- [ ] Fixed ports/DB schemas/file paths do not race when concurrency increases.
- [ ] `@Disabled` is not used to permanently ignore flaky tests.
- [ ] JUnit Platform launcher/engine dependencies are aligned with the Spring Boot BOM.
- [ ] CI uploads HTML/XML reports for every executed task.
- [ ] Task cache/`UP-TO-DATE` is properly understood without fabricating executed counts.
- [ ] Every command in documentation matches the exact Gradle task names.
- [ ] Actual tests executed and reports read before claiming runtime PASS.

## 20. Official Documentation

- [JUnit 5 User Guide — Tagging and Filtering](https://docs.junit.org/5.14.1/writing-tests/tagging-and-filtering.html): `@Tag`, tag expressions, tagging test classes/methods.
- [JUnit 5 User Guide — Gradle Build Support](https://docs.junit.org/5.14.1/running-tests/build-support.html): `useJUnitPlatform`, `includeTags`, `excludeTags`, runtime dependencies.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): tags, test filtering, `--tests`, reports.
- [Gradle — TestFilter API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/TestFilter.html): `includeTestsMatching`, `excludeTestsMatching`.
- [Gradle — Test Task API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html): `testClassesDirs`, `classpath`, `maxParallelForks`, `filter`, `useJUnitPlatform`.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): separating integration source sets/suites, task wiring, verification lifecycle.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices, and Spring Boot starter-test.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): context caching, transaction lifecycle, and mock overrides.
- [JUnit 5 User Guide — Test Instance Lifecycle](https://docs.junit.org/5.14.1/writing-tests/test-instance-lifecycle.html): instance lifecycle and test method semantics.

**Conclusion:** `@Tag` only **applies labels**, `useJUnitPlatform { includeTags ... }` decides which labels a Gradle `Test` task selects, and `--tests` only filters **class/method names** within what the task allows. In a Spring Boot project, a deliberate setup with `test` for `unit`, `integrationTest` for `integration & !slow`, `slowIntegrationTest` for `integration & slow`, and `smokeTest` for `smoke` lets local/PR/nightly/release runs execute at the right level. Remember to wire fast integration into `check`, guard against untagged tests, isolate dependencies/resources when needed, and verify **actual reports** before concluding CI checked everything.