# `@SpringJUnitConfig` When You Need Spring Without Spring Boot

## Learning Objectives

Spring Boot often provides `@SpringBootTest`, `@WebMvcTest`, and many convenient test slices. However, a class may only need **Dependency Injection (DI), bean configuration, profiles, properties, or the Spring TestContext lifecycle** without starting the entire Boot application. With JUnit Jupiter, the **`@SpringJUnitConfig`** annotation lets you write tests using plain Spring Framework with an explicitly declared `ApplicationContext`.

After this lesson, you will be able to:

- Explain how `@SpringJUnitConfig` combines `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`.
- Write JUnit 5 tests with Spring DI **without needing `@SpringBootApplication` or `@SpringBootTest`**.
- Choose when to use plain Java unit tests, `@SpringJUnitConfig`, Spring Boot slice tests, or `@SpringBootTest`.
- Configure `@Bean` definitions, supply properties via `@TestPropertySource`, inject dependencies into tests, and verify real behavior.
- Understand the TestContext lifecycle, `ApplicationContext` caching, test isolation, `@Transactional` limitations, and common pitfalls.
- Run a Java 17 example with the Gradle Wrapper and confirm tests were executed by JUnit Platform.

This lesson focuses on **Spring TestContext in JUnit Jupiter**. The concepts apply to plain Spring Framework modules or modules inside a Spring Boot repository that only need a narrow context.

## 1. When Do You Need Spring Without Spring Boot?

Suppose you have a pricing module driven by configuration. You want to verify that:

1. `@Configuration` creates `DiscountPolicy` properly.
2. `QuoteService` receives `DiscountPolicy` through Spring DI.
3. The `pricing.vipDiscount` property from the test environment is actually used.
4. The service's discounted output matches requirements.

A plain unit test using `new QuoteService(new DiscountPolicy(...))` can check the **algorithm**. However, it does not verify that Spring read the property, created the beans, and wired dependencies correctly. `@SpringJUnitConfig` fills that gap with a small context built from the configuration you specify.

~~~text
JUnit Jupiter
    |
    | @SpringJUnitConfig(PricingTestConfig.class)
    v
SpringExtension + Spring TestContext
    |
    | reads @ContextConfiguration / @TestPropertySource
    v
AnnotationConfigApplicationContext (appropriate ApplicationContext)
    |
    +-- Bean DiscountPolicy from Environment
    |
    +-- Bean QuoteService receiving DiscountPolicy
    |
    +-- Inject QuoteService into test
    |
    v
@Test -> assert configuration + DI + real logic behavior
~~~

The diagram describes the standard flow of an annotation-configured test. Spring TestContext chooses how to construct the `ApplicationContext` matching the test's declarations; you do not call `new AnnotationConfigApplicationContext(...)` manually in each test.

**Key point:** `@SpringJUnitConfig` **does not enable Spring Boot auto-configuration**, does not search for `@SpringBootApplication`, does not start an embedded server, and does not create a database/DataSource. What exists in the context depends on `@Configuration`, `@ComponentScan`, `@Import`, profiles, property sources, and the components you declare. This keeps tests isolated, while also meaning expected Boot beans will not appear automatically as they do in a full Boot startup.

## 2. What Does `@SpringJUnitConfig` Actually Do?

Semantically, you can view:

~~~java
@SpringJUnitConfig(PricingTestConfig.class)
class PricingSpringTest {
    // ...
}
~~~

as equivalent to the combination:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PricingTestConfig.class)
class PricingSpringTest {
    // ...
}
~~~

Both snippets **illustrate annotation syntax**; they are test class declarations, not standalone runnable Java programs. `@SpringJUnitConfig` is a composed annotation for JUnit Jupiter from **Spring Framework Test**, typically imported from `org.springframework.test.context.junit.jupiter.SpringJUnitConfig`.

Explanation:

