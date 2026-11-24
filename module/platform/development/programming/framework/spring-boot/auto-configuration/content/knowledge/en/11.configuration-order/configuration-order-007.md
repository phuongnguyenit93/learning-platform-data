# Referencing Optional Auto-Configurations by Name to Avoid Hard Dependencies

## Learning objectives

In Spring Boot, a library may need to run its auto-configuration **after** or **before** another integration library's auto-configuration. Yet that other library may be **optional**: not every application installs it. If you use `SomePartnerAutoConfiguration.class`, the source code must see that class at compile time. When you only need to describe **ordering**, you can reference the other class by its **fully qualified `String` name**.

This lesson explains exactly how to use `@AutoConfiguration(afterName = ...)`, `@AutoConfiguration(beforeName = ...)`, `@AutoConfigureAfter(name = ...)`, and `@AutoConfigureBefore(name = ...)`; how it behaves when the referenced configuration is absent; the limits of name-based references; and how to verify with Java 17+, Spring Boot 3.3, and `ApplicationContextRunner`.

After this lesson, you should distinguish **compile-time class dependencies**, **an auto-configuration's presence in the candidate list**, **bean definition registration order**, and **bean object creation order**.

## 1. The problem: an optional library where order still matters

Suppose an internal library provides a default `MessageService`, while a partner library **may** provide its own implementation. Goals:

1. If the partner's auto-configuration is included in the application and creates `MessageService`, process it first.
2. The internal auto-configuration registers its fallback only when no `MessageService` exists **yet**.
3. If the partner is completely absent from the classpath, the application still starts and the fallback still works.

One way that introduces a compile-time dependency:

~~~java
// Illustrative code; requires dependency to import the partner class.
import com.vendor.messaging.autoconfigure.PartnerMessageAutoConfiguration;

@AutoConfiguration(after = PartnerMessageAutoConfiguration.class)
class LocalMessageAutoConfiguration {
}
~~~

Even though this is merely an ordering annotation, the Java compiler still has to resolve `PartnerMessageAutoConfiguration.class`. If the internal library/starter does not want to add a dependency on the partner module, we can use the class name as a string:

~~~java
// No need to import or directly reference the partner class.
@AutoConfiguration(
    afterName = "com.vendor.messaging.autoconfigure.PartnerMessageAutoConfiguration"
)
class LocalMessageAutoConfiguration {
}
~~~

Both forms express the intent **LocalMessageAutoConfiguration is applied after PartnerMessageAutoConfiguration**. The difference is that `afterName` uses the fully qualified class name, so the ordering declaration itself does not require the partner class to be present at compile time.

**Important limitation:** a string name removes direct coupling only in **the ordering declaration**. If you still import the partner's APIs in fields, superclasses, method parameters, `@Bean` return types, or elsewhere, the library may still require the corresponding dependency. `afterName` does not automatically turn the entire integration into an optional one.

## 2. Primary API in Spring Boot 3.3

`@AutoConfiguration` resides in the `org.springframework.boot.autoconfigure` package and provides four ordering attributes:

| Attribute | Type | Meaning |
| --- | --- | --- |
| `after` | `Class<?>[]` | Apply the current auto-configuration **after** directly referenced classes |
| `afterName` | `String[]` | Apply **after** auto-configurations with the matching class names |
| `before` | `Class<?>[]` | Apply the current auto-configuration **before** directly referenced classes |
| `beforeName` | `String[]` | Apply **before** auto-configurations with the matching class names |

The name-based attributes are aliases for the dedicated annotations:

~~~java
// Two ways to express the same ordering requirement:
@AutoConfiguration(afterName = "com.vendor.OptionalAutoConfiguration")
class AfterUsingAutoConfiguration {
}

@AutoConfiguration
@AutoConfigureAfter(name = "com.vendor.OptionalAutoConfiguration")
class AfterUsingDedicatedAnnotation {
}
~~~

Corresponding forms for `beforeName`:

~~~java
@AutoConfiguration(beforeName = "com.vendor.OptionalAutoConfiguration")
class BeforeUsingAutoConfiguration {
}

@AutoConfiguration
@AutoConfigureBefore(name = "com.vendor.OptionalAutoConfiguration")
class BeforeUsingDedicatedAnnotation {
}
~~~

