# Verifying Ordering Relationships Across Multiple Auto-Configuration Classes

## 1. Why does auto-configuration order affect the outcome?

A custom starter often has multiple auto-configuration classes. For example:

- The foundation configuration creates a default `FoundationService`.
- The feature configuration creates `FeatureService` if `FoundationService` already exists.
- The audit configuration creates `AuditService` if `FeatureService` has already been registered.

These three classes have a dependency relationship regarding **when bean definitions are processed**. If the consumer is processed before the provider, `@ConditionalOnBean` may not yet see the bean definition that the provider will register later. In that case, the condition does not match and the consumer bean is skipped.

Spring Boot provides metadata to order auto-configurations:

- `@AutoConfiguration(after = ...)` and `afterName`.
- `@AutoConfiguration(before = ...)` and `beforeName`.
- `@AutoConfigureAfter` and `@AutoConfigureBefore`.
- `@AutoConfigureOrder` for general ordering among configurations that do not need to reference each other directly.

What needs to be verified is that **the provider configuration is processed before the consumer configuration**, so the condition sees the right bean definition. Order should not be inferred merely from class names, line order in the imports file, or the order of arguments passed into a test.

## 2. Three types of order to distinguish

### 2.1. Auto-configuration application order

This is the order in which Spring Boot processes auto-configuration classes and registers bean definitions from them.

Example:

```text
FoundationAutoConfiguration
        |
        v
FeatureAutoConfiguration
        |
        v
AuditAutoConfiguration
```

In the diagram, Foundation must be processed before Feature; Feature must be processed before Audit. This is the relationship required when a downstream class's condition checks a bean provided by an upstream class.

### 2.2. Bean instance initialization order

Only after bean definitions are registered does Spring create objects during context refresh and when they are needed.

Object creation order is determined by the bean dependency graph, constructor/factory-method injection, `@DependsOn` relationships, and container lifecycle.

Example:

```java
@Bean
FeatureService featureService(FoundationService foundationService) {
    return new FeatureService(foundationService.name());
}
```

The `FoundationService` parameter creates a dependency between the two beans. Spring must resolve that dependency when creating `FeatureService`. That relationship differs from Spring Boot processing `FoundationAutoConfiguration` before `FeatureAutoConfiguration`.

**Key point:** `@AutoConfiguration(after = ...)` only orders auto-configuration/bean-definition processing. It is not a command ordering object instantiation.

### 2.3. Ordering in collections and callbacks

`@Order`, `Ordered`, or `@Priority` can affect the order of certain bean lists, plugins, interceptors, or callbacks when injected/collected. They are not a substitute for auto-configuration ordering metadata.

To order auto-configurations, use `@AutoConfiguration` metadata or `@AutoConfigureOrder`. To establish dependencies between bean instances, use injection or `@DependsOn` when appropriate.

## 3. Ordering mechanisms in Spring Boot 3.3

### 3.1. `after` and `before` by class

The consumer configuration declares that it should be applied after the provider:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class FeatureAutoConfiguration {
    // Feature @Beans.
}
```

The provider configuration can declare the reverse direction:

```java
@AutoConfiguration(before = FeatureAutoConfiguration.class)
public class FoundationAutoConfiguration {
    // Foundation @Beans.
}
```

Normally only **one side** of the relationship needs to be declared. Avoid declaring both directions or creating circular relationships.

- `after`: the named auto-configurations must be applied before the current class.
- `before`: the current class must be applied before the named auto-configurations.

These attributes accept class references, allowing the compiler to catch class-name errors when the dependency is present.

### 3.2. `afterName` and `beforeName` by class name

When you do not want a compile-time link to an optional auto-configuration, use the fully-qualified name:

```java
@AutoConfiguration(
        afterName = "org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration"
)
public class AcmeJsonFeatureAutoConfiguration {
}
```

Using strings is helpful when the referenced class may be absent in certain dependency setups. There is no need to import that class just to declare ordering.

The name must be exact. For nested classes, the name uses `$` to separate the outer class and nested class.

### 3.3. Dedicated `@AutoConfigureAfter` and `@AutoConfigureBefore` annotations

Spring Boot also has two dedicated annotations:

```java
@AutoConfigureAfter(FoundationAutoConfiguration.class)
@Configuration(proxyBeanMethods = false)
public class FeatureAutoConfiguration {
}
```

```java
@AutoConfigureBefore(FeatureAutoConfiguration.class)
@Configuration(proxyBeanMethods = false)
public class FoundationAutoConfiguration {
}
```

In new code, `@AutoConfiguration(after = ...)` and `@AutoConfiguration(before = ...)` are usually cleaner because `@AutoConfiguration` is already the dedicated auto-configuration annotation and provides the corresponding alias attributes. The two separate annotations remain useful when a configuration uses traditional `@Configuration` style or when reading older code.

### 3.4. `@AutoConfigureOrder` for independent configurations

Sometimes two auto-configurations need a relative order without referencing each other's classes directly. In that case, you can use:

```java
@AutoConfigureOrder(-10)
@AutoConfiguration
public class EarlyDiagnosticsAutoConfiguration {
}

