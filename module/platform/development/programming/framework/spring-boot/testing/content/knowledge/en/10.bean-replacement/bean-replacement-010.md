# Impact of Mock Declarations on the `ApplicationContext` Cache Key

## 1. Real-world problem: why does the same app reload its test context repeatedly?

Spring Boot relies on the Spring TestContext Framework to build an `ApplicationContext` for integration tests. Starting a context can be expensive: processing configurations, instantiating beans, running auto-configuration, creating proxies, wiring test infrastructure, and running initialization callbacks.

Spring TestContext maintains a **context cache**: once a context is built for a set of configurations, the framework stores and **reuses** it across other test classes with equivalent configurations. This prevents restarting every bean repeatedly. Yet a tiny difference in **how mocked/spied beans are declared** can produce a **distinct cache key**, forcing Spring to build another context.

Consider two classes both annotated `@SpringBootTest` with the exact same configuration, except:

~~~java
// Class A
@MockitoBean
PaymentGateway paymentGateway;

// Class B
@MockitoBean
PaymentGateway mockGateway;
~~~

Both fields have type `PaymentGateway`; if the context contains only one bean of that type, both target the exact same **business bean**. However, without an explicit `@Qualifier`, the **field name** can act as a fallback qualifier. Spring includes override qualifier information when comparing test configurations. Consequently, these two declarations **may fail to share a cache entry**, solely from renaming the variable.

This is neither a Mockito bug nor a sign that business code changed. The cause is **two distinct test context descriptors**.

### Key learning outcomes

- Accurately explain Spring TestContext's **cache key** and the role of `contextCustomizers`.
- Distinguish plain Mockito mocks from **mocks replacing beans inside a Spring `ApplicationContext`**.
- Understand why adding, removing, or renaming `@MockitoBean` fields, qualifiers, bean names, or override metadata increases context count.
- Write Java 17 + JUnit Jupiter tests demonstrating shared vs. split cache entries.
- Measure using cache logs and optimize context configurations **without sacrificing test validity**.

## 2. What goes into the `ApplicationContext` cache key?

The framework does not simply key contexts by **test class name**. In Spring TestContext, the key uniquely identifies a configuration combination built from these main components:

| Key component | Typical source | Why it affects reuse |
| --- | --- | --- |
| `locations` | `@ContextConfiguration(locations=...)` | Different config sources cannot automatically share a context |
| `classes` | `@ContextConfiguration(classes=...)` and equivalents | Different config classes can define different bean sets |
| `contextInitializerClasses` | `ApplicationContextInitializer` | Different context initializers |
| **`contextCustomizers`** | `ContextCustomizerFactory`; bean overrides and other test hooks | Component directly affected by mock/spy declarations |
| `contextLoader` | Selected `ContextLoader` | Different context-loading strategy |
| `parent` | `@ContextHierarchy` | Different parent context |
| `activeProfiles` | `@ActiveProfiles` | Profiles alter active beans and properties |
| `propertySourceDescriptors` / `propertySourceProperties` | `@TestPropertySource` | Different property sources or inline values |
| `resourceBasePath` | `@WebAppConfiguration` | Different web context settings |

Spring Boot adds its own context customizers for Boot testing features; `@DynamicPropertySource` also participates via a customizer. Simply seeing `@SpringBootTest` on two classes is **not enough** to conclude they share a context.

Overview:

~~~text
Test class A                      Test class B
  |                                 |
  v                                 v
MergedContextConfiguration   MergedContextConfiguration
  |                                 |
  +-- classes/profiles/...          +-- classes/profiles/...
  +-- contextCustomizers           +-- contextCustomizers
  |                                 |
  v                                 v
     compare configuration as cache key
             /              \
       equivalent keys     different keys
            |                  |
      reuse cached        load new context
      ApplicationContext  (if not cached yet)
~~~

**Key distinction:** two tests can test the exact same bean and share `@ActiveProfiles("test")` yet differ in their bean overrides, making their keys non-equivalent. Conversely, two differently named test classes **can share one context** whenever every key-relevant configuration matches and the entry remains cached.

## 3. Why does `@MockitoBean` affect the cache key?

Since Spring Framework 6.2, `@MockitoBean` and `@MockitoSpyBean` replace beans in tests through Spring TestContext's **bean overriding infrastructure**.

