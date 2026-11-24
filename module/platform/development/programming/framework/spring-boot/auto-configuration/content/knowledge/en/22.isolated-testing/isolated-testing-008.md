# FilteredClassLoader to Simulate Missing Classes or Missing Library Packages

## 1. Problem: testing auto-configuration when an optional library is absent

A starter may integrate vendor SDKs, cloud clients, metrics libraries, drivers, or specialized adapters. Consuming applications do not always include those dependencies on their runtime classpath. If an auto-configuration still attempts to resolve SDK types, the application can fail at startup with `NoClassDefFoundError` or `ClassNotFoundException`.

Testing only the case where dependencies are present is not enough. A library must prove that:

- When the SDK is present, the auto-configuration branch needing the SDK applies properly.
- When a specific class is missing, that branch is skipped and the context still starts.
- When an entire SDK package is missing, beans depending on that package do not appear.
- Unrelated auto-configurations or beans continue to function.
- When the user disables the feature via a property, the default bean is not registered even if the SDK is present.

Spring Boot provides `FilteredClassLoader` in its test module to simulate a classpath missing specific classes or packages. Combining it with `ApplicationContextRunner`, you can test each scenario in a small, independent, fast `ApplicationContext`.

This lesson uses Java 17+, Spring Boot 3.3.13, Maven, JUnit 5, and AssertJ. The example simulates an SDK named `CatalogClient`; in real libraries, this type typically comes from an external dependency.

## 2. Reviewing ClassLoader and the runtime classpath

The JVM does not locate classes by scanning every JAR arbitrarily on each use. Class loading happens through a `ClassLoader` chain. A ClassLoader receives a binary name, such as `com.vendor.catalog.CatalogClient`, and locates bytecode according to its mechanism.

In a typical Java application:

- The runtime classpath contains compiled class directories and dependency JARs.
- The Application ClassLoader normally resolves application and library classes.
- Spring may use the context's ClassLoader to inspect classes, read resources, and build certain components.
- If a class cannot be found when code needs it, class loading or linking can fail.

For example, suppose a library has a method:

```java
@Bean
CatalogService catalogService(CatalogClient client) {
    return client::findById;
}
```

If `CatalogClient` comes from an SDK absent from the runtime classpath, the JVM/Spring may need to resolve types in the method signature when introspecting the configuration. Placing `@ConditionalOnClass` directly on this method does not always guard early enough, because the return type and parameters may already need resolution before the method condition is evaluated.

Spring Boot recommends isolating methods that depend on optional classes inside a separate nested `@Configuration` and placing `@ConditionalOnClass` on that nested configuration itself. A complete example appears in section 6.

## 3. What is FilteredClassLoader?

`org.springframework.boot.test.context.FilteredClassLoader` is a test ClassLoader provided by Spring Boot. It acts as a filter: specified classes or resources are treated as unloadable through this classloader.

Important point: `FilteredClassLoader` belongs to **test support**, not production classpath configuration. We use it to create a test environment with a restricted classpath without altering the entire project's dependencies.

Common constructors in Spring Boot 3.3:

| Constructor | Effect |
|---|---|
| `new FilteredClassLoader(SomeSdkClient.class)` | Hides one specific class |
| `new FilteredClassLoader(Foo.class, Bar.class)` | Hides multiple specific classes |
| `new FilteredClassLoader("com.vendor.sdk")` | Hides classes in the specified package |
| `new FilteredClassLoader("com.vendor.sdk", "com.vendor.auth")` | Hides multiple packages |

The API also supports predicates to filter class/resource names and `ClassPathResource` to hide specific resources. For missing optional libraries, the class and package forms are usually clear enough.

### 3.1. Hiding a single class

Use when testing an integration that depends on one specific type:

```java
new FilteredClassLoader(CatalogClient.class)
```

This simulates `CatalogClient` being absent from the classpath used by the context. The class still exists in the test process's own dependency/test runtime; the filter simply makes it unresolvable through the classloader given to the runner.

### 3.2. Hiding an entire package

Use when an integration depends on multiple types within the same SDK:

```java
new FilteredClassLoader("com.vendor.catalog")
```

If the configuration uses `CatalogClient`, `CatalogRequest`, `CatalogResponse`, and other classes in that package, the test can simulate the entire package not being provided.

Filter the narrowest package that sufficiently represents the optional dependency. Filtering an overly broad parent package can accidentally hide application or framework classes that the configuration still needs.

### 3.3. Hiding classes differs from removing dependencies

`FilteredClassLoader` does not edit `pom.xml`, delete JARs from the Maven repository, or change the dependency graph. It only controls how the test context looks up classes/resources via the configured classloader.

