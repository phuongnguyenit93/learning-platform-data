# Distinguishing conditional backoff from same-name bean definition overriding in Spring Boot

In **Spring Boot Auto Configuration**, starter authors often want to provide a default bean while letting the application choose a different implementation. Two mechanisms are often loosely grouped together as "overriding a bean": **conditional backoff** and **same-name bean definition overriding**. They are two different mechanisms, act at different moments, and should not be used interchangeably.

**Key points to remember:**

- **Backoff with `@ConditionalOnMissingBean`:** auto-configuration checks whether a matching bean already exists among processed definitions. If so, **the default bean is not registered**. The application's custom bean is preserved, even if it has a **different name** from the default bean.
- **Bean definition overriding:** one bean definition is already registered under the name `gateway`, and then another definition is registered under the exact same name `gateway`. If the registry permits overriding, the second definition can **replace** the earlier one; otherwise, a registration error usually occurs.
- **Spring Boot 3.x default:** `spring.main.allow-bean-definition-overriding` defaults to `false`. Supplying a custom bean via proper backoff **does not require** enabling this property.

Phrases like "custom bean overrides auto-configuration" in Spring Boot documentation usually mean **auto-configuration backs off**; they do not automatically mean replacing a bean definition with the same name.

## 1. Distinguishing bean name, bean type, and bean definition

A **bean definition** is metadata the container uses to manage a bean: name, type, how to create the object, scope, dependencies, factory method, etc. Definitions are normally registered before Spring creates actual **instances**.

- **Bean name** is an identifier in a bean registry, such as `"paymentGateway"`. With `@Bean`, the default name is usually the method name; `@Bean("specialGateway")` specifies an explicit name.
- **Bean type** is the Java type, e.g., the `PaymentGateway` interface. Two different names can still share the same type.
- **Bean instance** is the actual instantiated object. Changing a definition during context setup and replacing an already-created object are two different operations.

Illustrative example inside a configuration class:

```java
interface PaymentGateway {
    String provider();
}

@Bean("specialGateway")
PaymentGateway gateway() {
    return () -> "partner";
}
```

This is an **illustrative excerpt**, not a standalone Java file. The bean name is `specialGateway`, while the contract type is `PaymentGateway`.

| Case | Duplicate bean name? | Same bean type? | Consequence |
| --- | :---: | :---: | --- |
| `alphaGateway` and `betaGateway` are both `PaymentGateway` | No | Yes | Not name-based overriding; may be ambiguous when injecting by type. |
| Two definitions both named `gateway`, different types | Yes | No | Definition conflict/override by **name**. |
| Two definitions both named `gateway`, same type | Yes | Yes | Still a conflict/override by **name**. |
| User bean named `customGateway` of type `PaymentGateway`; auto-config checks missing `PaymentGateway.class` | Not required | Yes | Auto-config **backs off by type**. |

`@Primary` and `@Qualifier` help select **which bean is injected** when multiple compatible beans exist. They do not remove definitions and do not register over a bean of the same name.

## 2. Backoff with `@ConditionalOnMissingBean`

A default configuration can be written as:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultGateway() {
        return new DefaultPaymentGateway();
    }
}
```

`PaymentGateway` and `DefaultPaymentGateway` here are hypothetical project types. The snippet illustrates annotation placement; a complete Maven/JUnit example is in Section 5.

If the application provides:

```java
@Bean("customGateway")
PaymentGateway customGateway() {
    return new PartnerPaymentGateway();
}
```

then Spring Boot, when processing auto-configuration after the user's beans, sees that a matching bean of type `PaymentGateway` already exists. The `@ConditionalOnMissingBean(PaymentGateway.class)` condition **does not match**, so the `defaultGateway` definition **is not added**. No duplicate-name registration occurs: `customGateway` remains intact.

If the user provides no matching bean, the condition matches and the default definition `defaultGateway` is registered. This can be represented as:

```text
User bean of type PaymentGateway already exists?
  ├─ Yes → do not register defaultGateway (BACKOFF)
  └─ No  → register defaultGateway (DEFAULT)
```

### Does the condition check by type or by name?

The two options below have different meanings:

```java
// Any existing matching PaymentGateway bean causes the default to back off.
@ConditionalOnMissingBean(PaymentGateway.class)

