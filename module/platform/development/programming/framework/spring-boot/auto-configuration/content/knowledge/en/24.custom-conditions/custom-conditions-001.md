# Testing `@Primary` and Multiple Candidates Without a Primary

**Topic:** Spring Boot Auto Configuration  
**Knowledge Group:** Test Matrix  
**Objective:** Verify how Spring selects a bean when an injection point has multiple candidates of the same type. This lesson focuses on a single candidate, multiple candidates with a single `@Primary`, multiple candidates without a primary, multiple primaries, `@Qualifier`, and collection injection.

## 1. Multiple Beans of the Same Type Is a Valid Situation

Spring allows an `ApplicationContext` to contain multiple beans implementing the same interface. For example, a notification system that supports both email and SMS:

```java
public interface MessageSender {
    void send(String message);
}
```

Both implementations can coexist:

```java
@Component
class EmailSender implements MessageSender {
    @Override
    public void send(String message) {
        // Send email
    }
}

@Component
class SmsSender implements MessageSender {
    @Override
    public void send(String message) {
        // Send SMS
    }
}
```

The issue only arises when a consumer requires **a single value**:

```java
@Service
class NotificationService {

    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = sender;
    }
}
```

If the context has only one matching `MessageSender`, Spring injects that bean. If there are multiple beans, Spring needs additional metadata to determine the candidate. When it cannot uniquely choose one, creating the consumer fails with `NoUniqueBeanDefinitionException` (often wrapped in `UnsatisfiedDependencyException` or `BeanCreationException`).

Therefore, two ideas must be separated:

- Multiple beans of the same type: valid, and may be intentional.
- A single injection point requiring one bean while multiple equal candidates remain: cannot be resolved and can cause context startup to fail.

## 2. `@Primary` Marks the Preferred Bean for Single Injection

`@Primary` marks a bean as the preferred candidate when Spring must inject a single dependency and multiple candidates of the same type exist.

The annotation can be placed on a component:

```java
@Component
@Primary
class EmailSender implements MessageSender {
    // ...
}
```

Or on a `@Bean` method:

```java
@Configuration(proxyBeanMethods = false)
class SenderConfiguration {

    @Bean
    @Primary
    MessageSender emailSender() {
        return new EmailSender();
    }

    @Bean
    MessageSender smsSender() {
        return new SmsSender();
    }
}
```

When a bean requests `MessageSender` without any other qualifier, `emailSender` is chosen because it is the only candidate annotated with `@Primary`.

`@Primary` has the following characteristics:

1. It affects dependency resolution for single-valued injection points.
2. It does not remove, disable, or exclude the remaining bean(s) from the `ApplicationContext`.
3. It does not change the bean name.
4. It does not register a bean by itself; the bean must still be created via component scanning, `@Bean`, or another registration mechanism.
5. It does not replace `@ConditionalOnMissingBean` in auto-configuration.
6. It does not filter candidates when a consumer requests a collection.

If no injection point requires a single-valued `MessageSender`, both beans can coexist without causing ambiguity.

### 2.1. When Should a Primary Be Chosen?

Use `@Primary` when there is a sensible default implementation for most consumers in the application, for example:

- A default production `Clock`.
- A default `PaymentGateway`.
- A default `ObjectMapper`.
- A default notification channel when most services use the same channel.

If each consumer has different business requirements, a global primary can mask the wrong selection. In that case, `@Qualifier` at each injection point expresses intent more clearly.

## 3. No `@Primary` with Multiple Candidates

Suppose the configuration registers:

```java
@Bean
MessageSender emailSender() {
    return new EmailSender();
}

@Bean
MessageSender smsSender() {
    return new SmsSender();
}
```

Another bean requires:

```java
@Bean
NotificationService notificationService(MessageSender sender) {
    return new NotificationService(sender);
}
```

If there is no qualifier and no other metadata sufficient to uniquely choose one, Spring does not guess between email and SMS. The result is `NoUniqueBeanDefinitionException`.

The message may look like:

```text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'MessageSender' available:
expected single matching bean but found 2
```

The full exception depends on the injection point and Spring version. When diagnosing, look for `NoUniqueBeanDefinitionException` in the `Caused by` chain, then identify which consumer is requesting a single bean and the list of candidates Spring found.

### 3.1. Having Multiple Beans Does Not Always Break the Context

