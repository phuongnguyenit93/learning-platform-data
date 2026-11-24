# A `@Primary` bean does not automatically make all default beans disappear

**Topic:** Spring Boot Auto Configuration  
**Knowledge area:** Replacement and exclusion (override, back-off, exclusion)  
**Central question:** When an application declares a `@Primary` bean, why can Spring still keep the default bean created by auto-configuration? What must be done if you want the default bean not to be registered?

## 1. Key conclusion to understand first

Spring Framework's `@Primary` **only marks the preferred bean when multiple candidates exist for a single-valued dependency injection point**. It **does not delete other beans**, does not automatically disable an entire auto-configuration, and does not automatically stop default `@Bean` methods from running.

Example:

```java
@Bean
@Primary
MessageSender customSender() {
    return new CustomMessageSender();
}

@Bean
MessageSender defaultSender() {
    return new DefaultMessageSender();
}
```

Here Spring can keep **both beans**: `customSender` and `defaultSender`. When another bean requires a single `MessageSender`, Spring normally selects `customSender` because it is the sole `@Primary` candidate. However, choosing one object to inject **does not mean** the other bean is removed from `ApplicationContext`.

If the intent is **not to register** `defaultSender` when a user bean already exists, that logic must be expressed with an appropriate condition such as `@ConditionalOnMissingBean(MessageSender.class)` on the auto-configuration side. `@Primary` itself does not replace this condition.

> Distinguish three concepts: **bean registration** (whether a bean exists), **bean selection for injection** (which bean is used at an injection point), and **auto-configuration exclusion** (which configurations do not participate). They operate with different goals.

## 2. Two distinct phases: bean registration and dependency resolution

### 2.1. Bean definition registration phase

Spring reads `@Configuration`, `@Bean`, and auto-configurations. Each method can produce a `BeanDefinition` if permitted to register by its conditions.

For example, an unconditional default configuration:

```java
@AutoConfiguration
class SenderAutoConfiguration {

    @Bean
    DefaultMessageSender defaultSender() {
        return new DefaultMessageSender();
    }
}
```

As long as the configuration is applied and no other constraint blocks it, `defaultSender` is still registered. The application having `@Primary CustomMessageSender` is not a condition that eliminates this bean.

If the default should only appear when no matching service type exists yet:

```java
@AutoConfiguration
class SenderAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    DefaultMessageSender defaultSender() {
        return new DefaultMessageSender();
    }
}
```

`@ConditionalOnMissingBean(MessageSender.class)` checks whether a bean satisfying `MessageSender` has already been recognized at condition evaluation time. A user bean of that type, **with or without `@Primary`**, can still prevent the fallback from registering.

### 2.2. Single dependency resolution phase

When a consumer needs a `MessageSender`, Spring must pick a candidate:

```java
final class NotificationService {
    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = sender;
    }
}
```

If two beans share the type and only `customSender` is `@Primary`, autowiring can select `customSender`. Yet both beans remain present in the factory.

Diagram:

```text
Configuration + Auto-configuration
           |
           v
    Evaluate registration conditions
           |
           +-- customSender  [@Primary] --------+
           |                                    |
           +-- defaultSender [no @Primary] -----+--> BeanFactory has 2 beans
                                                 |
                                    Injection requires 1 MessageSender
                                                 |
                                      Select customSender
                                                 |
                            defaultSender can still be accessed
```

**Key takeaway:** `@Primary` helps choose among already-existing candidates. It has no role in "cleaning up" other beans from `BeanFactory`.

## 3. Scenarios to distinguish

Consider `MessageSender` as an interface; both `CustomMessageSender` and `DefaultMessageSender` implement it.

