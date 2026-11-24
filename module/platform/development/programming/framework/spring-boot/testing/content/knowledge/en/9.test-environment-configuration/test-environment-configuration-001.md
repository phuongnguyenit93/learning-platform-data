# Finding @SpringBootConfiguration and the Impact of Package Structure

## 1. Problem: Why does the same @SpringBootTest work in one class while another reports missing configuration?

In a Spring Boot project, tests often use `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, or other test slices. When no specific configuration class is declared, Spring Boot needs to find a **primary configuration** to serve as the starting point for building the `ApplicationContext`. The most common case is the application runner class annotated with `@SpringBootApplication`.

The **package** location of a test class directly affects the configuration discovery process. Tests placed under the application's root package can be discovered automatically; tests in a sibling package or a branch outside the same parent tree may fail with a message close to:

```text
IllegalStateException:
Unable to find a @SpringBootConfiguration, you need to use
@ContextConfiguration or @SpringBootTest(classes=...)
with your test
```

The exact message varies by Spring Boot version and test type. The core issue is: **Boot has not found a class to use as the configuration source**. This error is completely different from a **bean not found** error after the context has already been initialized.

This lesson helps you:

1. Understand the relationship between `@SpringBootConfiguration`, `@SpringBootApplication`, `@Configuration`, and `@TestConfiguration`.
2. Accurately explain the **package-based primary configuration search algorithm** in Spring Boot Test.
3. Structure `src/main/java` and `src/test/java` so tests find the right configuration.
4. Distinguish between **finding a configuration class** and **component scanning finding a bean**.
5. Troubleshoot missing configuration, multiple configurations, and test slices picking up the wrong beans.
6. Write and run Java 17+ tests that demonstrate auto-discovery and explicit configuration sources.

## 2. Annotations involved in configuration discovery

| Annotation | Meaning | Candidate for Boot Test primary configuration? |
| --- | --- | --- |
| `@Configuration` | Marks a Spring Framework class declaring beans/configuration | **Not automatically** selected by the package-based `@SpringBootConfiguration` search algorithm |
| `@SpringBootConfiguration` | A specialization of `@Configuration` signifying the root configuration of a Boot application | **Yes**, when located in a searched package |
| `@SpringBootApplication` | Combines `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan` | **Yes**, because it carries `@SpringBootConfiguration` as a meta-annotation |
| `@TestConfiguration` | Configuration dedicated to tests, adding test beans/setup | **Should not be used as the default primary application configuration**; nested test config is normally added on top of the discovered root |
| `@SpringBootTest(classes = ...)` | Explicitly specifies source classes for Spring Boot Test | **Bypasses the need for automatic root search** for the specified classes |
| `@ContextConfiguration(classes = ...)` | Explicitly specifies context sources for Spring TestContext | Can be used to provide explicit configuration instead of automatic discovery |

The three key components of `@SpringBootApplication`:

```java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
public @interface SpringBootApplication {
    // This illustrates the composing semantics, not the
    // full source code of the annotation in Spring Boot.
}
```

- `@SpringBootConfiguration` helps Boot identify the root configuration class.
- `@EnableAutoConfiguration` enables auto-configurations matching the classpath and conditions.
- `@ComponentScan` by default searches for Spring components from the package containing the application class down into subpackages.

Therefore, **`@SpringBootConfiguration` alone is not synonymous with `@SpringBootApplication`**: the class is found as the root, but it will not necessarily scan services/controllers/repositories automatically or enable full auto-configuration. If you write a root yourself with `@SpringBootConfiguration`, you must explicitly declare the required configurations, scans, or auto-configurations.

## 3. Package-based @SpringBootConfiguration search algorithm

For Spring Boot integration test annotations, when **no configuration source is specified**, Spring Boot searches starting from the **package of the test class**, then walks up through parent packages one by one until it finds a class annotated with `@SpringBootApplication` or `@SpringBootConfiguration`.

Example:

```text
Test class: com.example.catalog.order.OrderServiceTest

Packages searched from closest to farthest:

com.example.catalog.order
          ↓
com.example.catalog
          ↓
com.example
          ↓
com
          ↓
(default package)

Application class:
com.example.catalog.CatalogApplication
    @SpringBootApplication

