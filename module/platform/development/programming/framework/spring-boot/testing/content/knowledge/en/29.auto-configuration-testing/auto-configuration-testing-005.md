# @ConditionalOnClass, @ConditionalOnProperty, and @ConditionalOnMissingBean

## 1. Goal of this lesson: proving auto-configuration turns on/off under the right conditions

In the **Spring Boot - testing** module, under **Auto-Configuration Testing**, whether a bean is present in `ApplicationContext` is rarely just because an application has a `@Configuration` class. Spring Boot typically registers default beans **conditionally** based on the classpath, configuration properties, and beans the user has already declared.

Three annotations to master:

- **`@ConditionalOnClass`**: matches only when one or more required classes **exist on the runtime classpath**.
- **`@ConditionalOnProperty`**: matches only when the property value in `Environment` satisfies the rule; `havingValue` and `matchIfMissing` govern edge cases.
- **`@ConditionalOnMissingBean`**: matches only when no bean satisfying the criteria (usually by type) exists among the processed bean definitions; its common purpose is **backing off in favor of user configuration**.

A practical auto-configuration usually wants:

~~~text
Is the optional library class present?
        |
        no -------> do not create default bean
        |
       yes
        |
Is the feature property allowed?
        |
        no -------> do not create default bean
        |
       yes
        |
Has the user declared a bean of the same type?
        |
       yes -------> use user's bean; default backs off
        |
        no
        |
        v
create default bean
~~~

A test that only checks "the context starts" must never be considered enough. You must test both **matched** and **not matched** for each condition, overlapping multi-condition cases, user overrides, missing classpath, and root causes in **ConditionEvaluationReport**.

This lesson uses **Java 17, Spring Boot 3.5.16, JUnit Jupiter, AssertJ, ApplicationContextRunner, and FilteredClassLoader**, featuring a runnable project with an `AutoConfiguration.imports` resource, property truth-table tests, optional library absence, custom bean back-off, and a `@SpringBootTest` smoke test confirming real auto-discovery.

## 2. Auto-configuration is not component scanning

`@AutoConfiguration` is a Spring `@Configuration` specialized for default configurations applied when a library/starter is added to an application. In Spring Boot 3.5, auto-configuration candidates are listed in the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line in this resource is a fully qualified class name, for example:

~~~text
com.example.formatter.autoconfigure.FormatterAutoConfiguration
~~~

In an application annotated with `@SpringBootApplication`, `@EnableAutoConfiguration` is enabled implicitly and Boot reads the candidate list. You do not need and **should not** `@ComponentScan` the package containing auto-configuration as a normal component, because doing so breaks auto-configuration load/order/condition semantics.

### Three configuration types to distinguish

| Type | Where declared | Purpose |
| --- | --- | --- |
| User `@Configuration` + `@Bean` | Application using the starter | Explicit choice of the application |
| `@AutoConfiguration` | Library/starter, listed in `AutoConfiguration.imports` | Supplies defaults when conditions hold |
| Test `@TestConfiguration` | Test source set | Creates helper beans/configurations for a test case |
| `ApplicationContextRunner` configuration | Inside JUnit, using `AutoConfigurations.of(...)` and `withUserConfiguration(...)` | Builds a minimal context for a condition matrix |

Auto-configuration **does not take precedence over user configuration**; in principle, the user can declare another implementation, and `@ConditionalOnMissingBean` lets the default bean **back off** when it sees a matching user bean.

**Ordering note:** bean conditions are evaluated against bean definitions already **processed up to that point**, not by scanning everything that *will* be registered in the future. Auto-configurations are processed after user-defined configurations along the standard path; if a bean from another auto-configuration is needed, consider `@AutoConfiguration(after=...)`/`@AutoConfigureAfter` and test ordering with the runner.

## 3. @ConditionalOnClass: the condition is class existence, not a bean

A library class may sit on the runtime classpath while **no bean** of that type exists in Spring. That is still a `@ConditionalOnClass` match. Conversely, a bean factory might create a bean some other way, yet if the optional class required by the condition cannot be loaded, the condition **does not match**.

~~~java
@ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
@Configuration(proxyBeanMethods = false)
class OptionalClientConfiguration {
    // Beans depending on the optional library live here.
}
~~~

The snippet above is only a skeleton: it excludes the vendor library, bean methods, or package/imports. Use `name` when representing the class name as a string and avoiding compile-time references. When placed directly on a `@Configuration` class, Boot can safely read `value = OptionalClient.class` via **ASM metadata** without loading the optional class.

### Crucial pitfall: placing the condition on a `@Bean` method returning an optional type

~~~java
// ANTI-EXAMPLE: the JVM may resolve the return type before
// the method-level condition can protect it.
@Bean
@ConditionalOnClass(OptionalClient.class)
OptionalClient optionalClient() {
    return new OptionalClient();
}
~~~

This is a non-standalone method, and `OptionalClient` is just a placeholder class for explanation. If the optional dependency **does not exist**, the JVM may inspect the method return type / signatures before Spring evaluates the condition, leading to `NoClassDefFoundError` or metadata/reflection errors.

**Correct approach:** extract a separate `static @Configuration` class, put `@ConditionalOnClass` at the **class level**, and put `@Bean` methods depending on the optional type inside:

~~~java
@AutoConfiguration
public class MyAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
    static class OptionalClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        OptionalClient optionalClient() {
            return new OptionalClient();
        }
    }
}
~~~

This is a conceptual syntax pattern; without `OptionalClient` and imports it is **not a runnable demo file**. In the demo below, `OptionalCodec` is created as a class simulating an optional library so `FilteredClassLoader` can remove it from the test classpath in a controlled way.

### value and name

