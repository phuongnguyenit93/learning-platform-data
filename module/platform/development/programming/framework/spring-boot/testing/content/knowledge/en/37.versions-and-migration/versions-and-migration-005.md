# `@MockBean`, `@SpyBean`, and Migrating to `@MockitoBean`, `@MockitoSpyBean`

## 1. Problem and Objectives

A Spring Boot application has `CheckoutService` using two dependencies: `StockGateway` (which may call an external inventory service) and `PricePolicy` (which calculates totals). In an integration test, you want to run the **real service inside the Spring `ApplicationContext`** while replacing `StockGateway` with a Mockito mock; in another test, you want to **spy** on `PricePolicy`, keeping the real method when unstubbed while counting invocations or intentionally overriding one result. When upgrading Spring Boot, the annotations used to override Spring beans also change.

In **Spring Boot 3.3.5**, you use:
- `org.springframework.boot.test.mock.mockito.MockBean`
- `org.springframework.boot.test.mock.mockito.SpyBean`

Starting in **Spring Boot 3.4.0**, the old API was **deprecated** in favor of Spring Framework 6.2:
- `org.springframework.test.context.bean.override.mockito.MockitoBean`
- `org.springframework.test.context.bean.override.mockito.MockitoSpyBean`

According to the Spring Boot 4.0 migration guide, **Boot 4 removed** the legacy `@MockBean` and `@SpyBean`; you can no longer import them as before. Migrating is not just a rename: target selection, scope, annotation placement, default behavior, and context cache keys all have differences. This lesson provides **two independent Gradle projects** demonstrating the same business logic across both annotation generations while avoiding mixing Spring Framework versions. <Cite> Version conclusions are stated in the official references in the final section.

**Parent context:** *Versions and Migration* — Spring Boot testing.

**Learning objectives:**

1. Distinguish plain Mockito object mocks/spies from **Spring-managed mock/spy bean overrides**.
2. Choose the right annotation and imports for Boot 3.3, Boot 3.4/3.5, and Boot 4.
3. Understand `REPLACE_OR_CREATE`, `REPLACE`, and `WRAP`, including `enforceOverride=true`.
4. Distinguish mocks returning default values, stubbed mocks, spies invoking real methods, and stubbed spies.
5. Know how `Mockito.doReturn`/`doThrow` on a spy avoids invoking the real method during stubbing.
6. Identify when type, `name`, `@Qualifier`, and field-name fallback select the wrong bean.
7. Never copy `@MockBean` placed inside a `@Configuration` class directly to `@MockitoBean`.
8. Understand singleton scope, bean cardinality, `FactoryBean`, AOP proxies, and TestContext cache implications.
9. Understand Mockito reset `AFTER` and why mock resets do not reset state outside Spring.
10. Build **Java 17 + Spring Boot 3.3.5** and **Java 17 + Spring Boot 3.4.13**, sharing application sources with version-specific tests.
11. Verify all **16 JUnit Jupiter `@Test` methods**, split into 6 legacy and 10 modern, with no test-order dependence.
12. Have a Boot 4 upgrade checklist, compilation/bean-override debugging steps, and self-study exercises.

**Pinned versions for runnable sources:** Java 17; Spring Boot 3.3.5 / Spring Framework 6.1.x for the legacy project; Spring Boot 3.4.13 / Spring Framework 6.2.x for the modern project. Boot 4 uses Spring Framework 7 and also changes test modules, so **do not claim Boot 3.4 build files run as-is on Boot 4**.

## 2. Version Matrix and Important Imports

| Runtime/Test Stack | Available | Status |
|---|---|---|
| Boot 3.3.5 + Framework 6.1 | `@MockBean`, `@SpyBean` from Boot | Usable; Framework `@MockitoBean` is not yet in the managed stack |
| Boot 3.4.x + Framework 6.2 | Both old Boot annotations and new Framework annotations | Old Boot annotations **deprecated** since 3.4.0; migrate incrementally |
| Boot 3.5.x + Framework 6.2 | Framework `@MockitoBean`, `@MockitoSpyBean` | Prefer the new API; prepare for Boot 4 |
| Boot 4.0+ + Framework 7 | Framework Mockito annotations | Boot `@MockBean`, `@SpyBean` **removed**; check matching test modules |

**Legacy imports (Boot 3.3):**

~~~java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;
~~~

**Modern imports (Boot 3.4+):**

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
~~~

**Do not do this:** add `spring-test:6.2` alone to a Boot 3.3 dependency tree just so the compiler finds the annotation, because the Spring Boot BOM manages Framework 6.1 and mixing minor versions can break compatibility. Upgrade the **Spring Boot platform consistently** and re-run the full suite.

### 2.1. Plain Mocks Do Not Automatically Replace Spring Beans

~~~java
// Illustrates a unit test without running a Spring context.
@ExtendWith(MockitoExtension.class)
class PureCheckoutUnitTest {

    @Mock
    StockGateway stockGateway;

    @InjectMocks
    CheckoutService checkoutService;

    @Test
    void example() { }
}
~~~

The snippet above requires Mockito/JUnit imports and a matching `CheckoutService` constructor. `@Mock` creates a Mockito object in JUnit and `@InjectMocks` attempts to inject it into the Java object, yet it **does not replace an `@Autowired` Spring bean** inside a cached `ApplicationContext`. With `@SpringBootTest`, if the service comes from Spring, you must override **the bean by proper type/name** or provide an appropriate test configuration.

**Mock at the right boundary:** to test the real `CheckoutService.quote()`, mock `StockGateway`—**not** `CheckoutService`. If you mock the service under test itself, the test no longer verifies business branching or pricing calculations.

## 3. Understanding Mock vs. Spy Through Behavior