Therefore, there are two distinct kinds of verification:

- `FilteredClassLoader`: verifies conditions and how auto-configuration reacts when classes/packages are invisible.
- Dependency analysis or consumer integration tests: verify whether the library accidentally pulls the SDK into a consuming application's runtime.

Do not substitute the result of one check for the other.

## 4. Combining FilteredClassLoader with ApplicationContextRunner

`ApplicationContextRunner` is a Spring Boot utility for creating and running small application contexts in tests. On each `run(...)` call, the runner creates a context for the scenario under test, invokes the callback with that context, and then closes it.

A basic runner:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(CatalogAutoConfiguration.class));
```

`AutoConfigurations.of(...)` explicitly declares which auto-configurations to test. This keeps the test focused on one branch instead of booting the entire application.

To replace the context's classpath:

```java
contextRunner
        .withClassLoader(new FilteredClassLoader(CatalogClient.class))
        .run(context -> {
            // Assertions
        });
```

To simulate a whole package missing:

```java
contextRunner
        .withClassLoader(new FilteredClassLoader("demo.catalog.sdk"))
        .run(context -> {
            // Assertions
        });
```

Common operations in tests:

| API | Meaning |
|---|---|
| `withClassLoader(...)` | Runs the context using the filtered classloader |
| `withPropertyValues(...)` | Adds properties for the scenario |
| `withUserConfiguration(...)` | Supplies application-provided configuration |
| `withConfiguration(AutoConfigurations.of(...))` | Specifies auto-configurations to run |
| `run(context -> ...)` | Creates the context and checks results |
| `hasNotFailed()` | AssertJ check that the context started successfully |
| `doesNotHaveBean(...)` | Confirms a bean was not registered |
| `hasSingleBean(...)` | Confirms exactly one bean of the type exists |

### Why check both hasNotFailed and doesNotHaveBean?

If you only assert the bean does not exist, the test does not clarify whether the context started normally. The context might have failed before the bean was registered.

For a missing optional dependency, both assertions should go together:

```java
assertThat(context).hasNotFailed();
assertThat(context).doesNotHaveBean("catalogClient");
```

The first assertion confirms the application can still create a context. The second confirms the optional branch genuinely did not register the bean.

## 5. Designing auto-configuration safely when classes are missing

Suppose a library has an optional SDK `demo.catalog.sdk.CatalogClient`. The design should separate two parts:

- Outer auto-configuration containing only always-present types.
- Nested static configuration containing all references to `CatalogClient`, guarded by `@ConditionalOnClass`.

Model:

```text
CatalogAutoConfiguration
        |
        +-- does not directly reference CatalogClient
        |
        +-- CatalogSdkConfiguration
                |
                +-- @ConditionalOnClass(CatalogClient)
                +-- @ConditionalOnProperty(acme.catalog.enabled=true)
                |
                +-- CatalogClient bean
```

### 5.1. Why is nested configuration important?

Spring Boot can read configuration class annotation metadata using ASM. With `@ConditionalOnClass` on a configuration class, you can specify classes via `value` or `name`.

Conditions on `@Bean` methods behave differently: before the method condition is applied, the JVM may already need to load classes referenced by the return type/parameters or resolve method references. If an optional class is missing, an error can occur too early.

Therefore, place `@ConditionalOnClass` on a separate configuration class and keep methods referencing optional types inside that class. The outer class should have no constructors, fields, superclasses, or `@Bean` signatures depending on the optional SDK.

Using `name` is a readable choice when you want to express the class name explicitly as a string:

```java
@ConditionalOnClass(name = "demo.catalog.sdk.CatalogClient")
```

For class-level conditions, Spring Boot also supports `value = CatalogClient.class` thanks to annotation metadata reading. If packaging a condition into a custom meta-annotation, the documentation requires using `name` for class conditions.

### 5.2. Combining with a property condition

Classpath conditions and feature flags answer two different questions:

- Does the SDK exist?
- Did the user enable the integration?

Opt-in example:

```java
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

When the property is missing or `false`, the integration is not registered. When the SDK is missing, even setting `enabled=true` cannot make the class appear.

### 5.3. Allowing the application to replace the default bean

If the application can supply its own client, use `@ConditionalOnMissingBean` on the default bean:

```java
@Bean
@ConditionalOnMissingBean
CatalogClient catalogClient() {
    return new CatalogClient();
}
```

This condition applies once the classpath and property branches match. It allows the application to override the default implementation, without replacing the check for whether the SDK is present.

## 6. Complete example with Java 17 and Spring Boot 3.3