@AutoConfigureOrder(20)
@AutoConfiguration
public class LateDiagnosticsAutoConfiguration {
}
```

`@AutoConfigureOrder` is an auto-configuration-specific variant of the `@Order` mechanism. The default value is `0`; smaller order values have higher sorting priority.

Do not use `@AutoConfigureOrder` to replace a concrete dependency relationship. If Feature strictly must see beans from Foundation, declaring `after = FoundationAutoConfiguration.class` expresses intent more clearly and is more resilient than an arbitrary pair of order numbers.

### 3.5. Quick comparison

| Mechanism | Use when | Expresses a specific dependency relationship? |
| --- | --- | --- |
| `after` / `before` | The related auto-configuration class is known | Yes |
| `afterName` / `beforeName` | Class name is known, but compile-time coupling should be avoided | Yes |
| `@AutoConfigureAfter` / `@AutoConfigureBefore` | Traditional configuration using separate annotations | Yes |
| `@AutoConfigureOrder` | Independent configurations needing a general order | No |
| `@DependsOn` | One bean instance needs another bean initialized first | No; applies only to bean lifecycle |
| `@Order` | Ordering certain collections/callbacks per their contract | No; not auto-configuration metadata |

## 4. Why are `@ConditionalOnBean` and `@ConditionalOnMissingBean` order-sensitive?

Bean conditions are evaluated against the bean definitions that have already been processed at the time the condition runs.

Provider example:

```java
@AutoConfiguration
public class FoundationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationService.class)
    FoundationService foundationService() {
        return new FoundationService("default");
    }
}
```

Consumer:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(FoundationService.class)
    FeatureService featureService(FoundationService foundation) {
        return new FeatureService("uses:" + foundation.name());
    }
}
```

If the provider is processed first:

1. `FoundationAutoConfiguration` is applied.
2. `@ConditionalOnMissingBean` finds no matching user bean, so the default bean definition is registered.
3. `FeatureAutoConfiguration` is applied next.
4. `@ConditionalOnBean` sees `FoundationService` and registers `FeatureService`.

If the consumer were processed before the provider, the condition could evaluate before the foundational bean definition appeared. `FeatureService` would not be registered. When the provider is processed afterward, Spring does not go back and re-evaluate earlier conditions as if performing a new refresh.

That is why Spring Boot recommends using `@ConditionalOnBean` and `@ConditionalOnMissingBean` in auto-configuration, since auto-configurations are processed after user bean definitions. When relationships exist across multiple auto-configurations, declare ordering explicitly.

### Class-level condition vs. method-level condition

Conditions can be placed on the class or on individual `@Bean` methods:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
@ConditionalOnBean(FoundationService.class)
public class FeatureAutoConfiguration {
    // All beans in the class depend on FoundationService.
}
```

Or:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(FoundationService.class)
    FeatureService featureService(FoundationService foundation) {
        return new FeatureService("uses:" + foundation.name());
    }

    @Bean
    FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
```

In the second approach, only `featureService` depends on the condition; `featureMetrics` can still be registered. Choose the smallest scope matching actual dependencies to avoid accidentally excluding unrelated beans as a group.

## 5. Structure of an example verifying three auto-configuration layers

The example below uses Spring Boot 3.3.5 and Java 17+. We build a three-layer chain:

- `FoundationAutoConfiguration` creates the foundational bean.
- `FeatureAutoConfiguration` uses the foundational bean and creates the feature.
- `AuditAutoConfiguration` uses the feature and creates the audit component.

We intentionally pass the classes into `AutoConfigurations.of` in reverse order in the test. If metadata is right, the test still observes all three beans.