| Kind | Original Bean | Behavior When Unstubbed | Injected by Spring? |
|---|---|---|---|
| Mockito `@Mock` | Not needed | Default Mockito answer: primitive `int` is 0, references null | Not automatically |
| Mockito `@Spy` | Existing Java object | Calls real methods | Not automatically |
| Boot `@MockBean` | Spring bean may exist or be added as mock | Mock behavior | Yes |
| Boot `@SpyBean` | Spring bean wrapped with spy | Real behavior when unstubbed | Yes |
| Framework `@MockitoBean` | Overridden or newly created bean | Mock behavior | Yes |
| Framework `@MockitoSpyBean` | Existing Spring bean | `WRAP`s and calls real behavior when unstubbed | Yes |

If `StockGateway.available("SKU-1")` returns an `int`, an **unstubbed** Mockito mock normally returns `0`. A service checking `available < units` will report insufficient stock. With a `PricePolicy` spy, calling `totalWithFee(2,100)` executes real logic returning **220** when unstubbed.

### 3.1. Stubbing Spies: Avoiding Immediate Real Method Execution

~~~java
// With a Mockito mock, this is normal:
when(stockGateway.available("SKU-1")).thenReturn(4);

// With a Mockito spy, the following MAY invoke the real method immediately:
when(pricePolicy.totalWithFee(2, 100)).thenReturn(900);

// Usually safer when the spy has side effects:
doReturn(900).when(pricePolicy).totalWithFee(2, 100);

// Simulate failure:
doThrow(new IllegalStateException("Pricing unavailable"))
        .when(pricePolicy)
        .totalWithFee(2, 100);
~~~

`when(spy.method())` must evaluate the Java call `spy.method()`, so real logic can run **before stubbing takes effect**. If that method sends HTTP requests, mutates a DB, publishes to Kafka, or throws, this is dangerous. `doReturn`/`doThrow` is the standard pattern to avoid executing the real method during stub setup.

When you want to spy on real behavior, **leave it unstubbed** and use `verify(spy).method(...)`; that is a completely different goal.

## 4. Framework 6.2 Bean Override Strategies

### 4.1. `@MockitoBean` = `REPLACE_OR_CREATE`

~~~java
@MockitoBean
StockGateway stockGateway;
~~~

Spring TestContext searches for a matching bean in the application context. If one exists, it is **replaced by a mock**. If none exists, it **registers a new mock bean** by default under the `REPLACE_OR_CREATE` strategy.

This is a sensible default when a test slice intentionally omits real collaborators (e.g., a controller slice needing a mocked service). In a full integration test, however, if a vital bean disappears due to misconfigured component scanning, a test staying green because a mock was silently created can hide architectural bugs.

### 4.2. `@MockitoBean(enforceOverride = true)` = `REPLACE`

~~~java
@MockitoBean(enforceOverride = true)
StockGateway stockGateway;
~~~

When an **original bean must exist**, use `enforceOverride=true`. If no target bean exists, context setup fails instead of creating a new mock. In the modern demo project, `LocalStockGateway` truly exists via `@Component`, so this condition holds.

**Do not enforce everywhere blindly.** If a service outside a `@WebMvcTest` slice is intentionally not loaded, `REPLACE_OR_CREATE` may be the right policy.

### 4.3. `@MockitoSpyBean` = `WRAP`

~~~java
@MockitoSpyBean
PricePolicy pricePolicy;
~~~

`@MockitoSpyBean` **wraps a real bean with a spy**, requiring **exactly one existing candidate** to wrap. If zero beans exist or multiple candidates cannot be disambiguated, context setup fails. Modern Spring Framework bean overrides only support **singletons**; non-singleton/prototype/request-scoped targets cannot be overridden this way.

Spies and mocks are fundamentally different:
- Mocks use stubbed/default behavior, typically skipping real dependencies and network calls.
- Spies retain real behavior except for stubbed methods, so side-effect risks remain.
- Spying on a Spring AOP-proxied/`@Transactional` bean does not prove the transaction interceptor ran; verify proxy/target behavior separately.

### 4.4. FactoryBean, AOP, and Scope

When a bean is produced by a `FactoryBean<T>`:
- `MockitoBean` replaces the `FactoryBean` with a singleton mock of **object type `T`**.
- `MockitoSpyBean` creates a spy around the **object produced by the `FactoryBean`**, not the factory itself.
- `@Transactional`, `@Cacheable`, and `@Async` proxies may be replaced/wrapped differently than in legacy behavior: verifying Mockito interactions alone **does not prove** real transaction/security/cache behavior.
- Spring Framework annotations do not support overriding non-singleton targets; if legacy tests target prototypes, redesign the fixture or bean scope.

**When testing real AOP behavior, do not mock the layer carrying the interceptor.** Mock a lower-level client or run an integration test with the real service bean, then assert DB transaction/cache/security semantics.

## 5. Finding the Right Bean: Type, Name, Qualifier, Field Name, and Context Cache

### 5.1. Single Bean of That Type

The app has `LocalStockGateway implements StockGateway` as the **sole** implementation. The field:

~~~java
@MockitoBean
StockGateway stockGateway;
~~~

selects the target by type with no ambiguity. The field is also injected with the overridden mock by the framework—no separate `@Autowired` is needed.

### 5.2. Multiple Beans Implementing the Same Interface

If two `StockGateway` implementations exist, specify the name or qualifier:

~~~java
@MockitoBean(name = "primaryStockGateway")
StockGateway stockGateway;
~~~

or:

~~~java
@MockitoBean
@Qualifier("primaryStockGateway")
StockGateway stockGateway;
~~~

These two snippets are **illustrative only**; the sample production code has no `primaryStockGateway`. On fields, `@Qualifier` disambiguates targets; without a qualifier, the **field name** acts as a *fallback qualifier*. Differing field names across test classes can produce distinct TestContext cache keys and increase context startups.

