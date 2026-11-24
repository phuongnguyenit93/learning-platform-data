# Running a Single Class, a Single Method, or a Tag Group

## 1. Lesson objectives

In a Spring Boot project, running the entire test suite after every small edit can be slow: some tests only check Java logic, some build a Spring `ApplicationContext`, and some require a database or external services. To get fast feedback while still knowing exactly what you are verifying, master three ways to select tests:

1. **By class:** run all tests in one test class, e.g., `CalculatorTest`.
2. **By method:** run a single test method, e.g., `CalculatorTest.addsTwoNumbers`.
3. **By tag:** run a group of tests spanning multiple classes based on `@Tag("smoke")`, `@Tag("unit")`, or combined expressions.

The main scope of this lesson is **how to configure and run tests**, not how to write every type of unit/integration test. Examples use JUnit Jupiter (JUnit 5), Java 17+, and Gradle; a later section compares Maven Surefire for Spring Boot projects using Maven.

### Who actually selects the tests to run?

```text
Command in terminal
  └── Gradle Test task or Maven Surefire
        ├── Filter class/method via CLI arguments
        └── JUnit Platform + Jupiter TestEngine
              ├── Discover runnable tests
              ├── Further filter by JUnit @Tag if configured
              └── Execute tests, return PASS/FAIL/SKIPPED
```

- `@Test` marks a test method.
- `@Tag` **attaches a label**; it does not run or skip a test on its own. Only when tag filtering is configured do labels determine the selected test set.
- `--tests` is a **Gradle argument**, distinct from `@Tag` and distinct from Maven Surefire's `-Dtest`.
- When filtering by both class/method and tag simultaneously, a test must satisfy **both conditions** to be executed.
- Test filtering does not override `@Disabled` or other disabling conditions.

You do not need `@SpringBootTest` to select tests. Selecting a class, method, or tag works for plain JUnit Jupiter, `@WebMvcTest`, `@DataJpaTest`, `@SpringBootTest`, and Spring Framework tests.

## 2. Preparing a runnable demo test suite

To make command results easy to verify, we use a minimal Gradle Java project with **5 PASS tests** split across two classes. This selection mechanism works identically when the tests live inside a Spring Boot application with `spring-boot-starter-test`.

Structure:

```text
select-tests-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/testing/
│   ├── Calculator.java
│   └── GreetingFormatter.java
└── src/test/java/com/example/testing/
    ├── CalculatorTest.java
    └── GreetingFormatterTest.java
```

### 2.1. Gradle and JUnit Platform configuration

`settings.gradle`:

```groovy
rootProject.name = 'select-tests-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

def includedTagExpression = providers.gradleProperty('includeTags').orNull
def excludedTagExpression = providers.gradleProperty('excludeTags').orNull

tasks.named('test', Test) {
    useJUnitPlatform {
        if (includedTagExpression?.trim()) {
            includeTags includedTagExpression.trim()
        }
        if (excludedTagExpression?.trim()) {
            excludeTags excludedTagExpression.trim()
        }
    }

    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
```

This is a **standalone Gradle Java project** so you can run the examples even without a Boot application. The BOM aligns JUnit 5 library versions; `useJUnitPlatform` tells the `test` task to run via JUnit Platform. The two project properties `includeTags` and `excludeTags` take effect only when passed on the command line; if omitted, there is no default tag filter. Thus the build can still run **all 5 tests**.

For an **already configured Spring Boot project**, you usually only need to ensure the testing dependency:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Spring Boot manages JUnit versions via the Boot release's BOM. Keep the `tasks.named('test', Test) { useJUnitPlatform { ... } }` block to support dynamic tag selection; there is no need to force another JUnit BOM onto Boot just to use `@Tag`. This is an **adaptation for Boot projects**, not a requirement to add both dependency blocks to the same project.

If a **Gradle Wrapper** exists, use `./gradlew` on Linux/macOS or `gradlew.bat` on Windows. Without a Wrapper, example commands with `./gradlew` can be replaced with `gradle` if a compatible Gradle is installed on the machine. Run from the directory containing `settings.gradle`.