- `@ConditionalOnClass(OptionalCodec.class)` fits when the class is on the **compile classpath**, and the annotation is placed **directly on a `@Configuration` class**.
- `@ConditionalOnClass(name="com.example.optionalcodec.OptionalCodec")` fits when only a string class name is available.
- When creating a **composed meta-annotation** containing `@ConditionalOnClass`, Boot documentation recommends `name`; the class-literal safety mechanism does not behave identically on meta-annotations.
- If **multiple classes** are required in the annotation, every listed class must exist.
- `@ConditionalOnClass` does not check method behavior or bean state, nor guarantee that an optional client can connect to an external server.

## 4. @ConditionalOnProperty: condition based on Environment

Example:

~~~java
@ConditionalOnProperty(
        prefix = "training.formatter",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
~~~

The full property key is `training.formatter.enabled`. The rule above:

- Property **does not exist** -> **matches** because `matchIfMissing=true`.
- `enabled=true` -> matches (string comparison per Boot semantics).
- `enabled=false` -> does not match.
- `enabled=no`, `enabled=maybe`, empty string -> do not match `havingValue="true"`.

**`matchIfMissing` only handles the case where the property is absent**; it does not treat empty values, `null` from an unusual configuration, or invalid values as missing.

### Official truth table

Assume the property **is present** in `Environment`:

| Property value | `havingValue=""` (default) | `havingValue="true"` | `havingValue="false"` | `havingValue="foo"` |
| --- | --- | --- | --- | --- |
| `"true"` | Match | Match | No | No |
| `"false"` | **No match** | No | Match | No |
| `"foo"` | Match | No | No | Match |
| `"no"` | Match | No | No | No |

If the property **is absent**, the outcome comes from `matchIfMissing`: defaults to `false` so **no match**, unless `matchIfMissing=true`. When `havingValue` is not set, the condition **does not require boolean true**: almost any string other than `"false"` matches. Many tests need to catch this.

Spring Boot 3.5 also offers `@ConditionalOnBooleanProperty` with boolean-specific semantics; do not swap it in casually without checking version and compatibility. This exercise focuses on `@ConditionalOnProperty` to illustrate the rules clearly.

### prefix, name, value, multiple keys, and unusual configs

- `prefix="training.formatter"` and `name="enabled"` combine into the complete key.
- Use lower-case/kebab-case notation when declaring key names; avoid ambiguity in docs.
- `value` is an alias for `name`; do not pass both with conflicting values.
- If `name={"enabled","ready"}` then **all** keys must pass.
- `@ConditionalOnProperty` reads `Environment` rather than calling setters on a `@ConfigurationProperties` object.
- It is **unsuitable for checking collections** like `items[0]` when property `items` is not defined directly; use a custom `Condition` when needed.
- Properties come from CLI, environment variables, profiles, or the test runner; **precedence** applies across configuration sources if multiple sources define the same key.

Use `havingValue="true"` for explicit feature flags to prevent enabling a feature when a property has a typo like `"maybe"`.

## 5. @ConditionalOnMissingBean: default backs off for user's bean

A common auto-configuration:

~~~java
@Bean
@ConditionalOnMissingBean(TextFormatter.class)
TextFormatter textFormatter() {
    return new DefaultTextFormatter();
}
~~~

This is an illustrative method; `DefaultTextFormatter` is not part of the runnable demo. If the context already contains a `TextFormatter` created by the user, this method **does not register the default**. If none exists, it can create the default (still subject to class/property conditions on the configuration class).

### By type or by name?

- `@ConditionalOnMissingBean(TextFormatter.class)` checks **type**; a user bean named `customFormatter` still makes the default back off.
- `@ConditionalOnMissingBean(name="textFormatter")` checks **bean name**, which has different semantics: an unrelated-type bean with that name can block the default; a same-type bean with another name will not.
- When placed on a `@Bean` method **without value/type/name/annotation**, Boot defaults to using **the method's return type** as the bean type to check.
- `search` controls whether parent application contexts are searched.
- `ignored`/`ignoredType` and `parameterizedContainer` are advanced attributes, used only when genuinely needed.
- Bean definitions that **are not autowire candidates / default candidates** can be skipped per Boot 3.5 semantics.

### Why is @Primary not enough?

`@Primary` helps select one bean when multiple candidates exist for autowiring. It **does not stop the default bean from being created**, and does not solve every injection by name, `getBeansOfType`, lifecycle side effects, or unintended conflicts. If a starter's goal is **not creating the default when the user provided a replacement**, `@ConditionalOnMissingBean` means something different from `@Primary`.

### Evaluation time matters more than method call order

`@ConditionalOnMissingBean` inspects definitions registered earlier, without waiting for bean instances to be constructed with `new`. A `@Lazy` bean whose definition already exists can still block the auto default. Do not test ordering by calling `getBean` inside constructor side effects; use `ApplicationContextRunner.withUserConfiguration` to test when the user bean exists.

If other auto-configurations also register the same type, explicit `after`/`before` ordering is needed. Bean conditions should be placed in actual **auto-configurations**, since regular user-defined `@Configuration` classes lack equivalent registration order guarantees.

## 6. Three conditions combined with AND logic

Main pattern of the lesson:

~~~java
@AutoConfiguration
class FormatterAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(OptionalCodec.class)
    @ConditionalOnProperty(
        prefix = "training.formatter",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    static class EnabledFormatterConfiguration {

        @Bean
        @ConditionalOnMissingBean(TextFormatter.class)
        TextFormatter textFormatter() {
            OptionalCodec codec = new OptionalCodec();
            return codec::format;
        }
    }
}
~~~

This is a **condensed skeleton** before the detailed runnable sample below (missing package/imports). Conditions in the same scope combine with **AND**: the optional class must exist, the feature must be enabled/missing per policy, and no `TextFormatter` of the same type exists yet to create the default bean.

A user-defined `TextFormatter` bean can still exist **even when the flag is off or the optional class is absent**, because the conditions govern only the **auto default**, and never delete user-declared beans.

### Expected behavior matrix

| Class `OptionalCodec` | Property | User `TextFormatter` | Result in context |
| --- | --- | --- | --- |
| Present | Missing | No | Default `TextFormatter` |
| Present | `true` | No | Default |
| Present | `false` | No | No `TextFormatter` |
| Present | `foo` | No | No default |
| Present | Missing | Yes | **User bean**, no default |
| Present | `false` | Yes | User bean still present |
| Absent | Missing | No | No default |
| Absent | Missing | Yes | User bean still present |
| Absent | `true` | No | No default |

This test matrix is far more reliable than a single `@SpringBootTest`: it isolates individual branches and combinations, pinpointing bugs when auto-config code changes.

## 7. Why is ApplicationContextRunner better suited than @SpringBootTest for a condition matrix?

Spring Boot includes `ApplicationContextRunner` in `spring-boot-test`. Each `run(...)` creates a context **dedicated to that scenario**, allowing configuration:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                    AutoConfigurations.of(FormatterAutoConfiguration.class)
                );
