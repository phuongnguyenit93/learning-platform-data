# Risks of using spring.main.allow-bean-definition-overriding to mask design conflicts

## 1. Nature of the problem and objectives

In Spring Boot Auto Configuration, two configurations can define a bean under the **same name**, whether they come from two different classes, a starter library and the application, or two import/component-scan paths. When registering a second bean definition with an already-taken name, Spring encounters an **identifier conflict**.

Spring Boot 3.3 sets `spring.main.allow-bean-definition-overriding=false` by default to detect this situation during startup. Setting it to `true` can allow one bean definition to replace another, letting the application get past the startup error. However, a configuration that "starts" does not mean the relationships between beans are properly designed: the replaced bean might hold essential configuration, a back-off condition may not have been applied, or two components meant to coexist may have collided on the same name.

Lesson objectives:

1. Understand precisely what `spring.main.allow-bean-definition-overriding` controls and what it **does not** control.
2. Distinguish **duplicate bean names**, **multiple beans of the same type**, and **property value overriding**.
3. Analyze the risks of enabling overriding globally and how to resolve conflicts according to architectural intent.
4. Apply `@ConditionalOnMissingBean`, clear bean names, `@Primary`, `@Qualifier`, `@Profile`, or `@ConditionalOnProperty` in the right context.
5. Verify using Java 17+, Spring Boot 3.3, and JUnit 5.

## 2. What is bean definition overriding really?

A `BeanDefinition` describes how Spring creates a bean: name, type/factory method, scope, conditions, autowiring, and related metadata. Within the same `BeanFactory`, bean definitions are generally managed by **bean name**.

Suppose two configurations define the same name `messageSender`:

```java
@Configuration(proxyBeanMethods = false)
class FileSenderConfiguration {

    @Bean("messageSender")
    MessageSender fileSender() {
        return new FileMessageSender();
    }
}

@Configuration(proxyBeanMethods = false)
class SmtpSenderConfiguration {

    @Bean("messageSender")
    MessageSender smtpSender() {
        return new SmtpMessageSender();
    }
}
```

This is an **illustrative code snippet**, assuming `MessageSender`, `FileMessageSender`, and `SmtpMessageSender` are provided by the application. When both definitions are processed in the same `BeanFactory`, they compete for the name `messageSender`. The issue is **name duplication**, not merely "having two classes implementing the same interface."

Spring Boot configuration in `application.yml`:

```yaml
spring:
  main:
    allow-bean-definition-overriding: false
```

With `false` (also the **Spring Boot 3.3 default**), duplicate-name registration is normally rejected. A typical error is `BeanDefinitionOverrideException`, containing the bean name and the two bean definitions involved. Depending on the registration path, the conflict may be caught at a different step and surface under a different exception; do not rely solely on the exception class name to diagnose the whole root cause.

If changed to:

```yaml
spring:
  main:
    allow-bean-definition-overriding: true
```

the container can accept **re-registering the same name**. When calling `BeanDefinitionRegistry.registerBeanDefinition(...)` directly, the later definition replaces the earlier one. This **does not** mean Spring creates two instances and "merges" them, nor is there a universal contract that one specific configuration class always wins across all scanning/import mechanisms.

### Outcomes of an overriding policy decision

| Question | When `false` | When `true` |
| --- | --- | --- |
| Second registration with the same name in a standard registry | Rejected with an error | May replace the same-name definition |
| Does it merge configuration from both definitions? | No | **No** |
| Does it guarantee the "business-correct" bean wins? | Not applicable, conflict is exposed | **No** |
| Can two differently named beans share the same interface? | Yes | Yes |
| Does it solve all autowiring errors? | No | No |
| Does it alter precedence of `application.yml`/property sources? | No | No |

**Scope:** `spring.main.allow-bean-definition-overriding` is a Spring Boot policy configured on the bean factory at startup through `SpringApplication`. A manually instantiated `DefaultListableBeanFactory` in a unit test may have a different default policy, so direct factory tests must set the flag explicitly to mirror Spring Boot's behavior.

## 3. Distinguishing three easily confused types of "collision"

### 3.1. Duplicate **bean name**: target of this property

```java
@Bean("messageSender")
MessageSender a() { /* ... */ }

@Bean("messageSender")
MessageSender b() { /* ... */ }
```