- **`SpringExtension`** integrates the Spring TestContext Framework with JUnit Jupiter. It participates in JUnit callbacks to prepare test instances, inject dependencies, and run the relevant TestExecutionListeners.
- **`@ContextConfiguration`** describes the **context to load**: configuration classes, XML files, or context initializers, depending on options. `@SpringJUnitConfig(PricingTestConfig.class)` is shorthand for the `classes` attribute.
- **`@Autowired`** on fields or parameters is handled by Spring when TestContext prepares the test object. The injected object is a real bean from the context unless you explicitly declare a test double in the configuration.
- **`@TestPropertySource`** adds property sources to the test's context; `Environment` and beans can read them.
- **`@ActiveProfiles`** selects active profiles when loading the context, used to toggle beans/properties for testing needs.

`@SpringJUnitConfig` belongs to Spring Test, **not a Spring Boot-specific annotation**. You do not need `spring-boot-starter-test` in a plain Spring Framework project if you already declare `spring-test`, `spring-context`, and JUnit Jupiter properly.

### What Is Spring TestContext?

TestContext is a testing integration layer: it manages the context, injects dependencies into tests, coordinates listeners, and can cache `ApplicationContext` instances across tests with equivalent configurations. This avoids recreating the context for every test method.

This mechanism is **Spring's testing framework**. You still use JUnit Jupiter for discovery, running `@Test`, executing `assertEquals`, and reporting results; SpringExtension provides DI and context support. Therefore, both JUnit Platform configured in Gradle and Spring TestContext dependencies must be present.

## 3. Choosing the Right Test Level

| What Do You Want to Verify? | Usually Sensible Choice | Starts a Spring Context? |
| --- | --- | --- |
| Pure Java algorithms, validation, mapping | JUnit 5 + `new` objects | No |
| Bean wiring, `@Configuration`, properties, `@Profile`, Spring converters, or narrowly configured AOP | `@SpringJUnitConfig` | Yes, per specified configuration |
| Controller binding, validation, and JSON responses in a Spring Boot app | `@WebMvcTest`, `MockMvc` | Yes, a Boot-configured MVC slice |
| Full Spring Boot auto-configuration and multi-bean collaboration | `@SpringBootTest` | Yes, Boot application context |
| Repository/JPA mappings/transactions against a DB | Test slice or integration test with proper DB/infrastructure | Yes, needs DataSource and related config |
| Servlet-based web context in plain Spring Framework | `@SpringJUnitWebConfig` when appropriate | Yes, `WebApplicationContext` |

**Goal determines the tool.** If you only need to check `discount = subtotal × 0.9`, a plain Java unit test is usually simplest and fastest. If you need to prove Spring reads a property and injects the right bean, `@SpringJUnitConfig` adds value. If you need to verify Boot binding from `application.yml`, `@ConfigurationProperties`, web auto-configuration, or application-wide component scanning, `@SpringBootTest`/slices fit better.

There is no rule that "Spring tests are always better than unit tests" or "context tests are always too slow to use." Context cost depends on bean count, auto-configuration, I/O, and test setup. Used within proper boundaries, `@SpringJUnitConfig` is typically smaller and more deterministic than a full Boot context.

## 4. Setting Up a Java 17 + Spring Framework Test + JUnit 5 Project

The following example **does not apply the Spring Boot plugin and has no `@SpringBootApplication`**. Its goal is to run real Java beans inside a Spring TestContext with deterministic properties.

### 4.1. Problem Under Test

Assumed rules:

- VIP customers receive a **10%** discount based on the test property `pricing.vipDiscount=0.10`.
- Regular customers receive no discount.
- Monetary amounts keep two decimal places, rounded with `HALF_UP`.
- `null` or negative subtotals are rejected with `IllegalArgumentException`.
- `QuoteService` is created by Spring with `DiscountPolicy` and uses that policy properly.

Expected output for a VIP subtotal of 100.00 is 90.00; for a regular customer with 100.00 it is 100.00. Expected values are derived from the rules, **not by calling the SUT formula itself to generate expected results**.

File layout:

~~~text
spring-context-test-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/
    │   ├── DiscountPolicy.java
    │   └── QuoteService.java
    └── test/java/com/example/testing/
        ├── PricingTestConfig.java
        └── QuoteServiceSpringTest.java
~~~

All four Java files belong to the `com.example.testing` package. The Gradle Wrapper files are generated by a compatible Gradle installation or already committed in the repository; `gradle-wrapper.jar` is a binary artifact—**do not copy its contents by hand**.