**Trap:** `StockGateway stockGateway` and `StockGateway inventory` share the same Java type yet produce different fallback qualifier metadata. Avoid arbitrary field names when multiple classes are intended to share one context key.

### 5.3. Type-Level Annotations

With Spring Framework 6.2 matching Boot 3.4.13:

~~~java
@SpringBootTest
@MockitoBean(
        name = "localStockGateway",
        types = StockGateway.class,
        enforceOverride = true)
class ExampleTest {
}
~~~

This snippet is illustrative and needs Spring and JUnit imports in a real class. When placed on a **test type**, use the `types` attribute—unlike legacy `@MockBean`'s `classes`/`value`. When `name` is specified, the `types` list **must contain a single type**. Annotations can be repeated at the type level or extracted into a **composed annotation** reused across tests.

**The runnable project** in Section 11 includes `ModernByNameTest` as a complete demonstration.

### 5.4. Context Hierarchy

With `@ContextHierarchy`, the new mock/spy override may apply across context levels by default. To target one specific level, Framework 6.2 supports `contextName` matching `@ContextConfiguration(name=...)`:

~~~java
@MockitoBean(contextName = "app-config")
StockGateway stockGateway;
~~~

This is a snippet for a hierarchy configured outside the runnable lesson. Do not set `contextName` if the project has no named hierarchy. With multiple child contexts, specify the owning level explicitly to avoid mocking the wrong parent or creating redundant contexts.

## 6. Do Not Copy Old Annotations on `@Configuration` Directly to the New API

Legacy Boot allowed `@MockBean`/`@SpyBean` fields on `@Configuration`/`@TestConfiguration` classes in some patterns:

~~~java
// Legacy placement: needs to be moved during migration.
@Configuration
class LegacyMockConfig {

    @MockBean
    StockGateway stockGateway;
}
~~~

Spring Framework `@MockitoBean`/`@MockitoSpyBean` **does not support field placement on `@Configuration` classes** like legacy Boot did. A literal translation:

~~~java
// DO NOT do this:
@Configuration
class NewMockConfig {

    @MockitoBean
    StockGateway stockGateway;
}
~~~

is not a valid migration. This is an **anti-pattern**, not part of the runnable project.

**Simplest valid approach:** put the annotation on a field of the JUnit test class:

~~~java
@SpringBootTest
class CheckoutTest {

    @MockitoBean
    StockGateway stockGateway;
}
~~~

**If multiple classes need the same mock:** create a composed annotation at the test type level:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@MockitoBean(types = StockGateway.class)
@interface WithMockStockGateway {
}
~~~

This annotation snippet assumes `StockGateway` is defined and needs `package demo.migration;` if placed in a file. Apply `@WithMockStockGateway` to test classes needing the mock; do not use it to mark production `@Configuration`.

**Alternative:** create a manual Mockito mock inside a `@TestConfiguration @Bean` to inspect explicit bean factory behavior, while accounting for duplicate bean names, primary/qualifiers, and reset policy. That approach has no automatic reset equivalent unless configured manually. Do not enable global `spring.main.allow-bean-definition-overriding=true` just to mask bean graph conflicts.

## 7. Mock Reset and Test Isolation

In legacy Boot, the `MockReset` enum is:

~~~java
import org.springframework.boot.test.mock.mockito.MockReset;

@MockBean(reset = MockReset.AFTER)
StockGateway stockGateway;
~~~

In the new Framework API:

~~~java
import org.springframework.test.context.bean.override.mockito.MockReset;

@MockitoBean(reset = MockReset.AFTER)
StockGateway stockGateway;
~~~

`AFTER` is the common default: Mockito stubbings and interaction history are reset **after each JUnit test method**. Each package defines its own enum, so do not swap only half of the imports. `BEFORE`/`NONE` have specific use cases but can introduce test-order dependencies if misused.

**What is NOT reset:**
- Database writes performed by a real spy method.
- Kafka/Redis contents.
- Static fields or `ThreadLocal` state.
- Files on disk.
- Background tasks still running after the test.

If two JUnit methods run concurrently against **the same cached Spring `ApplicationContext`** and the same mock, one test can reset or stub the mock while another test is using it. Use independent fixtures, run shared-mock groups sequentially, or apply JUnit `@ResourceLock` (with the same key across all participants in one Jupiter JVM). JUnit locks **do not synchronize across Gradle forks or CI jobs**; do not sprinkle `@DirtiesContext` everywhere to "fix" mock resets, as context rebuilds are expensive and can introduce other races.

## 8. Two Version-Separated Runnable Projects

The exact same five Java production files are shared **across two independent Gradle projects**:

~~~text
legacy-boot33/
  settings.gradle
  build.gradle
  src/main/java/demo/migration/MockMigrationApplication.java
  src/main/java/demo/migration/StockGateway.java
  src/main/java/demo/migration/LocalStockGateway.java
  src/main/java/demo/migration/PricePolicy.java
  src/main/java/demo/migration/CheckoutService.java
  src/test/java/demo/migration/LegacyMockBeanTest.java
  src/test/java/demo/migration/LegacySpyBeanTest.java

modern-boot34/
  settings.gradle
  build.gradle
  src/main/java/demo/migration/MockMigrationApplication.java
  src/main/java/demo/migration/StockGateway.java
  src/main/java/demo/migration/LocalStockGateway.java
  src/main/java/demo/migration/PricePolicy.java
  src/main/java/demo/migration/CheckoutService.java
  src/test/java/demo/migration/ModernMockitoBeanTest.java
  src/test/java/demo/migration/ModernMockitoSpyBeanTest.java
  src/test/java/demo/migration/ModernByNameTest.java
~~~

