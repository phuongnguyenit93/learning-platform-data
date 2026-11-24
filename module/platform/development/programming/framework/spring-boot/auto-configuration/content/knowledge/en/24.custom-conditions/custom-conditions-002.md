# Implementing a Condition with Deterministic Inputs and No Side Effects

## 1. Goal and Problem to Solve

Spring lets you define custom conditions to decide whether a configuration class or a `@Bean` method is eligible for registration. This mechanism is useful when built-in condition annotations such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, or `@ConditionalOnWebApplication` cannot express your library's business rules.

A custom condition runs very early in the ApplicationContext initialization lifecycle. If it creates beans, calls external services, mutates the registry, reads the current time, or relies on mutable state, the outcome can become non-repeatable and break startup.

This lesson focuses on Spring Boot **3.3.13**, Spring Framework 6.1, and Java 17+. The goal is to implement a `Condition` with the following properties:

- **Deterministic inputs:** inputs come from annotation metadata and the context's `Environment`.
- **Pure result:** the same metadata and the same property values always yield the same boolean result.
- **No side effects:** do not create beans, call `getBean()`, write files, make network calls, access a database, modify the Environment, or register bean definitions.
- **Testable:** each test declares its own properties, independent of the machine, time of execution, or state of other tests.
- **Easy to diagnose:** know how to combine custom conditions with the condition report when developing auto-configuration.

The running example is a library that enables `RegionFeature` only when the `acme.region` property matches the region specified in the `@ConditionalOnRegion` annotation.

## 2. What Is a Condition and at Which Stage Does It Run?

`org.springframework.context.annotation.Condition` is a Spring Framework SPI. A condition decides whether a component is eligible to be registered.

Primary signature:

~~~java
boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
);
~~~

The two parameters provide two distinct groups of data:

| Parameter | Provides | What is it used for? |
| --- | --- | --- |
| `ConditionContext` | Environment, BeanDefinitionRegistry, BeanFactory if available, ResourceLoader, and ClassLoader | Reading properties, checking classes/resources, or inspecting needed registration information |
| `AnnotatedTypeMetadata` | Annotation metadata of the class or method being evaluated | Reading annotation attributes, including composed annotations |

Spring evaluates a condition **immediately before the corresponding bean definition is due to be registered**. The condition can allow or veto registration based on information determinable at that point.

This means `Condition` is not a callback that runs after the application has created all its beans. When `matches()` is called, many beans may not yet exist as instances.

### 2.1. How Condition Differs from BeanFactoryPostProcessor and BeanPostProcessor

| Component | Timing and responsibility |
| --- | --- |
| `Condition` | Evaluates a condition before a component/bean definition is registered |
| `BeanFactoryPostProcessor` | Works with bean definitions and BeanFactory metadata before regular beans are created |
| `BeanPostProcessor` | Intervenes on bean instances during initialization |

Spring requires `Condition` to follow the same restrictions as `BeanFactoryPostProcessor`, especially **never interacting with bean instances**. Calling `getBean()` from a condition can cause beans to be instantiated prematurely, bypassing part of the lifecycle or post-processing and creating hard-to-control dependencies.

Therefore, treat `Condition` as a calculation based on metadata/context, not a place to perform business work.

### 2.2. Where Can @Conditional Be Placed?

`@Conditional` can be used:

- Directly on a configuration class.
- On a `@Bean` method.
- As a meta-annotation on a custom annotation.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(InternalRegionCondition.class)
class InternalConfiguration {
    // Beans in this configuration are registered only when the condition matches.
}
~~~

When placed on a configuration class, associated `@Bean`, `@Import`, and `@ComponentScan` declarations on that class are subject to the condition. When placed on a `@Bean` method, the condition applies to the bean definition provided by that method.

Conditions on the same class or method are ordered according to `Ordered` and `@Order` rules. Even so, design each condition to be independent without relying on side effects from a previously evaluated condition.