When inspecting a test class, the framework gathers override declarations and builds descriptors for beans to replace/wrap:

1. **Bean type** to mock, e.g., `PaymentGateway.class`.
2. **Bean identifier/qualifier**, if present; when absent, **the field name may serve as a fallback qualifier**.
3. **Override strategy** and associated mock/spy configuration attributes.
4. **Hierarchy scope**, when `@ContextHierarchy` or `contextName` is used.

The infrastructure builds a matching `ContextCustomizer` to swap beans during context construction. Those customizers contribute to the **cache key**, ensuring a context with real beans is never mistaken for one with mocks.

### Differences that commonly produce separate contexts

| Test class A | Test class B | Observation |
| --- | --- | --- |
| No mocked beans | Has `@MockitoBean PaymentGateway` | Different context definitions: real bean vs. mock bean |
| Mocks `PaymentGateway` | Mocks `EmailGateway` | Different set of overridden beans |
| Mocks one bean | Mocks two beans | Different override set |
| Same type, differing qualifier/field name | Logically targets the same bean | Fallback qualifier can split the key |
| `@MockitoBean` | `@MockitoSpyBean` | Different strategy: replace vs. wrap |
| Overrides bean named A | Overrides bean named B | Different override target |
| Same mock, differing `@ActiveProfiles` | E.g., `test` vs. `ci` | Different key due to profile, independent of mock |
| Same mock, differing test properties | E.g., differing endpoint/config | Different key via property sources/customizers |

Do not assume **every arbitrary annotation tweak guarantees a new key**: equivalence depends on which attributes the active override mechanism and Spring version include in equality comparisons. Treat meaningful override metadata as part of the configuration and verify specific cases via cache logs.

### Fallback qualifier: a subtle trap

Given the field:

~~~java
@MockitoBean
PaymentGateway gateway;
~~~

Spring infers the bean type from the field type. When **multiple same-type candidates** exist, `@Qualifier` may be needed to pick one. When `@Qualifier` is absent, the field name `gateway` can act as a **fallback qualifier**. Spring documentation explicitly notes that both qualifiers and field names are factored in when deciding whether a separate context is required.

Hence, when multiple test classes override **the same bean**, name the field consistently or specify the bean name/qualifier explicitly in a shared convention. That reduces ambiguity and prevents accidental cache-key divergence.

## 4. Distinguishing three mock scopes: Mockito, Spring TestContext, and legacy Spring Boot

| Annotation / mock style | Who receives the mock? | Participates in bean-override cache key? |
|---|---|---|
| `@Mock` + `MockitoExtension` | Field/parameter on the **test class**; test passes it to SUT | **No**, does not replace Spring context beans |
| `Mockito.mock(Foo.class)` | Plain Java object created by the test | **No**, unless manually registered in context config |
| `@InjectMocks` | Instantiates real SUT and injects Mockito mocks | **No**, does not alter Spring beans |
| `@MockitoBean` | Bean in `ApplicationContext` created/replaced with mock | **Yes**, via bean override / context customizer |
| `@MockitoSpyBean` | Bean in context wrapped with spy | **Yes**, part of context configuration |
| Legacy Spring Boot `@MockBean` | Bean in Spring context replaced/registered as mock | **Yes**, via Boot's mock context customizer |

**Do not confuse them:** declaring `@Mock PaymentGateway gateway` inside a `@SpringBootTest` class creates a mock field in the test, yet the real `PaymentGateway` bean injected into `@Autowired OrderService` **remains unreplaced**. To give a Spring-managed service a mock, use the proper bean override mechanism—or write a plain Java unit test using constructor injection.

### Spring version matters greatly

- **Spring Framework 6.2+ / Spring Boot 3.4+**: provides `org.springframework.test.context.bean.override.mockito.MockitoBean` and `MockitoSpyBean`. The main examples here follow this path.
- **Spring Boot 3.4/3.5**: `org.springframework.boot.test.mock.mockito.MockBean` and `SpyBean` are **deprecated** in favor of Spring Framework's API.
- **Spring Boot 4.0**: Spring Boot's legacy `@MockBean`/`@SpyBean` annotations are **removed**; use `@MockitoBean`/`@MockitoSpyBean`.
- **Spring Boot 3.3 and earlier**: projects typically use `@MockBean` since Spring Framework 6.2 APIs are unavailable. Match annotations to your actual dependencies.

