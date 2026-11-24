# Limitations When Checking List or Indexed Element Properties in Spring Boot Auto-Configuration

## 1. Problem: "Having a List" Differs from "Having a Property Key"

When writing auto-configuration, we often enable a bean based on configuration:

```java
@Bean
@ConditionalOnProperty(prefix = "demo", name = "recipients")
NotificationDispatcher notificationDispatcher() {
    return new NotificationDispatcher();
}
```

The example above is an **illustrative snippet**, assuming the `NotificationDispatcher` class already exists in the project. The intent may be "only register `NotificationDispatcher` if the recipients list has at least one element". However, `@ConditionalOnProperty` **does not directly inspect the contents of a `List`**. It checks property keys and values in `Environment` at the time Spring processes conditions.

Specifically, according to the Spring Boot 3.3 Javadoc, this annotation is **not reliable when used to match collection properties**: the parent key `demo.recipients` and the element key `demo.recipients[0]` cannot be treated as equivalent. Consequently, an application can have a valid list yet the condition still fails to match.

This lesson belongs to the **property conditions** group, focusing on limitations when using `@ConditionalOnProperty` with lists, arrays, indexed elements, and nested configuration.

## 2. Mechanism of `@ConditionalOnProperty`

Example:

```java
@ConditionalOnProperty(
    prefix = "demo",
    name = "recipients",
    havingValue = "true",
    matchIfMissing = false
)
```

The annotation attributes mean:

| Attribute | Meaning |
|---|---|
| `prefix` | Key prefix, e.g., `demo`. |
| `name` or `value` | Key name to check, e.g., `recipients`; with `prefix` forms key `demo.recipients`. |
| `havingValue` | Compares the **string value** of the specified key; not used to iterate a `List`. |
| `matchIfMissing` | Result if the **checked key** is absent; defaults to `false`. |

By default, when `havingValue` is not declared, the condition matches if the key is present and its value **does not equal the string `"false"`** (case-insensitive per condition semantics). This does not mean "non-empty value" or "list has elements". A present key with an empty string value is also not automatically treated as an empty list to be rejected.

If `name` has multiple keys, **every key must pass** the condition; this is not an OR expression to try various list naming forms.

An important note: `@ConditionalOnProperty` relies on finding the **queried key** in `Environment`. Conversely, Spring Boot's configuration binding mechanism can aggregate multiple indexed keys into a `List<T>` via `Binder`. The two mechanisms are not equivalent.

## 3. Why YAML Lists and `.properties` Can Yield Different Results

Consider `application.yml`:

```yaml
demo:
  recipients:
    - alice@example.test
    - bob@example.test
```

When YAML is loaded into `Environment`, list elements are usually represented as flattened keys as follows:

```properties
demo.recipients[0]=alice@example.test
demo.recipients[1]=bob@example.test
```

In essence, the keys `demo.recipients[0]` and `demo.recipients[1]` exist. You cannot assume that `Environment` simultaneously holds a standalone string value at the parent key `demo.recipients`.

Meanwhile, `application.properties` can also use a single string value directly on the parent key:

```properties
demo.recipients=alice@example.test,bob@example.test
```

The table below describes how this behaves **in the scenario where only the stated keys exist** and `@ConditionalOnProperty(prefix = "demo", name = "recipients")` is used with default values:

| Data in property source | Standalone `demo.recipients` key present? | Condition checking parent key | Can bind into `List<String>`? |
|---|---|---|---|
| `demo.recipients=alice@example.test,bob@example.test` | Yes | Matches, because value is not `"false"` | Yes, two elements |
| `demo.recipients[0]=alice@example.test` | No | **Does not match** | Yes, one element |
| `demo.recipients[0]=alice...` and `[1]=bob...` | No | **Does not match** | Yes, two elements |
| `demo.recipients` not configured | No | Does not match, default `matchIfMissing=false` | No list to bind |

The table describes only the stated property sources. In a real application, the parent key might come from another source (profile file, environment variable, CLI argument), causing the condition result to differ from predictions made by looking at a single file.

**Important distinctions:**

- `Environment#getProperty("demo.recipients")` retrieves the value for a single key name. Do not assume this API automatically concatenates all indexed keys into a list string.
- `Binder` knows how to bind `[index]` notation into a `List` according to Spring Boot configuration rules.
- `@ConfigurationProperties` also uses typed binding; a working configuration bean with `List<String>` **does not prove** `@ConditionalOnProperty(name = "recipients")` will match.