## 3. What Are Deterministic Inputs and a Side-Effect-Free Condition?

A well-behaved condition can be described as a function:

~~~text
result = matches(annotationMetadata, environmentSnapshot)
~~~

If two evaluations have the same metadata and the same property values, the result must be identical.

### 3.1. Inputs You Should Use

Suitable inputs typically include:

- Explicitly declared annotation attributes, such as `@ConditionalOnRegion("internal")`.
- Properties already present in the `Environment`, such as `acme.region=internal`.
- Presence of classes via the ClassLoader.
- Presence of resources via the ResourceLoader.
- Bean definition metadata when it is truly necessary to inspect registration structure and the right configuration phase has been chosen.

These values belong to the context being initialized. Tests can supply them explicitly to reproduce the exact same scenario.

### 3.2. Sources That Make Results Non-Deterministic

Avoid introducing the following into `matches()`:

| Source | Why does it make control difficult? | How to handle it |
| --- | --- | --- |
| `System.currentTimeMillis()` or `LocalDateTime.now()` | Result changes depending on evaluation time | Pass the time as a fixed property/input if the business logic truly requires it |
| `new Random()` or `UUID.randomUUID()` | Same configuration can yield different results | Do not use randomness to decide bean registration |
| HTTP, database, message broker | Depends on network, services, timeouts, and external state | Move the check into a bean/service after the context is created |
| Reading arbitrary files on disk | Depends on working directory, permissions, and file contents | Use intentional properties or resource conditions |
| `System.getenv()` directly | Hard to isolate in tests and depends on the host machine | Read properties through Spring's `Environment` so tests can override them |
| Static mutable state | Result depends on test order or prior contexts | Use immutable local variables and context inputs |
| `getBean()` | Can instantiate beans before their normal lifecycle | Read only necessary metadata/definitions; do not fetch bean instances |
| Writing to the registry or modifying Environment | The condition alters the very data other conditions are evaluating | Only read the context and return a boolean |

Not every read operation is a side effect. Reading the `Environment`, annotation metadata, or the classpath is normal usage. The problem lies in conditions mutating state, creating external interactions, or depending on uncontrolled inputs.

### 3.3. Purity and Repeatability

Keep your implementation aligned with these principles:

1. Use local variables for intermediate values.
2. Do not store results in static fields or mutable caches.
3. Do not mutate objects passed via `ConditionContext`.
4. Do not assume `matches()` will be called only once.
5. Do not depend on the order of tests or other contexts.
6. Handle missing properties explicitly.
7. Clearly define case sensitivity, whitespace handling, and default values in comparisons.

In the example below, the comparison is an **exact, case-sensitive match**. `internal` matches `internal`; `Internal`, `internal `, and a missing property all fail to match. This simple rule keeps tests and behavior predictable.

## 4. Choose Built-In APIs Before Writing a Custom Condition

Not every condition needs a custom implementation. Spring Boot already provides standard conditions:

| Requirement | API to prefer |
| --- | --- |
| Class present/absent on classpath | `@ConditionalOnClass`, `@ConditionalOnMissingClass` |
| Property has a specific value | `@ConditionalOnProperty` |
| Bean present/absent | `@ConditionalOnBean`, `@ConditionalOnMissingBean` |
| Single candidate can be autowired | `@ConditionalOnSingleCandidate` |
| Resource exists | `@ConditionalOnResource` |
| Servlet/Reactive context | `@ConditionalOnWebApplication`, `@ConditionalOnNotWebApplication` |
| Custom business rule combining metadata/properties with custom logic | Custom `Condition` |

A custom condition is appropriate when the rule needs to read annotation attributes, combine multiple values, or apply a domain-specific comparison that built-in annotations do not express clearly.

If you only need to check `acme.feature.enabled=true`, use `@ConditionalOnProperty`. Writing a custom condition for the same task increases code to maintain without adding value.

## 5. Designing a Custom Annotation with Clear Inputs

