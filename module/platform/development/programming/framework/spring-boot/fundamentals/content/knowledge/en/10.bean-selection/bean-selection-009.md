# @Fallback in Supported Spring Framework Versions

In a Spring Boot application, multiple beans can implement the same interface. For example, an application needs a `MetricsPublisher` to record metrics. When running standalone or in a development environment, a simple implementation might do nothing; when deployed for real, the application might provide an implementation that sends metrics to an observability system.

If both beans are registered, a constructor requesting just `MetricsPublisher` can encounter multiple candidates. Spring provides several selection mechanisms such as `@Primary` and `@Qualifier`. Starting in **Spring Framework 6.2**, there is also the `@Fallback` annotation to mark a bean as a fallback choice: when one regular bean matches and all remaining beans are marked fallback, Spring prefers the regular bean for single-valued injection.

`@Fallback` is useful when a library or configuration wants to supply a default implementation while allowing the consuming application to register its own implementation without having to mark the application's bean with `@Primary`.

This lesson explains supported versions, usage on classes and `@Bean` methods, relationships with `@Primary` and `@Qualifier`, behavior with collections, and the difference between `@Fallback` and `@ConditionalOnMissingBean`.

## 1. The problem: multiple beans satisfy one type

Suppose the application has a contract:

~~~java
package com.example.metrics;

public interface MetricsPublisher {
    void publish(String name, long value);
}
~~~

A fallback implementation might not send metrics anywhere:

~~~java
package com.example.metrics;

public class NoOpMetricsPublisher implements MetricsPublisher {
    @Override
    public void publish(String name, long value) {
        // Intentionally performs no external action.
    }
}
~~~

Another implementation writes metrics to the log:

~~~java
package com.example.metrics;

public class LoggingMetricsPublisher implements MetricsPublisher {
    @Override
    public void publish(String name, long value) {
        System.out.println("[METRIC] " + name + "=" + value);
    }
}
~~~

The service only needs the contract:

~~~java
package com.example.metrics;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final MetricsPublisher metricsPublisher;

    public CheckoutService(MetricsPublisher metricsPublisher) {
        this.metricsPublisher = metricsPublisher;
    }

    public void checkout() {
        // Perform checkout business logic...
        metricsPublisher.publish("checkout.completed", 1);
    }
}
~~~

If both `NoOpMetricsPublisher` and `LoggingMetricsPublisher` are beans, Spring sees two candidates of type `MetricsPublisher`. For single-valued injection, the container needs to know which bean should be passed into the constructor.

An older approach was marking one bean `@Primary`. However, if the NoOp implementation is merely a default option when the application has not supplied a real implementation, we can mark NoOp as `@Fallback`. Then the regular application bean will be preferred.

## 2. What is @Fallback?

`@Fallback` is a Spring Framework annotation located in package:

~~~java
import org.springframework.context.annotation.Fallback;
~~~

It marks a bean as a **fallback autowire candidate** — a backup candidate when Spring resolves dependencies by type.

This annotation:

- Exists starting in **Spring Framework 6.2**.
- Can be placed on bean classes or methods annotated with `@Bean`.
- Has runtime retention and is read by Spring during bean processing.
- Complements and serves as an alternative to `@Primary` in scenarios where you want to mark fallback beans.
- Affects only bean selection for single-valued injection when multiple candidates share a type.
- Does not remove the bean from the container.

The official Javadoc describes the rule: if among multiple matching candidates, all beans except one are marked fallback, that remaining bean is selected. Type-matching beans are still included when injecting arrays, collections, maps, or streams from `ObjectProvider`.

Point to remember: **fallback is priority metadata during bean selection**, not a mechanism to auto-create missing beans, not runtime error handling, and not a circuit breaker.

## 3. Which versions support @Fallback?

`@Fallback` was introduced in Spring Framework 6.2. Therefore, check the actual Spring Framework version used by your application, not just the Java version.

| Spring line | Underlying Framework version | Has `@Fallback`? |
| --- | --- | --- |
| Spring Framework 6.0 / 6.1 | Before 6.2 | No |
| Spring Framework 6.2.x | 6.2 and later | Yes |
| Spring Framework 7.x | 7.x | Yes |

