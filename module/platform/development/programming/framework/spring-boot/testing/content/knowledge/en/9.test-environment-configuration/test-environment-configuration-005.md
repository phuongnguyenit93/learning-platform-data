# @TestPropertySource and `properties` on Spring Boot Test Annotations

When a test needs to run with configuration different from the regular application—such as a lower base fee, an enabled feature flag, or a mock endpoint—Spring Boot allows **overriding individual properties in the test's `Environment`**. Two common tools are Spring Test's `@TestPropertySource` and the `properties` attribute on `@SpringBootTest` or slice test annotations. They let tests use the desired settings without editing the original `application.yml`, though you must understand **configuration sources, precedence order, context scope, and how to verify values actually bound into beans**.

This lesson focuses on usage, comparisons, override precedence, and common mistakes; the complete examples use **Java 17, Spring Boot 3.3.x, Gradle, and JUnit Jupiter**.

## 1. Why override properties for a single test?

Suppose an application has this configuration:

```yaml
pricing:
  base-fee: 100
  provider: standard
  feature-enabled: false
```

The application uses `pricing.base-fee` to compute `total = subtotal + baseFee`. When testing the total calculation rule, you want the fee set to `20` for clean, readable assertions, or you want `feature-enabled=true` for a specific scenario. Editing the application configuration directly for every test does not scale because tests have different needs and may run within the same build.

With Spring TestContext, test annotations help create an `ApplicationContext` with **test-specific property sources**. When a bean uses `@Value`, `Environment`, or `@ConfigurationProperties`, it receives the overridden values within that context.

Short example:

```java
@SpringBootTest(properties = "pricing.base-fee=20")
class PricingTest {
    // Beans created by Spring in the test context see the corresponding configuration.
}
```

This is a snippet; runnable Java files and detailed assertions appear in Section 5. **Merely seeing the annotation does not prove the bean used the right value**: tests should assert effective properties and/or service behavior that depends on them.

## 2. Four ways to supply configuration to the test environment

| Mechanism | Example | Best suited when | Caveats to note |
| --- | --- | --- | --- |
| `@SpringBootTest(properties = ...)` | `@SpringBootTest(properties = "pricing.base-fee=20")` | A few dedicated values for an integration test using a full Spring Boot context | `properties` are added to the test context; does not alter original config files |
| `@TestPropertySource(properties = ...)` | `@TestPropertySource(properties = "pricing.base-fee=35")` | Expressing Spring TestContext overrides directly, optionally combining files and inline | Requires running under Spring TestContext; inline beats file within the same annotation |
| `@TestPropertySource(locations = ...)` | `@TestPropertySource(locations = "classpath:/pricing-override.properties")` | Multiple shared keys or an explicit configuration fixture | Loads `.properties` or Java XML properties by default; does not load YAML directly by default |
| `@ActiveProfiles("test")` + `application-test.yml` | Test profile selects config-data per Spring Boot rules | A test environment configuration with many properties or profile-specific beans | Profiles and property overrides are complementary, not identical |

Spring Boot slice test annotations such as `@WebMvcTest(properties = ...)` or `@DataJpaTest(properties = ...)` also accept a `properties` attribute in supported versions. **It affects that slice's test context**, without automatically expanding the slice into the full application. For instance, an MVC slice does not prove datasource configuration or repository transactions work if those beans are outside the slice.

### Are `@SpringBootTest(properties)` and `@TestPropertySource` the same annotation?

No. Spring Boot's `@SpringBootTest` builds the application context via Boot's startup mechanism while allowing extra attributes via `properties` (or its `value` alias). `@TestPropertySource` belongs to **Spring Test**, adding file or inline property sources to the `Environment` of the context managed by the test framework. They can be used together, though you should avoid setting conflicting values for the same key unless the test specifically verifies precedence.

A plain Java unit test using `@Test` **without activating Spring TestContext** will not automatically load properties from `@TestPropertySource`. If you only need a unit test for `new PriceService(new PricingProperties(...))`, pass the configuration directly rather than booting a context just to supply an integer.

## 3. `@TestPropertySource`: three important configuration forms

