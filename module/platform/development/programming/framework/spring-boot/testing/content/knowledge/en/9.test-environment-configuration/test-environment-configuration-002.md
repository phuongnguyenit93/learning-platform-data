# Nested @Configuration and @TestConfiguration in Spring Boot Test Classes

## 1. Problem: a test needs custom configuration while still knowing which ApplicationContext is loaded

In Spring Boot testing, we often want to introduce a supporting bean into the test environment: a fixed clock to test expiration dates, a fake HTTP client, configuration data, a behavior-recording bean, or a simple replacement implementation for a dependency. Declarations for configuration classes **nested inside a test** look very similar:

~~~java
@Configuration
static class LocalConfig { /* @Bean ... */ }

@TestConfiguration
static class TestOnlyConfig { /* @Bean ... */ }
~~~

However, in Spring Boot's test configuration auto-detection mechanism, the two annotations have **very different semantics**:

- **static nested @Configuration:** Typically treated by Spring Test as the **default configuration declared by the test**. For a `@SpringBootTest` that does not explicitly specify `classes`, this nested configuration is used **instead of the primary application configuration** that Spring Boot normally finds from `@SpringBootApplication` or `@SpringBootConfiguration`. This is a way to build a small, intentional context, but it very easily causes production beans to disappear.
- **static nested @TestConfiguration:** Spring Boot's dedicated test configuration annotation. When declared nested inside a test in the supported pattern, it is **added on top of the primary application configuration**, keeping application beans while adding test beans.
- **Top-level @TestConfiguration** (a separate class under `src/test/java`) is typically excluded from Spring Boot's default component scanning; when needed, **@Import** it explicitly into the test.
- **JUnit Jupiter @Nested** is a mechanism for *grouping test methods* using a non-static member class; it is **not the same concept** as a static nested configuration class. Spring Test also has `@NestedTestConfiguration` to control inheritance of test annotations across JUnit `@Nested` classes.

This lesson focuses on **test environment configuration**: configuration discovery, bean scope, usage patterns, interaction with Spring Boot, common pitfalls, and how to verify the right context has loaded. The examples use **Spring Boot 3.3.5, Spring Framework 6.x, Java 17, JUnit Jupiter, and Gradle**.

## 2. How does Spring Boot find the primary configuration for @SpringBootTest?

In a properly structured project:

~~~text
src/main/java/demo/config/
  DemoApplication.java        @SpringBootApplication
  TimeService.java            @Service
src/test/java/demo/config/
  MyServiceTest.java          @SpringBootTest
~~~

If `MyServiceTest` does not declare specific configuration classes, `@SpringBootTest` normally walks up parent packages from the test's package until it encounters a **`@SpringBootApplication`** or **`@SpringBootConfiguration`** class. Spring Boot then loads that primary configuration along with beans within its component scanning and imported configuration scope.

Example:

~~~java
@SpringBootTest
class MyServiceTest {
    // Spring Boot can automatically find demo.config.DemoApplication.
}
~~~

The snippet above only illustrates the annotation on a test, not a standalone Java program. Crucially: **primary configuration auto-detection** is only the behavior when no configuration has been explicitly specified by the test through a mechanism recognized by Spring Test. If a test declares **@SpringBootTest(classes = ...)** or **@ContextConfiguration(classes = ...)**, the outcome depends on the specified classes/loader and imports.

According to the Spring Boot 3.3 documentation, a **static nested @Configuration** class in a test can act as the test-provided primary configuration. When it does, Spring Boot no longer uses the auto-discovered `@SpringBootApplication` configuration. By contrast, a **static nested @TestConfiguration** has an **additive** role.

This practical difference matters more than the fact that both annotations register `@Bean` methods. `@TestConfiguration` itself is built on Spring's configuration mechanism, but Spring Boot applies its own test policy to it.

## 3. Quick comparison of @Configuration, @TestConfiguration, and @Import