For Spring Boot, common version relationships:

| Spring Boot line | Underlying Spring Framework | Can use `@Fallback`? |
| --- | --- | --- |
| Spring Boot 3.3.x | 6.1.x | No |
| Spring Boot 3.4.x | 6.2.x | Yes |
| Spring Boot 3.5.x | 6.2.x | Yes |
| Spring Boot 4.x | 7.x | Yes |

This table describes the corresponding release lines; specific patch versions and compatibility requirements must be checked against the documentation of the Boot version in use.

### 3.1. Why pay attention to version?

If a project uses Spring Boot 3.3.x, importing:

~~~java
import org.springframework.context.annotation.Fallback;
~~~

can cause a compiler error saying the class cannot be found, because Spring Framework 6.1.x does not provide this annotation yet.

Do not solve this by manually adding a standalone `spring-context` 6.2 JAR to a Boot 3.3 application managing Spring Framework 6.1. Spring Framework modules must be upgraded in sync according to combinations supported by Boot. If you want to use `@Fallback`, consider upgrading Spring Boot to a compatible line, such as 3.4 or later in the Boot 3.x series, then verify JDK, Gradle/Maven, and other dependency requirements.

If an application uses standalone Spring Framework, `spring-context` 6.2 or later and compatible related Spring modules of the same line are required.

### 3.2. Checking the running Framework version

In Maven, you can inspect the dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-context
~~~

In Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
~~~

This verifies the resolved version instead of guessing from a configuration line. For Boot applications, let Boot's BOM manage Spring Framework modules unless there is a clearly verified upgrade reason.

## 4. Using @Fallback on a component class

You can mark the implementation directly:

~~~java
package com.example.metrics;

import org.springframework.stereotype.Component;
import org.springframework.context.annotation.Fallback;

@Component
@Fallback
public class NoOpMetricsPublisher implements MetricsPublisher {
    @Override
    public void publish(String name, long value) {
        // Do not send metrics.
    }
}
~~~

Another regular implementation:

~~~java
package com.example.metrics;

import org.springframework.stereotype.Component;

@Component
public class LoggingMetricsPublisher implements MetricsPublisher {
    @Override
    public void publish(String name, long value) {
        System.out.println("[METRIC] " + name + "=" + value);
    }
}
~~~

When both beans are registered, the constructor:

~~~java
public CheckoutService(MetricsPublisher metricsPublisher) {
    this.metricsPublisher = metricsPublisher;
}
~~~

will receive `LoggingMetricsPublisher` because it is the only regular candidate; `NoOpMetricsPublisher` is marked fallback.

Selection flow:

~~~text
Required dependency: MetricsPublisher
             │
             ▼
Find beans matching the type
             │
       ┌─────┴─────┐
       ▼           ▼
NoOpMetrics     LoggingMetrics
 @Fallback       regular bean
       │           │
       └─────┬─────┘
             ▼
    Select regular bean
             │
             ▼
      CheckoutService
~~~

If `LoggingMetricsPublisher` is removed from the context, `NoOpMetricsPublisher` is the only candidate and can still be injected. That is the meaning of a fallback implementation.

## 5. Using @Fallback on a @Bean method

You do not have to annotate a class with `@Component`. When constructing objects via factory methods, `@Fallback` can be placed on a `@Bean` method.

~~~java
package com.example.metrics;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Fallback;

@Configuration
public class DefaultMetricsConfiguration {

    @Bean
    @Fallback
    public MetricsPublisher defaultMetricsPublisher() {
        return new NoOpMetricsPublisher();
    }
}
~~~

The application can provide its own regular bean:

~~~java
package com.example.metrics;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ApplicationMetricsConfiguration {

    @Bean
    public MetricsPublisher applicationMetricsPublisher() {
        return new LoggingMetricsPublisher();
    }
}
~~~

With these two beans, a service injecting `MetricsPublisher` receives the regular application bean. The default bean is still registered and managed by the container, yet marked as a fallback option.

