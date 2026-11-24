# FilteredClassLoader for Testing When a Dependency Is Absent from the Classpath

A Spring Boot **auto-configuration** library often integrates with optional dependencies: if Jackson is present, create a JSON codec; if a JDBC driver is present, configure a DataSource; if a provider SDK is present, register a client; if the SDK is absent, **do not** initialize the SDK bean or create a valid fallback instead. A bug that slips through easily is that the starter author's own project always has every dependency on the **test classpath**. A "context starts" test therefore stays green, yet a user's application that installs only the auto-config without the SDK hits `ClassNotFoundException`, `NoClassDefFoundError`, reflection errors on `@Bean` signatures, or an unwanted bean still gets registered.

**FilteredClassLoader** is Spring Boot's test utility solving an important part of this problem: it lets an `ApplicationContextRunner` run with a **simulated ClassLoader that cannot see specific classes/packages/resources**, while the Gradle/Maven project still compiles against the dependency. We can quickly test both `@ConditionalOnClass` and `@ConditionalOnMissingClass` branches without altering the dependency graph per test method.

This lesson belongs to the **Auto-Configuration Testing** group of the **Spring Boot – testing** module. Content progresses from classpath/conditional evaluation concepts, `FilteredClassLoader` APIs, and safe design with optional dependencies, to a Java 17+ project and a JUnit 5 suite runnable on **Spring Boot 3.5.16**, then explains **simulation limits**: `FilteredClassLoader` is not a real JVM with the JAR removed; certain JVM linkage/reflection/packaging bugs are only caught by integration tests with a runtime classpath genuinely lacking the module.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain `@ConditionalOnClass`, `@ConditionalOnMissingClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, and each condition's boundaries.
- Understand that `FilteredClassLoader` comes from `spring-boot-test` and is **not** an API to use in production.
- Hide **a single class**, **a package**, **a resource**, or customize via a predicate.
- Write `ApplicationContextRunner.withClassLoader(new FilteredClassLoader(...))`.
- Verify dependency **present** -> optional bean registered; dependency **absent** -> bean disappears and fallback works.
- Verify startup **does not fail** when the class is absent, not merely check bean counts.
- Distinguish a class hidden from the **context ClassLoader** from a dependency removed from the entire JVM/runtime.
- Place optional types inside a **nested `@Configuration` annotated with `@ConditionalOnClass`**, avoiding premature signature reflection.
- Know when to use `name` instead of `value` in composed condition annotations.
- Test `@ConditionalOnMissingBean` back-off when the user already defined their own bean.
- Recognize why `@MockBean`/`@MockitoBean` or `excludeAutoConfiguration` do not substitute for simulating an absent dependency.
- Inspect `ConditionEvaluationReport` to see which conditions matched or mismatched.
- Distinguish `ApplicationContextRunner` for regular contexts from `WebApplicationContextRunner`/`ReactiveWebApplicationContextRunner`.
- Design an additional **runtime packaging test** without the optional JAR when catching real `NoClassDefFoundError` is needed.
- Understand limitations of this test when using native image/AOT or module/OSGi systems.

## 2. Problem: dependency present in tests but missing in the user's app

Suppose there is an auto-config:

```java
// Illustrative code, not a standalone runnable file.
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.VendorClient")
class VendorAutoConfiguration {
    // When SDK is present, create VendorClient bean.
}
```

On the author's machine, `vendor-sdk.jar` is always present because it is declared in `testImplementation`, or because the starter pulls it in. The test:

```java
new ApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(VendorAutoConfiguration.class))
    .run(context -> assertThat(context).hasNotFailed());
```

only verifies the SDK-**present** branch. It does not guarantee that an application using only `my-autoconfigure.jar` without installing the SDK can start cleanly. To protect the remaining branch, we need an environment where Spring **observes** as though `VendorClient` has vanished.

`FilteredClassLoader` gives a fast answer at the test context level:

```java
// Snippet placed inside a test method, with runner having registered auto-config.
runner.withClassLoader(
        new FilteredClassLoader(VendorClient.class))
    .run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).doesNotHaveBean("vendorClient");
    });
```

This is a **simulation scoped to the classloader used by the runner**. Nobody edits `build.gradle`, deletes JARs on disk, changes the whole JVM's classpath, or alters the production application.

## 3. "Classpath missing dependency" spans multiple distinct issues

| Scenario | What is missing | Appropriate test |
|---|---|---|
| `@ConditionalOnClass` must evaluate false | Class name invisible to context classloader | `FilteredClassLoader` + `ApplicationContextRunner` |
| `@ConditionalOnMissingClass` must evaluate true | Class name invisible to context | `FilteredClassLoader` + assert fallback |
| SDK present but bean not yet configured | Bean definition/instance | `@ConditionalOnMissingBean` tests |
| SDK present but property disabled | Environment property | `withPropertyValues` |
| A service metadata/resource missing | Classpath resource | Filter resource + matching condition |
| JAR genuinely not packaged in application | Runtime dependency graph/JVM linkage | Forked JVM or consumer project lacking the JAR |
| Incompatible SDK version | Binary API signature/method | Compatibility/integration tests with real versions |
| Native image missing reflection hints | AOT image build/runtime | Native integration tests, not just runner |
| Client created yet downstream server not running | Network/service | Mock server/Testcontainers/other integration test |

**Do not equate class conditions with bean conditions.** Having a JAR present without a bean still lets `@ConditionalOnClass` match. Conversely, a test-created mock bean can make `@ConditionalOnBean` match even when the production application lacks that bean.

## 4. What is `FilteredClassLoader`?

Spring Boot 3.5 provides the class:

```java
import org.springframework.boot.test.context.FilteredClassLoader;
```

Javadoc describes it as a test `URLClassLoader` able to filter loaded classes and resources; it implements `SmartClassLoader` and `Closeable`. Common constructors:

| Constructor | Use when |
|---|---|
| `new FilteredClassLoader(SomeClass.class)` | Hiding one or more specific classes |
| `new FilteredClassLoader("com.vendor.sdk")` | Hiding all classes in the corresponding package |
| `new FilteredClassLoader(parent, SomeClass.class)` | Needing to specify the parent loader explicitly when simulating |
| `new FilteredClassLoader(new ClassPathResource("..."))` | Wanting to hide a classpath resource |
| `new FilteredClassLoader((Predicate<String>) name -> ...)` | Custom filtering rule by class/resource name |

**API note:** The `String...` constructor in Boot 3.5 accepts **package names**, not an arbitrary FQCN treated as a class name string. If you only need to hide a specific class, pick `SomeClass.class`. If you cannot reference the class at compile time, use a controlled predicate against the binary class name.

### 4.1. Hiding a specific class

```java
new FilteredClassLoader(ThirdPartyClient.class)
```

Within the context classloader, attempting to load `com.example.optional.ThirdPartyClient` is rejected. Other classes in the package may remain visible, depending on what you filter.

### 4.2. Hiding a package

```java
new FilteredClassLoader("com.example.optional")
```

Used when a dependency has multiple entrypoints: client, factory, configuration, serializers, or annotations. It can simulate "a JAR disappeared" better than hiding a single interface. **Do not filter overly broad packages like `org.springframework` or `java`**, as the Spring context would lose the test's own infrastructure.

### 4.3. Hiding a resource

```java
// Snippet: filtering a resource, not a Java class.
new FilteredClassLoader(
        new ClassPathResource("features/optional-adapter.flag"))