| Application-supplied bean | Default bean rule | Typical `MessageSender` bean count | Outcome |
| --- | --- | ---: | --- |
| `@Primary CustomMessageSender` | Unconditional `@Bean DefaultMessageSender` | 2 | Custom is preferred for single injection, default still exists |
| `CustomMessageSender` without `@Primary` | Unconditional `@Bean DefaultMessageSender` | 2 | Single injection by type can be ambiguous; needs qualifier/primary |
| `@Primary CustomMessageSender` | `@ConditionalOnMissingBean(MessageSender.class)` | 1 | Default backs off because a bean matching the interface already exists |
| `CustomMessageSender` without `@Primary` | `@ConditionalOnMissingBean(MessageSender.class)` | 1 | Default also backs off; `@Primary` is not required |
| `@Primary CustomMessageSender` | `@ConditionalOnMissingBean(DefaultMessageSender.class)` | 2 | No exact `DefaultMessageSender` type exists yet, so default still registers |
| No application `MessageSender` | `@ConditionalOnMissingBean(MessageSender.class)` | 1 | Default is registered as a fallback |

The table assumes user configurations are processed **before** auto-configuration and bean types are accurately inferred. In real projects, registration order, `@Bean` method return types, `ApplicationContext` scope, and other conditions can affect the outcome.

The most common confusion lies between these two conditions:

```java
@ConditionalOnMissingBean(MessageSender.class)
```

and

```java
@ConditionalOnMissingBean(DefaultMessageSender.class)
```

They are **not the same**. The first means "no bean matches the `MessageSender` interface"; the second means "no bean matches the `DefaultMessageSender` implementation." If the user already declared `CustomMessageSender`, the implementation-based condition can still match and create the default as well.

## 4. How far does `@Primary`'s effect reach?

According to Spring Framework, `@Primary` takes effect when **multiple candidates qualify for a single-valued dependency**. If only one matching bean exists, `@Primary` is unnecessary for selection. If exactly one `@Primary` candidate exists among eligible candidates, that candidate is normally preferred.

Example:

```java
@Bean
@Primary
MessageSender customSender() {
    return new CustomMessageSender();
}

@Bean
MessageSender defaultSender() {
    return new DefaultMessageSender();
}
```

Results:

- `NotificationService(MessageSender sender)` can receive `customSender`.
- `applicationContext.getBean("defaultSender")` can still retrieve the default bean.
- Injecting `List<MessageSender>`, `Map<String, MessageSender>`, or typed arrays normally still receives all eligible beans, including non-`@Primary` beans.
- `@Qualifier("defaultSender")` is a way to explicitly select the default bean at that injection point; do not expect `@Primary` to override an explicit qualifier.

Example of a consumer needing the default even when another candidate is primary:

```java
@Bean
NotificationService defaultNotificationService(
        @Qualifier("defaultSender") MessageSender sender) {
    return new NotificationService(sender);
}
```

This snippet illustrates code inside a configuration class and requires `NotificationService`/`MessageSender` to be defined. `@Qualifier` can narrow down the candidate set before primary selection occurs.

**If two beans are both marked `@Primary` for the same dependency** and no single-valued selection remains, Spring can fail with candidate ambiguity. Adding `@Primary` indiscriminately is not guaranteed to fix `NoUniqueBeanDefinitionException`; inspect bean counts, qualifiers, names, and injection points.

`@Primary` can be placed on a `@Bean` method or on a suitable component class. For beans created via `@Bean` methods, the direct and clearest placement is on **the factory method itself**.

## 5. Running tests: `@Primary` selects a bean but does not delete beans

The lab below uses **Java 17**, **Spring Boot 3.3.5**, **JUnit 5**, and `ApplicationContextRunner`. It verifies that one application can contain two beans while injection still picks the primary one. Then it alters the fallback condition to show the difference in **how many beans are actually registered**.

### 5.1. Create a Maven project

Structure:

```text
primary-vs-default-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── PrimaryAndDefaultBeanTest.java
```

Contents of `pom.xml`:

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
    <artifactId>primary-vs-default-demo</artifactId>
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

### 5.2. Write the complete test

