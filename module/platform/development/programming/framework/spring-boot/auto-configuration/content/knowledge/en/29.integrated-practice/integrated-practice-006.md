# Creating Two Auto-Configuration Classes with Before/After Ordering and Writing Proof Tests

## Lesson Objectives

When a Spring Boot library has multiple auto-configurations, one configuration may need to be processed before another. For example, a foundation configuration creates an infrastructure bean; a feature configuration registers a bean only if that infrastructure bean has already been declared.

Spring Boot provides several ways to declare ordering relationships:

- `@AutoConfiguration(before = ...)`
- `@AutoConfiguration(after = ...)`
- `beforeName` and `afterName` when referencing by fully qualified class name.
- Two dedicated annotations `@AutoConfigureBefore` and `@AutoConfigureAfter`.
- `@AutoConfigureOrder` when a general order is needed without creating a direct relationship between two classes.

This lab builds two auto-configuration classes, where `ZetaBaseAutoConfiguration` provides a foundation bean and `AlphaFeatureAutoConfiguration` must be processed after it. The class names are chosen intentionally: alphabetically, Alpha comes before Zeta. Tests will pass candidates into the runner in reverse order and prove that the `after` relationship still causes the dependent bean to be registered.

After this lesson, you can:

- Explain the purpose of ordering between auto-configurations.
- Distinguish `before`, `after`, `beforeName`, and `afterName`.
- Create two auto-configuration classes with an ordering dependency.
- Use `@ConditionalOnBean` to express that a configuration depends on a bean supplied by another configuration.
- Write tests using `ApplicationContextRunner` and `AutoConfigurations.of(...)`.
- Distinguish bean definition registration order from bean instance initialization order.
- Register classes in `AutoConfiguration.imports` and inspect the built artifact.

## 1. Problem: Feature Configuration Needs Foundation Configuration

Suppose the Acme library has two parts:

1. Foundation configuration creates `BaseMarker`, representing a ready foundation service or infrastructure.
2. Feature configuration creates `FeatureMarker`, but only if `BaseMarker` is already present in bean definitions.

Desired relationship:

~~~text
ZetaBaseAutoConfiguration
          |
          | registers BaseMarker
          v
AlphaFeatureAutoConfiguration
          |
          | @ConditionalOnBean(BaseMarker.class)
          v
FeatureMarker
~~~

If the feature configuration is processed first, the condition on its bean method may be evaluated before the `BaseMarker` bean definition is registered. In that case, `FeatureMarker` is not created.

We need to declare that the feature configuration must be applied after the foundation configuration. This is auto-configuration processing order, not a request to manually sort bean lists.

## 2. What Does Ordering Mean?

Spring Boot reads auto-configuration candidates and sorts them based on ordering metadata. Before/after relationships form an ordering dependency graph.

With two classes:

~~~java
@AutoConfiguration
class ZetaBaseAutoConfiguration {
}

@AutoConfiguration(after = ZetaBaseAutoConfiguration.class)
class AlphaFeatureAutoConfiguration {
}
~~~

This means `ZetaBaseAutoConfiguration` must be applied before `AlphaFeatureAutoConfiguration`.

The same relationship can be expressed from the opposite side:

~~~java
@AutoConfiguration(before = AlphaFeatureAutoConfiguration.class)
class ZetaBaseAutoConfiguration {
}
~~~

Both forms represent the same ordering edge. For a pair of configurations, pick one side to declare the relationship clearly; do not duplicate both `before` and `after` when they describe the exact same requirement.

### 2.1. Attributes on @AutoConfiguration

| Attribute | Meaning |
| --- | --- |
| `before` | The current class must be applied before the specified classes |
| `beforeName` | Same as `before`, but takes FQCNs as strings |
| `after` | The current class must be applied after the specified classes |
| `afterName` | Same as `after`, but takes FQCNs as strings |

Example:

~~~java
@AutoConfiguration(
        before = MetricsAutoConfiguration.class,
        after = FoundationAutoConfiguration.class)
public class AcmeFeatureAutoConfiguration {
}
~~~

Multiple classes can be declared in an attribute:

~~~java
@AutoConfiguration(
        after = {
                FoundationAutoConfiguration.class,
                ClientAutoConfiguration.class
        })
public class AcmeFeatureAutoConfiguration {
}
~~~