```

The constructor takes `ClassPathResource...`. This scenario is useful when testing `@ConditionalOnResource` or an integration's metadata lookup. However, hiding a resource **does not equal** hiding the class that resource describes; to simulate real service/provider discovery, understand which ClassLoader and resource path the lookup code uses.

### 4.4. Custom predicate

```java
// Snippet using java.util.function.Predicate:
Predicate<String> hidden = name ->
        name.equals("com.example.optional.ThirdPartyClient")
        || name.startsWith("com.example.optional.internal.");

FilteredClassLoader loader =
        new FilteredClassLoader(hidden);
```

Javadoc notes the predicate may receive a binary class name **or a resource name**; returning true means **hidden**. When using a custom predicate, pin down the rule clearly and verify it does not unintentionally mask essential dependencies.

## 5. Spring Boot `ApplicationContextRunner`: the right test level

`ApplicationContextRunner` creates a **non-web ApplicationContext** whose properties, user configurations, auto-configurations, bean registrations, and classloader can be customized per test. After the `run(...)` callback, the context closes. It differs from `@SpringBootTest`:

- Does not boot the entire Spring Boot application.
- Does not auto-scan every component in the module just because it sits in a package.
- Each `run` builds a small context for a clear scenario.
- Offers `withConfiguration(AutoConfigurations.of(...))` to test the auto-configuration itself.
- Offers `withClassLoader` to test presence/absence conditions.
- Offers `withBean` or `withUserConfiguration` to test user overrides.
- Offers `withPropertyValues` to test property conditions.
- Offers `hasNotFailed`/`getFailure` and bean assertions to express expectations clearly.

**Important:** `ApplicationContextRunner` is not supported as a direct runner for tests inside a native image. A native image has a different AOT/classpath model and needs separate tests.

### 5.1. Four states to distinguish

```text
Is JAR / class on the classpath?
    |
    +-- Yes:
    |     +-- @ConditionalOnClass matches?
    |     +-- Property allows?
    |     +-- User already provided bean?
    |           -> auto bean created or backs off
    |
    +-- No:
          +-- @ConditionalOnClass false -> do not create optional bean
          +-- @ConditionalOnMissingClass true -> fallback may be created
          +-- ApplicationContext still starts cleanly
```

Checking **only that a bean name is absent** is insufficient if the application context crashed. Therefore, the absence branch must include both `hasNotFailed()` and assertions on the fallback/missing bean.

## 6. `@ConditionalOnClass` and `@ConditionalOnMissingClass`

Conditions are checked via Spring Boot metadata/`OnClassCondition`:

```java
@ConditionalOnClass(ThirdPartyClient.class)
```

means proceed only when the class can be found on the appropriate classpath. Meanwhile:

```java
@ConditionalOnMissingClass(
        "com.example.optional.ThirdPartyClient")
```

means proceed only if the class cannot be found.

Spring Boot uses **ASM metadata** when reading annotations on configuration classes, so referencing a class literal directly in class-level `@ConditionalOnClass` is normally safe even when the dependency is genuinely missing. However:

- For **composed/meta-annotations**, Spring Boot recommends `name = "com.vendor.Type"` over `value = Type.class` because metadata processing differs.
- On a **`@Bean` method**, the JVM may introspect the method signature/return type before the method-level condition is applied.
- A false condition **cannot rescue** other code that actively loads the missing class from a static initializer, constructor, or bean method signature.
- Optional types must be organized inside safe nested configurations (section 7).

## 7. Pitfall #1: placing the condition on a bean method is too late

**Do not write:**

```java
// ANTI-EXAMPLE — broken structure only, do not use as runnable file.
@AutoConfiguration
class FragileAutoConfiguration {

    @Bean
    @ConditionalOnClass(ThirdPartyClient.class)
    ThirdPartyClient client() {
        return new ThirdPartyClient("auto");
    }
}
```

Even with `@ConditionalOnClass` on the method, the JVM may have to resolve `ThirdPartyClient` from the **return type** when Spring reflects `FragileAutoConfiguration`, before the condition skips the method. On a JVM genuinely lacking the SDK, processing bean methods can throw `NoClassDefFoundError`/`IllegalStateException`.

**Pattern recommended in Spring Boot docs:**

```java
@AutoConfiguration(proxyBeanMethods = false)
public class SafeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(ThirdPartyClient.class)
    static class SdkPresentConfiguration {

        @Bean
        ThirdPartyClient thirdPartyClient() {
            return new ThirdPartyClient("auto");
        }
    }
}
```

This snippet assumes full imports. The nested configuration is guarded at the **class level**, before Spring needs to inspect bean method signatures inside.

**Subtlety:** `FilteredClassLoader` helps prove Spring conditions skip the configuration; it **does not necessarily reproduce every linkage error in a real JVM**. Auto-config classes may still be **defined by the parent loader** that sees the optional dependency, masking a real reflection error during simulation. Therefore, both design nested configs per documentation and run real consumer packaging tests for critical optional JARs.

## 8. Pitfall #2: confusing class "present" with bean "present"

`@ConditionalOnClass(ThirdPartyClient.class)` is decided by **type visibility**, not whether a `ThirdPartyClient` bean exists.

`@ConditionalOnMissingBean(ThirdPartyClient.class)` is checked against the **`BeanFactory`** when auto-configuration runs. Typical meaning:

1. `ThirdPartyClient` class exists.
2. User has not configured a `ThirdPartyClient` bean.
3. Auto-configuration creates the default client.
4. If the user configured a custom bean, auto-config **backs off** and creates no duplicate.

Those are **two independent conditions**; tests should include all of:

- Class present -> default bean created.
- Class absent -> no default bean, context still lives.
- Class present + custom user bean -> auto-config backs off.
- Class present + property disabled -> no default bean **even though the dependency is present**.

Do not use `FilteredClassLoader` to pretend "the user has no bean"; use `withBean`/`withUserConfiguration` and assert exact bean counts.

## 9. Runnable Java 17+ project: an auto-config with mock SDK and fallback

The example includes:

- `ThirdPartyClient`: type simulating an optional SDK.
- `VendorClientAutoConfiguration`: creates client if type is present and app has not defined a bean.
- `FallbackAutoConfiguration`: creates `FallbackStatus` if SDK is absent.
- `@ConditionalOnProperty` to prove **disabled** differs from **classpath absent**.
- `AutoConfiguration.imports`: registration metadata for the library when installed in a real app.
- `VendorClientAutoConfigurationTest`: tests using `ApplicationContextRunner` and `FilteredClassLoader`.

**Illustration limitation:** To make a single-module project **easy to copy and test immediately**, the mock SDK `ThirdPartyClient` sits in `src/main/java`. In a **production starter**, the real SDK should reside in a separate artifact and be declared optional/`compileOnly` appropriately. This does not diminish the value of condition unit tests; however, the demo project's package physically contains the mock SDK, so **this project cannot be considered a test of real optional-JAR packaging**. Sections 26–28 explain how to add a consumer test without the JAR.

### 9.1. Directory tree

```text
filtered-classloader-demo/
  settings.gradle
  build.gradle
  src/main/java/com/example/optional/
    ThirdPartyClient.java
  src/main/java/com/example/autoconfig/
    FallbackStatus.java
    VendorClientAutoConfiguration.java
    FallbackAutoConfiguration.java
  src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
  src/test/java/com/example/autoconfig/
    VendorClientAutoConfigurationTest.java
