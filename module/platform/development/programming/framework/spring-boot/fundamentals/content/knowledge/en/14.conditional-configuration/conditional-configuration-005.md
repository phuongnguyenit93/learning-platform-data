# `@ConditionalOnSingleCandidate` When One Type Has Multiple Beans

In Spring Boot, an application can register multiple Beans implementing the same interface. This is normal: an application might have multiple notification senders, multiple cache types, multiple storage implementations, or multiple datasources. The issue arises when an auto-configuration needs **a single Bean** of a given type to create the next component.

For example, an auto-configuration wants to create `ReportPublisher`, and its factory method needs a `ReportStore`. If the container only has one `ReportStore` Bean, Spring can inject it directly. If there are two Beans of the same type, choosing one Bean can become ambiguous. A Bean marked with `@Primary` can resolve the default choice.

`@ConditionalOnSingleCandidate` is Spring Boot's condition for this situation. It only matches when the `BeanFactory` has **a single candidate** eligible to be autowired for the required type, or when there are multiple candidates and a single **primary candidate** can be determined. If there are multiple Beans of the same type without a unique primary candidate, the condition does not match.

This condition is especially useful in auto-configuration: only create a Bean that depends on a collaborator when the container can provide that collaborator unambiguously.

## 1. The Problem: One Type with Multiple Beans

Suppose an application has an interface:

```java
public interface ReportStore {
    void save(String report);
}
```

And two implementations:

```java
@Component("databaseReportStore")
public class DatabaseReportStore implements ReportStore {
    @Override
    public void save(String report) {
        // Save the report to the database.
    }
}
```

```java
@Component("fileReportStore")
public class FileReportStore implements ReportStore {
    @Override
    public void save(String report) {
        // Save the report to a file.
    }
}
```

The container now has two Beans assignable to type `ReportStore`:

| Bean name | Implementation | Injectable type |
|---|---|---|
| `databaseReportStore` | `DatabaseReportStore` | `ReportStore` |
| `fileReportStore` | `FileReportStore` | `ReportStore` |

A service requires one `ReportStore`:

```java
@Service
public class ReportPublisher {
    private final ReportStore store;

    public ReportPublisher(ReportStore store) {
        this.store = store;
    }
}
```

Without metadata helping Spring pick one candidate, constructor injection becomes ambiguous. The context may fail with an error such as `NoUniqueBeanDefinitionException` or a wrapping Bean creation error whose root cause is multiple matching candidates.

This does not mean having multiple Beans for the same interface is wrong. Having multiple implementations is a valid design; only when **exactly one default implementation is needed** must there be a selection rule.

## 2. What Is `@ConditionalOnSingleCandidate`?

`@ConditionalOnSingleCandidate` belongs to the package:

```java
org.springframework.boot.autoconfigure.condition
```

It is a Spring Boot conditional annotation. Spring evaluates the condition when processing configuration; the annotated configuration or Bean is only registered when there is a single matching candidate for the required type.

Basic usage:

```java
@Bean
@ConditionalOnSingleCandidate(ReportStore.class)
ReportPublisher reportPublisher(ReportStore store) {
    return new ReportPublisher(store);
}
```

Read this snippet as follows:

1. Spring Boot checks the `BeanFactory` for Beans matching type `ReportStore`.
2. If there is only one candidate, the condition matches.
3. If there are multiple candidates, yet there is a single primary candidate, the condition can also match.
4. If there are multiple candidates without a single primary candidate, the condition does not match.
5. Only when the condition matches is the `reportPublisher` Bean registered from the method above.

This annotation helps auto-configuration **back off safely** when a single dependency cannot be chosen. When the condition does not match, Spring does not create `ReportPublisher` from that method; other Beans in the application can still be created normally.

### Syntax

Common example:

```java
@ConditionalOnSingleCandidate(ReportStore.class)
```

The annotation also supports specifying the type via class name:

```java
@ConditionalOnSingleCandidate(type = "com.example.reporting.ReportStore")
```

