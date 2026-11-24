# Spring TestContext: Configuration Inheritance, @Nested Classes, and Composed Annotations

## 1. Objectives and Big Picture

The **Spring TestContext Framework** connects JUnit Jupiter with a Spring `ApplicationContext`: loading beans, injecting dependencies into tests, selecting profiles, applying test properties, managing transactions, running `TestExecutionListener` hooks, and caching contexts. When multiple tests share part of their configuration, you can organize them using **superclasses**, **`@Nested` classes**, or **composed annotations** (meta-annotations).

These three mechanisms are related but **not identical**:

1. **Class inheritance:** `ChildTest extends BaseTest`; Spring can inherit `@ContextConfiguration`, `@ActiveProfiles`, `@TestPropertySource`, and other eligible test annotations from the superclass.
2. **Enclosing class inheritance:** JUnit Jupiter's `@Nested` is an inner test class inside another class; since Spring Framework 5.3, Spring TestContext inherits test configuration from **enclosing classes** by default, with options `INHERIT` or `OVERRIDE`.
3. **Composed annotations:** defining a project annotation **meta-annotated** with JUnit and Spring annotations—for example `@SpringJUnitConfig`, `@ActiveProfiles`, `@TestPropertySource`—so multiple tests share one convention.

Do not confuse **test configuration inheritance** with **Java bean inheritance**. Configuration inheritance determines **which metadata builds the context**; it does not automatically create parent–child relationships between `ApplicationContext` instances. Only explicit `@ContextHierarchy` establishes parent/child context semantics.

### When to Use Which Mechanism?

| Need | Choice | Benefit | What to Watch Out For |
| --- | --- | --- | --- |
| Many tests need shared base Spring config and setup | Abstract superclass | Shares context metadata and helpers/lifecycle if needed | Wrong overrides can drop beans or profiles |
| Tests share a domain but have multiple sub-scenarios | JUnit `@Nested` | Groups cases by Given/When/Then context | `INHERIT`/`OVERRIDE` mode, outer class lifecycle |
| Dozens of tests need the same annotation config | Custom composed annotation | Cuts repetition, standardizes profiles and setup | Keep annotations small and clear; avoid conflicting meta-annotations |
| Each test needs a completely separate bean combination | Separate test config, optionally `OVERRIDE` | Deliberately isolates the test class | Distinct contexts incur loading/caching costs |
| Spring Boot app needs auto-configuration | `@SpringBootTest` or Boot test slice | Covers Boot behavior | Do not assume `@SpringJUnitConfig` equals full Boot auto-config |

Examples in this lesson use **Java 17, Spring Boot 3.5.x (Spring Framework 6.2), and JUnit Jupiter 5**. The principles also apply to Spring Boot 4/Spring Framework 7, though JUnit, dependencies, and extension lifecycle details change; check documentation for your exact version line.

## 2. Baseline Spring TestContext Configuration

`@ExtendWith(SpringExtension.class)` registers `SpringExtension` for JUnit Jupiter. `@ContextConfiguration` describes how Spring loads the `ApplicationContext`. Spring provides the shorthand annotation:

```java
@SpringJUnitConfig(MyTestConfig.class)
class MyServiceTest {
    // Test methods...
}
```

`@SpringJUnitConfig` combines `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`; you do not need to place all three annotations in the example above. `MyTestConfig` is the test configuration containing the beans under test.

An explicit component-by-component equivalent:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = MyTestConfig.class)
class MyServiceTest {
    // Test methods...
}
```

Both snippets **only illustrate annotation configuration**; types like `MyTestConfig` and imports must be defined in the project. A complete runnable example appears in Section 7.

In Spring Boot, `@SpringBootTest` already integrates JUnit Jupiter/Spring TestContext support and normally does not need `@ExtendWith(SpringExtension.class)`. `@SpringJUnitConfig` builds a Spring context from the specified configuration and **does not guarantee** that Boot auto-configuration, application startup logic, or a web server will load. Pure unit tests needing no Spring context should still use JUnit/Mockito directly.

## 3. Inheriting Configuration from a Superclass

Example:

```java
@SpringJUnitConfig(BaseConfig.class)
@ActiveProfiles("base")
@TestPropertySource(properties = "app.mode=base")
abstract class AbstractIntegrationTest {
}