// Only checks whether a bean named "paymentGateway" already exists.
@ConditionalOnMissingBean(name = "paymentGateway")
```

A user bean `@Bean("customGateway")` of type `PaymentGateway` causes the **type-based condition** not to match, whereas a **name-only** condition may still match because there is no bean named `paymentGateway`. As a result, Spring may register an extra bean of the same type with a different name. Therefore, when an interface is the starter's main extension point, check by **interface**, rather than relying on whatever name the application happens to pick.

`@ConditionalOnMissingBean` also has attributes such as `type`, `annotation`, `ignored`, `parameterizedContainer`, and `search` (search scope across current/parent contexts). Do not interpret every multi-attribute declaration as a simple "OR"; read the exact condition combination rules if a starter uses multiple criteria.

If no arguments are passed and the annotation is placed on a `@Bean` method, Spring Boot uses the method's **declared return type** to infer the type to search for:

```java
@Bean
@ConditionalOnMissingBean
PaymentGateway defaultGateway() {
    return new DefaultPaymentGateway();
}
```

In a starter with multiple implementations, writing `@ConditionalOnMissingBean(PaymentGateway.class)` explicitly helps readers understand the contract clearly.

### When does backoff occur?

Conditions are evaluated when the framework **processes and registers bean definitions**. It relies on bean definitions processed **up to that point**, not a lookahead scan of all future beans. Spring Boot recommends placing `@ConditionalOnMissingBean` in **auto-configuration**, because application-declared beans are normally processed first.

When two auto-configurations both want to provide a default `PaymentGateway`, one processed earlier can register its default and cause the later one to back off. When outcomes depend on order, use auto-configuration ordering metadata such as `@AutoConfiguration(before = …)`/`after = …` and write tests for both with and without user beans.

**Backoff deletes nothing:** if the condition does not match, the default method does not create a bean definition. No old definition has to be replaced.

## 3. Same-name bean definition overriding

Suppose the registry currently holds:

```text
bean name: "gateway"
bean definition: DefaultGateway
```

Then a component registers:

```text
bean name: "gateway"
bean definition: CustomGateway
```

The names are **identical** in the **same registry**. This is a bean definition overriding situation:

- With `allowBeanDefinitionOverriding=false`, duplicate-name registration may lead to `BeanDefinitionOverrideException`.
- With `allowBeanDefinitionOverriding=true`, the new definition can **replace** the old one. The outcome depends on which definition is registered **later**.
- Overriding replaces the **definition metadata** used for that bean name; it is not an operation mutating the state of a previously instantiated Java object.
- Some special Spring processing paths (such as Java configuration and component scanning) may skip a compatible duplicate-name definition or follow different processing rules. Therefore, do not claim that *every* pair of same-named `@Bean` methods always throws the exact same exception. To cleanly verify registry behavior, Section 5 uses `registerBeanDefinition` directly.

In a Spring Boot 3.x application, the option:

```properties
spring.main.allow-bean-definition-overriding=false
```

is the **default**. If intentionally enabled:

```properties
spring.main.allow-bean-definition-overriding=true
```

definition overriding cases permitted by the registry can take place. Another configuration path is calling:

```java
// Snippet inside main(String[] args) of an application with MyApplication:
SpringApplication application = new SpringApplication(MyApplication.class);
application.setAllowBeanDefinitionOverriding(true);
application.run(args);
```

**Do not use this global flag as the default way to customize a starter.** It can hide situations where two libraries accidentally register beans with the same name. It also does not solve the issue of **two beans of the same type with different names** causing injection ambiguity, because that is not a definition name collision.

## 4. Comparing mechanisms: differences in condition and action

| Property | Conditional backoff | Bean definition overriding |
| --- | --- | --- |
| Typical API | `@ConditionalOnMissingBean` | `DefaultListableBeanFactory.registerBeanDefinition` and option allowing override |
| Decision point | During **condition evaluation** before registering the default | When **registering an already-existing name** |
| When a matching bean exists | **Skips registering** the default | May attempt to register a **same-name** definition |
| Requires matching bean name? | **No**; condition can be type-based | **Yes**, in the same registry |
| Type-based condition? | Can target type or name | Same name is the defining factor of overriding |
| Is the old bean definition replaced? | **No** | **Potentially**, if registry permits |
| Does Boot block overriding by default? | Backoff still works normally | Many duplicate-name registration paths are blocked |
| Order-dependent? | Yes: condition only sees definitions processed so far | Yes: a later definition can replace an earlier one |
| Starter best practice | Recommended for providing customizable defaults | Only use for specific requirements with clear understanding of risks |

**Two distinct flows:**

```text
BACKOFF
UserConfig registers customGateway : PaymentGateway
  → AutoConfig checks @ConditionalOnMissingBean(PaymentGateway.class)
  → does not match because PaymentGateway already exists
  → DOES NOT register defaultGateway
  → customGateway remains the application's choice