=> Found when inspecting com.example.catalog.
```

**Key point to remember:** "walking upward" means following the **chain of parent packages of the test**, not recursively scanning every subpackage of each parent package to find any application class. A test in `com.example.qa` does not automatically look sideways into `com.example.catalog` just because both packages share the `com.example` prefix.

### 3.1. Why does test class placement matter?

Suppose the application class is placed at:

```java
package com.example.catalog;

@SpringBootApplication
public class CatalogApplication { /* ... */ }
```

- Test in `com.example.catalog`: discovers the application class.
- Test in `com.example.catalog.order`: walks up to `com.example.catalog` and discovers it.
- Test in `com.example.catalog.order.read`: walks through parent packages and discovers it.
- Test in `com.example.qa`: walks up to `com.example`, but the application class is in a **sibling subpackage** `com.example.catalog`, so it is not discovered automatically.
- Test in `com.other.catalog`: does not share a package path with the root.
- Test in the **default package** (no `package` declaration): hard to control discovery and component scanning; do not design a Boot project this way.

This is why tests are normally placed in the same package or a **subpackage** of the application root.

### 3.2. Directory paths and Java packages must be distinguished

`src/main/java/com/example/catalog/CatalogApplication.java` contains the declaration:

```java
package com.example.catalog;
```

The test can reside at:

```text
src/test/java/com/example/catalog/order/OrderServiceTest.java
```

with the declaration `package com.example.catalog.order;`. The two files live in different **source sets** yet still belong to the appropriate package tree. The test classpath normally includes compiled classes from both `src/main/java` and `src/test/java`, so the test finds the primary config located in the main source set.

If the directory path and the `package` declaration do not match, the Java compiler may still compile under some build setups, but it is the **package declared in the file** that defines the class name and affects the search—not the directory name seen by human eyes. Keep them matching to avoid mistakes and support IDE tooling.

### 3.3. Finding the configuration class is not scanning all beans

The two algorithms have different starting points:

```text
A. Test primary configuration search:
   package(test class) → parent packages → @SpringBootConfiguration

B. Default Spring component scan:
   package(application class) → subpackages
   → @Component, @Service, @Repository, @Controller, ...
```

For example, a test in `com.example.catalog.order` finds `CatalogApplication` in `com.example.catalog`, while bean `com.example.billing.PaymentService` lives in a package that is a **sibling** of `com.example.catalog`. With only the default component scan, that bean **is not found**. That is a `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` *after* the root has already been found, not a missing `@SpringBootConfiguration` error.

Conversely, adding `@ComponentScan("com.example.billing")` to the root may help find the bean, but it **does not fix the test root search algorithm** when the test is in `com.example.qa`. Each layer must be addressed appropriately.

## 4. Recommended package structure for Spring Boot

For a single-root Boot application:

```text
catalog-service/
├── src/main/java/com/example/catalog/
│   ├── CatalogApplication.java         @SpringBootApplication
│   ├── order/
│   │   ├── OrderService.java           @Service
│   │   └── OrderRepository.java        @Repository
│   └── web/
│       └── OrderController.java        @RestController
└── src/test/java/com/example/catalog/
    ├── CatalogApplicationTests.java    @SpringBootTest
    ├── order/
    │   └── OrderServiceTest.java       @SpringBootTest or unit test
    └── web/
        └── OrderControllerTest.java    @WebMvcTest