We want users to write:

~~~java
@ConditionalOnRegion("internal")
@AutoConfiguration
public class InternalRegionAutoConfiguration {
    // Beans for the internal region.
}
~~~

The annotation carries the expected value. The `acme.region` property in the `Environment` carries the actual value. The condition simply compares the two.

### 5.1. The ConditionalOnRegion Annotation

File `src/main/java/demo/condition/ConditionalOnRegion.java`:

~~~java
package demo.condition;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(RegionCondition.class)
public @interface ConditionalOnRegion {

    String value();
}
~~~

Explanation:

- `@Target(TYPE, METHOD)` allows using the annotation on a class or method.
- `@Retention(RUNTIME)` lets Spring read the annotation while processing configuration.
- `@Conditional(RegionCondition.class)` links the annotation to its implementation.
- `value()` is the explicit input provided by the configuration author.

This composed annotation does not need `@Component`. It simply describes a condition that can be applied to a component or bean method.

**Note on inheritance:** `@Conditional` is not declared with `@Inherited`; custom annotations meta-annotated with `@Conditional` should not add `@Inherited` either. When a condition needs to apply, place the annotation directly on the corresponding class/method.

## 6. Implementing a Pure, Side-Effect-Free RegionCondition

File `src/main/java/demo/condition/RegionCondition.java`:

~~~java
package demo.condition;

import java.util.Map;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class RegionCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Map<String, Object> attributes =
            metadata.getAnnotationAttributes(
                ConditionalOnRegion.class.getName()
            );

        if (attributes == null) {
            return false;
        }

        String expectedRegion = (String) attributes.get("value");
        String actualRegion =
            context.getEnvironment().getProperty("acme.region");

        return expectedRegion.equals(actualRegion);
    }
}
~~~

### 6.1. Step-by-Step Breakdown

**Step 1 — Read annotation metadata**

~~~java
Map<String, Object> attributes =
    metadata.getAnnotationAttributes(
        ConditionalOnRegion.class.getName()
    );
~~~

`AnnotatedTypeMetadata` provides the attributes of the annotation on the class or method being evaluated. This API can also read attributes of composed annotations (meta-annotation hierarchies) and supports `@AliasFor` via the merged annotations mechanism.

If the annotation is absent on the metadata being inspected, the implementation returns `false`. With proper usage, the condition is invoked via `@ConditionalOnRegion` so the attributes will be present; the null branch still provides safe handling.

**Step 2 — Retrieve the expected value**

~~~java
String expectedRegion = (String) attributes.get("value");
~~~

This is the static input declared on the annotation. For example, `@ConditionalOnRegion("internal")` gives the expected value `internal`.

**Step 3 — Read the actual value from Environment**

~~~java
String actualRegion =
    context.getEnvironment().getProperty("acme.region");
~~~

`ConditionContext` provides the current context's `Environment`. Properties are resolved according to the order of property sources configured in Spring.

In tests, you can set properties using `ApplicationContextRunner.withPropertyValues(...)`. There is no need to read OS environment variables directly.

**Step 4 — Compare and return the result**

~~~java
return expectedRegion.equals(actualRegion);
~~~

`String.equals` performs an exact comparison and returns `false` if `actualRegion` is `null`. The condition only returns a boolean; Spring is responsible for deciding whether the component/bean definition is registered.

### 6.2. Why Is This Implementation Side-Effect-Free?

Inside `matches()`:

- Does not create or retrieve bean instances.
- Does not modify the Environment or BeanDefinitionRegistry.
- Does not write files or make network/database calls.
- Does not read a clock or randomness.
- Does not write state to static fields.
- Does not mutate annotation metadata.
- Only reads two values and returns the comparison result.

As a result, the same `@ConditionalOnRegion("internal")` and the same `Environment` will always produce the same result. The condition can also be re-evaluated in another context without carrying over state from a previous run.

### 6.3. Do Not Inject Dependencies Like a Regular Bean

