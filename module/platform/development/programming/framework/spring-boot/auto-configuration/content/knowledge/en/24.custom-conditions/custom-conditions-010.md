# Checking List Properties with a Specialized Condition

**Topic:** Spring Boot Auto Configuration  
**Knowledge Group:** Custom Conditions  
**Objective:** Create a condition that activates auto-configuration only when a list property is declared. This lesson explains why `@ConditionalOnProperty` is unreliable for lists represented by indexed keys, how to use `Binder` and `OnPropertyListCondition`, and how to test different configuration formats.

## 1. The Problem: A List in YAML Is Not a Single Scalar Property

Suppose a starter registers `TargetRegistry` only when the application configures a list of targets:

```yaml
acme:
  targets:
    - eu-west
    - ap-southeast
```

Spring Boot flattens YAML into flat properties in `Environment`. The list above is equivalently represented as:

```properties
acme.targets[0]=eu-west
acme.targets[1]=ap-southeast
```

These are properties with indexed elements `[0]`, `[1]`. Another way to configure them is a comma-separated string:

```properties
acme.targets=eu-west,ap-southeast
```

Both forms can be bound by Spring Boot's `Binder` into `List<String>`. However, they do not produce the same key in `Environment`: the indexed form has keys `acme.targets[0]`, `acme.targets[1]`, whereas the comma-separated form has the direct key `acme.targets`.

This difference affects configuration conditions. A condition that checks for the presence of a scalar key does not automatically recognize that indexed child keys form a list.

## 2. Why Is `@ConditionalOnProperty` Unreliable for Collections?

A seemingly reasonable approach:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "acme", name = "targets")
class TargetAutoConfiguration {
    // Register beans depending on the target list.
}
```

`@ConditionalOnProperty` checks for a property named `acme.targets` in `Environment`. By default, the property must exist and its value must not equal the string `"false"`; `havingValue` and `matchIfMissing` can adjust this rule.

With comma-separated configuration:

```properties
acme.targets=eu-west,ap-southeast
```

the key `acme.targets` is present, so the condition can match.

With YAML list configuration:

```yaml
acme:
  targets:
    - eu-west
    - ap-southeast
```

the actual keys are `acme.targets[0]` and `acme.targets[1]`. The root key `acme.targets` may not exist, so `@ConditionalOnProperty(prefix = "acme", name = "targets")` does not match even though the list was configured.

Spring Boot API documentation explicitly warns that `@ConditionalOnProperty` cannot be used reliably to match collection properties. This is not a YAML bug; it is the difference between checking a specific key and binding a collection structure.

**Rule of thumb:** if a condition depends on a list, use `Binder` to bind that list or use the specialized base class `OnPropertyListCondition`.

## 3. `Binder` Aggregates Indexed Keys into a List

`Binder` resides in package:

```java
org.springframework.boot.context.properties.bind
```

You can obtain a binder from `Environment`:

```java
Binder binder = Binder.get(context.getEnvironment());
```

Then bind the property to a concrete collection type:

```java
BindResult<List<String>> result = binder.bind(
        "acme.targets",
        Bindable.listOf(String.class)
);
```

Key components:

| API | Role |
| --- | --- |
| `Binder.get(environment)` | Creates a binder using the Environment's property sources |
| `bind(name, target)` | Attempts to bind properties starting at the specified name |
| `Bindable.listOf(String.class)` | Describes the target type as `List<String>` |
| `BindResult.isBound()` | Indicates whether a value was bound |
| `BindResult.orElse(...)` | Retrieves the bound value or uses a fallback |

Example safely retrieving a list when the property is absent:

```java
List<String> targets = Binder.get(environment)
        .bind("acme.targets", Bindable.listOf(String.class))
        .orElseGet(List::of);