**`settings.gradle`**

~~~groovy
rootProject.name = 'spring-context-test-demo'
~~~

**`build.gradle`** — a consistent illustrative version set: Spring Framework 6.1.15, JUnit Jupiter 5.10.2, JUnit Platform Launcher 1.10.2. Requires JDK 17+ and a compatible Gradle version.

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.15'

    testImplementation 'org.springframework:spring-test:6.1.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Dependency explanation:

- **`spring-context`** provides `ApplicationContext`, `@Configuration`, `@Bean`, `Environment`, and DI support.
- **`spring-test`** provides `@SpringJUnitConfig`, `SpringExtension`, TestContext, and `@TestPropertySource`.
- **`junit-jupiter`** provides the Jupiter API/engine so JUnit 5 discovers `@Test`.
- **`junit-platform-launcher`** provides the runtime launcher for Gradle/JUnit Platform.
- **`useJUnitPlatform()`** configures Gradle's test task to execute on JUnit Platform. Adding dependencies without configuring the runner does not guarantee a working test pipeline.

If you are working inside a Spring Boot module that **already has dependency management**, let the Boot BOM manage compatible Spring/JUnit versions; do not copy raw dependency versions from a plain Spring example into a Boot project and cause Spring Framework version mismatches. This example keeps things simple to illustrate annotations, not to prescribe upgrading packages in existing repositories.

### 4.2. Production Code Is Plain Java

**`src/main/java/com/example/testing/DiscountPolicy.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class DiscountPolicy {

    private final BigDecimal vipDiscount;

    public DiscountPolicy(BigDecimal vipDiscount) {
        Objects.requireNonNull(vipDiscount, "vipDiscount");
        if (vipDiscount.signum() < 0
                || vipDiscount.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "vipDiscount must be between 0 and 1");
        }
        this.vipDiscount = vipDiscount;
    }

    public BigDecimal finalAmount(BigDecimal subtotal, boolean vip) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be non-negative");
        }

        BigDecimal multiplier = vip
                ? BigDecimal.ONE.subtract(vipDiscount)
                : BigDecimal.ONE;

        return subtotal.multiply(multiplier)
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

`DiscountPolicy` has no Spring dependencies. It accepts the rate via constructor, validates it between 0 and 1, and performs monetary math with `BigDecimal`. `setScale(2, HALF_UP)` normalizes the output according to the example's contract.

**`src/main/java/com/example/testing/QuoteService.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.util.Objects;

public final class QuoteService {

    private final DiscountPolicy policy;

    public QuoteService(DiscountPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    public BigDecimal quote(BigDecimal subtotal, boolean vip) {
        return policy.finalAmount(subtotal, vip);
    }
}
~~~

`QuoteService` is also plain Java; all Spring interaction resides in **test bean configuration**. This design separates three questions cleanly: is the algorithm right, which dependency does the service use, and did Spring DI wire that dependency properly?

### 4.3. Test-Only Spring Configuration

**`src/test/java/com/example/testing/PricingTestConfig.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class PricingTestConfig {

    @Bean
    DiscountPolicy discountPolicy(Environment environment) {
        String rateText =
                environment.getRequiredProperty("pricing.vipDiscount");

        return new DiscountPolicy(new BigDecimal(rateText));
    }

    @Bean
    QuoteService quoteService(DiscountPolicy policy) {
        return new QuoteService(policy);
    }
}
~~~

Important details explained:

- `@Configuration` tells Spring this class contains bean factory methods.
- `@Bean` registers `DiscountPolicy` and `QuoteService` in the `ApplicationContext`.
- Spring automatically supplies `Environment` to the bean method, which reads the test property.
- Spring also finds the `DiscountPolicy` bean and passes it to `quoteService(DiscountPolicy policy)`. This is **real DI**, not a mock.
- `@Configuration(proxyBeanMethods = false)` is appropriate because the bean methods are independent: `quoteService` receives its dependency as a parameter instead of calling `discountPolicy()` directly inside the config class. It does not rely on interception between `@Bean` methods.
- The configuration sits in `src/test/java`, so it exists only on this module's test classpath.

If `pricing.vipDiscount` is missing, `getRequiredProperty(...)` throws an exception when the context constructs `DiscountPolicy`; the test fails during context initialization. That signals missing configuration, distinct from a business-logic assertion failure.

### 4.4. Testing with `@SpringJUnitConfig`

**`src/test/java/com/example/testing/QuoteServiceSpringTest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(PricingTestConfig.class)
@TestPropertySource(properties = "pricing.vipDiscount=0.10")
class QuoteServiceSpringTest {