@ActiveProfiles("billing")
@TestPropertySource(properties = "app.mode=billing")
class BillingTest extends AbstractIntegrationTest {
}
```

This is a **configuration sketch**, not yet a runnable test class. Under Spring TestContext defaults:

- `BillingTest` gets bean configuration from `BaseConfig` via inherited `@ContextConfiguration`.
- Active profiles include `base` and `billing`, because `@ActiveProfiles(inheritProfiles=true)` is the default.
- The subclass property `app.mode=billing` overrides the same-named value from the superclass, because `@TestPropertySource(inheritProperties=true)` is the default and subclass-declared properties take higher precedence in that inherited group.
- If multiple `@ContextConfiguration` annotations appear across levels, subclass resources/classes are **appended** after inherited ones unless replacement is chosen.

### Inheritance Flags to Remember

| Annotation | Flag | Default | When Set to `false` |
| --- | --- | --- | --- |
| `@ContextConfiguration` | `inheritLocations` | `true` | Resource locations/**configuration classes** from the superclass are not inherited via this mechanism |
| `@ContextConfiguration` | `inheritInitializers` | `true` | Context initializers from the superclass are not inherited |
| `@ActiveProfiles` | `inheritProfiles` | `true` | Uses only profiles resolved from the current class declaration, without merging profiles from earlier levels |
| `@TestPropertySource` | `inheritLocations` | `true` | Does not merge test property **files/resources** from the superclass |
| `@TestPropertySource` | `inheritProperties` | `true` | Does not merge **inline properties** from the superclass |
| `@TestExecutionListeners` | `inheritListeners` | `true` | Does not inherit custom listeners declared on the superclass |
| `@DirtiesContext` | Depends on annotation mode | No single common inherit flag | Can mark the context cache dirty; understand scope and closure timing |

**Easy mistake:** `inheritLocations=false` on `@ContextConfiguration` applies even when declaring `classes`, despite the word "Locations" in the flag name. Similarly, `@TestPropertySource` has two independent flags: changing inline properties **does not** automatically replace the property files list unless `inheritLocations=false` is also set.

### Replacing Inherited Profiles

```java
@ActiveProfiles(profiles = "isolated", inheritProfiles = false)
class IsolatedProfileTest extends AbstractIntegrationTest {
}
```

Result: the parent's `base` profile **is not merged** into this subclass's active profiles. However, other configuration annotations retain their own rules: for instance, `@ContextConfiguration` and `@TestPropertySource` may still be inherited. Setting `inheritProfiles=false` alone does not sever every configuration element.

### Replacing Bean Configuration While Still Inheriting Other Settings

```java
@ContextConfiguration(
    classes = ChildOnlyConfig.class,
    inheritLocations = false)
class ChildOnlyContextTest extends AbstractIntegrationTest {
}
```

If `AbstractIntegrationTest` had `BaseConfig` in `@ContextConfiguration`, `ChildOnlyContextTest` does not inherit that bean config list. Still, `@ActiveProfiles("base")` and `@TestPropertySource` **can remain inherited** unless overridden separately. For initializers, dropping inherited ones requires `inheritInitializers=false` per the contract.

**Do not assume** Spring will always auto-discover every static nested `@Configuration` in a superclass identically. For tests that must behave consistently across Spring versions, declaring `classes=...` explicitly is easier to control. Default config auto-discovery order has evolved and received fixes across framework releases.

## 4. Precedence Rules of `@TestPropertySource` and `@ActiveProfiles`

When multiple configuration sources exist, you cannot determine final values simply by glancing at annotation names. Key rules to remember:

- `@TestPropertySource(properties = "...")` declares **inline properties**; `@TestPropertySource(locations = "...")` points to files such as `classpath:/test.properties`.
- In TestContext, **inline test properties** have higher precedence than test property files declared via `@TestPropertySource`.
- `@DynamicPropertySource` takes higher precedence than `@TestPropertySource` when both define the same key. This matters for JDBC URLs from Testcontainers.
- Properties declared by a subclass merge according to inheritance flags; later values generally shadow earlier values for the same key in that group.
- When Spring Boot combines `@SpringBootTest(properties = "...")`, `@DynamicPropertySource`, `@TestPropertySource`, and profile-specific configuration, inspect the **actual `PropertySource` order** rather than guessing all precedence from a simplified table.
- `@ActiveProfiles` selects active profiles for the context; it is **not** a direct assignment of an arbitrary property. When profiles register different beans, changing profiles can alter the entire bean graph and context cache key.

Example test observing the effective result at the right layer:

```java
@Test
void effectivePropertyIsVisible(@Autowired Environment environment) {
    assertEquals("billing", environment.getProperty("app.mode"));
}
```

This method is only an **excerpt** requiring a properly configured test class, imports, and `Environment`. Check `environment.getActiveProfiles()` when a test depends on profiles, rather than just verifying profile names written in source code.

**Avoid silent mistakes:** if both base and subclass use `@TestPropertySource(properties="db.url=...")`, a subclass could redirect tests to a different database. Keep test DB config isolated and never let a test context write to a production database.

## 5. JUnit Jupiter `@Nested` Classes and Spring TestContext

`@Nested` lives in `org.junit.jupiter.api.Nested` and applies to a **non-static inner class**. It groups tests by scenario and lets the inner class access state on the outer instance. JUnit runs test methods inside nested classes as independent tests and invokes enclosing lifecycle hooks according to JUnit rules.

```java
@SpringJUnitConfig(TestBeans.class)
class CheckoutTest {