Do not treat `@MockBean` and `@MockitoBean` as exact aliases: supported declaration sites and override semantics differ. Nor should you mix both styles in the same suite expecting uniform cache keys.

## 5. End-to-end example: same business beans, differing mock declarations

We build a total-price service taking a `PricingGateway` dependency. In real applications, that dependency might call HTTP or a database; in this test suite, it has a simple dummy implementation so tests run standalone.

Source files:

~~~text
src/main/java/com/example/testing/PricingGateway.java
src/main/java/com/example/testing/PricingService.java
src/test/java/com/example/testing/PricingTestConfig.java
src/test/java/com/example/testing/SharedMockATest.java
src/test/java/com/example/testing/SharedMockBTest.java
src/test/java/com/example/testing/RenamedFieldMockTest.java
src/test/java/com/example/testing/NoOverrideTest.java
~~~

Each class lives in its own file; all test classes share **`PricingTestConfig.class`**. Running the group inside one JVM lets us observe context instances and cache statistics without writing assertions dependent on test-class run order.

### 5.1. Dependency interface

**`src/main/java/com/example/testing/PricingGateway.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

public interface PricingGateway {
    BigDecimal unitPrice(String sku);
}
~~~

### 5.2. Real business service

**`src/main/java/com/example/testing/PricingService.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.util.Objects;

public final class PricingService {
    private final PricingGateway pricingGateway;

    public PricingService(PricingGateway pricingGateway) {
        this.pricingGateway =
                Objects.requireNonNull(pricingGateway, "pricingGateway");
    }