### 2.2. Java 17+ application code

`src/main/java/com/example/testing/Calculator.java`:

```java
package com.example.testing;

public final class Calculator {
    public int add(int left, int right) {
        return left + right;
    }

    public int divide(int left, int right) {
        return left / right;
    }
}
```

`src/main/java/com/example/testing/GreetingFormatter.java`:

```java
package com.example.testing;

public final class GreetingFormatter {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        return "Hello, " + name.strip() + "!";
    }
}
```

These two classes do not use Spring, making it easy to observe test selection without context startup overhead.

### 2.3. Two test classes and tags on each method

`src/test/java/com/example/testing/CalculatorTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("unit")
class CalculatorTest {
    private final Calculator calculator = new Calculator();

    @Test
    @Tag("smoke")
    void addsTwoNumbers() {
        assertEquals(5, calculator.add(2, 3));
    }

    @Test
    void dividesEvenly() {
        assertEquals(3, calculator.divide(12, 4));
    }

    @Test
    void rejectsDivisionByZero() {
        assertThrows(
                ArithmeticException.class,
                () -> calculator.divide(1, 0)
        );
    }
}
```

`src/test/java/com/example/testing/GreetingFormatterTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingFormatterTest {
    private final GreetingFormatter formatter = new GreetingFormatter();

    @Test
    @Tag("smoke")
    void formatsGreeting() {
        assertEquals("Hello, An!", formatter.greet(" An "));
    }

    @Test
    @Tag("contract")
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> formatter.greet("   ")
        );
    }
}
```

**Actual tests in the example:**

| Class | Method | Effective tags | Result |
| --- | --- | --- | --- |
| `CalculatorTest` | `addsTwoNumbers` | `unit`, `smoke` | PASS |
| `CalculatorTest` | `dividesEvenly` | `unit` | PASS |
| `CalculatorTest` | `rejectsDivisionByZero` | `unit` | PASS |
| `GreetingFormatterTest` | `formatsGreeting` | `smoke` | PASS |
| `GreetingFormatterTest` | `rejectsBlankName` | `contract` | PASS |

`@Tag("unit")` on the **class** applies to every test method inside `CalculatorTest`. `addsTwoNumbers` additionally carries the `smoke` tag from the method-level annotation. A test can belong to multiple groups; method-level tags combine with class-level tags rather than replacing them.

Default run:

```bash
./gradlew test
```

**Expected:** 5 tests run and PASS. The tests do not print fixed `stdout`; Gradle displays test events per logging and report settings. You can open `build/reports/tests/test/index.html` to view each test, or read the XML files in `build/test-results/test/`.

## 3. Running a single test class with Gradle

When editing `Calculator` logic, we often want to run only its test class:

```bash
./gradlew test --tests "com.example.testing.CalculatorTest"
```

In the sample project, this runs the **3 methods** of `CalculatorTest` and skips the two tests in `GreetingFormatterTest`.

Gradle also accepts a **short class name** when unambiguous:

```bash
./gradlew test --tests "CalculatorTest"
```

Or using the wildcard `*`:

```bash
./gradlew test --tests "*CalculatorTest"
```

All of these select the Calculator class in the current test suite. **The fully qualified name with package** is the clearest choice when a repository has multiple classes with the same name.

Several useful patterns:

| Gradle option | Meaning |
| --- | --- |
| `--tests "com.example.testing.CalculatorTest"` | Selects the exact class by fully qualified class name |
| `--tests "CalculatorTest"` | Selects by simple class name |
| `--tests "*CalculatorTest"` | Selects any class matching the wildcard |
| `--tests "com.example.testing.*"` | Selects tests in that package and classes matching the pattern |
| `--tests "*Test"` | Selects classes ending with `Test`; fine for this example, potentially too broad in real projects |

`--tests` filters during **test discovery of the `test` task**; it is not the same as picking a Java source file or running a class with the `java` command. Gradle may still compile sources/tests before running the filtered tests.

### Running multiple classes in one command

You can repeat `--tests`:

```bash
./gradlew test --tests "CalculatorTest" --tests "GreetingFormatterTest"
```