    @Nested
    class WithValidCart {

        @Test
        void completesCheckout(@Autowired CheckoutService checkout) {
            // Assertions...
        }
    }
}
```

This is an illustrative snippet; `TestBeans` and `CheckoutService` must exist. **Do not** declare `static class WithValidCart` if you intend it to be a JUnit `@Nested` test class.

### Two Inheritance Axes to Distinguish

1. **Superclass:** `CheckoutTest extends BaseTest` → inheritance along the **type hierarchy**.
2. **Enclosing class:** `CheckoutTest.WithValidCart` → inheritance along the **lexical enclosing hierarchy**, controlled by `@NestedTestConfiguration` in Spring TestContext.

Since **Spring Framework 5.3**, the default enclosing mode is **`INHERIT`**; in Spring Framework 5.0–5.2, outer class configuration was not inherited with the same semantics. This lesson targets 6.2/7.x, where nested inheritance is fully supported.

### `INHERIT`: Using Configuration from the Outer Class

```java
@SpringJUnitConfig(BaseConfig.class)
@ActiveProfiles("test")
class OrderTest {

    @Nested
    class ValidOrders {
        @Test
        void readsSpringBean(@Autowired SomeBean bean) {
            // Uses the context configured on the outer class.
        }
    }
}
```

`@NestedTestConfiguration(EnclosingConfiguration.INHERIT)` can be written explicitly to state intent, though `INHERIT` is the default unless the project changes the global setting. `@Nested` does not "boot a brand-new Spring context" for every inner class; TestContext can reuse the context cache when configurations match.

### `OVERRIDE`: Not Inheriting Test Configuration from the Outer Class

```java
@Nested
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
@SpringJUnitConfig(IsolatedConfig.class)
@TestPropertySource(properties = "app.mode=isolated")
class IsolatedOrders {
    @Test
    void usesOwnContext(@Autowired SomeBean bean) {
        // Relies only on the Spring test configuration declared on the nested class.
    }
}
```

**Important:** `OVERRIDE` stops the nested class from inheriting TestContext configuration **from the enclosing class**. Therefore, declare a complete `@SpringJUnitConfig` or required annotations/extensions on the nested class. `OVERRIDE` does not mean "strip every Java annotation or every inherited JUnit extension"; it governs the supported Spring TestContext annotation set. If the nested class itself extends another superclass, superclass inheritance still follows its own rules.

A `@NestedTestConfiguration` declaration on an outer class can also apply to inner nested classes. You can place:

```java
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
class TopLevelTest {
    @Nested
    class InnerTest {
        // Follows the OVERRIDE mode applied from the enclosing class.
    }
}
```

The project-wide default mode can be configured via system property `spring.test.enclosing.configuration=OVERRIDE` (or Spring's properties mechanism). When migrating an older test suite, check this flag to avoid misreading why a class cannot find beans. Declare `INHERIT`/`OVERRIDE` explicitly wherever behavior depends heavily on project mode.

### Nested Classes Adding Profiles/Properties

```java
@SpringJUnitConfig(TestBeans.class)
@ActiveProfiles("base")
class OuterTest {

    @Nested
    @ActiveProfiles("scenario")
    @TestPropertySource(properties = "app.label=nested")
    class ScenarioTest {
        // Profiles include base + scenario if inheritProfiles=true.
        // Inline properties can add to or override outer properties.
    }
}
```

In `INHERIT` mode, a nested class can **extend the outer configuration** much like a subclass. Two nested classes using `@ActiveProfiles("scenario-A")` and `@ActiveProfiles("scenario-B")` typically produce **two different merged context configurations**; because profiles contribute to the context cache key, they will not necessarily share a context.

### Lifecycle of `@Nested`

- `@BeforeEach` on the outer class runs before nested class lifecycle/test methods per JUnit; outer `@AfterEach` unwinds in proper order.
- A non-static `@Nested` class holds a reference to the outer instance; do not store mutable state on the outer class assuming nested tests always share one object in a fixed order. JUnit Jupiter defaults to per-method test instances; `@TestInstance(PER_CLASS)` alters instance lifecycle.
- On Java 17, static `@BeforeAll`/`@AfterAll` inside nested classes are supported by Java; older Java versions had restrictions or needed `PER_CLASS`. Check your active JUnit version.
- When a Spring context is marked `@DirtiesContext`, TestContext may have to reload it; nested tests sharing that context can be affected. Avoid `@DirtiesContext` when state can be reset via fixtures or transaction rollbacks.
- Avoid having nested tests with different configs rely on a Spring bean injected into an **outer field** and expecting that field to swap values as each nested child uses a different context. In Spring Framework 6.2, inject at the **nested test method/constructor/field** appropriately. Spring Framework 7.0 improves extension context handling in nested hierarchies, so check lifecycle behavior when upgrading.

## 6. Composed Annotations and `@SpringJUnitConfig`

Spring allows TestContext annotations to be used as **meta-annotations**. If every repository test requires the same config and profile, you can write one annotation instead of repeating multiple lines:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(TestBeans.class)
@ActiveProfiles("integration")
@TestPropertySource(properties = "app.feature.enabled=true")
@interface IntegrationScenarioTest {
}
```