Do not design a condition like this:

~~~java
// Do not use this approach inside a Condition.
@Autowired
private RegionService regionService;
~~~

A condition is used by the framework during bean definition registration processing. It is not the place to ask Spring to initialize a service and inject it into the condition. Retrieve data via `ConditionContext` and `AnnotatedTypeMetadata`.

If a service is needed to perform complex logic, create the bean/service after the context has been created and let that service do the work at runtime.

## 7. Using a Custom Condition in Auto-Configuration

File `src/main/java/demo/condition/RegionFeature.java`:

~~~java
package demo.condition;

public record RegionFeature(String region) {
}
~~~

File `src/main/java/demo/condition/RegionAutoConfiguration.java`:

~~~java
package demo.condition;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnRegion("internal")
public class RegionAutoConfiguration {

    @Bean
    public RegionFeature regionFeature() {
        return new RegionFeature("internal");
    }
}
~~~

When the property `acme.region=internal` is set, the auto-configuration class is eligible and the `RegionFeature` bean is registered. When the property is `public` or missing, the configuration class is vetoed by the condition and the bean is not registered.

### 7.1. Registering Auto-Configuration in a JAR

If the library is published as a JAR for other applications to use, add the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Contents:

~~~text
demo.condition.RegionAutoConfiguration
~~~

The imports file registers the auto-configuration candidate. The custom condition continues to decide whether that candidate is applied in the current context.

In the test example below, `AutoConfigurations.of(RegionAutoConfiguration.class)` feeds the class directly into the runner to test the condition in isolation. When packaging a real library, Spring Boot consumers discover the class through the imports file.

### 7.2. Condition on Class or Method?

Use on the class when the entire auto-configuration only applies to one input:

~~~java
@AutoConfiguration
@ConditionalOnRegion("internal")
public class InternalRegionAutoConfiguration {
    // All beans in this class depend on the same condition.
}
~~~

Use on a bean method when only a single bean needs that condition:

~~~java
@AutoConfiguration
public class RegionAwareAutoConfiguration {

    @Bean
    @ConditionalOnRegion("internal")
    InternalRegionClient internalRegionClient() {
        return new InternalRegionClient();
    }

    @Bean
    @ConditionalOnRegion("public")
    PublicRegionClient publicRegionClient() {
        return new PublicRegionClient();
    }
}
~~~

The two client classes are illustrative types. The difference is the scope of the condition: class-level vetoes the entire configuration; method-level only vetoes the corresponding bean definition.

## 8. Testing Determinism with ApplicationContextRunner

A custom condition needs to be tested with reproducible inputs. Spring Boot provides `ApplicationContextRunner` to create a small, isolated context for each scenario.

The tests below verify:

1. Exact region match.
2. Region differs from expected value.
3. Property is not provided.
4. The same input runs in two independent contexts and yields the same result.

### 8.1. Project Structure

~~~text
deterministic-condition-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/condition/
    │   │   ├── ConditionalOnRegion.java
    │   │   ├── RegionCondition.java
    │   │   ├── RegionFeature.java
    │   │   └── RegionAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/demo/condition/RegionConditionTests.java
~~~

### 8.2. File pom.xml

~~~xml
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
    <artifactId>deterministic-condition-demo</artifactId>
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
~~~

### 8.3. File src/test/java/demo/condition/RegionConditionTests.java