**Exact setup instructions:** create **all five files** from Section 9 with **identical content** under `src/main/java/demo/migration/` in **both legacy and modern**. Gradle configuration and Java test files are separated by version in Sections 10 and 11. Do not put the modern tests inside the Boot 3.3 project, since Framework 6.2's `@MockitoBean` class does not exist there.

This lesson uses two independent projects rather than trying to load two Spring Boot Gradle plugin versions in the same Gradle root classloader. Each project manages its own BOM and dependencies cleanly.

## 9. Five Shared Java Production Classes for Both Versions

### 9.1. `MockMigrationApplication.java`

~~~java
package demo.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockMigrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MockMigrationApplication.class, args);
    }
}
~~~

**File:** `src/main/java/demo/migration/MockMigrationApplication.java` in each project.

### 9.2. `StockGateway.java`

~~~java
package demo.migration;

public interface StockGateway {

    int available(String sku);
}
~~~

**File:** `src/main/java/demo/migration/StockGateway.java`. This is the boundary mocked in the integration tests. Production would call an external inventory API, whereas the demo uses a local implementation so no internet or Docker is needed.

### 9.3. `LocalStockGateway.java`

~~~java
package demo.migration;

import org.springframework.stereotype.Component;

@Component
public class LocalStockGateway implements StockGateway {

    @Override
    public int available(String sku) {
        return "OUT".equals(sku) ? 0 : 8;
    }
}
~~~

**File:** `src/main/java/demo/migration/LocalStockGateway.java`. Its default bean name is `localStockGateway` and it is the **sole `StockGateway` implementation** in the context. Stock for any SKU other than `OUT` is 8, sufficient for spy tests without stubbing.

### 9.4. `PricePolicy.java`

~~~java
package demo.migration;

import org.springframework.stereotype.Component;

@Component
public class PricePolicy {

    public int totalWithFee(int units, int pricePerUnit) {
        if (units < 1 || pricePerUnit < 0) {
            throw new IllegalArgumentException(
                    "Invalid price input");
        }

        return Math.addExact(
                Math.multiplyExact(units, pricePerUnit),
                20);
    }
}
~~~

**File:** `src/main/java/demo/migration/PricePolicy.java`. Real results: `totalWithFee(2,100)` is **220**, `totalWithFee(1,100)` is **120**. Exact math avoids silent `int` overflow; real monetary projects should consider `BigDecimal`/currency policies.

`PricePolicy` is concrete, singleton by default, has no AOP proxy, and touches no external resources. It is an ideal target for learning `@MockitoSpyBean` `WRAP` behavior without confounding factors.

### 9.5. `CheckoutService.java`

~~~java
package demo.migration;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final StockGateway stockGateway;
    private final PricePolicy pricePolicy;

    public CheckoutService(
            StockGateway stockGateway,
            PricePolicy pricePolicy) {

        this.stockGateway = stockGateway;
        this.pricePolicy = pricePolicy;
    }

    public int quote(String sku, int units) {
        if (sku == null || sku.isBlank() || units < 1) {
            throw new IllegalArgumentException(
                    "Invalid order input");
        }

        if (stockGateway.available(sku) < units) {
            throw new IllegalStateException(
                    "Insufficient stock");
        }

        return pricePolicy.totalWithFee(units, 100);
    }
}
~~~

**File:** `src/main/java/demo/migration/CheckoutService.java`. Constructor DI is explicit; the service never instantiates `new LocalStockGateway()` manually, so Spring context test overrides genuinely swap the dependency.

**Execution paths:**
- `quote("SKU-1",2)` with the real gateway (`available=8`): price=220.
- With mocked gateway returning 4: price=220.
- With unstubbed mocked gateway: `available` returns `int` 0, throws `"Insufficient stock"`.
- With `units=0`/blank `sku`: throws `"Invalid order input"` **before calling the gateway**.
- With pricing spy stubbed via `doReturn(777)` for `(2,100)`: result=777.

Do not place a test-only `@Configuration` in package `demo.migration` that unexpectedly alters bean scanning. All override annotations in the examples sit on **JUnit test classes/fields**.

## 10. Legacy Project: Spring Boot 3.3.5

### 10.1. `legacy-boot33/settings.gradle`

~~~groovy
rootProject.name = 'legacy-mock-bean'
~~~

### 10.2. `legacy-boot33/build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

`starter-test` already manages Mockito, JUnit Jupiter, Spring TestContext, and Boot's legacy Mockito support. Do not pin `spring-test` 6.2 while still on Boot 3.3.5.

### 10.3. `LegacyMockBeanTest.java`: 3 JUnit Tests

**File:** `legacy-boot33/src/test/java/demo/migration/LegacyMockBeanTest.java`

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class LegacyMockBeanTest {

    @MockBean
    StockGateway stockGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void usesStubbedStockAndRealCheckout() {
        when(stockGateway.available("SKU-1")).thenReturn(4);

        assertEquals(220, checkoutService.quote("SKU-1", 2));
        verify(stockGateway).available("SKU-1");
    }

    @Test
    void unstubbedMockReturnsZero() {
        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> checkoutService.quote("SKU-1", 1));

        assertEquals("Insufficient stock", error.getMessage());
        verify(stockGateway).available("SKU-1");
    }

    @Test
    void inputValidationPrecedesExternalDependency() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> checkoutService.quote(" ", 2));

        assertEquals("Invalid order input", error.getMessage());
        verifyNoInteractions(stockGateway);
    }
}
~~~

**Exactly 3 `@Test` methods.** The `StockGateway` mock replaces the Spring bean while `CheckoutService` and `PricePolicy` stay real. The unstubbed test expects Mockito to return `0` for `int`. `verifyNoInteractions` confirms guard validation executes before calling the gateway.

### 10.4. `LegacySpyBeanTest.java`: 3 JUnit Tests