When using YAML lists in auto-configuration, this is a frequent root cause of the "elements are configured yet the bean is not created" symptom.

## 4. Why Checking `[0]` Is Not a General Solution

You could write:

```java
@ConditionalOnProperty(prefix = "demo", name = "recipients[0]")
```

This checks **strictly the key** `demo.recipients[0]`. With a property source containing that key, the condition can match. However, it is still a check on a **single key**, so:

1. It cannot confirm **the whole list bound successfully**.
2. It does not check list size, valid elements, blank values, or business rules.
3. It depends on data being represented with `[0]`. If a source uses a single string value on the parent key or another property source mechanism, the `[0]` key may be absent.
4. For lists of objects, `demo.routes[0]` and `demo.routes[0].url` are two different names. A property source may expose only child keys, with no key for the parent object.
5. Declaring multiple indices in `name` does not turn the annotation into "has at least one element", because multiple names combine with AND logic by default.

For example, `@ConditionalOnProperty(name = "routes[0].url")` only answers whether **the key `routes[0].url` satisfies the condition**. It does not verify that valid routes exist at other indices, or that the entire list bound and validated cleanly.

Therefore, using an indexed key directly is only appropriate when the business requirement **genuinely is to check that exact fixed key**, not to detect a collection.

## 5. Right Way When Needing "List Has at Least One Valid Value"

When deciding bean creation depends on list contents, write a custom `Condition`, bind the configuration with `Binder`, and evaluate the business semantics of the data.

For example, enable the bean only when `demo.recipients` has at least one string that is **non-empty and not whitespace-only**:

```java
import java.util.List;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class NonEmptyRecipientsCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        List<String> recipients = Binder.get(context.getEnvironment())
                .bind("demo.recipients", Bindable.listOf(String.class))
                .orElse(List.of());

        return recipients.stream()
                .anyMatch(value -> value != null && !value.isBlank());
    }
}
```

This is the **complete code of a condition class**; save it to `NonEmptyRecipientsCondition.java` in the chosen package and add the appropriate `package` declaration. The condition is attached to a `@Bean` method or configuration class via `@Conditional(NonEmptyRecipientsCondition.class)`.

Mechanism:

1. `ConditionContext` supplies the `Environment` being used to evaluate conditions.
2. `Binder.get(environment)` accesses how Spring Boot binds configuration from property sources.
3. `bind("demo.recipients", Bindable.listOf(String.class))` attempts to build a `List<String>` from a parent string key or from `[0]`, `[1]`, ... keys.
4. `orElse(List.of())` returns an empty list when no bindable data exists.
5. `anyMatch(...)` applies the **at least one element with content** rule. If the requirement is that all elements are valid, use a different check, such as non-empty and `allMatch(...)`.

The example above assumes each element is a string. If configuration holds objects, bind to a list of the appropriate data type and check the required fields; do not force object structures into `List<String>`.

**Note on configuration errors:** `Binder` can throw binding errors on wrong data types or invalid structure. Do not assume all errors should be swallowed into `false`; the application may need to report clear configuration errors for operators to fix.

## 6. Runnable Test Example: Comparing Direct Condition vs. `Binder`

Below is a **standalone Java test file in a Spring Boot 3.3 project with Java 17+ and JUnit 5**, using `ApplicationContextRunner`. Static classes are placed in the same file for easy execution, without needing a web server.