```

For YAML lists or indexed keys, Binder recognizes the structure and collects elements by index. For comma-separated properties, Binder can also convert the value into `List<String>`.

Do not manually read `Environment.getProperty("acme.targets")` and split the string on commas. Doing so misses indexed keys, relaxed binding, conversion, and property source precedence rules handled by Binder.

## 4. Using Spring Boot's Built-In `OnPropertyListCondition`

Spring Boot provides the base class `OnPropertyListCondition` in package:

```java
org.springframework.boot.autoconfigure.condition
```

This class extends `SpringBootCondition` and uses `Binder` to check whether a property can be bound into a list. Its constructor accepts the full property name and a `Supplier<ConditionMessage.Builder>` to create a fresh message on each evaluation.

This is the right choice when an auto-configuration needs to check a list with a fixed name.

### 4.1. Creating a Custom Annotation

File `ConditionalOnConfiguredTargets.java`:

```java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnConfiguredTargetsCondition.class)
public @interface ConditionalOnConfiguredTargets {
}
```

The annotation can be placed on a configuration class or a `@Bean` method. `@Conditional` links the annotation to the condition class.

### 4.2. Writing the Condition with `OnPropertyListCondition`

File `OnConfiguredTargetsCondition.java`:

```java
package demo;

import org.springframework.boot.autoconfigure.condition.ConditionMessage;
import org.springframework.boot.autoconfigure.condition.OnPropertyListCondition;

public final class OnConfiguredTargetsCondition extends OnPropertyListCondition {

    public OnConfiguredTargetsCondition() {
        super(
                "acme.targets",
                () -> ConditionMessage.forCondition("Configured targets")
        );
    }
}
```

The condition checks the list property `acme.targets`. `OnPropertyListCondition` performs the binding itself and creates a condition outcome/message for Spring Boot diagnostics.

Using a `Supplier` is important: each condition evaluation needs a new `ConditionMessage.Builder`. Never share a stateful builder across evaluations.

### 4.3. Applying It to Auto-Configuration

File `TargetRegistry.java`:

```java
package demo;

import java.util.List;

public record TargetRegistry(List<String> targets) {
}
```

File `TargetAutoConfiguration.java`:

```java
package demo;

import java.util.List;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
@ConditionalOnConfiguredTargets
public class TargetAutoConfiguration {

    @Bean
    TargetRegistry targetRegistry(Environment environment) {
        List<String> targets = Binder.get(environment)
                .bind("acme.targets", Bindable.listOf(String.class))
                .orElseGet(List::of);

        return new TargetRegistry(List.copyOf(targets));
    }
}
```

The class-level condition decides whether the entire `TargetAutoConfiguration` is applied. When the list can be bound, the `TargetRegistry` bean is registered and receives the list from the same `Environment`.

In a real library, the bean might use `@ConfigurationProperties` instead of binding directly inside the method. The example binds directly to make clear how the same property name is checked by the condition and consumed by the bean.

If only a single bean depends on the list, you can place `@ConditionalOnConfiguredTargets` on that `@Bean` method alone. When placed at the class level, other bean methods in the configuration are also skipped if the condition does not match.

## 5. Testing Indexed Lists and Comma-Separated Lists

At least three scenarios should be tested:

1. No list provided: configuration is not applied.
2. Indexed keys provided: custom list condition matches.
3. A comma-separated property provided: custom list condition also matches.

Also test a standard `@ConditionalOnProperty` alongside it to see the difference with indexed lists.

### 5.1. `pom.xml`

The example uses Java 17 and Spring Boot 3.3.13:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>list-property-condition</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 5.2. `TargetAutoConfigurationTests.java`

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class TargetAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            TargetAutoConfiguration.class,
                            DirectPropertyConditionConfiguration.class
                    );

    @Test
    void indexedListActivatesCustomConditionButNotScalarPropertyCondition() {
        this.runner
                .withPropertyValues(
                        "acme.targets[0]=eu-west",
                        "acme.targets[1]=ap-southeast"
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(TargetRegistry.class);

                    assertThat(context.getBean(TargetRegistry.class).targets())
                            .containsExactly("eu-west", "ap-southeast");

                    assertThat(context)
                            .doesNotHaveBean("directPropertyMarker");
                });
    }

    @Test
    void missingListDoesNotRegisterTargetRegistry() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(TargetRegistry.class);
            assertThat(context).doesNotHaveBean("directPropertyMarker");
        });
    }

    @Test
    void commaSeparatedPropertyCanBeBoundAsList() {
        this.runner
                .withPropertyValues("acme.targets=eu-west,ap-southeast")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(TargetRegistry.class);

                    assertThat(context.getBean(TargetRegistry.class).targets())
                            .containsExactly("eu-west", "ap-southeast");

                    assertThat(context).hasBean("directPropertyMarker");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class DirectPropertyConditionConfiguration {

        @Bean
        @ConditionalOnProperty(prefix = "acme", name = "targets")
        String directPropertyMarker() {
            return "root-property-present";
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

Expected result from Maven Surefire:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

There is no custom stdout from the tests. Results are verified with AssertJ inside each `ApplicationContextRunner` callback.

### 5.3. Reading the Test Results

| Case | Property source | `OnPropertyListCondition` | `@ConditionalOnProperty` |
| --- | --- | --- | --- |
| No list | No `acme.targets` | No match | No match |
| YAML/indexed list | `acme.targets[0]`, `acme.targets[1]` | Match | Does not match if root key does not exist |
| Comma-separated | `acme.targets=eu-west,ap-southeast` | Match | Match |

The first test is the primary proof: `TargetRegistry` is created from the indexed list, while the `directPropertyMarker` bean is skipped because the scalar condition does not find the root key.

The last test shows `@ConditionalOnProperty` still works with a scalar property containing a comma-separated string. The issue is not that this annotation always fails for every list representation; the issue is that it does not aggregate indexed keys into a collection.

## 6. When Do You Only Need List Presence vs. a Non-Empty List?

`OnPropertyListCondition` checks whether the property can be bound as a list. Its purpose is to recognize a list property in `Environment`, including when represented by indexed keys.

That is not equivalent to every business rule about list contents. Different requirements may exist:

- The list property is declared.
- The list binds and has at least one element.
- The list has at least one non-empty or non-whitespace element.
- The list has at least one element matching a specific format or policy.

If you only need to know that the list property is declared, extending `OnPropertyListCondition` is appropriate.

If you need to check that the list has a non-blank element, write a `Condition` using Binder and inspect the contents after binding:

```java
package demo;