**File:** `legacy-boot33/src/test/java/demo/migration/LegacySpyBeanTest.java`

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.SpyBean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class LegacySpyBeanTest {

    @SpyBean
    PricePolicy pricePolicy;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void unstubbedSpyCallsRealMethod() {
        assertEquals(220, checkoutService.quote("SKU-1", 2));
        verify(pricePolicy).totalWithFee(2, 100);
    }

    @Test
    void doReturnOverridesOneMethod() {
        doReturn(777).when(pricePolicy).totalWithFee(2, 100);

        assertEquals(777, checkoutService.quote("SKU-1", 2));
        verify(pricePolicy).totalWithFee(2, 100);
    }

    @Test
    void doThrowSimulatesPricingFailure() {
        doThrow(new IllegalStateException("Pricing unavailable"))
                .when(pricePolicy)
                .totalWithFee(1, 100);

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> checkoutService.quote("SKU-1", 1));

        assertEquals("Pricing unavailable", error.getMessage());
        verify(pricePolicy).totalWithFee(1, 100);
    }
}
~~~

**Exactly 3 `@Test` methods.** `StockGateway` is not mocked in the spy class; the real `LocalStockGateway` bean returns 8. `PricePolicy`'s real method runs in the first test, while the remaining tests use `doReturn`/`doThrow`.

**Legacy total = 6 JUnit tests.** Because the two test contexts differ in mock vs. spy definitions, do not assume they share the exact same `ApplicationContext` instance.

## 11. Modern Project: Spring Boot 3.4.13

### 11.1. `modern-boot34/settings.gradle`

~~~groovy
rootProject.name = 'modern-mockito-bean'
~~~

### 11.2. `modern-boot34/build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Boot 3.4.13 dependency management supplies Spring Framework 6.2.x and the new bean overriding API. `spring-boot-starter-test` brings in Mockito; do not declare an unmatched standalone `mockito-core` version that could break the framework's mock resolver.

### 11.3. `ModernMockitoBeanTest.java`: 4 JUnit Tests

**File:** `modern-boot34/src/test/java/demo/migration/ModernMockitoBeanTest.java`

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ModernMockitoBeanTest {

    @MockitoBean(enforceOverride = true)
    StockGateway stockGateway;

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    ApplicationContext context;

    @Test
    void mockReplacesRealStockDependency() {
        when(stockGateway.available("SKU-1")).thenReturn(4);

        assertEquals(220, checkoutService.quote("SKU-1", 2));
        verify(stockGateway).available("SKU-1");
    }

    @Test
    void missingStubDoesNotCallRealGateway() {
        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> checkoutService.quote("SKU-1", 1));

        assertEquals("Insufficient stock", error.getMessage());
        verify(stockGateway).available("SKU-1");
    }

    @Test
    void invalidInputIsRejectedWithoutGatewayCall() {
        assertThrows(
                IllegalArgumentException.class,
                () -> checkoutService.quote(null, 2));

        verifyNoInteractions(stockGateway);
    }

    @Test
    void mockedObjectIsTheActualSpringBean() {
        assertSame(
                stockGateway,
                context.getBean(StockGateway.class));

        assertTrue(
                Mockito.mockingDetails(stockGateway).isMock());
    }
}
~~~

**Exactly 4 `@Test` methods.** `enforceOverride=true` is valid because the application defines the singleton `LocalStockGateway` implementing `StockGateway`. If the production bean were removed or excluded by a profile, context setup would fail rather than silently creating a new mock. The `ApplicationContext` interface **declares `getBean`**, so the assertion uses a valid API; do not call `isActive()` on that interface.

### 11.4. `ModernMockitoSpyBeanTest.java`: 4 JUnit Tests

**File:** `modern-boot34/src/test/java/demo/migration/ModernMockitoSpyBeanTest.java`

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ModernMockitoSpyBeanTest {

    @MockitoSpyBean
    PricePolicy pricePolicy;

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    ApplicationContext context;

    @Test
    void spyUsesRealPricePolicyByDefault() {
        assertEquals(220, checkoutService.quote("SKU-1", 2));
        verify(pricePolicy).totalWithFee(2, 100);
    }

    @Test
    void doReturnOverridesSpySafely() {
        doReturn(999).when(pricePolicy).totalWithFee(2, 100);

        assertEquals(999, checkoutService.quote("SKU-1", 2));
        verify(pricePolicy).totalWithFee(2, 100);
    }

    @Test
    void doThrowHandlesPricingFailure() {
        doThrow(new IllegalStateException("Pricing unavailable"))
                .when(pricePolicy)
                .totalWithFee(1, 100);

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> checkoutService.quote("SKU-1", 1));

        assertEquals("Pricing unavailable", error.getMessage());
        verify(pricePolicy).totalWithFee(1, 100);
    }

    @Test
    void spyIsTheBeanRegisteredWithSpring() {
        assertSame(
                pricePolicy,
                context.getBean(PricePolicy.class));

        assertTrue(
                Mockito.mockingDetails(pricePolicy).isSpy());
    }
}
~~~

**Exactly 4 `@Test` methods.** `PricePolicy` is a concrete singleton component with no transaction/AOP proxy, so `WRAP` targets it cleanly. The tests verify both the real method and intentional stubbing. The spy resets `AFTER` each JUnit test by default; there is no dependence on the order of the four methods.

### 11.5. `ModernByNameTest.java`: 2 JUnit Tests

**File:** `modern-boot34/src/test/java/demo/migration/ModernByNameTest.java`

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@MockitoBean(
        name = "localStockGateway",
        types = StockGateway.class,
        enforceOverride = true)
class ModernByNameTest {