Place the file at `src/test/java/demo/IndexedCollectionConditionTest.java`:

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.type.AnnotatedTypeMetadata;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IndexedCollectionConditionTest {

    // Naive condition: only asks Environment whether the parent key exists.
    @Configuration(proxyBeanMethods = false)
    static class DirectPropertyConfiguration {
        @Bean
        @ConditionalOnProperty(prefix = "demo", name = "recipients")
        String directMarker() {
            return "direct";
        }
    }

    // Appropriate condition when the intent is at least one useful element.
    public static final class HasRecipientsCondition implements Condition {
        @Override
        public boolean matches(
                ConditionContext context,
                AnnotatedTypeMetadata metadata) {

            List<String> recipients = Binder.get(context.getEnvironment())
                    .bind("demo.recipients", Bindable.listOf(String.class))
                    .orElse(List.of());

            return recipients.stream()
                    .anyMatch(value -> value != null && !value.isBlank());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BoundListConfiguration {
        @Bean
        @Conditional(HasRecipientsCondition.class)
        String boundMarker() {
            return "bound";
        }
    }

    @Test
    void indexedValuesDoNotMatchTheParentKey() {
        new ApplicationContextRunner()
                .withUserConfiguration(DirectPropertyConfiguration.class)
                .withPropertyValues(
                        "demo.recipients[0]=alice@example.test",
                        "demo.recipients[1]=bob@example.test"
                )
                .run(context ->
                        assertFalse(context.containsBean("directMarker"))
                );
    }

    @Test
    void binderFindsTheIndexedValues() {
        new ApplicationContextRunner()
                .withUserConfiguration(BoundListConfiguration.class)
                .withPropertyValues(
                        "demo.recipients[0]=alice@example.test",
                        "demo.recipients[1]=bob@example.test"
                )
                .run(context ->
                        assertTrue(context.containsBean("boundMarker"))
                );
    }

    @Test
    void missingListDoesNotCreateTheBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(BoundListConfiguration.class)
                .run(context ->
                        assertFalse(context.containsBean("boundMarker"))
                );
    }

    @Test
    void aBlankIndexedElementDoesNotActivateTheBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(BoundListConfiguration.class)
                .withPropertyValues("demo.recipients[0]= ")
                .run(context ->
                        assertFalse(context.containsBean("boundMarker"))
                );
    }

    @Test
    void commaSeparatedRootValueCanMatchBothConditions() {
        new ApplicationContextRunner()
                .withUserConfiguration(
                        DirectPropertyConfiguration.class,
                        BoundListConfiguration.class
                )
                .withPropertyValues(
                        "demo.recipients=alice@example.test,bob@example.test"
                )
                .run(context -> {
                    assertTrue(context.containsBean("directMarker"));
                    assertTrue(context.containsBean("boundMarker"));
                });
    }
}
```

The tests use `assertTrue`/`assertFalse` on **bean names**, avoiding the need to retrieve a `String` by type when two markers share the same type. Each `ApplicationContextRunner` creates an isolated context so properties do not leak across scenarios.

### Dependencies and how to run

The Spring Boot project needs the appropriate test dependency, typically:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Run from the Gradle project directory:

```bash
./gradlew test --tests demo.IndexedCollectionConditionTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.IndexedCollectionConditionTest
```

**Expected result:** all five tests pass. In particular, with two indexed keys, `directMarker` **is not created** whereas `boundMarker` **is created**; when the list is absent or has only a whitespace-only value, `boundMarker` is not created. This expectation is based on the binding/condition behavior described for Spring Boot 3.3; run the test suite on the actual project to confirm with your dependencies and configuration.

**If you already have the condition class from section 5:** in production code, use that class; `HasRecipientsCondition` nested inside the test is only so the example can run standalone.

## 7. Alternative When Only a Feature Toggle Is Needed

If the real intent is "operators allow the system to send notifications", a **single boolean property** is easier to understand and more reliable as a bean-enabling condition:

```yaml
demo:
  notifications:
    enabled: true
    recipients:
      - alice@example.test
      - bob@example.test
```

```java
@Bean
@ConditionalOnProperty(
    prefix = "demo.notifications",
    name = "enabled",
    havingValue = "true"
)
NotificationDispatcher notificationDispatcher() {
    return new NotificationDispatcher();
}
```

Here `NotificationDispatcher` is an assumed application class; the Java snippet only illustrates placing the annotation on an existing bean method.

The condition depends solely on `demo.notifications.enabled`, not on how the list is represented. However, `enabled=true` **does not guarantee** the `recipients` list has valid elements. Bind and **validate** configuration data according to application needs (for example via `@ConfigurationProperties` and Jakarta Bean Validation, if the project configures validation).

Choose based on requirements:

| Actual need | Appropriate approach |
|---|---|
| Enable feature based on an explicit flag | `@ConditionalOnProperty` on `enabled`, usually paired with `havingValue="true"` |
| Create bean when list has valid elements | Custom `Condition` + `Binder` + predicate |
| Only need to check one specific indexed key | Check exact name `items[0]`, understanding its limitations |
| Check objects in list have required fields | Bind corresponding structured type then validate/evaluate fields |

## 8. Edge Cases When Data Comes from Multiple Sources

### 8.1. A list differs from a scalar property

`@ConditionalOnProperty` operates on the string value reported for the specified key; it has no `minimumSize` parameter, does not call `isEmpty()`, and does not inspect a bound `List`. `havingValue="true"` does not make a `[0]` element satisfy a condition on the parent key; `matchIfMissing=true` only allows a **missing** key to still match and therefore certainly cannot express "non-empty list".

### 8.2. Relaxed binding and environment variables

Spring Boot supports multiple name formats when binding, but that does not mean every property source represents lists the same way. For object lists, Boot documentation describes the environment variable rule as:

```properties
my.service[0].other=abc
```

On operating systems supporting standard environment variable naming, the corresponding form is typically `MY_SERVICE_0_OTHER`. `Binder` recognizes this notation using source-specific rules; do not concatenate strings or guess which key a single `Environment#getProperty` call will see. Testing with the exact config format to be deployed is the best verification.

