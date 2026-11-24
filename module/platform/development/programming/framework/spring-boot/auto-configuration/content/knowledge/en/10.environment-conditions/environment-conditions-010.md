# `@Profile` in Conditional Configuration and Its Relationship with Boot's Annotation Group

> **Goal:** Understand how `@Profile` decides whether to register a configuration/bean based on the **active profile**, distinguish it from **Spring Boot Auto Configuration** conditional annotations, and know how to combine multiple conditions without accidentally enabling or disabling a feature in an environment.

In the Spring ecosystem, a **profile** is a logical label for an environment or deployment variant (such as `dev`, `staging`, `prod`). `@Profile` belongs to **Spring Framework**, not an annotation created specifically by Spring Boot. It is a form of `@Conditional`, whereas Spring Boot provides additional specialized conditional annotations such as `@ConditionalOnProperty`, `@ConditionalOnClass`, and `@ConditionalOnMissingBean`. These mechanisms can coexist on a single `@Configuration` class or `@Bean` method.

This lesson uses Java 17+ with Spring Boot 3.3 / Spring Framework 6.1 APIs. The examples do not assume that merely setting a profile name lets the application connect to a database or toggle all features automatically: a profile is **a bean registration condition**, not a complete feature suite.

## 1. From @Conditional to @Profile and Boot Conditions

At the foundational level, Spring evaluates `Condition` while processing configuration metadata and decides whether to register a bean definition. `@Profile` is defined with the `@Conditional(ProfileCondition.class)` meta-annotation; its condition asks `Environment` whether the requested profile expression matches.

Spring Boot builds on that foundation:

- `@AutoConfiguration` is an auto-configuration class discovered and applied by Boot; at its core it is a Spring configuration.
- `@ConditionalOnProperty` checks a property in `Environment`.
- `@ConditionalOnClass` or `@ConditionalOnMissingClass` checks class presence.
- `@ConditionalOnBean` or `@ConditionalOnMissingBean` checks matching bean definitions already processed up to evaluation time.
- `@ConditionalOnResource` checks resources.
- `@ConditionalOnWebApplication`, `@ConditionalOnNotWebApplication` check web application type.
- `@ConditionalOnExpression` evaluates a SpEL expression; when an expression directly references a bean, it can cause eager instantiation of that bean, so use caution.

**Difference in the question asked:** `@Profile("prod")` asks “is the `prod` profile active?”, whereas `@ConditionalOnProperty(prefix="demo.audit", name="enabled", havingValue="true")` asks “does the effective value of `demo.audit.enabled` equal `true`?”. An application can run with the `prod` profile while `demo.audit.enabled=false`, or run with the `dev` profile while the feature is enabled. Neither condition implies the other.

**Critical timing:** The condition result affects configuration/bean registration when the context is built. Once the context has initialized, changing an environment variable or editing a YAML file does not automatically re-register previously excluded beans. If runtime toggling is required, use an appropriate dynamic feature-management mechanism; do not treat `@Profile` as a runtime feature flag.

## 2. Where Can @Profile Be Placed?

### Placed on a @Configuration class

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("dev")
class DevelopmentConfiguration {
    @Bean
    String debugBanner() {
        return "Debug mode";
    }
}
~~~

When `dev` matches, the configuration class is eligible for processing and the `debugBanner` bean can be registered; when it does not match, the `@Bean`s inside the class and any `@Import`s attached to that configuration are skipped. Placing the annotation on the class restricts an entire group of beans at once.

### Placed on a @Bean method

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
class TransportConfiguration {
    @Bean
    @Profile("dev")
    String localTransport() {
        return "in-memory";
    }

    @Bean
    @Profile("prod")
    Integer productionPort() {
        return 443;
    }
}
~~~

This example illustrates **two independent beans of different types and names**, each with its own condition; it does not simulate a real transport interface. If `dev` is active, `localTransport` can be registered; if `prod` is active, `productionPort` can be registered. If both `dev` and `prod` are enabled simultaneously, **both** can be registered: profiles are not mutually exclusive by default.