The current class is applied only after all listed auto-configurations.

### 2.2. When to use beforeName or afterName?

Use string-based attributes when you want to avoid creating a direct compile-time dependency to the referenced auto-configuration, such as when two modules are released independently or the dependency is optional.

~~~java
@AutoConfiguration(
        afterName = "com.vendor.foundation.FoundationAutoConfiguration")
public class AcmeVendorIntegrationAutoConfiguration {
}
~~~

The name must be the exact FQCN. If the package or class is renamed, review the corresponding ordering strings and migration metadata.

### 2.3. Dedicated annotations

`@AutoConfigureBefore` and `@AutoConfigureAfter` can be used instead of attributes on `@AutoConfiguration`:

~~~java
@AutoConfigureAfter(FoundationAutoConfiguration.class)
@AutoConfiguration
public class AcmeFeatureAutoConfiguration {
}
~~~

~~~java
@AutoConfigureBefore(AcmeFeatureAutoConfiguration.class)
@AutoConfiguration
public class FoundationAutoConfiguration {
}
~~~

These are equivalent in intent. For new code, using `before`/`after` attributes on `@AutoConfiguration` is usually more concise and readable.

### 2.4. What is @AutoConfigureOrder used for?

`@AutoConfigureOrder` provides a general order for auto-configurations, similar to `@Order`. Use it when you need a broad relative position without a specific class as a dependency.

If configuration B must be processed specifically after configuration A, `after = A.class` expresses the contract more clearly than an arbitrary order number. Do not use `@AutoConfigureOrder` as a casual substitute for a direct relationship.

## 3. Ordering Does Not Sort Creation Time of Every Bean Instance

This is the most important point when designing auto-configuration.

Ordering only affects the order in which **configurations are applied and bean definitions are registered**. It does not govern the subsequent instantiation order of all singleton beans.

For example, if `FeatureService` needs `BaseService`, express that dependency via constructor injection or `@Bean` method parameters:

~~~java
@Bean
FeatureService featureService(BaseService baseService) {
    return new FeatureService(baseService);
}
~~~

Spring creates the required dependencies following the bean dependency graph.

`@DependsOn` can express instantiation order between beans when specific lifecycle requirements exist, but it does not replace ordering between auto-configurations. In particular, `@DependsOn` does not make a bean definition appear earlier so that an earlier `@ConditionalOnBean` evaluation can see it.

In summary:

| Mechanism | Controls |
| --- | --- |
| `@AutoConfiguration(after = ...)` | Order of applying auto-configurations and registering bean definitions |
| Constructor injection / `@Bean` parameters | Dependency relationships when creating bean instances |
| `@DependsOn` | Bean instance initialization order when explicit ordering is required |
| `@ConditionalOnBean` | Whether to register a component based on already-processed bean definitions |

## 4. Why Does Order Matter for @ConditionalOnBean?

`@ConditionalOnBean` inspects bean definitions that have already been processed at the moment the condition is evaluated. It does not wait until all auto-configurations in the application are processed and then re-evaluate.

For example:

~~~java
@Bean
@ConditionalOnBean(BaseMarker.class)
FeatureMarker featureMarker(BaseMarker baseMarker) {
    return new FeatureMarker(baseMarker.value());
}
~~~

If the foundation configuration has been processed first, the `BaseMarker` bean definition is visible to the condition and `FeatureMarker` is registered.

If the foundation configuration has not been processed yet, the condition may fail to match. A `BaseMarker` appearing later does not cause Spring to revisit and register the skipped bean method.

Spring Boot recommends using `@ConditionalOnBean` and `@ConditionalOnMissingBean` in auto-configuration because auto-configuration is processed after user-defined bean definitions. When one auto-configuration depends on a bean supplied by another auto-configuration, declare the corresponding ordering.

## 5. Building a Complete Example

We use Java 17+, Spring Boot 3.3.x, Gradle, and JUnit 5. The example consists of two auto-configurations and two marker records.

### 5.1. Directory structure

~~~text
acme-autoconfigure/
  build.gradle
  src/
    main/
      java/
        com/acme/autoconfigure/
          OrderingTypes.java
          ZetaBaseAutoConfiguration.java
          AlphaFeatureAutoConfiguration.java
      resources/
        META-INF/spring/
          org.springframework.boot.autoconfigure.AutoConfiguration.imports
    test/
      java/
        com/acme/autoconfigure/
          AutoConfigurationOrderingTests.java