OVERRIDING
Registry registers name "gateway" -> DefaultGateway
  → Registry receives registration name "gateway" -> CustomGateway
  → If overriding is disallowed: registration error
  → If overriding is allowed: replaces definition under name "gateway"
```

One might use the word "replace" to describe *the application outcome*, yet technically **not registering a default** and **replacing an existing definition** are two separate mechanisms.

## 5. Runnable example: Java 17 + Spring Boot 3.3.5 + JUnit 5

A practical test suite will prove all four aspects:

1. No user bean → auto-configuration registers the default.
2. User bean with a **different name** but the same type → auto-configuration **backs off**.
3. Two definitions with the **same name** → error when overriding is off, replaces definition when on.
4. Two definitions with **different names and the same type** → both coexist, potentially throwing `NoUniqueBeanDefinitionException` when requesting a single bean by type.

**Separating verification mechanisms:** `ApplicationContextRunner` demonstrates how Spring Boot applies auto-configuration. `DefaultListableBeanFactory` demonstrates bean definition registry behavior directly; in the registry tests, the flag is set explicitly so Spring Framework core's defaults are not confused with Spring Boot's defaults.

### 5.1. Project structure

```text
bean-backoff-lab/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── BackoffVersusOverrideTest.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>bean-backoff-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

### 5.2. Complete test file

`src/test/java/demo/BackoffVersusOverrideTest.java`:

```java
package demo;

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

class BackoffVersusOverrideTest {

    interface Gateway {
        String name();
    }

    public static class DefaultGateway implements Gateway {
        @Override
        public String name() {
            return "default";
        }
    }

    public static class CustomGateway implements Gateway {
        @Override
        public String name() {
            return "custom";
        }
    }

    public static class AlternativeGateway implements Gateway {
        @Override
        public String name() {
            return "alternative";
        }
    }

    @AutoConfiguration
    static class GatewayAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Gateway.class)
        Gateway defaultGateway() {
            return new DefaultGateway();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean("myGateway")
        Gateway myGateway() {
            return new CustomGateway();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            GatewayAutoConfiguration.class));

    @Test
    void defaultIsRegisteredWhenNoUserBeanExists() {
        runner.run(context -> {
            assertThat(context.getBeansOfType(Gateway.class))
                    .containsOnlyKeys("defaultGateway");
            assertThat(context.getBean(Gateway.class).name())
                    .isEqualTo("default");
        });
    }

    @Test
    void userBeanMakesDefaultBackOffWithoutMatchingName() {
        runner.withUserConfiguration(UserConfiguration.class)
                .run(context -> {
                    assertThat(context.getBeansOfType(Gateway.class))
                            .containsOnlyKeys("myGateway");
                    assertThat(context.getBean(Gateway.class).name())
                            .isEqualTo("custom");
                    assertThat(context.containsBean("defaultGateway"))
                            .isFalse();
                });
    }

    @Test
    void duplicateNameFailsWhenOverridingIsDisabled() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(false);

        factory.registerBeanDefinition(
                "sharedGateway",
                new RootBeanDefinition(DefaultGateway.class));

        assertThatThrownBy(() -> factory.registerBeanDefinition(
                "sharedGateway",
                new RootBeanDefinition(AlternativeGateway.class)))
                .isInstanceOf(BeanDefinitionOverrideException.class);

        assertThat(factory.getBean("sharedGateway", Gateway.class).name())
                .isEqualTo("default");
    }

    @Test
    void duplicateNameReplacesDefinitionWhenEnabled() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(true);

        factory.registerBeanDefinition(
                "sharedGateway",
                new RootBeanDefinition(DefaultGateway.class));
        factory.registerBeanDefinition(
                "sharedGateway",
                new RootBeanDefinition(AlternativeGateway.class));

        assertThat(factory.getBean("sharedGateway", Gateway.class).name())
                .isEqualTo("alternative");
        assertThat(factory.getBeanDefinitionCount()).isEqualTo(1);
    }

    @Test
    void sameTypeDifferentNamesAreNotDefinitionOverrides() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(false);

        factory.registerBeanDefinition(
                "firstGateway",
                new RootBeanDefinition(DefaultGateway.class));
        factory.registerBeanDefinition(
                "secondGateway",
                new RootBeanDefinition(AlternativeGateway.class));

        assertThat(factory.getBeanNamesForType(Gateway.class))
                .containsExactlyInAnyOrder("firstGateway", "secondGateway");

        assertThatThrownBy(() -> factory.getBean(Gateway.class))
                .isInstanceOf(NoUniqueBeanDefinitionException.class);
    }
}
```