| Declaration style | Typical role in Spring Boot tests | Loads main app configuration automatically? | When to choose |
|---|---|---|---|
| No nested config; only `@SpringBootTest` | Searches for `@SpringBootApplication`/`@SpringBootConfiguration` | Yes, if found and not replaced by explicit config | Normal full-context test |
| **static nested @Configuration** | Provides root configuration for the test | Normally **does not** use auto-discovered app config anymore | Testing a small context with only desired beans |
| **static nested @TestConfiguration** | Adds test beans onto the primary configuration | Yes, under normal auto-discovery | Adding a fixed Clock, fake dependency, helper bean |
| **@Import(TopLevelTestConfig.class)** | Imports the specified config class | Yes, when used with normal `@SpringBootTest` | Intentionally sharing test config across classes |
| **@SpringBootTest(classes = DemoApplication.class)** | Selects explicit primary sources | Loads only specified sources and what they pull in | When exact control over config source is needed |
| **@ContextConfiguration(classes = LocalConfig.class)** | Directly selects configuration for Spring TestContext | Depends on loader and cooperating annotations | Integration context test with specific configuration |

**Note:** "Additive" does not mean automatically replacing a bean with the same name. If two configurations register the same bean name and bean overriding is disabled, the context may fail to start. To pick a test bean of the same **type** while keeping the old bean, you can place **@Primary** on the test bean with a **different bean name**, or use **@Qualifier**. Choose the technique that matches your test goal.

## 4. Why are nested configuration classes usually declared static?

Common Java pattern:

~~~java
@SpringBootTest
class ExampleTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class LocalTestBeans {

        @Bean
        TestMarker marker() {
            return new TestMarker("test");
        }
    }

    record TestMarker(String value) {
    }
}
~~~

This is an illustrative snippet: to compile, it needs imports for Spring Test/Bean, JUnit if it has `@Test` methods, and a Spring Boot application so `@SpringBootTest` can find a primary source.

**static** allows Spring to instantiate the nested configuration class without needing an instance of the enclosing test class. A Java non-static inner class holds an implicit reference to the outer test instance, which does not fit the configuration pattern auto-discovered by TestContext. When you want nested config auto-discovered, use a **static nested class**.

With **@TestConfiguration(proxyBeanMethods = false)**:

- Spring registers the `@Bean` methods into the test context.
- `proxyBeanMethods = false` avoids proxying inter-`@Bean` method calls when methods do not call each other; it is well suited for independent beans.
- If one `@Bean` depends on another bean, prefer letting Spring **pass the dependency via a `@Bean` parameter or constructor** rather than calling another `@Bean` method directly inside the same config and assuming singleton semantics when `proxyBeanMethods = false`.

**Do not use JUnit's @Nested to turn a test group into a Spring configuration class**. The two kinds of "nested" differ in both purpose and lifecycle; Section 10 distinguishes them clearly.

## 5. Complete example: one application and three ways to configure tests

We will have a small Spring Boot application with a `TimeService` receiving `Clock` via constructor. The production bean uses **Clock.systemUTC()**; tests want to swap the time source for deterministic assertions. There are three independent cases:

1. **Nested @TestConfiguration:** Keeps application beans and adds a `Clock.fixed` marked `@Primary`.
2. **Nested @Configuration:** Uses only the test's small configuration; does not load the production service and marker bean.
3. **Top-level @TestConfiguration + @Import:** Brings a helper bean from a separate test file into the application context.

File layout:

~~~text
settings.gradle
build.gradle
src/main/java/demo/config/DemoApplication.java
src/main/java/demo/config/TimeService.java
src/test/java/demo/config/NestedTestConfigurationAdditionTest.java
src/test/java/demo/config/NestedConfigurationReplacementTest.java
src/test/java/demo/config/SharedTestConfiguration.java
src/test/java/demo/config/TopLevelImportTest.java
src/test/java/demo/config/JupiterNestedGroupsTest.java
~~~

### 5.1. Gradle build

**settings.gradle**

~~~groovy
rootProject.name = 'spring-test-nested-configuration'
~~~

**build.gradle**

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
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Spring Boot `starter-test` includes JUnit Jupiter, AssertJ, and Spring Test utilities. This example uses only the base Starter, needing no web server or database. **useJUnitPlatform()** ensures Gradle runs JUnit Jupiter.

### 5.2. Application code

**src/main/java/demo/config/DemoApplication.java**

~~~java
package demo.config;

import java.time.Clock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }

    @Bean
    ProductionMarker productionMarker() {
        return new ProductionMarker("application");
    }
}

record ProductionMarker(String value) {
}
~~~

The same Java file contains **one public class** matching the filename and a package-private record used by tests in the same package. `ProductionMarker` helps verify whether beans from the primary configuration were loaded.

**src/main/java/demo/config/TimeService.java**