~~~

Both auto-configuration classes are top-level classes. They are registered via the imports file, not by component scanning.

### 5.2. Shared data types

**File:** `src/main/java/com/acme/autoconfigure/OrderingTypes.java`

~~~java
package com.acme.autoconfigure;

public final class OrderingTypes {

    private OrderingTypes() {
    }

    public record BaseMarker(String value) {
    }

    public record FeatureMarker(String baseValue) {
    }
}
~~~

The two records serve solely as markers so tests can verify bean registration and data passed via dependency injection.

### 5.3. Foundation auto-configuration

**File:** `src/main/java/com/acme/autoconfigure/ZetaBaseAutoConfiguration.java`

~~~java
package com.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ZetaBaseAutoConfiguration {

    @Bean
    public OrderingTypes.BaseMarker baseMarker() {
        return new OrderingTypes.BaseMarker("zeta-base");
    }
}
~~~

This class provides the `BaseMarker` bean. It does not need to know which feature configurations will use that bean.

Separating foundation configuration from feature configuration gives each class a clear responsibility.

### 5.4. Feature auto-configuration depending on foundation configuration

**File:** `src/main/java/com/acme/autoconfigure/AlphaFeatureAutoConfiguration.java`

~~~java
package com.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = ZetaBaseAutoConfiguration.class)
public class AlphaFeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(OrderingTypes.BaseMarker.class)
    public OrderingTypes.FeatureMarker featureMarker(
            OrderingTypes.BaseMarker baseMarker) {

        return new OrderingTypes.FeatureMarker(baseMarker.value());
    }
}
~~~

Two details to note:

1. `after = ZetaBaseAutoConfiguration.class` requires the foundation configuration to be applied before the feature configuration.
2. `@ConditionalOnBean(BaseMarker.class)` registers the feature bean only when the foundation bean is already in the processed bean definitions.

The `BaseMarker` parameter on the bean method also expresses the actual dependency. Once bean definitions are registered, Spring injects the foundation instance when creating `FeatureMarker`.

### 5.5. Registering both classes in the imports file

**File:** `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

~~~text
com.acme.autoconfigure.AlphaFeatureAutoConfiguration
com.acme.autoconfigure.ZetaBaseAutoConfiguration
~~~

The file intentionally lists Alpha before Zeta. Line order in the file is not an ordering contract. Spring Boot uses `before`/`after` metadata to sort candidates.

Do not register the same auto-configuration with component scan or with another duplicate import mechanism. Auto-configurations should be discovered via the imports file following Spring Boot convention.

## 6. Writing Tests Proving Before/After Ordering

Use `ApplicationContextRunner` to create a small context and load only the two auto-configurations under test.

Key points of the tests:

- Candidates are passed into `AutoConfigurations.of(...)` in Alpha then Zeta order.
- Class names also put Alpha before Zeta alphabetically.
- Metadata `after = ZetaBaseAutoConfiguration.class` instructs Boot to process Zeta before Alpha.
- Alpha creates `FeatureMarker` only when `BaseMarker` has already been registered.

**File:** `src/test/java/com/acme/autoconfigure/AutoConfigurationOrderingTests.java`

~~~java
package com.acme.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderingTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            AlphaFeatureAutoConfiguration.class,
                            ZetaBaseAutoConfiguration.class));

    @Test
    void baseConfigurationIsAppliedBeforeDependentFeature() {
        this.contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(OrderingTypes.BaseMarker.class);

            assertThat(context)
                    .hasSingleBean(OrderingTypes.FeatureMarker.class);

            assertThat(context.getBean(OrderingTypes.FeatureMarker.class)
                    .baseValue())
                    .isEqualTo("zeta-base");
        });
    }

    @Test
    void featureIsNotCreatedWhenBaseConfigurationIsAbsent() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        AlphaFeatureAutoConfiguration.class))
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(OrderingTypes.BaseMarker.class);

                    assertThat(context)
                            .doesNotHaveBean(OrderingTypes.FeatureMarker.class);
                });
    }
}
~~~

### 6.1. What does the first test prove?

The test loads the two candidates in order:

~~~java
AutoConfigurations.of(
        AlphaFeatureAutoConfiguration.class,
        ZetaBaseAutoConfiguration.class)
~~~

However, Alpha's configuration declares:

~~~java
@AutoConfiguration(after = ZetaBaseAutoConfiguration.class)
~~~

When the runner applies the auto-configurations, Spring Boot sorts them according to ordering metadata. Zeta is applied before Alpha even though the candidates were passed in reverse order.

When Alpha is processed:
- The `BaseMarker` bean definition has already been registered.
- `@ConditionalOnBean(BaseMarker.class)` matches.
- The `FeatureMarker` bean definition is registered.
- When the context creates the beans, the `BaseMarker` parameter is injected into the bean method.
- The value `zeta-base` is passed into `FeatureMarker`.

Assertions check both beans and the passed data, so the test proves the condition matched and dependency injection works.

### 6.2. What does the second test prove?

The second test loads only `AlphaFeatureAutoConfiguration`, without loading the foundation configuration.

Then:
- There is no `BaseMarker`.
- `@ConditionalOnBean(BaseMarker.class)` does not match.
- `FeatureMarker` is not registered.

This test proves the condition actually guards the feature bean; it is not created merely because the auto-configuration class was loaded.

### 6.3. Why not just assert that the annotation is present?

A reflection test such as:

~~~java
assertThat(AlphaFeatureAutoConfiguration.class)
        .hasAnnotation(AutoConfiguration.class);
~~~

only confirms the class has the annotation. It does not prove:
- Spring Boot read the ordering metadata.
- Candidates were sorted properly.
- Bean conditions were evaluated after the foundation configuration.
- Bean definitions were registered.
- Dependency injection produced the right result.

Using ApplicationContextRunner verifies the real behavior of auto-configuration inside a Spring container.

## 7. Running Tests with Gradle

Example configuration for a module using Spring Boot 3.3.x. Versions can be managed via the Spring Boot plugin or the project's BOM.

**File:** `build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run just the test class:

~~~bash
# Linux/macOS
./gradlew test --tests "com.acme.autoconfigure.AutoConfigurationOrderingTests"

# Windows
gradlew.bat test --tests "com.acme.autoconfigure.AutoConfigurationOrderingTests"
~~~

**Expected result:** both tests complete and pass:
- The foundation configuration is applied before the feature configuration even though candidates were passed in reverse order.
- The feature is not created when the foundation configuration is not loaded.

The tests print nothing to stdout. Gradle/JUnit reports pass/fail counts according to the project's logging configuration.

## 8. Variant Using `before` Instead of `after`

The main example places ordering on the dependent class:

~~~java
@AutoConfiguration(after = ZetaBaseAutoConfiguration.class)
public class AlphaFeatureAutoConfiguration {
}
~~~

You can place the same relationship on the foundation class:

~~~java
@AutoConfiguration(before = AlphaFeatureAutoConfiguration.class)
public class ZetaBaseAutoConfiguration {
}
~~~

Only one of the two declarations is needed to express the same relationship. If declaring both, make sure they are consistent and do not create an ordering cycle.

When the referenced class should not be a compile-time dependency, use names:

~~~java
@AutoConfiguration(
        beforeName = "com.acme.feature.AlphaFeatureAutoConfiguration")
public class ZetaBaseAutoConfiguration {
}
~~~

Or:

~~~java
@AutoConfiguration(
        afterName = "com.acme.foundation.ZetaBaseAutoConfiguration")
public class AlphaFeatureAutoConfiguration {
}
~~~

Using string names requires extra care because the compiler does not validate package/class names. Add tests or metadata checks to catch typos and renames.

## 9. Notes When Having Multiple Auto-Configurations

### 9.1. Ordering is a relative relationship

If A needs to come before B and B needs to come before C, declare the necessary edges:

~~~text
A -> B -> C
~~~

There is no need to assign separate order numbers to each class when direct relationships already describe the dependencies completely.

### 9.2. Avoiding cycles

Do not simultaneously declare:
- A before B.
- B before C.
- C before A.

These relationships form a cycle and cannot all be satisfied at once. Redesign responsibilities or extract the shared part into a foundation auto-configuration.

### 9.3. Do not rely on accidental order in the imports file

The list in `AutoConfiguration.imports` identifies candidates. Do not rely on line position to express required order. Explicitly declare `before`/`after` and test it.