import java.util.List;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

final class OnNonEmptyTargetsCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        List<String> targets = Binder.get(context.getEnvironment())
                .bind("acme.targets", Bindable.listOf(String.class))
                .orElseGet(List::of);

        return targets.stream()
                .anyMatch(value -> value != null && !value.isBlank());
    }
}
```

Attach this condition with a custom annotation:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnNonEmptyTargetsCondition.class)
public @interface ConditionalOnNonEmptyTargets {
}
```

You can place `@ConditionalOnNonEmptyTargets` on the configuration class or bean method to guard. The example above defines a concrete policy: at least one element must contain non-whitespace characters. If business rules require elements to match a hostname, URI, or region code, validate that exact rule after binding.

When you need detailed messages in the Condition Evaluation Report, you can extend `SpringBootCondition` and return `ConditionOutcome` with match/no-match reasons. `OnPropertyListCondition` already provides outcome recording for checking list presence.

## 7. Lists of Objects Instead of Strings

Binder does not bind only `List<String>`. If each element is an object with multiple fields, use the concrete element type in `Bindable`.

YAML example:

```yaml
acme:
  endpoints:
    - name: europe
      url: https://eu.example.test
      enabled: true
    - name: asia
      url: https://asia.example.test
      enabled: false
```

Equivalent keys:

```properties
acme.endpoints[0].name=europe
acme.endpoints[0].url=https://eu.example.test
acme.endpoints[0].enabled=true
acme.endpoints[1].name=asia
acme.endpoints[1].url=https://asia.example.test
acme.endpoints[1].enabled=false
```

Type declaration:

```java
public record Endpoint(
        String name,
        URI url,
        boolean enabled
) {
}
```

You can bind:

```java
List<Endpoint> endpoints = Binder.get(environment)
        .bind("acme.endpoints", Bindable.listOf(Endpoint.class))
        .orElseGet(List::of);
```

The base `OnPropertyListCondition` is designed to check list properties as `List<String>`. If the list contains complex objects or needs to inspect a specific field such as `enabled=true`, use a custom `Condition` with Binder and `Bindable.listOf(Endpoint.class)`.

For instance, a condition "at least one endpoint is enabled" should check `endpoints.stream().anyMatch(Endpoint::enabled)` rather than merely checking that the list was declared.

## 8. Property Sources, Relaxed Binding, and Profiles

`Binder.get(context.getEnvironment())` uses the property sources loaded by Spring Boot into `Environment`. Thus the condition works across configuration sources such as:

- `application.yml` and `application.properties`.
- Profile-specific files such as `application-prod.yml`.
- Environment variables.
- System properties.
- Command-line arguments.
- Additional property sources registered by the application.

For example, a list from environment variables can take the form:

