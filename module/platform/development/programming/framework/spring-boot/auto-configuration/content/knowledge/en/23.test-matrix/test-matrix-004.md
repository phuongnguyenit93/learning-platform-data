# Testing `@Primary` and Multiple Candidates Without a Primary

**Topic:** Spring Boot Auto Configuration  
**Knowledge Group:** Test Matrix  
**Goal:** Understand how Spring Framework selects a bean when an injection point has multiple candidates of the same type; verify `@Primary`, no primary bean, multiple beans marked primary, `@Qualifier`, and collection injection through isolated tests.

## 1. Why can a type have multiple beans?

A Spring application often has multiple implementations of the same interface. For example, a notification-sending application may support email and SMS:

```java
public interface MessageSender {
    void send(String message);
}
```

Both implementations are valid:

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

If a service requires exactly one `MessageSender`:

```java
@Service
class NotificationService {

    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = sender;
    }
}
```

Spring must decide which implementation to inject. When the context has only one matching candidate, the choice is clear. When there are multiple candidates, Spring needs additional information to resolve it.

If there is not enough information to select a unique bean, the context typically fails when creating the consuming bean with `NoUniqueBeanDefinitionException`. This is a dependency resolution error, not an error in creating two beans of the same type: Spring allows a context to contain multiple beans implementing the same interface.

## 2. `@Primary` marks the preferred candidate

`@Primary` marks a bean as the preferred choice when Spring needs to inject **a single value** and multiple matching candidates exist.

The annotation can be placed on a component class:

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

In the example above, when a constructor requires `MessageSender`, Spring chooses `emailSender` because it is the sole candidate marked `@Primary`.

Key points to remember:

- `@Primary` does not delete or disable the remaining beans.
- Both `emailSender` and `smsSender` still exist in `ApplicationContext`.
- `@Primary` does not change bean names. For `@Bean`, the default name is usually the method name; for component scanning, the default name is derived from the class name.
- `@Primary` is metadata for dependency resolution; it is not a conditional bean-registration mechanism and does not replace `@ConditionalOnMissingBean`.
- If the application needs a specific implementation per use case, `@Qualifier` can be used instead of choosing a global default.

### 2.1. When is `@Primary` appropriate?

Use `@Primary` when one implementation is a sensible default for most injection points in the application.

Examples:

- Multiple `PaymentGateway` beans exist, and Stripe is the default gateway.
- Multiple `Clock` beans exist, and the production application uses the system clock.
- Multiple `MessageSender` beans exist, and email is the default channel.
- Multiple `ObjectMapper` beans exist, and one mapper is the default for services that do not require custom configuration.

Do not add `@Primary` just to make the context start if business logic actually requires each service to pick a different implementation. In that case, a qualifier expresses intent more clearly.

## 3. When there is no `@Primary` and multiple candidates exist

Suppose the context has:

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

and a bean requests:

```java
@Bean
NotificationService notificationService(MessageSender sender) {
    return new NotificationService(sender);
}
```

Both beans are valid candidates. There is no qualifier, no primary candidate, and no other resolution hint sufficient to select uniquely. Spring should not guess between email and SMS; picking the wrong one could alter business behavior.

The result is an error like:

```text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'MessageSender' available:
expected single matching bean but found 2
```

The full message may be wrapped in `UnsatisfiedDependencyException` or `BeanCreationException`, depending on the injection point and initialization timing. Look for `NoUniqueBeanDefinitionException` in the `Caused by` chain.

### 3.1. Multiple beans are not always an error

Spring needs a single candidate only for injection points requesting a single value. If the application merely declares two beans and no bean requests a single `MessageSender`, the context can still start.

This example is valid:

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

There is no single-valued consumer, so there is no conflict to resolve yet. The error occurs when Spring must satisfy a single dependency and cannot pick a unique candidate.

### 3.2. What additional information can Spring use?

`@Primary` is an important mechanism, but not the only piece of information. Depending on the injection point and context, Spring can also consider:

1. **Required type:** only beans compatible with the dependency type are candidates.
2. **Qualifier:** narrows candidates according to the requested qualifier.
3. **Primary:** prioritizes the candidate marked `@Primary` among the remaining matching beans.
4. **Priority:** priority metadata such as `@Priority` can participate in resolution where applicable.
5. **Dependency/bean name:** parameter or field names can help select a matching bean name if parameter-name metadata is retained and resolution rules permit it.