Declaring via `value` is usually easier to refactor and type-check at compile time. Use `type` when you need to reference the type as a string name, such as in an optional configuration where you do not want a direct compile-time dependency on that class.

There is no need to write a custom `@Conditional` or access `ApplicationContext` to count Beans in ordinary cases; this annotation already expresses the meaning "a single candidate by type".

## 3. Decision Rules: Single Candidate, Multiple Candidates, and `@Primary`

Consider four scenarios:

| Number of Beans matching type | Primary candidate | `@ConditionalOnSingleCandidate` |
|---:|---|---|
| 0 | None | Does not match |
| 1 | Not needed | Matches |
| 2 or more | None | Does not match |
| 2 or more | One unique primary candidate | Matches |

The core point is that the condition does not require the entire container to have only one Bean. It requires the container to be able to determine **a single candidate to autowire for that type**.

### Case with Only One Bean

```java
@Configuration(proxyBeanMethods = false)
class ReportStoreConfiguration {
    @Bean
    ReportStore reportStore() {
        return new DatabaseReportStore();
    }
}
```

If there are no other `ReportStore` Beans within the condition's search scope, `@ConditionalOnSingleCandidate(ReportStore.class)` matches. Marking `@Primary` is unnecessary because there is already only one candidate.

### Case with Multiple Beans and No Primary

```java
@Configuration(proxyBeanMethods = false)
class ReportStoreConfiguration {
    @Bean
    ReportStore databaseReportStore() {
        return new DatabaseReportStore();
    }

    @Bean
    ReportStore fileReportStore() {
        return new FileReportStore();
    }
}
```

There are two candidates. Neither Bean is marked primary, so the condition does not match. An auto-configured Bean requiring a single `ReportStore` will not be registered from that conditional method.

### Case with One Primary

```java
@Configuration(proxyBeanMethods = false)
class ReportStoreConfiguration {
    @Bean
    @Primary
    ReportStore databaseReportStore() {
        return new DatabaseReportStore();
    }

    @Bean
    ReportStore fileReportStore() {
        return new FileReportStore();
    }
}
```

Now `databaseReportStore` is the primary candidate. The condition can match, and when the factory method takes a `ReportStore` parameter, Spring can inject that primary Bean.

`@Primary` does not remove `fileReportStore` from the container. The second Bean can still be retrieved by name or injected when an injection point specifies an appropriate qualifier.

### What If There Are Multiple Primary Candidates?

`@Primary` is used to designate a preferred candidate. If there are multiple Beans of the same type and the primary metadata does not yield a unique choice, you should not expect `@ConditionalOnSingleCandidate` to pick arbitrarily. The condition is designed to avoid ambiguous situations, not to guess which Bean gets created first.

## 4. Complete Auto-Configuration Example

Let's build an auto-configuration that provides `ReportPublisher` if the application has a uniquely selectable `ReportStore`.

### Contract and Application-Provided Beans

```java
public interface ReportStore {
    void save(String report);
}
```

```java
public class ReportPublisher {
    private final ReportStore store;

    public ReportPublisher(ReportStore store) {
        this.store = store;
    }

    public void publish(String report) {
        store.save(report);
    }
}
```

`ReportPublisher` does not create `ReportStore` itself. It simply requires the dependency via its constructor.