```text
ACME_TARGETS_0=eu-west
ACME_TARGETS_1=ap-southeast
```

Spring Boot applies environment-variable name conversion rules for list elements, where indices are surrounded by underscores. Binder performs relaxed binding and conversion based on `Environment`.

If profile `prod` defines a list while that profile is not active, the condition will not see those values. When debugging, verify active profiles and effective property sources; do not just look at an unloaded YAML file.

When multiple property sources declare the list, Binder applies Spring Boot's precedence and collection-binding rules. Do not manually merge lists by reading each source separately. If you need to replace an entire list in a profile override, inspect the actual bound result to confirm the final list matches expectations.

## 9. When Is the Condition Evaluated and What Should Happen Inside?

Spring evaluates conditions while parsing/registering configuration classes and bean definitions. At that moment, beans defined by auto-configuration may not have been created yet.

Therefore, a custom condition should:

- Read `Environment` and bind properties using `Binder`.
- Perform only fast, deterministic, side-effect-free checks.
- Return consistent results for the same configuration.
- Avoid accessing application beans that may not exist yet.
- Avoid opening database connections, making HTTP calls, or querying remote services.
- Never create beans or mutate `Environment` inside `matches`.

Do not inject a `@ConfigurationProperties` bean into a condition to read the list. That bean may not be registered or initialized when the condition runs. Binding directly from `ConditionContext.getEnvironment()` is the appropriate approach.

If you need to check whether a bean already exists, use the corresponding bean conditions such as `@ConditionalOnBean`/`@ConditionalOnMissingBean` or a custom condition reading `BeanFactory` in the proper lifecycle phase. Do not mix bean checks with list-property checks if the two decisions can be expressed independently.

## 10. Handling Binding Errors and Invalid Data

A list condition should distinguish:

1. **Missing property:** Binder cannot bind a list; the condition can return no-match.
2. **Valid list:** Binder returns a list; the condition decides match according to policy.
3. **Unconvertible value:** Binder may throw `BindException` or a related conversion error. This signals invalid configuration and should not silently be treated as an absent list.
4. **List with blank elements:** Binder may bind elements that business rules reject. Content-checking conditions or validation must decide explicitly.

Do not catch every `Exception` and return `false`. Doing so turns real configuration mistakes into a hard-to-spot no-match; the application may start with the feature disabled and no explanation why.

For complex configuration lists, consider `@ConfigurationProperties` combined with Bean Validation (`@Validated`, `@NotEmpty`, `@NotBlank`, etc.) to validate contents after binding. Conditions decide whether configuration applies; validation verifies whether bound data conforms to the contract. The two mechanisms serve different purposes.

## 11. Diagnosing When the Condition Does Not Match as Expected

When auto-configuration is not applied:

1. Enable `--debug` or `debug=true` to inspect the Condition Evaluation Report.
2. Locate the configuration class or bean method guarded by the custom condition.
3. Confirm the full property name, e.g., `acme.targets`.
4. Check whether the actual configuration is an indexed list (`acme.targets[0]`) or scalar/comma-separated (`acme.targets`).
5. Use `Binder.get(environment).bind(..., Bindable.listOf(String.class))` in a test or debug point to see the final list.
6. Confirm active profiles and property sources.
7. Check conversion/validation if the property exists yet binding fails.
8. If the condition matches yet the bean is missing, check other conditions on the configuration/method, bean registration, and auto-configuration ordering.

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `@ConditionalOnProperty` no-match with YAML list | Only `[0]`, `[1]` keys exist, no root key | Use `OnPropertyListCondition` or Binder |
| Custom condition no-match when list is absent | No property to bind | Check active profiles and configuration sources |
| Comma-separated matches yet indexed no-match | Condition is reading the root key directly | Bind using `Binder` |
| Condition matches yet list is empty | Only checked whether the list bound | Check size/elements if business rules require |
| Condition throws binding error | Invalid data type or property structure | Read root cause and fix configuration |
| Tests pass yet application does not match | Test and runtime use different property sources/profiles | Reproduce with the exact active profiles and environment |

## 12. Common Misconceptions

**Misconception 1: `@ConditionalOnProperty` automatically recognizes all collection formats.**  
False. It checks a specific property name. Indexed keys do not guarantee the root key exists.

**Misconception 2: A YAML list is a single string in Environment.**  
False. YAML lists are typically flattened into indexed keys like `acme.targets[0]`.