The example below places a simulated SDK class in the project's sources. In a real library, that class comes from an external dependency. The tests use `FilteredClassLoader` to simulate a consuming application unable to see the SDK class or package.

### 6.1. Directory structure

```text
filtered-classloader-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/catalog/sdk/
    │   │   └── CatalogClient.java
    │   └── java/demo/catalog/autoconfigure/
    │       └── CatalogAutoConfiguration.java
    └── test/
        └── java/demo/catalog/autoconfigure/
            └── CatalogAutoConfigurationTests.java
```

### 6.2. pom.xml

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
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>filtered-classloader-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-autoconfigure` provides annotations and auto-configuration mechanisms. `spring-boot-starter-test` brings in JUnit, AssertJ, `ApplicationContextRunner`, and `FilteredClassLoader` for tests.

### 6.3. CatalogClient.java

```java
package demo.catalog.sdk;

public class CatalogClient {

    public String findById(String id) {
        return "catalog-item:" + id;
    }
}
```

This class acts as the optional SDK in the example. It has just one method so tests can easily observe output.

### 6.4. CatalogAutoConfiguration.java

```java
package demo.catalog.autoconfigure;

import demo.catalog.sdk.CatalogClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "demo.catalog.sdk.CatalogClient")
    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    public static class CatalogSdkConfiguration {

        @Bean
        @ConditionalOnMissingBean
        CatalogClient catalogClient() {
            return new CatalogClient();
        }
    }
}
```

Key observations:

1. Outer `CatalogAutoConfiguration` has no methods or fields returning/holding `CatalogClient`.
2. Nested `CatalogSdkConfiguration` is the sole place referencing the SDK.
3. `@ConditionalOnClass(name=...)` guards the branch if the SDK class is invisible.
4. `@ConditionalOnProperty` requires the user to enable the feature via `acme.catalog.enabled=true`.
5. `@ConditionalOnMissingBean` lets the application provide its own client.

If the library is packaged as a JAR for Spring Boot auto-discovery, add the following resource:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Contents:

```text
demo.catalog.autoconfigure.CatalogAutoConfiguration
```

The following tests use `AutoConfigurations.of(CatalogAutoConfiguration.class)` to invoke the auto-configuration directly, so the runner does not need to read the imports file. In consumer integration tests, also verify the imports resource inside the packaged JAR.

### 6.5. CatalogAutoConfigurationTests.java

```java
package demo.catalog.autoconfigure;

import demo.catalog.sdk.CatalogClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void clientIsCreatedWhenSdkIsAvailable() {
        contextRunner
                .withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context.getBean(CatalogClient.class)
                            .findById("42"))
                            .isEqualTo("catalog-item:42");
                });
    }

    @Test
    void missingClassDisablesTheOptionalConfiguration() {
        contextRunner
                .withClassLoader(
                        new FilteredClassLoader(CatalogClient.class))
                .withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("catalogClient");
                });
    }

    @Test
    void missingPackageDisablesTheOptionalConfiguration() {
        contextRunner
                .withClassLoader(
                        new FilteredClassLoader("demo.catalog.sdk"))
                .withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("catalogClient");
                });
    }

    @Test
    void disabledPropertyPreventsClientCreation() {
        contextRunner
                .withPropertyValues("acme.catalog.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("catalogClient");
                });
    }

    @Test
    void missingPropertyKeepsOptInFeatureDisabled() {
        contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean("catalogClient");
        });
    }
}
```

### 6.6. Running the tests

From the directory containing `pom.xml`, run with JDK 17+ and Maven:

```bash
mvn test
```

With the exact five tests above, the expected output is:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

This is the expected result of the example, not the log of an executed run. Maven Surefire may also print test names, timings, and plugin information.

### 6.7. Reading each scenario

| Test | Classpath | Property | Outcome |
|---|---|---|---|
| `clientIsCreatedWhenSdkIsAvailable` | SDK present | `true` | One `CatalogClient` exists |
| `missingClassDisablesTheOptionalConfiguration` | Hide `CatalogClient.class` | `true` | Context succeeds, no bean |
| `missingPackageDisablesTheOptionalConfiguration` | Hide package `demo.catalog.sdk` | `true` | Context succeeds, no bean |
| `disabledPropertyPreventsClientCreation` | SDK present | `false` | Context succeeds, no bean |
| `missingPropertyKeepsOptInFeatureDisabled` | SDK present | Missing | Context succeeds, no bean |

The `missingClass...` and `missingPackage...` tests are crucial because they prove the classpath condition is exercised. Setting the property to false alone only proves the feature flag works; it does not prove the library tolerates an absent SDK.

## 7. Advanced filtering patterns

### 7.1. Hiding multiple classes

If an auto-configuration depends on multiple optional types residing in different packages:

```java
new FilteredClassLoader(
        CatalogClient.class,
        CatalogRequest.class,
        CatalogResponse.class)