This example can still start normally:

```java
@Configuration(proxyBeanMethods = false)
class SenderConfiguration {

    @Bean
    MessageSender emailSender() {
        return new EmailSender();
    }

    @Bean
    MessageSender smsSender() {
        return new SmsSender();
    }
}
```

If no bean requires a single `MessageSender`, Spring does not need to select a unique candidate. Each bean can be retrieved by name or both can be injected as a collection.

This is a key point to verify in tests: to prove ambiguity, you must create an injection point that actually requires a single-valued bean. Merely asserting that the context has two beans of the same type is not enough to demonstrate the error.

### 3.2. Other Information That Can Help Resolution

`@Primary` is not the only signal. Depending on the injection point, Spring can also consider qualifiers, priority metadata, and the dependency/bean name if matching information is available.

However, do not rely on `@Bean` method declaration order, component scan order, or accidental variable names to select an implementation. When business requirements are specific, use `@Qualifier` to make the choice explicit. That ensures refactoring variable names or reordering configuration does not cause unintended behavior changes.

## 4. `@Qualifier` Selects a Candidate at Each Injection Point

`@Qualifier` narrows the candidate set for a specific consumer:

```java
@Service
class NotificationService {

    private final MessageSender sender;

    NotificationService(
            @Qualifier("smsSender") MessageSender sender) {
        this.sender = sender;
    }
}
```

If beans named `emailSender` and `smsSender` exist, this injection point requests `smsSender`.

A qualifier can also be placed on the bean:

```java
@Bean
@Qualifier("urgent")
MessageSender smsSender() {
    return new SmsSender();
}
```

and requested at the consumer:

```java
@Bean
NotificationService notificationService(
        @Qualifier("urgent") MessageSender sender) {
    return new NotificationService(sender);
}
```

A qualifier does not have to be just a bean name. You can define a custom qualifier annotation with attributes, such as `@Region("asia")`, to group candidates by business semantics.

### 4.1. `@Qualifier` Working Together with `@Primary`

Suppose `emailSender` is primary, but a consumer has `@Qualifier("smsSender")`. The consumer still receives the SMS sender because the qualifier requests a specific candidate.

You can use a global default with `@Primary`, and then use qualifiers in services that have specific requirements. Keep qualifiers stable and meaningful; avoid scattering concrete implementation names across the application if a business-oriented qualifier is clearer.

## 5. `@Primary` Does Not Filter Collection Injection

This is the most important difference between single injection and multi-candidate injection.

When a consumer requests:

```java
@Bean
SenderRegistry senderRegistry(List<MessageSender> senders) {
    return new SenderRegistry(senders);
}
```

Spring puts all beans matching the `MessageSender` type into the list, including beans not marked as primary.

Collection injection commonly supports:

```java
MessageSender[] senders;
List<MessageSender> senders;
Set<MessageSender> senders;
Map<String, MessageSender> sendersByBeanName;
```

With `Map<String, MessageSender>`, the key is the bean name and the value is the corresponding bean. `@Primary` does not exclude other beans from a list, set, array, or map.

If ordering in a list/array is needed, use `@Order` or `Ordered`:

```java
@Bean
@Order(1)
MessageSender emailSender() {
    return new EmailSender();
}

@Bean
@Order(2)
MessageSender smsSender() {
    return new SmsSender();
}
```

`@Order` can sort candidates in collection injection. It does not make a bean primary and does not resolve ambiguity for single injection. The first element of a list does not automatically become the bean injected into a single parameter.

## 6. Two Beans Both Annotated with `@Primary`

For an injection point without a qualifier, if multiple eligible candidates are both annotated with `@Primary`, Spring still does not have a single primary to choose from. This case continues to cause `NoUniqueBeanDefinitionException`.

Example configuration to avoid:

```java
@Bean
@Primary
MessageSender emailSender() {
    return new EmailSender();
}

@Bean
@Primary
MessageSender smsSender() {
    return new SmsSender();
}
```

How to handle this:

- Mark only one implementation as the default.
- Use qualifiers at injection points that need a specific selection.
- Split the interface if the two implementations actually have different roles.
- Use a strategy/factory if the decision depends on runtime data rather than a fixed default.

Do not use `@Order` to resolve multiple primaries. The two annotations serve two different purposes.

## 7. Distinguishing `@Primary` from `@ConditionalOnMissingBean`