Usage:

```java
@IntegrationScenarioTest
class OrderRepositoryTest {
    @Test
    void savesOrder() {
        // Test code...
    }
}
```

These are two **illustrative snippets**; a complete runnable example with a composed annotation is in Section 7. Key parts:

| Element | Purpose |
| --- | --- |
| `@Target(ElementType.TYPE)` | Allows placing on types/test classes |
| `@Retention(RetentionPolicy.RUNTIME)` | Lets Spring/JUnit read the annotation at runtime |
| `@Documented` | Includes the annotation in Javadoc; optional but helpful |
| `@SpringJUnitConfig(...)` | Registers SpringExtension and configures the context |
| `@ActiveProfiles(...)` | Applies standard profiles for the suite |
| `@TestPropertySource(...)` | Applies shared test properties |
| Project annotation | Short name expressing contract and scope |

Do not assume every Java annotation is valid as a meta-annotation across all Spring/JUnit versions. Spring TestContext documents supported annotations, such as `@ContextConfiguration`, `@ActiveProfiles`, `@TestPropertySource`, `@Transactional`, `@Sql`, `@DirtiesContext`, and `@SpringJUnitConfig`. JUnit Jupiter's `@Test` and `@Tag` also support method-level composition under JUnit rules.

### Composed Annotations vs. Superclasses

- Composed annotations share **metadata**; they do not bring Java fields, helpers, or methods from another test class.
- Superclasses share **inherited metadata** and can share **Java fields/lifecycle/helper methods**.
- You can combine them: base class for fixtures/helpers, composed annotation for standard Spring test context setup.
- If one test has unique needs, avoid creating dozens of composed annotations with vague names; keep a simple annotation and add clear local overrides.

### Exposing Attributes with `@AliasFor`

Sometimes tests need to pick a profile while keeping shared config. Spring lets a composed annotation attribute act as an **alias** for a meta-annotation attribute:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(TestBeans.class)
@ActiveProfiles
@interface ProfiledSpringTest {

    @AliasFor(annotation = ActiveProfiles.class, attribute = "profiles")
    String[] profiles() default {};
}
```

Use `@ProfiledSpringTest(profiles = "audit")` to pass a profile to `@ActiveProfiles`. This is an **annotation excerpt**, requiring imports for `org.springframework.core.annotation.AliasFor`, `ActiveProfiles`, `SpringJUnitConfig`, and the corresponding Java annotations. Not every attribute can be aliased arbitrarily: return types and defaults must obey `@AliasFor` rules; verify with a real context-loading test.

Aliasing a default Spring annotation attribute while also setting conflicting meta-annotation values or multiple conflicting aliases can fail at runtime during annotation synthesis. Do not use `@AliasFor` unless genuine reuse warrants it.

### Composed Annotations for Test Methods

Example combining `@Test` + `@Tag("integration")`:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Test
@Tag("integration")
@interface IntegrationCase {
}
```

Then `@IntegrationCase` on a method marks it as a JUnit test and attaches the tag. This is composition **in JUnit Jupiter**, and does not automatically load a Spring context: the enclosing class still needs appropriate Spring test setup when beans are required.

**Note:** A composed annotation carrying `@Transactional` can make every test using it run in a transaction and roll back per TestContext defaults, unintentionally preventing tests from checking real commits. Include `@Transactional` or `@DirtiesContext` in a shared annotation only when every test using it actually requires that behavior.

## 7. Complete Example: Spring Boot 3.5, Java 17, JUnit Jupiter

This example demonstrates **superclass inheritance, `@Nested` INHERIT, `@Nested` OVERRIDE, inline property precedence, and a composed annotation**. It runs without a database, network, or web server; Spring creates only a lightweight context with one bean.

### 7.1. Layout

```text
testcontext-inheritance-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── SpringContextInheritanceTest.java
```

### 7.2. Complete `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>testcontext-inheritance-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

The project uses the Boot parent to manage Spring Framework, JUnit, and test dependencies. Do not declare separate versions for `spring-test`/JUnit/Mockito. When applying this to a project that already has a BOM, keep **your project's official version** instead of copying `3.5.0`.

### 7.3. Complete `SpringContextInheritanceTest.java`