Create `src/test/java/demo/PrimaryAndDefaultBeanTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

class PrimaryAndDefaultBeanTest {

    interface Formatter {
        String format(String text);
    }

    static final class CustomFormatter implements Formatter {
        @Override
        public String format(String text) {
            return "custom:" + text;
        }
    }

    static final class DefaultFormatter implements Formatter {
        @Override
        public String format(String text) {
            return "default:" + text;
        }
    }

    record Selection(String value) {
    }

    @Configuration(proxyBeanMethods = false)
    static class UserPrimaryConfiguration {
        @Bean
        @Primary
        CustomFormatter customFormatter() {
            return new CustomFormatter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserWithoutPrimaryConfiguration {
        @Bean
        CustomFormatter customFormatter() {
            return new CustomFormatter();
        }
    }

    @AutoConfiguration
    static class UnconditionalDefaultAutoConfiguration {
        @Bean
        DefaultFormatter defaultFormatter() {
            return new DefaultFormatter();
        }
    }

    @AutoConfiguration
    static class InterfaceFallbackAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(Formatter.class)
        DefaultFormatter defaultFormatter() {
            return new DefaultFormatter();
        }
    }

    @AutoConfiguration
    static class ConcreteFallbackAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(DefaultFormatter.class)
        DefaultFormatter defaultFormatter() {
            return new DefaultFormatter();
        }
    }

    @AutoConfiguration(after = UnconditionalDefaultAutoConfiguration.class)
    static class SingleCandidateAutoConfiguration {
        @Bean
        @ConditionalOnSingleCandidate(Formatter.class)
        Selection selection(Formatter formatter) {
            return new Selection(formatter.format("hello"));
        }
    }

    @Test
    void primaryChoosesSingleInjectionButLeavesDefaultBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        UnconditionalDefaultAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Formatter.class))
                            .containsKeys("customFormatter", "defaultFormatter")
                            .hasSize(2);
                    assertThat(context.getBean(Formatter.class))
                            .isInstanceOf(CustomFormatter.class);
                    assertThat(context.getBean("defaultFormatter"))
                            .isInstanceOf(DefaultFormatter.class);
                });
    }

    @Test
    void fallbackByInterfaceBacksOffEvenIfUserBeanIsPrimary() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        InterfaceFallbackAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(Formatter.class);
                    assertThat(context).doesNotHaveBean("defaultFormatter");
                    assertThat(context.getBean(Formatter.class))
                            .isInstanceOf(CustomFormatter.class);
                });
    }

    @Test
    void fallbackByInterfaceAlsoBacksOffWithoutPrimary() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserWithoutPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        InterfaceFallbackAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Formatter.class);
                    assertThat(context).doesNotHaveBean("defaultFormatter");
                });
    }

    @Test
    void fallbackByConcreteTypeStillCreatesDefaultBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        ConcreteFallbackAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Formatter.class)).hasSize(2);
                    assertThat(context).hasBean("defaultFormatter");
                    assertThat(context.getBean(Formatter.class))
                            .isInstanceOf(CustomFormatter.class);
                });
    }

    @Test
    void fallbackCreatesDefaultWhenNoUserBeanExists() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        InterfaceFallbackAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Formatter.class);
                    assertThat(context.getBean(Formatter.class))
                            .isInstanceOf(DefaultFormatter.class);
                });
    }

    @Test
    void singleCandidateConditionCanUsePrimaryAmongTwoBeans() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        UnconditionalDefaultAutoConfiguration.class,
                        SingleCandidateAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Formatter.class)).hasSize(2);
                    assertThat(context).hasSingleBean(Selection.class);
                    assertThat(context.getBean(Selection.class).value())
                            .isEqualTo("custom:hello");
                });
    }

    @Test
    void singleCandidateConditionDoesNotMatchTwoNonPrimaryBeans() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserWithoutPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        UnconditionalDefaultAutoConfiguration.class,
                        SingleCandidateAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Formatter.class)).hasSize(2);
                    assertThat(context).doesNotHaveBean(Selection.class);
                });
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

**Expected result:** all seven tests pass. Maven Surefire typically displays a line like:

```text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
```

The code does not call `System.out.println`, so there is no custom stdout to match; Maven logs may vary by version and environment.

What the assertions verify:

1. A user bean marked `@Primary` is selected for single lookup by `Formatter`, yet the default bean **still exists** if auto-configuration registers it unconditionally.
2. `@ConditionalOnMissingBean(Formatter.class)` **backs off** when `CustomFormatter` already exists; whether that bean has `@Primary` does not change the conclusion.
3. If the condition only looks for `DefaultFormatter`, the presence of `CustomFormatter` does not block registering another `DefaultFormatter`.
4. When no user-declared `Formatter` exists, the interface-based fallback is registered.
5. `@ConditionalOnSingleCandidate(Formatter.class)` is **a different condition**: it can match when multiple beans of the same type exist and one primary is enough to identify a single candidate; without primary, two candidates cause that condition not to match.

The experiment separates branches into multiple `ApplicationContextRunner` instances so beans from one test do not interfere with another. Processing order for `SingleCandidateAutoConfiguration` is declared via `after = UnconditionalDefaultAutoConfiguration.class` so it checks after the default has been added.

## 6. Why might `@ConditionalOnMissingBean` fail to suppress the default?

There are at least four common reasons, and none of them are automatically fixed by `@Primary`.

### 6.1. Auto-configuration lacks an appropriate condition

```java
@Bean
DefaultFormatter defaultFormatter() {
    return new DefaultFormatter();
}
```

This method registers the bean per configuration; `@Primary CustomFormatter` does not block it. You must fix the **registration logic** if you manage that module's bean, or configure a way to disable/exclude the auto-configuration when working with a library.

### 6.2. Condition checks the wrong type

Compare:

```java
// Only skips fallback if this concrete implementation already exists:
@ConditionalOnMissingBean(DefaultFormatter.class)