~~~

- `withConfiguration(AutoConfigurations.of(...))` passes just the auto-config under test into the runner, without booting the entire application.
- `withPropertyValues("training.formatter.enabled=false")` creates an isolated feature flag scenario.
- `withUserConfiguration(UserFormatterConfiguration.class)` registers a user bean **before** auto-config to test back-off.
- `withClassLoader(new FilteredClassLoader(OptionalCodec.class))` simulates **a class absent from the runtime classpath**.
- `run(context -> {...})` receives an `AssertableApplicationContext`, using AssertJ to verify bean count/type/value; the context is closed by the runner after the callback.
- `withInitializer(ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))` helps debug condition reasons.

**No need for `@SpringBootTest` on every method.** When a test only verifies bean definitions and properties, a minimal context runs quickly, isolates cleanly, and avoids interference from unrelated auto-configurations.

`ApplicationContextRunner` **does not support testing native image runtimes** per Spring Boot documentation; Native/AOT smoke tests need a native-compatible approach. When servlet/reactive context conditions apply, use `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner` accordingly.

### Runner tests still need an autoload smoke test

The runner manually injects auto-config via `AutoConfigurations.of`, so it does not prove the jar declared the **right `AutoConfiguration.imports` resource**. We will add a `@SpringBootTest` with an application in a different package to verify Spring Boot actually auto-loads the candidate from the resource.

## 8. Project structure: Java 17 + Spring Boot 3.5.16

Runnable example with Gradle Wrapper:

~~~text
settings.gradle
build.gradle

src/main/java/com/example/app/
    FormatterDemoApplication.java

src/main/java/com/example/formatter/api/
    TextFormatter.java

src/main/java/com/example/optionalcodec/
    OptionalCodec.java

src/main/java/com/example/formatter/autoconfigure/
    FormatterAutoConfiguration.java

src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports

src/test/java/com/example/formatter/autoconfigure/
    FormatterAutoConfigurationTests.java

src/test/java/com/example/app/
    FormatterApplicationSmokeTests.java
~~~

Packages are intentionally separated: `com.example.app` is the demo application's component-scan region, while auto-configuration in `com.example.formatter.autoconfigure` is discovered by Spring Boot via `AutoConfiguration.imports`, **not by component scanning**.

`OptionalCodec` is currently compiled **in the same project** so the demo runs without extra Maven modules. In a real starter, it would reside in an external **optional dependency**; `FilteredClassLoader` simulates that dependency being omitted from the runtime classpath.

### settings.gradle

~~~groovy
rootProject.name = 'conditional-auto-configuration-demo'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` supplies `ApplicationContextRunner`, `FilteredClassLoader`, JUnit Jupiter, and AssertJ. No HTTP server, database, Docker, Redis, or Kafka needed to test bean conditions. `Spring Boot 3.5.16` is pinned to avoid confusing imports/mechanisms with Boot 4.x while learning.

**Note:** Building may require repository/network access to fetch dependencies and a configured Gradle Wrapper. The code has been checked for APIs and logic, though actual test execution results are confirmed only after running the suite.

## 9. Demo application: component scan does not touch auto-config

**`src/main/java/com/example/app/FormatterDemoApplication.java`:**

~~~java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormatterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormatterDemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` is in package `com.example.app`; by default component scanning sees only this package and its subpackages. `com.example.formatter.autoconfigure.FormatterAutoConfiguration` in a **sibling** package is not scanned.

If `AutoConfiguration.imports` is forgotten, `FormatterDemoApplication` will **have no default formatter bean**, and the smoke test at the end of the lesson FAILS; meanwhile runner tests directly specifying the auto-config could still PASS. That is why both test layers are necessary.

## 10. Public interface and optional class

**`src/main/java/com/example/formatter/api/TextFormatter.java`:**

~~~java
package com.example.formatter.api;

@FunctionalInterface
public interface TextFormatter {
    String format(String input);
}
~~~

**`src/main/java/com/example/optionalcodec/OptionalCodec.java`:**

~~~java
package com.example.optionalcodec;

import java.util.Locale;
import java.util.Objects;

public final class OptionalCodec {