```

This is helpful when you want to pinpoint the exact classes triggering an integration branch.

### 7.2. Hiding multiple packages

```java
new FilteredClassLoader(
        "com.vendor.catalog",
        "com.vendor.identity")
```

Use when an integration requires both a catalog SDK and an identity SDK. Tests can verify that the branch activates only when all required classes are present.

### 7.3. Filtering by predicate

The API has a constructor taking a predicate. The predicate returns `true` for class or resource names to hide:

```java
new FilteredClassLoader(
        name -> name.startsWith("com.vendor.catalog."))
```

This is more flexible, though an overly broad predicate can accidentally filter resources or classes outside the intended dependency. For standard tests, class/package constructors are easier to read and less surprising.

### 7.4. Hiding classpath resources

`FilteredClassLoader` also supports hiding `ClassPathResource`. This is useful when testing optional resources, such as configuration files or descriptors looked up by the library via `ClassLoader.getResource(...)`.

Do not substitute resource filtering for class filtering. A JAR may contain a resource while missing a class, or contain the class while missing the resource; both cases need separate tests if library logic depends on both.

## 8. Simulating real missing dependencies in multi-module libraries

The example in section 6 puts `CatalogClient` in the source tree so the project runs standalone. When building a real library, the SDK is usually a separate dependency.

A typical Maven configuration for a dependency not propagated automatically to consumers:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>catalog-sdk</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
```

An optional dependency remains present when compiling/testing the library module, but Maven does not propagate it as a transitive dependency to consuming applications. Applications needing the integration add the SDK themselves.

In a real project, you might organize:

```text
catalog-autoconfigure/
├── src/main/java/...
├── src/test/java/...
└── pom.xml

catalog-starter/
└── pom.xml
```

The `catalog-autoconfigure` module holds the code and conditions. The `catalog-starter` module decides which SDKs are included in the default dependency graph. If a starter requires the SDK for the feature to work, the starter declares that dependency; if the SDK should remain optional, let consumers pick the dependency or provide a dedicated starter flavor.

Regardless of module layout, the test classpath should still have the SDK in test runtime so `FilteredClassLoader` can hide those classes/packages per scenario.

### Inspecting the consumer's dependency graph

Use:

```bash
mvn dependency:tree
```

Read the dependency tree of the consuming application, not just the auto-config module. Confirm the optional SDK does not appear unexpectedly in the runtime graph. With Gradle, use `./gradlew dependencies` and inspect the relevant runtime configuration, such as `runtimeClasspath`.

## 9. Distinguishing types of classpath tests

| Check | Approach | Question answered |
|---|---|---|
| SDK present | Run runner unfiltered | Does the integration branch work when dependencies are present? |
| Missing one class | `FilteredClassLoader(SomeClass.class)` | Does auto-config skip the branch depending on that class? |
| Missing a package | `FilteredClassLoader("com.vendor.sdk")` | Does auto-config tolerate the whole SDK package being absent? |
| Missing multiple dependencies | Filter multiple classes/packages | Does the branch handle missing any one of the classpath conditions? |
| Dependency propagation | Maven/Gradle dependency tree | Does the consumer get the SDK pulled into runtime unexpectedly? |
| Packaging and discovery | Build JAR and run consumer test | Are imports, resources, and dependency graph correct in the real artifact? |

A test using `FilteredClassLoader` does not prove the published JAR has correct dependency metadata. Conversely, a dependency tree does not prove auto-configuration handles missing classes cleanly. A high-quality library needs both condition logic tests and artifact/consumer checks.