This works well when writing libraries or configuration modules that wish to provide a default implementation that consuming applications can override with their own bean.

### 5.1. The return type of @Bean still matters

Declare a return type reflecting the contract:

~~~java
@Bean
@Fallback
public MetricsPublisher defaultMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

If declared too broadly:

~~~java
@Bean
@Fallback
public Object defaultMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

Spring may lack type information to predict the bean is a `MetricsPublisher` when processing dependencies prior to invoking the factory method. Expose the interface type or a concrete type suited to autowiring needs.

If consumers only need the contract, `MetricsPublisher` is the appropriate return type. The runtime object remains `NoOpMetricsPublisher`.

## 6. When does @Fallback take effect?

`@Fallback` applies when selecting a bean for a **single-valued dependency** — an injection point needing only one object.

For example:

~~~java
@Service
public class CheckoutService {
    private final MetricsPublisher publisher;

    public CheckoutService(MetricsPublisher publisher) {
        this.publisher = publisher;
    }
}
~~~

If multiple beans match and only one regular candidate remains after excluding fallback choices from preferred status, Spring chooses that regular candidate.

Basic cases:

| Matching candidates | Expected outcome |
| --- | --- |
| Only one regular bean | The regular bean is injected |
| One regular bean and one or more fallback beans | The regular bean is preferred |
| Only one fallback bean | The fallback bean is still injected |
| Multiple matching regular beans | `@Fallback` does not resolve ambiguity among regular beans |
| Multiple matching fallback beans with no other selection rule | Needs clearer specification, e.g. via `@Qualifier` |
| No matching bean | Still a missing dependency; `@Fallback` does not create beans |

When multiple unresolved candidates remain, use qualifiers or an appropriate selection rule rather than relying on registration order.

## 7. @Fallback does not exclude beans from collections

A crucial point is that `@Fallback` affects selection only for single-valued injection. When injecting a collection or map, all type-matching beans are still included.

For example:

~~~java
@Service
public class MetricsCoordinator {
    private final List<MetricsPublisher> publishers;

    public MetricsCoordinator(List<MetricsPublisher> publishers) {
        this.publishers = publishers;
    }

    public void publishAll(String name, long value) {
        for (MetricsPublisher publisher : publishers) {
            publisher.publish(name, value);
        }
    }
}
~~~

If the context has `NoOpMetricsPublisher` marked fallback and a regular `LoggingMetricsPublisher`, the list still contains both beans.

Similarly, this rule applies to:

- Arrays, e.g., `MetricsPublisher[]`.
- `List<MetricsPublisher>` or `Set<MetricsPublisher>`.
- `Map<String, MetricsPublisher>`.
- Candidate streams from `ObjectProvider<MetricsPublisher>`.

Therefore, do not interpret `@Fallback` as "this bean is hidden everywhere." It remains a registered bean and can be accessed by name or appear in collection structures.

If business logic wants to run only regular implementations, design appropriate collection filtering or qualifiers; do not expect `@Fallback` to automatically omit beans from collections.

## 8. Comparing @Fallback, @Primary, and @Qualifier

These three annotations solve different aspects of bean selection.

### 8.1. @Primary: designating the preferred choice

`@Primary` marks a bean to be preferred when multiple candidates exist for single-valued injection.

~~~java
@Bean
@Primary
public MetricsPublisher loggingMetricsPublisher() {
    return new LoggingMetricsPublisher();
}

@Bean
public MetricsPublisher noOpMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

If exactly one matching primary bean exists, Spring selects it.

Use `@Primary` when you want to say: **"Among valid options, this is the default bean that should be preferred."**

### 8.2. @Fallback: marking a backup choice

~~~java
@Bean
public MetricsPublisher loggingMetricsPublisher() {
    return new LoggingMetricsPublisher();
}

@Bean
@Fallback
public MetricsPublisher noOpMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

Use `@Fallback` when you want to say: **"This bean can satisfy the contract, but prefer a regular implementation if one exists."**

Difference in intent:

| Annotation | Meaning |
| --- | --- |
| `@Primary` | Marks a bean that should be preferred |
| `@Fallback` | Marks a bean with fallback priority |
| Unmarked | Regular candidate |
| `@Qualifier` | Narrows candidates by a specific trait or qualifier |

Both `@Primary` and `@Fallback` only apply when Spring is resolving an injection point requiring a single value. If multiple primary beans or multiple unresolvable regular candidates exist, check other selection rules.

### 8.3. @Qualifier: selecting by specific consumer requirement

If a service needs specifically the bean with the `remote` qualifier:

~~~java
@Bean
@Qualifier("local")
public MetricsPublisher localPublisher() {
    return new NoOpMetricsPublisher();
}

@Bean
@Qualifier("remote")
public MetricsPublisher remotePublisher() {
    return new LoggingMetricsPublisher();
}
~~~

Constructor:

~~~java
public CheckoutService(
        @Qualifier("remote") MetricsPublisher publisher) {
    this.publisher = publisher;
}
~~~

`@Qualifier` filters candidates by qualifier. This is the right choice when a consumer has a specific requirement, such as needing local, remote, persistent, or a certain functional group.

Do not use `@Fallback` as a substitute for `@Qualifier` when a service truly needs a specific implementation.

### 8.4. Can the mechanisms be combined?

You can use qualifiers alongside priority metadata when needed, though you should avoid building a confusing configuration with many overlapping rules.

A readable design pattern:

- `@Fallback` for a library's default implementation.
- Regular beans for application-provided implementations.
- `@Qualifier` when each consumer must explicitly choose a kind.
- `@Primary` when the application has one preferred default among multiple regular beans.

`@Order` or `Ordered` is typically used to sort elements in collections or ordered mechanisms; do not confuse it with `@Fallback` when choosing a single bean.

## 9. How does @Fallback differ from @ConditionalOnMissingBean?

These two mechanisms are often mentioned when writing Spring Boot starters or auto-configurations, yet they are not equivalent.

### 9.1. @ConditionalOnMissingBean decides whether a bean is registered

For example:

~~~java
@Bean
@ConditionalOnMissingBean(MetricsPublisher.class)
public MetricsPublisher defaultMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

If a matching bean is already registered and the condition is evaluated in the corresponding context, the default factory method may not be registered as a bean definition at all.

In other words, the condition decides **whether to create this bean definition in the context**.

### 9.2. @Fallback keeps the bean registered but gives it a backup role

~~~java
@Bean
@Fallback
public MetricsPublisher defaultMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

In this case, the default bean is still registered. If the application has a regular bean of the same type, the regular bean is preferred for single-valued injection. The fallback bean still exists in the context and can appear when injecting collections.

### 9.3. Comparison table

| Criterion | `@ConditionalOnMissingBean` | `@Fallback` |
| --- | --- | --- |
| Origin | Spring Boot autoconfigure | Spring Framework 6.2+ |
| Role | Condition for registering a bean definition | Priority marker during autowiring |
| Default bean when app defines its own | May not be registered | Still registered |
| Effect on collection injection | Only actually registered beans appear | Fallback bean still appears if type matches |
| Use when | You only want to create the default bean if no other exists | You want to keep the default bean while preferring regular beans for single-valued injection |

The two mechanisms can serve different design goals. In Spring Boot auto-configuration, `@ConditionalOnMissingBean` remains the standard tool for letting users completely replace a default configuration. `@Fallback` is useful when multiple implementations should coexist while one plays a fallback role.

Do not put both annotations on one method without clear intent. If the condition prevents the bean from being registered, fallback metadata on that bean has no effect in that context.

## 10. Application example: providing a default implementation for a starter

Suppose you are writing a shared module providing audit logging. Consuming applications need an `AuditWriter` bean.

Contract:

~~~java
public interface AuditWriter {
    void write(String event);
}
~~~

Fallback implementation:

~~~java
public class NoOpAuditWriter implements AuditWriter {
    @Override
    public void write(String event) {
        // Do not record audits in the default configuration.
    }
}
~~~

Default configuration:

~~~java
@Configuration
public class AuditDefaultConfiguration {