    public BigDecimal total(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        BigDecimal unitPrice = Objects.requireNonNull(
                pricingGateway.unitPrice(sku),
                "Missing unit price"
        );
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

`PricingService` is a **real object**; input validation and multiplication execute as real Java code. Only `PricingGateway` gets replaced by Mockito.

### 5.3. Shared Spring TestContext configuration

**`src/test/java/com/example/testing/PricingTestConfig.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PricingTestConfig {

    @Bean
    PricingGateway pricingGateway() {
        return sku -> new BigDecimal("11.00");
    }

    @Bean
    PricingService pricingService(PricingGateway pricingGateway) {
        return new PricingService(pricingGateway);
    }
}
~~~

With **no overrides**, `pricingGateway.unitPrice(...)` returns `11.00` for any SKU. With `@MockitoBean`, `pricingGateway` is replaced by a mock, so the lambda no longer runs when `PricingService` calls its dependency.

All test classes below use `@SpringJUnitConfig(PricingTestConfig.class)`. That combines `@ContextConfiguration` and `@ExtendWith(SpringExtension.class)` provided by Spring, building a **small Spring TestContext** sufficient to demonstrate cache keys without loading `@SpringBootTest`.

## 6. Two classes with identical mock declarations: eligible to share a context

**`src/test/java/com/example/testing/SharedMockATest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(PricingTestConfig.class)
class SharedMockATest {
    @MockitoBean
    PricingGateway pricingGateway;

    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void total_whenMockProvidesPrice_returnsExpectedValue() {
        when(pricingGateway.unitPrice("A-1"))
                .thenReturn(new BigDecimal("4.50"));

        assertEquals(
                new BigDecimal("9.00"),
                pricingService.total("A-1", 2)
        );
        verify(pricingGateway).unitPrice("A-1");

        System.out.println(
                "SharedMockATest context@" + System.identityHashCode(context)
        );
    }
}
~~~

**`src/test/java/com/example/testing/SharedMockBTest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(PricingTestConfig.class)
class SharedMockBTest {
    @MockitoBean
    PricingGateway pricingGateway;

    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void total_whenSecondTestStubsPrice_returnsItsOwnValue() {
        when(pricingGateway.unitPrice("B-2"))
                .thenReturn(new BigDecimal("3.00"));

        assertEquals(
                new BigDecimal("9.00"),
                pricingService.total("B-2", 3)
        );
        verify(pricingGateway).unitPrice("B-2");

        System.out.println(
                "SharedMockBTest context@" + System.identityHashCode(context)
        );
    }
}
~~~

Both classes match on all cache-key components:

- Same `@SpringJUnitConfig(PricingTestConfig.class)`.
- Same **single bean override** of type `PricingGateway`.
- Same field name `pricingGateway` with no extra qualifiers or override metadata.
- No separate profiles, property sources, or context customizers.

**Expectation:** when executed together in one JVM without `@DirtiesContext`/eviction or hidden differences, Spring can reuse the **same cached `ApplicationContext`** for both A and B. Yet both tests use **different stubbings**: `4.50` in A and `3.00` in B. Stubbings occur inside test methods and are **not** part of the cache key.

`System.identityHashCode(context)` prints only an **indicative hint** for comparing runs. It is not a mathematically guaranteed unique ID; Spring's cache logs provide proper evidence. Hash numbers vary per JVM, so **there is no fixed stdout number** to assert.

**Important:** sharing a cached context never permits tests to rely on stubbings from an earlier class. Spring/Mockito handle lifecycle mock resets; each test must configure its own stubs and stay independent of state left by others.

## 7. Renaming only the mock field: can generate a new cache key

**`src/test/java/com/example/testing/RenamedFieldMockTest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(PricingTestConfig.class)
class RenamedFieldMockTest {
    @MockitoBean
    PricingGateway anotherPricingGateway;

    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void total_whenMockFieldNameDiffers_stillUsesMock() {
        when(anotherPricingGateway.unitPrice("C-3"))
                .thenReturn(new BigDecimal("6.00"));

        assertEquals(
                new BigDecimal("12.00"),
                pricingService.total("C-3", 2)
        );

        System.out.println(
                "RenamedFieldMockTest context@"
                        + System.identityHashCode(context)
        );
    }
}
~~~

`PricingTestConfig` has only **one `PricingGateway` bean**, so the target bean is still resolved by type. Business logic runs cleanly, yet field `anotherPricingGateway` introduces a **different fallback qualifier** from `pricingGateway` in A/B.

Spring notes that qualifiers, including field names, are evaluated when deciding whether a separate context is needed for mocked/spied beans. Hence this class illustrates **cache fragmentation from differing declarations**. With multiple same-type beans, renaming the field can also alter **which bean gets overridden** or fail setup; in those cases, use explicit `@Qualifier` or `name`.

To avoid unintended field-name differences, keep field names consistent like A/B or specify the target bean explicitly by name:

~~~java
@MockitoBean(name = "pricingGateway")
PricingGateway gateway;
~~~

This is an **illustrative field snippet** inside a Spring TestContext test class, not a standalone program. When selecting by name, do not treat renaming a field elsewhere as negligible if differing qualifiers/annotations accompany it; compare the full override descriptor to be sure.

## 8. No override declared: a distinct context configuration

**`src/test/java/com/example/testing/NoOverrideTest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(PricingTestConfig.class)
class NoOverrideTest {
    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void total_withoutMock_usesOriginalGatewayBean() {
        assertEquals(
                new BigDecimal("22.00"),
                pricingService.total("ANY-SKU", 2)
        );

        System.out.println(
                "NoOverrideTest context@" + System.identityHashCode(context)
        );
    }
}
~~~

Despite using the same `PricingTestConfig`, `NoOverrideTest` declares **no** `@MockitoBean`; it executes the real `pricingGateway` bean from the test config. Because its bean-override `contextCustomizers` differ, its context is distinct from the mocked context in A/B.

This demonstrates why splitting cache entries here is **semantically essential**: mixing the two contexts would feed mocks to tests expecting real beans and vice versa.

### Summary of example expectations

| Class | Override configuration | Business output | Expected cache relationship |
| --- | --- | --- | --- |
| `SharedMockATest` | `@MockitoBean PricingGateway pricingGateway` | `9.00` from stub `4.50 × 2` | Shares key with B |
| `SharedMockBTest` | Same field declaration as A | `9.00` from stub `3.00 × 3` | Reuses A's context when eligible |
| `RenamedFieldMockTest` | Same type, field `anotherPricingGateway` | `12.00` from stub `6.00 × 2` | May create distinct key via fallback qualifier |
| `NoOverrideTest` | No mock declared | `22.00` from real bean `11.00 × 2` | Key differs from A/B/C |

Business test goals live in **price assertions**. Performance diagnostics live in **cache logs and context reload counts**. Never assert expected cache sharing in tests depending on class execution order, because JUnit/Gradle do not guarantee ordering, cache entries can be evicted, and tests may run across separate JVMs.

## 9. Running the example and inspecting actual cache hits/misses

### 9.1. Dependency setup

This example targets **Spring Boot 3.4/3.5, Spring Framework 6.2, Java 17+, JUnit Jupiter, and Mockito**. In a Gradle Groovy DSL Spring Boot project with compatible Boot plugin, repositories, and dependency management, the relevant configuration looks like:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        showStandardStreams = true
    }
}
~~~

This is a **`build.gradle` snippet**, not a complete build script. `spring-boot-starter-test` in Boot 3.4/3.5 supplies JUnit Jupiter, Mockito, and Spring Test. Since the tests use Spring Framework `@MockitoBean`, Spring Framework **6.2+** must be on the classpath; older Spring Boot projects must upgrade before copying this code.

### 9.2. Enabling `DEBUG` logging for the cache

Spring recommends setting logger category **`org.springframework.test.context.cache`** to `DEBUG`. With Logback, create the following file.

**`src/test/resources/logback-test.xml`:**

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="org.springframework.test.context.cache" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

This alters logging for the **running test suite** without modifying the cache key. If the project already has a logging configuration, integrate this logger category there rather than overwriting existing files.

In full Spring Boot test contexts, you can also configure log levels via Boot properties; for our minimal `@SpringJUnitConfig` demo, `logback-test.xml` is direct whenever Logback is on the test classpath.

### 9.3. Running the classes in one test task / JVM

~~~bash
./gradlew test \
  --tests "com.example.testing.SharedMockATest" \
  --tests "com.example.testing.SharedMockBTest" \
  --tests "com.example.testing.RenamedFieldMockTest" \
  --tests "com.example.testing.NoOverrideTest" \
  --rerun-tasks
~~~

On Windows PowerShell, run on a single line:

~~~powershell
.\gradlew.bat test --tests "com.example.testing.SharedMockATest" --tests "com.example.testing.SharedMockBTest" --tests "com.example.testing.RenamedFieldMockTest" --tests "com.example.testing.NoOverrideTest" --rerun-tasks
~~~

When all assertions pass, all four test classes PASS. Output includes lines like `... context@<number>`; **numbers vary per JVM** and there is no deterministic exact stdout string. Inspect the cache logger for **hit**, **miss**, and **size** statistics alongside context creations.

**Do not count each `DEBUG` line as one context load.** Spring queries the cache at multiple points in a test lifecycle, so hit counters increment multiple times within a single class. Look at *deltas* in stats and matching configs rather than inferring "N hits means N classes shared a context."

A minimal experiment: run A+B together and watch one context load and reuse in the same JVM; add C or D and compare miss/size counts. Absolute counts also depend on other tests in the task, pre-warmed entries, eviction, and Gradle worker settings.

### 9.4. Conditions required to observe cache reuse

- Run the classes in the **same JVM test worker**. Spring TestContext's cache is stored in a `static` structure and **never shared across separate JVM processes**.
- Avoid `@DirtiesContext` unless the context is genuinely tainted; it evicts entries from the cache.
- Keep `@ActiveProfiles`, test properties, dynamic properties, and config classes identical between A and B when isolating mock effects.
- Avoid parallel forks/suites splitting classes across processes when measuring reuse.
- The cache is bounded and evicts least-recently-used entries (LRU); the **default maximum size is 32 contexts**, tunable via `spring.test.context.cache.maxSize` when warranted.
- Running a single class alone or spawning a fresh JVM each time naturally yields zero cross-class cache hits.

Note: `--rerun-tasks` tells Gradle to re-execute tasks rather than reusing build-cache/`UP-TO-DATE` results; it **does not** force Spring context sharing. Spring's cache lives solely inside the **current test JVM process**.

## 10. Mock declarations vs. test-time stubbing

A common misconception is thinking two test classes with different stubbings must have different cache keys:

~~~java
// Classes A and B: same mock bean and identical context configuration.

// Inside A's @Test:
when(pricingGateway.unitPrice("A-1"))
        .thenReturn(new BigDecimal("4.50"));

// Inside B's @Test:
when(pricingGateway.unitPrice("B-2"))
        .thenReturn(new BigDecimal("3.00"));
~~~

Both `when(...).thenReturn(...)` calls execute **after the context has been selected or created**, so normal stubbings are **not part of the cache key**.

By contrast, adding class/field annotations like `@MockitoBean` or changing the overridden target bean happens while the framework builds the **context configuration**, so it affects the key.

This distinction is practical:

| Aspect | Bean override declaration | Stubbing inside test method |
| --- | --- | --- |
| Timing | While constructing test context metadata | While `@Test` executes |
| Example | `@MockitoBean PricingGateway pricingGateway;` | `when(pricingGateway.unitPrice(...)).thenReturn(...)` |
| Context impact | Can change context customizers / cache key | Adds no bean override to key |
| Responsibility | Defines which real bean becomes a mock | Controls mock responses for one scenario |
| Risk | Too many keys → too many context startups | Leaked mock state if reset is misconfigured |

In Spring Framework's Mockito integration, mocks reset per test lifecycle and `reset` setting. Never disable resets to retain mock state in the name of "leveraging the cache": doing so couples one class's tests to another class's stubs and interactions even when sharing a context.

### Changing mock configuration without touching production source classes?

Changing target beans, qualifiers, or mock vs. spy alters the key. Changing **only stubbing statements inside test bodies** leaves the override descriptor unchanged. When a test genuinely needs a different set of beans, a separate context is right; never force non-equivalent configurations into sharing one context.

## 11. Ways to optimize context reuse while keeping tests accurate

### 11.1. Standardize mock field names

When multiple classes override `PaymentGateway`, pick a uniform name like `paymentGateway`. Avoid calling it `gatewayMock` in one class and `mockGateway` in another when targeting the same bean with no distinct qualifier need. Spring's `@MockitoBean`/`@MockitoSpyBean` documentation explicitly recommends this practice.

### 11.2. Specify bean names/qualifiers explicitly when needed

With multiple same-type beans, name the target unambiguously:

~~~java
@MockitoBean(name = "primaryPaymentGateway")
PaymentGateway paymentGateway;
~~~

This is an **illustrative field snippet** requiring a matching bean, Spring TestContext integration, and the right `@MockitoBean` import. When overriding a bean that must exist, consider:

~~~java
@MockitoBean(name = "primaryPaymentGateway", enforceOverride = true)
PaymentGateway paymentGateway;
~~~

`enforceOverride = true` switches the strategy from default **`REPLACE_OR_CREATE`** to **`REPLACE`**, failing the test if the expected bean is absent. This verifies wiring correctness, **not** a trick for forcing cache reuse. Across classes intended to share a context, align all override metadata (including the chosen strategy).

### 11.3. Use composed annotations for shared mock sets

Spring supports `@MockitoBean` at the **type** level and as meta-annotations to share a common mock configuration:

~~~java
package com.example.testing;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.test.context.bean.override.mockito.MockitoBean;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@MockitoBean(types = PricingGateway.class)
public @interface UsesMockPricingGateway {
}
~~~

**Illustrative file `src/test/java/com/example/testing/UsesMockPricingGateway.java`.** It uses a type-level annotation to override `PricingGateway` for any test class annotated `@UsesMockPricingGateway`. When needing multiple mocks, stack repeatable type-level annotations as supported by your API version.

Usage in a test class:

~~~java
@SpringJUnitConfig(PricingTestConfig.class)
@UsesMockPricingGateway
class PricingByCommonAnnotationTest {
    @Autowired
    PricingGateway pricingGateway;

    @Autowired
    PricingService service;

    @Test
    void stillWorks() {
        when(pricingGateway.unitPrice("X"))
                .thenReturn(new BigDecimal("2.00"));
        assertEquals(new BigDecimal("4.00"), service.total("X", 2));
    }
}
~~~

This is an **illustrative class snippet** needing package `com.example.testing` and JUnit/Spring/Mockito/`BigDecimal` imports. `@Autowired` retrieves the overridden bean so the test can stub it; there is **no need** to declare another `@MockitoBean` field, avoiding redundant overrides. Meta-annotations standardize mock sets across classes, though contexts with differing profiles or properties still retain distinct keys.

### 11.4. Do not mock more beans than necessary

Some suites follow an anti-pattern of putting `@MockitoBean` on every dependency across dozens of `@SpringBootTest` classes. If each class mocks a slightly different subset, **context variants** multiply rapidly. Instead, categorize:

- **Business logic unit tests**: instantiate the real service via constructor and mock dependencies with Mockito `@Mock`, starting no Spring context.
- **Web slice tests**: use appropriate slices (e.g., `@WebMvcTest` in Spring Boot 3.x) and mock only needed boundary beans.
- **Integration tests**: keep beans real when verifying wiring/integration; replace only boundaries that cannot or must not execute live.
- **Integration tests with matching needs**: intentionally share configurations and override sets.

A slice test and a full `@SpringBootTest` having separate contexts is **right**; never merge them artificially just to inflate hit counts.

### 11.5. Do not abuse `@DirtiesContext`

`@DirtiesContext` tells Spring the current context is unsafe for reuse. It evicts the context from cache, forcing later tests to reload it. Reserve it for tests that truly alter bean definitions or global context state—**never as a routine broom for Mockito stubbings**.

### 11.6. Keep profiles, properties, and JVMs consistent

Align `@ActiveProfiles`, test configs, `@DynamicPropertySource`, and context hierarchies across classes needing the same environment. Ensure your runner/Gradle does not split classes across multiple JVMs unnecessarily, since static caches never cross process boundaries.

When a suite genuinely needs many valid variants, tuning `spring.test.context.cache.maxSize` **after measuring** can curb LRU evictions at the cost of higher memory. **Increasing cache size never cures unnecessary key differences.**

## 12. Distinguishing `@MockitoBean` and `@MockitoSpyBean` regarding caching

`@MockitoBean` defaults to the **`REPLACE_OR_CREATE`** override strategy: it replaces an existing bean or creates a new one if missing. `enforceOverride = true` switches to **`REPLACE`**, requiring a matching existing bean.

`@MockitoSpyBean` uses **`WRAP`**: it requires an existing matching bean and wraps it in a Mockito spy. That executes partial real code while intercepting/observing methods, behaving differently from full mock replacement. The two do not share an identical "override profile" for reckless context reuse.

On spies, `when(spy.method())` can call the **real method during stubbing**. If the method has side effects or expects uninitialized data, consider `doReturn(...).when(spy).method()` per Mockito/Spring guidance.

In environments with `@Transactional`, `@Cacheable`, or AOP proxies, replacing a bean vs. wrapping with a spy also alters proxy behavior. Thus, differences between `@MockitoBean` and `@MockitoSpyBean` affect not only cache performance, but **test correctness**.

## 13. Extended cache factors: hierarchies, dynamic properties, and contention

### Context hierarchies

Projects using `@ContextHierarchy` can build parent/child contexts. By default, `@MockitoBean`/`@MockitoSpyBean` declarations may apply across hierarchy levels. To override within a single level, specify `contextName` matching the hierarchy configuration name:

~~~java
@MockitoBean(contextName = "web-config")
PaymentGateway paymentGateway;
~~~

This is an **illustrative snippet**, valid only when a matching `@ContextConfiguration(name = "web-config", ...)` exists. Incorrect hierarchy scoping can trigger unintended overrides, context errors, or cache-key shifts across levels.

### `DynamicPropertySource`

`@DynamicPropertySource` registers through a context customizer, so changing its method declaration or dynamic property sources can alter the key. Never assume two tests sharing a URL pattern while pointing at different container ports safely share a context. If dynamic properties vary across classes sharing a base class, `@DirtiesContext` is occasionally required to avoid reusing beans bound to stale properties.

### Parallelism and cache limits

Spring's cache is scoped per JVM; under parallel execution, the framework synchronizes cache access, yet **application state and Mockito stubbings** still need per-test isolation. Multiple tests mutating mocks/beans inside one cached context concurrently risk race conditions if parallelism is uncontrolled.

When diagnosing slow suites, look beyond class count: cache **misses**, context startup costs, evictions, parallel forks, and reset/state synchronization all contribute.

## 14. Common diagnostic mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Two classes share `@SpringBootTest` yet load different contexts | Differing `@MockitoBean`/`@MockBean` sets, field names, qualifiers, profiles, or properties | Compare full merged context configurations and customizers |
| Renaming a mock field increases context count | Fallback qualifier participates in key equality | Keep field names consistent or specify bean name explicitly |
| Added `@Mock` expecting Spring bean replacement | Plain Mockito mock lives only inside test class | Use `@MockitoBean` when overriding inside a Spring context |
| Missing bean yet test still boots | `@MockitoBean` uses `REPLACE_OR_CREATE` by default | Enable `enforceOverride = true` if the bean must exist |
| Test B sees A's stubs when sharing context | Assumed stubs survive across tests or reset misconfigured | Stub independently per test; keep proper lifecycle reset |
| Cache `DEBUG` logs many hits for one class | Spring queries cache multiple times per lifecycle | Read summary totals rather than equating hits with class count |
| No reuse observed across four classes | Gradle uses multiple JVMs/forks, eviction, or `@DirtiesContext` | Run in one test worker/JVM and inspect cache logs |
| Suite creates dozens of contexts | Too many mock/profile/property permutations | Standardize configs and eliminate needless override variations |
| Context reloads whenever running one class at a time | Each individual invocation starts a new JVM | Run classes together in one suite/process to observe caching |
| Mocked tests pass while real integration fails | Over-mocking real beans or bypassing AOP advice | Layer tests and keep real beans in integration tests |
| Error placing `@MockitoBean` inside `@Configuration` class | Spring Framework annotation differs from legacy `@MockBean` usage | Place on supported test classes/fields or use composed annotations |
| Increasing cache `maxSize` did not cut startups | Keys differ rather than suffering eviction | Fix unnecessary key differences before raising memory limits |

## 15. Checklist for measurably improving test speed

Before editing dozens of test classes:

1. **Choose a baseline measurement:** run a representative group of classes in one JVM and record duration, cache misses, and cache size.
2. **Enable the right logger:** `org.springframework.test.context.cache=DEBUG`; separate hit/miss lines from startup logs.
3. **Compare keys:** classes, profiles, test properties, dynamic properties, context customizers, and hierarchies.
4. **Compare overrides:** mocked bean count, target beans, qualifiers, field names, and mock vs. spy.
5. **Prioritize correctness:** never force context sharing when tests need different beans or properties.
6. **Standardize identical setups:** field names, explicit bean names when needed, and composed annotations/base classes for shared mock sets.
7. **Extract pure Java unit tests:** keep Spring contexts out of logic that needs no DI/container.
8. **Eliminate unnecessary reloads:** audit `@DirtiesContext` and avoidable state mutations.
9. **Verify runtime settings:** JVM forks, LRU cache size, parallel test settings, and memory.
10. **Rerun the full suite:** confirm assertions pass with zero state or stubbing leakage between tests.

Quick code-review checklist:

- [ ] Is there a clear reason to mock a Spring bean in context rather than writing a plain Mockito unit test?
- [ ] Do test classes with the same goal use consistent bean types, field names, bean names, and qualifiers?
- [ ] Where a bean must exist, was `@MockitoBean(enforceOverride = true)` considered?
- [ ] Are differing profiles, test properties, and context hierarchies intentional?
- [ ] Is Mockito state configured independently per test without relying on prior tests' stubs?
- [ ] Is `@DirtiesContext` avoided for routine state cleanup?
- [ ] Were cache `DEBUG` logs inspected before/after to verify impact?
- [ ] Were tests compared within the same JVM rather than across separate single-class runs?
- [ ] Were cache optimizations achieved without dropping critical integration tests?

**Conclusion:** mock declarations affect far more than stubbed calls. When mocks/spies **replace beans inside Spring TestContext**, override descriptors become part of the context configuration and can alter the **`ApplicationContext` cache key** via `contextCustomizers`. Keeping field names, qualifiers, and override sets consistent prevents redundant context startups, while context reuse remains valid only when configurations truly match.

### Official references

- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html)
- [Spring Boot 3.4 API — @MockBean deprecated](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