### 3.1. Inline `properties`: concise and close to the test

```java
@SpringBootTest
@TestPropertySource(properties = {
    "pricing.base-fee=35",
    "pricing.provider=inline-test"
})
class InlinePropertySourceTest {
}
```

Each element is a Java properties-style key/value declaration. You can use `key=value`, `key:value`, or whitespace per Spring Test syntax; good practice is **consistently using `key=value`** for readability and to avoid unnecessary variations in the test context cache key. In Java annotations, use string literals; you cannot compute dynamic Java expressions like `"pricing.base-fee=" + someRuntimeValue` inside an annotation.

### 3.2. `locations`: loading a reusable file

```java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/pricing-override.properties"
)
class FilePropertySourceTest {
}
```

The file should be placed in `src/test/resources/pricing-override.properties` if used only for tests:

```properties
pricing.base-fee=70
pricing.provider=file-test
pricing.feature-enabled=true
```

Writing `classpath:/...` makes the path relative to the classpath root explicit; it avoids confusion with relative paths. With `@TestPropertySource("some.properties")`, a path without a slash or protocol is interpreted relative to the package of the annotated class. The file must actually exist on the test runtime classpath; path mistakes usually cause context startup to fail.

**File format:** `@TestPropertySource` supports Java `.properties` and XML properties files by default. Even though Spring Boot loads `application.yml` or `application-test.yml` via config-data, **do not pass `@TestPropertySource(locations = "classpath:/custom.yml")` assuming YAML is understood automatically**. Spring Framework 6.1 supports a custom `factory` for other formats; if customization is unnecessary, use `.properties` files or Boot profile YAML as supported.

### 3.3. Using file and inline together: inline wins on duplicate keys

```java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/pricing-override.properties",
    properties = "pricing.base-fee=35"
)
class FileAndInlinePricingTest {
}
```

Assuming the file has `pricing.base-fee=70`, `pricing.provider=file-test`, and `pricing.feature-enabled=true`, the effective values in the test context are:

| Key | Test file | Inline | Value used |
| --- | --- | --- | --- |
| `pricing.base-fee` | `70` | `35` | **35** |
| `pricing.provider` | `file-test` | Not declared | **file-test** |
| `pricing.feature-enabled` | `true` | Not declared | **true** |

This is a precedence rule verifiable in code in Section 5. It fits when most properties live in a shared file while certain tests override one or two keys.

### 3.4. No arguments: default file detection mechanism

An empty `@TestPropertySource` **does not** mean "load every test file." Spring Test looks for a default file matching the test class: for `com.example.PricingTest`, the default name is `classpath:com/example/PricingTest.properties`. If the default file is missing, Spring may throw `IllegalStateException`. Therefore, in tutorials and large projects, specifying `locations` or `properties` explicitly reduces confusion.

## 4. Precedence order: which key actually wins?

Spring Boot has many property sources: defaults, application config-data, environment variables, Java system properties, command-line args, test annotations, and dynamic sources. When a key appears in multiple sources, the higher-precedence source decides the value returned by `Environment`.

In Spring Boot **3.3**, externalized configuration documentation lists test sources above config-data/command-line arguments. For the two annotations covered here, remember these key relationships:

1. Inline values in `@TestPropertySource(properties = ...)` **take precedence over** values for the same key in `@TestPropertySource(locations = ...)`.
2. `@TestPropertySource` in Boot 3.3 is ranked **above** the `properties` attribute on `@SpringBootTest`/test slices when configuring the same key.
3. `@SpringBootTest(properties = ...)` is commonly used to override values from `application.yml`, `application.properties`, and `application-{profile}.yml` in the test context.
4. A dynamic property source created by `@DynamicPropertySource` has high precedence in Spring TestContext. When combining multiple test mechanisms that write **the same key**, do not guess from annotation order in the source file: check the actual **Environment and bound bean** in your framework version.

Spring Framework documentation covers `@DynamicPropertySource` and `@TestPropertySource` in separate sections, while Boot 3.3 docs provide the overall precedence table; whenever overlapping dynamic and inline sources form part of a test's contract, verify the effective runtime value directly. The examples in Section 5 **avoid colliding dynamic properties with `@TestPropertySource`** so each assertion has a clear meaning.