~~~java
package demo.condition;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class RegionConditionTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(RegionAutoConfiguration.class)
            );

    @Test
    void matchesWhenRegionIsInternal() {
        this.contextRunner
            .withPropertyValues("acme.region=internal")
            .run(context -> {
                assertThat(context).hasSingleBean(RegionFeature.class);
                assertThat(context.getBean(RegionFeature.class).region())
                    .isEqualTo("internal");
            });
    }

    @Test
    void doesNotMatchWhenRegionIsDifferent() {
        this.contextRunner
            .withPropertyValues("acme.region=public")
            .run(context ->
                assertThat(context).doesNotHaveBean(RegionFeature.class)
            );
    }

    @Test
    void doesNotMatchWhenRegionPropertyIsMissing() {
        this.contextRunner.run(context ->
            assertThat(context).doesNotHaveBean(RegionFeature.class)
        );
    }

    @Test
    void sameInputProducesSameResultAcrossIndependentContexts() {
        for (int attempt = 0; attempt < 2; attempt++) {
            this.contextRunner
                .withPropertyValues("acme.region=internal")
                .run(context -> {
                    assertThat(context).hasSingleBean(RegionFeature.class);
                    assertThat(context.getBean(RegionFeature.class).region())
                        .isEqualTo("internal");
                });
        }
    }
}
~~~

### 8.4. Running the Tests

Requirements: JDK 17+, Maven 3.8+, and ability to download dependencies. Inside the project directory, run:

~~~bash
mvn clean test
~~~

The four tests should produce these results:

| Test | Input | Result |
| --- | --- | --- |
| `matchesWhenRegionIsInternal` | `acme.region=internal` | Has one `RegionFeature` |
| `doesNotMatchWhenRegionIsDifferent` | `acme.region=public` | Does not have `RegionFeature` |
| `doesNotMatchWhenRegionPropertyIsMissing` | Property not set | Does not have `RegionFeature` |
| `sameInputProducesSameResultAcrossIndependentContexts` | Both contexts have `acme.region=internal` | Both contexts have one `RegionFeature` |

Maven Surefire reports four passing tests and `BUILD SUCCESS` if all assertions hold. Console format and execution time may vary by Maven/Surefire version; the table above describes the logical outcomes to verify.

### 8.5. Why Is ApplicationContextRunner a Good Fit?

- Each `run()` call creates a separate context for a single scenario.
- `withPropertyValues()` supplies explicit inputs to the `Environment`.
- `AutoConfigurations.of()` specifies the exact auto-configuration under test.
- The callback receives the refreshed context to inspect the actual beans.
- The context is closed after the callback, preventing state leaks between tests.

There is no need to modify OS environment variables or call external services to test a condition.

## 9. ConfigurationCondition: When Do You Need to Control the Phase?

A standard `Condition` fits most cases. If the condition depends on **when** evaluation occurs during configuration processing, Spring Framework provides a specialized interface `ConfigurationCondition`.

This interface lets you choose one of two phases:

| Phase | Timing |
| --- | --- |
| `PARSE_CONFIGURATION` | While Spring is parsing configuration and imports |
| `REGISTER_BEAN` | While Spring is registering bean definitions |

Skeleton implementation example:

~~~java
public final class ExistingDefinitionCondition
        implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        // Read bean-definition metadata only if truly needed.
        // Do not call getBean() and do not modify the registry.
        return true;
    }
}
~~~

This is an illustrative snippet; the actual check depends on the library's rules.

Use `REGISTER_BEAN` when the condition needs to evaluate during the bean registration phase, for instance checking whether a bean definition has already been registered. Even in this phase, the condition still must not interact with bean instances.

Do not use `ConfigurationCondition` just to implement an extra interface. For the example above that reads `Environment` and annotation metadata, a plain `Condition` is sufficient.

## 10. Diagnosing Conditions in Spring Boot

### 10.1. When You Need Explanatory MATCH/NO MATCH Messages

`Condition.matches()` returns a boolean, so the interface itself does not require returning a message. If you develop a custom condition specifically for Spring Boot and want diagnostic messages consistent with built-in conditions, you can extend `SpringBootCondition`.

This base class provides `getMatchOutcome(...)`, returning a `ConditionOutcome` along with logging information. You can create outcomes using `ConditionOutcome.match("...")` or `ConditionOutcome.noMatch("...")`.

Skeleton example:

~~~java
public final class RegionCondition extends SpringBootCondition {

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        // Compute from annotation metadata and Environment.
        // Do not create beans or call external services.