These are two attempts to register definitions under **the same name**. The bean definition overriding policy applies here. This snippet only illustrates the concept; inside a concrete configuration, how Spring's `ConfigurationClass` parser handles them also depends on characteristics of the two `@Bean` methods and configuration rules.

### 3.2. Different names, **same type**: usually an injection candidate selection issue

```java
@Bean("fileSender")
MessageSender fileSender() { /* ... */ }

@Bean("smtpSender")
MessageSender smtpSender() { /* ... */ }
```

These two beans **do not share a name**. They can coexist even with overriding disabled. However, injecting a single `MessageSender` without selection criteria can trigger `NoUniqueBeanDefinitionException`. Setting `allow-bean-definition-overriding=true` **does not** fix multiple differently named candidates of the same type. When these represent two valid strategies, use `@Qualifier` or `@Primary` to pick the appropriate bean.

### 3.3. Duplicate **property key**: not bean definition overriding

If a property `demo.timeout` appears in multiple `PropertySource` entries, Spring Boot applies externalized configuration precedence rules to determine the **final property value**. That mechanism is **different** from re-registering a bean name. `spring.main.allow-bean-definition-overriding` does not govern `application.yml` overriding environment variables, command-line arguments, profile configurations, or other property sources.

This distinction is vital when a team says "config B overrides config A": first clarify whether they mean **property value**, **bean definition**, or **injected candidate**.

## 4. Why enabling `true` to fix an error often hides design flaws

### 4.1. Loss of explicitness: uncertainty over which bean is kept

A new dependency, starter, or library may introduce a bean with the same name. When overriding is allowed, the application may continue running with a **different definition**. Settings attached to the old definition (such as scope, qualifiers, init/destroy methods, factory methods, or property configuration) may stop taking effect as expected.

Relying on "which configuration gets scanned earlier/later" to pick a winner is fragile: import order, classpath conditions, profiles, library versions, and bean registration timing can shift. Never treat **"whichever bean registers last"** as a business contract.

### 4.2. Bugs appearing only in another environment

A test context might load fewer starters than production; another profile might add extra configurations; one environment might include an additional dependency. With overriding globally enabled, **two different bean sets** can both start successfully while behaving differently.

For instance, `messageSender` in tests may be a safe stub, while in production it gets replaced by a real SMTP-sending definition or vice versa. If the goal is intentional test replacement, scope the replacement to **test configuration** using appropriate test annotations/configurations rather than enabling a global override policy across all environments.

### 4.3. Hiding flaws in auto-configuration design

A starter might declare `DefaultMessageSender` unconditionally, while the application defines `CustomMessageSender` under the same name. Setting `true` to make the app start does not fix the fact that the starter failed to **yield to user configuration**.

Standard auto-configuration design uses **conditional back-off**, such as:

```java
@AutoConfiguration
class MessageSenderAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }
}
```

If the user has already declared a `MessageSender` bean recognizable before the condition is evaluated, auto-configuration **does not register** the default bean. That is **intentional conditional replacement**, different from trying to register two same-named beans and letting the bean factory discard one.

**Ordering note:** `@ConditionalOnMissingBean` only evaluates bean definitions processed up to that point. Spring Boot recommends placing this condition in auto-configuration because user-declared configurations are processed first; between dependent auto-configurations, `@AutoConfiguration(after=...)` may be needed. Declare explicit `@Bean` return types so type-based conditions can recognize them without instantiating objects.

### 4.4. Obscuring bean ownership

If two modules both declare `transactionManager`, `objectMapper`, or `httpClient`, you must decide which module owns the default configuration, which is the consumer, and when the application is permitted to customize. A single global flag cannot express those rules.

Practical consequences may include: the serializer silently changing, losing interceptors or timeouts, a mapper missing required modules, a client using wrong credentials, a bean losing lifecycle hooks, and downstream dependencies receiving an unexpected instance. These risks **depend on which bean was replaced**; not every app enabling the flag hits all of them at once.

## 5. Solutions aligned with architectural intent

### 5.1. Two configurations **should not both be active**: eliminate duplicate registration sources

First trace why the same bean is registered twice:

- A configuration is both manually `@Import`ed and picked up by component scanning.
- An auto-configuration was placed inside component scanning instead of only via `AutoConfiguration.imports`.
- An old starter and a new starter both declare infrastructure under the same name.
- An experimental `@Configuration` leaked into production, or two configuration profiles are active simultaneously.
- A manual `@Bean` collides in identifier with a library-configured bean.

The fix is to correct import/scan paths, narrow scopes, remove redundant beans, or replace the corresponding configuration. Do not arbitrarily rename beans if they are **two definitions for one single responsibility**; first decide which definition actually belongs in the architecture.

### 5.2. Library provides a default, application may customize: `@ConditionalOnMissingBean`

The example below illustrates a **type-based back-off contract**, without requiring the user to match the default bean's name.

```java
@AutoConfiguration
class SenderAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultSender() {
        return new DefaultMessageSender();
    }
}

@Configuration(proxyBeanMethods = false)
class ApplicationSenderConfiguration {
    @Bean
    MessageSender customSender() {
        return new CustomMessageSender();
    }
}
```

These two classes are **illustrative snippets** requiring the application's interface and implementations. When user configuration is processed first and `customSender` is recognized as `MessageSender`, `defaultSender` **backs off**. There are no two same-named definitions and no need for `allow-bean-definition-overriding=true`.

If the contract demands a **fixed name** instead of a type, `@ConditionalOnMissingBean(name="messageSender")` can be used. Choose the right criterion: by type for "user supplies any implementation," by name for "only one specific identifier is allowed." A type-based condition may not fit if the application needs **multiple beans** sharing an interface; in that case, design explicit bean names and qualifiers.

### 5.3. Two implementations **must both exist**: distinct names + `@Qualifier`/`@Primary`

```java
@Configuration(proxyBeanMethods = false)
class SenderConfiguration {
    @Bean("smtpSender")
    @Primary
    MessageSender smtpSender() {
        return new SmtpMessageSender();
    }

    @Bean("fileSender")
    MessageSender fileSender() {
        return new FileMessageSender();
    }

    @Bean
    DispatchJob dispatchJob(
            @Qualifier("fileSender") MessageSender sender) {
        return new DispatchJob(sender);
    }
}
```

This is an **application code snippet** with project-defined types. Both beans have distinct names so there is no name collision. `@Primary` selects the default when injecting by type without a qualifier; `@Qualifier("fileSender")` explicitly picks the other strategy at the injection point. **`@Primary` and `@Qualifier` do not make two same-named definitions valid.**

### 5.4. Select only **one variant**: `@Profile` or `@ConditionalOnProperty`

If only one implementation should be active based on environment or configuration, express mutual exclusion via conditions rather than definition overriding:

```java
@Bean("messageSender")
@ConditionalOnProperty(
    prefix = "demo.sender",
    name = "mode",
    havingValue = "smtp"
)
MessageSender smtpSender() {
    return new SmtpMessageSender();
}

@Bean("messageSender")
@ConditionalOnProperty(
    prefix = "demo.sender",
    name = "mode",
    havingValue = "file"
)
MessageSender fileSender() {
    return new FileMessageSender();
}
```

These are **two hypothetical declarations inside a valid configuration**. With `demo.sender.mode=smtp` or `file`, only one method matches. If the property is missing or has another value, neither is registered. To avoid accidental dual matches as conditions grow or edge cases with same-named `@Bean` methods in one class, a more maintainable pattern is placing each variant in a **separate `@Configuration` class** with class-level conditions, or selecting the bean via a single factory method. Add tests per mode.

Similarly, one configuration per profile makes sense when the environment genuinely determines the implementation. With `@Profile("test")` and `@Profile("prod")`, ensure the intended profiles are not enabled simultaneously if both use the same bean name; never assume two arbitrary profiles are mutually exclusive.

### 5.5. Replacing only for tests: keep it inside the test context

If you need a fake, mock, or stub in tests, use proper test mechanisms (explicitly scoped `@TestConfiguration`, mock overrides supported by your Spring Boot/Spring Test version, or an isolated `ApplicationContextRunner`). Ensure test configurations never leak into runtime. Tests should prove **which bean was injected**, not just that "the context started."

Setting `spring.main.allow-bean-definition-overriding=true` system-wide just to make a test pass is not an intentional replacement pattern: it opens the door to other name collisions and makes differences between test and production hard to detect.