// Skips fallback if any suitable Formatter already exists:
@ConditionalOnMissingBean(Formatter.class)
```

If the library's contract is "the user may replace it with any implementation of `Formatter`," checking the interface is more appropriate. If the library genuinely needs to register a `DefaultFormatter` even when another formatter exists, checking the concrete implementation reflects a different policy, and may be completely intentional.

### 6.3. Condition only knows bean definitions processed up to that point

`@ConditionalOnMissingBean` **is not a future scan**. It checks bean definitions recognized at evaluation time. Therefore:

- Place the condition in auto-configuration, where application configuration is typically processed first.
- If auto-configuration A supplies a bean and auto-configuration B depends on its presence, declare proper ordering with `@AutoConfiguration(after = ...)` or the corresponding ordering mechanism.
- Expose a sufficiently specific type in the `@Bean` signature. A `@Bean Formatter formatter()` returning `new DefaultFormatter()` does not necessarily allow a condition looking for `DefaultFormatter.class` to know the implementation before the bean is instantiated.

`@Primary` neither adds implementation type information to the factory method signature nor causes an already-evaluated condition to re-run.

### 6.4. Condition has a different search scope than expected

`@ConditionalOnMissingBean` has options such as `value`, `type`, `name`, `annotation`, `ignored`, `search`. A name-based condition differs from a type-based condition. The `search` attribute can limit the bean search scope across parent/child context hierarchies.

Example:

```java
@ConditionalOnMissingBean(name = "defaultFormatter")
```

This checks for the absence of the **name** `defaultFormatter`, not the absence of all `Formatter` implementations. A `customFormatter` bean, even with `@Primary`, will not make this name-based condition fail.

When parent contexts or non-autowire-candidate beans are involved, check the exact API for your version and inspect the Condition Evaluation Report; do not guess solely from the `@Primary` annotation.

## 7. `@ConditionalOnSingleCandidate`: where `@Primary` actually affects a condition

`@ConditionalOnSingleCandidate(Formatter.class)` answers the question:

> "At evaluation time, can Spring determine a single candidate to inject for `Formatter`?"

If **exactly one** matching bean exists, the condition matches. If **multiple beans** exist and a suitable primary bean is present, the condition can also match. If multiple equal candidates exist, the condition normally does not match.

This differs from `@ConditionalOnMissingBean`, which asks whether a matching bean already exists:

| Condition | Given `CustomFormatter @Primary` + `DefaultFormatter` | Meaning |
| --- | --- | --- |
| `@ConditionalOnMissingBean(Formatter.class)` | Does not match | Because a `Formatter` bean already exists |
| `@ConditionalOnBean(Formatter.class)` | Matches | Because a `Formatter` bean already exists |
| `@ConditionalOnSingleCandidate(Formatter.class)` | Can match | Because a primary resolves a single candidate |
| Injecting one `Formatter` without qualifier | Usually chooses custom | Due to primary preference |
| Injecting `List<Formatter>` | Usually contains both | Primary does not automatically filter collections |

Thus, `@Primary` **can serve as a signal for a single-candidate condition**, yet it **is not a condition that deletes fallbacks**. When using `@ConditionalOnSingleCandidate`, you must still ensure auto-configuration ordering and type inferability.

## 8. Three different replacement goals and their matching mechanisms

### Goal A: Keep multiple implementations but pick one default during injection

Use `@Primary` or `@Qualifier`:

```java
@Bean
@Primary
Formatter customFormatter() {
    return new CustomFormatter();
}
```

If both default and custom are needed across different flows, this can be a sound design. Consumers receiving collections can still see both.

### Goal B: Do not create the starter's fallback when a user bean exists

Place a condition on the default bean in the auto-configuration you control:

```java
@Bean
@ConditionalOnMissingBean(Formatter.class)
DefaultFormatter defaultFormatter() {
    return new DefaultFormatter();
}
```

With return type `DefaultFormatter`, the container has concrete type info; with target condition `Formatter.class`, the fallback backs off for another implementation of the interface. Both design decisions are stated explicitly.

### Goal C: Disable a specific auto-configuration completely

When you do not want a Spring Boot auto-configuration to participate, **exclude** that specific auto-configuration class:

```java
@SpringBootApplication(
    exclude = SomeLibraryAutoConfiguration.class
)
public class Application {
}
```

This is an illustrative snippet, requiring an actual `SomeLibraryAutoConfiguration` class, and is not a standalone runnable program. In a real application, exclude the real auto-configuration published as excludable; do not use a dummy class name.

Another way is declaring the configuration class name to exclude via:

```properties
spring.autoconfigure.exclude=com.example.library.SomeLibraryAutoConfiguration
```

This configuration line is also illustrative: the class must match the library in use. Do not arbitrarily exclude configurations containing other infrastructure without reviewing the impact. If the starter provides an official on/off property, prefer that mechanism when suitable.

**Do not confuse with bean definition overriding:** two differently named beans sharing an interface can coexist without enabling `spring.main.allow-bean-definition-overriding`. Allowing name-based overriding does not generally solve having two beans of the same type.

## 9. How to diagnose when "marked `@Primary` yet the default bean still exists"

Check in order:

1. **Count and list beans by type.** `applicationContext.getBeansOfType(Formatter.class)` shows the actual bean count and names after the context initializes.
2. **Identify which bean is primary.** Check `@Primary` on `@Bean`/component methods or bean definition metadata; do not infer it from bean names.
3. **Identify the injection point.** Is it a single dependency, `List`, `Map`, `ObjectProvider`, or a dependency with `@Qualifier`? Candidate selection varies accordingly.
4. **Read the default-creation logic.** Does it lack conditions, use `@ConditionalOnMissingBean` by interface, implementation, or name, or have other conditions?
5. **Check ordering and return types.** When the condition ran, had the user bean or earlier auto-config bean been recognized yet? Does the `@Bean` signature expose the type the condition checks?
6. **Read the Condition Evaluation Report** using `--debug`, Actuator `/actuator/conditions` if suitably enabled/exposed, or a listener in `ApplicationContextRunner`. Look at `OnBeanCondition` outcomes to see why the fallback registered.
7. **Write minimal tests** for both cases: without a user bean and with a user bean. If tests require multiple beans, add tests asserting `@Primary` only governs injection.

Example checking beans after startup in an existing context:

```java
Map<String, Formatter> beans =
        applicationContext.getBeansOfType(Formatter.class);

