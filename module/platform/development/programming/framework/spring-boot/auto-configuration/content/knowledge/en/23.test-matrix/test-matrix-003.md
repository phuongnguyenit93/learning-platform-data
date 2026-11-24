# No User Bean, Replacement Bean, and Multiple Candidates

## 1. Goal and scenario to solve

An auto-configuration often provides a default bean so an application can run immediately after adding a starter. At the same time, the library must yield to the application when the user declares their own implementation. The problem becomes more complex when the application has **multiple beans of the same type**: should auto-configuration still create a default bean, and can another bean that depends on that type be created?

Spring Boot provides two very important conditions with different meanings:

- `@ConditionalOnMissingBean`: matches only when **no bean** satisfies the checked criteria in the BeanFactory at the time the condition is evaluated. This is the common mechanism for creating a default bean and allowing user overrides.
- `@ConditionalOnSingleCandidate`: matches only when a matching bean exists and Spring can determine **a single candidate to autowire**. If multiple beans exist, one bean marked with `@Primary` can make the condition match.

This article uses `GreetingService` and `GreetingClient` as examples to analyze four scenarios:

1. No `GreetingService` bean declared by the user.
2. User declares exactly one replacement bean.
3. User declares multiple beans without a primary candidate.
4. User declares multiple beans and one bean is `@Primary`.

After this lesson, you should be able to distinguish **absent**, **single selectable candidate**, and **multiple ambiguous candidates**; know how to order auto-configurations; understand the roles of `@Primary`, `@Qualifier`, `List<T>`, and `ObjectProvider<T>`; and write dedicated tests for each combination.

Scope: Spring Boot 3.3.13, Spring Framework 6.1, and Java 17+.

## 2. Two different questions: is there any bean, and can one bean be chosen?

Suppose the application has an interface:

```java
public interface GreetingService {
    String greet(String name);
}
```

The two conditions correspond to two questions:

| Condition | Question | Matches when |
| --- | --- | --- |
| `@ConditionalOnMissingBean(GreetingService.class)` | Has any bean matching `GreetingService` already been registered? | No matching bean exists |
| `@ConditionalOnSingleCandidate(GreetingService.class)` | Can a single `GreetingService` be chosen for autowiring? | One bean exists, or multiple beans exist with a primary candidate |

The two questions are not two different ways of writing the same condition.

### 2.1. `@ConditionalOnMissingBean` is an absence check

Example:

```java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new DefaultGreetingService();
}
```

When Spring processes this method:

- If no bean matching `GreetingService` exists yet, the method is registered and the default bean can be created.
- If the user already has one `GreetingService` bean, the default method backs off.
- If the user already has two or more `GreetingService` beans, the default method still backs off. Having **at least one matching bean** is enough for the missing condition to no longer match.

`@Primary` does not change this check. A primary bean is still an existing bean; multiple beans with one primary still cause `@ConditionalOnMissingBean` not to match.

### 2.2. `@ConditionalOnSingleCandidate` checks single-dependency resolution

Example:

```java
@Bean
@ConditionalOnSingleCandidate(GreetingService.class)
GreetingClient greetingClient(GreetingService service) {
    return new GreetingClient(service);
}
```

This condition asks whether Spring can pick one candidate when it needs to autowire `GreetingService`.

- No matching bean: condition does not match.
- Exactly one bean: condition matches.
- Multiple beans and no primary candidate: condition does not match.
- Multiple beans and one primary candidate: condition matches; a single-valued dependency can be resolved via primary.

**"Single candidate" does not mean "only one bean exists in the context".** There can be two, three, or more beans, as long as one `@Primary` bean is chosen as the default candidate for single-valued injection.

The Spring Boot 3.3.13 Javadoc explicitly notes that the condition still matches when multiple beans of the same type exist provided there is a primary candidate; the condition corresponds to whether autowiring a single bean of that type can succeed.

## 3. Result matrix for 0, 1, and multiple beans