In Spring Boot auto-configuration, these two annotations often appear near each other but address two different phases:

| Annotation | Phase | Role |
| --- | --- | --- |
| `@ConditionalOnMissingBean` | Bean definition registration of auto-configuration | Creates a fallback only if no matching bean exists yet |
| `@Primary` | Dependency resolution during injection | Selects the preferred candidate for a single dependency |
| `@Qualifier` | Dependency resolution at the injection point | Narrows candidates according to a specific requirement |
| `@Order` | Ordering ordered components/collections | Controls order, does not select primary |

Example:

```java
@AutoConfiguration
class SenderAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    @Primary
    MessageSender defaultMessageSender() {
        return new EmailSender();
    }
}
```

`@ConditionalOnMissingBean` decides whether to create the fallback. If the application has already provided a `MessageSender` that the condition recognizes, the fallback is not registered. `@Primary` only matters after beans have been registered and Spring needs to pick a candidate.

If auto-configuration accidentally creates another bean of the same type without a back-off condition, marking that bean `@Primary` only affects injection selection; it does not prevent the application's bean from existing or automatically remove the other bean.

## 8. Required Test Matrix

| Scenario | Bean candidates | Injection point | Result |
| --- | --- | --- | --- |
| Single candidate | One sender | `MessageSender` | Injects the single sender |
| Multiple candidates, one primary | Email primary, SMS regular | `MessageSender` | Injects email |
| Multiple candidates, no primary | Email, SMS | `MessageSender` | Ambiguous if no other signal exists |
| Multiple candidates, qualifier | Email primary, SMS regular | `@Qualifier("smsSender") MessageSender` | Injects SMS |
| Two primaries | Email primary, SMS primary | `MessageSender` without qualifier | Ambiguous |
| Collection with primary | Email primary, SMS regular | `List<MessageSender>` | Receives both |
| Multiple beans, no single consumer | Email, SMS | No single injection | Context can still start |

A good test should verify both sides: which bean is injected into the single consumer and which beans remain in the context/collection.

## 9. Runnable Example: Java 17, Spring Boot 3.3.13, and `ApplicationContextRunner`

The following small Maven project tests five scenarios: single candidate, primary, no primary, qualifier, and two primaries. The primary test also verifies that collection injection still receives both implementations.

### 9.1. Project Structure

```text
primary-candidate-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── PrimaryCandidateResolutionTest.java
```

### 9.2. `pom.xml`

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
    <artifactId>primary-candidate-demo</artifactId>
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

### 9.3. `PrimaryCandidateResolutionTest.java`

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

import static org.assertj.core.api.Assertions.assertThat;

class PrimaryCandidateResolutionTest {

    interface MessageSender {
        String channel();
    }

    static class EmailSender implements MessageSender {
        @Override
        public String channel() {
            return "email";
        }
    }

    static class SmsSender implements MessageSender {
        @Override
        public String channel() {
            return "sms";
        }
    }

    record NotificationService(MessageSender sender) {
    }

    record SenderRegistry(List<MessageSender> senders) {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void aSingleCandidateIsInjectedWithoutPrimary() {
        this.runner
                .withUserConfiguration(SingleCandidateConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(MessageSender.class);
                    assertThat(context.getBean(NotificationService.class)
                            .sender().channel()).isEqualTo("email");
                });
    }