## 6. Hands-on Java 17+, Spring Boot 3.3: testing actual behavior

The tests below separate two layers: **(A) duplicate-name registration behavior of `DefaultListableBeanFactory`** and **(B) proper back-off of Spring Boot auto-configuration**. These are standalone scenarios requiring no web server.

Put the entire file at `src/test/java/example/overriding/BeanDefinitionOverridingTests.java` in a Java 17+ and Spring Boot 3.3.x project with `spring-boot-starter-test`, JUnit Jupiter, and AssertJ:

```java
package example.overriding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.support.BeanDefinitionOverrideException;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class BeanDefinitionOverridingTests {

    interface Sender {
        String id();
    }

    public static final class DefaultSender implements Sender {
        @Override
        public String id() {
            return "default";
        }
    }

    public static final class CustomSender implements Sender {
        @Override
        public String id() {
            return "custom";
        }
    }

    @Test
    void duplicateNameFailsWhenOverridingDisabled() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(false);
        factory.registerBeanDefinition(
                "messageSender",
                new RootBeanDefinition(DefaultSender.class));

        assertThatThrownBy(() -> factory.registerBeanDefinition(
                "messageSender",
                new RootBeanDefinition(CustomSender.class)))
                .isInstanceOf(BeanDefinitionOverrideException.class)
                .hasMessageContaining("messageSender");

        assertThat(factory.getBean("messageSender", Sender.class).id())
                .isEqualTo("default");
    }

    @Test
    void enabledOverridingReplacesDefinitionInRegistry() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(true);
        factory.registerBeanDefinition(
                "messageSender",
                new RootBeanDefinition(DefaultSender.class));
        factory.registerBeanDefinition(
                "messageSender",
                new RootBeanDefinition(CustomSender.class));

        assertThat(factory.getBeanDefinitionCount()).isEqualTo(1);
        assertThat(factory.getBean("messageSender", Sender.class).id())
                .isEqualTo("custom");
    }

    @Test
    void distinctNamesOfSameTypeAreNotDefinitionOverride() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(false);
        factory.registerBeanDefinition(
                "defaultSender",
                new RootBeanDefinition(DefaultSender.class));
        factory.registerBeanDefinition(
                "customSender",
                new RootBeanDefinition(CustomSender.class));

        assertThat(factory.getBeanDefinitionCount()).isEqualTo(2);
        assertThat(factory.getBeanNamesForType(Sender.class))
                .containsExactlyInAnyOrder(
                        "defaultSender",
                        "customSender");

        assertThatThrownBy(() -> factory.getBean(Sender.class))
                .isInstanceOf(NoUniqueBeanDefinitionException.class);
    }

    @AutoConfiguration
    static class SenderAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(Sender.class)
        Sender defaultSender() {
            return new DefaultSender();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ApplicationSenderConfiguration {
        @Bean
        Sender customSender() {
            return new CustomSender();
        }
    }

    @Test
    void autoConfigurationBacksOffForUserBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(ApplicationSenderConfiguration.class)
                .withConfiguration(
                        AutoConfigurations.of(
                                SenderAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Sender.class);
                    assertThat(context.getBean(Sender.class).id())
                            .isEqualTo("custom");
                    assertThat(context.containsBean("defaultSender"))
                            .isFalse();
                });
    }

    @Test
    void autoConfigurationProvidesDefaultWhenNoUserBean() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                SenderAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Sender.class);
                    assertThat(context.getBean(Sender.class).id())
                            .isEqualTo("default");
                });
    }
}
```

**Run command** in a project with Gradle wrapper and JUnit Platform test configuration:

```bash
./gradlew test --tests example.overriding.BeanDefinitionOverridingTests
```

With Maven using JUnit 5/Surefire:

```bash
./mvnw -Dtest=BeanDefinitionOverridingTests test
```

**Expected result:** five tests PASS; exact stdout depends on Gradle/Maven and logging settings. Note that the first two tests **set the flag directly** on `DefaultListableBeanFactory` to test exact registry mechanics. In a normal Spring Boot application, `spring.main.allow-bean-definition-overriding` configures the corresponding policy through `SpringApplication`. Those are two paths for setting the same kind of policy; reading the property does not automatically alter a manually constructed factory.

### How to read each test