Suppose the starter provides two ordered auto-configurations:

1. `DefaultGreetingAutoConfiguration` registers the default `GreetingService` when no bean exists.
2. `GreetingClientAutoConfiguration` registers `GreetingClient` when a single `GreetingService` candidate is available.

Result:

| Beans declared by the application | Default service from starter | `@ConditionalOnMissingBean` | `@ConditionalOnSingleCandidate` | Client from starter |
| --- | --- | --- | --- | --- |
| None | Created | Matches | Matches with default bean | Created |
| One custom bean | Backs off | Does not match | Matches with custom bean | Created |
| Two custom beans, no primary | Backs off | Does not match | Does not match | Not created |
| Two custom beans, one primary | Backs off | Does not match | Matches with primary candidate | Created |

In the "two custom beans, no primary" row, the context can still start normally if no other bean forces direct injection of a single `GreetingService`. The client is skipped by the condition so it does not trigger an ambiguity error at that method.

If another bean still injects `GreetingService` without a qualifier and without a primary, Spring can throw `NoUniqueBeanDefinitionException` when creating that dependent bean. An auto-configuration condition does not automatically fix every injection point in the application.

## 4. Scenario 1: no user bean — starter creates default

This is the most basic case. The application adds the starter without providing an implementation.

```text
Application user beans:
  GreetingService: 0

DefaultGreetingAutoConfiguration:
  @ConditionalOnMissingBean(GreetingService.class) -> MATCH
  register defaultGreetingService

GreetingClientAutoConfiguration:
  @ConditionalOnSingleCandidate(GreetingService.class) -> MATCH
  register greetingClient
```

Example default implementation:

```java
public final class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "default: " + name;
    }
}
```

Once the default service is registered, the client can receive it via constructor/method injection:

```java
public final class GreetingClient {

    private final GreetingService service;

    public GreetingClient(GreetingService service) {
        this.service = service;
    }

    public String greet(String name) {
        return this.service.greet(name);
    }
}
```

This design delivers the "add the starter and it works" experience: users do not have to write beans themselves if they accept default behavior. The default bean can still be replaced later by declaring a bean of the same type before auto-configuration evaluates its condition.

## 5. Scenario 2: user provides one replacement bean — default backs off

The application provides its own implementation:

```java
@Configuration(proxyBeanMethods = false)
class CustomGreetingConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return name -> "custom: " + name;
    }
}
```

When auto-configuration runs:

- Bean `customGreetingService` is already registered.
- `@ConditionalOnMissingBean(GreetingService.class)` does not match.
- The starter does not register the default service.
- `@ConditionalOnSingleCandidate(GreetingService.class)` matches because there is only one candidate.
- `GreetingClient` receives the custom service.

Result:

```text
GreetingService beans: 1
Default service: absent
Client: present
client.greet("Ada") -> custom: Ada
```

This is the standard back-off behavior Spring Boot aims for in starters: provide a default when the user has not configured anything, and respect the custom bean when one exists.

### 5.1. Why should the condition live in auto-configuration?

A bean condition can inspect only the bean definitions that the context has processed **up to the moment the condition is evaluated**. If similar logic is placed in an arbitrary configuration processed too early, the application's bean may not be visible yet and the default bean could be registered unintentionally.

Spring Boot recommends using `@ConditionalOnBean` and `@ConditionalOnMissingBean` on auto-configuration classes. Auto-configuration is processed after user-defined bean definitions, allowing default beans to back off properly.

## 6. Scenario 3: multiple beans, no primary — default still backs off

The application has two implementations:

```java
@Configuration(proxyBeanMethods = false)
class MultipleGreetingConfiguration {

    @Bean("formalGreetingService")
    GreetingService formalGreetingService() {
        return name -> "Good day, " + name;
    }

    @Bean("casualGreetingService")
    GreetingService casualGreetingService() {
        return name -> "Hi, " + name;
    }
}
```