### 9.4. Conditions only see already-processed bean definitions

`@ConditionalOnBean` and `@ConditionalOnMissingBean` do not wait for all configurations to finish processing. They rely on information available at evaluation time. That is why ordering matters when one auto-configuration depends on a bean supplied by another auto-configuration.

### 9.5. User configuration is normally processed before auto-configuration

One benefit of auto-configuration is that users can supply custom beans and let default beans back off:

~~~java
@Bean
@ConditionalOnMissingBean(BaseClient.class)
BaseClient baseClient() {
    return new DefaultBaseClient();
}
~~~

Spring Boot ensures auto-configurations are applied after user-defined bean definitions. Thus, missing-bean conditions in auto-configuration are an appropriate extension mechanism.

### 9.6. Ordering is not component scanning

Auto-configurations must be listed in the imports file. Do not use `@ComponentScan` to locate auto-configuration classes. For additional supporting configurations, use explicit `@Import` when needed.

## 10. Diagnosing When Tests Fail

If the first test lacks `FeatureMarker`, check:

1. Does `AlphaFeatureAutoConfiguration` declare `after = ZetaBaseAutoConfiguration.class`?
2. Were both classes actually passed into `AutoConfigurations.of(...)`?
3. Does `ZetaBaseAutoConfiguration` have a bean method returning the exact type `OrderingTypes.BaseMarker`?
4. Does the condition check that exact type?
5. Is the bean method excluded by another condition?
6. Is there an incompatible dependency version preventing the annotation/runner from working as expected?
7. Is the test using `AutoConfigurations.of` to apply candidates as auto-configurations?

You can enable the Condition Evaluation Report in the runner:

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .withConfiguration(AutoConfigurations.of(
                AlphaFeatureAutoConfiguration.class,
                ZetaBaseAutoConfiguration.class))
        .run(context -> {
            // Assertions.
        });
~~~

The report helps see whether `@ConditionalOnBean` matched and why. In real code, add imports for `ConditionEvaluationReportLoggingListener` and `LogLevel`:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

If the foundation bean does not appear, check the foundation class's conditions and bean definitions before investigating the dependent part.

## 11. Checking the Imports File in the JAR

ApplicationContextRunner with `AutoConfigurations.of(...)` tests ordering of directly supplied classes. It does not by itself prove the JAR packaged the imports file accurately.

After building:

~~~bash
jar tf build/libs/acme-autoconfigure-1.0.0.jar
~~~

Confirm the resource is present:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Read its content and confirm both FQCNs are present:

~~~text
com.acme.autoconfigure.AlphaFeatureAutoConfiguration
com.acme.autoconfigure.ZetaBaseAutoConfiguration
~~~

To test discovery from the imports file, add a smoke test running via `@EnableAutoConfiguration` in a sample application or artifact integration test. This is a different testing layer from unit-style runner tests:
- Runner tests verify behavior and ordering of loaded candidates.
- Smoke tests verify resource discovery in a real classpath/JAR.

## 12. Common Mistakes

1. **Relying on line order in the imports file.** Candidates can be reordered; declare before/after explicitly.
2. **Assuming the order passed to AutoConfigurations.of is an ordering contract.** Use ordering metadata to describe relationships.
3. **Using @Order on beans instead of @AutoConfiguration(after=...).** @Order does not express auto-configuration processing order.
4. **Using @DependsOn to fix a non-matching @ConditionalOnBean.** DependsOn governs bean initialization, not making a bean definition appear earlier during condition evaluation.
5. **Confusing ordering with dependency injection.** Ordering sorts configurations; constructor/bean method parameters express dependencies between instances.
6. **Placing @ConditionalOnBean on regular configurations processed too early.** Target bean definitions might not be processed yet; prefer placing bean conditions in auto-configurations.
7. **Missing a concrete return type on @Bean methods.** Conditions rely on available type information; declare sufficiently specific return types.
8. **Using class literals for optional dependencies inappropriately.** Consider beforeName/afterName if you want to avoid a compile-time dependency.
9. **Typo in FQCN inside beforeName/afterName.** Strings are not compiler-checked; add tests.
10. **Declaring conflicting bidirectional ordering.** Avoid cycles or contradictory edges.
11. **Using @AutoConfigureOrder for a direct dependency.** Use before/after to express relationships between two concrete classes.
12. **Checking annotations only via reflection.** Context tests are needed to prove real bean conditions and ordering.
13. **Using AutoConfigurations.of and concluding the imports file is right.** Check the JAR resource separately or smoke test via @EnableAutoConfiguration.
14. **Including auto-configurations in component scan.** Register candidates via the imports file per convention.
15. **Assuming ordering dictates singleton creation order.** Bean dependency graphs and lifecycle dictate instantiation order.