### Auto-Configuration

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportPublisherAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(ReportStore.class)
    ReportPublisher reportPublisher(ReportStore store) {
        return new ReportPublisher(store);
    }
}
```

Here:

- `@AutoConfiguration` marks the Spring Boot auto-configuration.
- `@Bean` declares the factory method creating `ReportPublisher`.
- `@ConditionalOnSingleCandidate` checks whether `ReportStore` can be uniquely resolved.
- The method parameter `ReportStore store` asks the container to inject the selected candidate.

In a separately packaged auto-configuration library, the configuration class needs to be registered via Spring Boot's auto-configuration import mechanism, typically through the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

with the fully qualified configuration class name, for example:

```text
com.example.reporting.ReportPublisherAutoConfiguration
```

This step is for auto-configuration library authors. Ordinary applications do not need to create this file themselves just to use a `@Configuration` Bean they declared.

### Behavior Across Three Application Configurations

**Configuration A — only one `ReportStore`:**

```java
@Configuration(proxyBeanMethods = false)
class ApplicationStoreConfiguration {
    @Bean
    ReportStore reportStore() {
        return new DatabaseReportStore();
    }
}
```

Result: condition matches; `ReportPublisher` is registered and receives `reportStore`.

**Configuration B — two `ReportStore`s without a primary:**

```java
@Configuration(proxyBeanMethods = false)
class ApplicationStoreConfiguration {
    @Bean
    ReportStore databaseReportStore() {
        return new DatabaseReportStore();
    }

    @Bean
    ReportStore fileReportStore() {
        return new FileReportStore();
    }
}
```

Result: condition does not match; the `reportPublisher(...)` method does not provide a Bean. Auto-configuration avoids creating a Bean whose dependency has no unique choice.

**Configuration C — two `ReportStore`s, one primary:**

```java
@Configuration(proxyBeanMethods = false)
class ApplicationStoreConfiguration {
    @Bean
    @Primary
    ReportStore databaseReportStore() {
        return new DatabaseReportStore();
    }

    @Bean
    ReportStore fileReportStore() {
        return new FileReportStore();
    }
}
```

Result: condition matches; `ReportPublisher` is registered and the `ReportStore` parameter receives `databaseReportStore`.

## 5. How Does `@ConditionalOnSingleCandidate` Differ from `@ConditionalOnBean`?

Both annotations are conditions based on existing Beans, yet they answer different questions.

| Annotation | Question | Multiple Beans of same type |
|---|---|---|
| `@ConditionalOnBean(ReportStore.class)` | Is there at least one matching Bean? | Usually still matches |
| `@ConditionalOnSingleCandidate(ReportStore.class)` | Is there a single autowirable candidate? | Matches only if there is a unique primary candidate |
| `@ConditionalOnMissingBean(ReportStore.class)` | Is there no matching Bean so a default can be configured? | Does not match if a matching Bean already exists |

### When to Use `@ConditionalOnBean`?

If a Bean only needs to know that an integration has been registered, regardless of whether there is one or multiple implementations, `@ConditionalOnBean` may be appropriate.

For example, a registry might operate when at least one `ReportStore` exists and receive all implementations via a collection:

```java
@Bean
@ConditionalOnBean(ReportStore.class)
ReportStoreRegistry reportStoreRegistry(List<ReportStore> stores) {
    return new ReportStoreRegistry(stores);
}
```

Because the registry takes a list, multiple candidates are not a problem. `@ConditionalOnSingleCandidate` here would be too strict and could prevent the Bean from being created even though a list of multiple implementations is completely valid.

### When to Use `@ConditionalOnSingleCandidate`?

If the factory method takes only a single `ReportStore` and needs a default selection:

```java
@Bean
@ConditionalOnSingleCandidate(ReportStore.class)
ReportPublisher reportPublisher(ReportStore store) {
    return new ReportPublisher(store);
}
```

This is exactly the case this annotation was designed to solve.

### When to Use `@ConditionalOnMissingBean`?

Auto-configuration often provides a default Bean if the application has not declared a matching Bean itself:

```java
@Bean
@ConditionalOnMissingBean(ReportStore.class)
ReportStore defaultReportStore() {
    return new InMemoryReportStore();
}
```

If the application has already registered one or more `ReportStore`s, the default Bean may not be created. This condition supports Spring Boot's "back off" philosophy: default configuration yields to configuration provided by the application.

Do not swap these annotations interchangeably just because they all check the `BeanFactory`. Choose according to the exact contract the Bean requires: **at least one**, **none yet**, or **a single candidate**.

## 6. `@Primary` and `@Qualifier` Have Different Roles

`@Primary` and `@Qualifier` both participate in dependency injection resolution, yet they do not serve the same purpose.

### `@Primary`: Default Choice by Type

```java
@Primary
@Component
public class DatabaseReportStore implements ReportStore {
    // ...
}
```

When there are multiple `ReportStore` Beans, a primary Bean can be selected for injection points requesting only type `ReportStore` without specifying a qualifier.

This metadata aligns with the meaning of `@ConditionalOnSingleCandidate`: when multiple candidates exist, a single primary candidate lets the condition identify a unique choice.

### `@Qualifier`: Selection at a Specific Injection Point

```java
@Service
public class ArchiveService {
    private final ReportStore store;