Multiple patterns combine with **OR**; the example runs all 5 tests. Use multiple `--tests` flags when you need to check a few specific classes without modifying `build.gradle`.

## 4. Running a single test method with Gradle

When debugging a narrow bug, running one method gives the shortest feedback loop:

```bash
./gradlew test --tests "com.example.testing.CalculatorTest.addsTwoNumbers"
```

Or with the short class name:

```bash
./gradlew test --tests "CalculatorTest.addsTwoNumbers"
```

**Expected:** only **1 test**, `addsTwoNumbers`, runs; the other two methods in the same class do not run.

To run another method:

```bash
./gradlew test --tests "CalculatorTest.rejectsDivisionByZero"
```

This test PASSES because `assertThrows` expects `ArithmeticException` when dividing by 0. An expected exception does not mean the test failed.

### Selecting multiple methods or using wildcards

```bash
./gradlew test \
  --tests "CalculatorTest.addsTwoNumbers" \
  --tests "CalculatorTest.rejectsDivisionByZero"
```

Expected to run **2 tests**. The trailing `\` is Bash line continuation; on Windows or PowerShell, simply put all arguments on **one line**:

```bash
./gradlew test --tests "CalculatorTest.addsTwoNumbers" --tests "CalculatorTest.rejectsDivisionByZero"
```

If a project has methods sharing a prefix, use `--tests "CalculatorTest.*"` to select the test methods of that class. Do not confuse the Java method name with `@DisplayName`: when running tests by method, use the **method name in source code** for reliable patterns.

**Special cases:** selecting a `@ParameterizedTest` method may run **all parameter invocations** of that method; selecting `@RepeatedTest` may run all repetitions. It does not automatically run just a single invocation. With `@Nested` or dynamic tests, engine-generated display names and identifiers can complicate detailed patterns; start from the enclosing class and inspect the actual report.

## 5. Assigning and understanding JUnit tags

JUnit Jupiter supports `@Tag("group-name")` on classes or methods. Tags are well-suited for managing test groups across multiple packages:

- `unit`: isolated logic tests, run frequently;
- `smoke`: a very small group verifying critical behaviors;
- `integration`: tests integrating with a Spring context, database, or real service;
- `contract`: verifies an input/output contract.

These are **project naming conventions**; JUnit does not infer whether a test is truly a unit or integration test from the tag name alone. Do not put `integration` on a test that does not actually test an integration boundary.

A tag must be a non-empty string; after trimming, it must not contain whitespace, control characters, or reserved characters such as commas, `(`, `)`, `&`, `|`, `!`. Names like `integration-db` are valid and readable.

### Tag expressions

JUnit Platform supports **tag expressions** with these operators:

| Expression | Selected tests |
| --- | --- |
| `smoke` | Has tag `smoke` |
| `unit \| contract` | Has `unit` **or** `contract` |
| `unit & smoke` | Has both `unit` **and** `smoke` |
| `unit & !smoke` | Has `unit` but **not** `smoke` |
| `(smoke \| contract) & !integration` | Has `smoke` or `contract`, and not `integration` |
| `any()` | Has at least one tag |
| `none()` | Has no tags at all |

Operator precedence is `!` before `&` before `|`; use parentheses to express intent clearly. **Do not** use commas to join multiple tags inside one `@Tag`; commas are invalid in tag names.

## 6. Running a tag group with Gradle

Gradle drives JUnit Platform through `useJUnitPlatform { ... }`. In `build.gradle` from Section 2, we mapped the two project properties `includeTags` and `excludeTags` to Platform filters. This lets us pick groups **from the command line** without editing the build file every time.

### Running the entire smoke group

```bash
./gradlew test -PincludeTags=smoke
```

**Expected: 2 tests** — `CalculatorTest.addsTwoNumbers` and `GreetingFormatterTest.formatsGreeting`. Both classes are inspected, and the other methods lack the `smoke` tag so they are not selected.

### Running the entire unit group

```bash
./gradlew test -PincludeTags=unit
```

**Expected: 3 tests** — all tests in `CalculatorTest`, thanks to the class-level `unit` tag.

### Filtering with boolean expressions

In Bash/zsh, wrap the entire argument in single quotes when the expression contains spaces or `!`:

```bash
./gradlew test '-PincludeTags=unit & !smoke'
```

**Expected: 2 tests** — `dividesEvenly` and `rejectsDivisionByZero`. `addsTwoNumbers` has both `unit` and `smoke`, so it is excluded by this expression.

Run the `smoke` or `contract` group:

```bash
./gradlew test '-PincludeTags=smoke | contract'
```

**Expected: 3 tests** — `addsTwoNumbers`, `formatsGreeting`, `rejectsBlankName`.

On **Windows PowerShell/cmd**, use double quotes for arguments with special characters:

```powershell
.\gradlew.bat test "-PincludeTags=unit & !smoke"
.\gradlew.bat test "-PincludeTags=smoke | contract"
```

Quoting ensures the shell passes the expression intact as a single argument. Do not split `unit`, `&`, and `!smoke` into three separate arguments.

### Excluding only one test group

```bash
./gradlew test -PexcludeTags=smoke
```

**Expected: 3 tests** remaining in the sample suite. When both include and exclude are specified, the resulting filter matches "in the allowed group **and** not in the excluded group":

```bash
./gradlew test -PincludeTags=unit -PexcludeTags=smoke
```

This command also runs the **2 tests** in `CalculatorTest` that do not carry the `smoke` tag.

### Static tag filtering in the build script

If every run of a specific task must always execute the same group, you can configure it statically:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'unit'
        excludeTags 'integration'
    }
}
```