When the context processes auto-configuration:

- At least one `GreetingService` bean exists, so the default service backs off.
- There are two candidates of the same type.
- There is no `@Primary`, so Spring cannot automatically choose one candidate for single-valued injection.
- `@ConditionalOnSingleCandidate` does not match.
- The default `GreetingClient` is not registered.

Result:

```text
GreetingService beans: 2
Default service: absent
Single candidate: no
Client: absent
```

This is a situation where library policy must be chosen deliberately. A starter should not silently pick the first bean based on registration order if its API requires a unique strategy.

### 6.1. What if a single bean is injected directly?

Example:

```java
@Bean
GreetingClient greetingClient(GreetingService service) {
    return new GreetingClient(service);
}
```

If there are two `GreetingService` beans and no primary/qualifier, when Spring creates `GreetingClient`, the dependency cannot be resolved and the context can fail with `NoUniqueBeanDefinitionException`.

Using `@ConditionalOnSingleCandidate` on the bean method is one way to register the client only when a single dependency can be chosen. The condition avoids registering a bean whose required dependency is ambiguous.

### 6.2. If the client needs all implementations, do not use single candidate

If business logic wants to run both the formal and casual services, inject a collection:

```java
@Bean
GreetingBatchClient greetingBatchClient(
    List<GreetingService> services
) {
    return new GreetingBatchClient(services);
}
```

Or use `ObjectProvider<GreetingService>` for flexible lookup:

```java
@Bean
GreetingBatchClient greetingBatchClient(
    ObjectProvider<GreetingService> services
) {
    return new GreetingBatchClient(
        services.orderedStream().toList()
    );
}
```

With collections, multiple beans are valid; there is no need to force them into a single candidate. If processing order matters, use `@Order`/`Ordered` and an explicit rule.

## 7. Scenario 4: multiple beans with one @Primary — one can be chosen

If one implementation is considered the default choice, mark it with `@Primary`:

```java
@Configuration(proxyBeanMethods = false)
class PrimaryGreetingConfiguration {

    @Bean("formalGreetingService")
    @Primary
    GreetingService formalGreetingService() {
        return name -> "Good day, " + name;
    }

    @Bean("casualGreetingService")
    GreetingService casualGreetingService() {
        return name -> "Hi, " + name;
    }
}
```

Now:

- Both `GreetingService` beans still exist.
- `@ConditionalOnMissingBean` still does not match because beans already exist.
- `@ConditionalOnSingleCandidate` matches because there is a primary candidate.
- Single-valued `GreetingService` injection receives the primary bean.
- `List<GreetingService>` injection still receives both implementations.

Result:

```text
GreetingService beans: 2
Primary candidate: formalGreetingService
Default service: absent
Single candidate: yes
Client: present
client.greet("Ada") -> Good day, Ada
```

**`@Primary` does not delete or remove the remaining beans.** It only helps Spring prioritize one candidate in situations requiring a single dependency. If you need all implementations, use a collection; if you need a specific bean by name/role, use a qualifier.

### 7.1. What if multiple beans are marked primary?

Do not configure multiple candidates marked as primary for the same type and expect Spring to pick one automatically. If a unique primary cannot be determined, single-valued injection remains ambiguous and `@ConditionalOnSingleCandidate` cannot rely on a clear choice.

Design a single primary candidate for the target type, or switch to qualifiers/collections with an explicit selection rule.

## 8. @Qualifier, @Primary, @Order, and collections have different jobs