    public String format(String input) {
        Objects.requireNonNull(input, "input");
        return "CODEC:" + input.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

`OptionalCodec` is **a class simulating an external library API**. It is not a Spring bean; the class's presence on the classpath is **enough** for `@ConditionalOnClass` to match. At the same time, creating the `TextFormatter` bean also depends on the property and other user beans.

The `format` method is intentionally designed to yield deterministic output, for example:

~~~text
new OptionalCodec().format(" hello ") -> "CODEC:HELLO"
new OptionalCodec().format("  mixed case  ") -> "CODEC:MIXED CASE"
~~~

This is output deduced from the source code, **not executed stdout**. Never call `System.out.println` in production code.

Using `Locale.ROOT` for technical normalization ensures results never vary with CI's `Locale.getDefault()`; auto-configuration tests focus on bean conditions without locale noise.

## 11. Complete auto-configuration and three conditions

**`src/main/java/com/example/formatter/autoconfigure/FormatterAutoConfiguration.java`:**

~~~java
package com.example.formatter.autoconfigure;

import com.example.formatter.api.TextFormatter;
import com.example.optionalcodec.OptionalCodec;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class FormatterAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(OptionalCodec.class)
    @ConditionalOnProperty(
            prefix = "training.formatter",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    static class OptionalCodecFormatterConfiguration {

        @Bean
        @ConditionalOnMissingBean(TextFormatter.class)
        TextFormatter textFormatter() {
            OptionalCodec codec = new OptionalCodec();
            return codec::format;
        }
    }
}
~~~

**How each layer operates:**

1. `@AutoConfiguration` is the candidate imported by Boot via the metadata file.
2. `@Configuration(proxyBeanMethods=false)` is a nested configuration isolating the `OptionalCodec` dependency scope.
3. `@ConditionalOnClass(OptionalCodec.class)` guards **the entire nested configuration** before the parser processes `@Bean` methods inside.
4. `@ConditionalOnProperty(...havingValue="true",matchIfMissing=true)` enables the default feature when the property is true **or undeclared**, blocking false/invalid.
5. `@ConditionalOnMissingBean(TextFormatter.class)` backs off for user-defined beans implementing the same interface.
6. Returning `TextFormatter` from the `@Bean` method supports interface-based injection; `OptionalCodec` is instantiated with `new` only when the configuration actually matches.

**Do not** return the optional type directly from a method in an unprotected top-level configuration. Do not put conditions on component-scanned beans and assume auto-config ordering like Spring Boot's candidate pipeline.

### If you want default off

Change `matchIfMissing=false` in the auto-config code and update the default tests. That is a **product contract change**: a missing property will no longer create the bean. Do not edit the annotation while keeping a `missingPropertyUsesDefault...` test expecting PASS.

## 12. Registering the candidate via AutoConfiguration.imports

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:**

~~~text
com.example.formatter.autoconfigure.FormatterAutoConfiguration
~~~

This file:

- Has the exact standard path and resource name for Spring Boot 3.5.
- Contains one **fully-qualified class name** per line, not bean names.
- Does not need and does not use the legacy `spring.factories` file to register auto-configs in Boot 3.5.
- Can contain comments starting with `#`, though avoid typos or moved classes left un-updated.
- Must live in the **published jar** of the starter/auto-config module, not only in test resources.
- Must not be replaced by `@ComponentScan` or regular `@Import` and claimed as tested auto-discovery.

The runner tests below bring the auto-config into context explicitly, whereas the `@SpringBootTest` smoke test needs this file to automatically discover the default bean.

When publishing a standalone starter, it is common to separate the `autoconfigure` module from the `starter` convenience dependency module, marking optional dependencies appropriately so client applications are not forced to pull every optional library.

## 13. ApplicationContextRunner tests — complete code

**`src/test/java/com/example/formatter/autoconfigure/FormatterAutoConfigurationTests.java`:**

~~~java
package com.example.formatter.autoconfigure;

import com.example.formatter.api.TextFormatter;
import com.example.optionalcodec.OptionalCodec;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FormatterAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    FormatterAutoConfiguration.class
                            )
                    );

    @Test
    void missingPropertyUsesDefaultBecauseMatchIfMissingIsTrue() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(TextFormatter.class);
            assertThat(context.getBean(TextFormatter.class)
                    .format(" hello ")).isEqualTo("CODEC:HELLO");
        });
    }

    @Test
    void explicitTrueCreatesDefaultBean() {
        runner.withPropertyValues(
                "training.formatter.enabled=true"
        ).run(context -> {
            assertThat(context).hasSingleBean(TextFormatter.class);
            assertThat(context.getBean(TextFormatter.class)
                    .format("demo")).isEqualTo("CODEC:DEMO");
        });
    }

    @Test
    void trueValueMatchIsCaseInsensitive() {
        runner.withPropertyValues(
                "training.formatter.enabled=TRUE"
        ).run(context -> {
            assertThat(context).hasSingleBean(TextFormatter.class);
        });
    }

    @Test
    void falseFlagRemovesOnlyTheAutoDefaultBean() {
        runner.withPropertyValues(
                "training.formatter.enabled=false"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(TextFormatter.class);
        });
    }

    @Test
    void invalidValueDoesNotAccidentallyEnableFeature() {
        runner.withPropertyValues(
                "training.formatter.enabled=maybe"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(TextFormatter.class);
        });
    }

    @Test
    void presentButEmptyValueIsNotTheSameAsMissingProperty() {
        runner.withPropertyValues(
                "training.formatter.enabled="
        ).run(context -> {
            assertThat(context).doesNotHaveBean(TextFormatter.class);
        });
    }

    @Test
    void userProvidedFormatterMakesAutoDefaultBackOff() {
        runner.withUserConfiguration(UserFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(TextFormatter.class);

                    TextFormatter formatter =
                            context.getBean(TextFormatter.class);
                    assertThat(formatter.format("abc"))
                            .isEqualTo("USER:abc");

                    assertThat(context)
                            .doesNotHaveBean("textFormatter");
                    assertThat(context.getBean("customFormatter"))
                            .isSameAs(formatter);
                });
    }

    @Test
    void userBeanStillExistsEvenWhenAutoFlagIsFalse() {
        runner.withUserConfiguration(UserFormatterConfig.class)
                .withPropertyValues(
                        "training.formatter.enabled=false"
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(TextFormatter.class);
                    assertThat(context.getBean(TextFormatter.class)
                            .format("abc")).isEqualTo("USER:abc");
                });
    }

    @Test
    void unrelatedBeanDoesNotCauseFormatterToBackOff() {
        runner.withUserConfiguration(UnrelatedConfig.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(TextFormatter.class);
                    assertThat(context).hasSingleBean(OtherService.class);
                    assertThat(context.getBean(TextFormatter.class)
                            .format(" hi ")).isEqualTo("CODEC:HI");
                });
    }

    @Test
    void missingOptionalClassMeansNoAutoFormatter() {
        runner.withClassLoader(
                new FilteredClassLoader(OptionalCodec.class)
        ).run(context -> {
            assertThat(context).doesNotHaveBean(TextFormatter.class);
            assertThat(context).doesNotHaveBean("textFormatter");
        });
    }

    @Test
    void userFormatterDoesNotDependOnOptionalCodec() {
        runner.withUserConfiguration(UserFormatterConfig.class)
                .withClassLoader(
                        new FilteredClassLoader(OptionalCodec.class)
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(TextFormatter.class);
                    assertThat(context.getBean(TextFormatter.class)
                            .format("abc")).isEqualTo("USER:abc");
                });
    }

    @Test
    void absentPropertyDoesNotMatchWhenMatchIfMissingIsDefault() {
        new ApplicationContextRunner()
                .withUserConfiguration(StrictPropertyConfig.class)
                .run(context -> {
                    assertThat(context.containsBean("strictSignal"))
                            .isFalse();
                });
    }

    @Test
    void defaultHavingValueMatchesNonFalseStrings() {
        new ApplicationContextRunner()
                .withUserConfiguration(StrictPropertyConfig.class)
                .withPropertyValues("training.strict.enabled=yes")
                .run(context -> {
                    assertThat(context.containsBean("strictSignal"))
                            .isTrue();
                    assertThat(context.getBean("strictSignal"))
                            .isEqualTo("STRICT");
                });
    }

    @Test
    void defaultHavingValueRejectsStringFalse() {
        new ApplicationContextRunner()
                .withUserConfiguration(StrictPropertyConfig.class)
                .withPropertyValues("training.strict.enabled=false")
                .run(context -> {
                    assertThat(context.containsBean("strictSignal"))
                            .isFalse();
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFormatterConfig {
        @Bean("customFormatter")
        TextFormatter myFormatter() {
            return value -> "USER:" + value.strip();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UnrelatedConfig {
        @Bean
        OtherService otherService() {
            return new OtherService();
        }
    }

    static class OtherService {
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "training.strict",
            name = "enabled"
    )
    static class StrictPropertyConfig {
        @Bean
        String strictSignal() {
            return "STRICT";
        }
    }
}
~~~

**14 JUnit test methods** in the runner class, split into two groups: 11 cases testing the three conditions of `FormatterAutoConfiguration` and 3 cases testing **default** `@ConditionalOnProperty` semantics using `StrictPropertyConfig`.

### Why write StrictPropertyConfig separately?

The main auto-config uses `havingValue="true", matchIfMissing=true`. If you test only that, it is easy to mistakenly think every `@ConditionalOnProperty` defaults to "true only" or enabled when missing. The last three tests prove:

- Missing key -> no match (default `matchIfMissing=false`).
- Present `"yes"` -> matches with default `havingValue=""` because it is not `false`.
- Present `"false"` -> no match.

`StrictPropertyConfig` is a test configuration living in the test class, not registered as an auto-config candidate in `AutoConfiguration.imports`. It is loaded only when a specific runner calls `withUserConfiguration(StrictPropertyConfig.class)`.

### Why use FilteredClassLoader?

In the demo project, `OptionalCodec` always exists on the regular test classpath. `FilteredClassLoader(OptionalCodec.class)` simulates the user **lacking the optional library** at application runtime. Thanks to the nested `@Configuration` and class-level `@ConditionalOnClass`, the context avoids instantiating the default bean depending on `OptionalCodec` and starts cleanly.

There is no reason for tests to remove dependencies from `build.gradle` and rebuild between methods; `FilteredClassLoader` accurately simulates classpath variants without creating multiple Gradle modules.

### Why not use @MockBean to replace the user bean?

`@MockitoBean`/`@MockBean` primarily serve mock injection in `@SpringBootTest`. For auto-config tests, the goal is **an actual user-registered bean definition**, so `withUserConfiguration` and a simple `@Bean TextFormatter` express back-off more clearly, avoid slowing context caching, and need no Mockito interaction verification.

## 14. Full Spring Boot smoke test: testing the imports file and autoload

**`src/test/java/com/example/app/FormatterApplicationSmokeTests.java`:**

~~~java
package com.example.app;

import com.example.formatter.api.TextFormatter;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = FormatterDemoApplication.class,
        properties = "training.formatter.enabled=true"
)
class FormatterApplicationSmokeTests {

    @Autowired
    TextFormatter formatter;

    @Test
    void applicationAutoDiscoversFormatterFromImportsResource() {
        assertThat(formatter.format(" hello "))
                .isEqualTo("CODEC:HELLO");
    }
}
~~~

When `AutoConfiguration.imports` is valid, Boot loads `FormatterAutoConfiguration`; `OptionalCodec` is on the classpath, the flag is true, and there is no user `TextFormatter`, so the default bean is created. The test autowires `TextFormatter` and checks the result.

If you **run only `ApplicationContextRunner` tests**, a wrong or missing imports resource may go unnoticed because the runner specified the auto-config class directly. The smoke test closes that gap.

This is **1 more JUnit test method**; **15 JUnit cases** total across two test classes, covering both the **condition matrix** and the **real auto-configuration discovery path**. There is no network I/O, JDBC, or Kafka in the sample.

## 15. Guide to reading the QA matrix from test results

| Scenario | Test | Expected |
| --- | --- | --- |
| Optional class present; flag missing; no user bean | `missingPropertyUsesDefaultBecauseMatchIfMissingIsTrue` | 1 default bean |
| Flag true | `explicitTrueCreatesDefaultBean` | Default works |
| Flag TRUE | `trueValueMatchIsCaseInsensitive` | Match |
| Flag false | `falseFlagRemovesOnlyTheAutoDefaultBean` | No formatter |
| Flag maybe | `invalidValueDoesNotAccidentallyEnableFeature` | No formatter |
| Key present with empty value | `presentButEmptyValueIsNotTheSameAsMissingProperty` | No formatter |
| Differently named user bean | `userProvidedFormatterMakesAutoDefaultBackOff` | 1 user formatter, no default |
| Flag off + user bean | `userBeanStillExistsEvenWhenAutoFlagIsFalse` | User bean still present |
| Unrelated bean | `unrelatedBeanDoesNotCauseFormatterToBackOff` | Default still created |
| OptionalCodec filtered out | `missingOptionalClassMeansNoAutoFormatter` | No formatter |
| OptionalCodec filtered + user bean | `userFormatterDoesNotDependOnOptionalCodec` | User bean still present |
| Missing property with default matchIfMissing | `absentPropertyDoesNotMatchWhenMatchIfMissingIsDefault` | No strictSignal |
| Property yes with default havingValue | `defaultHavingValueMatchesNonFalseStrings` | strictSignal present |
| Property false with default havingValue | `defaultHavingValueRejectsStringFalse` | strictSignal absent |
| Full Spring Boot auto-discovery | `applicationAutoDiscoversFormatterFromImportsResource` | Formatter present and formats properly |

**This is expected behavior based on APIs and source code**; not Gradle/JUnit results already executed on a specific machine.

### Why is testing negative cases important?

A serious auto-config bug can cause a default bean to appear **when the optional class does not exist** or when the feature is disabled, causing `NoClassDefFoundError`, bean ambiguity, or unintended connections. Testing only the positive path will not catch this.

At the same time, a matching condition **does not guarantee the bean works properly**: it only verifies configuration wiring. A smoke test formatting a string connects conditional definition with minimal service behavior.

## 16. ConditionEvaluationReport to diagnose positive/negative matches

When a bean is absent, you often need to answer **"which condition did not match?"** instead of guessing which property/bean is loaded.

Spring Boot provides `ConditionEvaluationReport` and `ConditionEvaluationReportLoggingListener`. With `ApplicationContextRunner`, you can attach the initializer:

~~~java
ApplicationContextRunner debugRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                FormatterAutoConfiguration.class
                        )
                )
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO)
                );