```

Placing `CatalogApplication` in the **highest common package owned by the application** lets component scanning find almost all beans of the same application. Tests in branches underneath it can discover the primary configuration automatically.

Do not place the application class in `com.example.catalog.bootstrap.internal` if most controllers/services live in `com.example.catalog.order`, unless the application explicitly configures scanning/imports; doing so will cause the default component scan to miss beans in sibling packages.

On the other hand, moving the root up to an overly broad package like `com.example` may accidentally scan beans from multiple applications or shared modules if they share the classpath. Choose a **root package broad enough to encompass one application without encompassing independent applications**.

### Layouts prone to errors

| Layout | Issue | Appropriate fix |
| --- | --- | --- |
| `@SpringBootApplication` in `com.acme.app`, test in `com.acme.tests` | Root not found through parent packages | Move test under `com.acme.app` or use `classes = AppApplication.class` |
| Application in `com.acme.app.bootstrap`, `@Service` in `com.acme.app.domain` | Root may be found, but default scan skips domain | Place application in `com.acme.app` or define explicit scan/import |
| Two Boot roots found in the same package | Cannot determine a unique primary configuration | Specify `classes` on the test or adjust root placement/role |
| Multi-module project, shared test not in app package | Discovery depends on the test's package | Specify the exact root application of the module under test |
| A top-level `@Configuration` for tests gets scanned accidentally | Test beans may appear in other tests | Use `@TestConfiguration` + intentional `@Import` |
| Overly specific configuration placed on the application root | Slice tests may end up processing out-of-scope configuration | Extract into a separate configuration class and import only when needed |

## 5. Java 17+ and Spring Boot 3.3.x sample project

Let us build a small application to **directly demonstrate** package-based primary configuration discovery in tests. We use Spring Boot 3.3.5 as a concrete example version, Java 17+, and Gradle. These versions are for this hands-on example and do not imply they are the latest releases.

Structure:

```text
configuration-discovery-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/catalog/
│   ├── CatalogApplication.java
│   └── service/
│       └── GreetingService.java
└── src/test/java/
    ├── com/example/catalog/service/
    │   ├── AutomaticPrimaryConfigTest.java
    │   ├── AdditiveTestConfigurationTest.java
    │   └── ExplicitMinimalConfigurationTest.java
    └── com/example/qa/
        └── ExplicitPrimaryConfigTest.java
```

### 5.1. Gradle setup

`settings.gradle`:

```groovy
rootProject.name = 'configuration-discovery-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-test` provides JUnit Jupiter, Spring Test, and Spring Boot Test, along with common testing libraries. In a **Boot application that already has its own Gradle/BOM setup**, reuse existing dependency management; there is no need to change your project's versions just to try this snippet.

### 5.2. Application class as primary configuration

`src/main/java/com/example/catalog/CatalogApplication.java`:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

`src/main/java/com/example/catalog/service/GreetingService.java`:

```java
package com.example.catalog.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        return "Hello, " + name.strip() + "!";
    }
}
```

The application class is in `com.example.catalog`. Because `@SpringBootApplication` includes default component scanning, the `GreetingService` bean in `com.example.catalog.service` is discovered.

## 6. Example 1: test in a subpackage automatically finds the application

`src/test/java/com/example/catalog/service/AutomaticPrimaryConfigTest.java`:

```java
package com.example.catalog.service;

import com.example.catalog.CatalogApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class AutomaticPrimaryConfigTest {
    @Autowired
    ApplicationContext context;

    @Autowired
    GreetingService greetingService;

    @Test
    void findsApplicationRootFromParentPackage() {
        assertNotNull(context.getBean(CatalogApplication.class));
        assertEquals("Hello, An!", greetingService.greet(" An "));
    }
}
```

Run:

```bash
./gradlew test --tests 'com.example.catalog.service.AutomaticPrimaryConfigTest'
```

**Expected:** 1 test PASSES if the build/dependencies resolve successfully. The test verifies not only that the context can be created, but also that `CatalogApplication` is a bean in the context and `GreetingService` can be injected via component scanning.

What happens:

1. The test class is in `com.example.catalog.service`, with no `classes` declared on `@SpringBootTest`.
2. Boot searches for primary configuration in `com.example.catalog.service`, then `com.example.catalog`.
3. In `com.example.catalog`, Boot finds `CatalogApplication` annotated with `@SpringBootApplication`.
4. Spring Boot creates an `ApplicationContext` from this configuration.
5. Component scanning starts from `CatalogApplication`'s package and finds `GreetingService`.

Note that `@SpringBootTest` and JUnit Jupiter integrate via `SpringExtension`, which is already built into the Boot Test annotation; you do not need to add `@ExtendWith(SpringExtension.class)` just to make this test run.

## 7. Example 2: test in a sibling package must specify classes explicitly

Now place a test in `com.example.qa`. This package is **not under `com.example.catalog`**. If the test only declares `@SpringBootTest`, Boot will not be able to find the root.

The accurate and stable approach is to specify the source:

`src/test/java/com/example/qa/ExplicitPrimaryConfigTest.java`:

```java
package com.example.qa;

import com.example.catalog.CatalogApplication;
import com.example.catalog.service.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(classes = CatalogApplication.class)
class ExplicitPrimaryConfigTest {
    @Autowired
    GreetingService greetingService;

    @Test
    void usesExplicitApplicationEvenOutsideItsPackageTree() {
        assertEquals("Hello, Binh!",
                greetingService.greet(" Binh "));
    }
}
```

Run:

```bash
./gradlew test --tests 'com.example.qa.ExplicitPrimaryConfigTest'
```

**Expected:** 1 test PASSES. `classes = CatalogApplication.class` explicitly identifies the configuration source; the test does not depend on package traversal. **Important point:** because the source class is still `CatalogApplication` in `com.example.catalog`, the default component scan scope **remains tied to the application class**, and does not change to `com.example.qa`.

### Counterexample: omitting classes in the wrong package

If you change the annotation in a class under `com.example.qa` to:

```java
@SpringBootTest
class FailingOutsidePackageTest {
    @Test
    void contextLoads() {
    }
}
```

this is an **error illustration snippet**, not one of the four passing classes in the hands-on project. With the layout shown and no matching Boot root in parent packages, Boot cannot find a `@SpringBootConfiguration`. Do not add a counterexample file to the default test suite and expect `gradle test` to still PASS.

There are two ways to fix this: move the test into the `com.example.catalog` branch if appropriate for the module, or keep its location and declare `@SpringBootTest(classes = CatalogApplication.class)`.

## 8. Example 3: nested @TestConfiguration adds configuration on top of the root

In a test you may need a bean only for testing, such as `Clock.fixed(...)` so results do not depend on wall-clock time. With Spring Boot, a **nested `@TestConfiguration` is applied in addition to the primary application configuration**, rather than replacing the root configuration.

`src/test/java/com/example/catalog/service/AdditiveTestConfigurationTest.java`:

```java
package com.example.catalog.service;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class AdditiveTestConfigurationTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {
        @Bean
        Clock testClock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }

    @Autowired
    Clock clock;

    @Autowired
    GreetingService greetingService;

    @Test
    void keepsApplicationBeanAndAddsTestClock() {
        assertNotNull(greetingService);
        assertEquals("2024-01-01T00:00:00Z",
                clock.instant().toString());
        assertEquals("Hello, An!",
                greetingService.greet("An"));
    }
}
```

Run:

```bash
./gradlew test --tests 'com.example.catalog.service.AdditiveTestConfigurationTest'
```

**Expected:** 1 test PASSES. The application root is discovered from the test's package as in Example 1; the nested `@TestConfiguration` class provides an additional `Clock`; the application's `GreetingService` remains available.

### How @TestConfiguration differs from nested @Configuration

- **Nested `@TestConfiguration`:** Boot Test uses it *in addition to* the discovered primary configuration. Suitable for adding fixture beans and test-specific configuration.
- **Regular nested `@Configuration`:** Spring Test may use it as the configuration source **instead of** the primary application configuration; this difference can prevent application beans from being loaded.
- **Top-level `@TestConfiguration`:** marked so it does not automatically appear through normal component scanning; intentionally import it into tests that need it with `@Import(MyTestConfiguration.class)`.

Do not change a nested `@TestConfiguration` into `@Configuration` just to avoid an import: doing so can alter the entire context under test. And do not place a top-level `@Configuration` meant for tests inside a package broadly scanned by the application unless you want test beans appearing unexpectedly.

## 9. Example 4: explicit classes with a minimal configuration

Sometimes a test's goal is only to test a few beans without scanning the whole application. `@SpringBootTest(classes = ...)` can point to a specific `@Configuration`. That is an **intentional choice**, unlike letting Boot search for the root automatically.

`src/test/java/com/example/catalog/service/ExplicitMinimalConfigurationTest.java`:

```java
package com.example.catalog.service;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import com.example.catalog.CatalogApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(classes = ExplicitMinimalConfigurationTest.MinimalConfig.class)
class ExplicitMinimalConfigurationTest {

    @Configuration(proxyBeanMethods = false)
    static class MinimalConfig {
        @Bean
        Clock testClock() {
            return Clock.fixed(
                    Instant.parse("2024-03-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }

    @Autowired
    Clock clock;

    @Autowired
    ApplicationContext context;

    @Test
    void usesOnlyRequestedConfigurationSource() {
        assertEquals("2024-03-01T00:00:00Z",
                clock.instant().toString());
        assertThrows(NoSuchBeanDefinitionException.class,
                () -> context.getBean(CatalogApplication.class));
        assertThrows(NoSuchBeanDefinitionException.class,
                () -> context.getBean(GreetingService.class));
    }
}
```

Run:

```bash
./gradlew test --tests 'com.example.catalog.service.ExplicitMinimalConfigurationTest'
```

**Expected:** 1 test PASSES with the sample configuration. The `Clock` bean is created directly; `CatalogApplication` and `GreetingService` are not scanned because the supplied root is only `MinimalConfig`, which declares no `@ComponentScan`. `SpringBootTest(classes=...)` does not automatically "turn on the full application" if the specified class is in fact a minimal `@Configuration`.

For testing small beans, you can also use `@SpringJUnitConfig(MinimalConfig.class)` to create a Spring Framework context without opting into the full Spring Boot model. Choose the approach that matches what you need to prove: application auto-configuration or specific component configuration.

### Four passing tests with different meanings

| Test | Test package | Configuration source | Expected |
| --- | --- | --- | --- |
| `AutomaticPrimaryConfigTest` | `com.example.catalog.service` | Auto-discovery from parent package | Has app bean and service |
| `ExplicitPrimaryConfigTest` | `com.example.qa` | `classes = CatalogApplication.class` | Has service even though test is in an outside package |
| `AdditiveTestConfigurationTest` | `com.example.catalog.service` | App root + nested `@TestConfiguration` | Has service and fixed clock |
| `ExplicitMinimalConfigurationTest` | `com.example.catalog.service` | `classes = MinimalConfig.class` | Has clock, no app/service |

Run the entire suite:

```bash
./gradlew test
```

**Expected:** 4 tests PASS (one method per class), provided the project is created with the right structure and dependencies resolve. There is no fixed business stdout; Gradle reports the build/test status and writes the HTML report at `build/reports/tests/test/index.html`. Test contexts may initialize multiple times due to different configurations; that does not change the method count.

## 10. When does @SpringBootConfiguration discovery fail?

### 10.1. No root on the parent package chain

Typical symptom:

```text
Unable to find a @SpringBootConfiguration
```

Common causes are a test residing in `com.example.tests` while the app is in `com.example.orders`; or a multi-module application where the test class sits in a shared package outside the module being tested.

How to handle it:

1. Identify the **actual declared package of the test class**.
2. Identify the package/class carrying `@SpringBootApplication` or `@SpringBootConfiguration` for the target application.
3. Check whether the application class belongs to the test's own package or one of its parent packages.
4. If possible, organize tests within the application's package tree.
5. If the test has a valid reason to sit elsewhere, declare `classes = YourApplication.class` with the right source.

Do not resolve this by arbitrarily adding a new `@SpringBootApplication` in `src/test/java`: a fake root can cause tests to initialize the wrong configuration and skip real application beans.

### 10.2. Multiple candidate roots

If Spring Boot finds **multiple `@SpringBootConfiguration` classes within the searched package scope**, it may report an error like:

```text
Found multiple @SpringBootConfiguration annotated classes
```

This can happen when a source set or test classpath brings multiple application roots into the **same search scope**, especially in multi-module setups or experimental apps with multiple bootstrapping classes. Do not confuse this into thinking any two roots in arbitrary subpackages are always scanned at once: the algorithm walks **along parent packages**, not across the entire child tree.

The usual fix is to specify the single appropriate source with `@SpringBootTest(classes = CorrectApplication.class)` or split application configurations so each test has an unambiguous primary configuration.

### 10.3. Root found, but beans are still missing

Example:

```text
NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.billing.PaymentService'
```

This indicates **the context has already initialized up to the bean wiring step**, yet a required bean is missing. Check component scan base packages, `@Component`/`@Service` annotations, `@Conditional...` conditions, `@Profile`, `@Import`, `@Bean`, and test slice scope. Adding `classes=...` only fixes source selection when the wrong root was picked; it does not by itself guarantee that beans in packages outside the scan scope are included.