This is an **alternative** to the dynamic tag setup in Section 2, not something to append after it. Combining static filters with passed project properties can narrow the test set unpredictably. For developer and CI suites, dynamic `-PincludeTags` from Section 2 makes it obvious which group is running.

**Common pitfall:** Gradle does not support `./gradlew test --tag smoke` out of the box. `-PincludeTags=smoke` works here **because** build script code wires that project property into `useJUnitPlatform`; it is not a built-in Gradle tag-filtering option.

## 7. Combining class/method selection and tags

Sometimes you want to run only the smoke tests of one class:

```bash
./gradlew test --tests "CalculatorTest" -PincludeTags=smoke
```

**Expected: 1 test** — `CalculatorTest.addsTwoNumbers`.

A command that looks plausible yet matches nothing:

```bash
./gradlew test --tests "GreetingFormatterTest.rejectsBlankName" -PincludeTags=smoke
```

`rejectsBlankName` only has the `contract` tag, so **no test satisfies both filters**. With Gradle's filtering, this can fail the task for finding no matching tests, depending on `failOnNoMatchingTests`. Never interpret "0 tests" as confirming correct functionality.

In Gradle, multiple `--tests` patterns combine with OR, and JUnit Platform tag filters further narrow that set:

```text
Tests executed
= matches at least one --tests filter (if given)
  AND satisfies includeTags expression (if given)
  AND does not satisfy excludeTags expression (if given)
  AND is not skipped by @Disabled / execution conditions
```

For instance, "all `smoke` tests across the repository" is a **tag** filter; "all tests in `CalculatorTest`" is a **class** filter; "`addsTwoNumbers`" is a **method** filter. Pick the filter matching your intent instead of stacking unnecessary conditions.

## 8. Comparing with Maven Surefire in a Spring Boot project

If the project uses Maven, test selection is handled by the **Maven Surefire Plugin**. The commands below assume `pom.xml` configures JUnit Jupiter via `spring-boot-starter-test` or suitable JUnit dependencies, using a Surefire version that supports JUnit Platform (e.g., Surefire 3.x).

| Goal | Equivalent Maven command |
| --- | --- |
| Run all tests | `./mvnw test` |
| Run one class | `./mvnw -Dtest=CalculatorTest test` |
| Run one class by full name | `./mvnw -Dtest=com.example.testing.CalculatorTest test` |
| Run one method | `./mvnw "-Dtest=CalculatorTest#addsTwoNumbers" test` |
| Run `smoke` tag | `./mvnw -Dgroups=smoke test` |
| Run tag expression | `./mvnw '-Dgroups=unit & !smoke' test` |
| Exclude `smoke` tag | `./mvnw -DexcludedGroups=smoke test` |