### 5.1. Project structure

```text
auto-configuration-order-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/api/
    │   │   ├── FoundationService.java
    │   │   ├── FeatureService.java
    │   │   └── AuditService.java
    │   ├── java/demo/autoconfigure/
    │   │   ├── FoundationAutoConfiguration.java
    │   │   ├── FeatureAutoConfiguration.java
    │   │   └── AuditAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/autoconfigure/
        └── AutoConfigurationOrderingTests.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>auto-configuration-order-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

`spring-boot-autoconfigure` provides the annotations and conditions. `spring-boot-starter-test` is used in test scope for JUnit, AssertJ, `ApplicationContextRunner`, and `AutoConfigurations`.

### 5.3. Three API types

**`src/main/java/demo/api/FoundationService.java`**

```java
package demo.api;

public record FoundationService(String name) {
}
```

**`src/main/java/demo/api/FeatureService.java`**

```java
package demo.api;

public record FeatureService(String description) {
}
```

**`src/main/java/demo/api/AuditService.java`**

```java
package demo.api;

public record AuditService(String description) {
}
```

The records hold data so tests can clearly verify which bean was used.

### 5.4. Provider: `FoundationAutoConfiguration.java`

**`src/main/java/demo/autoconfigure/FoundationAutoConfiguration.java`**

```java
package demo.autoconfigure;

import demo.api.FoundationService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FoundationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationService.class)
    public FoundationService foundationService() {
        return new FoundationService("default");
    }
}
```

The provider creates a default if the application has not supplied `FoundationService`. If the user already declared a bean of the same type, the auto-configuration yields.

### 5.5. First consumer: `FeatureAutoConfiguration.java`

**`src/main/java/demo/autoconfigure/FeatureAutoConfiguration.java`**

```java
package demo.autoconfigure;

import demo.api.FeatureService;
import demo.api.FoundationService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(FoundationService.class)
    public FeatureService featureService(
            FoundationService foundationService) {

        return new FeatureService(
                "uses:" + foundationService.name());
    }
}
```

`after` ensures the provider is processed before the feature's condition is evaluated. The `FoundationService` parameter also creates a dependency between the two bean instances when Spring instantiates `FeatureService`.

### 5.6. Second consumer: `AuditAutoConfiguration.java`

**`src/main/java/demo/autoconfigure/AuditAutoConfiguration.java`**

```java
package demo.autoconfigure;

import demo.api.AuditService;
import demo.api.FeatureService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = FeatureAutoConfiguration.class)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnBean(FeatureService.class)
    public AuditService auditService(FeatureService featureService) {
        return new AuditService(
                "audit:" + featureService.description());
    }
}
```

Audit needs Feature, so it declares `after = FeatureAutoConfiguration.class`. We obtain the dependency chain:

```text
FoundationAutoConfiguration
          |
          | after
          v
FeatureAutoConfiguration
          |
          | after
          v
AuditAutoConfiguration
```

The arrow means the configuration above must be processed before the configuration below.

### 5.7. Registering auto-configuration candidates

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
demo.autoconfigure.AuditAutoConfiguration
demo.autoconfigure.FeatureAutoConfiguration
demo.autoconfigure.FoundationAutoConfiguration
```

The file intentionally lists them in reverse order to emphasize that line order in imports is not a dependency contract. Spring Boot sorts candidates according to `before`/`after` metadata before applying them.

Auto-configurations should reside in their own package and be registered via the imports file; do not use application component scanning to discover auto-configuration classes.

## 6. Verifying with `ApplicationContextRunner`

### 6.1. Test with reversed input order

Create **`src/test/java/demo/autoconfigure/AutoConfigurationOrderingTests.java`**:

```java
package demo.autoconfigure;

import demo.api.AuditService;
import demo.api.FeatureService;
import demo.api.FoundationService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderingTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            AuditAutoConfiguration.class,
                            FeatureAutoConfiguration.class,
                            FoundationAutoConfiguration.class));

    @Test
    void metadataOrdersThreeConfigurationsEvenWhenInputIsReversed() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();

            assertThat(context).hasSingleBean(FoundationService.class);
            assertThat(context).hasSingleBean(FeatureService.class);
            assertThat(context).hasSingleBean(AuditService.class);

            assertThat(context.getBean(FoundationService.class).name())
                    .isEqualTo("default");

            assertThat(context.getBean(FeatureService.class).description())
                    .isEqualTo("uses:default");

            assertThat(context.getBean(AuditService.class).description())
                    .isEqualTo("audit:uses:default");
        });
    }

    @Test
    void downstreamConfigurationsAreSkippedWhenProviderIsAbsent() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        AuditAutoConfiguration.class,
                        FeatureAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(FoundationService.class);
                    assertThat(context).doesNotHaveBean(FeatureService.class);
                    assertThat(context).doesNotHaveBean(AuditService.class);
                });
    }

    @Test
    void userDefinedFoundationBeanIsVisibleToBothConsumers() {
        this.runner
                .withUserConfiguration(UserFoundationConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(FoundationService.class);
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context).hasSingleBean(AuditService.class);

                    assertThat(context.getBean(FoundationService.class).name())
                            .isEqualTo("custom");

                    assertThat(context.getBean(FeatureService.class).description())
                            .isEqualTo("uses:custom");

                    assertThat(context.getBean(AuditService.class).description())
                            .isEqualTo("audit:uses:custom");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFoundationConfiguration {

        @Bean
        FoundationService customFoundationService() {
            return new FoundationService("custom");
        }
    }
}
```

### 6.2. Meaning of each test

**Test 1 — metadata establishes the right order**

The classes are passed in the order `Audit`, `Feature`, `Foundation`. Thanks to metadata, the provider is processed before both consumers. All three beans appear and each bean's value proves dependencies are wired properly.

**Test 2 — missing provider**

Only the two consumers are loaded. Without `FoundationService`, `FeatureService` is not registered; without `FeatureService`, `AuditService` is not registered either. The context still starts successfully because both consumers are guarded by `@ConditionalOnBean`.

**Test 3 — user bean replaces default provider**

The application provides `FoundationService("custom")`. `@ConditionalOnMissingBean` causes the default provider to yield. Both Feature and Audit are still created, using the custom value. This test confirms auto-configuration runs after user configuration and back-off works properly.

### 6.3. Running the tests

From the `auto-configuration-order-demo` directory:

```bash
mvn -q test
```

If the tests pass, the verified contracts include:

- Ordering metadata works even when input order is reversed.
- Consumers are not registered when the provider is absent.
- User-provided beans are visible and replace defaults.
- The three-layer dependency chain is preserved from Foundation to Audit.

`ApplicationContextRunner` creates small contexts suited for testing auto-configuration without running a web server or a full business application.

## 7. Checking ordering in a real packaged application

### 7.1. Checking the imports file inside the JAR

After building the starter module, inspect the packaged file:

```bash
jar tf target/auto-configuration-order-demo-0.0.1-SNAPSHOT.jar
```

For an auto-configuration library packaged as a separate JAR, inspect:

```bash
jar tf acme-autoconfigure-1.0.0.jar
jar xf acme-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

The imports file must be present and contain the exact fully-qualified class names of the candidates. If a class is not in imports, its before/after metadata will not help Spring Boot auto-discover that class.

### 7.2. Enabling Condition Evaluation Report

Run the Spring Boot application with:

```bash
java -jar app.jar --debug
```

In `CONDITIONS EVALUATION REPORT`, look for the relevant sources:

- `FoundationAutoConfiguration#foundationService`.
- `FeatureAutoConfiguration#featureService`.
- `AuditAutoConfiguration#auditService`.

Read the condition messages to see which beans were found or not found. If a consumer does not match, check whether the provider is imported, whether the provider's condition matches, and whether the after relationship is declared properly.

The report helps diagnose conditions; testing the bean registry remains the direct proof that the final outcome is right.

### 7.3. Distinguishing definition order from instantiation order

You can add logging inside constructors or factory methods to observe when objects are created, yet do not use those logs to deduce auto-configuration processing order. A bean definition can be registered early while its instance is created only when a dependency or singleton pre-instantiation requires it.

In the example, factory method parameters establish explicit dependencies. If two beans have no injection relationship yet one must initialize before another for side effects/lifecycle reasons, consider `@DependsOn`:

```java
@Bean
@DependsOn("foundationInitializer")
FeatureRegistry featureRegistry() {
    return new FeatureRegistry();
}
```

`@DependsOn` controls only the initialization relationship of the named bean. It does not make `@ConditionalOnBean` see an unregistered bean definition, does not force an auto-configuration to be imported, and does not alter already-evaluated condition order.