    @Autowired
    private QuoteService quoteService;

    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void vipCustomerGetsDiscountFromTestConfiguration() {
        // Arrange: Spring injects QuoteService and property 0.10
        BigDecimal subtotal = new BigDecimal("100.00");

        // Act
        BigDecimal actual = quoteService.quote(subtotal, true);

        // Assert: 10% discount leaves 90.00
        assertEquals(new BigDecimal("90.00"), actual);
    }

    @Test
    void regularCustomerKeepsFullPrice() {
        BigDecimal actual =
                quoteService.quote(new BigDecimal("100.00"), false);

        assertEquals(new BigDecimal("100.00"), actual);
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> quoteService.quote(new BigDecimal("-1.00"), true));
    }

    @Test
    void injectedServiceIsManagedBySpring() {
        assertSame(
                applicationContext.getBean(QuoteService.class),
                quoteService);
    }
}
~~~

This class uses only:

- `@SpringJUnitConfig(PricingTestConfig.class)` to create the context from the specified bean config.
- `@TestPropertySource` to supply the discount rate to `Environment`.
- `@Autowired` to inject beans into the test; `ApplicationContext` is also supplied by Spring.
- JUnit Jupiter `@Test` and `Assertions` to verify behavior.

There is no `@SpringBootTest`, `@SpringBootApplication`, `@SpringBootConfiguration`, or Boot auto-configuration. **Four test methods produce four test executions** when the class is discovered by JUnit Jupiter. The tests do not print to `System.out`, so there is **no fixed business stdout**; pass/fail results are recorded in Gradle/JUnit reports.

**The fourth test protects wiring:** `applicationContext.getBean(QuoteService.class)` and the `quoteService` field must reference the same singleton bean (the default `@Bean` scope). This is an assertion about **Spring configuration**; it might be redundant if the goal is solely checking formulas, but here it helps learners observe DI directly.

**Do not misread the first test:** when the VIP test passes, it shows that the `0.10` configuration, bean wiring, and calculation work together on the chosen input; it does not prove every pricing rule or edge case. To thoroughly test `DiscountPolicy`, add direct unit tests across many inputs and policies instead of spinning up a context for every case.

### 4.5. Running with the Gradle Wrapper

From the directory containing `settings.gradle` and `gradlew`/`gradlew.bat`:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run this class specifically:

~~~bash
./gradlew test --tests 'com.example.testing.QuoteServiceSpringTest'
~~~

View the Gradle/JUnit reports at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.testing.QuoteServiceSpringTest.xml
~~~

With the complete files above, **4 tests are expected to pass**. `BUILD SUCCESSFUL` is Gradle's message when the build succeeds, not stdout printed by the tests. If the task reports `UP-TO-DATE` or `FROM-CACHE`, results may be reused; to investigate issues, run `./gradlew test --rerun-tasks` when needed.

If the repository does not yet have a Wrapper, generate one with a compatible installed Gradle version, e.g., `gradle wrapper --gradle-version 8.5` for a Java 17 demo project, and keep the wrapper scripts and files in VCS. This is a bootstrap step; in real repositories, use the Gradle version already chosen by the project. The Java toolchain still requires an available JDK 17 or configured provisioning.

## 5. Extending `@SpringJUnitConfig` When More Configuration Is Needed

### 5.1. Longhand Equivalent

If you want to see each piece of the annotation explicitly, the following is semantically equivalent to the example's declaration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PricingTestConfig.class)
@TestPropertySource(properties = "pricing.vipDiscount=0.10")
class QuoteServiceSpringTest {
    // Can include the same @Autowired fields and @Test methods as the example.
}
~~~