debugRunner.withPropertyValues(
        "training.formatter.enabled=false"
).run(context -> {
    assertThat(context).doesNotHaveBean(TextFormatter.class);
});
~~~

This is an **illustrative snippet outside the main runnable project**; it requires imports:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

It feeds the report to the logger, which does not necessarily display in the JUnit console unless the logging level or test runner capture permits it. Tests **should not assert raw text logs** because messages/formatting can change across minor versions. You can inspect `ConditionEvaluationReport` programmatically or enable Boot debug when needed.

In a real Spring Boot application, the `--debug` flag prints the condition evaluation report at startup; Spring Boot Actuator's `conditions` endpoint is also useful if Actuator is added/enabled and properly secured. Do not expose internal conditions/configs/secrets publicly just for test debugging.

### Using the report to pinpoint the exact branch

- `OnClassCondition`: missing `OptionalCodec` or a transitive dependency.
- `OnPropertyCondition`: key missing/false/maybe, or unexpected property source precedence.
- `OnBeanCondition`: user bean `TextFormatter` already registered, so default backs off.
- Bean condition matched yet context startup FAILS: could be an exception in the `@Bean` method or another dependency, not a false condition.

**A negative test should assert both no bean and successful context startup.** If a `NoClassDefFoundError` prevents the context from starting, the test must FAIL rather than implicitly treating "no bean" as correct.