1. `duplicateNameFailsWhenOverridingDisabled`: the second `messageSender` registration is blocked, leaving the old definition intact; the bean name is mentioned in the exception.
2. `enabledOverridingReplacesDefinitionInRegistry`: when overriding is allowed in a direct registry scenario, the later registration replaces the earlier one; only one definition remains for that name and the retrieved instance behaves as `custom`.
3. `distinctNamesOfSameTypeAreNotDefinitionOverride`: two **differently named** definitions sharing an interface both exist while overriding is off; single-bean lookup by type fails due to candidate ambiguity. Use names, qualifiers, or `@Primary` when both are intentionally needed.
4. `autoConfigurationBacksOffForUserBean`: user bean is present; `@ConditionalOnMissingBean(Sender.class)` prevents registering the default bean. There is no duplicate-name competition.
5. `autoConfigurationProvidesDefaultWhenNoUserBean`: without a user bean, auto-configuration registers the default implementation.

Nested `@AutoConfiguration` classes in the test file are passed explicitly via `AutoConfigurations.of(...)`. In a production library, Spring Boot discovers auto-configurations via `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Do not add this test configuration to application runtime.

## 7. Before–after scenario: why silencing the error does not solve the bug

**Before:** the application has `ApplicationSenderConfiguration` declaring `@Bean("messageSender")` returning `CustomSender`. A third-party starter also declares `@Bean("messageSender")` returning `DefaultSender` without checking whether a user bean exists.

- With overriding disabled, the context may fail with a bean name collision error. The error highlights **two places claiming ownership of one identifier**.
- When set to `true`, the context may proceed with one definition winning during registration. If the starter's default wins, the application may lose the customization the team expected. If the user bean wins, the ownership rule still has not been expressed as a contract.
- Behavior becomes even less predictable if starter versions, classpath conditions, or import paths change.

**After:** the starter provides `@ConditionalOnMissingBean(Sender.class)`, and the application uses `@Bean Sender customSender()`. Because auto-configuration is applied after user-declared definitions, the default backs off; the single remaining configuration clearly reflects intent: **the starter supplies a default, and the application has the right to replace it**.

If both senders serve **two different channels** and must coexist, the fix is not backing off on the whole `Sender` type, but **giving distinct names** and selecting at injection points, e.g., `@Qualifier("smtpSender")` and `@Qualifier("fileSender")`. Before choosing conditions, decide whether the design wants **one single bean** or **multiple coexisting beans**.

## 8. Diagnosing duplicate-name registration errors in order

1. **Read the actual error message.** For `BeanDefinitionOverrideException`, note the `beanName`, the existing definition, the new definition, and where each is defined; if the error comes from scanning or parsing, look up the corresponding exception type. Do not flip the property before identifying the registration sources.
2. **Find all sources defining the colliding name.** Check `@Bean("...")`, default `@Bean` method names, `@Component("...")`, `@Named`, `@Import`, scanning, auto-configuration imports files, and library declarations.
3. **Clarify the business contract.** Should only one implementation be active at a time, or must two distinct beans coexist? Who owns the default and who may customize?
4. **Pick the proper resolution.** Remove redundant registration; use type/name back-off; add environment conditions; or give distinct names with qualifiers/`@Primary`. Do not use a global flag instead of these rules.
5. **Check auto-configuration order and return types.** `@ConditionalOnMissingBean` relies on metadata already processed; beans with overly broad return types or prematurely evaluated conditions can keep defaults from backing off. Only add `after` when genuinely needed between auto-configurations.
6. **Test minimal combinations.** No user bean; with user bean; with both sources accidentally present; different profiles; with/without optional starters. Verify **the exact bean name and instance used**, not just that the context starts.
7. **Keep the strict policy after fixing.** `false` shows whether conflicts remain. If `true` is ever needed for a special compatibility case, document the scope, reason, controlled ordering, and a test verifying the winning definition; never treat it as default practice.

You can launch a Spring Boot application in debug mode to inspect the condition evaluation report:

```bash
java -jar app.jar --debug
```

This command assumes an executable JAR named `app.jar`. The condition report is helpful when `@ConditionalOnMissingBean` does not match as expected, though a bean name collision is not always fully explained by the condition report alone. Cross-check bean definition errors and registration sources too.

If testing the flag in a real runtime environment, the command-line syntax is:

```bash
java -jar app.jar --spring.main.allow-bean-definition-overriding=false
```

Keeping `false` during diagnosis surfaces conflicts rather than letting them silently overwrite. There is no need to add this property to configuration files if you already rely on the default value.

## 9. Common misconceptions and mistakes

- **"Setting `true` makes Spring pick the best bean."** False. It enables same-name re-registration; it does not evaluate quality, business priority, or compatibility of the replacement bean.
- **"Overriding only happens when two classes share the same type."** False. The core trigger is a **duplicate bean name**, regardless of whether the classes or interfaces match.
- **"Having two beans implementing the same interface is bean definition overriding."** False when the two beans have different names. That situation can cause injection ambiguity, not a name collision.
- **"`@Primary` resolves two same-named beans."** False. `@Primary` only prioritizes one candidate by type when multiple **differently named** beans are eligible for injection.
- **"`@Qualifier` makes Spring permit same-name registration."** False. Qualifiers select candidates at injection points.
- **"`@ConditionalOnMissingBean` is just another name for overriding."** False. Back-off avoids creating a default definition when a matching bean already exists; overriding replaces a definition after both attempt to register the same name.
- **"Just ordering an auto-configuration later guarantees its override is right."** False. Definition order is not a bean selection contract; proper conditions are needed, especially so defaults yield to user beans.
- **"Tests passing with `true` proves there are no more conflicts."** False. It only proves the context under that test configuration passed registration, not that a shadowed definition did not break behavior.
- **"Changing this flag alters `application.yml` precedence."** False. Externalized configuration property precedence is a separate mechanism.
- **"All `@Bean` conflicts throw the exact same exception."** Not necessarily. Errors can occur during scanning, parsing, or registry registration; inspect the stack trace and specific definitions.
- **"Putting `@Profile` on two same-named beans automatically makes them mutually exclusive."** Only true if the profiles or conditions actually **exclude** each other in that environment; test active profile combinations.
- **"Enabling overriding fixes circular dependencies or missing beans."** No. Those issues belong to the dependency graph, condition configuration, or other lifecycle concerns.

## 10. Self-check exercises

1. `@Bean("mailClient")` in config A returns `SmtpClient`, while config B returns `FakeClient` also named `mailClient`. What error is this? **Duplicate bean name**; the bean definition overriding policy applies.
2. Beans `smtpClient` and `fakeClient` both implement `MailClient`. Does enabling overriding fix `NoUniqueBeanDefinitionException` when injecting `MailClient`? **No.** Express selection with `@Primary`, `@Qualifier`, or restructure injection.
3. A starter supplies `DefaultSender`, and the application wants to inject `CustomSender` instead of the default. Best approach? **Use `@ConditionalOnMissingBean(Sender.class)` on the auto-configuration's default**, ensuring proper bean definition ordering.
4. A team sets `spring.main.allow-bean-definition-overriding=true` after adding a new dependency and the startup error goes away. Can this be considered fixed? **No.** You must identify which bean was replaced, why two definitions shared the same name, and what behavior is retained.
5. To vary `demo.timeout` per environment, is this flag needed? **No.** Use externalized configuration/profiles/property sources, which are separate from bean registration.
6. In the `DefaultListableBeanFactory` unit test, overriding is enabled and two same-named definitions are registered sequentially. What is the test outcome? **The registry keeps only the newer definition for that name**, so `getBean("messageSender")` creates `CustomSender`.
7. When putting `@Profile("test")` and `@Profile("prod")` on two same-named definitions, what assumption must be verified? **That both profiles are not active simultaneously** in any environment intended to have only one bean.

## 11. Official reference sources (Spring Boot 3.3 baseline)

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.main.allow-bean-definition-overriding`, default `false`, controlling same-name bean definition re-registration.
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): how to configure the bean definition overriding policy at startup.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `@ConditionalOnMissingBean`, bean definition processing order, and back-off mechanics.
- [Spring Framework — BeanDefinitionOverrideException API](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionOverrideException.html): exception thrown when a new bean definition attempts to register under an existing name while overriding is disallowed.
- [Spring Framework — DefaultListableBeanFactory API](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/beans/factory/support/DefaultListableBeanFactory.html): `setAllowBeanDefinitionOverriding` and managing bean definitions.