In the `bean-backoff-lab` directory, using JDK 17+ and Maven:

```bash
mvn test
```

**Expected result:** five tests pass. Maven Surefire typically prints `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0` in its report; other log lines vary by environment. The tests do not call `System.out.println`, so do not expect a specific business stdout line.

| Test | Verified behavior |
| --- | --- |
| `defaultIsRegisteredWhenNoUserBeanExists` | `defaultGateway` exists when no user bean is present. |
| `userBeanMakesDefaultBackOffWithoutMatchingName` | `myGateway` exists and `defaultGateway` **does not**, even though the two bean names differ. |
| `duplicateNameFailsWhenOverridingIsDisabled` | `BeanDefinitionOverrideException` is thrown and the original definition is kept. |
| `duplicateNameReplacesDefinitionWhenEnabled` | `sharedGateway` follows the second definition; definition count stays 1. |
| `sameTypeDifferentNamesAreNotDefinitionOverrides` | Two names of the same type coexist; unique lookup by type is ambiguous. |

**Why it runs cleanly:**

- The implementation classes in the test are `public static` with no-arg constructors, so `RootBeanDefinition` can instantiate them.
- `GatewayAutoConfiguration` is an auto-configuration **nested in the test**; the runner loads it via `AutoConfigurations.of`, so no imports file is needed in the lab.
- `UserConfiguration` is loaded as application configuration via `withUserConfiguration`; auto-configuration is processed later, so the missing-bean condition sees `myGateway`.
- The three registry tests intentionally call `registerBeanDefinition` **before instantiating beans with `getBean`**. They verify **definition** replacement, rather than simulating overwriting a singleton already in use at runtime.
- In a real starter, place the auto-configuration class in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, using one fully qualified class name per line.

### 5.3. Extending the test yourself

Try changing the condition in `GatewayAutoConfiguration` to:

```java
// Only replace the annotation in the example, not a standalone file:
@ConditionalOnMissingBean(name = "defaultGateway")
```

The user bean named `myGateway` does not satisfy the condition checking for **the name `defaultGateway`**. Therefore, the default can also be registered, yielding two beans of type `Gateway` with different names. This is an exercise to observe the **difference between name-based backoff and type-based backoff**; if you apply the change, the assertions in the second test must be updated accordingly.

Try calling `factory.setAllowBeanDefinitionOverriding(true)` in the duplicate-name test expecting an exception and inspect the behavior. Changing that flag only controls registry behavior on **name** collisions; it does not turn `@ConditionalOnMissingBean` into an overriding mechanism.

## 6. How to design customizability in a starter

A starter providing `PaymentGateway` should:

1. **Define a clear interface** that applications can implement themselves.
2. **Register the default bean in auto-configuration** with `@ConditionalOnMissingBean(PaymentGateway.class)`. If classpath, property, or web environment conditions are needed, combine the corresponding conditions.
3. **Allow the application to choose any bean name**, as long as it exposes the `PaymentGateway` type. Avoid forcing users to re-declare the starter's exact internal bean name.
4. **Test both branches**: without a custom bean and with a custom bean; add tests when two auto-configurations compete for the same type if the starter has fallbacks.
5. **Do not rely on enabling global bean definition overriding** to implement standard extension points.

When requirements call for **multiple implementations coexisting**, give them distinct names and use `@Qualifier`, `@Primary`, or inject collections `List<PaymentGateway>` / `Map<String, PaymentGateway>` as needed. This is a dependency selection mechanism, not backoff or definition overriding.

If **same-name definition overriding** is genuinely required due to an integrating framework's specific contract, verify the flag, registration path, registration timing, and stable bean name; add integration tests to observe the result in a real context. Avoid assuming a bean in a library will always register earlier or later merely due to dependency order in `pom.xml`.

## 7. Troubleshooting: look at bean names first, then conditions

### Encountering `BeanDefinitionOverrideException`

- Read the error message to identify the duplicate **bean name** and the two definition sources.
- Check whether `@Bean` methods or component scanning accidentally produce the same name. Two beans with the same name can come from different modules or packages.
- If the library's bean should yield, fix the auto-configuration to use an appropriate condition and test; give distinct names to two valid implementations.
- Only consider `spring.main.allow-bean-definition-overriding=true` when you genuinely want definition-replacing registration and understand the ordering and impact on other libraries.

### Encountering `NoUniqueBeanDefinitionException`