| Mechanism | Use when | Effect |
| --- | --- | --- |
| `@Primary` | Multiple beans of the same type exist and one should be the default for single injection | Prioritizes one candidate |
| `@Qualifier` | The injection point knows exactly which bean or group of beans it needs | Selects by the declared qualifier |
| `@Order` / `Ordered` | Multiple beans need ordering in a collection/ordered stream | Defines order, does not exclude beans |
| `List<T>` | All matching implementations are needed | Injects multiple beans |
| `Map<String,T>` | Multiple beans are needed and accessed by bean name | Key is the Spring bean name |
| `ObjectProvider<T>.orderedStream()` | Flexible ordered lookup of 0/N beans is needed | Stream may be empty or contain multiple candidates |
| `@ConditionalOnSingleCandidate` | Auto-configuration should create a bean only when one dependency can be uniquely selected | Gates bean creation by candidate selectability |
| `@ConditionalOnMissingBean` | Auto-configuration should create a default when no matching bean exists yet | Backs off when a bean already exists |

Example using a qualifier:

```java
@Bean
GreetingClient formalClient(
    @Qualifier("formalGreetingService") GreetingService service
) {
    return new GreetingClient(service);
}
```

`@Qualifier` is an explicit choice at the injection point. It does not remove other beans from the context. Nor should you assume that adding a qualifier to a method parameter causes `@ConditionalOnSingleCandidate` to treat the context as having only one bean; that condition evaluates candidate selectability under its own rules, notably the primary candidate.

**Do not use `@Order` instead of `@Primary`.** Order sorts collections; primary resolves single-valued injection. The bean with the lowest order value does not automatically become the selected bean for every single dependency.

## 9. Auto-configuration order determines which beans a condition sees

Both `@ConditionalOnMissingBean` and `@ConditionalOnSingleCandidate` see only the bean definitions that have already been processed at evaluation time. Therefore, when one auto-configuration depends on a bean provided by another auto-configuration, declare the order explicitly.

Example:

```java
@AutoConfiguration
public class DefaultGreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}

@AutoConfiguration(after = DefaultGreetingAutoConfiguration.class)
public class GreetingClientAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(GreetingService.class)
    GreetingClient greetingClient(GreetingService service) {
        return new GreetingClient(service);
    }
}
```

The `after` relationship ensures the auto-configuration creating the client is processed after the auto-configuration providing the default service. Then:

- No user bean: the default service has already been registered before checking the client.
- One custom bean: the default service backs off, and the client sees the custom bean.
- Multiple custom beans without primary: default backs off, client condition does not match.
- Multiple custom beans with one primary: default backs off, client condition matches thanks to the primary candidate.

**Do not use line order in `AutoConfiguration.imports` as a dependency rule.** Declare `before`/`after` or `beforeName`/`afterName` on the auto-configurations according to actual relationships. Auto-configuration application order affects bean definition registration order; it does not by itself dictate instantiation order of every bean instance.

## 10. Standalone Java 17+ test example with ApplicationContextRunner

This example verifies the four scenarios in a Maven project. `ApplicationContextRunner` creates an isolated context for each scenario; `AutoConfigurations.of(...)` loads the auto-configurations under test; `withUserConfiguration(...)` adds beans provided by the application.

### 10.1. Structure

```text
single-candidate-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── GreetingAutoConfigurationTests.java
```

### 10.2. `pom.xml` file

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
    <artifactId>single-candidate-demo</artifactId>
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

