# How the Return Type of `@Bean` Affects Candidate Inference

**Topic:** Spring Boot Auto Configuration → Bean Conditions  
**Focus:** Why the declared return type on a `@Bean` method can determine the outcome of `@ConditionalOnBean` and `@ConditionalOnMissingBean`, even when the actual returned object is still the exact same class.

## 1. Understanding the Problem Properly

In Spring, a `@Bean` method both creates an object and provides type information to the container:

```java
@Bean
AuditSink auditSink() {
    return new FileAuditSink();
}
```

Suppose `FileAuditSink implements AuditSink`. Here there are **two different types**:

- **Declared return type:** `AuditSink`, which is the type Spring sees directly from the method signature.
- **Runtime object type:** `FileAuditSink`, which is only certain once the method is invoked and the object is created.

Spring does not necessarily instantiate every bean before deciding whether to register other beans. When evaluating bean-based conditions, the framework must use the type information *currently available* in the bean definitions. For beans coming from `@Bean`, the declared return type is a key source of information for predicting candidate types.

**Consequence:** A bean that is actually a `FileAuditSink` at runtime but declared to return `AuditSink` may not be recognized as a candidate for a condition looking for `FileAuditSink` at the time the condition runs. After the bean has been instantiated, a runtime type lookup can see the concrete class; that does not change the condition decision that was already made earlier.

## 2. Why Auto-Configuration Is Especially Sensitive to Type Information

Two familiar Spring Boot conditions are:

- `@ConditionalOnBean(X.class)`: matches only when a bean compatible with type `X` exists in the search scope.
- `@ConditionalOnMissingBean(X.class)`: matches only when no bean compatible with type `X` exists yet in the search scope; commonly used to provide a default bean and **back off** for an application-defined bean.

Conditions are evaluated against **the bean definitions processed up to that point**. Therefore, there are **two independent variables** to control: the type exposed by the bean definition and the processing order of configurations. Spring Boot recommends placing conditions that depend on bean presence in auto-configuration, because user configuration is typically processed before auto-configuration.

Visualizing the typical sequence:

1. Spring reads user configuration and creates a bean definition for `@Bean AuditSink auditSink()`.
2. The bean definition has return type info `AuditSink`; it does not necessarily contain info that the object will be `FileAuditSink`.
3. Auto-configuration checks `@ConditionalOnMissingBean(FileAuditSink.class)`.
4. If no candidate of type `FileAuditSink` is recognized, the condition can match and register an additional default bean.
5. Singletons are created later; at that point both objects may implement `AuditSink`.

This is a matter of **type inference capability before instantiation**, not Java losing the runtime type, nor `@Bean` itself always creating an extra object.

## 3. A Trap Easy to Hit: Returning an Interface While the Condition Looks for an Implementation

Suppose the library has two types:

```java
interface AuditSink {
}

final class FileAuditSink implements AuditSink {
}
```

The application configuration declares it broadly:

```java
@Configuration(proxyBeanMethods = false)
class UserAuditConfiguration {

    @Bean
    AuditSink auditSink() {
        return new FileAuditSink();
    }
}
```

The auto-configuration, however, checks for the concrete type:

```java
@AutoConfiguration
class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FileAuditSink.class)
    FileAuditSink defaultAuditSink() {
        return new FileAuditSink();
    }
}
```

`auditSink` already exists under the declared type `AuditSink`, but the condition on `defaultAuditSink` needs to see `FileAuditSink`. When the user bean has not been instantiated yet and the container cannot infer the concrete class, the condition concludes no candidate exists yet, resulting in **two beans** (`auditSink` and `defaultAuditSink`).

Fixing the user configuration's method signature:

```java
@Bean
FileAuditSink auditSink() {
    return new FileAuditSink();
}
```

Then the bean definition exposes `FileAuditSink` directly; `@ConditionalOnMissingBean(FileAuditSink.class)` recognizes the candidate and the default bean backs off, assuming the user configuration is processed before the auto-configuration condition.

| Declaration in User `@Bean` | Auto-Configuration Condition | Expected Result When Evaluated Before Singleton Creation |
| --- | --- | --- |
| `AuditSink auditSink()` | `@ConditionalOnMissingBean(AuditSink.class)` | Bean recognized by interface; default bean backs off |
| `AuditSink auditSink()` | `@ConditionalOnMissingBean(FileAuditSink.class)` | Risk of not recognizing the bean by implementation; registers an extra default |
| `FileAuditSink auditSink()` | `@ConditionalOnMissingBean(FileAuditSink.class)` | Implementation recognized; default bean backs off |
| `FileAuditSink auditSink()` | `@ConditionalOnMissingBean(AuditSink.class)` | Recognized because `FileAuditSink` implements `AuditSink`; default bean backs off |

The table describes the typical case when conditions are evaluated against bean definitions before singletons are instantiated. Mechanisms such as special factory methods, `FactoryBean`, proxies, already-instantiated beans, or custom type prediction can supply different information; do not treat the example as an absolute rule for every phase of the container lifecycle.