### 10.4. Creating a nested @Configuration accidentally replaces the root

A test might look like:

```java
@SpringBootTest
class OrderServiceContextTest {
    @Configuration
    static class Config {
        @Bean
        Clock clock() {
            return Clock.systemUTC();
        }
    }
}
```

This is a **non-standalone illustration snippet**: imports for annotations/Clock are needed, and the test name is just an example. With a nested `@Configuration`, this configuration can be picked by Spring Test as the primary context source, preventing app beans from loading. If the goal is to **add** a Clock bean to the Boot context, change the nested class to `@TestConfiguration`, as in Example 3.

### 10.5. Test run from the wrong module or source set

In a Gradle multi-project build, task `:module-a:test` uses module A's classpath. If the `@SpringBootApplication` class actually belongs to module B and module A does not include that class on its test runtime classpath, discovery still fails even if the package names look compatible. A test cannot find a class that **is not on the classpath**.

Do not solve this by making every module depend on every application module: that breaks architectural boundaries and leads to multiple roots. Check which module owns the application, where tests should live, and what test dependencies are needed. In a pure library module with no Boot root, use JUnit Jupiter/Mockito or Spring Test with `@ContextConfiguration`/`@SpringJUnitConfig` as appropriate.

## 11. Impact on test slices

Annotations such as `@WebMvcTest`, `@DataJpaTest`, and `@JsonTest` also use Boot's test configuration discovery mechanism, but **once they know the configuration source**, they build a **slice context** rather than the full application.

