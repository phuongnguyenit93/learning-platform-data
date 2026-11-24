# Per-bean back-off instead of disabling an entire configuration group

> **Design principle:** When a Spring Boot auto-configuration provides multiple default beans, whichever bean the application wants to replace should have **the corresponding default bean** back off; the other default beans should still be kept if no application-provided version exists. Consider placing `@ConditionalOnMissingBean` on **each `@Bean` method** to achieve this level of replacement, rather than putting a missing-bean condition at the entire auto-configuration class level and accidentally dropping the whole group.

This lesson belongs to **Spring Boot Auto Configuration → Replacement and Exclusion**. It explains the difference between *per-bean back-off*, *class-level conditions*, and *excluding an entire auto-configuration*; how to organize a library with independent defaults; and how to test with `ApplicationContextRunner` on Spring Boot 3.3 and Java 17+.

## 1. Problem: a configuration group provides multiple capabilities

Suppose a reporting library comes with three components:

1. `Encoder`: converts content into a suitable representation.
2. `Exporter`: outputs the encoded data.
3. `ReportPipeline`: coordinates `Encoder` and `Exporter`.

Application A wants to use all three default beans. Application B only wants to replace `Encoder` to support a custom format while still using the `Exporter` and `ReportPipeline` created by the library. Application C wants to replace `Exporter` without touching `Encoder`.

If declaring a single user `Encoder` caused **the entire auto-configuration to disappear**, Application B would lose `Exporter` and `ReportPipeline` unrelated to the replacement. The result could be missing beans, dependency injection errors, or forcing the user to manually reconfigure the entire library.

What is desired here is **selective replacement**:

| Bean declared by the application | Library's default `Encoder` | Library's default `Exporter` | Library's default `ReportPipeline` |
| --- | --- | --- | --- |
| No custom beans | Registered | Registered | Registered |
| Custom `Encoder` provided | Backs off | Still registered | Still registered, uses custom `Encoder` |
| Custom `Exporter` provided | Still registered | Backs off | Still registered, uses custom `Exporter` |
| Both custom `Encoder` and `Exporter` provided | Backs off | Backs off | Still registered, uses both custom beans |
| Custom `ReportPipeline` provided | Still registered if still missing | Still registered if still missing | Backs off |

The table assumes the beans satisfy normal lookup conditions, there is only one matching bean per dependency, and no class-level condition blocks the entire configuration. If multiple candidates of the same type exist, dependency injection also depends on `@Primary`, `@Qualifier`, or other bean selection mechanisms.

**Distinguishing the steps:** "Backs off" here means **not registering the default bean definition** when the condition detects that a matching bean is already registered; it does not mean deleting a previously created bean object or mutating an object at runtime.

## 2. Why is a class-level condition often too broad?

The following example is a **design pattern unsuitable for per-bean replacement requirements**:

~~~java
// Structural illustration code; Encoder, Exporter, and ReportPipeline
// are types defined by the library in the sections below.
@AutoConfiguration
@ConditionalOnMissingBean(Encoder.class)
class ReportAutoConfiguration {
    @Bean
    Encoder encoder() {
        return new DefaultEncoder();
    }

    @Bean
    Exporter exporter() {
        return new DefaultExporter();
    }

    @Bean
    ReportPipeline reportPipeline(Encoder encoder, Exporter exporter) {
        return new ReportPipeline(encoder, exporter);
    }
}
~~~

If the application has already registered **one** `Encoder` bean:

- The **class-level** `@ConditionalOnMissingBean(Encoder.class)` condition does not match.
- The entire `ReportAutoConfiguration` class is not registered through this branch.
- The `exporter()` and `reportPipeline()` methods are also not used to provide defaults.
- Those beans **may still exist** if configured elsewhere, but this auto-configuration no longer provides them.

A class-level condition is not syntactically wrong. It is simply the wrong **scope of restriction** if the intent is to allow `Encoder` to be replaced independently. A class-level condition makes sense when **the entire** configuration only makes sense if that condition holds—for example, an integration that should only be loaded when a required dependency is present on the classpath.