## 17. Bean definition processing order and other auto-configurations

`@ConditionalOnMissingBean` is a **snapshot of known definitions** at the moment the condition is evaluated. If auto-config A creates `Service` and auto-config B also wants to create `Service` when missing, candidate order can decide which bean gets created.

You can specify:

~~~java
@AutoConfiguration(after = OtherAutoConfiguration.class)
public class MyAutoConfiguration {
    // @ConditionalOnMissingBean on @Bean method.
}
~~~

This is a skeleton, not part of the runnable project; `OtherAutoConfiguration` must exist. For independent auto-config libraries you can use `afterName` with a full class name string to reduce compile dependencies. The order of **bean definition registration** differs from **bean instance initialization**; `@DependsOn` resolves initialization order, not the condition order of auto-config classes.

### When a user bean returns an overly broad interface

For example, the user writes:

~~~java
@Bean
Object myFormatter() {
    return (TextFormatter) value -> value;
}
~~~

This snippet is an illustrative counter-example. Condition evaluation sees only the type metadata available at registration time. When a `@Bean` method returns `Object`, the framework may fail to deduce that it actually creates a `TextFormatter`, causing the default bean to register anyway and create ambiguity or unexpected overrides.

**Declare the most accurate return type possible**, at least the `TextFormatter` interface or appropriate concrete type. With `@ConditionalOnMissingBean` on bean factories, the type published in the method signature is a crucial part of the contract.

## 18. @ConditionalOnClass when an optional library has an incompatible version

`@ConditionalOnClass` only checks class presence by name; it **does not verify API binary compatibility or method contracts**. If the class exists in a version lacking the called method, bean creation can fail with `NoSuchMethodError`. If the class exists while a transitive dependency is absent, you may hit linkage errors.

Therefore in a real starter you should:

1. Manage compatible dependency versions via BOM/constraints.
2. Test a classpath matrix with **library present** and **library absent**.
3. If supporting multiple major versions, add integration tests for binary compatibility.
4. Never use `@ConditionalOnClass` to guess whether an external service is reachable.
5. Avoid returning optional class types from bean methods inside unguarded configurations.
6. When differentiating classpaths, use `FilteredClassLoader` or dependency variants in CI instead of arbitrarily mutating jar classpaths inside the same JVM runtime.

A class being present while no bean exists is normal; clearly distinguish `@ConditionalOnClass` from `@ConditionalOnBean`. If a dependency bean must exist first, use bean conditions with proper ordering rather than forcing a class condition to carry that meaning.

## 19. @ConditionalOnProperty and Spring Profiles

Properties come from `Environment`, and may vary across `application.properties`, YAML, profile-specific configs, environment variables, command-line args, or inline test properties.