    public ArchiveService(
            @Qualifier("fileReportStore") ReportStore store) {
        this.store = store;
    }
}
```

A qualifier states that this consumer needs a specific Bean. It can help a constructor resolve successfully even when the container has multiple implementations.

However, `@ConditionalOnSingleCandidate(ReportStore.class)` does not accept an injection-point qualifier as its parameter. Do not assume that another service using `@Qualifier` will cause a type-based condition to treat the remaining Beans as nonexistent. This condition checks the ability to select a single candidate by type and primary candidate; it is not an annotation for selecting Beans by arbitrary qualifiers.

If an auto-configuration needs a specific store by name/qualifier, design the condition and factory method to match that contract; do not use `@ConditionalOnSingleCandidate` as a qualifier-selection annotation.

## 7. `@ConditionalOnSingleCandidate` Is Not "Counting Classes"

The condition evaluates matching Beans in the `BeanFactory`, not simply counting Java files or classes implementing an interface.

For example:

- An implementation class present on the classpath but not registered as a Bean does not create an extra candidate.
- A Bean may be created from a factory method and have an interface return type.
- A Bean may come from another auto-configuration.
- A Bean may reside in a parent context, depending on the search strategy used.
- Beans that are not autowire candidates or are skipped by corresponding metadata/conditions are not necessarily treated like regular candidates.

Therefore, when the condition does not match, the question should be "Which candidates does the `BeanFactory` see at evaluation time?" rather than "How many classes implement the interface in the source code?".

### `@Bean` Return Type Matters

```java
@Bean
ReportStore reportStore() {
    return new DatabaseReportStore();
}
```

Declaring the return type `ReportStore` gives the container clear type information for evaluating conditions and resolving dependencies. If the factory method returns `Object` even though it actually creates `DatabaseReportStore`, Spring may not be able to infer the concrete type at certain metadata processing moments.

For auto-configuration, declare concrete/appropriate abstraction return types instead of unnecessarily returning `Object`. This ensures type-based conditions have enough information to evaluate.

### `FactoryBean` and Early Undetermined Types

If a Bean is provided by a `FactoryBean`, determining the product type can depend on metadata supplied by the factory. Spring may need to query the factory's product type; if the type cannot be determined early, some type-based conditions may lack sufficient information at evaluation time.

When writing auto-configuration, expose clear type metadata and avoid forcing conditions to initialize infrastructure just to guess types. If using a library with a `FactoryBean`, inspect how it declares its product type and check the condition report if results are unexpected.

## 8. Condition Evaluation Timing and Auto-Configuration Ordering

Spring Boot conditions are evaluated during configuration processing, based on `BeanDefinition`s already registered and visible at that moment. Therefore **configuration processing order can affect the result**.

For example, auto-configuration A wants to check for a Bean provided by auto-configuration B. If A is evaluated before B contributes its `BeanDefinition`, A might not see the candidate you expect.

When an auto-configuration depends on a Bean/configuration from another auto-configuration, declare the ordering explicitly:

```java
@AutoConfiguration(after = ReportStoreAutoConfiguration.class)
public class ReportPublisherAutoConfiguration {
    // ...
}
```

Or use the corresponding ordering annotation such as `@AutoConfigureAfter` in suitable configurations.

Do not use ordering to hide a missing dependency in your design. Ordering only resolves relationships between configuration sources; it does not turn an undeclared Bean into a candidate.

### User-Defined Beans and Auto-Configuration

Spring Boot normally processes auto-configuration after application configurations so that user-declared Beans are visible when conditions are evaluated. This is the foundation for replaceable defaults.

However, if you build multiple configuration modules yourself and import them in a custom order, you still need to understand definition registration order. When a condition unexpectedly fails to match, read the condition evaluation report rather than guessing the order.

## 9. Example Testing Three States with `ApplicationContextRunner`

Spring Boot provides `ApplicationContextRunner` to test auto-configuration in a small, isolated context. It is especially well suited for verifying conditions without booting the whole application.

Suppose the auto-configuration is:

```java
@AutoConfiguration
public class ReportPublisherAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(ReportStore.class)
    ReportPublisher reportPublisher(ReportStore store) {
        return new ReportPublisher(store);
    }
}
```

Tests can configure the input Beans:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

class ReportPublisherAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ReportPublisherAutoConfiguration.class));

    @Test
    void matchesWhenThereIsOneCandidate() {
        runner.withUserConfiguration(OneStoreConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportPublisher.class);
                });
    }

    @Test
    void doesNotMatchWhenThereAreMultipleCandidatesWithoutPrimary() {
        runner.withUserConfiguration(TwoStoresConfiguration.class)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportPublisher.class);
                });
    }

    @Test
    void matchesWhenOneOfSeveralCandidatesIsPrimary() {
        runner.withUserConfiguration(PrimaryStoreConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportPublisher.class);
                    assertThat(context.getBean(ReportPublisher.class))
                            .isNotNull();
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class OneStoreConfiguration {
        @Bean
        ReportStore reportStore() {
            return new DatabaseReportStore();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoStoresConfiguration {
        @Bean
        ReportStore databaseReportStore() {
            return new DatabaseReportStore();
        }

        @Bean
        ReportStore fileReportStore() {
            return new FileReportStore();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryStoreConfiguration {
        @Bean
        @Primary
        ReportStore databaseReportStore() {
            return new DatabaseReportStore();
        }

        @Bean
        ReportStore fileReportStore() {
            return new FileReportStore();
        }
    }
}
```