### 8.3. Lists from multiple property sources are not necessarily merged

For lists, Spring Boot defines configuration precedence rules: higher-priority configuration usually **replaces the entire list** from lower priority, rather than merging every element across profiles/files. A custom condition using `Binder` will evaluate the bound list according to that rule. Do not manually sum `[index]` entries across all sources to predict the outcome.

### 8.4. Discontinuous indices and wrong data types

The `[index]` notation uses indices to describe element positions; configuration with index gaps, object elements missing fields, or unconvertible values can lead to unexpected binding or even binding failures. Do not build an algorithm assuming "finding any `[n]` means the list is valid". Use contiguous configuration, correct data types, and dedicated tests for critical failure cases.

### 8.5. Conditions are evaluated at bean registration time

Like other conditions, `@ConditionalOnProperty`/`@Conditional` take effect when Spring processes configurations and registers bean definitions. Changing configuration at runtime does not automatically cause a previously skipped bean to be created immediately or an existing bean to be removed. When dynamic runtime toggling is needed, that requires a separate runtime design rather than relying solely on startup annotations.

## 9. Common Mistakes and How to Diagnose

1. **Seeing `@ConfigurationProperties` bind a list while `@ConditionalOnProperty` does not match.** They are two different mechanisms; check the actual key name: `list` versus `list[0]`.
2. **Using `havingValue="true"` on a list key.** The condition requires a scalar value equal to `true`, not checking "has elements".
3. **Using `matchIfMissing=true` to work around a missed list.** This changes logic to "enable even when key is missing", potentially creating the bean even with no data.
4. **Thinking `name={"items[0]", "items[1]"}` means either one.** In reality, all names must satisfy the condition; it does not express at least one element.
5. **Checking only `items[0]` and assuming the entire list is valid.** One existing key is insufficient to guarantee every object in the list has required fields or useful values.
6. **Using the condition while related configuration data is still missing.** Auto-configuration should be tested with the property source types supported by the application; if there is bean registration ordering or custom property sources, verify evaluation timing.
7. **Assuming output from a single YAML file is all the data.** Profiles, CLI, environment variables, and other property sources can alter values and precedence.

To investigate:

- Enable `--debug` when running the Spring Boot application to view the condition evaluation report.
- If Actuator is already used and properly configured, inspect `/actuator/conditions`; check matched/unmatched conditions of the relevant auto-configuration.
- Create `ApplicationContextRunner` tests for at least: comma-separated parent key, `[0]` element, multiple `[0]/[1]` elements, missing config, blank data, and profiles/sources with different precedence if the system uses them.
- For complex binding, test binding into `List<T>` directly first, then test the bean-creation decision. Do not infer solely from the presence of a `PropertySource`.

## 10. Practical Conclusion

**The right question must be:** "Do I want to know whether a **key** is present, or whether the **bound list** has valid data?"

- When checking a **scalar property** (especially a boolean flag), `@ConditionalOnProperty` is appropriate and readable.
- When checking a **collection**, `@ConditionalOnProperty(name = "some-list")` may fail to match even when `some-list[0]` exists. The Spring Boot Javadoc recommends using a custom condition for this situation.
- `Binder` combined with business conditions can express "at least one element", "all elements valid", or complex rules over list structures.
- Do not turn `matchIfMissing`, `havingValue`, or a fixed index into a substitute for collection checks.
- You must test with actual configuration formats because YAML, `.properties`, environment variables, and property-source precedence can affect how keys appear.

### Official Documentation

- Spring Boot 3.3 `ConditionalOnProperty` Javadoc — explicitly notes limitations for collections: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 `Binder` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- Spring Boot 3.3 Reference — Externalized Configuration (YAML lists, binding, property-source precedence): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