Example:

~~~properties
# application.properties
training.formatter.enabled=true
~~~

And in a test:

~~~java
runner.withPropertyValues(
        "training.formatter.enabled=false"
).run(context -> {
    assertThat(context).doesNotHaveBean(TextFormatter.class);
});
~~~

In `ApplicationContextRunner`, `withPropertyValues` creates property sources solely for that scenario rather than editing system properties for the entire JVM. This is far better than `System.setProperty(...)` in parallel tests.

### Relaxed binding is not an excuse to write arbitrary keys

Spring Boot has property binding rules, yet do not assume every hyphen/underscore/case variant is interpreted identically by `@ConditionalOnProperty` and `@ConfigurationProperties` in every environment. Declare the full canonical key in annotations, use kebab-case names, and test against the actual property sources in use. If using environment variables, verify concrete integration behavior.

### Default-on or default-off flag?

- `matchIfMissing=true` suits a default feature designed to be **enabled** when the user configures nothing.
- `matchIfMissing=false` is safer when a feature should enable only via explicit opt-in, such as an integration with significant cost or side effects.
- `havingValue="true"` avoids accepting odd strings like `maybe` as true under default semantics.
- When a property has multiple enum values, use `havingValue="foo"` or a custom condition with explicit validation; do not assume all text is boolean.

The demo code chose **default ON** to illustrate `matchIfMissing`, though production architecture may require **default OFF** depending on the feature.

## 20. @ConditionalOnMissingBean, @Primary, and overriding in Spring Boot 3.5

A user wants to replace the formatter:

~~~java
@Configuration(proxyBeanMethods = false)
class MyFormatterConfiguration {
    @Bean
    TextFormatter customFormatter() {
        return value -> "CUSTOM:" + value;
    }
}
~~~

This is a snippet that can live in an application, requiring imports and a package. When Spring Boot loads user config before auto-config, `@ConditionalOnMissingBean(TextFormatter.class)` does not create the default formatter.

Differences:

| Mechanism | Creates default bean? | Main purpose |
| --- | --- | --- |
| `@ConditionalOnMissingBean` on auto bean | No when a matching candidate exists | Back-off extension point |
| `@Primary` on user bean | Default may still exist | Resolves autowiring across multiple candidates |
| `spring.main.allow-bean-definition-overriding=true` | Allows overriding same-named definitions in some cases | Does not replace back-off design |
| `@ConditionalOnProperty` false | Does not create default within conditioned scope | Feature flag/conditional module |

Enabling bean definition overriding to mask a flawed auto-config can blind tests to duplicate configurations, and fails to guarantee that a differently named bean of the same type works as intended. Instead, fix `@ConditionalOnMissingBean` and write user-override tests.

### With @MockBean/@MockitoBean in tests

Bean overrides can affect `@ConditionalOnMissingBean` outcomes and context cache keys. If a lesson's goal is verifying whether auto-defaults back off, using a **real user `@Bean`** like `withUserConfiguration` is clearer. Use mocks when genuinely testing interactions between components; do not turn condition logic into a Mockito interaction test that skips bean definition checks.

## 21. Placing @Conditional on the class vs @Bean method?

| Location | Effect | When to use |
| --- | --- | --- |
| `@ConditionalOnClass` on auto-config/nested `@Configuration` | Can exclude entire config before method types are inspected | **Preferred for optional dependencies** |
| `@ConditionalOnProperty` on `@Configuration` | Registers none of the configuration's beans when flag fails | Group of beans sharing a feature |
| `@ConditionalOnProperty` on a `@Bean` | Blocks only that bean method | Single-bean feature scope |
| `@ConditionalOnMissingBean` on a `@Bean` | Blocks specific default if candidate bean exists | **Bean-specific user override** |
| `@ConditionalOnMissingBean` on auto-config class | Blocks whole config when condition fails | When all beans in config depend on the same absence |

In the sample, class-level and bean-method conditions cooperate intentionally:

~~~text
Nested configuration:
  OnClass OptionalCodec
  AND OnProperty training.formatter.enabled true/missing
      |
      v
@Bean textFormatter:
  OnMissingBean TextFormatter
      |
      v
register formatter
~~~

Do not put `@ConditionalOnMissingBean(TextFormatter.class)` on the entire auto-config if the auto-config also declares other beans still needed when the user overrides the formatter. Annotation placement should match the exact scope of what you intend to disable.

## 22. Why is ApplicationContextRunner fast, yet not enough for every test?

`ApplicationContextRunner` focuses on one configuration with a small set of beans instead of booting the entire application. Therefore:

- Great for running **matrices of properties/classpath/user beans**.
- Should not be used to claim JPA schemas, HTTP routes, Kafka brokers, Redis connections, or production Actuator endpoints work.
- Does not by itself prove an `AutoConfiguration.imports` resource is right (we added a smoke test for that).
- When running multiple interacting auto-config classes, pass them into `AutoConfigurations.of(A.class, B.class)` to use real ordering.
- If an auto-config is web-only, use `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner` accordingly.
- For native images, `ApplicationContextRunner` is unsupported per docs; add smoke/AOT tests.

### Context closes after the runner callback

A runner callback should only assert and never leak `ApplicationContext` outward for use after the callback finishes. Context resources/beans are closed after the run. Do not store a singleton or random port in a static field expecting the runner to manage lifecycles outside the context.

### Testing context errors

When intentionally configuring a missing dependency where the context **must fail**, assert `context.getStartupFailure()` (rather than swallowing exceptions). However, with an absent optional library under `@ConditionalOnClass`, **the expectation is that the context starts cleanly and the default bean is absent**, not a test claiming "allowed to fail on startup".