Do not rely on parameter names as a substitute for an explicit contract. With Java 17, you can enable the `-parameters` compiler option to preserve parameter names; however, `@Qualifier` is usually easier to read and more stable across variable renames or refactors.

If multiple tied candidates remain after these resolution steps, Spring throws `NoUniqueBeanDefinitionException`. Do not treat bean declaration order or component scan order as a default selection rule.

## 4. `@Qualifier` selects an implementation per injection point

`@Qualifier` lets you request a specific candidate by qualifier or bean name:

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

If the configuration has two beans named `emailSender` and `smsSender`, this injection point requests `smsSender`.

A qualifier can be placed on a bean:

```java
@Bean
@Qualifier("urgent")
MessageSender smsSender() {
    return new SmsSender();
}
```

and requested on the consumer:

```java
@Bean
NotificationService notificationService(
        @Qualifier("urgent") MessageSender sender) {
    return new NotificationService(sender);
}
```

A qualifier does not have to be just a bean name. It can be a custom qualifier annotation with attributes, such as `@Region("asia")`, to describe a group of candidates by application semantics.

### 4.1. How do `@Qualifier` and `@Primary` work together?

Qualifiers narrow the candidate set to the specific requirement of the injection point. `@Primary` selects the preferred candidate within the remaining matching set if multiple candidates still exist.

Example:

- `emailSender` is marked `@Primary`.
- `smsSender` is not primary.
- The consumer has `@Qualifier("smsSender")`.

The consumer receives `smsSender`. `@Primary` does not override an explicit qualifier to force email.

Thus, you can combine a global default via `@Primary` with specialized use cases via `@Qualifier`.

## 5. `@Primary` does not affect collection injection

A very common misconception: `@Primary` resolves single-valued injection; it **does not filter out** other beans when a consumer requests multiple candidates.

Example:

```java
@Bean
SenderRegistry senderRegistry(List<MessageSender> senders) {
    return new SenderRegistry(senders);
}
```

If the context has `emailSender` and `smsSender`, the list receives both, even when email is primary.

The same applies to all forms of collection injection:

```java
MessageSender[] senders;
List<MessageSender> senders;
Set<MessageSender> senders;
Map<String, MessageSender> sendersByBeanName;
```

With `Map<String, MessageSender>`, the key is the bean name and the value is the corresponding bean. All matching candidates are included in the map.

If you need to order beans in an array/list, use `@Order` or `Ordered`:

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

`@Order` controls ordering when Spring builds a candidate list/array in supported cases. It is not synonymous with `@Primary` and is not a way to resolve ambiguity for single-valued injection. An ordered list does not mean the first element automatically becomes primary.

## 6. Multiple beans both marked `@Primary`

Normally, a group of matching candidates for a single injection should have at most one primary candidate.

Anti-pattern example:

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

If a consumer asks for one `MessageSender`, both are marked preferred. Spring still has no basis to choose a single bean. The outcome can continue to be `NoUniqueBeanDefinitionException`.

If two implementations are both marked primary, fix the design in one of these ways:

- Keep only one default with `@Primary`.
- Use `@Qualifier` at injection points that need a specific choice.
- Split the interface by clearer roles if the two implementations serve different contracts.
- Use a factory/strategy bean that selects an implementation according to business logic if the decision depends on runtime input.

Do not use `@Order` to resolve two primaries of the same type; `@Order` does not turn one bean into a unique primary.

## 7. `@Primary` differs from `@ConditionalOnMissingBean`

Both annotations appear frequently in Spring Boot, but they have different responsibilities.

| Annotation | Purpose | Result |
| --- | --- | --- |
| `@Primary` | Selects the preferred candidate when injecting a single dependency | Multiple beans remain registered |
| `@Qualifier` | Narrows candidates at an injection point | Consumer receives the bean matching the qualifier |
| `@ConditionalOnMissingBean` | Registers a default bean only if no matching bean exists yet | Fallback bean may not be created |
| `@Order` | Sorts certain collections/arrays or ordered components | Does not select a default for single injection |

Auto-configuration example:

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

Here `@ConditionalOnMissingBean` decides whether to create the default bean. `@Primary` matters only if the default bean is created and multiple matching candidates later exist.