### Reading the effective value instead of guessing

```java
@Autowired
Environment environment;

@Test
void selectedPropertyIsVisible() {
    assertEquals(
            "35", environment.getProperty("pricing.base-fee"));
}
```

This snippet belongs inside a Spring test class with the appropriate imports. Beyond `Environment`, assert the **`@ConfigurationProperties` bean or service result**, because a property can appear as a string in `Environment` yet fail type binding, field name matching, or business usage.

### Where do overridden properties apply?

These annotations **do not modify YAML files** and do not write back to the operating system environment. They contribute property sources to the test's `ApplicationContext`. If two test classes use different configs, Spring TestContext may create two separately cached contexts. Never expect an override in test A to act as a global default for test B.

## 5. Runnable Spring Boot 3.3.x project: testing all override forms

The example uses **Java 17, Spring Boot 3.3.5, Gradle Groovy DSL, and JUnit Jupiter** without needing a database or web server. `PricingProperties` is bound by Spring Boot from `Environment`, and `QuoteService` uses that value to compute fees. Thus assertions check both the property source and actual behavior.

### 5.1. Layout

```text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/testproperties/PropertyDemoApplication.java
src/main/java/com/example/testproperties/PricingProperties.java
src/main/java/com/example/testproperties/QuoteService.java
src/test/resources/pricing-override.properties
src/test/resources/application-test.yml
src/test/java/com/example/testproperties/BootInlinePropertiesTest.java
src/test/java/com/example/testproperties/FileAndInlinePropertiesTest.java
src/test/java/com/example/testproperties/CombinedAnnotationsTest.java
src/test/java/com/example/testproperties/ActiveProfilePropertiesTest.java
src/test/java/com/example/testproperties/DynamicPricingPropertyTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'test-property-overrides'
```

**`build.gradle`**

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` includes the required Spring/JUnit testing libraries. Use a Gradle Wrapper compatible with Java 17 and Spring Boot 3.3.5 for the commands below. No HTTP server is required because the lesson examines binding, precedence, and service behavior.

**`src/main/resources/application.yml`**

```yaml
pricing:
  base-fee: 100
  provider: standard
  feature-enabled: false
```

These are the example's default values; without an override or test profile, the service adds a fee of `100` to `subtotal`.

**`src/main/java/com/example/testproperties/PropertyDemoApplication.java`**

```java
package com.example.testproperties;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PropertyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PropertyDemoApplication.class, args);
    }
}
```

**`src/main/java/com/example/testproperties/PricingProperties.java`**

```java
package com.example.testproperties;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "pricing")
public record PricingProperties(
        int baseFee,
        String provider,
        boolean featureEnabled) {
}
```

`@ConfigurationPropertiesScan` lets Spring Boot discover and register the `PricingProperties` record. For a Java record with one canonical constructor, Spring Boot binds constructor parameters from `pricing.base-fee`, `pricing.provider`, and `pricing.feature-enabled`. Types `int` and `boolean` are converted from the property source. The example includes no Bean Validation constraints, so this is a **binding demo**, not a demo of rejecting missing or invalid configs.

**`src/main/java/com/example/testproperties/QuoteService.java`**

```java
package com.example.testproperties;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final PricingProperties pricing;

    public QuoteService(PricingProperties pricing) {
        this.pricing = pricing;
    }

    public int quote(int subtotal) {
        if (subtotal < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be non-negative");
        }
        return Math.addExact(subtotal, pricing.baseFee());
    }
}
```

`quote(100)` must return `120` when `baseFee=20`, `135` when `baseFee=35`, and `180` when `baseFee=80`. `Math.addExact` throws `ArithmeticException` on `int` overflow; this is pure Java behavior independent of property sources so the demo never overflows silently.

### 5.2. `@SpringBootTest(properties)` test: concise annotation-level override

**`src/test/java/com/example/testproperties/BootInlinePropertiesTest.java`**

```java
package com.example.testproperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(properties = {
        "pricing.base-fee=20",
        "pricing.provider=boot-inline"
})
class BootInlinePropertiesTest {
    @Autowired
    private Environment environment;