```java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.NestedTestConfiguration;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

// Lightweight context proving properties apply when creating the bean.
@Configuration(proxyBeanMethods = false)
class MessageConfig {
    @Bean
    MessageReader messageReader(Environment environment) {
        return new MessageReader(
                environment.getProperty("demo.message", "unset"));
    }
}

record MessageReader(String value) {}

// Superclass configuration inherited by subclasses by default.
@SpringJUnitConfig(MessageConfig.class)
@ActiveProfiles("base")
@TestPropertySource(properties = {
        "demo.message=base",
        "demo.common=shared"
})
abstract class BaseSpringTest {
}

@ActiveProfiles("feature")
@TestPropertySource(properties = "demo.message=feature")
class SpringContextInheritanceTest extends BaseSpringTest {

    @Test
    void subclassAddsProfileAndOverridesInlineProperty(
            @Autowired MessageReader reader,
            @Autowired Environment environment) {
        assertEquals("feature", reader.value());
        assertEquals("shared",
                environment.getProperty("demo.common"));
        List<String> profiles =
                Arrays.asList(environment.getActiveProfiles());
        assertTrue(profiles.contains("base"));
        assertTrue(profiles.contains("feature"));
    }

    @Nested
    class InheritedNested {

        @Test
        void inheritsEnclosingConfiguration(
                @Autowired MessageReader reader,
                @Autowired Environment environment) {
            assertEquals("feature", reader.value());
            assertEquals("shared",
                    environment.getProperty("demo.common"));
        }
    }

    @Nested
    @TestPropertySource(properties = "demo.message=nested")
    class NestedWithDifferentProperty {

        @Test
        void nestedPropertyWins(
                @Autowired MessageReader reader,
                @Autowired Environment environment) {
            assertEquals("nested", reader.value());
            assertEquals("shared",
                    environment.getProperty("demo.common"));
            assertTrue(Arrays.asList(environment.getActiveProfiles())
                    .contains("base"));
        }
    }

    @Nested
    @NestedTestConfiguration(
            NestedTestConfiguration.EnclosingConfiguration.OVERRIDE)
    @SpringJUnitConfig(MessageConfig.class)
    @TestPropertySource(properties = "demo.message=isolated")
    class NestedWithOverride {

        @Test
        void doesNotInheritEnclosingProfileAndProperties(
                @Autowired MessageReader reader,
                @Autowired Environment environment) {
            assertEquals("isolated", reader.value());
            assertFalse(Arrays.asList(environment.getActiveProfiles())
                    .contains("base"));
            assertFalse(Arrays.asList(environment.getActiveProfiles())
                    .contains("feature"));
            assertEquals(null, environment.getProperty("demo.common"));
        }
    }
}

// Composed annotation sharing the same config with its own metadata.
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(MessageConfig.class)
@ActiveProfiles("meta")
@TestPropertySource(properties = "demo.message=composed")
@interface MessageScenarioTest {
}

@MessageScenarioTest
class ComposedAnnotationTest {

    @Test
    void composedAnnotationLoadsItsOwnTestMetadata(
            @Autowired MessageReader reader,
            @Autowired Environment environment) {
        assertEquals("composed", reader.value());
        assertTrue(Arrays.asList(environment.getActiveProfiles())
                .contains("meta"));
    }
}
```

Notice that in `NestedWithOverride`, `@SpringJUnitConfig(MessageConfig.class)` is redeclared so the nested class has explicit context metadata. `@NestedTestConfiguration(OVERRIDE)` does not remove Java access to the outer instance, but Spring TestContext annotations from the outer class are not merged under this mode.

The example deliberately avoids injecting a Spring bean into an **outer field** for nested tests: each test method receives beans matching the context of the case it tests. This avoids mistakenly assuming an outer field automatically swaps values for every nested child's context across all Spring Framework versions.

### 7.4. Running and Expected Results

From the directory containing `pom.xml`:

```bash
mvn test
```

You can run the top-level test specifically:

```bash
mvn test -Dtest=SpringContextInheritanceTest
```

Depending on Maven Surefire and JUnit Platform discovery, filtering a single class may select nested classes differently; running `mvn test` is the simplest way to observe all methods in the example.

**Expected:** **5 test methods** total achieve PASS: one on the inheriting class, three inside nested classes, and one on the test using the composed annotation. There is no `System.out.println`, so there is no fixed program stdout. Maven prints logs and test results per plugin configuration; check `target/surefire-reports` if a test fails.