~~~java
package demo.config;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class TimeService {

    private final Clock clock;

    public TimeService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Instant now() {
        return clock.instant();
    }
}
~~~

`TimeService` is component-scanned by `@SpringBootApplication` in `demo.config`. In the normal application, only the `Clock` **systemClock** exists, so the constructor receives the system Clock. When a test adds a `Clock` **fixedClock** marked `@Primary`, the service in that test context receives the fixed Clock.

### 5.3. Nested @TestConfiguration: **adds** configuration without replacing the application

**src/test/java/demo/config/NestedTestConfigurationAdditionTest.java**

~~~java
package demo.config;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NestedTestConfigurationAdditionTest {

    private static final Instant FIXED_TIME =
            Instant.parse("2026-11-08T10:00:00Z");

    @Autowired
    TimeService timeService;

    @Autowired
    ProductionMarker productionMarker;

    @Autowired
    TestMarker testMarker;

    @Autowired
    @Qualifier("systemClock")
    Clock systemClock;

    @Autowired
    @Qualifier("fixedClock")
    Clock fixedClock;

    @Test
    void keepsApplicationBeansAndUsesPrimaryTestClock() {
        assertThat(productionMarker.value()).isEqualTo("application");
        assertThat(testMarker.value()).isEqualTo("test-only");
        assertThat(timeService.now()).isEqualTo(FIXED_TIME);
        assertThat(fixedClock.instant()).isEqualTo(FIXED_TIME);
        assertThat(systemClock).isNotSameAs(fixedClock);
    }

    record TestMarker(String value) {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockTestConfig {

        @Bean
        @Primary
        Clock fixedClock() {
            return Clock.fixed(FIXED_TIME, ZoneOffset.UTC);
        }

        @Bean
        TestMarker testMarker() {
            return new TestMarker("test-only");
        }
    }
}
~~~

Exact explanation following the loading process:

1. `@SpringBootTest` finds `DemoApplication` (the primary class) from the test's package, then loads `TimeService` and `productionMarker`.
2. Spring Boot also detects the **static nested @TestConfiguration** class in the test to add `fixedClock` and `testMarker`.
3. The context has two beans of type `Clock`: `systemClock` and `fixedClock`. Because `fixedClock` has **@Primary**, injecting `Clock` into `TimeService` selects `fixedClock`.
4. There is no bean name conflict: `systemClock` and `fixedClock` have **different names**. Thus bean-definition overriding does not need to be enabled.
5. The test verifies **both sides**: `productionMarker` proves the primary configuration is still present; `testMarker` proves the test config was loaded; `timeService.now()` proves the right `Clock` was selected.

**This is the best-fitting case when you want to "keep the real application and add a few test-specific beans."** A nested `@TestConfiguration` like this does not require an explicit `@Import` when auto-detected by the Spring Boot test loader.

### 5.4. Nested @Configuration: **replaces auto-discovered primary sources** in this test

**src/test/java/demo/config/NestedConfigurationReplacementTest.java**

~~~java
package demo.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NestedConfigurationReplacementTest {

    @Autowired
    ApplicationContext context;

    @Test
    void usesOnlyExplicitNestedConfiguration() {
        assertThat(context.getBean(LocalMarker.class).value())
                .isEqualTo("isolated");

        assertThat(context.getBeansOfType(ProductionMarker.class))
                .isEmpty();
        assertThat(context.getBeansOfType(TimeService.class))
                .isEmpty();
    }

    record LocalMarker(String value) {
    }

    @Configuration(proxyBeanMethods = false)
    static class IsolatedBeans {

        @Bean
        LocalMarker localMarker() {
            return new LocalMarker("isolated");
        }
    }
}
~~~

With a test that does not explicitly declare `classes` and this example's package layout, Spring Boot chooses the static nested configuration **IsolatedBeans** as the test configuration source. Because it has no `@ComponentScan` and does not import `DemoApplication`, **TimeService** and **ProductionMarker** from the main application are not created. The assertions check this directly against `ApplicationContext`.

This is the case of **intentionally replacing** configuration to test an isolated group of beans. If you add a nested `@Configuration` just because you want an extra `Clock` while still expecting Spring Boot to load the whole application automatically, the test may fail with **NoSuchBeanDefinitionException** or required beans may not be found. In the additive case, switch to **@TestConfiguration**.

**Do not equate "replacing the auto-discovered primary configuration" with "all other beans disappear regardless of circumstances."** If your nested `@Configuration` adds its own `@ComponentScan`, `@Import(DemoApplication.class)`, enables auto-configuration, or the test has other explicit configuration, those beans can still be brought in. The result always depends on the actual sources.

### 5.5. Top-level @TestConfiguration: explicitly import when sharing is needed

**src/test/java/demo/config/SharedTestConfiguration.java**

~~~java
package demo.config;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class SharedTestConfiguration {

    @Bean
    ImportedMarker importedMarker() {
        return new ImportedMarker("from-import");
    }

    public record ImportedMarker(String value) {
    }
}
~~~

**src/test/java/demo/config/TopLevelImportTest.java**

~~~java
package demo.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(SharedTestConfiguration.class)
class TopLevelImportTest {

    @Autowired
    ProductionMarker productionMarker;

    @Autowired
    SharedTestConfiguration.ImportedMarker importedMarker;

    @Test
    void keepsApplicationAndImportsSharedTestBeans() {
        assertThat(productionMarker.value()).isEqualTo("application");
        assertThat(importedMarker.value()).isEqualTo("from-import");
    }
}
~~~

When `SharedTestConfiguration` sits at the **top level** in `src/test/java`, annotating it with `@TestConfiguration` helps Spring Boot avoid picking it up as regular configuration via `@SpringBootApplication`'s default component scan. A test that needs it adds **@Import(SharedTestConfiguration.class)**.

Differences to note:
- `@Import` can import a `@Configuration` or `@TestConfiguration` class; in this example the goal is to **limit the scope of test-only configuration**.
- Using a top-level `@Configuration` inside the component scan area can accidentally cause test beans to appear in many other tests. Spring Boot excludes `@TestConfiguration` from default scanning to reduce that risk.
- If you configure a custom **@ComponentScan** on the application, `@SpringBootApplication`'s default test filters may no longer apply as expected; check/restore `TypeExcludeFilter` per the Spring Boot guide.
- When reusing test configuration across multiple classes, `@Import` makes the configuration dependency visible right at the call site. It also affects the context cache key.

### 5.6. JUnit Jupiter @Nested differs from static nested configuration

**src/test/java/demo/config/JupiterNestedGroupsTest.java**

~~~java
package demo.config;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class JupiterNestedGroupsTest {

    @Nested
    class GroupOfAssertions {

        @Autowired
        ProductionMarker productionMarker;

        @Test
        void inheritsSpringTestConfigurationByDefault() {
            assertThat(productionMarker.value())
                    .isEqualTo("application");
        }
    }
}
~~~

JUnit Jupiter's **@Nested** uses a **non-static inner class** to group tests. Spring TestContext supports inheriting test configuration from the outer class; the default mode is **INHERIT** in corresponding Spring Framework 6.x versions. You can use **@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)** if you want a nested test class to manage its own test configuration annotations, but this behavior is completely different from putting **@TestConfiguration** on a **static config class**.

To remember easily:

| Kind of "nested" | Usually static? | Annotation | Purpose |
|---|---|---|---|
| Nested config | **Yes** | `@Configuration` | Defines a context/configuration source |
| Nested test-only config | **Yes** | `@TestConfiguration` | Adds test beans |
| JUnit test grouping class | **No** | `@Nested` | Groups `@Test` methods in JUnit Jupiter |
| Annotation inheritance policy for nested test classes | Applied to test class | `@NestedTestConfiguration` | `INHERIT`/`OVERRIDE` Spring TestContext configuration |

## 6. Running the example, reading results, and verifying reality

Assuming the project already has the **Gradle Wrapper**:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

The files above are the complete source code and Gradle configuration of the example. The `./gradlew` command requires the corresponding wrapper files; if creating the project manually from scratch without a wrapper, generate it using an installed compatible Gradle version or run **gradle test** with a version compatible with Spring Boot 3.3.x.

The test suite should run the methods of:
- `NestedTestConfigurationAdditionTest`: proves **application beans + test beans** coexist and the `@Primary` Clock is selected.
- `NestedConfigurationReplacementTest`: proves **only the small test context** is created per the nested `@Configuration`.
- `TopLevelImportTest`: proves the **bean imported via @Import** is present alongside application beans.
- `JupiterNestedGroupsTest`: proves a **@Nested test** can inherit Spring configuration from the outer test.

Inspect the HTML report at **build/reports/tests/test/index.html**. If an assertion fails, check bean names, package paths, classpath, annotations, and configuration discovery before adding workarounds.

The example requires no database configuration and opens no HTTP port: **@SpringBootTest(webEnvironment = NONE)** still loads the Spring context without creating a web environment. These tests are **Spring configuration integration tests**, not pure unit tests (even though the assertions are very short). For Java logic that needs no container, use `new Service(fakeDependency)` or Mockito/JUnit Jupiter for faster tests.

**Determinism:** Do not compare the system time of `productionClock` with a fixed `Instant`. The example only checks that `systemClock` and `fixedClock` are two distinct instances, then verifies `TimeService` uses `fixedClock` with the exact timestamp.

## 7. Common mistakes when replacing beans in tests

### 7.1. @TestConfiguration does not automatically override a bean with the same name

In Spring Boot 3.3.x, **spring.main.allow-bean-definition-overriding** defaults to **false**. If a test adds a bean with the exact same name as a production bean, you may get **BeanDefinitionOverrideException** instead of Spring silently replacing it.

Collision-prone example (illustrative, not included in the passing examples above):

~~~java
// In the application:
@Bean
Clock systemClock() { return Clock.systemUTC(); }

// In the test config, also named systemClock:
@Bean
Clock systemClock() { return Clock.fixed(fixed, ZoneOffset.UTC); }
~~~

If both are loaded, this is a bean definition name conflict. A safer approach when the goal is only to swap the bean injected by type:
- Keep the production bean named **systemClock**.
- Add the test bean named **fixedClock**.
- Place **@Primary** on `fixedClock`.
- Inject `Clock` into `TimeService` by type, without hard-coding `@Qualifier("systemClock")` in the service if you want `@Primary` to take effect.

If production code already uses `@Qualifier("systemClock")`, `@Primary` will not automatically bypass that qualifier. In that case, design the test to match the real qualifier, or use a bean replacement mechanism supported by your Spring Boot version.

**Do not enable `allow-bean-definition-overriding=true` globally just to mask confusion.** If you must replace a definition by name, consider a test bean replacement mechanism and keep names/versions and test scope well controlled.

### 7.2. @Primary does not "replace" the old bean in the ApplicationContext

`@Primary` is a **rule for selecting a dependency when multiple candidates match by type**. The old bean still exists and can be retrieved by name/qualifier. If the system runs both beans and some component injects using a different qualifier, merely adding `@Primary` may not replace every usage path. Always verify **the bean the SUT actually receives**, as in the `TimeService.now()` example.

When a test truly needs to replace a dependency across the whole flow, you can use the Spring Boot Test mocking/replacement mechanism for your version; for example, Spring Boot 3.3.x has **@MockBean**. However, a mock does not automatically provide behavior like `Clock.fixed`: you still have to stub methods. For `Clock`, a `@Primary` fake bean is simple and deterministic.

### 7.3. @TestConfiguration and @Import differ from @Profile

**@Profile("test")** is only a condition enabling a bean when the matching profile is active. **@ActiveProfiles("test")** activates the profile for the test, but does not by itself decide the primary configuration class. If you put `@Profile` on a test `@Configuration` that is also discovered/imported in another way, you must account for both **config discovery** and **profile conditions**.

Do not mechanically put `@ActiveProfiles("test")` on every test; different profiles change context cache keys, properties, and bean conditions. Only use a profile when the test genuinely needs that configuration branch.

## 8. How to choose between @Import, nested @TestConfiguration, and @SpringBootTest(classes = ...)

**Scenario A: Adding a bean needed by a single test class.**

Use a **static nested @TestConfiguration** at the bottom of the test class—for example, a fixed clock, fake publisher, or test marker bean. This makes the scope of usage easiest to see: code and configuration sit right next to the assertions.

**Scenario B: Multiple test classes need the same set of helper beans.**

Create a **top-level @TestConfiguration** in `src/test/java` and use **@Import** on the classes that need it. This prevents the configuration from being scanned into every context automatically and shares test fixtures intentionally.

**Scenario C: You only want to load a few beans, not the entire app.**

Use a **nested @Configuration** with appropriate Spring TestContext setup or **@SpringBootTest(classes = SmallConfig.class)**. If you do not need Spring Boot's test bootstrap features, you can use Spring Framework Test's **@SpringJUnitConfig(SmallConfig.class)** instead of loading the full application.

**Scenario D: You want to test a web or JPA slice rather than the full context.**

Prefer a **test slice** such as `@WebMvcTest` or `@DataJpaTest`, then `@Import` the supporting configuration beans appropriate to that scope. Understand that slices filter auto-configuration and component scanning; importing an entire application configuration can make the slice heavy and turn the test into a broader scope than intended.

**Scenario E: Explicitly configure all primary sources.**

Use **@SpringBootTest(classes = DemoApplication.class)** or another explicit list when you want to eliminate ambiguity from auto-search. Once `classes` are explicit, do not assume a nested `@Configuration` will "naturally replace the app" in the same way it does under auto-search. Evaluate the actual declared config sources and all `@Import`s in effect.

## 9. Context caching: why changing config can slow down tests or leak state

Spring TestContext **caches the ApplicationContext** across tests that share the same effective configuration. This reduces Spring startup overhead. Differences such as configuration classes, imports, active profiles, property sources, and context customizers can produce different cache keys, causing a separate context to load.

| Pattern | Common impact |
|---|---|
| Two tests use the same app config and matching options | Opportunity to reuse the cached context |
| One test adds its own nested `@TestConfiguration` | Likely needs a separate context due to different configuration |
| One test `@Import`s a different test configuration | Likely produces a different context key |
| Every test overrides different properties/profiles | Usually reduces context sharing |
| Keeping mutable state in a singleton test bean | Easily causes order-dependent tests or leftover state |
| Overusing `@DirtiesContext` | Forces context eviction from cache, slowing down the suite |

**Rule of thumb:** Test configurations should be isolated enough to prevent state leakage, without creating dozens of configs differing only in minor unnecessary details. If you use a mutable singleton fake that changes during tests, reset its state between tests or design an immutable fake; context caching does not automatically refresh business state inside beans.

Do not use `@DirtiesContext` as the default cure for every test failing due to leftover state from a previous run; first look for static state, mutable singleton data, and uncleaned database/test fixtures.

## 10. Distinguishing @NestedTestConfiguration from @TestConfiguration

The names look similar, yet their meanings differ:

- **org.springframework.boot.test.context.TestConfiguration** is an annotation **defining a configuration class** containing `@Bean`s for tests.
- **org.springframework.test.context.NestedTestConfiguration** is an annotation setting the **TestContext metadata inheritance policy** on a hierarchy of **JUnit Jupiter @Nested test classes**. Common values are **INHERIT** (default) or **OVERRIDE**.

Conceptual illustration (not a standalone runnable class):

~~~java
@SpringBootTest
class OuterTest {

    @Nested
    class InnerTest {
        // Inherits configuration metadata from OuterTest by default.
    }

    @Nested
    @NestedTestConfiguration(
        NestedTestConfiguration.EnclosingConfiguration.OVERRIDE)
    class IndependentInnerTest {
        // Must declare test metadata suited to the new scope.
    }
}
~~~

In `OVERRIDE` mode, the nested test class must declare the Spring configuration annotations it needs if it does not want to use the outer class's metadata. **OVERRIDE does not mean "override every @Bean"** and is not a mechanism for replacing production beans. For a test that simply needs a new bean, still prefer `@TestConfiguration`/`@Import`.

## 11. Troubleshooting failures in order

| Symptom | Possible cause | Check / fix |
|---|---|---|
| Missing `TimeService` in `@SpringBootTest` | Added static nested `@Configuration`, replacing primary config | Change to `@TestConfiguration` if the goal is additive |
| `NoSuchBeanDefinitionException` for production bean | `@SpringBootApplication` app was not loaded or slice excluded the bean | Check primary source, component scan, slice, and `@Import` |
| Two `Clock` beans and `NoUniqueBeanDefinitionException` | Both beans share the same type with no clear selection | `@Primary` or `@Qualifier`; verify which bean SUT uses |
| `BeanDefinitionOverrideException` | Two configs register the same bean name with overriding off | Rename + `@Primary` or use an intentional replacement mechanism |
| Test uses system `Clock` instead of fixed | SUT injects `@Qualifier("systemClock")` or another bean | Check constructor/qualifier and test actual output |
| Nested config not found | Non-static class, explicit config, or wrong annotation/import | Use static nested config; check bootstrap metadata |
| Top-level `@TestConfiguration` not loaded | `@TestConfiguration` in a separate file but forgot `@Import` | Add `@Import` to the test class that needs it |
| Test helper picked up by unexpected tests | Top-level `@Configuration` in scanned package, custom ComponentScan | Use `@TestConfiguration` and explicit import |
| `@Nested` test does not pick up outer Spring annotations | `@NestedTestConfiguration` set to `OVERRIDE` or missing config | Check `INHERIT`/`OVERRIDE` and test annotations |
| Test suite very slow after adding many configs | Context cache split into many keys, frequent `@DirtiesContext` | Review effective configuration, reduce redundant custom contexts |
| Test slice accidentally loads entire app | Overly broad `@Import`/config, custom `@ComponentScan` | Narrow config to the slice, preserve exclude filters |

**Investigation workflow:**

1. Read the stack trace to tell whether the error happened during **ApplicationContext initialization** or during **assertion execution**.
2. Identify whether the test uses **@SpringBootTest, a slice annotation, @SpringJUnitConfig**, or `@ContextConfiguration`; check explicit `classes`.
3. Locate static nested `@Configuration`/`@TestConfiguration` classes and all active `@Import`s.
4. Check **bean types, bean names, and qualifiers**, especially when names collide or multiple candidates exist.
5. Verify with assertions close to the goal: presence of the production bean, test bean, and SUT method result.
6. Once the right configuration scope is chosen, run tests via your CI tool (Gradle/Maven) rather than relying only on the IDE Run button.

## 12. Notes for designing maintainable tests

- **Do not create a nested `@Configuration` just to "conveniently add a `@Bean`"** when the test must keep the full app context. It can replace the entire bean set of the test.
- **Use nested `@TestConfiguration`** for customization private to a single class; it expresses the intent to "add to app config."
- **Use top-level `@TestConfiguration` + `@Import`** for shared fixtures or test slices needing a specific bean.
- **Check the primary source when using explicit classes**; nested annotations do not alter an explicitly supplied configuration list in the same way you might expect from auto-search.
- **Do not treat `@Primary` as bean overriding**. It selects a candidate during injection by type, while the old bean still exists.
- **Do not confuse static config classes with JUnit `@Nested`**; the former contributes beans to the context, while the latter groups test methods.
- **Avoid global configuration affecting many tests** just to solve one case. Minimal, intentional configuration and clear assertions are easier to understand.
- **Separate unit tests from context tests:** pure Java business logic should be tested directly; only use a Spring context when proving bean discovery, wiring, profiles, or auto-configuration.

## 13. Self-check after the lesson

1. A test has **@SpringBootTest** and a **static nested @Configuration** that creates only bean X. Why might the application's `@Service` beans be absent? When should `@TestConfiguration` be used instead?
2. A test adds a `Clock.fixed` with **@Primary** inside a nested `@TestConfiguration`. Is production `Clock.systemUTC` removed from the context? What happens if the service uses `@Qualifier("systemClock")`?
3. A top-level `@TestConfiguration` in `src/test/java` is not discovered by a test. Which annotation lets you bring it into the context of a single test class?
4. How does a JUnit **@Nested** class differ from a nested configuration class? What does `@NestedTestConfiguration(OVERRIDE)` control?
5. Two tests initialize separate contexts after adding configuration. How can that affect suite runtime and test independence?

**Answer hints:** (1) nested `@Configuration` can act as the test-discovered primary configuration; use nested `@TestConfiguration` to be additive. (2) The production bean still exists; `@Primary` wins type-based injection but does not override an explicit qualifier. (3) `@Import`. (4) `@Nested` groups tests; `@NestedTestConfiguration` controls Spring TestContext metadata inheritance, not bean definitions. (5) Context cache keys and singleton state may differ; manage fixtures carefully and avoid redundant custom contexts.

## 14. Official documentation

- [Spring Boot 3.3 — Testing Spring Boot Applications: Detecting Test Configuration and Excluding Test Configuration](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Framework — TestContext Framework Support Classes, @Nested test class configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html)
- [Spring Framework 6.1 — @NestedTestConfiguration Javadoc](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/test/context/NestedTestConfiguration.html)
- [Spring Boot 3.3 — TestConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/TestConfiguration.html)

**Key takeaway:** Choose configuration according to test intent: **separate minimal configuration** uses nested `@Configuration`; **adding onto the real application** uses nested `@TestConfiguration`; **explicit sharing** uses top-level `@TestConfiguration` + `@Import`. Then always write assertions verifying that the expected beans or behaviors are provided.