    @Bean
    @Fallback
    public AuditWriter defaultAuditWriter() {
        return new NoOpAuditWriter();
    }
}
~~~

In the actual application, the development team provides an implementation:

~~~java
@Component
public class DatabaseAuditWriter implements AuditWriter {
    @Override
    public void write(String event) {
        // Write event to database.
    }
}
~~~

Service consuming the contract:

~~~java
@Service
public class AccountService {
    private final AuditWriter auditWriter;

    public AccountService(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    public void changeEmail(String email) {
        // Perform email change...
        auditWriter.write("Account email changed");
    }
}
~~~

Two scenarios:

**Application provides no custom implementation:** `defaultAuditWriter` is the sole candidate, so it is injected. The application still starts and has intentional default behavior.

**Application provides `DatabaseAuditWriter`:** this bean is a regular candidate; `NoOpAuditWriter` is still present but marked fallback. `AccountService` receives `DatabaseAuditWriter`.

Thanks to this, the service does not need to know whether the application has real audit configuration or is using the fallback. It depends solely on `AuditWriter`.

Note on the example: `NoOpAuditWriter` is only suitable when skipping audit logs is acceptable for that use case. For legally or security-mandated audits, a no-op implementation can be dangerous; in those cases, require real audit configuration or fail startup when configuration is missing.

## 11. Testing bean selection behavior

A context test can verify that Spring picks the regular implementation when a fallback bean exists.

Example beans in configuration:

~~~java
@Configuration
public class AuditTestConfiguration {

    @Bean
    @Fallback
    AuditWriter fallbackAuditWriter() {
        return new NoOpAuditWriter();
    }

    @Bean
    AuditWriter customAuditWriter() {
        return new RecordingAuditWriter();
    }
}
~~~

`RecordingAuditWriter` is a test implementation that records events. Service:

~~~java
@Service
public class AccountService {
    private final AuditWriter auditWriter;

    public AccountService(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    public void changeEmail(String email) {
        auditWriter.write("Changed: " + email);
    }
}
~~~

Spring Boot test:

~~~java
@SpringBootTest(classes = {
        AuditTestConfiguration.class,
        AccountService.class
})
class AuditFallbackSelectionTest {

    @Autowired
    private AuditWriter auditWriter;