```

There is no `@SpringBootApplication` or `main` because this is an **auto-configuration library**. Tests use `ApplicationContextRunner` directly; no Docker, network, database, or HTTP server required.

## 10. Gradle setup for an auto-configuration library

**`settings.gradle`**

```groovy
rootProject.name = 'filtered-classloader-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java-library'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.16'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Why not apply the Spring Boot Gradle plugin here?** The library has no `main` and needs no executable `bootJar`. `java-library` + Spring Boot BOM accomplish the exact goal: compiling the library and running JUnit tests. An application consuming the starter can apply the Boot plugin itself.

**Dependency for `FilteredClassLoader`:** It belongs to `org.springframework.boot.test.context` inside `spring-boot-test`; `spring-boot-starter-test` brings this test module onto the test scope. Never add `spring-boot-test` to production runtime just to use `FilteredClassLoader` in production.

**Gradle test classpath:** `testImplementation` provides JUnit/AssertJ/Spring Test; `useJUnitPlatform()` lets Gradle discover Jupiter `@Test` methods. Remember to use Java 17+ for Spring Boot 3.5.

## 11. Mock SDK: merely a dependency type to filter

**`src/main/java/com/example/optional/ThirdPartyClient.java`**

```java
package com.example.optional;

import java.util.Objects;

public final class ThirdPartyClient {

    private final String source;

    public ThirdPartyClient(String source) {
        this.source = Objects.requireNonNull(source, "source");
    }

    public String source() {
        return source;
    }

    public String ping() {
        return "pong:" + source;
    }
}
```

This class is **not automatically a Spring bean**. It is just a Java type present on the demo's physical classpath. The bean appears only if configuration is registered and conditions match. Writing `new FilteredClassLoader(ThirdPartyClient.class)` requires the class literal to compile in the test; using the literal in test code **does not defeat the simulation** because the runner uses its own filtered ClassLoader to evaluate conditions.

**In production:** Replace the demo type with a real SDK JAR, e.g., `com.vendor.sdk.Client` in `vendor-sdk.jar`. When creating an optional library integration, ensure the artifact dependency graph does not accidentally force all consumers to pull the SDK jar if they do not use that feature.

## 12. Fallback status: a type always on the classpath

**`src/main/java/com/example/autoconfig/FallbackStatus.java`**

```java
package com.example.autoconfig;

public record FallbackStatus(String reason) {
}
```

`FallbackStatus` is completely independent of `ThirdPartyClient`. When the SDK is absent, we do not want to create a `ThirdPartyClient` bean, yet **may** create a fallback/metadata bean that other code uses to report the feature is unavailable. This illustrates `@ConditionalOnMissingClass`, without implying every starter must create a fallback.

A real application may choose **to create nothing** when the SDK is missing. If a real feature is mandatory and missing the dependency is a deployment error, fail-fast with a clear error — do not create a fake no-op that silently drops business work. Choose behavior per library contract.

## 13. Auto-config for SDK-present branch: safe nested configuration

**`src/main/java/com/example/autoconfig/VendorClientAutoConfiguration.java`**

```java
package com.example.autoconfig;

import com.example.optional.ThirdPartyClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration(proxyBeanMethods = false)
public class VendorClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(ThirdPartyClient.class)
    @ConditionalOnProperty(
            prefix = "demo.vendor",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    static class SdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(ThirdPartyClient.class)
        ThirdPartyClient thirdPartyClient() {
            return new ThirdPartyClient("auto");
        }
    }
}
```

**Mechanism:**

1. `VendorClientAutoConfiguration` holds only the nested configuration, avoiding putting the optional return type on an outer `@Bean` method.
2. `@ConditionalOnClass(ThirdPartyClient.class)` decides whether to process the nested configuration.
3. `@ConditionalOnProperty` separates **"user disabled the feature"** from **"SDK is absent at runtime"**.
4. `@ConditionalOnMissingBean(ThirdPartyClient.class)` ensures custom user beans take precedence.
5. The `@Bean` returning typed `ThirdPartyClient` sits solely inside the condition-guarded class.
6. `proxyBeanMethods=false` fits configurations that do not cross-call bean methods.

**On software packaging:** Auto-config source code **still needs to compile against `ThirdPartyClient`**. In a real multi-module project, declare the dependency as `compileOnly`/optional in the auto-config module and let the starter decide how users opt into the SDK. The demo puts the type in main sources for readability, without claiming the package is truly optional yet.

## 14. Auto-config for SDK-absent branch: using FQCN string

**`src/main/java/com/example/autoconfig/FallbackAutoConfiguration.java`**

```java
package com.example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(proxyBeanMethods = false)
@ConditionalOnMissingClass(
        "com.example.optional.ThirdPartyClient")
public class FallbackAutoConfiguration {

    @Bean
    FallbackStatus fallbackStatus() {
        return new FallbackStatus("optional SDK not available");
    }
}
```

The fallback class **does not import `ThirdPartyClient`**; the condition checks the name as a String. It does not need the SDK class to exist to compile and causes no reflection of an optional return type. When the SDK class is genuinely missing, Spring can still create `FallbackStatus` if the auto-config is registered.

**Easy-to-confuse point:** `@ConditionalOnMissingClass` **does not mean** `@ConditionalOnMissingBean`. In a test where the SDK class is still present yet the user sets `demo.vendor.enabled=false`, the fallback condition **does not match** because the class is still present. Under the demo contract, when the feature is disabled there is neither an SDK client bean nor a fallback bean. If business logic wants "disabled = fallback", use a different condition rather than pretending that equals classpath absence.

## 15. Registering auto-configurations in Boot 3.5

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

```text
com.example.autoconfig.VendorClientAutoConfiguration
com.example.autoconfig.FallbackAutoConfiguration
```

In **Spring Boot 3.x**, library auto-configurations are discovered from `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Each line is a fully qualified class name, optionally with `#` comments. Do not rely on Spring component scanning accidentally picking up an auto-configuration class from an application package.

**Why do tests still pass `AutoConfigurations.of(...)` explicitly?** `ApplicationContextRunner` in the demo intentionally specifies the auto-configurations under test to keep the context narrow; it **does not prove imports metadata gets scanned properly when a consumer uses the starter**. Checking that the file is named/formatted accurately and that auto-configs appear in a real consumer app must be verified separately (section 27).