    @Test
    void primaryWinsForSingleInjectionButOtherBeanRemainsInCollection() {
        this.runner
                .withUserConfiguration(PrimaryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(NotificationService.class);

                    NotificationService service =
                            context.getBean(NotificationService.class);

                    assertThat(service.sender().channel()).isEqualTo("email");
                    assertThat(context.getBeansOfType(MessageSender.class))
                            .hasSize(2);

                    SenderRegistry registry =
                            context.getBean(SenderRegistry.class);

                    assertThat(registry.senders().stream()
                            .map(MessageSender::channel)
                            .toList())
                            .containsExactly("email", "sms");
                });
    }

    @Test
    void multipleCandidatesWithoutPrimaryFailSingleInjection() {
        this.runner
                .withUserConfiguration(AmbiguousConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    NoUniqueBeanDefinitionException.class);
                });
    }

    @Test
    void qualifierSelectsSmsEvenWhenEmailIsPrimary() {
        this.runner
                .withUserConfiguration(QualifiedConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBean(NotificationService.class)
                            .sender().channel()).isEqualTo("sms");
                });
    }

    @Test
    void twoPrimaryCandidatesAreStillAmbiguous() {
        this.runner
                .withUserConfiguration(TwoPrimaryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    NoUniqueBeanDefinitionException.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class SingleCandidateConfiguration {

        @Bean
        MessageSender emailSender() {
            return new EmailSender();
        }

        @Bean
        NotificationService notificationService(MessageSender sender) {
            return new NotificationService(sender);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryConfiguration {

        @Bean
        @Primary
        @Order(1)
        MessageSender emailSender() {
            return new EmailSender();
        }

        @Bean
        @Order(2)
        MessageSender smsSender() {
            return new SmsSender();
        }

        @Bean
        NotificationService notificationService(MessageSender sender) {
            return new NotificationService(sender);
        }

        @Bean
        SenderRegistry senderRegistry(List<MessageSender> senders) {
            return new SenderRegistry(senders);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AmbiguousConfiguration {

        @Bean
        MessageSender emailSender() {
            return new EmailSender();
        }

        @Bean
        MessageSender smsSender() {
            return new SmsSender();
        }

        @Bean
        NotificationService notificationService(MessageSender sender) {
            return new NotificationService(sender);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class QualifiedConfiguration {

        @Bean
        @Primary
        MessageSender emailSender() {
            return new EmailSender();
        }

        @Bean
        MessageSender smsSender() {
            return new SmsSender();
        }

        @Bean
        NotificationService notificationService(
                @Qualifier("smsSender") MessageSender sender) {
            return new NotificationService(sender);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoPrimaryConfiguration {

        @Bean
        @Primary
        MessageSender emailSender() {
            return new EmailSender();
        }

        @Bean
        @Primary
        MessageSender smsSender() {
            return new SmsSender();
        }

        @Bean
        NotificationService notificationService(MessageSender sender) {
            return new NotificationService(sender);
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

Expected result:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

Maven Surefire may also display timing and test names depending on the plugin version. The tests do not write custom stdout.

### 9.4. Meaning of the Five Tests

| Test | What is proven |
| --- | --- |
| `aSingleCandidateIsInjectedWithoutPrimary` | A single candidate does not require `@Primary` |
| `primaryWinsForSingleInjectionButOtherBeanRemainsInCollection` | Primary is injected singly; the collection still receives both beans ordered by `@Order` |
| `multipleCandidatesWithoutPrimaryFailSingleInjection` | Two candidates without a resolution signal cause single injection to fail |
| `qualifierSelectsSmsEvenWhenEmailIsPrimary` | A qualifier can request a candidate other than the primary |
| `twoPrimaryCandidatesAreStillAmbiguous` | Multiple eligible primaries do not produce a unique selection |

The collection test is direct evidence that `@Primary` is not a bean filter. The ambiguity test also shows that two beans of the same type can coexist; the failure only occurs when a consumer requests a single unique bean.

## 10. How to Diagnose `NoUniqueBeanDefinitionException`

When context startup fails due to multiple candidates:

1. Identify the consumer bean being created.
2. Find the constructor parameter, field, or method parameter requiring a single-valued type.
3. Read the dependency type and the candidate list in the exception.
4. Check whether a qualifier is missing, has the wrong value, or does not match any bean.
5. Check whether the candidates have a single primary.
6. If there are multiple primaries, keep one default or use a qualifier to narrow down.
7. If the choice depends on the use case, design a qualifier/strategy instead of choosing a global default.
8. If the consumer needs all implementations, change the dependency to an appropriate collection.

An example error may be wrapped as follows:

```text
UnsatisfiedDependencyException
  caused by NoUniqueBeanDefinitionException:
  expected single matching bean but found 2:
  emailSender, smsSender
```

The exact format and bean names depend on the configuration. Rely on the root cause and injection point rather than line numbers or exact message text.

Do not fix this by mechanically adding `@Primary`. If an OTP-sending service must use SMS, the qualifier `smsSender` is a more accurate contract than hoping SMS becomes primary in every context.

## 11. Common Misconceptions

**Misconception 1: Having two beans implementing the same interface is an error.**  
False. Spring allows multiple implementations to coexist. The error occurs when a single dependency cannot uniquely select one.

**Misconception 2: `@Primary` removes the remaining bean.**  
False. The remaining bean still exists in the context and can be retrieved by name, qualifier, or collection.

**Misconception 3: `@Primary` reduces a list to a single element.**  
False. Collections receive all matching candidates; primary only affects single-valued selection.

**Misconception 4: `@Order(1)` is equivalent to `@Primary`.**  
False. Order sorts collections/ordered processing; primary selects the preferred candidate for a single dependency.

**Misconception 5: With two primary beans, Spring picks the one declared first.**  
Do not rely on declaration order. If multiple primaries remain eligible for a single injection, add a qualifier or redesign.

**Misconception 6: `@ConditionalOnMissingBean` and `@Primary` are the same.**  
False. The condition decides whether a fallback bean is registered; primary only participates in bean selection after the beans already exist.

**Misconception 7: A context that starts proves the right bean for the business logic was chosen.**  
False. A primary can allow the context to start while the service still uses the wrong implementation. Tests must assert the actual injected bean.

## 12. Design and Testing Checklist

- [ ] Determine whether the consumer needs one implementation or all implementations.
- [ ] If a default is needed, mark only one eligible candidate with `@Primary`.
- [ ] If the choice depends on each consumer, use `@Qualifier`.
- [ ] If all candidates are needed, use `List`, `Set`, an array, or `Map<String, T>`.
- [ ] If collection ordering matters, use `@Order`/`Ordered`.
- [ ] Test the single-candidate case.
- [ ] Test multiple candidates with one primary.
- [ ] Test multiple candidates without a primary and verify the root cause.
- [ ] Test a qualifier selecting a non-primary bean.
- [ ] Test multiple eligible primaries.
- [ ] Test that collections still contain all required beans.
- [ ] For auto-configuration, also verify `@ConditionalOnMissingBean` so an application-provided bean causes the fallback to back off.

## 13. Self-Check Questions

**Question 1.** A context has two `MessageSender` beans, one of which is annotated with `@Primary`. Which bean does a constructor requiring `MessageSender` receive?  
**Answer:** The single primary bean among the eligible candidates.

**Question 2.** There are two beans of the same type, no primary or qualifier, and a constructor requires one bean. What happens?  
**Answer:** Spring cannot uniquely select one and the context fails with `NoUniqueBeanDefinitionException` (typically wrapped in a bean creation exception).

**Question 3.** There is one primary and one regular bean. How many beans does `List<MessageSender>` receive?  
**Answer:** Both eligible candidates; `@Primary` does not filter collections.

**Question 4.** Email is primary, but the injection point has `@Qualifier("smsSender")`. Which bean is injected?  
**Answer:** The SMS sender, because the qualifier requests a specific candidate.

**Question 5.** Two beans of the same type are both annotated with `@Primary`. Can you rely on declaration order to pick one?  
**Answer:** No. If both remain eligible and there is no other resolution signal, single injection remains ambiguous.

**Question 6.** Does `@Order(1)` make a bean primary?  
**Answer:** No. `@Order` controls ordering; `@Primary` controls single-candidate selection.

**Question 7.** How does `@ConditionalOnMissingBean` differ from `@Primary`?  
**Answer:** The condition decides whether to register a fallback; primary marks an already-registered bean as the preferred candidate for single injection.

## 14. Key Principles to Remember

- Multiple beans of the same type are valid; ambiguity only arises when an injection point needs a single bean and Spring cannot resolve it.
- `@Primary` selects the preferred candidate for single injection; it does not remove other beans.
- Multiple candidates without a primary can cause `NoUniqueBeanDefinitionException` if qualifiers or other metadata do not resolve it.
- `@Qualifier` expresses selection at each injection point and can request a bean other than the primary.
- `List`, `Set`, arrays, and `Map<String, T>` receive all eligible candidates; `@Primary` does not filter collections.
- `@Order` sorts collections in cases Spring supports; it does not replace `@Primary`.
- Multiple eligible primaries do not produce a unique selection.
- Use `@ConditionalOnMissingBean` for auto-configuration back-off; use `@Primary` for candidate resolution.

### Official References

- [Spring Framework — Using `@Primary` to Fine-tune Autowiring](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Autowired Collections and Ordering](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Framework API — `NoUniqueBeanDefinitionException`](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/NoUniqueBeanDefinitionException.html)