| Test | What It Proves | Expectation |
| --- | --- | --- |
| `subclassAddsProfileAndOverridesInlineProperty` | Subclass inherits parent config, merges `base` + `feature`, overrides property | `reader.value() = "feature"` |
| `InheritedNested.inheritsEnclosingConfiguration` | Nested defaults to INHERIT and gets config from outer | `reader.value() = "feature"` |
| `NestedWithDifferentProperty.nestedPropertyWins` | Nested adds inline property for the same key | `reader.value() = "nested"` |
| `NestedWithOverride.doesNotInheritEnclosingProfileAndProperties` | OVERRIDE ignores enclosing profiles/properties | `reader.value() = "isolated"`; no `base`/`feature` |
| `ComposedAnnotationTest.composedAnnotationLoadsItsOwnTestMetadata` | Custom annotation is read by Spring/JUnit | `reader.value() = "composed"`; profile `meta` |

**Scope limit of the demo:** the test proves only that Spring TestContext loads beans, configurations, and properties. It does not check Spring Boot auto-configuration, transaction rollback, HTTP routes, databases, Security filter chains, or `@SpringBootTest` context initialization.

## 8. When Applying to `@SpringBootTest` and Test Slices

In a real Boot application:

```java
@SpringBootTest
@ActiveProfiles("test")
abstract class BaseBootIntegrationTest {
}

class OrderIntegrationTest extends BaseBootIntegrationTest {
    // @Test methods...
}
```

`@SpringBootTest` participates in Boot-managed bootstrapping; the superclass can supply shared test metadata and `@ActiveProfiles`. You do not necessarily need `@ContextConfiguration` if Boot automatically locates `@SpringBootApplication`/`@SpringBootConfiguration` by package.

### `@TestConfiguration` vs. Boot's `@Configuration`

When a Boot test needs an extra test bean, you can declare a static nested `@TestConfiguration` to **supplement** the application configuration:

```java
@SpringBootTest
class PaymentIntegrationTest {
    @TestConfiguration(proxyBeanMethods = false)
    static class ExtraTestBeans {
        @Bean
        Clock testClock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC);
        }
    }
}
```

This is an illustrative configuration snippet requiring imports and other test/application code to run. A static nested `@Configuration` (not `@TestConfiguration`) can cause Boot to use that configuration **instead of** the primary application configuration during Boot's test config auto-detection; a static nested `@TestConfiguration` is normally added alongside the primary config. A top-level `@TestConfiguration` usually needs explicit `@Import(...)` to appear in a test.

**Do not confuse** a static nested `@TestConfiguration` with a JUnit `@Nested` test class:

| Class Type | Purpose | Typical Declaration |
| --- | --- | --- |
| JUnit nested test | Contains test methods, inherits enclosing test metadata by mode | `@Nested class Cases { ... }` (non-static) |
| Spring test bean config | Defines supporting `@Bean` methods | `@TestConfiguration static class Beans { ... }` |
| Spring `@Configuration` | Defines application/configuration bean graph | `@Configuration static class Config { ... }` |

Slice tests like `@WebMvcTest` and `@DataJpaTest` have their own bootstrappers and scan filters. **Do not stack multiple slice annotations** on one test and assume they merge cleanly. If multiple layers are needed, pick a broader test scope or import supported configurations.

In Boot 4, test starters are split by technology; pick the matching test starter such as `spring-boot-starter-webmvc-test` for MVC tests. Inheritance and composed annotation principles remain valid, though **package imports and module dependencies** for some annotations change when migrating from Boot 3 → 4.

## 9. `TestExecutionListeners`, Transactions, and High-Impact Annotations

### `TestExecutionListeners`

`@TestExecutionListeners` controls which listeners run around the test lifecycle (dependency injection, transactions, SQL, bean overrides, etc.). Custom listeners can be inherited from a superclass or enclosing class depending on mode.

```java
@TestExecutionListeners(
    listeners = MyAuditListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
class AuditTest {
}
```

The snippet above is illustrative only and requires `MyAuditListener` to be a valid implementation. **Do not forget `MERGE_WITH_DEFAULTS`** if you want to keep default listeners alongside your custom listener. Declaring custom listeners without merging can strip dependency injection or test transactions because the config replaces the default listener set.

`inheritListeners=false` only controls inherited listeners, not `mergeMode`. Just like other annotations with inherit flags, check both axes: superclass declarations and enclosing class declarations when using `@Nested`.

### `@Transactional` on Base or Composed Annotations

`@Transactional` in TestContext typically activates test-managed transactions and rolls back after each method by default when an appropriate transaction manager exists. If a base test or composed annotation carries `@Transactional`, child tests will experience its effects without seeing the annotation written directly on the class.

- Service tests needing to verify real post-transaction commits/side effects may have problems masked by automatic rollback.
- Tests with `@SpringBootTest(webEnvironment=RANDOM_PORT)` making HTTP calls on a separate server thread cannot rely on the test method's transaction to roll back server-side transactions.
- With `@Nested` classes having different transaction configs, verify the inheritance mode and the effective annotation.
- Put `@Transactional` into a custom annotation only for suites where rollback is part of the test contract.