If the library renames an auto-config class, review Boot's replacement metadata mechanism and backward compatibility for `before/after/exclude`; do not rename entries in the imports file without considering existing users.

## 16. JUnit tests: reusable harness for every scenario

**`src/test/java/com/example/autoconfig/VendorClientAutoConfigurationTest.java`**

```java
package com.example.autoconfig;

import com.example.optional.ThirdPartyClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

class VendorClientAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            VendorClientAutoConfiguration.class,
                            FallbackAutoConfiguration.class));

    @Test
    void sdkAvailableCreatesDefaultClient() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(
                    ThirdPartyClient.class);
            assertThat(context.getBean(
                    ThirdPartyClient.class).source())
                    .isEqualTo("auto");
            assertThat(context).doesNotHaveBean(
                    FallbackStatus.class);
        });
    }

    @Test
    void sdkClassHiddenSkipsClientAndCreatesFallback() {
        runner.withClassLoader(
                new FilteredClassLoader(ThirdPartyClient.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(
                            "thirdPartyClient");
                    assertThat(context).hasSingleBean(
                            FallbackStatus.class);
                    assertThat(context.getBean(
                            FallbackStatus.class).reason())
                            .isEqualTo(
                                    "optional SDK not available");
                });
    }

    @Test
    void sdkPackageHiddenBehavesLikeMissingLibrary() {
        runner.withClassLoader(
                new FilteredClassLoader("com.example.optional"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(
                            "thirdPartyClient");
                    assertThat(context).hasSingleBean(
                            FallbackStatus.class);
                });
    }

    @Test
    void customUserBeanWinsOverAutoConfiguredClient() {
        runner.withBean(
                ThirdPartyClient.class,
                () -> new ThirdPartyClient("custom"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            ThirdPartyClient.class);
                    assertThat(context.getBean(
                            ThirdPartyClient.class).source())
                            .isEqualTo("custom");
                    assertThat(context).doesNotHaveBean(
                            FallbackStatus.class);
                });
    }

    @Test
    void propertyDisabledDoesNotMeanClassAbsent() {
        runner.withPropertyValues(
                "demo.vendor.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(
                            ThirdPartyClient.class);
                    assertThat(context).doesNotHaveBean(
                            FallbackStatus.class);
                });
    }

    @Test
    void filteredLoaderRejectsClassNameDirectly()
            throws Exception {

        try (FilteredClassLoader loader =
                new FilteredClassLoader(
                        ThirdPartyClient.class)) {
            assertThrows(ClassNotFoundException.class,
                    () -> loader.loadClass(
                            ThirdPartyClient.class.getName()));
        }
    }
}
```

**This is a complete JUnit file with six `@Test` methods**, not pseudocode. Package names, imports, class names, and files stay consistent. Each `runner.run(...)` creates a context and closes it after the callback; the tests use no Docker/network/JPA or `@SpringBootTest`.

### 16.1. Test 1 — dependency present

`sdkAvailableCreatesDefaultClient` proves:

- Context does not fail.
- Exactly one `ThirdPartyClient` bean.
- Default bean has `source="auto"`.
- No `FallbackStatus`.

If a test only asserts context startup without asserting bean behavior, an accidentally deleted condition can keep the test green even though auto-config did nothing.

### 16.2. Test 2 — dependency class hidden

`sdkClassHiddenSkipsClientAndCreatesFallback` is the core lesson:

- `withClassLoader(new FilteredClassLoader(ThirdPartyClient.class))` alters class visibility for the context.
- `@ConditionalOnClass` on the nested config does not match.
- `thirdPartyClient` bean is not created.
- `@ConditionalOnMissingClass` on the fallback matches.
- `FallbackStatus` is created with the right reason.
- Context does not crash in **this simulation**.

**Using a bean-name assertion** `"thirdPartyClient"` is clear when the bean type belongs to a hidden optional dependency; there is no need to force the context to resolve the optional type itself via a class literal from the test's parent ClassLoader.

### 16.3. Test 3 — hiding the entire package

`sdkPackageHiddenBehavesLikeMissingLibrary` simulates a broader scope than a single type. Useful when an SDK has factory classes, annotations, and converters referenced by multiple conditions. However, package filtering still does not promise to erase the physical bytecode of every class/JAR from the JVM.

### 16.4. Test 4 — user bean override/back-off

`customUserBeanWinsOverAutoConfiguredClient` registers a bean before auto-configuration has a chance to register its default. This tests **`@ConditionalOnMissingBean`**, without `FilteredClassLoader`. The result must have one bean with source `custom`, without creating an extra `auto`.

### 16.5. Test 5 — property disabled

`propertyDisabledDoesNotMeanClassAbsent` simulates disabling the feature. The SDK remains visible, so the fallback is **not** triggered by the classpath condition. This is a good signal to catch confusing `@ConditionalOnProperty` with `@ConditionalOnMissingClass`.

### 16.6. Test 6 — directly testing the loader

`filteredLoaderRejectsClassNameDirectly` verifies the classloader itself filters as expected. It **does not** prove every class is defined by that loader in the JVM; test 2 is what shows Spring conditions actually use visibility from the runner and take the desired branch.

## 17. Expected results and how to run

The project structure runs with Gradle 8.x compatible with Spring Boot 3.5, JDK 17+, and BOM dependencies:

```bash
./gradlew test --tests com.example.autoconfig.VendorClientAutoConfigurationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.autoconfig.VendorClientAutoConfigurationTest
```

If the project lacks a Gradle wrapper, generate the wrapper per team convention first; `build.gradle` and `settings.gradle` above do not generate `gradlew` themselves.

**Six test methods** are expected to PASS:

| Test | Class visible? | Auto SDK bean? | Fallback bean? |
|---|---|---|---|
| `sdkAvailableCreatesDefaultClient` | Yes | Yes, 1 bean | No |
| `sdkClassHiddenSkipsClientAndCreatesFallback` | Exact class hidden | No | Yes |
| `sdkPackageHiddenBehavesLikeMissingLibrary` | Package hidden | No | Yes |
| `customUserBeanWinsOverAutoConfiguredClient` | Yes | User bean, auto backs off | No |
| `propertyDisabledDoesNotMeanClassAbsent` | Yes, but property false | No | No |
| `filteredLoaderRejectsClassNameDirectly` | FilteredLoader directly | No context created | No context created |

There is no fixed business stdout. With Gradle/JUnit ready, the expected outcome is `BUILD SUCCESSFUL`, with reports at `build/reports/tests/test/index.html`. **This assessment is based on Spring Boot 3.5 APIs and code review; I do not claim to have executed Gradle/JUnit on the learner's repository.**

## 18. Reading results via ConditionEvaluationReport

A test asserting no bean is good, yet when you do not know **why** a bean was skipped, use `ConditionEvaluationReport`. Spring Boot provides an initializer:

```java
// Snippet that can be added to a test when debugging.
import org.springframework.boot.autoconfigure.logging
        .ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

ApplicationContextRunner debugRunner =
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO))
                .withConfiguration(AutoConfigurations.of(
                        VendorClientAutoConfiguration.class,
                        FallbackAutoConfiguration.class));

debugRunner.withClassLoader(
        new FilteredClassLoader(ThirdPartyClient.class))
        .run(context -> assertThat(context).hasNotFailed());
```

