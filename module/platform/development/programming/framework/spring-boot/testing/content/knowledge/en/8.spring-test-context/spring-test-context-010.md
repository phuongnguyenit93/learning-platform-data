# Distinguishing Context Load Errors from Assertion or Business Errors in Spring TestContext

## 1. Problem to Solve

In a Spring Boot project, Maven/JUnit can report `BUILD FAILURE` in all cases, yet the root causes and fixes differ greatly:

1. **Spring context load errors**: Spring failed to create the `ApplicationContext` or prepare the test instance; the `@Test` method may **never have run**.
2. **Assertion errors**: the test check ran and the actual result did not match expectations; typically `AssertionFailedError` from JUnit or `AssertionError` from AssertJ/MockMvc.
3. **Business errors / exceptions during application code execution**: service, controller, or repository code threw an exception while the test executed. This may be **correct behavior** if the exception was expected and checked with `assertThrows`, or an **actual bug** if unexpected.

A line reading `Tests run: 3, Failures: 1, Errors: 1` is only an initial signal. **Test runner `Failures`/`Errors` buckets are not an absolute root-cause classification**: a business bug can surface as an assertion failure; a business exception thrown inside `@PostConstruct` can make context loading fail; and a setup bug inside `@BeforeEach` is not necessarily a Spring context load failure.

This lesson focuses on identifying the **phase of failure**, the **root exception**, and the **contract under test**. Examples use Java 17+, Spring Boot 3.5.16, JUnit Jupiter, Mockito, and Spring TestContext. The techniques apply to both `@SpringBootTest` and slice tests like `@WebMvcTest`/`@DataJpaTest`, once the right test boundary is chosen.

## 2. Lifecycle Map of a Spring Test

A `@SpringBootTest` using JUnit Jupiter typically follows these steps (exact order can depend on extensions/listeners and configuration):

```text
Maven Surefire / Gradle Test / IDE
          |
          v
Discover test classes and test methods
          |
          v
JUnit Jupiter + SpringExtension
          |
          v
Spring TestContext prepares test instance
          |
          +-- Locate config (@SpringBootTest, @ContextConfiguration)
          |   Select profiles, property sources, context customizers
          |
          +-- Load / retrieve cached ApplicationContext
          |   Bean definitions, auto-configuration, bean creation,
          |   dependency injection, @PostConstruct, DB/Broker setup...
          |
          +-- Inject @Autowired / @MockitoBean into test
          |
          v
@BeforeEach and pre-method callbacks
          |
          v
@Test: invoke service / controller / repository
          |
          +-- No exception -> run assertions
          +-- Exception caught by assertThrows -> test can PASS
          +-- Unexpected exception -> test ERROR/FAIL per runner
          +-- Failed assertion -> AssertionFailedError / AssertionError
          |
          v
@AfterEach and post-method callbacks
          |
          v
Test results and Surefire/JUnit report
```

**Classify by phase, not merely by exception name:**
- When `ApplicationContext` fails to load, the error usually appears in `SpringExtension`/`TestContextManager.prepareTestInstance`, before the test method body runs.
- When `@BeforeEach` throws `NullPointerException`, the context may already have loaded. That is a *test setup* bug, not automatically a context-load failure.
- When `@Test` throws `IllegalArgumentException` from a service, that is runtime business behavior or a business bug.
- When `assertEquals` sees a different value than expected, that is an assertion failure. The deeper cause may be a business bug, wrong fixture data, timezone, or wrong expected value.
- When `@AfterEach` or cleanup fails, the assertion itself may have PASSED while the overall test still reports an error.

## 3. Quick Identification Table

| Log Signal | Likely Phase | Diagnostic Question |
| --- | --- | --- |
| `Failed to load ApplicationContext` | Loading Spring context / preparing test instance | How is the context configured? What is the lowest meaningful `Caused by`? |
| `Error creating bean with name '...'` | Bean initialization inside context | Which bean lacks a dependency/config or failed in its factory method? |
| `UnsatisfiedDependencyException` / `NoSuchBeanDefinitionException` | Context startup or lazy lookup | Is the bean missing due to component scan, profile, test slice, qualifier, or mock? |
| `Failed to bind properties` / `BindException` | Spring Boot config binding | Are property keys/types/sources/profiles accurate? |
| `ApplicationContext failure threshold ... exceeded` | Subsequent context load attempt skipped | Why did the **first** attempt with the same cache key fail? |
| `org.opentest4j.AssertionFailedError` | JUnit Jupiter assertion | Which expected/actual values diverged? How far did test execution reach? |
| `java.lang.AssertionError` from AssertJ/MockMvc | Assertion / response expectation | Wrong data, status, list order, comparator, or JSON path? |
| `IllegalArgumentException`, custom `BusinessException` from service | Business logic execution | Is the exception part of the contract or unexpected? Does `assertThrows` match class/message? |
| `HttpClientErrorException`/timeout/`DataAccessException` inside `@Test` | Adapter/infrastructure during test execution | Calling a real environment, bad data, or service unavailable? |
| `Exception in @BeforeEach` | Setup before method, after or alongside lifecycle callbacks | Did setup construct objects incorrectly or did context injection fail? |
| `expected: <201> but was: <401>` | HTTP assertion; root cause may be filter/security | Did the request reach the app? Did the security chain return 401? |