More precisely, the different places to put conditions have different meanings:

| Placement | When the condition does not match | Scope of impact |
| --- | --- | --- |
| `@ConditionalOnMissingBean(Encoder.class)` on `@AutoConfiguration` class | Skips that configuration class | Beans from the entire class are not contributed via this path |
| `@ConditionalOnMissingBean(Encoder.class)` on `@Bean Encoder ...` method | Does not register the bean from that specific method | Other methods are still evaluated if class-level conditions pass |
| `@ConditionalOnProperty` on the class | If the flag is not met, the entire configuration is skipped | Appropriate if intentionally enabling/disabling **the whole feature** |
| `spring.autoconfigure.exclude` or `@SpringBootApplication(exclude=...)` | Named auto-configuration is removed from the applied set | Use only when intentionally disabling **the entire auto-configuration** |

**Note:** `@ConditionalOnMissingBean` is a condition in the bean registration system. It is not entirely equivalent to "if startup fails, create another bean," nor does it automatically re-evaluate if another bean is registered later.

## 3. Correct design: each default bean checks its own back-off condition

Write each `@Bean` with its corresponding condition:

~~~java
@AutoConfiguration
class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Encoder.class)
    Encoder defaultEncoder() {
        return value -> "encoded(" + value + ")";
    }

    @Bean
    @ConditionalOnMissingBean(Exporter.class)
    Exporter defaultExporter() {
        return value -> "out[" + value + "]";
    }

    @Bean
    @ConditionalOnMissingBean(ReportPipeline.class)
    ReportPipeline defaultPipeline(Encoder encoder, Exporter exporter) {
        return new ReportPipeline("auto", encoder, exporter);
    }
}
~~~

The snippet above illustrates configuration logic; the `Encoder`, `Exporter`, and `ReportPipeline` types are fully defined in the runnable test in Section 5. The condition explicitly specifies the type so readers do not mistake which bean type the condition checks.

Three key points:

**(1) Independent fallbacks.** When a user-registered `Encoder` exists, only `defaultEncoder()` backs off. The `defaultExporter()` method can still contribute an `Exporter` if no bean of that type exists yet. The same applies to `ReportPipeline`.

**(2) Definition registration differs from object creation.** When Spring processes `defaultPipeline(Encoder, Exporter)`, it can register the pipeline's definition; the `Encoder`/`Exporter` dependencies are resolved when the pipeline object is instantiated. Spring will pick the matching beans present in the container (whether from the application or default).

**(3) Type is the replacement contract.** `@ConditionalOnMissingBean(Encoder.class)` searches for a matching bean by **type**, not by the method name `defaultEncoder`. Therefore, `@Bean Encoder preferredEncoder()` also makes the default encoder back off. This is usually what users expect when providing a custom implementation.

If you place `@ConditionalOnMissingBean` on a `@Bean` without specifying `value`/`type`/`name`, Spring Boot can infer the checked type from that method's return type. However, in a public library, writing the target type explicitly makes the contract easier to read; avoid overly generic return types such as `Object` because type metadata during condition evaluation may be insufficient to identify candidates.

### Why not just use @Primary?

`@Primary` tells Spring which bean to prefer when injecting a single bean by type and multiple candidates exist. It **does not prevent** the default bean from being registered.

For example, an application provides a custom `Encoder` with `@Primary`, while the library still registers the default `Encoder` unconditionally. The container might work with the primary bean, yet two beans still exist; places that inject a `List<Encoder>` collection, look up a bean by name, or use a bean post-processor will still see both. When the desired contract is **back-off**, `@ConditionalOnMissingBean(Encoder.class)` expresses it more clearly.

Similarly, enabling `spring.main.allow-bean-definition-overriding=true` only allows overriding definitions with the same **name** via container mechanics; it does not solve type-based **back-off** and can hide misconfigurations. Do not use it as the default way to design a starter.