### `@Sql`, `@Rollback`, `@DirtiesContext`

`@Sql` can load datasets before tests or clean up, `@Rollback` alters transaction behavior, and `@DirtiesContext` closes/evicts the cache entry. If a composed annotation includes them, every test using it is affected. Avoid putting `@DirtiesContext` on all tests just for "clean data" since it increases context startup time and can mask poor fixture design.

## 10. Context Caching: Identical Structure Does Not Always Mean a New Context

Spring TestContext caches `ApplicationContext` instances by **merged context configuration**, not simply by class name. Cache key components can include:

- `@ContextConfiguration` classes/locations/initializers, context loaders, and hierarchies.
- `@ActiveProfiles`.
- `@TestPropertySource` properties and locations.
- Context customizers, including `@DynamicPropertySource`, `@MockitoBean`/bean overrides, and Spring Boot customizers.
- Other Spring test settings affecting how the context loads.

Example:

| Test | Config | Profile | Inline properties | Context Reused? |
| --- | --- | --- | --- | --- |
| Test A | `MessageConfig` | `base` | `demo.message=base` | First context |
| Test B | `MessageConfig` | `base` | `demo.message=base` | **May** reuse if the entire cache key matches |
| Test C | `MessageConfig` | `base` | `demo.message=feature` | Usually a different key |
| Test D | `MessageConfig` | `feature` | `demo.message=base` | Usually a different key |
| Test E | `MessageConfig` | `base` | `demo.message=base` + different mock bean | May differ due to context customizers |

**Do not use `assertSame(contextA, contextB)` as a guarantee across Maven forks or JVMs.** The cache is static inside the same TestContext process; when a build tool spawns a new process, the context reloads. By default Spring caps cache size and evicts LRU entries; `@DirtiesContext` also prevents standard reuse.

When two different composed annotations end up producing **equivalent merged metadata**, Spring can still share the same context. Conversely, two classes with the same base annotation where one adds a different `@TestPropertySource` get separate contexts.

### Informed Optimization

1. Keep shared configuration in one place; avoid giving tests semantically identical properties with unnecessary **whitespace/ordering differences**. For inline test properties, the declared strings can participate in the cache key.
2. Use `@DirtiesContext` only if a test truly mutates context/bean state in a way that cannot be reset safely.
3. If tests legitimately need different configurations, accept separate contexts; do not force reuse and cross-contaminate data or beans.
4. Prefer test slices or pure unit tests when a test does not need the full application context.
5. When tests run slowly, inspect cache statistics before blindly cranking up parallelism or turning everything into a shared singleton.
6. With Testcontainers and `@DynamicPropertySource`, if dynamic properties produce different values across subclasses sharing the same config metadata/cache key, consider `@DirtiesContext` or dedicated context configs to avoid pointing to a stale container connection.

## 11. Common Pitfalls, Causes, and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Nested test fails to inject outer-configured bean | `OVERRIDE` mode or missing own config; incompatible version/package | Check `@NestedTestConfiguration` and declare `@SpringJUnitConfig` when overriding |
| Subclass gets unwanted beans from base | `inheritLocations=true` by default | Review `@ContextConfiguration(inheritLocations=false)` if replacing config |
| Wanted to replace profile but still see base profile | `inheritProfiles=true` by default | Use `inheritProfiles=false` when truly isolating profiles |
| Set `inheritProperties=false` yet still see parent property file | `inheritProperties` applies only to inline properties | Also check `inheritLocations=false` on `@TestPropertySource` |
| Subclass reads unexpected property value | Inline property shadowed by other config or dynamic properties | Inspect `Environment`/`PropertySources` and check precedence |
| Adding custom listener breaks `@Autowired` | Accidentally replaced all default listeners | Use `MERGE_WITH_DEFAULTS` |
| Putting `@Transactional` in custom annotation causes tests to always roll back | Composed annotation side effect | Audit meta-annotations and write dedicated commit integration tests |
| Context reloads too many times | Varying profiles/properties/mock customizers or `@DirtiesContext` | Check cache keys and eliminate unnecessary configuration variants |
| Outer field injects bean from context A while nested test uses context B | Expecting outer field to switch per nested configuration | Inject dependencies in nested class/test methods rather than relying on outer fields |
| `@Nested` reports no tests or structure error | Used a `static` class or unsupported runner/JUnit version | Use a non-static inner class, JUnit Jupiter engine, and proper test platform |
| Custom annotation ignored by Spring | Missing `@Retention(RUNTIME)`, wrong `@Target`, or missing meta-annotation | Inspect declaration and imports; run a test to confirm |
| `@AliasFor` reports invalid alias configuration | Mismatched type/default/attribute or conflicting meta-annotations | Follow alias contract and verify when Spring synthesizes annotations |
| Used `@SpringJUnitConfig` in Boot test and auto-config is missing | `@SpringJUnitConfig` only builds context from explicit Spring config | Pick `@SpringBootTest` or a test slice when Boot features are needed |
| Used nested `@Configuration` instead of `@TestConfiguration` in Boot | Unintentionally replaces primary configuration | Use static nested `@TestConfiguration` when supplementing |
| 6.2 test behaves differently on 7.x in nested injection/lifecycle | Changes in `SpringExtension` scoping with nested hierarchies | Check upgrade notes; avoid outer fields depending on nested contexts |
| Inherited annotation plus multiple slice-test annotations | Conflicting bootstrap strategies | Pick one appropriate test bootstrap/slice for the test level |