**Syntax warning:** The two `import` lines above are line-wrapped for display; Java does not allow splitting between package and class name with a newline lacking a properly positioned dot. When using the snippet, replace them with one import per line:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
```

`ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)` exists in Spring Boot 3.5; it logs the report at INFO level. Usually enable it only when debugging since reports can be long. Read the positive/negative matches for `OnClassCondition`, `OnBeanCondition`, and `OnPropertyCondition`. Do not assert verbatim report text in unit tests because phrasing/logging can change across versions; prefer bean assertions, treating the report as investigative data.

### 18.1. A condition can fail to match for many reasons

A bean can fail to appear because:

- `@ConditionalOnClass` did not match.
- `@ConditionalOnProperty` is false.
- A user bean caused `@ConditionalOnMissingBean` to back off.
- Parent context/bean search strategy differs.
- Auto-configuration was not imported.
- Web/reactive context type does not fit.
- Bean definition was excluded or not scanned.

**Do not guess the reason solely from "bean missing".** To pinpoint a cause, test an isolated scenario and inspect the condition report.

## 19. Why not use `@SpringBootTest` for every branch?

`@SpringBootTest` loads a full application context with component scanning, data sources, HTTP clients, security, and other beans. When checking an optional class condition, a full context typically:

- Runs much slower.
- May touch network/DB or trigger startup side effects.
- Easily has bean conditions skewed by another test configuration.
- Cannot conveniently swap classloaders per test method.
- Ties tests to the application startup path rather than the auto-configuration contract alone.

`ApplicationContextRunner` is built for this exact job: **each scenario creates a small controlled context**. Yet do not absolutize it: you still need at least one consumer integration test with `AutoConfiguration.imports`, real dependencies, and scanning to protect packaging.

## 20. Non-web, servlet, and reactive context runners

`ApplicationContextRunner` creates a **non-web** context. If auto-configuration has:

```java
@ConditionalOnWebApplication(type = Type.SERVLET)
```

then a non-web test may not trigger it even though all SDK classes are present. Use the matching runner:

- `ApplicationContextRunner`: core/non-web auto-config.
- `WebApplicationContextRunner`: servlet web context conditions.
- `ReactiveWebApplicationContextRunner`: reactive web context conditions.

Example snippet:

```java
WebApplicationContextRunner servletRunner =
        new WebApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        MyServletAutoConfiguration.class))
                .withClassLoader(
                        new FilteredClassLoader(
                                OptionalServletAdapter.class));
```

The snippet requires imports and hypothetical classes; it is not a file in the runnable project. Likewise, WebFlux/reactive auto-configs must use the reactive runner and matching dependencies. Do not use `@SpringBootTest(webEnvironment=...)` merely to trick a condition class into thinking it runs in a servlet context — the runner already has dedicated variants.

## 21. Class filter vs package filter: choosing the right level

**Hiding a single class** works well when auto-config checks only a single "marker" type:

```java
new FilteredClassLoader(ThirdPartyClient.class)
```

**Hiding a package** works well when a dependency has many public API types and annotations:

```java
new FilteredClassLoader("com.example.optional")
```

However, an SDK can span multiple packages: `com.vendor.api`, `com.vendor.internal`, `org.reactivestreams`. Hiding one package does not necessarily catch every related condition. When you need to simulate lacking a **real artifact**, a runtime dependency test with the JAR removed is more trustworthy.

**Optimizing test coverage across the matrix:**

| Variant | Risk | Priority |
|---|---|---|
| Hide main marker class | Auto-config creates bean wrongly | Mandatory |
| Hide whole SDK package | Code still loads secondary classes | Recommended for broad SDKs |
| Hide one optional SPI resource | Wrong condition/service loader | When SPI is used |
| Hide transitive optional module class | Indirect conditions | Per dependency graph |
| Real absent JAR in consumer runtime | Linkage/packaging errors | Required for public starters |
| Mismatch SDK versions | Binary incompatibility | When supporting multiple versions |

## 22. `@ConditionalOnBean` and `@ConditionalOnMissingBean` under test filters

There is a subtle ordering point:

- Bean conditions evaluate the **`BeanFactory` at the moment auto-configuration is processed**.
- User-defined beans are expected to be registered before auto-config.
- If two auto-configs both create beans of the same type, ordering and `@AutoConfigureAfter/Before` can affect outcomes.
- `@ConditionalOnMissingBean` is not a global "nowhere in the JVM is there a bean"; it inspects the `BeanFactory`/context hierarchy and search strategy.
- A mock bean added in a test can make a condition match differently than in production.

Therefore, tests using `withBean(ThirdPartyClient.class, ...)` should run **on a normal runner**, rather than filtering `ThirdPartyClient` out of the context and simultaneously trying to inject a bean of that same type. If the goal is an absent SDK, test no-bean/fallback; if the goal is custom user override, test class present.

When testing BeanFactory hierarchies, use `withParent(...)` or a concrete context structure and state the `SearchStrategy`. Do not turn an absence test into a hierarchy test unless your auto-config genuinely depends on it.

## 23. `@ConditionalOnMissingClass` vs `@ConditionalOnMissingBean`

Two similarly named annotations for different situations:

```text
Is dependency on the classpath?
    |
    +-- No:
    |      @ConditionalOnMissingClass => true
    |      @ConditionalOnMissingBean   => depends on BeanFactory, says nothing about dependency
    |
    +-- Yes:
           @ConditionalOnMissingClass => false
           Does bean exist?
               +-- No  => @ConditionalOnMissingBean true
               +-- Yes => @ConditionalOnMissingBean false
```

For a fallback only when the SDK is missing, use `@ConditionalOnMissingClass`. For a default SDK client that respects user-configured beans, use `@ConditionalOnMissingBean` inside the SDK-present branch.

If the product needs a fallback even when the SDK exists yet is disabled, design clear multi-branch conditions with property-false tests. Never "fake classpath absent" to test a property branch.

## 24. Fundamental limitation: parent ClassLoader and JVM linkage

**Point never to overstate:** `FilteredClassLoader` **does not remove JARs** from Gradle/Maven `testRuntimeClasspath`. It blocks loading **through the filtered loader**; many auto-config classes may still be **defined by the parent application ClassLoader**. When the JVM reflects a class defined in the parent, it can resolve optional types using the parent loader, which still sees the SDK.

Consequence: A test using `FilteredClassLoader` can PASS `hasNotFailed()` even though **a real JVM lacking the SDK** would fail when reflecting a `@Bean` method with an optional return type. This is a real limitation discussed in Spring Boot issue #51377 (2026) regarding classloader simulation. Therefore:

1. Continue using `FilteredClassLoader` for **`OnClassCondition` and `OnMissingClassCondition` branch tests**.
2. Place optional return types inside **nested configurations with class-level guards**, per official docs.
3. Do not treat filter tests as 100% proof against linkage/`NoClassDefFoundError`.
4. For important starters, run at least one **consumer app/JVM** whose `runtimeClasspath` **excludes the optional dependency** and verify startup.
5. For `ServiceLoader` and resource scanning, verify which loader the real library uses; different ClassLoaders can see different resources.

### 24.1. A "passing" test does not mean the SDK disappeared

```java
// Snippet: the SDK class is still on the test's bytecode classpath.
ThirdPartyClient compiledType =
        new ThirdPartyClient("test");