## 4. Runnable Experiment: Same Object, Different Signature, Different Condition Result

The experiment below uses **Java 17**, **Spring Boot 3.3.5**, JUnit 5, and `ApplicationContextRunner`. This is a standalone test program: no web server, database, or running Boot application is required.

### 4.1. Create the Maven Project

Save the `pom.xml` file in the project directory:

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
    <artifactId>bean-return-type-demo</artifactId>
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

### 4.2. Write a Complete Test Class

Create `src/test/java/demo/BeanReturnTypeConditionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class BeanReturnTypeConditionTest {

    interface AuditSink {
    }

    static final class FileAuditSink implements AuditSink {
    }

    @Configuration(proxyBeanMethods = false)
    static class BroadReturnConfiguration {
        @Bean
        AuditSink auditSink() {
            return new FileAuditSink();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SpecificReturnConfiguration {
        @Bean
        FileAuditSink auditSink() {
            return new FileAuditSink();
        }
    }

    @AutoConfiguration
    static class DefaultAuditAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(FileAuditSink.class)
        FileAuditSink defaultAuditSink() {
            return new FileAuditSink();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(DefaultAuditAutoConfiguration.class)
                    );

    @Test
    void broadReturnTypeCanHideConcreteCandidateAtConditionTime() {
        runner.withUserConfiguration(BroadReturnConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasBean("auditSink");
                    assertThat(context).hasBean("defaultAuditSink");
                    assertThat(context.getBeansOfType(AuditSink.class)).hasSize(2);
                });
    }

    @Test
    void specificReturnTypeLetsConditionFindTheCandidate() {
        runner.withUserConfiguration(SpecificReturnConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasBean("auditSink");
                    assertThat(context).doesNotHaveBean("defaultAuditSink");
                    assertThat(context.getBeansOfType(AuditSink.class)).hasSize(1);
                });
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

**Expected result:** both tests PASS (Maven reports `Tests run: 2, Failures: 0, Errors: 0, Skipped: 0` in the Surefire output under standard configuration). No `System.out.println` output is needed from the Java code. The assertions prove:

- With `AuditSink auditSink()`, the `defaultAuditSink` bean can still be registered even though the `auditSink` object ultimately turns out to be a `FileAuditSink`.
- With `FileAuditSink auditSink()`, the condition sees the candidate bean and does not register `defaultAuditSink`.
- Being able to count two instances of type `AuditSink` after the context has refreshed **does not** mean the earlier condition had to know their runtime types.

If the first test fails because of an environment or library version with a different type-prediction mechanism, inspect the condition report and bean definitions instead of concluding that Java does not support interfaces. These two tests are intentionally checking the behavior under the stated Spring Boot configuration.

## 5. Subtle Point: The Signature Also Affects the *Default* Target Type of the Condition Itself

On a `@Bean` method, when `value`, `type`, `name`, `annotation`, etc. are not explicitly specified to determine what to look up, `@ConditionalOnMissingBean` can use **the return type of the annotated method** as its target.

```java
@Bean
@ConditionalOnMissingBean
AuditSink defaultAuditSink() {
    return new FileAuditSink();
}
```

In this case, the condition's target is `AuditSink`. If you change the return type to `FileAuditSink` while **leaving** `@ConditionalOnMissingBean` without arguments, the check target becomes `FileAuditSink`. The condition then no longer carries the same policy meaning: another `OtherAuditSink implements AuditSink` bean may not cause the `FileAuditSink` fallback to back off.

If the business rule is **there may only be one application-chosen `AuditSink`, with the fallback used only when no `AuditSink` exists at all**, a clearer way to write it is:

```java
@Bean
@ConditionalOnMissingBean(AuditSink.class)
FileAuditSink defaultAuditSink() {
    return new FileAuditSink();
}
```

This approach separates two goals:

- **Return type `FileAuditSink`:** provides the concrete type to the container and other conditions/injection points.
- **Condition target `AuditSink.class`:** specifies precisely when the fallback must back off for another implementation.

Conversely, if the fallback should only be replaced by the *same implementation* `FileAuditSink`, keep `@ConditionalOnMissingBean(FileAuditSink.class)` and understand that a different `AuditSink` implementation will not automatically disable the fallback.

Similarly, you should explicitly declare `@ConditionalOnBean(AuditSink.class)` or `@ConditionalOnBean(FileAuditSink.class)` depending on the actual required dependency, rather than letting the annotated method signature accidentally define the lookup policy.

## 6. Principles for Applying in Projects

### 6.1. Expose a Specific Yet Contract-Accurate Type

Prefer:

```java
@Bean
FileAuditSink auditSink() {
    return new FileAuditSink();
}
```

over:

```java
@Bean
Object auditSink() {
    return new FileAuditSink();
}
```

or declaring an overly broad interface if other conditions, injections, or configurations in the system need to know `FileAuditSink` before the bean is instantiated. A method returning `Object` typically hides nearly all useful type prediction.

However, **declaring an interface is not always wrong**. If all consumers and conditions only depend on `AuditSink`, returning `AuditSink` can be a consistent API design. Put the implementation in the return type when the concrete class is genuinely information that other bean definitions need to recognize and when it fits your API exposure level.

### 6.2. Be Careful with Generics, Factories, and Proxies

For example, the difference between the full parameterized type `Handler<Order>` and the raw type `Handler` can lose generic info used for dependency resolution. Spring uses `ResolvableType` to preserve type info when possible. With `FactoryBean`, the container also needs metadata or a suitable `getObjectType()` to recognize the type of object produced. Proxies can cause the observed runtime type to differ from the original implementation class.

These are situations you should verify practically with `ApplicationContextRunner` and bean definitions. Do not deduce everything solely from `getClass()` or from a single `getBeanNamesForType()` call after the application has started.

### 6.3. Do Not Mix Up Three Different Mechanisms

| Mechanism | Purpose | Does It Solve Missing Type Info at Condition Time? |
| --- | --- | --- |
| `@Bean` return type | Exposes the type for the container to predict and look up beans | **Yes**, when the type to recognize is in the signature |
| `@ConditionalOnBean` / `@ConditionalOnMissingBean` | Decides whether to register a bean based on already-known beans | **Affected** by type info and configuration ordering |
| `@Primary` / `@Qualifier` | Helps select a bean when injecting dependencies | **Does not fix** a condition decision that has already been made |
| Duplicate bean names / allowing bean definition overriding | Controls bean definition conflicts by name | **A different issue** from two differently named beans sharing an interface |

Two differently named beans (`auditSink`, `defaultAuditSink`) can exist even when the application **does not enable** `spring.main.allow-bean-definition-overriding`; that flag is not a solution for type-prediction issues.

## 7. Systematic Inspection and Debugging

When auto-configuration does not create a bean as expected or creates a duplicate bean:

1. **Read the `@Bean` signature** of the candidate bean and check the declared return type, not just the `return new ...` statement.
2. **Read the condition accurately:** does the condition look for an interface, an implementation, a bean name, an annotation, or a type implicitly inferred from the return type?
3. **Check registration timing:** has the user bean been processed before the auto-configuration yet? `@AutoConfiguration(after = ...)` and ordering attributes must be used when auto-configurations depend on each other.
4. **Write tests with `ApplicationContextRunner`** covering having a user bean, having no user bean, and having a bean with a broad return type.
5. **Inspect the Condition Evaluation Report**: run the Spring Boot application with `--debug`, or use `ConditionEvaluationReportLoggingListener` in tests, to see why `OnBeanCondition` matched or did not match. When the application uses Actuator and the endpoint is appropriately enabled/exposed, `/actuator/conditions` can also help with analysis.
6. **Compare bean definitions against instances**: a lookup after refresh may see a concrete type that a condition before refresh could not see.

If a dependency is optional and may be completely absent from the classpath, handle class loading separately: place `@ConditionalOnClass` on a separate configuration class (often a nested `@Configuration`) to avoid forcing the JVM to resolve a `@Bean` signature containing an absent type before the method-level condition is checked. That is a classpath/bytecode issue, distinct from an interface masking an implementation.

## 8. Self-Check Questions

**Question 1.** A `@Bean PaymentGateway gateway()` returns `new StripeGateway()`. When `@ConditionalOnBean(StripeGateway.class)` is evaluated before singletons are instantiated, can we conclude for certain that the condition matches?  
**Answer:** No. The return type only exposes `PaymentGateway`; `StripeGateway` type info may not have been inferred yet. You need to inspect the declared type, other metadata sources, and evaluation timing.

**Question 2.** If we want a `DefaultPaymentGateway` fallback to appear only when *no* `PaymentGateway` exists at all, how should we write it?  
**Answer:** `@Bean @ConditionalOnMissingBean(PaymentGateway.class) DefaultPaymentGateway defaultGateway() { ... }`. This gives both a concrete return type and an interface-based target matching the policy.

**Question 3.** Does adding `@Primary` to the user bean guarantee preventing auto-configuration from creating a fallback?  
**Answer:** No. `@Primary` generally governs dependency selection when multiple candidates exist; it does not make a condition checking an implementation with missing type info suddenly match.

**Question 4.** Why can `getBeansOfType(StripeGateway.class)` after context startup return a different result from the earlier condition evaluation?  
**Answer:** After the singleton is created, the runtime type may be known; bean registration conditions are decided at an earlier stage.

## 9. Key Takeaway

**The return type of a `@Bean` method is important design metadata in `BeanDefinition`, not merely a Java type for the compiler.** When writing auto-configuration, expose a usefully concrete type in the signature while explicitly stating the type the condition should look up according to business intent. Check both the signature and configuration processing order before concluding that Spring Boot "cannot see" or "creates duplicate" beans.

### References

- [Spring Boot — Creating Your Own Auto-configuration, Bean Conditions section](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