Usually **multiple differently named beans of the same type** exist and an injection point requires a single bean. Decide whether multiple implementations are intentional. If only one default is wanted, verify whether the condition checks the **interface type** or only a name. If multiple implementations are needed, use appropriate qualifiers, `@Primary`, or collections. Enabling overriding **does not** resolve this if the names are not duplicates.

### Custom bean exists, yet the default is still created

- Does the default condition check `PaymentGateway.class`, a concrete implementation, or `name`?
- Does the user's `@Bean` signature declare a specific enough type? Returning `Object` can prevent interface-based conditions from recognizing the definition in time.
- Is the custom bean loaded **before** auto-configuration? Is it in the current context or a parent/child context? Check the `search` attribute if using context hierarchies.
- Is the auto-configuration loaded properly via the imports file? Are there other class-level or method-level conditions?

You can pass `--debug` when running a Spring Boot application to view the **Condition Evaluation Report**, or use Actuator `/actuator/conditions` if enabled and permitted. For starters, `ApplicationContextRunner` is particularly convenient for isolating conditions.

### Overriding is enabled, yet the final bean is not the expected one

Inspect the **registration path** and **actual order**, because name-based bean definition overriding does not imply the user bean always wins. Some `@Configuration`/component-scan processing paths follow special definition rules. Write an integration test with the application's actual dependency set rather than guessing from imports line order.

## 8. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "A custom bean must have the same name as the default bean." | Type-based backoff does not require matching names. |
| "`@ConditionalOnMissingBean` deletes an already-registered default." | It prevents **registering the default** when the condition does not match. |
| "Two beans of the same type are overriding each other." | With different names, it is not definition overriding. |
| "`@Primary` makes one definition replace another." | `@Primary` affects selection during injection. |
| "Enabling bean definition overriding makes every custom bean win." | When overriding is allowed, a later-registered definition can replace an earlier one; the winner is not guaranteed. |
| "Overriding is enabled by default in Spring Boot 3." | `spring.main.allow-bean-definition-overriding` defaults to `false`. |
| "`@ConditionalOnMissingBean` sees every bean registered in the future." | Conditions only inspect definitions processed up to evaluation time. |
| "Two same-named `@Bean` methods always throw the exact same error regardless of how they are loaded." | Different processing/scan paths have distinct rules; verify the concrete scenario. |
| "Allowing overriding fixes all injection conflicts." | Multiple **differently named beans of the same type** can still cause injection ambiguity. |

## 9. Self-check

**Question 1.** A starter registers `defaultGateway` with `@ConditionalOnMissingBean(Gateway.class)`, and the application declares `@Bean("myGateway") Gateway custom()`. Does overriding need to be enabled?  
**Answer:** No. Auto-configuration backs off on the `Gateway` type when it sees the user bean; the default is not registered.

**Question 2.** Two definitions share the name `sharedGateway` in a registry with overriding disabled. What can happen when the second definition is registered?  
**Answer:** A `BeanDefinitionOverrideException` on a registration path that rejects duplicate names.

**Question 3.** Two beans named `bankGateway` and `cardGateway` both implement `Gateway`. Is this overriding?  
**Answer:** No, because the names differ. Injecting a single `Gateway` may require `@Qualifier` or `@Primary`.

**Question 4.** Why does `@ConditionalOnMissingBean(name = "defaultGateway")` not necessarily back off when a user bean named `myGateway` of the same type exists?  
**Answer:** The condition only looks for the **name** `defaultGateway` and does not treat `myGateway` as satisfying it.

**Question 5.** Does setting `spring.main.allow-bean-definition-overriding=true` guarantee the application's bean always wins?  
**Answer:** No. Override outcomes depend on which definition is registered later and the registration path.

**Question 6.** If another competing auto-configuration is processed earlier and registers a bean of the same interface, what happens to the later auto-configuration's missing-bean condition?  
**Answer:** It normally does not match and the later class's default backs off, assuming both conditions check the same contract type and no special conditions apply.

**Conclusion:** **Conditional backoff** decides **not to register** a default bean when a matching bean exists; **bean definition overriding** decides whether a **same-name registered definition** may be replaced. For extension points in a Spring Boot starter, prefer proper type-based backoff, keep name overriding disabled by default, and verify with tests. When errors occur, distinguish **duplicate names**, **duplicate types**, condition evaluation order, and definition registration order.

### Official references

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — `@ConditionalOnMissingBean` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — `SpringApplication` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework 6.1 — `BeanDefinitionOverrideException` API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionOverrideException.html