```

This line can run fine inside a JUnit test class loaded from the parent classloader, even while an **isolated context** is built with `FilteredClassLoader(ThirdPartyClient.class)`. That is not a bug in `FilteredClassLoader`; it reflects two environments seeing classes differently. Do not use reflection on the test classpath to "prove" context conditions evaluated wrongly.

## 25. Limitation: hiding a class does not change runtime API versions

An auto-config might call a method available only in SDK v2:

```java
// Conceptual anti-example:
client.newMethodOnlyInV2();
```

`FilteredClassLoader` checks only **whether a type is visible**. It does not swap SDK v2 bytecode for v1, nor verify every constructor/method signature difference. Thus an SDK v1 still has `ThirdPartyClient` while lacking the v2 method; the condition can match and then runtime throws `NoSuchMethodError`.

To protect against this:

- Publish the supported SDK version range.
- Use Gradle dependency constraints/BOM and version alignment.
- Test consumer apps against **each supported version**.
- Verify binary compatibility with compile/runtime tests.
- Include startup tests with **SDK absent**, **SDK present-min**, and **SDK present-max**.
- For native/AOT, run dedicated tests for reflection/proxies/hints.

If production deployments use Gradle dependency locking, verify the exact `runtimeClasspath` from the lockfile, not only `compileClasspath`.

## 26. Making an optional dependency truly optional in a multi-module project

When implementing a real starter, the structure often looks like:

```text
acme-project/
  vendor-api/                   <- Third-party API or external dependency
  acme-autoconfigure/           <- @AutoConfiguration, optional integration
  acme-starter/                 <- default dependencies per product
  consumer-with-sdk/            <- app running with vendor SDK
  consumer-without-sdk/         <- app running without vendor SDK
```

**Conceptual Gradle configuration** example for the auto-config module:

```groovy
// Snippet belonging to :acme-autoconfigure/build.gradle, not standalone:
dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    compileOnly 'com.vendor:vendor-sdk:1.2.3'
    testImplementation 'com.vendor:vendor-sdk:1.2.3'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

`compileOnly` lets source code compile against optional types without publishing them as mandatory runtime dependencies. `testImplementation` ensures unit tests still have the class and can apply `FilteredClassLoader`. With Maven, you can use `<optional>true</optional>` on the dependency in the autoconfigure module alongside a consumer testing strategy.

**However**, do not mistake `compileOnly` for making all runtime paths safe: if `@Bean` signatures/static initializers still reference the SDK before conditions evaluate, an app lacking the SDK can still crash. Always verify with real packaging tests.

### 26.1. A starter may intentionally pull the SDK in

If `acme-starter` represents the "just add starter, SDK ready" experience, it may pull the SDK at runtime. `acme-autoconfigure` alone must still be safe when the SDK is absent. Structure your test matrix around **the artifact real users install**, not only the module holding auto-config sources.

## 27. Consumer test when the SDK is genuinely not installed

Goals of a **runtime absent-dependency test**:

- Fork a JVM or run tests in a separate consumer module.
- Dependencies include `acme-autoconfigure` and required Spring Boot runtime.
- **No** `vendor-sdk` on `runtimeClasspath`.
- Actual Boot startup/auto-configuration import executes.
- Assert the application **starts**, does not register vendor-specific beans, and fallback/absence behavior is right.

The "absent" condition must be verified against the dependency graph before running:

```bash
./gradlew :consumer-without-sdk:dependencies --configuration runtimeClasspath
./gradlew :consumer-without-sdk:dependencyInsight --dependency vendor-sdk --configuration runtimeClasspath
```

The second command reporting **no matching dependency** can be expected. Still, checking `dependencyInsight` alone is not enough if a jar was placed manually on the classpath or shaded into another dependency. In a real consumer, you can use `Class.forName("com.vendor.sdk.VendorClient")` inside the forked JVM itself to verify the class is absent.

**Never place the real SDK in `testImplementation` of `consumer-without-sdk`** if tests run in the same process with the test runtime classpath — otherwise you accidentally bring the class back. When asserting without the API type, use **class name strings** and bean names instead of importing optional SDK types in the consumer test.

### 27.1. How to test startup?

One option: create a minimal Spring Boot consumer application depending on `acme-autoconfigure`, use `@SpringBootTest` or invoke `SpringApplication.run` in a forked JVM; **ensure the app does not pull the SDK through test dependencies**. Check startup, condition report, and bean names. This is a **separate integration test**, outside the runnable single-module demo in sections 9–17.

## 28. Pitfall of `AutoConfiguration.imports` being masked by the test runner

In the runnable demo, tests use:

```java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                VendorClientAutoConfiguration.class,
                FallbackAutoConfiguration.class));
```

This **registers auto-configurations explicitly**. If `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` is misnamed, tests can still PASS because the runner does not rely on the imports file in this example.

**Solution:** Besides classloader branch tests, add a test/consumer module verifying **auto-registration** from the published JAR:

- The JAR contains the exact imports file.
- Every FQCN in the file still exists after refactors.
- A real Spring Boot app sees the auto-config candidates.
- When the SDK is present, auto-config creates the bean (subject to custom overrides/properties).
- When the SDK is absent, the app still starts per contract.
- No component-scan workaround accidentally hides broken auto-imports.

A focused `ApplicationContextRunner` test answers "are these conditions right?"; a consumer test answers "is the library packaged/imported properly?". Both are necessary when releasing a starter to multiple teams.

## 29. Resource filters and `@ConditionalOnResource`

Example of an auto-config active only when a file is present:

```java
// Snippet:
@AutoConfiguration
@ConditionalOnResource(
        resources = "classpath:features/optional-adapter.flag")
class FeatureResourceAutoConfiguration {

    @Bean
    FeatureMarker featureMarker() {
        return new FeatureMarker();
    }
}
```

To simulate an absent resource:

```java
runner.withClassLoader(new FilteredClassLoader(
        new ClassPathResource(
                "features/optional-adapter.flag")))
    .run(context ->
        assertThat(context).doesNotHaveBean("featureMarker"));
```

These are snippets, **not part of the runnable project**; add the resource, bean type, and imports if implementing. Note that `ClassPathResource` uses a classpath path, not an arbitrary file on disk. If real code reads files via an absolute `Path` or HTTP, `FilteredClassLoader` does not intervene. If code fetches resources directly through a parent ClassLoader, the runner's filter may be bypassed. Tests must hit the same lookup boundary that production code uses.

## 30. Do not use `@MockitoBean` to "remove a dependency from the classpath"

A test declaring:

```java
@MockitoBean
ThirdPartyClient client;
```

does not remove `ThirdPartyClient` from the classpath. On the contrary:

- Mockito must see the class in order to mock the type.
- The mock bean can make `@ConditionalOnBean(ThirdPartyClient.class)` match.
- The mock bean can make `@ConditionalOnMissingBean(ThirdPartyClient.class)` **not match**.
- Auto-config may back off simply because the test added a bean.
- The test passes without ever testing the missing-SDK branch.

To test **missing bean** while the class is present, build a runner without the bean or test conditional bean logic. To test **missing class**, use `FilteredClassLoader`. To test **missing JAR**, use a runtime packaging test.

## 31. Do not use `excludeAutoConfiguration` as proof of a missing class

`@SpringBootTest(excludeAutoConfiguration=...)` or `@ImportAutoConfiguration(exclude=...)` (depending on the annotation supported) can **prevent an auto-configuration from being applied**, yet does not make the SDK dependency disappear from the classpath. A "bean absent" test resulting from excluding the auto-config **does not** prove `@ConditionalOnClass` backed off.

Likewise, setting `@ConditionalOnProperty` to false can suppress the bean while the class remains present. Those conditions must be tested separately by cause to avoid false confidence.

## 32. Avoid passing class name Strings in the wrong place

Some APIs take class names, others take package names:

| API | String argument means |
|---|---|
| `@ConditionalOnClass(name = "...")` | **Fully qualified class name** |
| `@ConditionalOnMissingClass("...")` | **Fully qualified class name** |
| `new FilteredClassLoader("...")` | **Package name(s)** to hide |
| `new FilteredClassLoader(MyClass.class)` | Specific type |
| `new FilteredClassLoader((Predicate<String>) name -> ...)` | Binary class name or resource name per callback |
| `new ClassPathResource("...")` | **Resource path** on the classpath |
| `AutoConfiguration.imports` | One **auto-configuration FQCN** per line |

If you write `new FilteredClassLoader("com.vendor.sdk.VendorClient")` because it looks like `@ConditionalOnMissingClass("com.vendor.sdk.VendorClient")`, you are passing a **package filter string** rather than targeting a single class per API intent. Use `new FilteredClassLoader(VendorClient.class)` when the class can be referenced, or a predicate matching the exact binary name.

## 33. Debugging "bean still appears even though class was filtered"

Possibilities:

1. The condition was **not** applied: the auto-config class lacks `@ConditionalOnClass` in the right place.
2. The filter targeted the wrong package/FQCN/classloader.
3. The bean came from **user configuration** or another auto-config.
4. The condition used **a different marker class** that is still present.
5. The filter ran on this runner, yet the test checked a different context.
6. A parent ClassLoader still loaded/defined an auto-config class holding an optional reference.
7. The SDK appeared via another transitive/shaded dependency or child classloader.
8. The test accidentally added a mock/user bean before the run.
9. The app context was cached from another configuration (with `@SpringBootTest`).
10. Code used reflection/`ServiceLoader` bypassing the intended context classloader.

**How to debug:** Assert bean names and types, inspect `ConditionEvaluationReport`, verify the right test runner classloader, inspect the dependency graph, and add a **real absent-JAR** scenario if JVM linkage is suspected. Never just "add `@DirtiesContext`" since it does not alter the classpath.

## 34. Debugging "context crashes when SDK is hidden"

Common causes:

| Symptom | Possibility | Resolution |
| --- | --- | --- |
| `NoClassDefFoundError` when Spring reflects auto-config | Optional type in return/parameter of outer `@Bean` method | Extract nested config and place class-level `@ConditionalOnClass` |
| `ClassNotFoundException` calling `Class.forName` | Code loads class itself without guarding | Use conditions and avoid eager static loads |
| `BeanCreationException` | Optional bean still invoked | Check conditions, `@Import`, bean overrides |
| `NoSuchMethodError` | Incompatible SDK version | Binary compatibility/real runtime tests |
| Report lacks auto-config | Imports registration error | Test real consumer imports |
| Condition unexpectedly positive | Filter targeted wrong class or condition uses another type | Javadoc, source, report |
| Fallback not created | Property/other condition, config not imported | Check condition report and bean names |
| Context fails due to another library | Filtered package too broad | Filter only the SDK, narrow scope |
| Spring web condition does not match | Used non-web runner | Appropriate Web/Reactive runner |
| Native tests fail with runner | AOT limitations | Dedicated native tests |

**Never swallow a startup failure** and merely assert no bean; a dead context is not a successful "optional dependency skipped". Always use `assertThat(context).hasNotFailed()` on branches expected to start.

### 34.1. Mistake causing a falsely green test

If a test only writes:

```java
runner.withClassLoader(new FilteredClassLoader(
        ThirdPartyClient.class))
    .run(context -> assertThat(context)
            .doesNotHaveBean("someUnrelatedBean"));
```

then even if the optional client is created erroneously, the test still passes because it asserted an unrelated bean. Tests must assert **the exact conditioned bean** and optionally the fallback behavior.

## 35. Minimum test matrix for an optional integration

| Dependency | Property | Custom user bean | Expected SDK bean | Expected fallback | Startup |
|---|---|---|---|---|---|
| Present | default true | No | Auto bean | None | PASS |
| Present | default true | Yes | User bean, auto backs off | None | PASS |
| Present | false | No | None | None per demo | PASS |
| Absent (FilteredClassLoader) | default | No | None | Fallback | PASS |
| Absent (whole package) | default | No | None | Fallback | PASS |
| Absent (real consumer runtime) | default | No | None | Fallback | PASS |
| Present but old binary-incompatible SDK | default | No | Policy-dependent | Policy-dependent | Test compatibility |
| Absent SDK but missing imports metadata | default | No | None | May lack fallback | Test packaging, not just runner |

**At a minimum**, include positive + negative classpath tests + context startup. For a published starter, add consumer tests to guard against differences between simulation and runtime packaging.

## 36. When is FilteredClassLoader not needed?

Not needed when the real problem is:

- A false property -> `withPropertyValues("feature.enabled=false")`.
- User supplies a bean -> `withBean(...)`.
- Missing HTTP response -> mock web server/`RestClientTest`.
- An unreachable runtime service -> Testcontainers/WireMock network tests.
- A test slice excluding beans due to scan/filter -> slice config tests.
- An inactive `@Profile` -> profile property/environment tests.
- An unmapped enum value -> unit test/domain test.
- An optional JAR **genuinely** needing removal -> consumer runtime test.

`FilteredClassLoader` is a **sharp tool for class/resource visibility**, not a catch-all way to simulate every unavailable dependency or auto-config exception.

## 37. Practice exercises

### A. Reading filter results

A test uses `new FilteredClassLoader(ThirdPartyClient.class)`, `@ConditionalOnClass` is false, yet the context has the fallback. Is this a successful skip or a test failure? What else must be asserted?

**Answer:** Successful skip **if** the contract expects a fallback; assert `hasNotFailed()`, client bean absent, and fallback present.

### B. Class or bean?

The SDK JAR is present, yet the user did not declare an SDK bean. What do `@ConditionalOnClass` and `@ConditionalOnMissingBean` return?