### 10.3. `src/test/java/demo/GreetingAutoConfigurationTests.java` file

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

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    DefaultGreetingAutoConfiguration.class,
                    GreetingClientAutoConfiguration.class
                )
            );

    interface GreetingService {
        String greet(String name);
    }

    static final class DefaultGreetingService implements GreetingService {
        @Override
        public String greet(String name) {
            return "default: " + name;
        }
    }

    static final class GreetingClient {
        private final GreetingService service;

        GreetingClient(GreetingService service) {
            this.service = service;
        }

        String greet(String name) {
            return this.service.greet(name);
        }
    }

    @AutoConfiguration
    static class DefaultGreetingAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(GreetingService.class)
        GreetingService greetingService() {
            return new DefaultGreetingService();
        }
    }

    @AutoConfiguration(after = DefaultGreetingAutoConfiguration.class)
    static class GreetingClientAutoConfiguration {

        @Bean
        @ConditionalOnSingleCandidate(GreetingService.class)
        GreetingClient greetingClient(GreetingService service) {
            return new GreetingClient(service);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OneUserServiceConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return name -> "custom: " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoUserServicesConfiguration {

        @Bean("formalGreetingService")
        GreetingService formalGreetingService() {
            return name -> "formal: " + name;
        }

        @Bean("casualGreetingService")
        GreetingService casualGreetingService() {
            return name -> "casual: " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoServicesWithPrimaryConfiguration {

        @Bean("primaryGreetingService")
        @Primary
        GreetingService primaryGreetingService() {
            return name -> "primary: " + name;
        }

        @Bean("secondaryGreetingService")
        GreetingService secondaryGreetingService() {
            return name -> "secondary: " + name;
        }
    }

    @Test
    void createsDefaultWhenNoUserBeanExists() {
        this.contextRunner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasSingleBean(GreetingClient.class);

            assertThat(context.getBean(GreetingService.class))
                .isInstanceOf(DefaultGreetingService.class);

            assertThat(context.getBean(GreetingClient.class).greet("Ada"))
                .isEqualTo("default: Ada");
        });
    }

    @Test
    void backsOffWhenOneUserBeanExists() {
        this.contextRunner
            .withUserConfiguration(OneUserServiceConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context).hasSingleBean(GreetingClient.class);

                assertThat(context.getBean(GreetingClient.class).greet("Ada"))
                    .isEqualTo("custom: Ada");
            });
    }

    @Test
    void skipsSingleCandidateClientWhenMultipleBeansHaveNoPrimary() {
        this.contextRunner
            .withUserConfiguration(TwoUserServicesConfiguration.class)
            .run(context -> {
                assertThat(context.getBeanNamesForType(GreetingService.class))
                    .hasSize(2);

                assertThat(context)
                    .doesNotHaveBean(GreetingClient.class);
            });
    }

    @Test
    void usesPrimaryWhenMultipleBeansExist() {
        this.contextRunner
            .withUserConfiguration(TwoServicesWithPrimaryConfiguration.class)
            .run(context -> {
                assertThat(context.getBeanNamesForType(GreetingService.class))
                    .hasSize(2);

                assertThat(context).hasSingleBean(GreetingClient.class);

                assertThat(context.getBean(GreetingClient.class).greet("Ada"))
                    .isEqualTo("primary: Ada");
            });
    }
}
```

### 10.4. Running tests

Requirements: JDK 17+, Maven 3.8+, and dependency download access. In the `single-candidate-demo` directory, run:

```bash
mvn clean test
```

Logical outcomes to verify across the four tests:

| Test | Key assertion | Result |
| --- | --- | --- |
| `createsDefaultWhenNoUserBeanExists` | One default service and one client exist | Pass |
| `backsOffWhenOneUserBeanExists` | Only custom service exists; client uses custom service | Pass |
| `skipsSingleCandidateClientWhenMultipleBeansHaveNoPrimary` | Two services exist; client is not created | Pass |
| `usesPrimaryWhenMultipleBeansExist` | Two services exist; client uses primary service | Pass |

Maven Surefire will report four passing tests and `BUILD SUCCESS` if all assertions succeed. Execution time, banners/logs, and report formatting depend on the environment; the table above represents expected behavioral outcomes, not fixed full stdout.

### 10.5. Why are two separate auto-configurations needed?

If the default service and the client condition are placed arbitrarily inside a single configuration, bean method registration order can cause the client's condition to be evaluated before the default bean definition is processed. Splitting them into two auto-configurations and declaring `after` expresses the dependency clearly:

- The first configuration is responsible for providing the default service if missing.
- The second configuration creates the client only when the service already has an autowirable candidate.

This is also how to make the contract between auto-configurations explicit in a real starter.

## 11. Design variants when multiple candidates exist

### 11.1. Multiple implementations, but the client only needs one preconfigured choice

If users need to specify exactly which implementation to use, you can provide a property:

```properties
acme.greeting.service=primaryGreetingService
```

The starter reads the property and selects the bean by name/qualifier through an explicit mechanism. In that case, do not rely purely on `@Primary` if business logic requires dynamic configuration or multiple strategy groups.

Define the behavior when the property is missing, misspelled, or points to a non-existent bean: fall back to a default, fail fast, or disable the client. Do not treat an arbitrary string as a valid bean without checking.

### 11.2. Multiple implementations must all run

If every implementation has a role to play, inject `List<GreetingService>` or `ObjectProvider<GreetingService>`. Apply `@Order` to define the pipeline when ordering affects the result. Do not use `@ConditionalOnSingleCandidate` because that condition is designed for a single-candidate dependency.

### 11.3. Exactly one bean is strictly required

If business rules require **literally one actual bean**, `@ConditionalOnSingleCandidate` is not enough to check cardinality because multiple beans with one primary still satisfy the condition.

Count the candidates or write dedicated validation:

```java
List<GreetingService> services =
    provider.orderedStream().toList();