Do not diagnose solely from an `Exception` suffix. For instance, `IllegalStateException` can be Spring reporting a failed context load, or a service intentionally throwing when an order is already closed. **Read the stack trace and origin point.**

## 4. Context Load Errors: Mechanics and Signals

### 4.1. Nature of the Failure

Spring TestContext attempts to build an `ApplicationContext` (or fetch a matching one from cache). With `@SpringBootTest`, Spring Boot uses `SpringApplication` to load application configuration. Errors locating configuration, building the bean graph, binding properties, starting embedded infrastructure, or running bean lifecycle hooks can cause this phase to fail.

Typical error chain example:

```text
java.lang.IllegalStateException: Failed to load ApplicationContext
  ...
Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
  Error creating bean with name 'checkoutService'
  ...
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
  No qualifying bean of type '...ShippingGateway' available
```

This is a **simulated log structure excerpt**, not fixed stdout from an example. `Failed to load ApplicationContext` is the outer symptom; the missing `ShippingGateway` bean is the root cause to address.

### 4.2. Common Causes

- Missing dependency: controller/service/repository has no bean due to missing `@Component`/`@Service`/`@Repository`, package scanning, or `@Import`.
- Profile mismatch: bean exists only under `@Profile("prod")` while the test runs `@ActiveProfiles("test")`.
- Slice scope: `@WebMvcTest` intentionally excludes services/repositories; a controller with an unmocked/unimported constructor dependency fails immediately during bean creation.
- Bad config types: `@ConfigurationProperties` binding/validation fails, `@Value("\${...}")` placeholder fails to resolve, invalid URL/port/timeout.
- External dependency unavailable: database, broker, vault, config server, Testcontainers/Docker, credentials, or DNS.
- JPA issues: broken mappings, Hibernate unable to build `EntityManagerFactory`, Flyway/Liquibase migration failure, `DataSource` missing driver.
- Bean lifecycle: `@PostConstruct` or `@Bean` factory method throws an exception itself.
- Multiple beans of the same type without clear `@Primary`/`@Qualifier`, yielding `NoUniqueBeanDefinitionException`.
- Circular dependencies/constructor cycles or duplicate/conflicting context configurations imported.

**Start fixing from the concrete root cause, not by adding `@SpringBootTest`, disabling security, or randomly mocking every bean.** Each workaround changes test scope and invalidates what the test proves.

### 4.3. Spring TestContext Context Cache

Spring reuses successfully loaded contexts sharing the same configuration. Cache keys factor in classes/locations, initializers, active profiles, test property sources, context customizers (bean overrides like `@MockitoBean`), context loaders, and parent contexts.

Since Spring Framework **6.1**, the default **context failure threshold** is **1**. If a cache key already failed to load, subsequent attempts in the same test process may abort immediately:

```text
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for [...]
```

**That is a follow-on error, not the original cause.** Locate the first context failure in the same run and inspect its `Caused by`. Running a single test class in a fresh JVM can surface the original failure since the static cache does not cross processes. You can adjust the threshold via JVM system property `spring.test.context.failure.threshold` using a positive integer, though raising it **does not fix configuration**. Do not use threshold increases as a standard CI fix.

## 5. Assertion Errors: The Test Reached the Comparison Step

### 5.1. Example

```java
int actual = service.total(100, "HCM"); // actual is 110
assertEquals(999, actual);               // intentionally wrong expected value
```

With JUnit Jupiter, `assertEquals(expected, actual)` usually throws `org.opentest4j.AssertionFailedError` when values differ. With AssertJ, `assertThat(actual).isEqualTo(999)` throws `AssertionError` with a diff report. In MockMvc, `andExpect(status().isCreated())` throws an assertion error if the actual response is 200/400/401/500.