`@Profile` can also be used on `@Component`/stereotype classes, or as a meta-annotation on custom application-defined annotations.

**Note with `@ConfigurationProperties`:** When a properties class is discovered via scanning, `@Profile` can be placed on the properties class. When a properties bean is registered via `@EnableConfigurationProperties`, place `@Profile` on the `@Configuration` class containing `@EnableConfigurationProperties`. These are two different registration paths; do not assume an annotation on a properties class is evaluated identically in both paths.

## 3. Profile Expression Syntax: OR, AND, NOT

Spring Framework supports profile expressions with `!` (not), `&` (and), `|` (or), parentheses, and multiple expression strings.

| Syntax | Matching condition | Notes |
| --- | --- | --- |
| `@Profile("dev")` | `dev` is active | Selects one specific profile. |
| `@Profile({"dev", "staging"})` | `dev` **or** `staging` is active | Multiple array elements mean **OR**, not AND. |
| `@Profile("dev & cloud")` | Both `dev` and `cloud` are active | Use a single expression with `&` when both are needed simultaneously. |
| `@Profile("dev | staging")` | `dev` or `staging` is active | An OR expression, equivalent to a two-element array. |
| `@Profile("!prod")` | `prod` is not active | Can be true even when **no active profile is declared**. |
| `@Profile("dev & !cloud")` | `dev` is active and `cloud` is not active | Combined condition with negation. |
| `@Profile("(dev & cloud) | staging")` | (`dev` and `cloud`) or `staging` | When mixing `&` and `|` you must **use parentheses**. |
| `@Profile("default")` | The `default` profile is in use | Typically happens when no active profile is specified. |

Do not write `@Profile("dev & cloud | staging")` because mixing `&` and `|` without parentheses is an invalid expression. Write `@Profile("(dev & cloud) | staging")` or `@Profile("dev & (cloud | staging)")` according to your intended logic.

A common pitfall is `@Profile({"dev", "!prod"})`. The comma here means **OR**: in a `staging` environment (which is not `prod`), the `!prod` branch is already true, so the bean can be registered even when the `dev` profile is absent. If you want “dev and not prod”, use `@Profile("dev & !prod")`.

**Default profile:** When no active profile is specified, Spring uses the default profiles set, which defaults to `default`. This can be changed via `spring.profiles.default`. `@Profile("!prod")` still typically matches then, while `@Profile("prod")` does not. Distinguish `getActiveProfiles()` (which may be an empty array) from the default profiles used when active profiles are empty.

## 4. How Does Spring Boot Determine Active Profiles?

Spring Boot uses `Environment` to manage active/default profiles. Common ways to configure:

~~~properties
# application.properties in a profile-unspecific document
spring.profiles.active=dev
~~~

~~~bash
# Configure via command-line argument
java -jar app.jar --spring.profiles.active=staging
~~~

Or use the environment variable `SPRING_PROFILES_ACTIVE=prod` supplied by the OS, IDE, or container. `PropertySource` precedence determines the effective `spring.profiles.active` value when multiple sources declare it: for example, command-line arguments typically override config file values. Do not infer active profiles solely from the file you have open; when debugging, check the actual process state.

Spring Boot also supports:

- `spring.profiles.include` to **append** profiles instead of replacing the active profile list.
- `spring.profiles.group.production=proddb,prodmq` to activate logical groups: enabling `production` also activates its member profiles.
- `spring.config.activate.on-profile=prod` to condition **a config data document**; this is a property/YAML document loading rule, distinct from `@Profile` conditioning bean definitions.
- Files like `application-dev.yml` and `application-prod.properties` are loaded according to activated profiles and config data ordering.

Multi-document YAML example:

~~~yaml
# application.yml - shared document
sample:
  audit:
    enabled: false
---
spring:
  config:
    activate:
      on-profile: "dev"
sample:
  audit:
    enabled: true