The illustrative example requires the `ReportStore`, `ReportPublisher`, `DatabaseReportStore`, and `FileReportStore` classes defined earlier. The test uses AssertJ/JUnit via Spring Boot's test dependencies. It verifies three important branches:

1. One candidate: condition matches.
2. Multiple candidates without primary: condition does not match.
3. Multiple candidates with one primary: condition matches.

`ApplicationContextRunner` helps verify auto-configuration behavior across different sets of input Beans. This is a great way for starter authors to ensure default configurations do not break applications with multiple implementations.

## 10. Observing Why Conditions Match or Do Not Match

When the application starts in debug mode, Spring Boot can print the **Condition Evaluation Report**:

```bash
java -jar app.jar --debug
```

Or enable the property:

```properties
debug=true
```

In the report, search for the relevant auto-configuration or method name. You can see whether the condition matched or did not match and the message describing why.

If the application includes Actuator and the `conditions` endpoint is enabled, this endpoint can also help observe conditions. Exposing the endpoint should be restricted according to appropriate security/operational configurations; do not arbitrarily make internal diagnostic info public.

Some questions when reading the report:

- Which Bean type is the condition checking?
- Was the corresponding `BeanDefinition` already registered before the condition evaluated?
- How many matching candidates exist?
- Which candidate is marked primary?
- Has another auto-configuration not run yet or been excluded?
- Is the factory method's return type clear enough for Spring to infer?

Do not just look at the "did not match" line; read the message/condition details to know the specific reason.

## 11. Common Misconceptions

**"When there are multiple Beans of the same type, `@ConditionalOnSingleCandidate` is always false."** Not true. If there is a unique primary candidate, the condition can still match.