    @Autowired
    private PricingProperties pricing;

    @Autowired
    private QuoteService service;

    @Test
    void inlinePropertiesReachEnvironmentBeanAndBusinessCode() {
        assertEquals("20", environment.getProperty("pricing.base-fee"));
        assertEquals(20, pricing.baseFee());
        assertEquals("boot-inline", pricing.provider());
        assertFalse(pricing.featureEnabled());
        assertEquals(120, service.quote(100));
    }
}
```

`pricing.feature-enabled` is not overridden in the annotation, so it continues to take `false` from `application.yml`. This demonstrates **selective** overriding rather than replacing the whole configuration set.

### 5.3. `@TestPropertySource(locations, properties)` test: file plus inline

**`src/test/resources/pricing-override.properties`**

```properties
pricing.base-fee=70
pricing.provider=file-test
pricing.feature-enabled=true
```

**`src/test/java/com/example/testproperties/FileAndInlinePropertiesTest.java`**

```java
package com.example.testproperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@TestPropertySource(
        locations = "classpath:/pricing-override.properties",
        properties = "pricing.base-fee=35"
)
class FileAndInlinePropertiesTest {
    @Autowired
    private Environment environment;

    @Autowired
    private PricingProperties pricing;

    @Autowired
    private QuoteService service;

    @Test
    void inlineValueOverridesFileButOtherFileValuesRemain() {
        assertEquals("35", environment.getProperty("pricing.base-fee"));
        assertEquals(35, pricing.baseFee());
        assertEquals("file-test", pricing.provider());
        assertTrue(pricing.featureEnabled());
        assertEquals(135, service.quote(100));
    }
}
```

Three sources define `pricing.base-fee`: `application.yml` (100), `pricing-override.properties` (70), and inline `@TestPropertySource` (35). The result `35` intentionally verifies **inline override**. The test also proves keys defined only in the test file are bound properly.

### 5.4. Combining both annotations and checking precedence in Boot 3.3

**`src/test/java/com/example/testproperties/CombinedAnnotationsTest.java`**

```java
package com.example.testproperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
        "pricing.base-fee=15",
        "pricing.provider=boot-annotation"
})
@TestPropertySource(properties = "pricing.base-fee=45")
class CombinedAnnotationsTest {
    @Autowired
    private PricingProperties pricing;

    @Autowired
    private QuoteService service;

    @Test
    void testPropertySourceWinsForTheSameKey() {
        assertEquals(45, pricing.baseFee());
        assertEquals("boot-annotation", pricing.provider());
        assertEquals(145, service.quote(100));
    }
}
```

In Spring Boot 3.3's precedence order, `@TestPropertySource` ranks above test annotation `properties`. Therefore **`base-fee=45`** from `@TestPropertySource` beats `base-fee=15` from `@SpringBootTest`. Meanwhile `pricing.provider` is overridden only by `@SpringBootTest`, resulting in `boot-annotation`.

This test is **for learning and proving precedence**, not a recommendation to routinely duplicate keys. In business tests, having a single override source per key is much easier to maintain.

### 5.5. Test profile: YAML belongs to Boot's config-data mechanism

**`src/test/resources/application-test.yml`**

```yaml
pricing:
  base-fee: 80
  provider: profile-test
  feature-enabled: true