The snippets above only **illustrate annotation syntax** and require importing `AutoConfiguration`, `AutoConfigureAfter`, and `AutoConfigureBefore` in a real Java file. The name `com.vendor.OptionalAutoConfiguration` is an example, not a real class.

In Spring Boot 3.3, you can prefer `beforeName` and `afterName` directly on `@AutoConfiguration` because they read nicely alongside other conditions. `@AutoConfigureBefore(name=...)` and `@AutoConfigureAfter(name=...)` remain useful when reading or maintaining existing code.

### One string or multiple names?

Each `*Name` attribute has type `String[]`, so it can hold multiple names:

~~~java
@AutoConfiguration(afterName = {
    "com.vendor.alpha.AlphaAutoConfiguration",
    "com.vendor.beta.BetaAutoConfiguration"
})
class MyFallbackAutoConfiguration {
}
~~~

Meaning: if the referenced auto-configurations are **also in the selected set**, the current configuration is ordered after them. These are ordering constraints; **they are not a list of dependencies to install**.

## 3. What if the referenced configuration does not exist?

Spring Boot processes the list of **auto-configuration candidates** discovered and selected for the application context. Names in `afterName`/`beforeName` participate in sorting this list. They are **not** class-loading directives, not `@Import`, and do not cause the application to pull in extra dependencies.

| Status of `PartnerMessageAutoConfiguration` | Effect of `afterName` |
| --- | --- |
| Class **does not exist on the classpath** | No ordering constraint can be formed against that candidate; the string reference itself does not fail due to the missing class |
| Class is on the classpath, yet **not registered as an auto-configuration candidate** | There is no corresponding candidate to apply the constraint against |
| Partner auto-configuration is selected and processed | Current auto-configuration is ordered **after** the partner configuration |
| Partner auto-configuration is selected, yet its own conditions prevent its bean from being created | Order still applies; the current fallback can still register if `@ConditionalOnMissingBean` matches |
| Both are selected, yet the partner does not create a bean of the right type | Current configuration runs after, yet the missing-bean condition may still match |