Key points:
- **The Spring context already loaded** if the assertion runs on a `@Autowired` Spring service.
- Application logic may have completed, yet its output did not match expectations.
- You cannot tell whether the bug is in the test or production code without checking requirements/contracts.
- Assertion failures can also stem from clock/time differences, unguaranteed collection ordering, mismatched fixtures, leftover database rows, or wrong mock stubs.

### 5.2. Types of Assertion Failures

| Test Code | Signal | Meaning |
| --- | --- | --- |
| `assertEquals(201, response.status())` | expected 201, got 401 | HTTP contract mismatch; inspect security/filters/request |
| `assertThat(items).containsExactly(...)` | list order differs | Does the contract guarantee order? Is there an `ORDER BY`? |
| `assertThrows(IllegalArgumentException.class, () -> service.call())` | no exception thrown | Test expected an exception, yet code returned normally |
| `assertThrows(SomeException.class, ...)` | different exception type thrown | JUnit assertion failed on type mismatch even though code threw |
| `assertThat(result).usingRecursiveComparison().isEqualTo(expected)` | field path differs | Inspect field, comparator, null/ID/timestamp |
| `verify(mock).save(...)` | wanted but not invoked | Mockito verification failure; service did not reach the stubbed/verified mock |

`assertThrows` "turns a valid business exception into PASS" if the exception class matches. Note that `assertThrows` accepts the exact class or any subtype; use `assertThrowsExactly` when the contract demands the exact class without subtypes.

## 6. Business Errors: Expected Exceptions vs. Unexpected Exceptions

A service may specify that negative inputs are invalid:

```java
public int total(int subtotal, String region) {
    if (subtotal < 0) {
        throw new IllegalArgumentException("subtotal must be >= 0");
    }
    // calculate total...
}
```

Three scenarios:

1. **Correct behavior**: the test calls `service.total(-1, "HCM")` inside `assertThrows(IllegalArgumentException.class, ...)`. The test PASSES; the exception is the expected result.
2. **Unhandled business exception**: the test passes a negative value without asserting an exception; JUnit records an error when the method throws. The code may be right while **the test expectation is wrong**.
3. **Business bug**: the test passes valid input yet the service throws `IllegalStateException` or returns the wrong total. This is an SUT behavior bug, surfacing as either an exception or an assertion failure.

Therefore, "business error" describes **a cause in domain/application code**, not a fixed label in test reports. If a business exception is thrown during bean initialization inside `@PostConstruct`, the **observed phase** is context load. Always separate two axes:

| Axis | Question | Example |
| --- | --- | --- |
| **Failure phase** | Failed during context load, setup, test execution, assertion, or cleanup? | Bean could not be constructed before `@Test` |
| **Actual root cause** | Missing config, logic bug, wrong expectation, infrastructure, or test setup? | Wrong DB URL; miscalculated formula; bad fixture |

## 7. Runnable Practice Project: Two Passing Tests and Three Intentionally Failing Exercises

The project includes 2 default passing test classes plus 3 **exercise classes whose names do not match Maven Surefire's default pattern** so they do not break `mvn test`. When targeted explicitly with `-Dtest=...`, each exercise demonstrates one failure type. All Java code uses package `com.example.contextdiag`.

### 7.1. Structure

```text
context-diagnosis-lab/
├── pom.xml
├── src/main/java/com/example/contextdiag/
│   ├── ContextDiagnosisApplication.java
│   ├── TaxPolicy.java
│   ├── FixedTaxPolicy.java
│   └── PriceService.java
└── src/test/java/com/example/contextdiag/
    ├── PriceServiceUnitTest.java
    ├── PriceServiceSpringTest.java
    ├── BrokenContextExercise.java
    ├── WrongAssertionExercise.java
    └── UnhandledBusinessExceptionExercise.java
```

### 7.2. Maven POM

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>context-diagnosis-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
```

The Spring Boot parent manages dependencies and Maven test tooling. No web server or SQL is needed for this example; the Spring context failure is created via an intentionally missing dependency.

### 7.3. Main Code

`src/main/java/com/example/contextdiag/ContextDiagnosisApplication.java`

```java
package com.example.contextdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextDiagnosisApplication.class, args);
    }
}
```

`src/main/java/com/example/contextdiag/TaxPolicy.java`

```java
package com.example.contextdiag;

public interface TaxPolicy {
    int percent(String region);
}
```

`src/main/java/com/example/contextdiag/FixedTaxPolicy.java`

```java
package com.example.contextdiag;