```

**`src/test/java/com/example/testproperties/ActiveProfilePropertiesTest.java`**

```java
package com.example.testproperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class ActiveProfilePropertiesTest {
    @Autowired
    private PricingProperties pricing;

    @Autowired
    private QuoteService service;

    @Test
    void profileSpecificYamlOverridesBaseConfiguration() {
        assertEquals(80, pricing.baseFee());
        assertEquals("profile-test", pricing.provider());
        assertTrue(pricing.featureEnabled());
        assertEquals(180, service.quote(100));
    }
}
```

`@ActiveProfiles("test")` activates the `test` profile in the context; Boot automatically loads matching config-data such as `application-test.yml`. `@ActiveProfiles` is not `@TestPropertySource` and does not need you to point to the YAML path via `locations`.

If the same key is also set in `@SpringBootTest(properties)` or `@TestPropertySource(properties)`, the test override wins over the profile YAML value. When the entire test suite needs a shared base configuration, profile YAML is a clean starting point; when a single class needs 1–2 small variations, use inline properties.

### 5.6. Dynamic properties: `@DynamicPropertySource` for values generated at runtime

**`src/test/java/com/example/testproperties/DynamicPricingPropertyTest.java`**

```java
package com.example.testproperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class DynamicPricingPropertyTest {
    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("pricing.base-fee", () -> 65);
    }

    @Autowired
    private PricingProperties pricing;

    @Autowired
    private QuoteService service;

    @Test
    void dynamicPropertyIsBoundIntoTheContext() {
        assertEquals(65, pricing.baseFee());
        assertEquals(165, service.quote(100));
    }
}
```

`@DynamicPropertySource` fits when values are only known at test runtime, such as a real container's port URL. The registration method must be `static` and accept a single `DynamicPropertyRegistry`. The `Supplier` supplies the value when resolved; **do not treat this as a mechanism that automatically updates already-bound beans if the supplier changes after context startup**.

In the example, the dynamic key is placed in only one test source to avoid precedence conflicts. With dynamic containers, you must also manage container/resource lifecycle; getting the right property into Spring does not by itself prove the dependency is healthy or the business test succeeds.

## 6. Running the full example and verifying values yourself

With a suitable Gradle Wrapper in place, run from the project root:

```bash
./gradlew test
./gradlew test --tests com.example.testproperties.BootInlinePropertiesTest
./gradlew test --tests com.example.testproperties.FileAndInlinePropertiesTest
./gradlew test --tests com.example.testproperties.CombinedAnnotationsTest
./gradlew test --tests com.example.testproperties.ActiveProfilePropertiesTest
./gradlew test --tests com.example.testproperties.DynamicPricingPropertyTest
```

On Windows, use `gradlew.bat test` with the same arguments. The tests run JUnit Jupiter and Spring TestContext; `bootRun` is not needed to verify these annotations because `@SpringBootTest` builds the context for the tests. These tests do not start an HTTP server (`@SpringBootTest` defaults to a mocked web environment when web starter is present; this demo adds no web starter).

With the code and properties above, **the checks are designed to PASS**. That is the expected result from the example logic, not live Gradle stdout. Each test asserts both bound values and service output, preventing cases where `Environment` contains the key yet the service uses the wrong value.

### Expected value table to compare when tests are green

| Test class | Final base fee | Provider | Feature enabled | `service.quote(100)` |
| --- | ---: | --- | --- | ---: |
| `BootInlinePropertiesTest` | 20 | `boot-inline` | false | 120 |
| `FileAndInlinePropertiesTest` | 35 | `file-test` | true | 135 |
| `CombinedAnnotationsTest` | 45 | `boot-annotation` | false | 145 |
| `ActiveProfilePropertiesTest` | 80 | `profile-test` | true | 180 |
| `DynamicPricingPropertyTest` | 65 | `standard` | false | 165 |

If an assertion fails to match, check **which annotations the test class has, which profile is active, whether resource files are on the classpath, and whether another property source sets the same key**. Never adjust expected results to match whatever value happens to appear just to make tests pass; first establish what the intended configuration requirement is.

## 7. Context caching: property annotations affect test speed

Spring TestContext caches the `ApplicationContext` by **merged context configuration**. Factors such as configuration classes, active profiles, test property locations, inline test properties, and context customizers affect the cache key. Two tests with different inline values for the same key normally require separate contexts; Spring does not "switch" the same context from fee 20 to 35 merely by changing an annotation.

Practical consequences:

- Assigning unnecessarily different inline properties across dozens of classes can increase context startup counts.
- Inline lines with different formatting or whitespace yet identical meaning can also affect cache matching because Spring uses configuration strings in the cache key. Pick a convention like `pricing.base-fee=20` and stick to it consistently.
- If multiple tests share the same configuration, group properties into an appropriate profile/file or use a test base class/composed annotation as needed to reduce duplication.
- `@DirtiesContext` asks to evict a modified context from the cache; do not use it just to toggle a property per test method when separate test classes/contexts make more sense.

Important: **properties declared on annotations are normally resolved when the context is built**, not switches you can flip freely from one test method to the next. Calling `System.setProperty("pricing.base-fee", "99")` after the `PricingProperties` bean has bound will not make the record bean pick up `99`. Worse, system properties are JVM-wide and can leak state between parallel tests.

## 8. `@TestPropertySource` inheritance and declaration order

When a test class inherits from a superclass annotated with `@TestPropertySource`, Spring Test supports `inheritLocations` and `inheritProperties`, both **true** by default. Subclasses can add files and inline properties; on duplicate keys, higher-precedence sources win. To **replace** instead of inherit a group, set `inheritLocations=false` or `inheritProperties=false` accordingly.

The following are **illustrative snippets**; they are not in the runnable project in Section 5:

```java
@TestPropertySource(properties = "pricing.provider=parent")
abstract class ParentTestConfig {
}