## 23. Common mistakes and fixes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Bean still appears when property is `false` | Condition in wrong scope or wrong key | Check annotation/key, test negative case |
| Flag `maybe` accidentally enables | Missing `havingValue="true"` | Use explicit havingValue |
| Missing property still creates bean | Intentional `matchIfMissing=true` | Clarify default-on contract, change if unwanted |
| Missing property prevents bean creation | Default `matchIfMissing=false` | Set true if default-on |
| Optional class absent yet context fails linkage | Method return type depends on unguarded optional class | Extract nested configuration with class-level condition |
| Optional class present yet no bean | Class condition only checks classpath; other bean/property conditions exist | Check ConditionEvaluationReport |
| User creates differently named bean yet default still created | Condition checks **name** instead of type | Use `@ConditionalOnMissingBean(TargetType.class)` |
| User bean return type is `Object` | Type metadata lacking; default may register | Declare exact return type |
| User bean declared yet default still created | Wrong auto-config order / condition placed in user config | Ensure user config first, proper auto-config ordering |
| `@Primary` user bean still leaves 2 beans | `@Primary` does not remove default | Add/fix OnMissingBean |
| Runner tests PASS, real app lacks bean | Missing `AutoConfiguration.imports` | Check resource path and `@SpringBootTest` smoke |
| Auto-config picked up by component scanning | Placed under root scan package | Separate packages, use imports |
| FilteredClassLoader fails to hide class | Filtered wrong package/type/loader | Specify exact optional type |
| Context crashes due to missing transitive library | Class present but method/supertype cannot load | Check dependency graph/binary compatibility |
| Test fails when switching profiles | Property precedence changed | Set scenario properties explicitly and test per profile |
| Condition report shows negative match unclear to test | Misreading conditions in same scope | Inspect OnClass/OnProperty/OnBean outcomes |
| `@ConditionalOnProperty` on a list | Indexed collection does not match as expected | Use custom Condition or separate metadata logic |
| Mock bean causes unexpected default back-off | Test overrides count as bean definitions | Use real `@Bean` configs for condition tests |
| Spring Boot 4 test imports mismatch | Packages/versions differ from 3.5 | Pin target version, migrate with verification |

Do not widen `@SpringBootTest` scope just to avoid understanding conditions. A small runner test with clear classes/properties/user configs usually provides better diagnostics.

## 24. QA checklist before releasing a starter/auto-configuration

- [ ] `@AutoConfiguration` has exact class name in `META-INF/spring/...AutoConfiguration.imports`?
- [ ] Auto-config is not accidentally registered via `@ComponentScan`?
- [ ] Optional class condition uses class-level `@Configuration` isolation when bean methods depend on the library?
- [ ] Tested both class present and class absent via `FilteredClassLoader`?
- [ ] Tested flag missing, true, false, invalid, and empty?
- [ ] `havingValue` and `matchIfMissing` reflect the intended default-on/default-off contract?
- [ ] Understand default `havingValue=""` differs from `havingValue="true"`?
- [ ] Avoided using `@ConditionalOnProperty` as a reliable condition for indexed lists?
- [ ] Tested user bean with **different name yet same type** making default back off?
- [ ] Tested user bean still exists when auto flag is off or optional class is absent?
- [ ] Tested unrelated bean does not affect default?
- [ ] `@Bean` method declares a return type accurate enough for bean conditions?
- [ ] Avoided using `@Primary` to replace conditional back-off?
- [ ] Interdependent auto-configs have explicit ordering?
- [ ] Context startup success and bean absence are asserted separately?
- [ ] Have `ConditionEvaluationReport`/debug procedure for unexpected no-match?
- [ ] Have a smoke test ensuring real `imports` resource auto-discovery?
- [ ] If web/reactive-only, used the right context runner?
- [ ] Tests do not depend on OS locale, network, database, or ports unnecessarily?
- [ ] Code examples reviewed for Java 17 and Spring Boot 3.5 without falsely claiming compiled/executed?
- [ ] Distinguished compile-time optional classes from runtime classpath filtering?
- [ ] Verified binary compatibility when supporting multiple optional library versions?

## 25. Run commands and expected results

With JDK 17+ and Gradle Wrapper in the project:

~~~bash
./gradlew test --tests "com.example.formatter.autoconfigure.FormatterAutoConfigurationTests"
./gradlew test --tests "com.example.app.FormatterApplicationSmokeTests"
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.formatter.autoconfigure.FormatterAutoConfigurationTests"
.\gradlew.bat test --tests "com.example.app.FormatterApplicationSmokeTests"
.\gradlew.bat test
~~~

There are **15 JUnit test methods** across two classes: 14 runner tests and 1 smoke test. Expected outcomes:

~~~text
default/missing flag + OptionalCodec present -> CODEC:HELLO
training.formatter.enabled=true           -> default bean
training.formatter.enabled=false          -> no default bean
training.formatter.enabled=maybe          -> no default bean
user TextFormatter present                -> USER:abc (default backs off)
OptionalCodec hidden by FilteredClassLoader -> no default bean
Property not set + default matchIfMissing -> no strictSignal
Property present and "yes" + default havingValue -> strictSignal
Application smoke test with imports file  -> CODEC:HELLO
~~~

This is **expected output derived from code analysis**, not stdout collected from an actual run. The sample uses no `System.out.println`, so there is no fixed stdout. **The code was not compiled or run via Gradle/JUnit during authoring**; verifying requires downloading dependencies, a Gradle Wrapper, and JDK 17.

**Summary:** To test auto-configuration properly, create **a separate context for each combination of classpath, properties, and user beans**. `@ConditionalOnClass` should guard nested configurations depending on optional libraries; `@ConditionalOnProperty` needs a clear truth table and missing-property policy; `@ConditionalOnMissingBean` lets auto-defaults back off based on registered bean definitions. `ApplicationContextRunner` and `FilteredClassLoader` verify the matrix quickly; a `@SpringBootTest` smoke test verifies **`AutoConfiguration.imports`** actually works.

### Official documentation

- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.5.16 — @ConditionalOnClass Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot 3.5.16 — @ConditionalOnProperty Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.5.16 — @ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.5.16 — ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Framework 6.2 — Core @Conditional and @Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html)