## 13. Two-Auto-Configuration Review Checklist

### Design

- [ ] Each auto-configuration has one clear responsibility.
- [ ] Foundation bean is declared in the foundation class.
- [ ] Dependent bean has the appropriate condition.
- [ ] Before/after relationship is declared clearly on one side.
- [ ] No ordering cycles are created.
- [ ] Bean methods have sufficiently specific return and parameter types.

### Registration

- [ ] Both classes have `@AutoConfiguration`.
- [ ] Both FQCNs are listed in the imports file.
- [ ] Not relying on line order in the resource.
- [ ] Not using component scan to discover auto-configurations.

### Testing

- [ ] Runner loads both candidates.
- [ ] Candidates are passed in reverse order to avoid relying on input order.
- [ ] Test confirms the foundation bean appears.
- [ ] Test confirms the dependent bean appears when ordering is right.
- [ ] Test confirms the dependent bean is absent when the foundation bean is missing.
- [ ] Test checks injected dependency data.
- [ ] JAR contains the correct imports file.
- [ ] Discovery smoke test present if end-to-end artifact verification is needed.

## 14. Self-Check Questions

**Question 1.** What does `@AutoConfiguration(after = BaseAutoConfiguration.class)` mean?

**Answer:** The current auto-configuration must be applied after BaseAutoConfiguration; the foundation configuration's bean definitions are processed before the current configuration.

**Question 2.** Can `before` and `after` express the same relationship?

**Answer:** Yes. A before B is equivalent to B after A. Pick one side to declare clearly and avoid redundant or conflicting relationships.

**Question 3.** Why can `@ConditionalOnBean` depend on auto-configuration order?

**Answer:** Conditions are evaluated against bean definitions processed up to that point. If the sought bean has not been registered yet, the condition may fail to match.

**Question 4.** Does ordering determine the creation order of every bean instance?

**Answer:** No. It affects the order of applying configurations and registering bean definitions. Dependency injection and lifecycle relationships determine instance creation order.

**Question 5.** When you do not want a compile-time dependency to the referenced class, which attributes do you use?

**Answer:** `beforeName` or `afterName`, with string FQCNs.

**Question 6.** Why does the test pass Alpha before Zeta yet still expect Zeta to be processed first?

**Answer:** Because the `after = ZetaBaseAutoConfiguration.class` metadata instructs Boot to sort Zeta before Alpha. The candidate declaration order in the test is not an ordering contract.

**Question 7.** Does a test using AutoConfigurations.of prove the imports file is in the JAR?

**Answer:** No. The runner loads classes directly. You must inspect the JAR resource or run a smoke test via `@EnableAutoConfiguration`.

## 15. Key Takeaways

When an auto-configuration depends on a bean supplied by another auto-configuration, describe the before/after relationship with `before` or `after`. Spring Boot uses ordering metadata to sort configuration application and bean definition registration. This is especially important for `@ConditionalOnBean` and `@ConditionalOnMissingBean`, because they inspect only bean definitions processed so far.

This lab uses `ZetaBaseAutoConfiguration` providing `BaseMarker`, while `AlphaFeatureAutoConfiguration` declares `after = ZetaBaseAutoConfiguration.class` and creates `FeatureMarker` only when the foundation bean exists. The test passes candidates in reverse order, then asserts both beans and the injected value. A separate test verifies the feature does not appear when the foundation configuration is absent.

Always distinguish bean definition registration order from bean instance initialization order. Use dependency injection to express bean usage relationships, use ordering to sort auto-configurations, and inspect the imports file in the artifact to ensure classes are actually discovered by Spring Boot.

### Official Spring Boot 3.3 Documentation

- [Creating Your Own Auto-configuration — Ordering and Testing](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [@AutoConfiguration Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [@AutoConfigureBefore Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html)
- [@AutoConfigureAfter Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html)
- [ApplicationContextRunner Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [AutoConfigurations Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html)