        boolean matched = /* pure comparison */ true;

        if (matched) {
            return ConditionOutcome.match(
                "acme.region matched the required region"
            );
        }

        return ConditionOutcome.noMatch(
            "acme.region did not match the required region"
        );
    }
}
~~~

This illustrates the API; in real code, replace the placeholder comparison with the pure logic from section 6. `SpringBootCondition` is responsible for recording the outcome through Boot's logging mechanism. Evaluation logic should still remain deterministic and have no side effects beyond the diagnostics provided by the base class.

If you do not need custom messages, using `Condition` from Spring Framework as in the main example is the simplest approach.

### 10.2. Condition Report

Spring Boot records condition outcomes in `ConditionEvaluationReport`. When you need to check why an auto-configuration was not applied:

- Run the application with `--debug` to enable the condition report.
- In tests, use `ConditionEvaluationReportLoggingListener` at INFO or DEBUG level.
- If you need the report over HTTP and the application has Actuator configured appropriately, inspect the `/actuator/conditions` endpoint.

The condition report helps answer which conditions matched or did not match. It does not replace assertions on actual beans in tests.

## 11. Common Mistakes and How to Fix Them

| Mistake / anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Calling `context.getBeanFactory().getBean(...)` in `matches()` | Instantiates beans prematurely, breaking lifecycle/post-processing | Read only metadata and Environment; let bean methods handle dependencies |
| Using `@Autowired` or `@Value` in a condition | The condition does not operate as a regular, fully managed bean | Use `ConditionContext` and `AnnotatedTypeMetadata` |
| Making HTTP/database calls to decide bean registration | Startup depends on network, timeouts, and external services | Move health checks or remote calls into a bean/service after context creation |
| Using `LocalDate.now()` or random values | The same configuration can produce different results across evaluations | Pass fixed inputs via Environment/metadata |
| Reading `System.getenv()` directly | Hard for tests to override and depends on the host machine | Use `Environment.getProperty()` |
| Writing a static flag to remember a previous run | Contexts/tests can affect each other | Keep conditions stateless; compute each time from current inputs |
| Modifying `BeanDefinitionRegistry` in `matches()` | The condition mutates the context currently being evaluated | Return a boolean; let Spring register bean definitions |
| Modifying Environment or property sources | Subsequent conditions may see altered inputs | Only read the Environment |
| Not handling missing properties | Can cause a NullPointerException | Clearly define whether missing means match or no-match; use null-safe comparisons |
| Using a custom Condition for a simple boolean property | Increases code and maintenance burden | Prefer `@ConditionalOnProperty` |
| Condition reads bean definitions in too early a phase | Required definitions are not visible yet | Consider `ConfigurationCondition` and the `REGISTER_BEAN` phase |
| Condition logic depends on the order of other conditions | Unpredictable results when configuration changes | Make each condition independent, returning a result solely from its own inputs |

## 12. Design and Review Workflow for a Custom Condition

Before shipping a condition in a library, follow these steps:

1. **Describe the rule in one sentence:** e.g., "only register the feature when the region in Environment matches the region on the annotation".
2. **List inputs:** which annotation attributes, which properties, which classes/resources.
3. **Define missing/default behavior:** if the property does not exist, does it match or not match? Is an empty string treated differently?
4. **Pick built-in APIs first:** if a standard condition already satisfies the need, do not write a custom one.
5. **Keep implementation pure:** no bean instances, I/O, network, clock, randomness, or registry/environment mutations.
6. **Choose the right phase:** use default `Condition`; use `ConfigurationCondition` only when phase control is genuinely needed.
7. **Write tests for every branch:** match, no-match, missing property, missing metadata, and same input across multiple contexts.
8. **Verify actual beans:** assert bean presence/absence in `ApplicationContextRunner`, not just calling `matches()` directly.
9. **Add appropriate diagnostics:** use `SpringBootCondition` if `ConditionOutcome` and logging are needed.
10. **Document for users:** property names, annotation values, defaults, comparison rules, and when beans are skipped.