Example:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    // Tests MVC mappings/HTTP behavior of OrderController.
}
```

This is an **illustration snippet**, requiring a real controller and appropriate dependencies/MockMvc. `@WebMvcTest` normally loads only MVC-related beans and does not automatically instantiate every service/repository outside the slice. Finding `@SpringBootApplication` **does not mean** all beans will be loaded in a test slice.

### Explicit @ComponentScan and TypeExcludeFilter

Spring Boot uses default filters in `@SpringBootApplication`'s scan configuration to keep test slices properly scoped. When you add an explicit `@ComponentScan(...)` directly on the application class, those default slice-related exclude filters may stop taking effect as intended. As a result, `@DataJpaTest` or `@WebMvcTest` may unexpectedly load out-of-slice beans or configurations and fail.

If you need to scan additional packages, prefer extracting the scan configuration into a separate class that is intentionally imported. When you must use a custom `@ComponentScan`, account for `TypeExcludeFilter` and the filters needed by slice tests. Do not treat suppressing the error by adding `@SpringBootTest` alongside `@WebMvcTest` as a fix: do not combine those two Boot test bootstrap styles.

Another issue is placing domain-specific configuration (such as enabling Mongo auditing) on the application root: it can cause unintended side effects for slices that do not need Mongo. Extract it into a separate `@Configuration` so tests can import it only when truly needed.

## 12. @TestConfiguration: organizing test setup without polluting the application

There are two useful patterns.

**Nested config inside a test class**:

```java
@SpringBootTest
class TimeSensitiveServiceTest {
    @TestConfiguration(proxyBeanMethods = false)
    static class FixedTimeConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }
}
```

The snippet above **illustrates structure**; imports and test methods must be added if used standalone. It adds `Clock` to the test's context while preserving the primary app root.

**Top-level test config in `src/test/java`**:

```java
@TestConfiguration(proxyBeanMethods = false)
public class SharedTestClockConfig {
    @Bean
    public Clock testClock() {
        return Clock.fixed(
                Instant.parse("2024-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
```

This class is **part of a project**, needing an appropriate package/imports. For a test to use it:

```java
@SpringBootTest
@Import(SharedTestClockConfig.class)
class ReportServiceTest {
    // @Autowired Clock ...
}
```

Explicit importing prevents a top-level test configuration from accidentally affecting every test. Avoid declaring multiple beans of the same type without clear `@Primary`/`@Qualifier` annotations, as that can cause ambiguity. If you want to **replace** an existing bean in the context, choose the appropriate test bean override mechanism rather than creating a `@Bean` with the same name and assuming Boot allows overrides.

## 13. Distinguishing package search from component scan and auto-configuration

Even though all of them sound like "Spring couldn't find something," there are three independent phases:

```text
Phase 1 — Boot test selects configuration source
    Test package -> parent packages -> @SpringBootConfiguration
    or classes = ExplicitApplication.class

Phase 2 — Build context from configuration source
    @EnableAutoConfiguration and @ComponentScan/@Import/@Bean
    -> Spring creates bean definitions

Phase 3 — Resolve dependencies into tests and beans
    @Autowired, constructor injection, conditions, profiles, ...
```

| Observed error | Phase with issue | What to check |
| --- | --- | --- |
| "Unable to find a @SpringBootConfiguration" | 1 | Test package, application location, explicit classes, classpath |
| "Found multiple @SpringBootConfiguration" | 1 | Number of root classes found together, selecting the right application |
| "No qualifying bean of type ..." | 2 or 3 | Scan/import/conditional/profile/test slice |
| "Failed to load ApplicationContext" | 2 or 3 (or dependency system) | Read the deepest root cause: config/bean/network/database |
| Application class found, but controller is missing | 2 or slice restriction | Component scan base package, `@WebMvcTest` filter, bean condition |
| Test run from another module reports missing class/bean | 1 or 2 | Test runtime classpath and module ownership |

Do not rush to change packages when the real issue is datasource config, a missing profile, a component condition, or JPA mapping. Read the stack trace to identify the failing layer.

### @ActiveProfiles and test properties do not change the root search algorithm

`@ActiveProfiles("test")`, `@TestPropertySource`, or `@SpringBootTest(properties = "...")` alter environment/properties or conditional bean selection. They **do not automatically make Boot search for `@SpringBootConfiguration` in another package**. If the root is not discovered, adding properties will not solve the underlying cause.

### Context cache

Spring Test caches the `ApplicationContext` for tests with compatible configurations. Changing `classes`, nested `@TestConfiguration`, active profiles, or properties can change the cache key and force Spring to create a new context. Avoid overusing `@DirtiesContext`, and do not swap roots just to fix a small bean unnecessarily; each new context can add substantial test execution time.

## 14. Step-by-step troubleshooting guide when a test fails

When encountering a configuration error, follow this order:

1. **Read the first useful cause message.** Is it genuinely "Unable to find a @SpringBootConfiguration" or a "NoSuchBeanDefinitionException" inside a context that already found the right root?
2. **Read the package declarations of the test** and the application root. Trace the path from the test up through parent packages to see if it reaches the root.
3. **Check the root annotation:** `@SpringBootApplication` or `@SpringBootConfiguration`; a standalone `@Configuration` is not automatically discovered as the root.
4. **Check whether the source was replaced:** does the test already have a nested `@Configuration`, `@ContextConfiguration(classes=...)`, or `@SpringBootTest(classes=...)`?
5. **If the test is outside the app package tree**, specify `classes = CorrectApplication.class` or move the test into the right branch.
6. **If the root was found**, check the component scan base packages; if the bean lies outside, configure scanning/imports intentionally.
7. **If using a slice**, check whether the bean belongs to the slice and whether the root has a custom component scan breaking slice filters.
8. **If multiple roots exist**, choose the exact single source of the application you want to test and review the multi-module layout.
9. **If context loading still fails**, inspect the root cause regarding beans, profiles, properties, database, port, or security; do not blame everything on packages.
10. **Run the specific class to verify**, then run the related test suite to ensure the fix does not affect other contexts.

Gradle commands for the sample project:

```bash
./gradlew test --tests 'com.example.catalog.service.AutomaticPrimaryConfigTest'
./gradlew test --tests 'com.example.qa.ExplicitPrimaryConfigTest'
./gradlew test --tests 'com.example.catalog.service.AdditiveTestConfigurationTest'
./gradlew test --tests 'com.example.catalog.service.ExplicitMinimalConfigurationTest'
./gradlew test
```

On Windows, use `gradlew.bat` instead of `./gradlew`. For Maven projects, selecting a class via Maven Surefire is typically `./mvnw -Dtest=AutomaticPrimaryConfigTest test`, though this sample project is provided with Gradle.

## 15. Frequently asked questions

**Q: Does `@SpringBootTest` have to be in the exact same package as `@SpringBootApplication`?**

Not necessarily. A test in a **subpackage** can search upward through parent packages. A test outside the app's package tree still runs when `classes = Application.class` is explicitly specified and that class is on the test classpath.

**Q: Does the filename `CatalogApplication.java` determine the search algorithm?**

The filename is not the primary condition. The condition is a **class with the appropriate annotation on the classpath** found in the relevant packages. The `*Application` name is a readable convention.

**Q: Does `@SpringBootConfiguration` automatically scan `@Service` classes like `@SpringBootApplication` does?**

No. `@SpringBootConfiguration` is not equivalent to the trio of annotations in `@SpringBootApplication`. You must check `@ComponentScan`, `@EnableAutoConfiguration`, and other bean sources.

**Q: Does a test with `@SpringBootTest(classes=...)` still search for a root by package?**

Once a sufficient configuration source is explicitly specified, Boot uses that source and does not need the default search mechanism. However, the specified class may itself import other configurations, so the final context still depends on annotations/beans on that source.

**Q: Does using a nested `@TestConfiguration` replace the application?**

Normally no: it adds onto the primary configuration. A regular nested `@Configuration`, however, can cause Boot to use that configuration **instead of** the primary app configuration.

**Q: Why does adding `@WebMvcTest` still report a missing service?**

Because the MVC slice only loads the relevant MVC beans. Finding `@SpringBootApplication` properly does not mean a test slice loads all services/repositories; mock or import the required collaborators according to your MVC test goal.

**Q: What should I do if a project has multiple `@SpringBootApplication` classes?**

Ensure each test gets the exact context it needs to verify. If a test sits in a location where multiple roots could be found, specify `classes = SpecificApplication.class`. Avoid tests where the target application under test is ambiguous.

**Q: Does changing `@ActiveProfiles("test")` help find the root?**

No. Active profiles control which beans/properties are enabled when the context runs; they do not alter the package root search path.

## 16. Verification exercises

With the project in Section 5:

1. Keep `AutomaticPrimaryConfigTest` in `com.example.catalog.service` and run it: confirm the root is discovered automatically.
2. Copy that test's content to package `com.example.qa`, give it a different name, and keep `@SpringBootTest` without `classes`: predict the missing `@SpringBootConfiguration` error. Do this only on an experimental test; do not break the passing suite.
3. Restore or add `classes = CatalogApplication.class` for the test in `com.example.qa`: confirm it PASSES.
4. In `AdditiveTestConfigurationTest`, verify both `GreetingService` from the app and `Clock` from nested `@TestConfiguration` are present.
5. In `ExplicitMinimalConfigurationTest`, explain why the clock is present while `GreetingService` is absent; change `classes` to `CatalogApplication.class`, observe the context change, and adjust assertions accordingly.
6. Try creating a service in `com.example.billing` (outside `com.example.catalog`), then try autowiring it into a full app test: explain why the bean is missing even though the root was found.
7. Read the test report `build/reports/tests/test/index.html`, confirming the number of executed tests and the real cause of each failure before fixing.

The key takeaway is that **"searching for configuration from test up through parent packages"** and **"component scanning from application down into subpackages"** are two distinct rules.

## 17. References

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html), especially *Detecting Test Configuration*, *Excluding Test Configuration*, and *User Configuration and Slicing*.
- [Spring Boot 3.3 — @SpringBootTest Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/SpringBootTest.html).
- [Spring Boot 3.3 — @SpringBootConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringBootConfiguration.html).
- [Spring Framework 6.1 — TestContext Framework](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework.html), on context configuration and caching.

## 18. Summary

Spring Boot Test finds the root configuration by starting from the **test's package**, walking up through parent packages, and selecting the matching class annotated with `@SpringBootApplication` or `@SpringBootConfiguration`, unless you have supplied explicit configuration. A consistent package layout lets most tests find the application automatically. When a test lives in another module/package or needs a smaller context, `classes = ...` resolves source selection transparently.

After finding the configuration, Spring still has to **scan/import/create beans** according to annotations and test slice boundaries. Knowing how to distinguish these two stages—along with the special role of nested `@TestConfiguration`—helps accurately diagnose "unable to find Boot configuration" versus "bean not found" errors and avoids fixes that unintentionally alter the entire test context.