    @Test
    void selectsRegularBeanOverFallbackBean() {
        assertInstanceOf(RecordingAuditWriter.class, auditWriter);
    }
}
~~~

The test requires JUnit, Spring Boot Test, and corresponding Spring types imported; `NoOpAuditWriter` and `RecordingAuditWriter` implementations must be defined in test or appropriate sources.

You can also test the collection:

~~~java
@Autowired
private List<AuditWriter> writers;

@Test
void includesFallbackBeanInCollection() {
    assertEquals(2, writers.size());
}
~~~

This illustrates that the fallback bean remains registered and still appears in collection injection.

### 11.1. Testing with only the fallback bean

Create a context registering only `fallbackAuditWriter`, then inject `AuditWriter`. The fallback bean remains the sole choice and is supplied.

### 11.2. Testing with two regular beans

If you configure two `AuditWriter` beans not marked fallback and an injection point asks for a single value, `@Fallback` on a third bean does not choose between the two regular beans. The test should confirm the context fails with ambiguity unless there is a qualifier, primary, or another selection rule.

Do not merely test that the application starts with one implementation; verify the exact configuration scenarios your module intends to support.

## 12. Common misconceptions

### 12.1. "@Fallback means only create the bean when no other bean exists"

Incorrect. `@Fallback` is not a condition preventing registration. The bean is registered normally; the annotation only marks its role in autowire candidate selection. If you want to skip registering the bean when another implementation exists, consider `@ConditionalOnMissingBean`.

### 12.2. "@Fallback excludes the bean from List or Map"

No. Type-matching beans are still included in arrays, collections, maps, and `ObjectProvider` streams. Fallback only affects single-valued dependency selection.

### 12.3. "@Fallback is error handling when the primary service fails"

No. The annotation does not automatically detect exceptions, timeouts, connection errors, or unhealthy states. It does not switch to another implementation after a method on the main bean throws an error.

If runtime failover is needed, design dedicated resilience mechanisms such as retries, circuit breakers, routing, or business exception handling.

### 12.4. "@Fallback replaces @Qualifier"

No. If a consumer needs specifically an implementation with certain characteristics, a qualifier is the right way to express it. Fallback only distinguishes backup beans from regular candidates during single-valued autowiring.

### 12.5. "Just add @Fallback and NoUniqueBeanDefinitionException goes away"

No. If multiple matching regular candidates remain, or multiple fallback candidates remain without a clear selection rule, ambiguity can still exist. Inspect the bean list, qualifiers, and primary metadata.

### 12.6. "@Fallback works on every Spring Boot 3.x"

No. Spring Boot 3.3.x uses Spring Framework 6.1.x, which does not include this annotation. Framework 6.2 or later is required; in the Boot 3.x line, that corresponds to Boot 3.4 or later.

### 12.7. "Marking a class as fallback is enough even if the class is not registered"

No. `@Fallback` does not replace `@Component`, `@Bean`, or other bean registration mechanisms. If the class is not discovered or registered by the container, the annotation cannot create a bean definition on its own.

## 13. Diagnostic workflow when the fallback bean is not chosen as expected

When injection outcomes differ from expectations, check in order:

1. **Framework version:** does the application have Spring Framework 6.2+?
2. **Is the bean registered?** Do component scan, `@Bean` methods, profiles, and conditions allow the bean to exist?
3. **Does the type match?** Does the bean actually implement the interface or extend the type requested by the injection point?
4. **Is fallback metadata placed properly?** Is the annotation on the component class or factory method actually attached to the real bean definition?
5. **Are there multiple regular beans?** `@Fallback` does not pick between remaining regular candidates.
6. **Are there qualifiers or primary?** Other metadata may affect candidate selection.
7. **Is injection single-valued or a collection?** Collections still receive every type-matching bean, including fallbacks.
8. **Is a bean coming from another context?** Parent/child contexts or test configurations can make the candidate set differ from expectations.

Common exceptions:

| Exception | Possible related meaning |
| --- | --- |
| `NoSuchBeanDefinitionException` | No matching bean registered/visible |
| `NoUniqueBeanDefinitionException` | Multiple candidates exist, yet a single bean cannot be chosen |
| `UnsatisfiedDependencyException` | A dependency could not be resolved during bean creation |

Read the root cause and bean names in the stack trace. Do not fix blindly by adding `@Primary` or changing scopes before understanding the candidate set.

## 14. When should you use @Fallback?

`@Fallback` fits well in situations such as:

- A library wants to provide a default implementation so applications can run out of the box.
- An application has a no-op or simple implementation for environments not needing external integrations.
- A module provides a backup bean while allowing consuming applications to register a regular bean.
- You want to keep multiple beans in the container while letting one bean act as a fallback for single-valued injection.

Do not use `@Fallback` when:

- Only one bean exists with no competing candidates; the annotation usually adds no selection value.
- A consumer needs a specific implementation; use `@Qualifier`.
- You need to explicitly prioritize one implementation among multiple regular candidates; consider `@Primary`.
- You want not to register the default bean when the user already provided one; consider `@ConditionalOnMissingBean`.
- You need to switch to another implementation after a runtime failure; use an appropriate resilience mechanism.

Choose the annotation based on the configuration intent you want to express, not merely to make the context start up.

## 15. Practice exercises

### Exercise A: Selecting a default bean

Create an interface:

~~~java
public interface GreetingProvider {
    String greeting(String name);
}
~~~

Create two implementations:

- `DefaultGreetingProvider` returns a simple greeting and is marked `@Fallback`.
- `VietnameseGreetingProvider` responds according to its own rules and is a regular bean.

Create a service injecting `GreetingProvider`. When both beans are registered, verify the Vietnamese implementation is selected.

### Exercise B: Only the fallback bean

Temporarily remove `VietnameseGreetingProvider` from the context. Re-run the test and verify `DefaultGreetingProvider` is still injected.

Explain why a fallback bean is not ignored simply because it carries `@Fallback`.

### Exercise C: Multiple regular beans

Add `EnglishGreetingProvider` without marking it fallback. Now there are two regular beans of the same type and one fallback bean.

Observe the error when injecting a single `GreetingProvider`. Fix it with `@Qualifier` or `@Primary` and explain the distinct role of each annotation.

### Exercise D: Collection injection

Inject `List<GreetingProvider>`. Confirm the list still contains both the fallback bean and the regular beans.

Explain why this outcome differs from a constructor taking a single `GreetingProvider`.

### Exercise E: Comparing with @ConditionalOnMissingBean

Write two separate configurations:

1. One configuration using `@Fallback` on the default bean.
2. One configuration using `@ConditionalOnMissingBean(GreetingProvider.class)`.

When the application provides its own implementation, observe the difference in the number of registered beans and collection injection results.

### Exercise F: Checking version compatibility

In a Spring Boot 3.3.x project, try importing `org.springframework.context.annotation.Fallback` and note the compilation error. Then inspect the dependency tree of `spring-context`, upgrade the project to a Boot line compatible with Spring Framework 6.2, and confirm the import resolves.

This exercise helps understand that the annotation belongs to Framework and is supplied according to Boot's managed versions.

## 16. Self-check questions

**1. Which Spring Framework version introduced @Fallback?**

Spring Framework 6.2. Applications using Framework 6.1 or earlier do not have this annotation.

**2. Can Spring Boot 3.3.x use @Fallback directly?**

Not under the default dependency combination, because Boot 3.3.x uses Framework 6.1.x. Spring Boot 3.4.x moves to Framework 6.2.x and supports the annotation.

**3. If there are one regular bean and one fallback bean of the same type, which bean is injected into a constructor?**

The regular bean is preferred, unless another specific selection rule alters the candidates.

**4. If only one fallback bean exists, can Spring inject it?**

Yes. In that case it is the sole matching candidate.

**5. Does @Fallback exclude beans from List?**

No. All type-matching beans are still included in arrays, collections, maps, and `ObjectProvider` streams.

**6. How does @Fallback differ from @Primary?**

`@Primary` marks the preferred bean; `@Fallback` marks the backup bean so a regular bean is chosen when available.

**7. Does @Fallback replace @ConditionalOnMissingBean?**

No. `@ConditionalOnMissingBean` controls bean definition registration; `@Fallback` controls priority when choosing beans for autowiring.

**8. Does @Fallback automatically handle runtime errors of the main implementation?**

No. It is a bean selection mechanism during dependency resolution, not a failover mechanism when a method call fails.

## 17. Conclusion

`@Fallback` helps Spring Framework explicitly express that an implementation is a **backup choice** when multiple beans satisfy one type. Introduced in Spring Framework 6.2, the annotation can be placed on bean classes or `@Bean` methods. In the Spring Boot 3.x family, Boot 3.4 or later is required to get Framework 6.2 in the base configuration; Boot 3.3.x and Framework 6.1 lines do not support it.

When injecting a single value, if a single regular bean exists alongside fallback beans, Spring picks the regular bean. If only a fallback bean exists, it is still used. When injecting collections, fallback beans remain included. Use `@Primary` for preferred choices, `@Qualifier` for specific choices, and `@ConditionalOnMissingBean` when you want to control default bean registration.

The value of `@Fallback` lies in letting a library or configuration offer a default implementation that consuming applications can effortlessly supersede with their own bean. Properly understanding the annotation's scope and limits helps design clean IoC configurations without confusing startup-time bean selection with runtime failover.

## References

- [Spring Framework 6.2 — @Fallback Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/annotation/Fallback.html)
- [Spring Framework Reference — Fine-tuning Autowiring with @Primary or @Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework 6.2 Release Notes — Support for fallback beans](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes)
- [Spring Boot 3.3 System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html)
- [Spring Boot 3.4 System Requirements](https://docs.spring.io/spring-boot/3.4/system-requirements.html)