## 13. Self-Check Questions

**Question 1.** At what stage is `Condition.matches()` called?  
**Answer:** Immediately before the corresponding component/bean definition is registered. It can allow or veto registration.

**Question 2.** Why must you not call `getBean()` inside a condition?  
**Answer:** The bean may be instantiated too early, before its normal lifecycle and post-processing; conditions must follow `BeanFactoryPostProcessor` restrictions and not interact with bean instances.

**Question 3.** What useful inputs does `ConditionContext` provide?  
**Answer:** `Environment`, `BeanDefinitionRegistry`, `BeanFactory` if available, `ResourceLoader`, and `ClassLoader`.

**Question 4.** What is `AnnotatedTypeMetadata.getAnnotationAttributes()` used for?  
**Answer:** Reading the attributes of an annotation on the class or method being evaluated, including composed/meta-annotations.

**Question 5.** With the same annotation, if `acme.region` changes from `internal` to `public`, what is the outcome in the example?  
**Answer:** `internal` matches; `public` does not match because the condition performs an exact comparison against the annotation value.

**Question 6.** Why should missing properties be tested?  
**Answer:** Because a missing property is a realistic input and needs clear semantics. This example fails closed: if the property is missing, the feature is not registered.

**Question 7.** When is `ConfigurationCondition` needed?  
**Answer:** When you need to choose the configuration-parsing phase (`PARSE_CONFIGURATION`) or bean-registration phase (`REGISTER_BEAN`), usually because the condition depends on bean-definition metadata.

**Question 8.** When should `SpringBootCondition` be used?  
**Answer:** When a Spring Boot condition needs to return a `ConditionOutcome` and provide consistent diagnostic logging. Evaluation logic must still remain deterministic and side-effect-free.

**Question 9.** If a condition only checks `acme.feature.enabled=true`, should you write a custom `Condition` class?  
**Answer:** Usually not. Using `@ConditionalOnProperty` is sufficient and leaves less code to maintain.

## 14. Takeaways and References

- `Condition` is an SPI that decides whether a component is eligible for registration; `matches()` receives `ConditionContext` and `AnnotatedTypeMetadata`.
- Conditions run before bean definitions are registered, so never interact with bean instances and never call `getBean()`.
- Good inputs come from annotation metadata, Environment, classpath, or deterministic resources.
- The same inputs must yield the same result; avoid current time, randomness, I/O, network, database, and mutable static state.
- Custom composed annotations use `@Conditional(YourCondition.class)` to attach a condition to a class or method.
- Use `ConfigurationCondition` when phase selection is needed; use `SpringBootCondition` when `ConditionOutcome` and diagnostic logging are needed.
- `ApplicationContextRunner` helps test each input in an isolated context; assertions on beans are the final proof of behavior.

Official documentation:

1. Spring Framework 6.1 — [Condition Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html): evaluation timing and restriction against interacting with bean instances.
2. Spring Framework 6.1 — [Conditional Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Conditional.html): usage scope on classes, methods, and meta-annotations.
3. Spring Framework 6.1 — [ConditionContext Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html): Environment, BeanFactory, registry, resource loader, and class loader.
4. Spring Framework 6.1 — [AnnotatedTypeMetadata Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotatedTypeMetadata.html): reading annotation attributes and meta-annotations.
5. Spring Framework 6.1 — [ConfigurationCondition Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html): `PARSE_CONFIGURATION` and `REGISTER_BEAN`.
6. Spring Boot 3.3.13 — [SpringBootCondition Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html): `ConditionOutcome` and diagnostic logging.
7. Spring Boot 3.3 — [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): custom auto-configuration, condition annotations, ApplicationContextRunner, and the condition report.
8. Spring Boot 3.3.13 — [ConditionEvaluationReport Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html).