if (services.size() != 1) {
    throw new IllegalStateException(
        "Expected exactly one GreetingService, found " + services.size()
    );
}
```

This is an illustrative example using an injected `ObjectProvider<GreetingService>`. This policy differs from "being able to choose one bean for autowiring". Use it only when business requirements genuinely forbid multiple beans.

### 11.4. Multiple beans with specific qualifiers

`@Qualifier` is useful when a bean depends on a specific role:

```java
@Bean
GreetingClient formalClient(
    @Qualifier("formalGreetingService") GreetingService service
) {
    return new GreetingClient(service);
}
```

This is an explicit choice at the injection point. If auto-configuration conditionally registers the client, design the condition to match that qualifier policy; do not assume `@ConditionalOnSingleCandidate` automatically understands every qualifier at individual injection points.

## 12. Common pitfalls and fixes

| Mistake / misconception | Why it is wrong | How to handle it |
| --- | --- | --- |
| Thinking `@ConditionalOnMissingBean` backs off only when there is exactly one custom bean | The condition checks for absence; one or many beans both cause it not to match | Test both one and multiple custom beans |
| Thinking `@Primary` makes other beans disappear | Primary only prioritizes a candidate for single injection | Use a collection when all are needed; check count via bean names |
| Thinking `@ConditionalOnSingleCandidate` means only one bean exists | Multiple beans with a primary candidate still match | If literally one is required, count collection/provider elements |
| Using `@Order` to pick one bean for single injection | Order sorts collections; it does not replace primary/qualifier | Use `@Primary` or `@Qualifier` |
| Injecting a single `GreetingService` when two non-primary beans exist | Spring cannot decide which bean to choose | Use a qualifier, primary, or collection |
| Placing a bean condition in a configuration processed too early | The condition sees only already-processed bean definitions | Use auto-configuration and declare `after` when depending on another configuration |
| Using `@ConditionalOnMissingBean` to gate a pipeline that needs exactly one plugin | Missing bean checks only absence, not cardinality | Use `@ConditionalOnSingleCandidate` or count validation as required |
| Assuming a matching client condition guarantees the client bean constructs successfully | Other dependencies or constructor logic can still fail | Test the actual context and bean behavior |
| Testing only the no-custom-bean case | Misses back-off, ambiguity, and primary bugs | Test the 0/1/N matrix with and without primary |
| Using a fixed bean name without a qualifier | Bean name does not automatically pick an injection candidate in all cases | Declare `@Qualifier` wherever explicit selection is needed |

## 13. Matrix testing workflow for a starter

When developing auto-configuration with a default service and a bean depending on that service, include at least these tests:

1. **No user bean:** default is registered; client is created; output uses default.
2. **One user bean:** default backs off; client uses the application's implementation.
3. **Two user beans without primary:** default backs off; single-candidate condition does not match; confirm client is not registered if that is the policy.
4. **Two user beans, one primary:** default backs off; client is created and uses primary.
5. **Multiple primary beans or ambiguous primary config:** verify the expected error/behavior; do not assume a unique choice exists.
6. **User beans with qualifiers:** test specific injection points if the starter supports qualifier-based selection.
7. **Parent/child contexts:** if beans can reside in a parent context, test the condition's `search` attribute and context hierarchy.
8. **Other conditions:** combine property, classpath, and bean conditions to ensure one condition does not mask a failure in another.

`ApplicationContextRunner` fits these combinations well because each test creates a context with an explicit configuration. When multiple auto-configurations participate, `AutoConfigurations.of(...)` uses the same ordering rules as a Spring Boot application.

## 14. Self-check questions

**Question 1.** The user declares two `GreetingService` beans without `@Primary`. Does `@ConditionalOnMissingBean(GreetingService.class)` match?  
**Answer:** No. At least one matching bean exists, so the default service backs off.

**Question 2.** With two beans of the same type and one primary bean, does `@ConditionalOnSingleCandidate(GreetingService.class)` match?  
**Answer:** Yes. Spring can determine a primary candidate for single injection.

**Question 3.** Does `@ConditionalOnSingleCandidate` guarantee that the context contains only one `GreetingService`?  
**Answer:** No. Multiple beans can exist as long as one primary candidate can be determined.

**Question 4.** Does `@Primary` make `@ConditionalOnMissingBean` match again?  
**Answer:** No. A primary bean is still an existing bean; the missing condition still does not match.

**Question 5.** There are two non-primary services, and a client wants to use all of them. What should it inject?  
**Answer:** `List<GreetingService>` or `ObjectProvider<GreetingService>`; if order matters, use `orderedStream()` and specify `@Order`.

**Question 6.** Why should the client auto-configuration run after the default service auto-configuration?  
**Answer:** Conditions see only already-processed bean definitions. Declaring `after` ensures the client condition sees the default service if that configuration registered the bean.

**Question 7.** If literally one bean is required, is `@ConditionalOnSingleCandidate` alone sufficient?  
**Answer:** No. Multiple beans with one primary still match. You must count the beans/candidates and validate explicitly if exact cardinality is required.

**Question 8.** Do `@Order(1)` and `@Order(2)` select the order-1 bean for single injection?  
**Answer:** No. Order primarily sorts beans in collections/ordered streams; single injection uses primary/qualifier and candidate resolution rules.

## 15. Takeaways and official references

- `@ConditionalOnMissingBean` checks **no matching bean exists**; one or more existing beans make the default back off.
- `@ConditionalOnSingleCandidate` checks **a single candidate can be resolved for autowiring**; a primary candidate lets the condition match even when multiple beans coexist.
- `@Primary` prioritizes one bean for single injection; it does not remove other beans or reduce a collection to one element.
- `@Qualifier` expresses intent at a specific injection point; `@Order` sorts multiple beans; collections receive all matching candidates.
- Bean conditions see only bean definitions already processed. Place conditions on auto-configuration and use `@AutoConfiguration(after = ...)` when depending on another configuration.
- A minimal test matrix should cover 0 beans, 1 custom bean, multiple beans without primary, and multiple beans with primary.

Official Spring Boot 3.3.13 / Spring Framework 6.1 documentation:

1. [`@ConditionalOnMissingBean` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html) — condition that matches only when no beans meeting the criteria exist in the BeanFactory; notes on bean definition ordering.
2. [`@ConditionalOnSingleCandidate` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html) — multiple beans still match if a primary candidate exists.
3. [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html) — bean conditions, auto-configuration ordering, and ApplicationContextRunner.
4. [`@Primary` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/context/annotation/Primary.html).
5. [`@Qualifier` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/beans/factory/annotation/Qualifier.html).
6. [`@Order` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/core/annotation/Order.html).
7. [`ApplicationContextRunner` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