**Misconception 3: Simply calling `Environment.getProperty("acme.targets")` is enough.**  
False. Reading a scalar key does not aggregate indexed elements. Use Binder for list structures.

**Misconception 4: `OnPropertyListCondition` validates that every element is valid.**  
False. It checks that the list property can be bound; business rules for individual element values must be checked separately.

**Misconception 5: A declared list is guaranteed to be non-empty.**  
False. "Having the property" and "having at least one useful element" are two distinct conditions.

**Misconception 6: You can access a `@ConfigurationProperties` bean inside a condition.**  
You should not. Conditions run before configuration beans are guaranteed to be created; bind directly from Environment.

**Misconception 7: Binding errors should also return no-match.**  
You should not do this. Conversion or data structure errors are usually configuration errors that should surface clearly.

**Misconception 8: Key declaration order in YAML determines condition evaluation order.**  
False. Binder reads property sources and list indices; textual declaration order is not a mechanism for toggling conditions.

## 13. Review Checklist

- [ ] Clearly define whether the condition checks list declaration or valid elements.
- [ ] Do not use `@ConditionalOnProperty` to check indexed collection keys.
- [ ] Use `OnPropertyListCondition` for fixed list properties when only bindability needs checking.
- [ ] Use `Binder` + `Bindable.listOf(...)` for custom types or custom content rules.
- [ ] Place the condition at the configuration class level or the exact bean method to guard.
- [ ] Do not depend on `@ConfigurationProperties` beans while the condition is running.
- [ ] Include tests for missing list, indexed list, and comma-separated list.
- [ ] Include a test proving `@ConditionalOnProperty` does not match indexed keys.
- [ ] Treat conversion/binding failures as configuration errors, not masked by catch-alls.
- [ ] Verify profiles and property sources match the deployment environment.
- [ ] Read the Condition Evaluation Report when outcomes differ from expectations.

## 14. Self-Check Questions

**Question 1.** Why might `@ConditionalOnProperty(prefix = "acme", name = "targets")` not match when YAML contains an `acme.targets` list?  
**Answer:** YAML lists are flattened into `acme.targets[0]`, `acme.targets[1]`; the root key `acme.targets` may not exist for the condition to check.

**Question 2.** Which API binds an indexed list into `List<String>`?  
**Answer:** `Binder.get(environment).bind("acme.targets", Bindable.listOf(String.class))`.

**Question 3.** What is the role of Spring Boot's `OnPropertyListCondition`?  
**Answer:** It uses Binder to check whether a property can be bound into a list and provides condition outcomes/log messages.

**Question 4.** Does `OnPropertyListCondition` imply the list definitely contains non-blank elements?  
**Answer:** No. If non-blank elements are required, bind the list and inspect its contents according to business rules.

**Question 5.** When can `@ConditionalOnProperty` work with a list?  
**Answer:** When the property is represented under the root key, such as `acme.targets=eu-west,ap-southeast`; this does not cover cases with only indexed keys.

**Question 6.** Why should a condition not access a `@ConfigurationProperties` bean?  
**Answer:** Conditions are evaluated during configuration processing before that bean is guaranteed to exist. Bind directly from `Environment`.

**Question 7.** If Binder throws a conversion error, should it be treated as a no-match?  
**Answer:** No. That usually indicates invalid configuration; preserve the root cause so operators can fix the data.

## 15. Key Principles to Remember

- `@ConditionalOnProperty` checks a specific key; it does not aggregate indexed collection properties.
- YAML lists typically become `property[0]`, `property[1]` in Environment.
- `Binder` and `Bindable.listOf(...)` are the right way to read lists following Spring Boot's binding rules.
- `OnPropertyListCondition` is the built-in base class for building conditions that check list properties.
- Distinguish a declared list from a list with valid elements.
- Use a custom `Condition` when you need to inspect contents, element types, or custom business rules.
- Conditions should be fast, deterministic, side-effect-free, and independent of yet-uncreated beans.
- Test indexed lists, comma-separated lists, and missing properties using `ApplicationContextRunner`.

### Official References

- [Spring Boot 3.3.13 API — `@ConditionalOnProperty`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3.13 API — `OnPropertyListCondition`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/OnPropertyListCondition.html)
- [Spring Boot 3.3.13 API — `Binder`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html)
- [Spring Boot 3.3 — Externalized Configuration and YAML Lists](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