This snippet **only illustrates annotation configuration**, as the test body was shown in Section 4.4. If using the longhand form, import `org.junit.jupiter.api.extension.ExtendWith`, `org.springframework.test.context.junit.jupiter.SpringExtension`, and `org.springframework.test.context.ContextConfiguration`.

**Do not add both `@SpringJUnitConfig` and `@ExtendWith(SpringExtension.class)` for the same purpose** without a special reason. Stacking annotations does not make a test "more Spring" or automatically add beans; it only causes confusion because `@SpringJUnitConfig` already includes the needed extension.

### 5.2. Multiple Config Classes

If you have separate groups of beans, you can combine them:

~~~java
@SpringJUnitConfig(classes = {
        CoreConfig.class,
        TestAdapterConfig.class
})
class CoreIntegrationTest {
    // Beans from both @Configuration classes participate in the context.
}
~~~

This is a syntax snippet: `CoreConfig`, `TestAdapterConfig`, and imports must exist in a real project. Do not confuse listing two classes in the annotation with **scanning an entire package**; TestContext loads precisely the specified configurations and any imports/scans those configurations request.

Use `@Import(SomeConfig.class)` inside a config when you need to reuse a group of beans. If `@ComponentScan` is used, restrict the packages to avoid accidentally loading many beans outside the test scope.

### 5.3. Profiles and Properties

When only configuration differs between tests, combine:

~~~java
@SpringJUnitConfig(PricingTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "pricing.vipDiscount=0.20")
class TwentyPercentDiscountTest {
    // Test case for a 20% discount configuration, distinct from the 10% example.
}
~~~

This is a configuration snippet; it is not a runnable program on its own. Import `org.springframework.test.context.ActiveProfiles` and `org.springframework.test.context.TestPropertySource`.

`@ActiveProfiles("test")` activates that profile when TestContext builds the context. It **does not automatically create or read `application-test.yml` by Spring Boot convention** in a plain Spring Framework project. If you want properties from a file, declare `@TestPropertySource(locations = "classpath:pricing-test.properties")` or register a `PropertySource` via standard Spring configuration. `@TestPropertySource(properties = "...")` is convenient and readable for a few small values.

Each combination of configuration, profiles, and property sources can yield a **different context cache key**. The `0.10` test and the `0.20` test should not assume they share the same singleton context.

### 5.4. Injecting Dependencies via Constructor or Method Parameters

The example used field injection for simplicity. In JUnit Jupiter + SpringExtension tests, you can also use Spring-managed constructor injection when appropriately annotated:

~~~java
@SpringJUnitConfig(PricingTestConfig.class)
@TestPropertySource(properties = "pricing.vipDiscount=0.10")
class ConstructorInjectionExampleTest {

    private final QuoteService quoteService;