**Answer:** Class condition true; missing bean true (in the appropriate context/phase), because the two conditions measure different things.

### C. Property false

The SDK class is still there, yet `demo.vendor.enabled=false`. Is the fallback created automatically by `@ConditionalOnMissingClass`?

**Answer:** No; the class is still present. The demo lesson expects neither auto client nor fallback.

### D. User bean

The application has a custom `ThirdPartyClient("custom")`. May auto-config create an additional default client?

**Answer:** No, thanks to `@ConditionalOnMissingBean`; verify the context has only one bean and source `custom`.

### E. Package filtering

An SDK has classes in `com.vendor.api` and `com.vendor.internal`. Is hiding `com.vendor.api` equivalent to removing the whole JAR?

**Answer:** Not yet; other packages, resources, transitive JARs, and parent loaders may still exist.

### F. Composed annotation

You create `@ConditionalOnVendor` as a meta-annotation over `@ConditionalOnClass(VendorClient.class)`. What does Spring Boot documentation note?

**Answer:** Prefer `name="com.vendor.VendorClient"` on composed conditions, because ASM metadata handles class literals on meta-annotations differently than directly on classes.

### G. Method signature

`@Bean @ConditionalOnClass(VendorClient.class) VendorClient client()` in an outer config hits a JVM linkage error when the SDK is genuinely absent. How do you fix it?

**Answer:** Move the optional bean method into a nested `@Configuration @ConditionalOnClass(VendorClient.class)`.

### H. Loader vs real JAR

`FilteredClassLoader` tests pass, yet a consumer without `vendor-sdk.jar` gets `NoClassDefFoundError`. Did the test "lie"?

**Answer:** It only proved the condition under a simulated context classloader, without guaranteeing class resolution for parent-defined classes. Add a real consumer runtime test and fix config signatures.

### I. Imports metadata

`AutoConfigurations.of(VendorClientAutoConfiguration.class)` passes, yet users installing the starter see no bean. What could be wrong?

**Answer:** `AutoConfiguration.imports` is wrong/missing; explicit context runner imports do not test auto-discovery. Test the published artifact.

### J. Native image

You run an `ApplicationContextRunner` test inside a native image and want to conclude the auto-config is AOT-safe. Is that reliable?

**Answer:** Spring Boot explicitly notes the runner does not work as a native-image test tool; use native-specific builds/tests.

### K. Filtering resources

A condition depends on `classpath:feature.flag`, yet you only filter a Java class. Does that test the missing-resource branch?

**Answer:** No; filter the specific resource via the `ClassPathResource` constructor and test the right lookup boundary.

### L. SDK version changes

SDK v1 and v2 both contain `VendorClient`, yet only v2 has `newFeature()`. Does `@ConditionalOnClass` prevent `NoSuchMethodError` on v1?

**Answer:** No; verify supported versions and run compatibility tests against real JARs.

### M. Test framework present

A test uses `@MockitoBean` to mock `VendorClient` in order to "simulate absent SDK". Why is this wrong?

**Answer:** Mocking a bean requires the class to be present and also alters `@ConditionalOnBean/MissingBean`, without making the class disappear.

### N. Debugging method

The context lacks the default client. Name five causes unrelated to a broken `FilteredClassLoader`.

**Hint:** Property false, user bean, imports not registered, web-type condition unmatched, excluded bean, condition on another class, auto-config ordering.

## 38. Checklist before merging a starter

- [ ] Identified the kind of optionality: class, bean, property, or runtime service.
- [ ] `@ConditionalOnClass` checks the right SDK entrypoint class.
- [ ] `@ConditionalOnMissingClass` uses the exact FQCN per contract.
- [ ] Optional SDK is not accidentally forced as a mandatory runtime dependency.
- [ ] Optional types are referenced only inside safely guarded configurations.
- [ ] Do not put an optional return type on an outer `@Bean` method expecting a method condition to protect it.
- [ ] Composed annotations use `name` when needed to avoid metadata issues.
- [ ] Tested class present with default bean.
- [ ] Tested class absent using `FilteredClassLoader(SomeClass.class)`.
- [ ] Tested package absent if the library spans multiple related types.
- [ ] Asserted context `hasNotFailed()` in the absence branch.
- [ ] Asserted the optional bean is absent **by exact bean name/type**.
- [ ] Asserted the fallback is created or intentionally omitted per contract.
- [ ] Tested custom user bean making auto-config back off.
- [ ] Tested disabled feature property separately.
- [ ] Did not use `@MockitoBean` to simulate an absent classpath.
- [ ] Did not use `excludeAutoConfiguration` in place of a class condition test.
- [ ] Used `ApplicationContextRunner` when targeting non-web auto-config.
- [ ] Used the appropriate Web/Reactive runner when web-type conditions exist.
- [ ] Aware that `FilteredClassLoader(String...)` takes **package names**, not class names.
- [ ] Did not filter overly broad Spring/JDK packages in tests.
- [ ] Resource filters used only when code relies on classpath resources.
- [ ] Condition report can be enabled to debug match/mismatch.
- [ ] `AutoConfiguration.imports` has exact FQCNs and is packaged in the JAR.
- [ ] Added a consumer startup test with the SDK **genuinely absent** for public starters/critical integrations.
- [ ] Added SDK version compatibility tests if APIs change across versions.
- [ ] Added dedicated AOT/native tests if the product supports native images.
- [ ] Did not report simulated classpath tests as proof of "removing the JAR from the JVM".
- [ ] Tests remain readable after Spring Boot version upgrades; import packages do not mix Boot 3.x/4.x.
- [ ] QA accurately distinguishes code review from tests actually executed.

**Conclusion:** `FilteredClassLoader` enables systematic testing of **dependency present/absent** branches in Spring Boot auto-configurations without changing Gradle dependencies per test. Combining `ApplicationContextRunner`, `@ConditionalOnClass`, `@ConditionalOnMissingClass`, and bean assertions confirms that the auto bean is created when the SDK is present, skipped when missing, fallback is registered when appropriate, and the context does not crash in simulation. However, **classloader tests are not proof of full runtime linkage**. When releasing starters for real users, always protect optional class signatures with nested configurations and add consumer tests inside a JVM **genuinely lacking the optional JAR**.

### Official and supplementary references

- Spring Boot 3.5.16 — Creating Your Own Auto-configuration, Class Conditions, Testing Auto-configuration, and Overriding the Classpath sections: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 — Javadoc `FilteredClassLoader` and filter constructors/APIs: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.5 — Javadoc `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.5 — Javadoc `AbstractApplicationContextRunner.withClassLoader`/`withBean`/`run`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html
- Spring Boot 3.5 — Javadoc `@ConditionalOnClass`, class-level annotation and `@Bean` method signature caveat: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.5 — `ConditionEvaluationReportLoggingListener` forLogLevel API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html
- Spring Boot — Discussed limitation of FilteredClassLoader and parent-defined classes, issue #51377: https://github.com/spring-projects/spring-boot/issues/51377
- Gradle — Dependency configurations, `compileOnly` vs `implementation`/`testImplementation`: https://docs.gradle.org/current/userguide/java_library_plugin.html