`-Dtest` is **Surefire's** test class/method filter, where `#` separates class and method. It **differs** from Gradle's dot notation in `--tests "Class.method"`.

Surefire's `groups` and `excludedGroups` on JUnit Platform filter tags/tag expressions; they are **not** Spring `@Profile`s. On Windows PowerShell/cmd, double-quote expressions:

```powershell
.\mvnw.cmd "-Dgroups=unit & !smoke" test
```

Maven Surefire discovers test classes by default patterns such as `*Test`, `*Tests`, `Test*`, and `*TestCase`. The example classes `CalculatorTest` and `GreetingFormatterTest` match. If the project customizes includes/excludes, follow the actual configuration.

When a project separates integration tests into **Maven Failsafe** (`integration-test`/`verify`), `mvn test` does not execute the Failsafe lifecycle; use the corresponding lifecycle goals and filters. Similarly in Gradle, a custom `integrationTest` task is not automatically part of the `test` task.

## 9. When a real app uses Spring Boot Test

The examples above intentionally used plain Java tests. In Spring Boot, the exact same selection mechanisms apply:

```java
package com.example.testing;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@Tag("integration")
class ApplicationStartupTest {
    @Test
    void contextLoads() {
        // PASSES when Spring Boot ApplicationContext initializes successfully.
    }
}
```

This is an **example snippet to add to a Spring Boot project that has `@SpringBootApplication`**; it does not run standalone in the minimal Java project from Section 2. Once this class is in a Boot application, you can select it:

```bash
./gradlew test --tests "ApplicationStartupTest"
./gradlew test -PincludeTags=integration
```

These commands choose **which tests execute**; they do not change the size of the Spring context. Running a single method inside a `@SpringBootTest` class may still initialize the `ApplicationContext` and its dependencies. Do not assume running one method is always instantaneous; the main difference is **the number of selected tests**.

With `@WebMvcTest` or `@DataJpaTest`, tags only filter which tests run; they do not turn a slice test into a full integration test. With Testcontainers, a selected test may still start containers and require Docker/a compatible container runtime. When a test is excluded by tag, its own setup cost usually does not occur in that run, though shared hooks/contexts for other selected tests may still initialize.

**Practical tagging:** put `@Tag("integration")` on the class if **every method** is an integration test; put it on individual methods if only some belong to that group. A class-level tag is not merely decorative — it affects all test methods in that class during filtering.

## 10. How to verify the filter actually worked properly

After running a command, check three things:

1. **Right task:** did you run `test`, `integrationTest`, or the module's corresponding task?
2. **Executed test count and names:** did they match the target, or did you accidentally run too many or zero tests?
3. **Outcome:** did executed tests PASS or FAIL? If tests were SKIPPED, why?

In Gradle, common report files:

```text
build/reports/tests/test/index.html
build/test-results/test/TEST-*.xml
```

With Maven Surefire:

```text
target/surefire-reports/
```

These are default paths inside the running module; multi-module projects, custom configurations, or other test tasks may use different paths. HTML/XML reports verify exactly which methods ran; never glance solely at `BUILD SUCCESSFUL` or `BUILD SUCCESS` and assume the whole suite was verified.

### Expected result table for the Section 2 example

| Gradle command (abbreviated after `./gradlew`) | Expected test count |
| --- | ---: |
| `test` | 5 |
| `test --tests "CalculatorTest"` | 3 |
| `test --tests "CalculatorTest.addsTwoNumbers"` | 1 |
| `test -PincludeTags=smoke` | 2 |
| `test -PincludeTags=unit` | 3 |
| `test '-PincludeTags=unit & !smoke'` | 2 |
| `test '-PincludeTags=smoke \| contract'` | 3 |
| `test -PexcludeTags=smoke` | 3 |
| `test --tests "CalculatorTest" -PincludeTags=smoke` | 1 |