If the application has already registered its own `MessageSender`, auto-configuration yields; the `@Primary` annotation on the fallback bean does not force Spring to create an extra bean. That is auto-configuration back-off, which is distinct from selecting among beans in a context that already has multiple candidates.

## 8. Runnable example: testing candidate resolution with Java 17 and Spring Boot 3.3.13

We use `ApplicationContextRunner` to build small contexts, each test with its own configuration. That lets us verify behavior precisely when:

1. There is a single candidate.
2. There are two candidates and exactly one `@Primary`.
3. There are two candidates and no `@Primary`.
4. There is a `@Qualifier` selecting a specific candidate.
5. There are two primary candidates at the same time.
6. A collection is injected to prove both beans remain present.

### 8.1. Project structure

```text
primary-candidate-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── PrimaryCandidateResolutionTest.java
```

### 8.2. `pom.xml`

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

### 8.3. `PrimaryCandidateResolutionTest.java`

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
    void primaryWinsForSingleValuedInjectionButOtherBeanStillExists() {
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
                    assertThat(context).hasBean("emailSender");
                    assertThat(context).hasBean("smsSender");

                    SenderRegistry registry =
                            context.getBean(SenderRegistry.class);

                    assertThat(registry.senders())
                            .extracting(MessageSender::channel)
                            .containsExactly("email", "sms");
                });
    }

    @Test
    void multipleCandidatesWithoutPrimaryFailSingleValuedInjection() {
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

Expected output:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

Maven Surefire may show additional timing or test names depending on plugin version. The tests do not print custom stdout.

### 8.4. What do the tests prove?

| Test | Configuration | Expected result |
| --- | --- | --- |
| `aSingleCandidateIsInjectedWithoutPrimary` | Only email sender | Context starts, injects email |
| `primaryWinsForSingleValuedInjectionButOtherBeanStillExists` | Email primary, regular SMS | Single consumer gets email; registry still has both ordered by `@Order` |
| `multipleCandidatesWithoutPrimaryFailSingleValuedInjection` | Email and SMS, no primary/qualifier | Context fails with `NoUniqueBeanDefinitionException` |
| `qualifierSelectsSmsEvenWhenEmailIsPrimary` | Email primary, injection has SMS qualifier | Consumer receives SMS |
| `twoPrimaryCandidatesAreStillAmbiguous` | Both email and SMS are primary | Context fails because there is no unique primary |

The second test is the most important for understanding `@Primary` properly: the email bean is chosen for single injection, yet SMS still exists in `ApplicationContext` and inside `List<MessageSender>`. `@Primary` is not a candidate filter for collections.

The third test shows that the error occurs only when an injection point requests a single bean. If `NotificationService` is removed from the ambiguous configuration, both sender beans can coexist without causing a resolution error.

## 9. Reading `NoUniqueBeanDefinitionException`

When application startup fails due to multiple candidates, read the exception details in order:

1. Identify the consumer bean being created, e.g., `notificationService`.
2. Identify what type the injection point requires, e.g., `MessageSender`.
3. Read the list of candidates in the exception message.
4. Check whether any qualifier is missing or misspelled.
5. Check whether there is a single primary candidate.
6. If there are multiple primaries, resolve the ambiguity with a single default or qualifiers.
7. If the choice depends on use case, use qualifiers/strategies instead of trying to force a global primary.

A typical error looks like:

```text
Parameter 0 of method notificationService in
demo.PrimaryCandidateResolutionTest$AmbiguousConfiguration
required a single bean, but 2 were found:
    - emailSender
    - smsSender
```

Actual class/method names and formatting depend on the injection point and Spring version. Rely on the reported candidate types/names, not on line numbers or a fixed exception layout.

You can enable debug logging when you need to trace context creation:

```properties
debug=true
logging.level.org.springframework.beans.factory.support=DEBUG
```

Do not leave overly verbose logging enabled long-term in production if logs can grow too large or expose internal structure details.

## 10. Key distinctions to remember

### 10.1. `@Primary` is not `@Order`

- `@Primary`: selects a candidate for a single dependency when multiple candidates exist.
- `@Order`: controls order in collections/ordered processing supported by Spring.
- `@Qualifier`: selects a candidate as requested by the injection point.

Do not use `@Order(1)` expecting it to make that bean win a single injection like `@Primary`.

### 10.2. `@Primary` is not `@ConditionalOnMissingBean`

- `@ConditionalOnMissingBean` decides whether to register a fallback bean.
- `@Primary` only marks an already-registered bean as preferred during candidate resolution.
- A bean can be both a conditional fallback and primary, but the two annotations solve two different stages.

### 10.3. `@Primary` does not replace business qualifiers

If a service must always send SMS for OTP, use `@Qualifier("smsSender")` so the code states the requirement clearly. Do not rely on SMS happening to be primary in another configuration.

### 10.4. Do not depend on declaration order

`@Bean` method order, configuration file order, or component scan order is not a default bean-selection policy. When an explicit decision is needed, declare primary or a qualifier.

### 10.5. `@Primary` does not alter the bean list

Unselected beans can still be injected in collections, looked up by name, and used at injection points with specific qualifiers. If you want a bean never to be an autowire candidate, that is a separate candidate-configuration concern; `@Primary` does not do that.

## 11. Decision checklist when designing multiple implementations

Before adding `@Primary`, answer:

1. Is an application-wide default implementation genuinely needed?
2. Do all consumers mean the same thing when they receive that default?
3. Can specialized consumers express their choice using qualifiers?
4. Is there a use case that needs all implementations as a collection?
5. Does collection order matter? If so, use `@Order`.
6. Does auto-configuration need to back off when the application provides its own bean?
7. Are there tests for single candidate, multiple candidates, no-primary, qualifiers, and collections?

A sound design usually combines an intentional primary default, qualifiers for specialized cases, and collection injection when fan-out is needed. If there is no business-valid default, let ambiguity surface in tests rather than silently picking an arbitrary implementation.

## 12. Self-check questions

**Question 1.** The context has two `MessageSender` beans, one marked `@Primary`. Which bean does a constructor requesting `MessageSender` receive?  
**Answer:** The single bean marked primary, provided both remain matching candidates for the injection point.

**Question 2.** Two beans of the same type exist with no `@Primary`, qualifier, or other resolution hint. What happens when a constructor requires exactly one bean?  
**Answer:** Spring cannot choose uniquely and the context fails with `NoUniqueBeanDefinitionException` (usually wrapped in a bean creation exception).

**Question 3.** There is one primary bean and one regular bean. How many beans does `List<MessageSender>` receive?  
**Answer:** Both matching candidates. `@Primary` does not exclude regular beans from collections.

**Question 4.** Email is primary, but the injection point has `@Qualifier("smsSender")`. Which bean is injected?  
**Answer:** The SMS sender, because the qualifier requests that specific candidate for that injection point.

**Question 5.** Two beans of the same type are both marked `@Primary`. Can Spring rely on declaration order to pick one?  
**Answer:** No. Without other resolution information, it remains ambiguous and can throw `NoUniqueBeanDefinitionException`.

**Question 6.** Does `@Order(1)` make a bean primary?  
**Answer:** No. `@Order` relates to ordering; `@Primary` relates to selecting one candidate.

**Question 7.** How do `@ConditionalOnMissingBean` and `@Primary` differ?  
**Answer:** The condition decides whether to register a fallback; primary marks a registered bean as the preferred candidate for single injection.

## 13. Principles to remember

- Multiple beans of the same type are valid; errors arise only when an injection point needs a single bean and candidates cannot be resolved.
- `@Primary` picks a preferred candidate for single injection; it does not remove the remaining beans.
- Multiple candidates without a primary can trigger `NoUniqueBeanDefinitionException` if qualifiers, names, or other priority metadata do not resolve it.
- `@Qualifier` expresses per-injection-point selection and can override a primary default when the qualifier selects another candidate.
- `List`, `Set`, arrays, and `Map<String, T>` receive all matching candidates; `@Primary` does not filter collections.
- `@Order` sorts collections in supported cases and does not replace `@Primary`.
- Two equally matching primaries do not produce a unique choice.
- Use `@ConditionalOnMissingBean` for auto-configuration back-off; use `@Primary` for candidate resolution.

### Official References

- [Spring Framework — Using `@Primary` to Fine-tune Autowiring](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Using `@Order` with Component Scanning](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Framework API — `NoUniqueBeanDefinitionException`](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/NoUniqueBeanDefinitionException.html)