## 4. Bean lifecycle flow: who is created first, who depends on whom?

Spring Boot processes application-declared configurations before regular auto-configurations. Therefore, a library can use `@ConditionalOnMissingBean` to back off for user-defined beans.

Suppose the app has:

~~~java
@Configuration(proxyBeanMethods = false)
class UserReportConfiguration {
    @Bean
    Encoder customEncoder() {
        return value -> "custom(" + value + ")";
    }
}
~~~

At the time auto-configuration is processed:

1. The `customEncoder` bean definition has already been declared, with type `Encoder`.
2. `@ConditionalOnMissingBean(Encoder.class)` on `defaultEncoder()` does not match.
3. `@ConditionalOnMissingBean(Exporter.class)` on `defaultExporter()` still matches if no other exporter exists.
4. `@ConditionalOnMissingBean(ReportPipeline.class)` still matches if no other pipeline exists.
5. When the pipeline is created, Spring injects `customEncoder` and `defaultExporter`.

There is no need to delete the auto-configuration or copy all the default beans. The application replaces only the component it owns.

**When multiple auto-configurations exist:** Bean conditions only see definitions that have already been processed **at evaluation time**. If auto-configuration A needs to back off for a bean provided by auto-configuration B, you must declare appropriate ordering, such as `@AutoConfiguration(after = B.class)` on A. The `after` relationship governs **bean definition registration** order, not object creation order. `@DependsOn`, on the other hand, primarily affects initialization order and therefore cannot fix a condition seeing a bean too late.

Example ordering relationship:

~~~java
// Metadata illustration code; OtherProviderAutoConfiguration
// is another auto-configuration in the same library or dependency.
@AutoConfiguration(after = OtherProviderAutoConfiguration.class)
class ReportAutoConfiguration {
    // Individual @Bean methods with @ConditionalOnMissingBean(...)
}
~~~

This is an illustration, not a standalone class since it does not define `OtherProviderAutoConfiguration`. Do not order by line position in the `AutoConfiguration.imports` file; Boot uses `before`/`after` metadata.

## 5. Runnable example: replacing one part while keeping other defaults

The following test file defines `Encoder`, `Exporter`, `ReportPipeline`, and three different user configurations. It runs with **Java 17+, Spring Boot 3.3.x, JUnit Jupiter, and AssertJ**, via the `spring-boot-starter-test` dependency. No web application or database is required.

**File:** `src/test/java/example/autoconfig/PerBeanBackoffTest.java`