import org.springframework.stereotype.Component;

@Component
public class FixedTaxPolicy implements TaxPolicy {
    @Override
    public int percent(String region) {
        return 10;
    }
}
```

`src/main/java/com/example/contextdiag/PriceService.java`

```java
package com.example.contextdiag;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    private final TaxPolicy taxPolicy;

    public PriceService(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }

    public int total(int subtotal, String region) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
        return subtotal + subtotal * taxPolicy.percent(region) / 100;
    }
}
```

Integer math is used only for illustration. Production code must account for overflow, rounding, and monetary representation using `BigDecimal` or minor units per domain rules. With subtotal 100 and 10% tax, the exact result is `110`. With a negative subtotal, the service throws `IllegalArgumentException` before calling the policy.

### 7.4. PASS Test #1: Unit Test Without Spring

`src/test/java/com/example/contextdiag/PriceServiceUnitTest.java`

```java
package com.example.contextdiag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PriceServiceUnitTest {
    @Mock
    TaxPolicy taxPolicy;

    @Test
    void totalsExpectedPercentage() {
        when(taxPolicy.percent("HCM")).thenReturn(10);
        PriceService service = new PriceService(taxPolicy);

        assertEquals(110, service.total(100, "HCM"));
    }

    @Test
    void rejectsNegativeSubtotal() {
        PriceService service = new PriceService(taxPolicy);

        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> service.total(-1, "HCM"));

        assertEquals("subtotal must be >= 0", ex.getMessage());
        verifyNoInteractions(taxPolicy);
    }
}
```

This test proves calculation rules and input validation. It starts no Spring context; therefore, if an assertion fails here, **do not look for Spring component scan bugs**.

### 7.5. PASS Test #2: Spring Context Loads Successfully, Real Logic Runs

`src/test/java/com/example/contextdiag/PriceServiceSpringTest.java`

```java
package com.example.contextdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class PriceServiceSpringTest {
    @Autowired
    PriceService priceService;

    @Test
    void usesRealSpringBeanGraph() {
        assertEquals(110, priceService.total(100, "HCM"));
    }

    @Test
    void expectedBusinessExceptionIsNotTestFailure() {
        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> priceService.total(-1, "HCM"));

        assertEquals("subtotal must be >= 0", ex.getMessage());
    }
}
```

Here `@SpringBootTest` locates `@SpringBootApplication` in the package and creates a context containing `PriceService` and `FixedTaxPolicy`. `@Autowired` works and both assertions PASS. Asserting the right exception type is still a **passing test**, not "a test error occurred."

### 7.6. FAIL Exercise #1: Context Load Error Before the Test Body Runs

`src/test/java/com/example/contextdiag/BrokenContextExercise.java`

```java
package com.example.contextdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.fail;

@SpringBootTest(classes = BrokenContextExercise.BrokenConfig.class)
class BrokenContextExercise {

    interface MissingPort {}

    static class BrokenService {}

    @Configuration(proxyBeanMethods = false)
    static class BrokenConfig {
        @Bean
        BrokenService brokenService(MissingPort missingPort) {
            return new BrokenService();
        }
    }

    @Autowired
    BrokenService brokenService;