These counts are based on **these exact five methods**, assuming test code compiles, JUnit Platform is enabled, and no other filters are active. When adding or changing tags/test methods, update expectations for the actual test set.

### Common errors and how to handle them

**`No tests found for given includes` / "0 tests"**

- Verify the class and package name; use the fully qualified name to rule out ambiguity.
- Verify the test is in `src/test/java`, JUnit Jupiter is on the classpath, and the task uses `useJUnitPlatform`.
- Check `@Test` and the real method name; `@DisplayName` can differ from the method name.
- If combining `--tests` and `includeTags`, verify their intersection is non-empty.
- Check whether the class is excluded by configuration, marked `@Disabled`, or belongs to another task/source set.

**Added `@Tag("smoke")` yet `./gradlew test` still runs the whole suite**

This is expected behavior: `@Tag` is only a label. You need `useJUnitPlatform { includeTags 'smoke' }` or the dynamic `-PincludeTags=smoke` setup as shown in the example.

**Typed `./gradlew test -PincludeTags=smoke` yet the whole suite still runs**

Check that `build.gradle` actually reads `includeTags` and passes it into `useJUnitPlatform`. A project property by itself does not control JUnit unless wired into the build script.

**Typed `--tests "Class#method"` out of Maven habit**

Gradle uses `Class.method`; Maven Surefire uses `-Dtest=Class#method`. The two filters use different syntax.

**Tag expression containing `&`, `|`, or `!` gets split by the shell**

Quote the entire `-PincludeTags=...` argument appropriately for your shell. In Maven, similarly quote `-Dgroups=...` whenever it contains spaces or operators.

**Running one test still takes a long time**

Check whether the test uses `@SpringBootTest` or external containers/DBs; selecting one method does not eliminate the startup cost needed for the context, container, Gradle build, and fixtures.

**Tests PASS yet CI skipped an important group**

Class/method filters are great for local debugging; full CI checks must run the full suite or complementary groups. Ensure `includeTags 'smoke'` was not accidentally left hardcoded on the `test` task.

**Tests show as skipped without a clear reason**

Distinguish three states: **not selected** (discovery filter), **disabled/skipped** (`@Disabled`, assumptions, conditions), and **executed and FAILED** (assertion/exception). Reports and test logs confirm which occurred.

## 11. Self-check practice exercises

With the 5-method suite, perform these steps in order:

1. Run all of `CalculatorTest` and predict the 3 method names that will appear.
2. Run only `GreetingFormatterTest.formatsGreeting`; confirm only 1 test runs.
3. Run the `smoke` group; confirm the two tests reside **in two different classes**.
4. Run `unit & !smoke`; explain why `addsTwoNumbers` is excluded even though the class has the `unit` tag.
5. Run `--tests "CalculatorTest"` combined with `-PincludeTags=smoke`; predict exactly 1 test.
6. Add `@Tag("smoke")` to `rejectsBlankName`, rerun the `smoke` group, and confirm the count increases from 2 to **3**.

These exercises require only changing annotations and rerunning tests; no Spring context or database is needed to understand filtering mechanics.

## 12. Takeaways for applying in projects

- **One class:** `./gradlew test --tests "package.ClassTest"`.
- **One method:** `./gradlew test --tests "package.ClassTest.methodName"`.
- **One tag group:** apply `@Tag` and use `useJUnitPlatform { includeTags ... }`; to control via CLI, map a project property like `-PincludeTags=smoke`.
- **Maven:** `-Dtest=ClassTest`, `-Dtest=ClassTest#methodName`, and `-Dgroups=smoke` with Surefire/JUnit Platform.
- **Combining filters:** tests must satisfy both class/method patterns and tag expressions, so always verify the count in the report.
- **Spring Boot:** test selection is still governed by Gradle/Maven and JUnit Platform; `@SpringBootTest`/slice annotations govern the Spring environment once a selected test actually runs.

Official references for usage details and version changes:

- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html) (Test filtering; Test grouping).
- [JUnit 5 User Guide — Tagging and Filtering / Tags](https://docs.junit.org/5.10.2/user-guide/index.html).
- [Maven Surefire — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html).