## 8. Situations requiring choosing the right mechanism

### 8.1. Consumer depends on another auto-configuration's provider

Use `@AutoConfiguration(after = ProviderAutoConfiguration.class)`. This is the classic case for `@ConditionalOnBean` and `@ConditionalOnMissingBean`.

### 8.2. Configuration must run before an existing auto-configuration

Use `before` or `beforeName`. For example, a custom auto-configuration needs to register metadata or a bean so a later configuration can see it. Use this only when there is a concrete reason involving condition/definition processing.

### 8.3. Two independent auto-configurations need a general order

Use `@AutoConfigureOrder`. Avoid creating class coupling just to achieve order when the two configurations have no real dependency.

### 8.4. One bean instance must be alive before another bean

Use dependency injection. If there is no injection relationship yet a lifecycle requirement exists, use `@DependsOn` deliberately.

### 8.5. Element order in a list needs to be chosen

Use `@Order` or `Ordered` on the relevant beans. For instance, a `List<Handler>` can be sorted by order; this is not the application order of auto-configuration classes.

## 9. Common mistakes

1. **Relying on line order in `AutoConfiguration.imports`.** Do not use line order as a dependency contract; declare `before`/`after` explicitly.
2. **Relying on class argument order passed to tests.** `AutoConfigurations.of` applies Boot's auto-configuration sorting mechanism; test metadata by intentionally reversing input order.
3. **Confusing config order with object order.** `after` affects bean definition processing, whereas the dependency graph and `@DependsOn` govern instance creation.
4. **Using `@DependsOn` to fix an unmatched condition.** If a bean definition does not exist, `@DependsOn` cannot create it.
5. **Using `@AutoConfigureOrder` instead of an explicit dependency relationship.** An order number does not express why a consumer needs a provider; use after/before.
6. **Forgetting that user beans are registered before auto-configuration.** `@ConditionalOnMissingBean` can yield to custom beans; do not assume the default provider always exists.
7. **Placing bean conditions too early in regular user configuration.** Conditions rely on already-processed bean definitions; place them in auto-configurations and order providers/consumers properly.
8. **Placing overly broad class-level conditions.** One bean missing a dependency can exclude the entire config class, taking unrelated beans with it.
9. **Creating before/after cycles.** Ordering relationships must form a directed acyclic graph; audit the edges when multiple starters constrain each other.
10. **Referencing optional classes directly in metadata without considering dependencies.** Use `afterName`/`beforeName` when you need to avoid compile-time coupling to a class that may be absent.
11. **Forgetting to register the class in the imports file.** Ordering annotations do not by themselves make a class an auto-configuration candidate.
12. **Reading only the report without asserting beans.** Condition messages explain decisions; tests of bean counts, bean names, and output values verify behavior.

## 10. Auto-configuration ordering review checklist

- [ ] Every auto-configuration class is registered in `AutoConfiguration.imports`.
- [ ] Providers and consumers are clearly identified according to bean conditions.
- [ ] Required relationships are declared with `after`/`before` or their name variants.
- [ ] Nothing relies on imports line order or class names.
- [ ] `@AutoConfigureOrder` is used only for general ordering among independent configurations.
- [ ] User-defined beans are tested to verify default back-off.
- [ ] Missing provider is tested to verify consumers are not registered unintentionally.
- [ ] Tests pass candidates in reversed order to verify metadata.
- [ ] Bean instance order is handled via dependency injection or `@DependsOn` when genuinely needed.
- [ ] There are no circular before/after relationships.
- [ ] Condition Evaluation Report is inspected whenever a condition does not match.
- [ ] Tests have been run on the exact Spring Boot version supported by the starter.

## Official Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): locating candidates, imports file, ordering metadata, bean conditions, and testing.
- [Spring Boot 3.3 — `@AutoConfiguration` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): `before`, `beforeName`, `after`, and `afterName` attributes.
- [Spring Boot 3.3 — `@AutoConfigureBefore` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html): meaning of application order and distinction from bean initialization order.
- [Spring Boot 3.3 — `@AutoConfigureAfter` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html): declaring configuration that must be applied after a provider.
- [Spring Boot 3.3 — `@AutoConfigureOrder` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html): general ordering for auto-configuration.
- [Spring Boot 3.3 — `ApplicationContextRunner` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): creating isolated test contexts to verify bean conditions.