## 10. Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Test with missing SDK fails with `NoClassDefFoundError` | Optional type is referenced in outer auto-configuration or unisolated method signature | Move SDK-dependent methods into a nested `@Configuration` with `@ConditionalOnClass` |
| Test only asserts the bean does not exist | The context may have failed earlier | Check both `hasNotFailed()` and `doesNotHaveBean(...)` |
| Class filter used, yet another SDK type still loads | Integration branch depends on additional classes | Hide the entire package or add all needed classes to the test |
| Filtering too broad a parent package makes unrelated beans vanish | Filter covers application/framework classes too | Use a narrower package or hide exact classes |
| SDK present, yet bean is not created | Feature property is missing/false or another condition failed | Check properties and Condition Evaluation Report |
| Property is true, yet bean is still absent | SDK was filtered or classpath condition failed to match | Check class/package names in `@ConditionalOnClass` |
| Tests pass, yet consumer app still lacks the SDK | Test runtime has a dependency the consumer lacks, or dependency scope was published wrongly | Inspect consumer's dependency tree and run packaged integration tests |
| Thinking FilteredClassLoader removed the JAR from the project | Confusing test classloader with dependency management | Use Maven/Gradle to inspect the dependency graph |
| Optional SDK loads eagerly during method introspection | `@ConditionalOnClass` placed only on `@Bean` method with optional type in signature | Place the condition on a nested configuration class |
| Test contexts share state | Tests mutate static state or reuse contexts unintentionally | Create fresh runner contexts per scenario, avoid mutable static state |

### Note on classloader limitations

`FilteredClassLoader` simulates class/resource visibility for the test context. It is great for verifying classpath conditions and how Spring Boot selects beans. However, if you need to investigate very specific classloading errors involving classes already loaded by a parent/defining classloader, perform additional checks with a consumer process or real classloader isolation. Do not treat a class-filtering test as absolute proof for every JVM linkage situation.

## 11. Pre-release auto-configuration testing workflow

1. Identify optional dependencies and representative classes for each integration.
2. Isolate all references to optional types inside nested configurations guarded by `@ConditionalOnClass`.
3. Use `ApplicationContextRunner` to invoke the auto-configurations under test.
4. Write a test with the full classpath and confirm the default bean appears.
5. Use `FilteredClassLoader(SomeClass.class)` to test missing a class.
6. Use `FilteredClassLoader("com.vendor.sdk")` to test missing a package.
7. Verify the context does not fail and the optional bean is not registered.
8. Test property off/missing and bean overrides if the library supports those contracts.
9. Inspect the consuming application's dependency graph.
10. Build the JAR, inspect `AutoConfiguration.imports`, and run consumer integration tests to verify the real artifact.

When a test fails, attach `ConditionEvaluationReportLoggingListener` to the runner at INFO/DEBUG level to observe conditions:

```java
.withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(
                LogLevel.INFO))
```

Then look for `OnClassCondition` on the nested configuration. If the condition did not match yet the context still failed, search for another class referencing the optional type outside the guarded branch.

## 12. Self-check questions

**Question 1.** To simulate missing a single class `CatalogClient`, which constructor do you use?

**Answer:** `new FilteredClassLoader(CatalogClient.class)`.

**Question 2.** How do you simulate an entire SDK package being absent?

**Answer:** `new FilteredClassLoader("com.vendor.sdk")`, with the package name to filter.

**Question 3.** Does `FilteredClassLoader` remove dependencies from the Maven runtime graph?

**Answer:** No. It filters class/resource loading through the test context's classloader. Use `mvn dependency:tree` to inspect the dependency graph.

**Question 4.** Why combine `FilteredClassLoader` with `ApplicationContextRunner`?

**Answer:** The runner creates an isolated context and lets you attach a custom classloader for a specific scenario, then assert conditions and beans with AssertJ.

**Question 5.** When an SDK is missing, why should `@ConditionalOnClass` be placed on a nested configuration?

**Answer:** So Spring evaluates the classpath condition on the configuration class before processing method signatures or type references depending on the SDK. Placing the condition on a `@Bean` method with optional return/parameter types can be too late.

**Question 6.** If a test only calls `doesNotHaveBean("catalogClient")`, has it proven the context ran successfully?

**Answer:** No. You must check `hasNotFailed()` to confirm the context started normally.

**Question 7.** Does passing tests with `FilteredClassLoader` prove the consuming application will not have the SDK pulled into its runtime?

**Answer:** No. You must inspect the consumer's dependency tree or runtime classpath separately.

## 13. Takeaways

- `FilteredClassLoader` is a Spring Boot test utility to hide classes, packages, or resources from a context.
- Use `new FilteredClassLoader(SomeClass.class)` to hide a specific class.
- Use `new FilteredClassLoader("com.vendor.sdk")` to hide a package.
- Combine with `ApplicationContextRunner.withClassLoader(...)` to test each scenario in an independent context.
- When optional SDKs are absent, place `@ConditionalOnClass` on a nested configuration and keep optional types inside that branch.
- Always check both that the context did not fail and that the optional bean did not appear.
- `FilteredClassLoader` does not replace inspecting Maven/Gradle dependency graphs or real consumer JARs.

### Official documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Testing and Overriding the Classpath](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3.13 API — FilteredClassLoader](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