    @Test
    void bodyCannotRunIfContextFails() {
        fail("If you see this line, the context loaded successfully");
    }
}
```

Because `@SpringBootTest(classes=...)` specifies `BrokenConfig` directly, Spring tries to build `BrokenService` from the `@Bean` method, yet no `MissingPort` bean exists. Parameter resolution fails during context loading, typically with `UnsatisfiedDependencyException` caused by `NoSuchBeanDefinitionException`. **The test method is never called**, so `fail("...")` is not the cause of the observed failure.

What to spot in the stack trace:
- Outer frame may be `IllegalStateException: Failed to load ApplicationContext`.
- Middle frame identifies `Error creating bean with name 'brokenService'`.
- Root cause identifies no qualifying bean of type `MissingPort`.
- Do not try to fix it by changing expected assertions because execution never reached assertions.

**This is an intentionally failing exercise.** Do not include it in normal CI without an automated mechanism asserting the expected failure.

### 7.7. FAIL Exercise #2: Context Succeeds, Assertion Fails

`src/test/java/com/example/contextdiag/WrongAssertionExercise.java`

```java
package com.example.contextdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class WrongAssertionExercise {
    @Autowired
    PriceService priceService;

    @Test
    void expectedValueIsIntentionallyWrong() {
        int actual = priceService.total(100, "HCM");

        assertEquals(999, actual); // expected 999, actual 110
    }
}
```

`PriceService` and `FixedTaxPolicy` are fully wired; the context loads and `@Test` reaches `assertEquals`. The expected failure is `AssertionFailedError` with 999 vs. 110. **Do not** tweak component scanning or the TestContext failure threshold. Compare requirements to fix either the expected value or the service; in this exercise, 999 is intentionally wrong.

### 7.8. FAIL Exercise #3: Business Exception Unhandled by the Test

`src/test/java/com/example/contextdiag/UnhandledBusinessExceptionExercise.java`

```java
package com.example.contextdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class UnhandledBusinessExceptionExercise {
    @Autowired
    PriceService priceService;

    @Test
    void doesNotDeclareExpectedException() {
        priceService.total(-1, "HCM");
    }
}
```

The context loads; `@Test` calls the service; the service throws `IllegalArgumentException("subtotal must be >= 0")`; without `assertThrows`, JUnit treats it as an unhandled exception. Some test runner reports list it under `Errors`. **It is not a context error.** If "reject negative subtotal" is the intended contract, fix the test using `assertThrows` as in PASS Test #2; do not alter production code to swallow the exception.

### 7.9. Running Each Case Explicitly

In the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
# Default runs the two *Test classes: all PASS
mvn -q clean test

# Run each exercise individually whose name does not match default *Test patterns:
mvn -Dtest=BrokenContextExercise test
mvn -Dtest=WrongAssertionExercise test
mvn -Dtest=UnhandledBusinessExceptionExercise test
```

Maven Surefire by default matches class names like `Test*`, `*Test`, `*Tests`, and `*TestCase`. The three classes ending in `Exercise` are skipped by a regular `mvn test` but can be selected with `-Dtest=ClassName`. Run **each exercise separately** because each command is designed to return a non-zero exit code. Afterward, `mvn -q clean test` still PASSES.

| Command | Context | `@Test` Method | Expected Result |
| --- | --- | --- | --- |
| `mvn -q clean test` | Unit needs none; Spring test loads | Yes | Exit code 0; tests PASS |
| `-Dtest=BrokenContextExercise` | **FAILS** creating `BrokenService` | No | `Failed to load ApplicationContext` + cause missing `MissingPort` |
| `-Dtest=WrongAssertionExercise` | PASS | Yes | `AssertionFailedError` due to expected 999, actual 110 |
| `-Dtest=UnhandledBusinessExceptionExercise` | PASS | Yes, throws exception | `IllegalArgumentException` from `PriceService.total` |

Exact full output depends on Maven Surefire, JDK, and library versions. The table describes **the expected failure categories**, not a verbatim full stack trace. Reports can be inspected under `target/surefire-reports` in each test class's report file.

## 8. Method for Finding Root Causes in Stack Traces

An effective debugging approach traces **outer error → `Caused by` chain → most specific actionable cause**.

### 8.1. Read the Top Line Without Stopping There

Example:

```text
IllegalStateException: Failed to load ApplicationContext
    at ...
Caused by: BeanCreationException: Error creating bean 'dataSource'
    at ...
Caused by: IllegalArgumentException: Could not resolve placeholder 'DB_URL'
```

Stopping at `IllegalStateException` misses the real configuration error: missing `DB_URL`. Not every deepest `Caused by` is self-explanatory; pick **the first exception carrying actionable information** and read the stack frames around it.

Search reports/logs for keywords:
- `Failed to load ApplicationContext`, `Error creating bean`, `UnsatisfiedDependencyException`.
- `Caused by:`, `No qualifying bean`, `Failed to bind properties`, `ConnectException`, `Access denied`.
- `expected:`, `but was:`, `ComparisonFailure`, `AssertionFailedError`.
- Class/method names in your application package (`PriceService.java:...`), not only Spring internal frames.

### 8.2. Determine Whether the Test Method Ran

Use a breakpoint or a temporary debug statement inside the method body (without leaving it in production code). If the test body **was never entered** and the log reports context load failure, focus on Spring configuration and the bean graph. If the body ran and an assertion failed, compare actual vs. expected. If the body ran and threw an exception, inspect the offending method and inputs.

One caveat: a test can fail **before its body** inside `@BeforeEach`, parameter resolution, or an extension even though the Spring context loaded. Thus, seeing that the body did not run **is not enough** to conclude the context failed: always read the stack trace.

### 8.3. Do Not Rely Solely on `Failures`/`Errors` Columns