**"With `@Primary`, the remaining Beans are excluded."** No. `@Primary` only affects the default choice for matching injection points; the other Beans are still registered and can be selected by qualifier/name or injected as a collection.

**"`@ConditionalOnSingleCandidate` is the same as `@ConditionalOnBean`."** No. `@ConditionalOnBean` checks for the presence of a matching Bean; it does not require a single candidate to inject a single parameter.

**"`@Qualifier` on one service makes a type-based condition see only one Bean."** Do not infer this. A qualifier is metadata used at a specific injection point. `@ConditionalOnSingleCandidate` checks the ability to select one candidate by type and primary candidate; it does not accept arbitrary qualifiers as a Bean-selection parameter.

**"A non-matching condition means the application is broken."** No. When the condition does not match, the guarded Bean is simply not registered. This is often the intended behavior of auto-configuration; the application can provide a different configuration itself.

**"The condition checks classes implementing the interface on the classpath."** No. It checks Bean candidates that the `BeanFactory` can recognize at evaluation time.

**"Marking `@Primary` is how you fix every ambiguity."** Not always true. If each consumer needs a different implementation, qualifiers or collection injection express intent better. `@Primary` is only appropriate when there is a sensible global default.

## 12. When Should You Use `@ConditionalOnSingleCandidate`?

Consider this annotation when writing an auto-configuration or conditional configuration whose created Bean needs a single type-based dependency:

- Creating an integration adapter based on a selected `DataSource`.
- Creating a client wrapper based on an autowirable default `ObjectMapper`.
- Creating a publisher based on a store/service interface.
- Activating a feature only when the application has an unambiguous default implementation.

Do not use it when:

- The Bean needs all implementations; inject `List<T>` or `Map<String, T>`.
- You only need to know at least one Bean exists; `@ConditionalOnBean` may be more accurate.
- You want to provide a default Bean when the user has not configured one; see `@ConditionalOnMissingBean`.
- A consumer always needs a specific implementation by name; look at `@Qualifier` and conditions suited to that contract.
- The condition is placed at a configuration stage where the Bean being checked has not been registered yet; review ordering.

## 13. Reasoning Workflow When a Condition Behaves Unexpectedly

When `@ConditionalOnSingleCandidate` does not match, analyze in order:

1. **Confirm the type:** is the annotation checking the exact interface/class that the factory method needs?
2. **Confirm Bean registration:** has the implementation been registered as a `BeanDefinition`, or is it just a class present on the classpath?
3. **Count candidates:** are there 0, 1, or multiple matching Beans within the search scope?
4. **Check primary:** if multiple Beans exist, is there exactly one primary candidate?
5. **Check timing:** were the required `BeanDefinition`s processed before the condition evaluated?
6. **Check type metadata:** do the factory method/`FactoryBean` provide sufficiently clear type information?
7. **Read the condition report:** confirm the actual reason from Spring Boot.

This workflow distinguishes three kinds of issues: missing Beans, ambiguity due to multiple Beans, and conditions evaluated before the required information appeared.

## 14. Mental Model

```text
@ConditionalOnSingleCandidate(SomeType.class)
                 |
                 v
     BeanFactory searches candidates by type
                 |
        +--------+---------+
        |                  |
    0 candidates       1 candidate
        |                  |
      NO MATCH           MATCH
                           |
        +------------------+
        |
   Multiple candidates
        |
   Exactly one primary?
      /       \
    Yes        No
    |           |
  MATCH      NO MATCH
```

`@ConditionalOnSingleCandidate` helps Spring Boot register a configuration only when the container can supply a single dependency for the required type. When there is one Bean, the condition matches; when there are multiple Beans, a unique primary candidate can clarify the choice; otherwise, auto-configuration backs off to avoid creating a Bean with an ambiguous dependency.

Choose the annotation according to the factory method's exact requirement: needing **at least one Bean**, needing **no Bean yet**, or needing **a single candidate**. Once you understand that distinction, you can write auto-configurations that are flexible across multiple implementations while keeping dependency injection rules clear.