It does not mean "the referenced partner configuration must be present." Nor does it mean "once the partner configuration is applied, it definitely creates a bean": it can still be blocked by `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, or other conditions.

**Note:** if **your own code** uses partner APIs in method signatures or directly instantiates partner classes, classpath errors can still occur. String names only reduce coupling for *the ordering relationship*; they do not automatically guard the entire runtime dependency path.

## 4. Production example: fallback must run after optional integration

Suppose there is a `MessageService` interface owned by your library and two auto-configurations capable of providing a bean of that type. Your fallback configuration can be written as:

**File:** `src/main/java/example/messaging/autoconfigure/MessageFallbackAutoConfiguration.java`

~~~java
package example.messaging.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(
        afterName = "com.vendor.messaging.autoconfigure.PartnerMessageAutoConfiguration"
)
public class MessageFallbackAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageService.class)
    MessageService defaultMessageService() {
        return () -> "local-fallback";
    }

    public interface MessageService {
        String source();
    }
}
~~~

In this illustrative code:

- `afterName` describes relative **order**; it creates no objects.
- `@ConditionalOnMissingBean(MessageService.class)` decides **whether to register the fallback**, based on bean definitions Spring has already seen at evaluation time.
- If the partner is selected and has registered `MessageService`, the fallback configuration processed afterwards detects that bean and **does not** register `defaultMessageService`.
- If the partner is absent or does not register a bean of the right type, the fallback can be created.
- The fallback source code **does not import** the partner's auto-configuration class.

**Prerequisite:** for the two sides to interact in practice, the partner configuration must register a bean compatible with `MessageService` (or a shared interface known to both). Naming the partner in `afterName` does not make beans of unrelated types share a type.

In a real starter, place the shared interface in a dedicated API package; in this example, the interface is nested for concise presentation. The service type used for `@ConditionalOnMissingBean` must be the proper type that downstream consumers expect to use.

### Registering auto-configurations properly

Spring Boot 3.x discovers a library's auto-configurations from:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example content:

~~~text
example.messaging.autoconfigure.MessageFallbackAutoConfiguration
~~~

List only **auto-configurations actually provided by your library**. Do not add `com.vendor.messaging.autoconfigure.PartnerMessageAutoConfiguration` to your imports file merely because you want to order after it. If the partner integration is not present, attempting to register a nonexistent class can cause errors when Spring Boot processes candidates.

If the partner has its own starter, that starter is responsible for registering its own auto-configuration when used.

## 5. Why is ordering especially important with `@ConditionalOnMissingBean`?

Bean conditions are evaluated against **bean definitions already processed up to the current moment**. Therefore, two configurations providing the same bean type can produce different outcomes if registered in the wrong order.

For this example, the desired flow is:

~~~text
Is PartnerMessageAutoConfiguration selected?
    |
    +-- No ---> Process MessageFallbackAutoConfiguration
    |             -> No MessageService yet: register defaultMessageService
    |
    +-- Yes --> Process PartnerMessageAutoConfiguration first
                  |
                  +-- Registered MessageService
                  |     -> Fallback runs after, sees bean
                  |     -> DO NOT register defaultMessageService
                  |
                  +-- Did not register MessageService
                        -> Fallback runs after, bean still missing
                        -> Register defaultMessageService
~~~

**Important:** `afterName` does not "choose which bean gets injected." It affects **auto-configuration processing order**; `@ConditionalOnMissingBean` decides whether a fallback bean definition exists. Once multiple beans of the same type already exist, injection mechanisms like `@Primary` or `@Qualifier` are a separate concern.

### Bean definitions and bean objects are two different milestones

Suppose bean A is registered before bean B; that **does not** guarantee A's constructor runs before B's constructor. Bean creation order is determined by the dependency graph, `@DependsOn`, and Spring's lifecycle mechanisms.

Therefore:

- `afterName`/`beforeName`: used to determine **auto-configuration application sequence**.
- `@DependsOn`: used when you genuinely need to express **bean initialization relationships**, not as a replacement for auto-configuration ordering.
- `@AutoConfigureOrder`: hints at general order among auto-configurations; does not express "after optional class X" as clearly as `afterName`.
- `@ConditionalOnMissingBean`: checks bean presence by type/name at evaluation time; does not replace ordering constraints when two auto-configurations provide the same type.

## 6. Complete verification example with JUnit 5 and ApplicationContextRunner

This example simulates a partner auto-configuration that **may or may not be registered**, along with another configuration name **absent from the classpath**. When both auto-configurations are selected, Spring Boot must honor the `afterName` constraint and register the partner bean before the fallback bean.

**File:** `src/test/java/example/order/NameOnlyOrderingTest.java`

~~~java
package example.order;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class NameOnlyOrderingTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner();

    @Test
    void usesFallbackWhenPartnerAutoConfigurationIsNotSelected() {
        runner.withConfiguration(
                AutoConfigurations.of(FallbackAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasSingleBean(MessageService.class);
                assertThat(context.containsBean("fallbackMessageService")).isTrue();
                assertThat(context.getBean(MessageService.class).source())
                        .isEqualTo("fallback");
            });
    }

    @Test
    void partnerWinsWhenBothAutoConfigurationsAreSelected() {
        // Intentionally put Fallback before Partner in the list.
        // AutoConfigurations.of applies Boot's auto-configuration ordering.
        runner.withConfiguration(
                AutoConfigurations.of(
                        FallbackAutoConfiguration.class,
                        PartnerAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasSingleBean(MessageService.class);
                assertThat(context.containsBean("partnerMessageService")).isTrue();
                assertThat(context.containsBean("fallbackMessageService")).isFalse();
                assertThat(context.getBean(MessageService.class).source())
                        .isEqualTo("partner");
            });
    }

    @Test
    void userBeanAlsoPreventsFallback() {
        runner.withUserConfiguration(UserConfiguration.class)
            .withConfiguration(AutoConfigurations.of(FallbackAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasSingleBean(MessageService.class);
                assertThat(context.containsBean("userMessageService")).isTrue();
                assertThat(context.containsBean("fallbackMessageService")).isFalse();
            });
    }

    interface MessageService {
        String source();
    }

    @AutoConfiguration(afterName = {
        "example.order.NameOnlyOrderingTest$PartnerAutoConfiguration",
        "com.vendor.unavailable.NotInstalledAutoConfiguration"
    })
    static class FallbackAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(MessageService.class)
        MessageService fallbackMessageService() {
            return () -> "fallback";
        }
    }

    @AutoConfiguration
    static class PartnerAutoConfiguration {

        @Bean
        MessageService partnerMessageService() {
            return () -> "partner";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean
        MessageService userMessageService() {
            return () -> "user";
        }
    }
}
~~~

### Special explanation regarding nested class names

In the test file, `PartnerAutoConfiguration` is a **static nested class** inside `NameOnlyOrderingTest`. The exact binary name Spring Boot uses for ordering references is:

~~~text
example.order.NameOnlyOrderingTest$PartnerAutoConfiguration
~~~

The **`$`** sign, not a dot, separates the outer enclosing class from the inner nested class. This is also the convention documented in the official Javadoc of `afterName`/`beforeName`. In production code, prefer making auto-configurations **top-level classes**; their names typically look like `com.vendor.package.SomeAutoConfiguration`.

The string `com.vendor.unavailable.NotInstalledAutoConfiguration` in the test is a hypothetical name **with no corresponding dependency**. It demonstrates that an ordering constraint with no matching target does not prevent the fallback from working. The first test loads only fallback, the second loads both fallback and partner, and the third verifies that user beans are processed before auto-configurations.

### Dependencies and run commands

The test file uses Java 17+ and Spring Boot 3.3.x. With Gradle Groovy DSL, a project with the Spring Boot plugin or BOM-managed dependency versions can use:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run inside the module containing the test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.order.NameOnlyOrderingTest"

# Windows
gradlew.bat test --tests "example.order.NameOnlyOrderingTest"
~~~

**Expected result:** all three tests PASS. Test 1 yields `"fallback"`, test 2 yields `"partner"` with no fallback bean, and test 3 has no fallback bean because the user bean is already present. There is no `System.out.println`; the tests verify via assertions, so **there is no fixed content stdout** beyond Gradle/test-runner output.

This example tests **auto-configuration ordering and bean definitions** in a small context. It does not require installing a real partner library. When integrating a real partner, add dedicated tests against the partner artifact to catch package/class renames or changes in their bean registration conditions.

## 7. Relationship to classpath conditions: two distinct responsibilities

When a partner class is optional, sometimes besides ordering you must check that an **API/SDK** actually exists. In that case, use `@ConditionalOnClass`:

~~~java
@AutoConfiguration(
    afterName = "com.vendor.messaging.autoconfigure.PartnerMessageAutoConfiguration"
)
@ConditionalOnClass(name = "com.vendor.messaging.PartnerClient")
class PartnerBridgeAutoConfiguration {
    // Integration configuration written safely according to the actual classpath.
}
~~~

The snippet above illustrates annotations only. In production code, import `ConditionalOnClass` and organize `@Bean` methods whose return types or parameters belong to the optional SDK inside a **separate nested configuration** guarded by the classpath condition, since the JVM may load method signatures before method-level conditions are evaluated.

Do not confuse these three questions:

| Tool | What question does it answer? |
| --- | --- |
| `afterName` / `beforeName` | "If those auto-configurations are selected, which should we process first?" |
| `@ConditionalOnClass(name = "...")` | "Does the application's classpath contain this API/SDK type?" |
| `@ConditionalOnMissingBean(Service.class)` | "At evaluation time, does the context already have a bean matching this type?" |

Combine the right tools for the right purposes. **The name of an auto-configuration in `afterName` is not an SDK-presence condition**.

## 8. Limitations and common mistakes

1. **Using a simple class name instead of a fully qualified class name.** Writing `"PartnerAutoConfiguration"` will not match the real class `"com.vendor.autoconfigure.PartnerAutoConfiguration"`. Obtain the full class name from the partner's artifact/documentation.
2. **Confusing the SDK package with the auto-configuration package.** `com.vendor.api.Client` and `com.vendor.autoconfigure.ClientAutoConfiguration` are different classes. `afterName` needs the exact **auto-configuration** name, not the SDK client name.
3. **Assuming `afterName` enables or imports the partner configuration.** It only describes order if the partner is already a selected candidate. The partner must still be registered via the proper auto-configuration/imports mechanism.
4. **Assuming the partner class being on the classpath means the partner bean was created.** Its auto-configuration might not be selected or its conditions might not match. Check actual conditions and bean definitions.
5. **Directly referencing `OptionalAutoConfiguration.class` when wanting the module independent at compile time.** That requires the class on the compile classpath. `afterName="fully.qualified.Name"` avoids that coupling in the ordering declaration.
6. **Mixing dots and `$` for nested classes.** For nested configurations, the binary name uses `$`; a wrong name prevents the intended ordering from taking effect.
7. **Setting before/after opposite to the fallback's intent.** If `@ConditionalOnMissingBean` needs to see a bean registered by the partner, the fallback configuration normally uses `afterName`, not `beforeName`.
8. **Expecting the annotation to change constructor order.** Auto-configuration application order does not guarantee bean initialization order. When a real initialization relationship is needed, model it via dependencies and `@DependsOn` if appropriate.
9. **Hard-coding third-party class names without integration tests.** A partner upgrade may rename or move packages; when the string stops matching, the ordering constraint silently loses effect with no compile error warning.
10. **Putting `@ConditionalOnClass` on a `@Bean` method whose signature directly references a class absent from the classpath.** Isolate the integration into a class-level conditional configuration following Spring Boot guidance.

### If the partner renames its auto-configuration

FQCN strings are not checked by the compiler, so when a partner changes package or class names, an ordering constraint can stop working. For libraries you control, Spring Boot provides `AutoConfiguration.replacements` when relocating/renaming auto-configurations to preserve compatibility with older references and exclusions. For external libraries, verify release notes and add integration tests against the supported versions.

### Practical diagnostics

- Check whether the expected class is actually listed in the relevant artifact's `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- Check whether the auto-configuration was selected, or excluded by classpath/property/bean conditions or explicit exclusions.
- Enable `--debug` and read the **Condition Evaluation Report** to see which bean/class conditions matched or failed to match.
- When the issue is **ordering**, write an `ApplicationContextRunner` test containing both auto-configurations and verify bean definitions/fallback as shown above. The condition report does not always tell you why sorting occurred; testing both candidates gives more direct evidence.