@TestPropertySource(properties = "pricing.provider=child")
class ChildPricingTest extends ParentTestConfig {
}
```

The subclass receives `provider=child` for this key. `@TestPropertySource` is also repeatable on a single class in modern Spring Framework; configurations merge per TestContext rules. When multiple annotations or meta-annotations are present, inspect effective values via `Environment` instead of guessing from source-file text order.

If designing many test classes inheriting base settings, consider a **composed annotation** or base test context to clarify shared defaults. Also avoid inheriting overly broad overrides that cause new tests to accidentally use the wrong datasource, timeout, or feature flag.

## 9. Common mistakes and how to handle them

| Symptom | Common cause | Correct fix |
| --- | --- | --- |
| `@TestPropertySource("config.yml")` fails to read file properly | The annotation's default loader does not parse YAML automatically | Use `.properties` or Boot's `application-test.yml` via profile; only use a custom factory when needed |
| Empty `@TestPropertySource` fails | Default file matching the test class name is missing | Specify `locations` or `properties` explicitly |
| Misspelled inline key; bean keeps default | Key typo; another configuration supplies fallback | Assert both `Environment` and `@ConfigurationProperties`; check canonical kebab-case |
| Test changes a property, yet bean keeps old value | Bean was bound at context startup; system property changed too late | Declare source before startup or create a context with the right config |
| Tests A and B have different configs but expected same bean | TestContext cache key varies with annotations/profiles | Accept separate contexts or share configuration where appropriate |
| `@TestPropertySource(locations=...)` cannot find file | Wrong classpath or relative path mistake | Use `classpath:/...`, verify the file is in `src/test/resources` |
| Both annotations set the same key; unclear which wins | Overlapping property sources with different precedence | Remove redundant declarations unless intentionally testing precedence at runtime |
| Calling `new QuoteService(...)` expecting property overrides | No Spring TestContext running to bind config | Use `@SpringBootTest`/slice as needed and retrieve bean via `@Autowired` |
| `@ActiveProfiles("test")` enabled, yet YAML ignored | Wrong filename/path, different profile, or higher-precedence override | Check `application-test.yml`, active profiles, `Environment`, and colliding keys |
| Mocked database and assumed datasource override works | Mock bypassed real DB connection path | Test context/wiring and integration tests with a real datasource |
| Tests behave differently between IDE and CI | Mismatched JVM args, profiles, test resources, env vars | Standardize execution; assert critical settings instead of trusting defaults |

### Distinguishing "property exists" from "behavior is properly configured"

For example, a test containing only:

```java
assertEquals("35", environment.getProperty("pricing.base-fee"));
```

only proves `Environment` can look up the string `35`. If `PricingProperties` was not scanned or the service never injects that bean, that line can pass while the application never uses `35`. That is why the demo also asserts `pricing.baseFee() == 35` **and** `service.quote(100) == 135`. Those are three steps of evidence: key present → binder mapped it → business code used it.

Likewise, if a boolean property is configured from string `true`, assert `pricing.featureEnabled()` rather than just checking text contains `true`. For complex data, test type conversion, missing properties, and validation when required.

## 10. When to pick which approach in a real project?

**Choose `@SpringBootTest(properties)`** when a full-context test needs a couple of dedicated keys, such as `feature.enabled=false` or safe timeouts. It is concise and lets reviewers see the test scenario right away.

**Choose `@TestPropertySource(properties)`** when you want Spring Test's property source mechanism, especially when combining with `locations`, inheriting settings, or demonstrating precedence explicitly.

**Choose `@TestPropertySource(locations)`** when many keys belong in a shared `.properties` fixture and you want them out of Java annotations. Keep files small and descriptively named; avoid turning a test-specific file into a full copy of production config.

**Choose `@ActiveProfiles("test")` + `application-test.yml`** when you need a shared baseline environment configuration across many test classes, profile-conditional beans, or Spring Boot YAML/config-data features.

**Choose `@DynamicPropertySource`** when values only appear after test resources start—typically Testcontainers URLs/ports. Those properties are unknown at compile time, so inline annotations cannot express them well.

These approaches **can be combined**, though you should favor one clear source per key in each scenario. For critical integration tests, assert properties and behavior directly to catch configuration mismatches.

## 11. Knowledge self-check

**A.** `application.yml` sets `pricing.base-fee=100`; `@SpringBootTest(properties = "pricing.base-fee=20")`. Inside the test context, what is the expected fee? **20**. That is an inline override from the Boot test annotation.

**B.** `pricing-override.properties` sets `pricing.base-fee=70`, while `@TestPropertySource(locations=..., properties="pricing.base-fee=35")`. Effective value? **35**, because inline takes higher precedence than `locations` files.

**C.** `@SpringBootTest(properties="pricing.base-fee=15")` and `@TestPropertySource(properties="pricing.base-fee=45")` set the same key in Spring Boot 3.3. What does the example test prove? **45** wins. In business code, avoid creating duplicate-key conflicts unless truly needed.

**D.** Can you point `@TestPropertySource(locations="classpath:/application-test.yml")` and expect YAML to be parsed like Boot config-data by default? **No**. Use `@ActiveProfiles("test")` so Boot loads `application-test.yml`, or supply an appropriate `PropertySourceFactory` if YAML must be loaded through the Spring Test annotation.

**E.** A unit test constructs `new PricingProperties(20, "test", false)` and passes it into `new QuoteService(...)`. Does it verify that `application.yml` was overridden? **No**. It only tests business logic against a manually constructed configuration object.

**F.** A test running in the same JVM calls `System.setProperty` to change a key after the Spring context was already created. Are all `@ConfigurationProperties` records guaranteed to pick up the new value? **No**. Beans were bound during context startup; mutating system properties also risks leaking configuration across tests.

### Checklist when reviewing a PR with property overrides

- Does each key have an intentional override source using the right annotation/context?
- Is `@TestPropertySource(locations)` accidentally mixed with YAML without a factory?
- Are `.properties` test files in `src/test/resources` with explicit paths?
- If `@ActiveProfiles` is used, does the profile YAML load cleanly without higher-precedence test sources silently overriding the same keys?
- Are `Environment`, `@ConfigurationProperties` beans, and necessary business outcomes asserted?
- Do tests avoid relying on JVM-wide system properties or passing only when executed in a specific order?
- Are excessive inline configuration variants fragmenting the context cache?
- Does the chosen test slice contain all beans required to verify the target behavior?
- Are test values clearly separated from production config without generalizing one test context to another deployment environment?

**Conclusion:** `@TestPropertySource` and `properties` on test annotations are tools for **creating configuration values scoped to a test context**. `@TestPropertySource` is flexible with `.properties` files and inline overrides; `@SpringBootTest(properties)` is handy for a few keys right on the test class; profile YAML and dynamic properties address other needs. Reliable usage means **verifying both the actual bound values and bean behavior**, while understanding context scope and precedence so tests remain independent, clear, and maintainable.

### Official references

- Spring TestContext — Test Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Spring Boot 3.3 — Externalized Configuration and PropertySource order: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring TestContext — Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html