~~~java
package example.autoconfig;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class PerBeanBackoffTest {

    interface Encoder {
        String encode(String value);
    }

    interface Exporter {
        String export(String value);
    }

    record ReportPipeline(String source, Encoder encoder, Exporter exporter) {
        String run(String input) {
            return source + "|" + exporter.export(encoder.encode(input));
        }
    }

    @AutoConfiguration
    static class ReportAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Encoder.class)
        Encoder defaultEncoder() {
            return value -> "encoded(" + value + ")";
        }

        @Bean
        @ConditionalOnMissingBean(Exporter.class)
        Exporter defaultExporter() {
            return value -> "out[" + value + "]";
        }

        @Bean
        @ConditionalOnMissingBean(ReportPipeline.class)
        ReportPipeline defaultPipeline(Encoder encoder, Exporter exporter) {
            return new ReportPipeline("auto", encoder, exporter);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserEncoderConfiguration {
        @Bean
        Encoder userEncoder() {
            return value -> "custom(" + value + ")";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserExporterConfiguration {
        @Bean
        Exporter userExporter() {
            return value -> "user-out[" + value + "]";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserPipelineConfiguration {
        @Bean
        ReportPipeline userPipeline(Encoder encoder, Exporter exporter) {
            return new ReportPipeline("user", encoder, exporter);
        }
    }

    // Intentionally flawed model: a user-defined Encoder causes
    // the ENTIRE configuration class to back off, including defaultExporter.
    @AutoConfiguration
    @ConditionalOnMissingBean(Encoder.class)
    static class IncorrectReportAutoConfiguration {

        @Bean
        Encoder defaultEncoder() {
            return value -> "encoded(" + value + ")";
        }

        @Bean
        Exporter defaultExporter() {
            return value -> "out[" + value + "]";
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(ReportAutoConfiguration.class));

    @Test
    void withoutUserBeansRegistersAllDefaults() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Encoder.class);
            assertThat(context).hasSingleBean(Exporter.class);
            assertThat(context).hasSingleBean(ReportPipeline.class);
            assertThat(context).hasBean("defaultEncoder");
            assertThat(context).hasBean("defaultExporter");
            assertThat(context).hasBean("defaultPipeline");
            assertThat(context.getBean(ReportPipeline.class).run("hello"))
                    .isEqualTo("auto|out[encoded(hello)]");
        });
    }

    @Test
    void customEncoderOnlyReplacesEncoder() {
        runner.withUserConfiguration(UserEncoderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Encoder.class);
                    assertThat(context).hasBean("userEncoder");
                    assertThat(context).doesNotHaveBean("defaultEncoder");
                    assertThat(context).hasBean("defaultExporter");
                    assertThat(context).hasBean("defaultPipeline");
                    assertThat(context.getBean(ReportPipeline.class).run("hello"))
                            .isEqualTo("auto|out[custom(hello)]");
                });
    }

    @Test
    void customExporterOnlyReplacesExporter() {
        runner.withUserConfiguration(UserExporterConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Exporter.class);
                    assertThat(context).doesNotHaveBean("defaultExporter");
                    assertThat(context).hasBean("defaultEncoder");
                    assertThat(context).hasBean("defaultPipeline");
                    assertThat(context.getBean(ReportPipeline.class).run("hello"))
                            .isEqualTo("auto|user-out[encoded(hello)]");
                });
    }

    @Test
    void twoCustomComponentsKeepDefaultPipeline() {
        runner.withUserConfiguration(
                    UserEncoderConfiguration.class,
                    UserExporterConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Encoder.class);
                    assertThat(context).hasSingleBean(Exporter.class);
                    assertThat(context).hasSingleBean(ReportPipeline.class);
                    assertThat(context).doesNotHaveBean("defaultEncoder");
                    assertThat(context).doesNotHaveBean("defaultExporter");
                    assertThat(context).hasBean("defaultPipeline");
                    assertThat(context.getBean(ReportPipeline.class).run("hello"))
                            .isEqualTo("auto|user-out[custom(hello)]");
                });
    }

    @Test
    void customPipelineKeepsOtherDefaults() {
        runner.withUserConfiguration(UserPipelineConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("userPipeline");
                    assertThat(context).doesNotHaveBean("defaultPipeline");
                    assertThat(context).hasBean("defaultEncoder");
                    assertThat(context).hasBean("defaultExporter");
                    assertThat(context).hasSingleBean(ReportPipeline.class);
                    assertThat(context.getBean(ReportPipeline.class).run("hello"))
                            .isEqualTo("user|out[encoded(hello)]");
                });
    }

    @Test
    void classLevelConditionIncorrectlyRemovesExporter() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        IncorrectReportAutoConfiguration.class))
                .withUserConfiguration(UserEncoderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Encoder.class);
                    assertThat(context).hasBean("userEncoder");
                    assertThat(context).doesNotHaveBean("defaultEncoder");
                    assertThat(context).doesNotHaveBean(Exporter.class);
                });
    }
}
~~~

**How to run** in a Maven/Gradle project with Spring Boot 3.3 and JUnit 5 configured:

~~~bash
mvn -Dtest=PerBeanBackoffTest test
# Or on Linux/macOS with the Gradle wrapper:
./gradlew test --tests example.autoconfig.PerBeanBackoffTest
~~~

**Expected result:** **6 tests PASS**; there are no fixed stdout lines because the tests only use assertions. The key results lie in the bean names and return values of `run("hello")`:

| Test | Beans that must remain | Default beans that must back off | `ReportPipeline.run("hello")` result |
| --- | --- | --- | --- |
| No user beans | 3 defaults | None | `auto\|out[encoded(hello)]` |
| Replace `Encoder` | `userEncoder`, `defaultExporter`, `defaultPipeline` | `defaultEncoder` | `auto\|out[custom(hello)]` |
| Replace `Exporter` | `defaultEncoder`, `userExporter`, `defaultPipeline` | `defaultExporter` | `auto\|user-out[encoded(hello)]` |
| Replace both | 2 user beans, `defaultPipeline` | `defaultEncoder`, `defaultExporter` | `auto\|user-out[custom(hello)]` |
| Replace `ReportPipeline` | `userPipeline`, two component defaults | `defaultPipeline` | `user\|out[encoded(hello)]` |
| Wrong condition at class level | Only `userEncoder` | Entire auto-config class skipped | No `Exporter` |

The `\|` sequences in the last column represent literal `|` characters in the Java string output; the backslash is only used to escape this character inside a Markdown table.

Two notes to understand the tests accurately:

- `AutoConfigurations.of(...)` loads the auto-configuration class directly for testing, so an `AutoConfiguration.imports` registration file is **not needed** in the test. When packaged as a starter, the actual auto-configuration needs to be discovered by Boot via `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- The last test **intentionally simulates a flawed design** and verifies the consequence: having a user `Encoder` makes even the default `Exporter` disappear. A "PASS" on that test means the assertion describing the design flaw was accurately reproduced, **not** that such configuration should be used.

### Why is this test section useful?

It tests the most important contract of auto-configuration: **a local replacement does not cause defaults in other branches to vanish**. Simply testing "the context starts up successfully" is not enough; when a user bean appears, the context might still start while auxiliary functionality disappears. The `hasBean`/`doesNotHaveBean` assertions and pipeline output show both **bean structure** and **integration behavior**.

## 6. Choosing condition scope based on architecture

The "each bean backs off individually" rule does not mean banning all class-level conditions. Distinguish between conditions **mandatory for the entire group** and conditions **applicable only to a specific bean**.

Layered design example:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.ClientLibrary")
@ConditionalOnProperty(
        prefix = "demo.integration",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
class IntegrationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Transport.class)
    Transport defaultTransport() {
        return new DefaultTransport();
    }

    @Bean
    @ConditionalOnMissingBean(Codec.class)
    Codec defaultCodec() {
        return new DefaultCodec();
    }
}
~~~

*This snippet is a **structural illustration** and does not compile standalone because `Transport`/`Codec`/`DefaultTransport`/`DefaultCodec` and the optional library class are not declared.*

- `@ConditionalOnClass` at the class level is a **shared gate**: if the required integration library is missing, none of the integration's defaults should be registered.
- `@ConditionalOnProperty` at the class level is a **group-wide on/off gate**, if that is indeed the meaning of the `demo.integration.enabled` flag.
- `@ConditionalOnMissingBean(Transport.class)` and `@ConditionalOnMissingBean(Codec.class)` on the methods are **independent replacement gates**.

If only one component supports a dedicated flag, place `@ConditionalOnProperty` on that component's method; do not put that flag on the entire class. If a bean truly requires another bean, you can use `@ConditionalOnBean` or appropriate dependency injection, while carefully considering registration order and missing-dependency cases.

A useful partitioning rule: **each group should represent an independently toggleable capability**, while replaceable defaults should have conditions at the appropriate scope. If a class grows too large and contains many distinct dependency conditions, splitting it into nested `@Configuration(proxyBeanMethods = false)` classes or separate auto-configurations is a clean approach; it still allows each default bean to back off on its own.

## 7. When should an entire auto-configuration be excluded?

Spring Boot allows applications to exclude an auto-configuration by class name, for example:

~~~properties
spring.autoconfigure.exclude=com.example.library.ReportAutoConfiguration
~~~

Or in Java:

~~~java
@SpringBootApplication(
        exclude = ReportAutoConfiguration.class
)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

This is **illustrative code**: you must import `SpringBootApplication` and `SpringApplication`, and `ReportAutoConfiguration` must be an actual auto-configuration on the classpath referenceable from the application. The exclude mechanism is intended for Boot-discovered auto-configuration classes, not as a general way to drop any `@Configuration` class manually `@Import`ed by the user.

Only use exclude when there is a reason at the **entire integration module level**: for example, the library is incompatible, all beans in the auto-configuration branch must be turned off, or the application wants full ownership of the entire configuration branch. When only **one** serializer/encoder/exporter needs replacing, excluding the whole group removes the remaining useful defaults and increases manual configuration cost.

**Do not confuse the three options:**

1. `@ConditionalOnMissingBean` on a method: *allows users to replace a single bean while keeping the rest*.
2. `@ConditionalOnProperty` on the class: *an intentional toggle switch for the entire group*.
3. `spring.autoconfigure.exclude`: *completely removes the named auto-configuration from the applied set*.

The same application can use all three mechanisms, each solving a different intent.

## 8. Risks to check when designing fallbacks

### 8.1. Check the right type, do not guess by name

`@ConditionalOnMissingBean(Encoder.class)` reacts to a bean of type `Encoder` regardless of whether it is named `userEncoder` or `preferredEncoder`. A name-based condition like `@ConditionalOnMissingBean(name = "reportEncoder")` is only appropriate if the bean name itself is the contract the library wants to support. If the user declares the same type with a different name, a name-based condition may fail to detect the replacement.

If you write a method returning `Object` that actually creates an `Encoder`, Spring Boot may lack sufficient type metadata when the condition is evaluated. Use concrete return types and explicit type conditions, especially when writing a starter with multiple beans.

### 8.2. Multiple candidates do not disappear due to back-off

`@ConditionalOnMissingBean(Encoder.class)` avoids creating an extra default when a matching `Encoder` **already exists**. It does not guarantee the user only registers one `Encoder`. If the application declares two encoders and the pipeline injects a single `Encoder` without a qualifier, `NoUniqueBeanDefinitionException` can occur. Resolve this with a clear contract: `@Primary`, `@Qualifier`, `@ConditionalOnSingleCandidate` where appropriate, or maps/collections if multiple implementations are intentionally supported.

### 8.3. Do not place missing-bean conditions on user configurations

Spring Boot recommends using `@ConditionalOnBean` and `@ConditionalOnMissingBean` in **auto-configurations**, because auto-configurations are processed after user-declared configurations. In user configurations or component-scanned classes, ordering may not be guaranteed as expected; the condition may only see a subset of bean definitions. For dependencies coming from another auto-configuration, declare explicit `before`/`after` ordering relationships.

### 8.4. Avoid using exclusion to fix a dependency injection error

If a default auto-configured bean uses an inappropriate dependency, check that dependency's contract and whether the user can declare a replacement bean. Excluding the entire auto-configuration may also remove beans supporting health checks, metrics, or infrastructure. Conditions should be scoped tightly to the reason each bean should or should not exist.

### 8.5. A class-level gate can be valid, if intentional

Not every group of defaults is valid in every environment. Some groups have genuinely shared conditions such as "only run with Servlet," "JDBC driver present," or "feature X enabled." In those cases, using class-level `@ConditionalOnWebApplication`, `@ConditionalOnClass`, or `@ConditionalOnProperty` is reasonable, combined with method-level `@ConditionalOnMissingBean` for replaceable parts.

## 9. Inspecting the Condition Evaluation Report to find skipped beans

When `Exporter` is missing after declaring a custom `Encoder`, diagnose by layers of cause:

1. **Identify the bean type and name** being searched: call `applicationContext.getBeansOfType(Exporter.class)` in a test, or use `ApplicationContextRunner` assertions.
2. **Inspect conditions on the auto-configuration class**: was `@ConditionalOnMissingBean` placed on the class? Is there a class-level `@ConditionalOnClass`/`@ConditionalOnProperty`/`@Profile` blocking the whole group?
3. **Inspect conditions on the method**: is `@ConditionalOnMissingBean(Exporter.class)` properly on `defaultExporter()`, or did it mistakenly check `Encoder.class`?
4. **Inspect the user's bean**: did the user register the right type? Is the `@Bean` method's return type specific enough? Are there multiple candidates causing injection ambiguity?
5. **Check auto-configuration ordering**: was the other dependency declared before or after? Bean conditions only see what has been processed at evaluation time.

In Spring Boot, you can start with `--debug` to view the Condition Evaluation Report. If Spring Boot Actuator is present and configured for secure access, the `/actuator/conditions` endpoint reveals positive/negative matches of auto-configurations. `ApplicationContextRunner` also lets you compare two nearly identical contexts differing by a single user bean to spot which bean was unintentionally replaced.

When replacing only one bean, verification must prove **both sides**: the corresponding default backed off **and** unrelated defaults remain present. That is why the test section above checks both bean names and integrated pipeline output rather than just verifying that the context starts up.

## 10. Quick decision table

| Intent | Recommended condition placement | Reason |
| --- | --- | --- |
| User may supply a custom `Encoder`, still needs default `Exporter` | `@ConditionalOnMissingBean(Encoder.class)` on default encoder method | Backs off only the bean to be replaced |
| User may replace entire `ReportPipeline`, while encoder/exporter can still be used separately | `@ConditionalOnMissingBean(ReportPipeline.class)` on pipeline method | Pipeline is independent of the remaining beans |
| Activate integration only when vendor library is present | `@ConditionalOnClass` on integration class/group | Truly shared condition for the entire group |
| Disable **entire** integration when property `enabled=false` | `@ConditionalOnProperty` on class/group | Group-level toggle switch |
| Completely disable a registered auto-configuration | `spring.autoconfigure.exclude` or `@SpringBootApplication(exclude=...)` | Intentionally removes the entire auto-configuration |
| Bean A should only be created if bean B exists | `@ConditionalOnBean(B.class)` at bean A's scope, with proper auto-config ordering | Dependency exists at evaluation time |

## 11. Self-check questions

1. Auto-configuration creates `Encoder` and `Exporter`. The user only declares a custom `Encoder`. Should `@ConditionalOnMissingBean(Encoder.class)` be on the class or which method? **On the method creating the default `Encoder`**; `Exporter` needs its own condition.
2. Why doesn't `@Primary` replace the back-off mechanism? **Because it helps select a bean during injection but does not prevent registering the default bean**, so two beans can still exist.
3. The user already has a custom `ReportPipeline`. Is it necessary to drop both the default `Encoder` and `Exporter`? **Not necessarily**; if they are independently useful and do not violate shared conditions, they should still be provided when missing.
4. Why can a class-level `@ConditionalOnMissingBean(Encoder.class)` cause the exporter to disappear? **Because a non-matching condition drops the entire auto-configuration class**, including unrelated methods.
5. Why does auto-configuration ordering matter? **Because bean conditions only see bean definitions already processed at evaluation time**; a provider arriving later does not cause an already-failed condition to be re-evaluated.
6. When is excluding an entire auto-configuration right? **When the application intentionally wants to drop that entire branch**, not merely replace a single implementation.

## Official documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): class/method conditions, bean back-off, processing order, return types, and `ApplicationContextRunner`.
- [Spring Boot 3.3 API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): search scope by type/name, type inference from `@Bean`, and the "processed so far" limitation.
- [Spring Boot 3.3 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): `before`/`after` metadata and how to define an auto-configuration.
- [Spring Boot 3.3 — Using Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html): overriding auto-config with beans and how to exclude an entire auto-configuration.

**Remember:** place **the back-off condition on the exact bean to be replaced**. Only place a condition at the entire configuration level when that condition truly applies to the whole group. Verify with a scenario where the user replaces **one** bean to ensure the remaining defaults still appear.