## 9. Self-check

**Question 1.** Starter A declares `@AutoConfiguration(afterName="com.vendor.BAutoConfiguration")`, yet B is not installed at all. Must A fail due to not finding class B?

**Answer:** No; merely referencing B by string name in an ordering constraint does not force loading that class. A still needs classes/dependencies for any APIs A itself uses.

**Question 2.** B's artifact is installed, yet B's auto-configuration is not selected. Does `afterName` register B automatically?

**Answer:** No. The attribute only orders auto-configurations already selected as candidates.

**Question 3.** B is processed before A, yet B does not create a `MessageService` bean. Can A still register its fallback?

**Answer:** Yes. `@ConditionalOnMissingBean(MessageService.class)` relies on bean definitions actually present at evaluation time, not on whether B's name appears in `afterName`.

**Question 4.** Why did the test need `NameOnlyOrderingTest$PartnerAutoConfiguration` rather than `NameOnlyOrderingTest.PartnerAutoConfiguration`?

**Answer:** Because it is a **nested Java class**. The binary class name used in annotation metadata has `$` between the outer class and the nested class.

**Question 5.** Does `afterName` guarantee bean B's constructor runs before bean A's constructor?

**Answer:** No. It affects auto-configuration processing / bean definition order, while object instantiation depends on Spring's lifecycle and dependency graph.

## 10. Takeaways when applying

When an auto-configuration needs relative ordering with an **optional library**, prefer declaring it using the **fully qualified name of the auto-configuration**:

~~~java
@AutoConfiguration(afterName = "com.vendor.OptionalAutoConfiguration")
~~~

Use `beforeName` for the reverse direction. Do not add a dependency merely to reference `SomeAutoConfiguration.class` when the only information needed is its name for ordering. At the same time, if a bean should exist only when an SDK class is present, check the classpath separately; if you want a fallback to yield to an already-registered bean, use `@ConditionalOnMissingBean` and verify **when the partner configuration is absent, when it is present, and when a user bean already exists**.

### Official documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — `@AutoConfiguration` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 — `@AutoConfigureAfter` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html)
- [Spring Boot 3.3 — `@AutoConfigureBefore` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html)