Many test runners classify `AssertionError` as a `failure` and any other exception as an `error`. Yet:
- A service exception caught by a matching `assertThrows` → PASS.
- A service bug returning the wrong number → assertion failure.
- A Spring context error throwing an exception → usually error.
- An `AssertionError` thrown by custom init code inside a bean → can fail context loading.
- A `Mockito.verify` mismatch → assertion-like failure.

Runner categories help **triage**, not replace phase + root-cause analysis.

## 9. 8-Step Diagnostic Workflow

1. **Re-run a single class:** target the failing test with `mvn -Dtest=ClassName test` or Gradle `--tests fully.qualified.ClassName`; record exact command, JDK, profile, and environment.
2. **Identify the phase:** compilation error, context loading, setup, test execution, assertion, or cleanup?
3. **If context loading failed:** find the **first** failure for that context key and the most informative `Caused by`; inspect configs, beans, profiles, drivers, migrations, and ports.
4. **If an assertion failed:** compare expected/actual against the contract; check fixtures, mock behavior, clocks/timezones, numeric types, and list ordering.
5. **If an exception occurred during app code:** check the first stack frame in project source, actual inputs, exception type, and `assertThrows`.
6. **Narrow the surface area:** run unit tests without Spring for pure Java logic; `@WebMvcTest` for HTTP; `@DataJpaTest` or DB integration for SQL; full context only when wiring requires it.
7. **Fix at the right layer:** config/beans for context failures; code/expectations for assertion mismatches; inputs/exception contracts/infrastructure for business errors.
8. **Re-run the test and related suite:** confirm no new failures were introduced via profiles, context caching, test order, or leaked test data.

If repeated runs produce inconsistent results, investigate isolation/flakiness: static state, files, DB records, ports, clocks, test ordering, shared mocks, or Testcontainers lifecycles.

## 10. Real-World Spring Boot Scenarios and How to Read Them