    @Autowired
    StockGateway stockGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void typeLevelOverrideTargetsExistingBeanByName() {
        when(stockGateway.available("SKU-2")).thenReturn(3);

        assertEquals(320, checkoutService.quote("SKU-2", 3));
        verify(stockGateway).available("SKU-2");
    }

    @Test
    void eachTestMustConfigureItsOwnStub() {
        assertThrows(
                IllegalStateException.class,
                () -> checkoutService.quote("SKU-2", 1));

        verify(stockGateway).available("SKU-2");
    }
}
~~~

**Exactly 2 `@Test` methods.** The default component name is `localStockGateway`, and there is only one `StockGateway` in the app. The class-level annotation specifies one entry in `types` when `name` is set. The second test does not rely on the first test having run to assert Mockito's default behavior; `AFTER` reset ensures stubbing is not inherited within the cached context.

**Modern total = 4+4+2 = 10 JUnit tests.**

**Combined total across both independent builds = 6+10 = 16 JUnit Jupiter `@Test` methods.**

## 12. Running Gradle and Expected Outcomes

Requires JDK 17, Gradle compatible with both Boot plugins (Gradle 8.x fits), and Maven Central access to download dependencies if not already cached. Neither project uses a web server, DB, or containers.

If Gradle wrappers are already present in each project:

~~~bash
cd legacy-boot33
./gradlew test
cd ../modern-boot34
./gradlew test
~~~

Windows PowerShell:

~~~powershell
Set-Location legacy-boot33
.\gradlew.bat test
Set-Location ../modern-boot34
.\gradlew.bat test
~~~

If you only created the files above **without wrapper scripts/JAR**, `./gradlew` will not exist. You can run `gradle test` using an installed Gradle or generate a Gradle Wrapper first:

~~~bash
cd legacy-boot33
gradle test
cd ../modern-boot34
gradle test
~~~

Run individual classes inside the matching project directory:

~~~bash
# Inside legacy-boot33:
./gradlew test --tests demo.migration.LegacyMockBeanTest
./gradlew test --tests demo.migration.LegacySpyBeanTest

# Inside modern-boot34:
./gradlew test --tests demo.migration.ModernMockitoBeanTest
./gradlew test --tests demo.migration.ModernMockitoSpyBeanTest
./gradlew test --tests demo.migration.ModernByNameTest
~~~

**Test count table:**

| Build | Class | `@Test` Methods |
|---|---|---:|
| Boot 3.3.5 | `LegacyMockBeanTest` | 3 |
| Boot 3.3.5 | `LegacySpyBeanTest` | 3 |
| Boot 3.4.13 | `ModernMockitoBeanTest` | 4 |
| Boot 3.4.13 | `ModernMockitoSpyBeanTest` | 4 |
| Boot 3.4.13 | `ModernByNameTest` | 2 |
| **Total** | 5 classes | **16** |

Gradle reports are typically written to `build/reports/tests/test/index.html`. **The suite is designed to PASS**, though this is an expectation from the APIs/sources, not a claim that Gradle was run on the reader's machine. When applying these patterns to a real project with custom bean profiles, AOP proxies, or test slices, compile and run tests on the target version branch.

**Why these assertions matter:**
- Mocking `StockGateway` replaces the bean while keeping `CheckoutService` real.
- An unstubbed mock returns `0`, causing the service to report insufficient stock instead of silently calling the local implementation (which returns 8).
- Spying on real `PricePolicy` returns 220, `doReturn` yields 777/999, and `doThrow` simulates failure.
- `verify` confirms business collaboration and arguments.
- `context.getBean(...)` proves the object is the Spring-managed mock/spy, not a standalone Mockito field.
- `enforceOverride` proves the production bean exists.
- The by-name class-level annotation selects the target by name.
- No tests intentionally fail or depend on test ordering.

## 13. Real-Repo Migration Workflow

1. **Capture baseline:** Boot/JDK versions, test counts, failures, Spring `ContextCache` stats, and test task runtimes.
2. **Upgrade the platform consistently:** Boot 3.3 → an approved Boot 3.4/3.5 patch; do not pin `spring-test` 6.2 into Boot 3.3.
3. **Audit all imports** of `org.springframework.boot.test.mock.mockito.*`, including class-level annotations and custom test annotations.
4. **Migrate straightforward field-level usages** to the Framework imports and annotations.
5. **Audit legacy `@Configuration` fields:** move them to test-class/type-level/composed annotations; do not copy placement verbatim.
6. **Audit `@MockBean(classes=...)`:** switch to `@MockitoBean(types=...)` where type-level placement is supported by your version, and verify bean names.
7. **Audit `@SpyBean` target cardinality:** requires exactly one existing bean; when multiple candidates exist, use explicit `name`/`@Qualifier`.
8. **Audit target existence:** decide when `enforceOverride=true` applies vs. when a test slice needs mock creation.
9. **Audit singleton scope:** tests targeting non-singletons need a different strategy.
10. **Audit `MockReset` package/behavior:** `AFTER`, `BEFORE`/`NONE`, and cross-method interactions.
11. **Audit AOP/`FactoryBean`:** do not assume identical `proxyTargetAware` or factory bean semantics.
12. **Audit context cache keys:** differing field names/qualifiers create extra contexts; standardize metadata.
13. **Audit parallel tests:** stubbing/resetting shared Mockito objects can race in cached Spring contexts.
14. **Audit tests mocking the SUT:** keep dependency boundaries mocked and the service under test real.
15. **Run representative tests + full suite** on the new branch, checking JUnit reports and bean override errors.
16. **Prepare for Boot 4:** eliminate legacy APIs completely, review testing module reorganizations and other migration notes.
17. **Code review** behavioral changes; do not merge simply because deprecation warnings cleared.
18. **Keep migration guardrail tests** to catch missing targets, wrong qualifiers, accidental mock creation, and AOP regressions.

### 13.1. Common Diffs