~~~

With `dev`, the second document supplies `sample.audit.enabled=true`; with `prod`, the second document is not activated. These are **two related yet independent condition layers**: the profile decides which document is loaded, then the final property is resolved across `PropertySource`s and can govern `@ConditionalOnProperty`. Environment variables or command-line args can override values in YAML.

**Restriction rule:** `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include`, and `spring.profiles.group` must be declared in a **profile-unspecific** document, not placed inside `application-dev.yml` or a document with `spring.config.activate.on-profile`. Putting them in the wrong place can cause Boot to report a config data error instead of applying the profiles as desired.

## 5. Relationship with Boot's Conditional Annotation Group

Conditions **on the same configuration/bean target** must all be satisfied for the component to be registered. For example:

~~~java
@AutoConfiguration
@Profile("dev | staging")
@ConditionalOnClass(name = "com.example.vendor.AuditClient")
class AuditAutoConfiguration {
    @Bean
    @ConditionalOnProperty(
            prefix = "sample.audit",
            name = "enabled",
            havingValue = "true")
    @ConditionalOnMissingBean(AuditService.class)
    AuditService auditService() {
        // Illustrates a method inside a library where AuditService is available.
        return new AuditService();
    }
}
~~~

*This is **structural illustration** code, not a standalone runnable Java file:* `AuditService` and the library class `com.example.vendor.AuditClient` are not defined in this snippet. The complete test example in section 6 uses built-in and self-defined types.

With the structure above, evaluated in logical order:

1. **Class level:** Profile must be `dev` or `staging` **and** the `AuditClient` dependency must be on the classpath. If either fails, the auto-configuration class is not applied.
2. **Method level:** Once the class qualifies, `sample.audit.enabled` must equal `true` **and** no matching `AuditService` bean has been processed yet for the fallback to register.
3. **At object creation:** Only after the bean definition is registered does Spring instantiate objects according to dependencies. Bean definition conditions do not necessarily force objects to be instantiated beforehand.

The combined condition can be written symbolically:

~~~text
register(auditService) =
    (profile = dev OR profile = staging)
AND (class com.example.vendor.AuditClient is present)
AND (sample.audit.enabled = true)
AND (matching AuditService bean is missing at evaluation time)
~~~

This does **not** mean the four annotations are interchangeable:

| Annotation | “Question” the condition answers | When to use |
| --- | --- | --- |
| Spring `@Profile` | Which profile/expression is active? | Branch configurations by environment or deployment variant. |
| Boot `@ConditionalOnProperty` | Does the `Environment` key have the required value? | Toggle features via config and override at deployment time. |
| Boot `@ConditionalOnClass` | Is the dependency/class on the classpath? | Configure integration only when the library exists. |
| Boot `@ConditionalOnMissingBean` | Has a matching bean already been declared? | Provide a default and defer to an application-defined bean. |
| Boot `@ConditionalOnBean` | Does a matching dependency bean already exist? | Configure add-ons only when the dependency bean is already present. |
| Boot `@ConditionalOnResource` | Is the specified resource present? | Open configuration only when a required file/resource exists. |
| Boot `@ConditionalOnWebApplication` | Is this a web application of the right type? | Conditionally configure Servlet/Reactive setups. |
| Boot `@ConditionalOnExpression` | Does the SpEL expression return true? | Conditions hard to express with built-in ones; avoid bean references in expressions if possible. |

Two key design points:

- **Prioritize intent, do not “cram” every condition onto one bean.** If a library has an optional feature, `@ConditionalOnClass` + `@ConditionalOnProperty` + `@ConditionalOnMissingBean` usually express the contract more clearly than hard-binding to a user's `dev`/`prod` profile. `@Profile` makes sense when a component inherently belongs only to a specific environment.
- **Bean ordering still matters.** `@ConditionalOnBean` and `@ConditionalOnMissingBean` only observe bean definitions already processed when the condition runs; if another auto-configuration supplies a bean later, two candidates may exist. Order them with `@AutoConfiguration(after = ...)` or `@AutoConfigureAfter` when needed; do not use `@DependsOn` as a fix for condition evaluation order.