beans.forEach((name, bean) ->
        System.out.println(name + " = " + bean.getClass().getSimpleName()));
```

This is an illustrative snippet inside a Java method, requiring an `applicationContext` variable of type `ApplicationContext` and the application's `Formatter` interface. Bean names and iteration order should not be relied upon as a default ordering contract; checking membership by name and type is more stable.

## 10. Common mistakes

**Mistake 1 — "I added `@Primary`, so Boot won't create the default bean."**  
False, because `@Primary` controls injection priority, not bean registration policy. Check `@ConditionalOnMissingBean` and the starter's conditions.

**Mistake 2 — "Having two beans with the same interface definitely breaks startup."**  
Not necessarily. Two beans of the same type can coexist normally; errors usually appear when a single-valued injection point cannot resolve a unique candidate. Primary or qualifiers can disambiguate the dependency.

**Mistake 3 — "`@ConditionalOnMissingBean(DefaultFormatter.class)` backs off for every `Formatter` implementation."**  
No. It only checks for `DefaultFormatter`. To apply an "any formatter" policy, check `Formatter.class`.

**Mistake 4 — "All Spring Boot default beans vanish when you create a primary bean."**  
No. Different auto-configurations and beans have different conditions, and primary is not a global off switch.

**Mistake 5 — "Just enable `spring.main.allow-bean-definition-overriding=true`."**  
This flag deals with duplicate-name bean definitions; it does not automatically remove differently named beans sharing an interface and can mask design flaws.

**Mistake 6 — "A `List<Formatter>` will only contain the primary bean."**  
No. Collection dependencies normally include all eligible beans per resolution rules, rather than filtering to only primary.

**Mistake 7 — "Adding `@Primary` fixes every `NoUniqueBeanDefinitionException`."**  
No. If multiple primaries exist, qualifiers conflict, bean types mismatch, or an injection point expects another selection, it can still fail.

## 11. Self-check questions

**Question 1.** Auto-configuration has an unconditional `@Bean DefaultFormatter defaultFormatter()`. The user adds `@Primary CustomFormatter customFormatter()`. How many `Formatter` beans exist?  
**Answer:** Normally **two**. `@Primary` decides the preferred candidate for single injection; it does not delete `defaultFormatter`.

**Question 2.** Change the default factory to `@ConditionalOnMissingBean(Formatter.class)`. Does the default still appear when custom exists and is recognized before the condition?  
**Answer:** No. The interface-based condition does not match because `Formatter` already exists; this effect **does not require** custom to be `@Primary`.

**Question 3.** What if the condition is `@ConditionalOnMissingBean(DefaultFormatter.class)` instead?  
**Answer:** `CustomFormatter` does not match `DefaultFormatter`, so the default bean **can still be registered**. Two beans exist; primary can still win for single `Formatter` injection.

**Question 4.** When two `Formatter` beans exist and one is primary, can `@ConditionalOnSingleCandidate(Formatter.class)` match?  
**Answer:** Yes, because one primary allows a single candidate to be resolved. This condition differs from `@ConditionalOnMissingBean`.

**Question 5.** If a consumer must receive the exact default bean despite another bean being primary, what should be used?  
**Answer:** Use `@Qualifier` or another explicit compatible bean selector at the injection point; do not try removing `@Primary` from unrelated beans.

**Question 6.** To remove a library's entire auto-configuration, where should `@Primary` be placed?  
**Answer:** Do not use `@Primary` for this purpose. Use the library's official configuration/condition mechanisms or exclude the specific auto-configuration after checking affected beans.

## 12. Knowledge summary

`@Primary` is responsible for **prioritizing bean selection** from a set of candidates when injecting a single-valued dependency. It **does not govern how many beans are registered** and does not automatically remove other default beans.

To design Spring Boot customizability properly:

1. Define the replacement contract: by **interface**, **implementation**, or **name**.
2. Place an appropriate `@ConditionalOnMissingBean` on the fallback configuration, control processing order, and declare informative return types.
3. Use `@Primary` when the goal is prioritizing one bean among multiple coexisting beans.
4. Use `@ConditionalOnSingleCandidate` when the condition requires "a single autowire candidate can be determined," taking primary into account.
5. Use properties or auto-configuration exclusion when the goal is disabling registration completely, rather than misusing `@Primary` as an off switch.

### Official references

- [Spring Framework — Fine-tuning Annotation-based Autowiring with `@Primary`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Javadoc `@Primary`](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/annotation/Primary.html)
- [Spring Boot — Creating Your Own Auto-configuration, Bean Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Javadoc `@ConditionalOnMissingBean`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.3 — Javadoc `@ConditionalOnSingleCandidate`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html)