**Field-level mock:**

~~~diff
-import org.springframework.boot.test.mock.mockito.MockBean;
+import org.springframework.test.context.bean.override.mockito.MockitoBean;

-@MockBean
+@MockitoBean
 StockGateway stockGateway;
~~~

**Field-level spy:**

~~~diff
-import org.springframework.boot.test.mock.mockito.SpyBean;
+import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

-@SpyBean
+@MockitoSpyBean
 PricePolicy pricePolicy;
~~~

**Class-level mock:**

~~~diff
-@MockBean(classes = StockGateway.class)
+@MockitoBean(types = StockGateway.class)
 class CheckoutTest {
 }
~~~

These are **illustrative diff fragments**, not standalone Java files. They apply only when target bean, annotation placement, Framework version, and semantics match; do not run them as blind regex rewrites across every file.

## 14. Tricky Cases Requiring Special Verification

### 14.1. Type With No Existing Bean

~~~java
@MockitoBean
OptionalGateway optionalGateway;
~~~

By default this **creates a new mock** if no matching bean exists. For full integration tests that expect the real production bean to exist:

~~~java
@MockitoBean(enforceOverride = true)
OptionalGateway optionalGateway;
~~~

fails when missing. This snippet uses a hypothetical `OptionalGateway` type and is not part of the runnable sources. A test slice, by contrast, may want `REPLACE_OR_CREATE` because service collaborators are excluded from the slice.

### 14.2. Multiple Implementations of the Same Interface

Legacy `@SpyBean(classes=...)` could spy on multiple matching beans under Boot behavior; the new `@MockitoSpyBean` must select exactly one candidate. For example:

~~~java
@MockitoSpyBean(name = "primaryPaymentClient")
PaymentClient primaryClient;
~~~

The real app must have that `PaymentClient`/bean name; this snippet is illustrative. To spy on two clients, declare two distinct targets and verify actual object matching. Avoid omitting the qualifier and letting field-name fallback silently pick a different bean.

### 14.3. AOP Proxies and Security/Transactions

If a `@Transactional` service is replaced with a mock via `@MockitoBean`, real transaction logic is no longer tested. If a spy wraps a `@Cacheable` service with an AOP proxy, `Mockito.verify` on target vs. proxy requires careful matching, and the real method invocation count will reflect caching. Test real behavior—database rollback/commit, cache hits, authorization—rather than treating mock interaction counts as proof of cross-cutting concerns.

### 14.4. `FactoryBean`

A `FactoryBean` can produce the type injected into application code. The new mock replaces the `FactoryBean` with a singleton mock of the produced type, while the spy wraps the produced object. Do not assume `@MockitoSpyBean` spies on the factory itself. Explicitly name the object/bean in tests if there is ambiguity.

### 14.5. Shared Mocks and Parallel JUnit

A mock in a cached context can be reset after Test A while concurrent Test B is still stubbing or reading it. The cleanest design avoids mutable cross-test state, runs related classes sequentially, or applies `@ResourceLock` with the same key across all participating Jupiter nodes. Because JUnit locks do not span Gradle JVMs, shared external DB/Kafka state still requires separate test namespaces.

### 14.6. When Is a Spring Context Unnecessary?

Pure service unit tests using Java constructors + Mockito `@Mock`/`@InjectMocks` do not need `@SpringBootTest`. They run faster and avoid bean-overriding complexity, though they **do not verify Spring DI wiring**. Match test type to purpose:
- Unit: fast service logic with mocked collaborators in Java.
- Slice: controller/repository/JSON subset; mock beans excluded from the slice.
- Full context: wiring, transactions, real service integration.
- Real HTTP server/DB: when proving transport, persistence, and external side effects.

## 15. Common Errors and Remedies

| Error | Cause | Fix |
|---|---|---|
| `MockitoBean cannot be resolved` on Boot 3.3 | Framework 6.1 lacks the API | Keep legacy API or upgrade the whole Boot stack |
| `MockBean cannot be resolved` on Boot 4 | Legacy API was removed | Use Framework bean override imports and test modules |
| `MockitoSpyBean cannot be resolved` | Wrong package/dependency | Check `org.springframework.test.context.bean.override.mockito` and BOM |
| Mock field exists yet service uses real bean | Used plain Mockito `@Mock`, or service calls `new` | Use Spring override and constructor DI |
| Unwanted mock bean created | `REPLACE_OR_CREATE` when target was absent | Set `enforceOverride=true` to assert target existence |
| Spy fails to start due to missing bean | `WRAP` requires a real target | Register a singleton bean in the proper scope |
| Spy fails to start due to ambiguous type | Multiple candidate beans | Specify explicit `@Qualifier`/`name` |
| Legacy `@Configuration` mock fields fail to migrate | New Framework does not support that placement | Move to test class/type-level/composed annotation |
| Class annotation `classes=` fails to compile | New API uses `types=` | Update attribute names properly |
| Legacy `proxyTargetAware` fails to compile | New `SpyBean` does not keep identical attributes | Review proxy-target verification |
| `MockReset` type mismatch | Boot enum differs from Framework enum | Import `MockReset` from the right package |
| Spy stubbing invokes real method | `when(spy.method())` | Use `doReturn`/`doThrow` |
| Spy resets yet DB retains data | Mockito reset does not roll back DB | Use transaction/fixture cleanup |
| Test passes yet business service was untested | Accidentally mocked the SUT | Mock external boundary; keep SUT real |
| Test suite startup got slower | Differing field names/qualifiers fragment contexts | Standardize metadata; inspect `ContextCache` stats |
| Flaky parallel tests | Shared mock reset/stubbed between methods | Disable parallelism for this group; isolate fixtures |
| Multiple bean candidates | Type alone is ambiguous | Specify exact `@Qualifier`/`name` |
| Prototype bean not overridden | Framework supports singleton overrides only | Choose a different test strategy |
| Test slice lacks bean to enforce | Full app vs. slice bean graph differs | Adjust enforce policy intentionally |
| Boot 4 upgrade fails after swapping mock annotations | Other testing modules/deps changed too | Follow the complete Boot 4 migration guide |
| `@ContextHierarchy` override hits wrong level | Default override spans levels | Set `contextName` to match the named level |