### Class-level and @Bean-level create a two-tier “AND”

If the class has `@Profile("dev")` and the method has `@ConditionalOnProperty(... havingValue="true")`, **both** must match. If the class does not match, the method gets no chance to register a bean, even if the property equals `true`. If the class matches but the method does not, the configuration class may still be processed, yet no bean is registered from that method.

Do not treat `@Profile({"dev", "staging"})` as an AND operation and assume both must be enabled together; it is OR **within one annotation**. Conversely, two different conditional annotations on the same class are multiple gates that must all pass.

## 6. Runnable Java 17+ Test: profile + class + property + bean

To observe the exact mechanism without running a full web application, use Spring Boot's `ApplicationContextRunner`. This is **a source-independent Java test file**, requiring a project with Spring Boot 3.3 and the `spring-boot-starter-test` test dependency (JUnit Jupiter + AssertJ).

**File:** `src/test/java/example/conditions/ProfileConditionTest.java`

~~~java
package example.conditions;

import java.time.Clock;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

import static org.assertj.core.api.Assertions.assertThat;

class ProfileConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(AuditAutoConfiguration.class));

    private ApplicationContextRunner profile(String profileName) {
        return runner.withInitializer(context ->
                context.getEnvironment().setActiveProfiles(profileName));
    }

    @Test
    void devWithEnabledFlagRegistersAutoBean() {
        profile("dev")
                .withPropertyValues("sample.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditSink.class);
                    assertThat(context.getBean(AuditSink.class).source())
                            .isEqualTo("auto");
                });
    }

    @Test
    void stagingWithEnabledFlagRegistersAutoBean() {
        profile("staging")
                .withPropertyValues("sample.audit.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(AuditSink.class));
    }

    @Test
    void productionProfileRejectsAutoConfiguration() {
        profile("prod")
                .withPropertyValues("sample.audit.enabled=true")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    @Test
    void devWithDisabledFlagRejectsBeanMethod() {
        profile("dev")
                .withPropertyValues("sample.audit.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    @Test
    void devWithoutFlagRejectsBeanMethod() {
        profile("dev")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    @Test
    void userBeanOverridesAutoDefault() {
        profile("dev")
                .withPropertyValues("sample.audit.enabled=true")
                .withUserConfiguration(UserAuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditSink.class);
                    assertThat(context.getBean(AuditSink.class).source())
                            .isEqualTo("user");
                    assertThat(context).doesNotHaveBean("auditSink");
                });
    }

    record AuditSink(String source) {}

    @AutoConfiguration
    @Profile("dev | staging")
    @ConditionalOnClass(Clock.class)
    static class AuditAutoConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "sample.audit",
                name = "enabled",
                havingValue = "true")
        @ConditionalOnMissingBean(AuditSink.class)
        AuditSink auditSink() {
            return new AuditSink("auto");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditConfiguration {
        @Bean
        AuditSink customAuditSink() {
            return new AuditSink("user");
        }
    }
}
~~~

**How to run** in a Maven or Gradle project with JUnit 5:

~~~bash
mvn -Dtest=ProfileConditionTest test
# Or with Gradle wrapper on Linux/macOS:
./gradlew test --tests example.conditions.ProfileConditionTest
~~~

**Expected result:** **6 tests PASS**, with no guaranteed program stdout because the methods only contain assertions. The tests cover all critical branches:

- Profile `dev` or `staging` + flag `true` → auto bean is registered.
- Profile `prod` + flag `true` → `@AutoConfiguration` class is blocked by `@Profile`.
- Profile `dev` + flag `false` or missing flag → `@Bean` method is blocked by `@ConditionalOnProperty`.
- Profile `dev` + flag `true` + user bean → `@ConditionalOnMissingBean` lets the default auto bean back off; the user-configured `customAuditSink` bean is retained.

`@ConditionalOnClass(Clock.class)` in the example always matches on Java 17+ because `java.time.Clock` is built into the JDK; its purpose is to also illustrate **a classpath dependency gate** at the class level. To test the missing-class branch, replace the simulated dependency with an optional library class and test with Boot's `FilteredClassLoader`.

The classes in the test are passed **directly** to `AutoConfigurations.of(...)`, so no `AutoConfiguration.imports` file is needed. When packaging as a starter for Boot auto-discovery, auto-configuration classes should live in a separate package not component-scanned, and be listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. For nested classes, the binary name contains `$`; in real libraries consider top-level configurations for easier maintenance.

### Reading the example's “truth table”

| Profile | `sample.audit.enabled` | User `AuditSink` exists? | Outcome |
| --- | --- | --- | --- |
| `dev` | `true` | No | Creates `auditSink` from auto-configuration |
| `staging` | `true` | No | Creates `auditSink` from auto-configuration |
| `prod` | `true` | No | Does not create `auditSink` (profile mismatch) |
| `dev` | `false` | No | Does not create `auditSink` (property mismatch) |
| `dev` | Key absent | No | Does not create `auditSink` (default `matchIfMissing=false`) |
| `dev` | `true` | Yes | Keeps user bean; default auto bean is not registered |

If using `@ConditionalOnProperty` **without `havingValue="true"`**, any present value other than the string `false` can match (for example `custom`). Therefore, for toggle flags, specify `havingValue` explicitly to avoid misinterpretation.

## 7. How to Debug When @Profile and Boot Conditions Give Unexpected Results

A typical case: a bean is only needed on `staging`, yet the staging environment lacks the bean even though `sample.audit.enabled=true` is in the file.

**Check in order:**

1. **Verify the process's actual active/default profiles.** `spring.profiles.active` in a file can be overridden by the command line or environment variables; Boot also has `include` and `group`.
2. **Cross-check the `@Profile` expression.** If written `"dev & staging"`, both profiles must be enabled simultaneously; `{"dev","staging"}` or `"dev | staging"` is the OR choice.
3. **Check annotation placement.** A condition on the class excludes the whole group; a condition on a method governs only that bean. If the class is already excluded, no method condition inside can save it.
4. **Check remaining Boot conditions.** Does the classpath have the required dependency? Is the effective property value actually `true`? Is a user bean causing `@ConditionalOnMissingBean` not to match? Is an auto-configuration providing a dependency ordered before the consumer?
5. **Test the profile × property × user bean matrix** with `ApplicationContextRunner` as in section 6. This is a fast way to isolate the root cause when production has many property sources.

The following snippet is **illustrative inside a bean injected with `Environment`**, used for inspection:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

static void describe(Environment env) {
    System.out.println("active=" +
            Arrays.toString(env.getActiveProfiles()));
    System.out.println("default=" +
            Arrays.toString(env.getDefaultProfiles()));
    System.out.println("dev matches=" +
            env.acceptsProfiles(Profiles.of("dev")));
    System.out.println("audit flag=" +
            env.getProperty("sample.audit.enabled"));
}
~~~

This snippet is an illustrative method, **with no main method and no Spring context created**. Printed values depend on the running environment. Remember that `getActiveProfiles()` can be empty even while `@Profile("default")` still matches due to the default profile.

In Spring Boot, you can start with `--debug` to view the condition evaluation report, or use Actuator `/actuator/conditions` if Actuator is added and the endpoint is secured/exposed. **Limitation to remember:** Boot's conditions report focuses on tracked Boot conditions; do not assume every Spring Framework `@Profile` evaluation appears as its own separate entry. Also cross-check active profiles and actual beans in the context. Diagnostic endpoints should not be exposed publicly in production.

## 8. Common Mistakes and Better Designs

**Mistake 1 — Using @Profile instead of a property flag.** If you want a feature shared across all environments while allowing toggling from config, `@ConditionalOnProperty` is usually more suitable. Profiles are for selecting by environment group, not for every boolean feature option.

**Mistake 2 — Treating profiles as mutually exclusive labels.** Spring can have multiple active profiles. `@Profile("dev")` and `@Profile("prod")` both match if both labels are active together. Do not assume “only one” unless startup guarantees it.

**Mistake 3 — Using @Profile("!prod") as a safe description.** Negating `prod` also allows `default`, `test`, or `staging`; this expression is quite broad. When the requirement is clearly “dev only”, `@Profile("dev")` is stricter.

**Mistake 4 — Mixing AND/OR incorrectly.** The array `@Profile({"dev", "test"})` is OR, whereas `@Profile("dev & test")` is AND. Use parentheses whenever both `&` and `|` appear in one expression.

**Mistake 5 — Using @Profile to pick overloaded @Bean methods.** Spring Framework has a special note: for overloaded `@Bean` methods sharing **the same Java method name**, `@Profile` conditions must not be used as an overload-selection mechanism based on signature; if you want two methods to alternate by profile, give them **different Java method names** and a shared bean name when appropriate by design, while ensuring mutually exclusive profile conditions to avoid conflicts.

**Mistake 6 — Confusing @Profile with @ActiveProfiles.** `@Profile` is placed on configurations/beans to condition registration. `@ActiveProfiles` belongs to Spring Test and configures active profiles for a **test context**; it is not an annotation to put on production business beans.

**Mistake 7 — Ignoring bean-condition timing.** `@ConditionalOnMissingBean` looks at bean definitions already present when the condition runs; if another auto-configuration provides a bean later, two candidates may appear. Order them with `@AutoConfiguration(after = ...)` or `@AutoConfigureAfter` when needed; do not use `@DependsOn` as a fix for condition ordering.

**Mistake 8 — Putting spring.profiles.active in a profile-activated document.** Spring Boot 3.3 does not allow configuring `spring.profiles.active` inside a profile-specific document. Put it in a profile-unspecific document, or supply it at runtime from the environment/command line.

## 9. Self-Check Exercises

1. The sole active profile is `staging`. Does `@Profile({"dev", "!prod"})` match? **Yes**, because `!prod` is true; multiple array elements are OR.
2. `dev` and `cloud` are active. Does `@Profile("dev & !cloud")` match? **No**, because `!cloud` is false.
3. `dev` is active, property `sample.audit.enabled=false`, and a bean is marked with both `@Profile("dev")` and `@ConditionalOnProperty(... havingValue="true")`. Is it registered? **No**, because the property condition does not match.
4. The property equals `true`, but the enclosing class has `@Profile("prod")` and the active profile is `dev`. Is the `@Bean` method evaluated for registration? **No**, the configuration class was already skipped.
5. No profile is declared and the default profile is unchanged. Can `@Profile("default")` match? **Yes**, because `default` is the default profile.
6. When developing a starter, you need to skip the default if the application defines its own bean. What should you use? **`@ConditionalOnMissingBean` on the auto-configuration**, combined with profile/property/class gates only when matching business requirements exist.

## Official Documentation for Reference

- [Spring Framework 6.1 — @Profile Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/context/annotation/Profile.html): applicability scope, method/class config, OR in arrays, note on `@Bean` overloads.
- [Spring Framework 6.1 — Profiles API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/env/Profiles.html): profile expressions with `!`, `&`, `|`, and parentheses.
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html): active/default profiles, `include`, profile groups, profile-specific config files, and config placement restrictions.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): conditional annotation group, auto-configuration ordering, and `ApplicationContextRunner`.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): `conditions` diagnostic endpoint and how to control exposure.

**Takeaway:** `@Profile` is a **Spring Framework profile-based condition** that can be combined with Boot conditions as **AND** gates. Choose the right annotation for the question you want to test, clearly distinguish class-level from `@Bean`-level scope, and verify with real combinations of profiles, properties, classpath, and beans.