### 10.1. `@WebMvcTest` Reports a Missing Service Bean

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired MockMvc mvc;
}
```

If `OrderController` requires `OrderService` via constructor and the slice excludes `OrderService`, Spring can throw `UnsatisfiedDependencyException` while creating the controller. **This is a slice context load error**, not an HTTP assertion error. You can resolve it with:

```java
@MockitoBean
OrderService orderService;
```

Snippets in this section are **illustrative**, because `OrderController` and `OrderService` belong to a concrete project. In Spring Framework 6.2/Spring Boot 3.5, import `org.springframework.test.context.bean.override.mockito.MockitoBean`. If you want to test the real service alongside the controller, consider `@Import` or a broader scope instead of mocking the service.

However, if the `MockMvc` request executes and returns `404` due to a wrong mapping, causing `andExpect(status().isOk())` to fail, that is an **assertion failure** even though the root bug lies in web configuration. The difference lies in the **detection phase**.

### 10.2. Database Fails to Connect

- If `DataSource`/`EntityManagerFactory` initializes eagerly in the context, driver/config/migration failures can break `@SpringBootTest` or `@DataJpaTest` before the test body.
- If connections open *lazily* only when a repository query executes, the test can load the context successfully and then throw `DataAccessException`/SQL exceptions inside `@Test`.
- The same bad URL can surface in different phases depending on lifecycle. Never classify solely by error category.

When a JPA test fails, check drivers, connection URLs, secrets/env, transactions, schema migrations, Testcontainers, and database engine. Passing on H2 does not prove PostgreSQL queries, indexes, or constraints match production.

### 10.3. `@ConfigurationProperties` and Unresolved Placeholders

```text
Failed to bind properties under 'app.timeout' to java.time.Duration
Caused by: ...
```

If the config bean is created during context load, this is a config/context failure. Fix the property value, type/format, validation, or active profiles. Do not edit assertions since test code has not executed yet.

### 10.4. Security Returns 401/403

In `@WebMvcTest` with Spring Security on the classpath, the filter chain typically participates in tests. Unauthenticated requests may be rejected with 401/403 before reaching the controller. When `MockMvc` asserts 200 and gets 401, the test failure is a status assertion mismatch. Check security configuration or missing principal/CSRF token on the test request. Use Spring Security Test support with `@WithMockUser` or request post-processors per the contract; do not disable all filters just to turn tests green.

### 10.5. Assertions on JSON/Collections

```java
mockMvc.perform(get("/orders"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[0].id").value(12));
```

This illustrates a test with `MockMvc` injected and `get`/`status`/`jsonPath` DSL imported. If the API does not guarantee ordering, hardcoding `[0]` causes assertion failures even when the app works properly. Change the assertion to match meaningful result sets/IDs, or add sort parameters/`ORDER BY` if order is part of the contract.

### 10.6. Business Exceptions Mapped to HTTP Status by a Controller

The service throws `OrderClosedException`, which `@RestControllerAdvice` translates to HTTP 409. At the **service test** boundary, use `assertThrows(OrderClosedException.class, ...)`. At the **MVC test** boundary, assert `status().isConflict()` and error JSON. Do not expect `assertThrows(OrderClosedException.class)` on an HTTP call if the framework already caught and mapped the exception into an HTTP response.

### 10.7. Mocking in the Wrong Place

Mockito's `@Mock Repository` creates a mock field in the test; it does not replace the Spring `Repository` bean automatically. If the `@Autowired` service still uses the real repository, calls may hit the DB or fail context startup over datasource settings. In Spring TestContext when a collaborator must be mocked, use `@MockitoBean` for that bean; in plain Java unit tests, inject `@Mock` via the service constructor. When verifying JPA mappings, **do not mock the repository itself**.

## 11. Observing at the Right Level with Tooling

### 11.1. Maven Surefire

```bash
mvn -Dtest=PriceServiceSpringTest test
mvn -Dtest=BrokenContextExercise test
```

The second command intentionally fails. Inspect `target/surefire-reports/*.txt` or the corresponding XML files; check `Caused by` and the failing method. Add `-e`/`-X` for **Maven lifecycle/plugin errors** when needed, though Maven debug output is noisy and no substitute for Spring's root-cause trace.

### 11.2. Gradle

For a Gradle project with a `test` task:

```bash
./gradlew test --tests "com.example.contextdiag.PriceServiceSpringTest"
./gradlew test --stacktrace
./gradlew test --info
```

`--stacktrace` exposes exceptions from Gradle/plugins; the test framework keeps its own reports/console output. On Windows use `gradlew.bat`. These Gradle commands are **illustrative**; the sample project in Section 7 uses Maven and has no `build.gradle`.

### 11.3. Spring Condition Evaluation

When auto-configuration is involved, enable the condition evaluation report per Spring Boot docs—for example running with `--debug` or setting `debug=true` in appropriate test config. The report reveals which `@ConditionalOnClass`/`@ConditionalOnBean`/`@ConditionalOnProperty` conditions matched or did not match. **Unmatched conditions are not always errors**; focus only on missing beans needed by the test.

To inspect caching without excessive noise, selectively enable DEBUG logging for `org.springframework.test.context.cache` to view cache statistics and spot duplicate context creations. Never enable full DEBUG logging in production and commit logs containing secrets.

### 11.4. Context Failure Threshold

`spring.test.context.failure.threshold` defaults to 1 in Spring Framework 6.1+; documentation describes setting it via a positive JVM system property. For example:

```bash
mvn -Dtest=BrokenContextExercise -Dspring.test.context.failure.threshold=2 test
```

Whether Maven/Surefire forwards a system property to the forked test JVM depends on build configuration; if needed, configure Surefire's `systemPropertyVariables`/`argLine`. A value of 2 only retries loading within the same cache key across multiple attempts—**it does not fix missing beans**. In the sample project with only one attempt against the broken context, changing this value may not alter the log output.

### 11.5. `@DirtiesContext` Is Not a Cure-All

`@DirtiesContext` marks the used context for eviction/recreation when appropriate. It is useful if a test corrupts bean definitions or application context state affecting later tests. It does not help Spring instantiate missing beans or resolve broken properties. Overusing it slows the suite and can mask test isolation flaws.

## 12. Distinguishing Exceptions and Statuses in CI Reports

When reviewing a CI failure, capture at least four details (and ideally reproduction/verification):

| Item | Example | Diagnostic Value |
| --- | --- | --- |
| **Test ID** | `BrokenContextExercise#bodyCannotRunIfContextFails` | Identifies the test/class |
| **Phase** | `context initialization` | Isolates configuration before test method |
| **Observed exception** | `UnsatisfiedDependencyException -> NoSuchBeanDefinitionException` | Points to the missing dependency |
| **Expected contract** | Should a `MissingPort` bean exist or is it intentionally absent? | Guides config/fixture fix |
| **Reproduction** | `mvn -Dtest=BrokenContextExercise test` | Independent reproduction |
| **Verification** | Context loads / assertions pass / DB state valid | Proves the root cause was fixed |

By contrast:
- `WrongAssertionExercise`: `phase=assertion`, `observed=AssertionFailedError`, `expected=999`, `actual=110`. Fix the expectation in the exercise.
- `UnhandledBusinessExceptionExercise`: `phase=test method`, `observed=IllegalArgumentException`, `contract=reject negative subtotal`. Add `assertThrows` if this is the expected outcome.
- If the service returns 110 while product requirements specify 120, the test asserting 120 is **right** and the business code is wrong; do not change expected to 110 just to turn it green.

## 13. Common Diagnostic Mistakes

| Mistake | Why It Is Wrong | How to Handle It |
| --- | --- | --- |
| Seeing `IllegalStateException` and immediately blaming context failure | Business services can also throw `IllegalStateException` | Read stack frames and phase |
| Seeing `@Test` never ran and assuming context failed | `@BeforeEach`/parameter resolvers can also fail | Read trace and lifecycle callbacks |
| Seeing `Tests run:..., Errors:1` and blaming Spring | Uncaught exceptions inside test methods are also reported as errors | Find the first meaningful application frame |
| Trying to "fix" `Failed to load ApplicationContext` directly | It is usually just a wrapper | Trace down to `Caused by` bean/config/Hikari/migration |
| Looking only at `failure threshold exceeded` | An earlier run with the same cache key already failed | Find the initial context error or run the class standalone |
| Switching every test to `@SpringBootTest` | Inflates context/infrastructure without fixing logic | Use unit/slice tests matching boundaries |
| Mocking all dependencies when context fails | Can mask genuinely missing production beans | Inspect which beans belong to the boundary; use `enforceOverride=true` when appropriate |
| Disabling security/filters to turn 401 into 200 | Hides policy instead of testing the contract | Add proper authentication/CSRF or fix endpoint policy |
| Changing expected to match actual just to pass | Can legitimize a business bug | Verify against requirements and edge cases |
| Removing `assertThrows` because an exception looks scary | The exception may be the API contract | Assert the exact class/message and side effects |
| Relying on `@DirtiesContext` to make every test PASS | Slows caching, fixes neither config nor external data | Isolate fixtures and clean up properly |
| Raising context failure threshold for CI | Retries a known broken context load | Fix root cause; threshold is only a diagnostic aid |
| Running only in the IDE, skipping Maven/Gradle | Profiles/classpath/working directory differ from CI | Reproduce with the real build and environment config |
| Seeing `BeanCreationException` and editing a random bean | The reported bean may depend on a deeper layer | Follow the dependency chain and direct root cause |

## 14. Pre-Bug-Report Checklist

- [ ] Do I know whether the test runs with **plain JUnit**, a Spring slice, or `@SpringBootTest`?
- [ ] Did the exception occur during context loading, test setup, test body, assertion, or cleanup?
- [ ] Is there `Failed to load ApplicationContext` and a `Caused by` chain? Did I read the deepest actionable cause?
- [ ] Is there a `failure threshold exceeded` message? Did I find **the initial failure sharing that cache key**?
- [ ] Did the test body execute? If not, did I rule out `@BeforeEach`/extension errors?
- [ ] If an assertion failed, did I compare the contract against expected/actual and fixtures rather than tweaking numbers to pass?
- [ ] If a service threw an exception, is it expected behavior needing `assertThrows` or an actual bug?
- [ ] If `@WebMvcTest` lacks a bean, did I distinguish an intentionally excluded slice dependency from missing production config?
- [ ] If JPA/DB failed, did the connection happen at context initialization or during a query inside the test?
- [ ] If HTTP failed with 401/403/404/500, did I inspect security, mappings, exception handlers, and response status?
- [ ] If mocking, did the test actually wire the mock into the right Spring/Java object graph?
- [ ] Did I reproduce with a single exact command, noting JDK/Boot/profile/test class?
- [ ] After fixing, did I re-run the failing case and related suite without hiding risks?

**Guiding principle:** a context-load failure means **the Spring environment for the test was not assembled successfully**; an assertion failure means **a test expectation did not match observation**; a business exception means **application code signaled a condition or failed at runtime**. Distinguishing the phase of occurrence from the root cause leads you straight to the right layer to fix.

## 15. Official Documentation

- Spring Framework 6.2 — TestContext Framework: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework.html
- Spring Framework 6.2 — Context Failure Threshold: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html
- Spring Framework 6.2 — Context Caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Testing how-to: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- JUnit Jupiter 5.11 — Assertions and assertThrows: https://docs.junit.org/5.11.4/user-guide/
- Maven Surefire — Selecting tests: https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html