## 16. Review Checklist, QA, and Exercises

**Pre-merge checklist:**

- [ ] Using matching Boot/Framework versions from the BOM without mixing Spring 6.1 and 6.2.
- [ ] Legacy Boot imports replaced on modern branches; no removed APIs left when targeting Boot 4.
- [ ] Target bean **is truly Spring-managed**, not instantiated via `new` inside the SUT.
- [ ] Explicitly decided between `REPLACE_OR_CREATE` and `enforceOverride`.
- [ ] Spy targets exactly one existing singleton candidate; not applied to prototypes.
- [ ] When multiple beans share a type, qualifiers/names are explicit and consistent.
- [ ] No `@MockitoBean` fields remain inside `@Configuration` classes.
- [ ] Class-level annotations use `types`, with a single type when `name` is set.
- [ ] `MockReset` comes from the matching package; tests do not rely on previous tests' stubbing.
- [ ] Avoided `when(spy...)` where stubbing could trigger side effects.
- [ ] AOP/transaction/security tests retain the real behavior being verified.
- [ ] Field names/qualifiers are consistent for sensible context cache reuse.
- [ ] Parallel tests do not restub/reset shared mocks without synchronization.
- [ ] Bean identity or `Mockito.mockingDetails` verified where real override needs proof.
- [ ] Compiled and ran JUnit tests for both legacy and modern projects.
- [ ] Reviewed other Boot 4 testing-module migrations beyond annotation names.

**Self-study exercises:**

1. Remove `@Component` from `LocalStockGateway`. Explain why `@MockitoBean(enforceOverride=true)` must fail in the modern full-context test.
2. Change the `StockGateway` mock to Mockito's `@Mock` while keeping `@Autowired CheckoutService`. Why does the service not use the test field's Mockito object?
3. Try `when(pricePolicy.totalWithFee(0,100)).thenReturn(1)` on the spy. Why can setup throw `Invalid price input` before the test body assertion runs?
4. Add `@Qualifier("localStockGateway")` on the modern field and check bean target selection.
5. Create two `StockGateway` implementations and migrate a spy; design qualifiers for each bean.
6. Put `@MockitoBean(types=StockGateway.class)` at the test type level and compare with field-level injection.
7. Migrate a legacy mock annotation from a `@TestConfiguration` field to a composed type-level annotation.
8. Test `MockReset.NONE` in a sandbox to observe state-leak risk; revert after experimenting.
9. Keep real `PricePolicy` while mocking `StockGateway` in a transaction test; evaluate what remains verified.
10. Have a Mockito spy method write to a real DB; after the test, why is rollback/cleanup still required even though Mockito reset?
11. Write a `@WebMvcTest` where the target service is unavailable; is `enforceOverride=true` the right policy?
12. Rename a `MockitoBean` field in another test class and measure context-cache keys/hits.
13. Enable parallel tests on a shared mock and resolve races using fixtures or resource locks—never `Thread.sleep`.
14. Draft a Boot 3.3 → 3.5 → Boot 4 migration plan covering compiler, bean targets, coverage, and CI reports.
15. Add a regression test confirming the overridden bean is the exact instance injected into the service.
16. Explain clearly why annotation migration **does not prove** concurrent safety, database correctness, or HTTP contract compatibility.

## 17. Official References

- [Spring Boot 3.4 API — `MockBean`](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): deprecated since 3.4.0, for removal.
- [Spring Boot 3.4 API — `SpyBean`](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/SpyBean.html): legacy spy options and deprecation.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): removal of Boot `@MockBean`/`@SpyBean` and limitations when migrating annotations on `@Configuration`.
- [Spring Framework 6.2 — MockitoBean and MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): target selection, qualifiers, `contextName`, strategy, singleton, and `FactoryBean`.
- [Spring Framework 6.2 — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html): `REPLACE_OR_CREATE`, `REPLACE`, `WRAP`.
- [Spring Framework 6.2 API — MockitoBean](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html): `types`, `name`, `reset`, `enforceOverride`.
- [Spring Framework 6.2 API — MockitoSpyBean](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoSpyBean.html): `WRAP` and singleton behavior.
- [Spring Framework 6.2 API — MockReset](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/bean/override/mockito/MockReset.html): `AFTER`, `BEFORE`, `NONE`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `SpringBootTest`, `MockBean`, test slices.
- [Spring Boot 3.4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html): Boot 3.4 testing and Mockito support.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): customizers, qualifier fallback, cache reuse.
- [Mockito Java API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html): `doReturn`/`doThrow`/`verify`.
- [Gradle Testing](https://docs.gradle.org/current/userguide/java_testing.html): Gradle test task/JUnit Platform.

**Conclusion:** `@MockBean`/`@SpyBean` belong to legacy Spring Boot Test (Boot 3.3), were deprecated in 3.4, and were removed in Boot 4. Starting with Framework 6.2, use `@MockitoBean`/`@MockitoSpyBean` with clear rules: **mock = `REPLACE_OR_CREATE`** (or **`REPLACE`** with `enforceOverride=true`), **spy = `WRAP` existing singleton**. Never swap imports mechanically on `@Configuration` fields, AOP proxies, multiple bean candidates, or non-singletons. Migrate the whole Spring Boot stack, keep the service under test real, check bean targets/qualifiers, mock resets, and context caching, and re-run the test suite on the target version.