    @Autowired
    ConstructorInjectionExampleTest(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @Test
    void quoteServiceIsInjected() {
        assertNotNull(quoteService);
    }
}
~~~

This is a snippet with an illustrative body; to compile, add imports for `@Autowired`, `@Test`, `assertNotNull`, `@SpringJUnitConfig`, `@TestPropertySource`, and classes `QuoteService` and `PricingTestConfig` from the example. In a test class with multiple constructors or mixed parameter resolution mechanisms, clarify which parameters JUnit vs. Spring is responsible for providing; adding `@Autowired` on the constructor instructs Spring to resolve it.

SpringExtension also supports resolution on test method parameters (e.g., `@Autowired QuoteService`), though it is optional. Avoid mixing many different injection styles across the same suite unless it improves clarity.

### 5.5. XML Context (When Legacy Projects Require It)

`@SpringJUnitConfig` can point to XML configuration resources using the `locations` attribute from `@ContextConfiguration`; syntax example:

~~~java
@SpringJUnitConfig(locations = "classpath:test-context.xml")
class LegacyXmlContextTest {
    // ...
}
~~~

This snippet is illustrative only and requires `test-context.xml` to exist on the classpath with valid bean definitions. Do not introduce XML configuration into modern projects when Java `@Configuration` suffices. The purpose of `locations` is to allow reusing existing context definitions in legacy projects.

## 6. TestContext Lifecycle and `ApplicationContext` Caching

When JUnit creates a test instance, SpringExtension integrates with TestContext to handle bean injection; TestContext can cache loaded `ApplicationContext` instances to reduce startup time. Across tests with equivalent Spring configurations, the context is typically **reused** rather than recreated for every method.

This has two consequences:

**Benefit:** Creating `ApplicationContext` once for multiple tests with the same configuration speeds up the suite and cuts bean registration overhead. Even when a test class has multiple methods, do not assume the context reopens per method.

**Risk:** Singleton beans holding **mutable state** can retain data across methods or test classes. If test A modifies singleton state without resetting it, test B may become order-dependent or fail intermittently. This is a test isolation bug, not necessarily a bug in `@SpringJUnitConfig`.

### How to Keep Tests Independent

- Prefer **stateless** domain/service beans whenever possible. For example, `DiscountPolicy` and `QuoteService` store no mutable data across tests.
- Give each test its own inputs; do not modify shared properties or singleton fields and forget to reset them.
- If a fake database/repository retains state, clear the data or create isolated fixtures matching the lifecycle.
- If a test spawns threads, schedulers, or system side effects, stop/close resources properly; context caching does not isolate external side effects.
- Only use `@DirtiesContext` when a test **truly dirties context configuration or state** to the extent it cannot be safely reused. This annotation forces Spring to evict the context from cache and reload when needed, adding cost. It is not a "reset everything" button to slap onto every test by default.
- For transactional testing, TestContext supports transaction management when a `PlatformTransactionManager` and proper listeners/configuration are present. In the plain Spring example without a DataSource or transaction manager, putting `@Transactional` on a test does not create a database or guarantee rollback.

### Caching Is Not Stateful Chaining

Do not write tests designed around "test 1 adds an item, test 2 sees the added item"; JUnit does not guarantee execution in the order you expect unless explicitly ordered, and ordering is generally unnecessary for independent unit/integration tests. Each test should prepare its own initial state, or use fixtures placed in the appropriate lifecycle hook with controlled resets.

## 7. Things `@SpringJUnitConfig` Does Not Provide Automatically

| Feature You Want to Use | Why It May Be Missing | What Needs to Be Added? |
| --- | --- | --- |
| A bean by interface | Bean not declared or component scan missing | `@Bean`, `@Import`, or scoped `@ComponentScan` |
| Properties from `application.yml` | Boot conventions are not enabled | `@TestPropertySource`, `@PropertySource` with appropriate format, or custom property setup |
| Embedded HTTP server | No Boot web server lifecycle by default | Appropriate web context or Boot test depending on goal |
| `MockMvc` auto-config | MVC setup/Boot auto-config not enabled | Web test context or explicit `MockMvc` setup; in Boot you can use `@WebMvcTest` |
| JPA `EntityManager`, repositories, and DB | No persistence config, DataSource, or transaction manager | Dedicated persistence/integration test configuration |
| Spring Security filter chain | Security config not loaded | Import/configure Security when the contract requires it |
| `@ConfigurationProperties` bound by Boot conventions | Boot binder/auto-config not automatically present | Suitable Boot test or explicit binding setup |
| A "guaranteed fast run" | Loaded beans/infrastructure depend on actual config | Keep the context narrow and fixtures independent |
| Mockito mocks for every dependency | Spring TestContext does not auto-mock | Declare test doubles via an appropriate mechanism or use real objects |

A common misconception: inside a Spring Boot application, a `@Configuration` carrying `@ComponentScan` on a broad root package can pull in many beans, including beans tied to Boot/application config. When that happens, the test is no longer "lightweight" as expected. **Explicitly bound classes/imports/scans** rather than assuming the annotation name implies a "slice."

Conversely, if a test needs to verify full Boot behavior yet hand-picks a few beans in `@SpringJUnitConfig`, passing the test does not prove the Boot application can start. Both test types must provide complementary evidence.

## 8. Comparison with `@SpringBootTest` and `@SpringJUnitWebConfig`

### `@SpringJUnitConfig` vs. `@SpringBootTest`

`@SpringJUnitConfig` explicitly names Spring context configuration and activates SpringExtension via Spring Test. `@SpringBootTest` uses Spring Boot's test infrastructure to locate/initialize Boot application configuration and apply appropriate Boot mechanisms. Both use JUnit Jupiter via SpringExtension when configured properly, but **the startup scope and enabled features differ**.

For plain Spring Framework modules, use `@SpringJUnitConfig` to verify bean wiring/configuration. For Boot modules where tests need property binding or Boot's security/web/repository auto-configuration, use a Boot test slice or `@SpringBootTest` according to the goal. Do not assume `@SpringBootTest` always starts a real HTTP server: the default `webEnvironment` mode does not require a server on a real port, whereas random/defined port modes change that behavior.

### `@SpringJUnitWebConfig`

Spring Framework also provides `@SpringJUnitWebConfig` for JUnit Jupiter with a **`WebApplicationContext`**; this annotation combines most of `@SpringJUnitConfig` with `@WebAppConfiguration`. It fits when testing plain Spring MVC web configurations.

However, if the project uses Spring Boot and only needs to test controller serialization/binding, `@WebMvcTest` with `MockMvc` usually expresses intent more clearly. `@SpringJUnitWebConfig` does not enable Boot's MVC auto-configuration equivalent to `@WebMvcTest`.

## 9. Common Errors and How to Resolve Them

| Symptom | Possible Cause | How to Diagnose/Fix |
| --- | --- | --- |
| `No qualifying bean of type…` | Required bean not declared or config not loaded | Check `@SpringJUnitConfig(classes=...)`, `@Bean`, imports/scans, profiles |
| `Failed to load ApplicationContext` | Broken bean config, missing property, exception during bean creation | Read the **root cause** down the stack trace, not just the first line |
| Property `pricing.vipDiscount` not found | Missing `@TestPropertySource`, wrong key, or wrong property source | Verify key and annotation, confirm context uses the intended config |
| JUnit discovers no tests | Missing JUnit Jupiter engine/`useJUnitPlatform()` | Check Gradle test dependencies, task config, and `org.junit.jupiter.api.Test` |
| `@Autowired` field is null | Missing SpringExtension, test instantiated/handled outside TestContext, or missing bean | Use `@SpringJUnitConfig` properly on a JUnit Jupiter test |
| Wrong `org.junit.Test` imported | JUnit 4 vs. Jupiter differ | Import `org.junit.jupiter.api.Test`; for legacy tests use appropriate migration/engine |
| Extra beans make test very slow | Component scan too wide or config pulls I/O | Restrict test config classes and required imports |
| Test fails in full suite but passes alone | Shared mutable singleton state, context cache, shared DB, ordering | Reset fixtures, eliminate cross-test state, use `@DirtiesContext` deliberately |
| `@Transactional` does not roll back as expected | Missing transaction manager or test not managed properly | Configure persistence/transaction manager and appropriate test level |
| `@ConfigurationProperties` not bound | Using plain Spring while expecting Boot Binder | Use a Boot test or configure binding explicitly |
| Duplicate context/bean definitions or two beans of same type | Repeated imports/configs or two indistinguishable beans | Clarify test config, use `@Qualifier` when business logic requires it |
| Test only verifies bean existence | Fails to check behavior or whether property actually applied | Assert both business results and property values affecting output |
| Context fails due to missing external service | Test config accidentally pulls external dependency | Use fake/test adapters, separate boundaries cleanly, drop unneeded scans |
| Context not cached as expected | Different configs, profiles, properties; `@DirtiesContext` active | Inspect test configs; avoid unnecessary variations if equivalent |

### Pinpointing Which Layer Failed

If JUnit reports **no tests found**, start with the runner, imports, and dependencies before assuming Spring beans are broken.

If JUnit ran but Spring reports **Failed to load ApplicationContext**, read the nearest root cause in the stack trace: missing bean, missing property, exception thrown in a bean factory method, or mismatched profile.

If the context loaded and injection succeeded but `assertEquals` fails, check **business logic, expected values, or property values**. Do not tweak Gradle configuration or add `@DirtiesContext` as a default fix for a value mismatch assertion.

If a test fails only in CI, check JDK/Gradle versions, dependency repositories, environment variables, property resources, and external I/O. A test using strictly Java beans like the example is far easier to reproduce than one accidentally hitting a database or network.

## 10. Workflow for Applying to a Codebase

1. **State the behavior to prove.** If it is a pure Java formula, prefer direct unit tests. If it is bean wiring/properties/profiles/AOP, consider Spring TestContext.
2. **Create the smallest possible test config.** Use `@Configuration` and only the `@Bean`/`@Import` entries truly needed; limit component scanning.
3. **Use `@SpringJUnitConfig(MyConfig.class)`.** It already integrates JUnit Jupiter and SpringExtension. Add `@TestPropertySource`/`@ActiveProfiles` when required.
4. **Inject beans via `@Autowired`.** Keep test setup clear; do not mix manual `new` service instantiation and Spring-injected beans without explaining the boundary.
5. **Write assertions from the contract.** For the pricing example, verify VIP 100.00 -> 90.00 and regular -> 100.00; ensure invalid inputs are not silently accepted.
6. **Run with the Wrapper and read the report.** Confirm tests were discovered, the context loaded, assertions passed, and no unintended I/O occurred.
7. **Keep state isolated.** Remember contexts can be cached and singletons persist across runs; clean up state intentionally.
8. **Add tests at the right level if needed.** If proving HTTP/DB/Boot auto-config is required, step up to an MVC slice or Boot integration test; do not infer whole-system correctness from a small context test.

## 11. Practice Exercises

**Exercise A — Changing properties:** Change `@TestPropertySource(properties = "pricing.vipDiscount=0.10")` to `0.20`. Before running, update the VIP expected value from 90.00 to 80.00 (for subtotal 100.00). If the bean reads the property properly, the test must pass. If you leave expected as 90.00, the VIP test must fail; then restore the original value.

**Exercise B — Removing a bean:** Temporarily remove `@Bean QuoteService quoteService(...)` from `PricingTestConfig`. Predict that the context will fail to inject the test's `QuoteService` field. Observe the root cause and restore it. This exercise proves the test genuinely checks Spring wiring rather than constructing the service outside the context.

**Exercise C — Plain unit test:** Write a `DiscountPolicyTest` without any Spring annotations, instantiating `new DiscountPolicy(new BigDecimal("0.10"))`. Test three cases: 0.00, 10.05 (rounding `HALF_UP` to 9.05 if VIP), and a negative subtotal. Explain why no Spring context is needed for these assertions.

**Exercise D — Profiles:** Create two `@Configuration` classes with `@Profile("test")` and `@Profile("prod")`, defining beans implementing the same interface per profile. Use `@SpringJUnitConfig` + `@ActiveProfiles("test")` to verify the test bean is injected. Avoid scanning the entire package or importing both beans unconditionally.

**Exercise E — Context cache:** Create a singleton fake repository holding a mutable list, write tests that add data, and run multiple test methods. Observe the risk of state leakage when the context is reused. Fix it by clearing the list before each test or using an isolated fixture; only use `@DirtiesContext` if a clean reset is impractical.

## 12. Checklist Before Finishing

- [ ] Am I verifying **Spring configuration/wiring**, not merely a pure Java calculation?
- [ ] Does `@SpringJUnitConfig` point to the right config class, with JUnit Jupiter and `spring-test` on the test classpath?
- [ ] Is `useJUnitPlatform()` applied to the Gradle test task?
- [ ] Are all required beans created by the specified context, without relying accidentally on Boot auto-config?
- [ ] Do properties and profiles have explicit sources (`@TestPropertySource`/`@ActiveProfiles` or equivalent config)?
- [ ] Do assertions verify meaningful behavior, not just "bean != null"?
- [ ] Are tests free from dependencies on shared singleton state, execution order, or uncontrolled infrastructure?
- [ ] When verifying HTTP, transactions, repositories, or Boot auto-config, did I use the matching test layer?
- [ ] Does the Gradle/JUnit report show the actual test count executed and clear failure messages pointing to causes?

**Remember:** `@SpringJUnitConfig` is a concise way to use **SpringExtension + `@ContextConfiguration`** in JUnit Jupiter. It fits when you need **Spring DI and TestContext** with an explicit set of configured beans, without Spring Boot application startup. Verify algorithms with plain unit tests whenever possible; verify Beans/Properties/Profiles with a small Spring context; expand to Boot or real infrastructure only when the contract demands it.