## 12. Test Suite Design Workflow and Checklist

### 8-Step Workflow

1. **Define the test goal**: pure unit, Spring context, slice, or full Boot integration. Do not create a context if unnecessary.
2. **Identify shared parts**: bean configs, test properties, active profiles, listeners, transactions, data fixtures.
3. **Choose the abstraction**: abstract base class for fixtures/helpers; `@Nested` for domain scenarios; composed annotations for reusable metadata.
4. **Lock down inheritance rules**: explicitly check `inheritLocations`/`inheritInitializers`/`inheritProfiles`/`inheritProperties` and `INHERIT`/`OVERRIDE`.
5. **Choose the smallest override scope**: to change one key, add `@TestPropertySource` on the subclass/nested class; for a completely separate context, declare `OVERRIDE` and full config.
6. **Test the merged configuration**: assert injected beans, actual `Environment` values, active profiles, and key behaviors. Do not guess from annotation names.
7. **Evaluate caching and side effects**: differing profile/property keys create separate contexts; transaction rollbacks and `@DirtiesContext` impact the suite.
8. **Run all tests on JUnit Platform** and inspect reports to confirm nested/composed tests are genuinely discovered and executed.

### Acceptance Checklist

- [ ] Understand the difference between superclass inheritance and enclosing `@Nested` inheritance?
- [ ] Know which annotations `@SpringJUnitConfig` bundles?
- [ ] `@ContextConfiguration` has appropriate `inheritLocations`/`inheritInitializers`?
- [ ] `@ActiveProfiles(inheritProfiles=...)` used properly when adding vs. replacing profiles?
- [ ] `@TestPropertySource` distinguishes inheritance flags for inline properties vs. resource locations?
- [ ] Verified actual property values via `Environment`?
- [ ] `@Nested` is a non-static class and `INHERIT`/`OVERRIDE` mode is chosen intentionally?
- [ ] Nested class provides complete config of its own when using `OVERRIDE`?
- [ ] Did not confuse `@Nested` with Boot's static nested `@TestConfiguration`?
- [ ] Custom composed annotation has accurate `@Target`, `@Retention(RUNTIME)`, and meta-annotations?
- [ ] If using `@AliasFor`, the alias was actually tested and has no conflicts?
- [ ] `@TestExecutionListeners` preserves default listeners when needed?
- [ ] `@Transactional`, `@Sql`, and `@DirtiesContext` do not cause unintended side effects?
- [ ] Context cache is reused when metadata matches, and differences are intentional?
- [ ] Executed all test methods across superclass/nested/composed annotations without accidental runner filtering?
- [ ] If migrating Spring Boot 3 → 4, audited modules, JUnit version, and `SpringExtension` lifecycle?

## 13. Official References

1. [Spring Framework — Context Configuration Inheritance](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/inheritance.html): `@ContextConfiguration` and its two inherit flags.
2. [Spring Framework — @Nested test class configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html): `INHERIT`, `OVERRIDE`, and nested examples.
3. [Spring Framework — Spring JUnit Jupiter Testing Annotations](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-junit-jupiter.html): `@SpringJUnitConfig`, `@NestedTestConfiguration`, and supported annotation catalog.
4. [Spring Framework — Meta-Annotation Support for Testing](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-meta.html): custom composed annotations.
5. [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): inheritance and precedence of inline/file properties.
6. [Spring Framework — Active Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html): `inheritProfiles` and resolvers.
7. [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): context cache keys and reload timing.
8. [Spring Framework — TestExecutionListener Configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html): `inheritListeners` and `MERGE_WITH_DEFAULTS`.
9. [JUnit Jupiter — Nested Tests](https://docs.junit.org/5.14.1/writing-tests/nested-tests.html): `@Nested` syntax and lifecycle.
10. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@TestConfiguration`, test slices, and context caching.

**Key takeaway:** superclasses and `@Nested` determine **where Spring TestContext metadata is inherited from**; `@NestedTestConfiguration` determines **whether enclosing class metadata is inherited**; composed annotations determine **how reusable metadata is packaged**. Always verify with **actual beans, properties, and profiles** before optimizing context caching.
