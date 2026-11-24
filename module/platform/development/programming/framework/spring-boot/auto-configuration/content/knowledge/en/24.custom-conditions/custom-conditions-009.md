# Choosing the Right ConfigurationPhase for the Data Observed

## 1. Why Does a Custom Condition Need to Choose the Right Phase?

Spring Framework lets you write custom conditions using the `Condition` interface. A condition decides whether a configuration class or bean definition is registered. When a condition cares about whether it is reading configuration or registering beans, checking data without considering timing can yield wrong results.

For example:

- Wanting to decide whether to include an entire `@Configuration` class in the context based on active profiles, properties, classpath, or resources: this data is already available from the environment, so it can be evaluated when parsing configurations.
- Wanting to register a `@Bean` only if another bean definition has already been registered: you must wait until the bean-registration stage. If you inspect the registry too early, the target bean definition might not exist yet.
- Wanting to read a value from a bean instance: **no phase is appropriate**. A condition must never retrieve or instantiate a bean instance to decide configuration.

`ConfigurationCondition` extends `Condition` and lets you specify one of two phases:

- `PARSE_CONFIGURATION`
- `REGISTER_BEAN`

This lesson uses **Java 17+, Spring Framework 6.1.x, and Spring Boot 3.3.x**. The focus is selecting the phase based on the kind of data observed, implementing conditions safely, controlling registration order, and testing both cases.

## 2. How Do the Two Phases Differ?

| Phase | Evaluation timing | Suitable data | Outcome if unmatched |
|---|---|---|---|
| `PARSE_CONFIGURATION` | While Spring is parsing a `@Configuration` class | Environment, profiles, properties, classpath, resources, and annotation metadata | The configuration class is excluded from processing |
| `REGISTER_BEAN` | When Spring registers a regular bean, e.g., a bean method | Bean definition registry and already-parsed configuration state | The bean under evaluation is not registered; the configuration class can still exist |

### 2.1. PARSE_CONFIGURATION: Deciding Whether to Include the Configuration Class

Spring is reading the metadata of a configuration class and determining whether it is eligible for further processing. If a condition in this phase returns `false`, that class is not added to the configuration model.

Suitable data:

- `Environment`: effective properties, active profiles, system properties, and environment variables.
- `ClassLoader`: whether optional classes are present.
- `ResourceLoader`: whether configuration resources exist.
- `AnnotatedTypeMetadata`: annotations and attributes on the class being inspected.

Do not inspect bean definitions assuming all other configurations have already been processed. At parse time, the registry is not yet a complete list of the bean definitions that will be created.

Good example: include a production-only configuration in the context only when `app.mode=production`.

### 2.2. REGISTER_BEAN: Deciding Whether to Register a Specific Bean

By this phase, `@Configuration` classes have already been parsed. Spring is registering bean definitions. This is the right time when a condition needs to see whether another bean definition is already in the registry.

Suitable data:

- `BeanDefinitionRegistry` via `ConditionContext.getRegistry()`.
- `ConfigurableListableBeanFactory` via `ConditionContext.getBeanFactory()` if available.
- Bean names, registered bean definitions, aliases, and related metadata.

`REGISTER_BEAN` does not mean every bean instance has been created. This is still the definition-registration stage; dependency injection and instance initialization happen later during refresh/lifecycle processing.

Good example: register `OptionalFeature` only when a bean definition named `acmePrerequisite` already exists.

### 2.3. Timing Diagram

~~~text
Read Environment / profiles / classpath
                 |
                 v
       PARSE_CONFIGURATION
                 |
          @Configuration
          class matches?
             /       \
           Yes        No
           |            |
           v            v
    Parse config      Skip class
           |
           v
  All configuration classes
       finished parsing
           |
           v
       REGISTER_BEAN
           |
    Evaluate condition
      on bean method
           |
        Matches?
        /     \
      Yes      No
      |          |
      v          v
Register bean  Skip bean
definition     definition
      |
      v
Later create bean instances
by dependency and lifecycle
~~~

This diagram is a conceptual model. Internal steps can be more intricate, but the key point to remember is that **the phase determines when the condition is evaluated, not the instantiation order of bean instances**.

## 3. What Data Do Condition APIs Provide?

### 3.1. Condition and ConfigurationCondition

`Condition` requires one method:

~~~java
boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
);
~~~

Return `true` if the component is allowed to register; return `false` to veto registration.

`ConfigurationCondition` adds:

~~~java
ConfigurationCondition.ConfigurationPhase getConfigurationPhase();
~~~

The return value tells Spring which phase should evaluate the condition. When explicit phase control is needed, implement `ConfigurationCondition` instead of only implementing `Condition`.

### 3.2. ConditionContext

`ConditionContext` provides the objects needed to evaluate a condition:

| Method | Return value | Use when |
|---|---|---|
| `getEnvironment()` | `Environment` | Reading properties, profiles, and effective configuration |
| `getRegistry()` | `BeanDefinitionRegistry` | Inspecting bean definition metadata |
| `getBeanFactory()` | `ConfigurableListableBeanFactory` or `null` | Querying factory metadata when the factory is available |
| `getResourceLoader()` | `ResourceLoader` | Checking resources using Spring's mechanism |
| `getClassLoader()` | `ClassLoader` or `null` | Checking the presence of optional classes |

`getBeanFactory()` can return `null` if the factory is unavailable or cannot be cast to the expected type. `getRegistry()` can throw `IllegalStateException` in certain contexts lacking a registry; during normal configuration processing, the registry is typically available.

### 3.3. AnnotatedTypeMetadata

`AnnotatedTypeMetadata` describes the element currently being inspected, which can be a class or a method. It allows reading annotation metadata without loading or instantiating the class or method itself.

Commonly used operations:

~~~java
metadata.isAnnotated("com.example.ConditionalFeature")
~~~

Checks whether a direct annotation or meta-annotation is present.

~~~java
metadata.getAnnotationAttributes(
        "com.example.ConditionalFeature"
);
~~~

Reads the annotation's attributes, such as configuration values declared on a custom annotation.

If the condition is placed on a configuration class, metadata describes the class. If placed on a `@Bean` method, metadata describes that method. Do not assume all metadata is class `AnnotationMetadata`; method metadata can be `MethodMetadata`.

## 4. Rules for Choosing a Phase Based on Observed Data

| Question the condition must answer | Suitable phase | Reason |
|---|---|---|
| Is the current profile production? | `PARSE_CONFIGURATION` | Read from Environment before parsing the class |
| Is property `app.feature.enabled` enabled? | `PARSE_CONFIGURATION` | Property is already in Environment |
| Is an optional SDK class on the classpath? | `PARSE_CONFIGURATION` | Classloader can check before loading configuration |
| Does a required resource exist? | `PARSE_CONFIGURATION` | ResourceLoader can check the resource |
| Has a specific bean definition already been registered? | `REGISTER_BEAN` | Must wait until the bean-registration stage |
| Does a bean definition have a specific attribute/role? | `REGISTER_BEAN` | Needs to read BeanDefinitionRegistry/BeanFactory |
| Has a bean instance been initialized and what is its runtime state? | **Do not use a condition** | Conditions must not interact with bean instances |

Guidelines:

- **Only static/environmental data needed:** prefer `PARSE_CONFIGURATION`.
- **Need to observe bean definitions:** choose `REGISTER_BEAN`.
- **Need data from a bean instance or service call:** move the logic to an appropriate runtime component, not inside a condition.

Do not pick `REGISTER_BEAN` thinking a later phase is somehow safer. The phase should reflect when the required data is ready.

## 5. Example 1: PARSE_CONFIGURATION Based on a Property

Suppose a configuration should only be loaded in a production environment. Create a condition that reads the `app.mode` property.

### 5.1. ProductionModeCondition

File `src/main/java/com/example/condition/ProductionModeCondition.java`:

~~~java
package com.example.condition;

import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class ProductionModeCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String mode = context.getEnvironment()
                .getProperty("app.mode", "");

        return "production".equalsIgnoreCase(mode);
    }
}
~~~

The condition chooses `PARSE_CONFIGURATION` because it only reads a property from Environment. It does not need to know which beans have been registered.

### 5.2. Configuration Using the Condition

File `src/main/java/com/example/condition/ProductionOnlyConfiguration.java`:

~~~java
package com.example.condition;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@Conditional(ProductionModeCondition.class)
public class ProductionOnlyConfiguration {

    @Bean
    ProductionMarker productionMarker() {
        return new ProductionMarker();
    }

    static class ProductionMarker {
    }
}
~~~

When `app.mode=production`, the configuration class is parsed and the `productionMarker` bean can be registered. When the property is missing or has another value, the configuration class is skipped.

### 5.3. Testing Both Cases

File `src/test/java/com/example/condition/ProductionModeConditionTests.java`:

~~~java
package com.example.condition;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ProductionModeConditionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            ProductionOnlyConfiguration.class
                    );

    @Test
    void includesConfigurationInProductionMode() {
        this.runner
                .withPropertyValues("app.mode=production")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(
                                    ProductionOnlyConfiguration
                                            .ProductionMarker.class
                            );
                });
    }

    @Test
    void skipsConfigurationOutsideProductionMode() {
        this.runner
                .withPropertyValues("app.mode=development")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(
                                    ProductionOnlyConfiguration
                                            .ProductionMarker.class
                            );
                });
    }
}
~~~

Expected results:

| Property | Configuration class | Bean |
|---|---|---|
| `app.mode=production` | Parsed | `ProductionMarker` present |
| `app.mode=development` | Skipped | No `ProductionMarker` |
| Property missing | Skipped | No `ProductionMarker` |

This is an example to illustrate phases. In a real application, if you only need profile activation, consider `@Profile`; if you only need a property toggle, prefer `@ConditionalOnProperty`. Write a custom condition only when the logic adds domain rules that built-in annotations do not express sufficiently.

## 6. Example 2: REGISTER_BEAN Based on a Bean Definition

Suppose a starter has two auto-configurations:

- `PrerequisiteAutoConfiguration` provides a bean definition named `acmePrerequisite`.
- `OptionalFeatureAutoConfiguration` registers `OptionalFeature` only if the prerequisite has already been registered.

The condition must inspect the **bean definition**, without calling `getBean()` to instantiate the prerequisite.

### 6.1. PrerequisiteBeanDefinitionCondition

File `src/main/java/com/example/condition/PrerequisiteBeanDefinitionCondition.java`:

~~~java
package com.example.condition;

import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class PrerequisiteBeanDefinitionCondition
        implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        return context.getRegistry()
                .containsBeanDefinition("acmePrerequisite");
    }
}
~~~

The condition chooses `REGISTER_BEAN` because the question it needs to answer is: has a bean definition named `acmePrerequisite` already been registered?

`containsBeanDefinition` only checks the definition in the registry. It does not instantiate the bean and does not prove the instance was created successfully. That is the exact kind of data a condition should observe.

### 6.2. Auto-Configuration Providing the Prerequisite

File `src/main/java/com/example/condition/PrerequisiteAutoConfiguration.java`:

~~~java
package com.example.condition;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class PrerequisiteAutoConfiguration {

    @Bean(name = "acmePrerequisite")
    Prerequisite prerequisite() {
        return new Prerequisite();
    }

    static class Prerequisite {
    }
}
~~~

### 6.3. Auto-Configuration Providing the Optional Feature

File `src/main/java/com/example/condition/OptionalFeatureAutoConfiguration.java`:

~~~java
package com.example.condition;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration(after = PrerequisiteAutoConfiguration.class)
public class OptionalFeatureAutoConfiguration {

    @Bean
    @Conditional(PrerequisiteBeanDefinitionCondition.class)
    OptionalFeature optionalFeature() {
        return new OptionalFeature();
    }

    static class OptionalFeature {
    }
}
~~~

`@AutoConfiguration(after = PrerequisiteAutoConfiguration.class)` declares auto-configuration processing order. When the feature is evaluated, the prerequisite auto-configuration has already been processed in the declared order, ensuring the checked bean definition is present in the registry.

Ordering here is ordering of auto-configuration/bean definitions. It **does not** require the prerequisite instance to be instantiated first. When the application actually retrieves beans, the dependency graph and lifecycle govern instance creation order.

### 6.4. Testing With and Without the Prerequisite

File `src/test/java/com/example/condition/PrerequisiteConditionTests.java`:

~~~java
package com.example.condition;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PrerequisiteConditionTests {

    private final ApplicationContextRunner withPrerequisite =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    OptionalFeatureAutoConfiguration.class,
                                    PrerequisiteAutoConfiguration.class
                            )
                    );

    @Test
    void registersFeatureWhenPrerequisiteDefinitionExists() {
        this.withPrerequisite.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(
                            OptionalFeatureAutoConfiguration
                                    .OptionalFeature.class
                    );
        });
    }

    @Test
    void skipsFeatureWhenPrerequisiteDefinitionIsAbsent() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                OptionalFeatureAutoConfiguration.class
                        )
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(
                                    OptionalFeatureAutoConfiguration
                                            .OptionalFeature.class
                            );
                });
    }
}
~~~

`AutoConfigurations.of(...)` accepts auto-configuration classes and applies ordering metadata such as `after`. The first test intentionally passes feature before prerequisite in the list to prove annotation ordering is honored. The second test includes only the feature in the context, so the condition does not find the prerequisite definition and does not register the feature.

Expected results:

| Loaded auto-configurations | Bean definition `acmePrerequisite` | Bean `OptionalFeature` |
|---|---|---|
| Prerequisite + OptionalFeature | Present | Present |
| Only OptionalFeature | Absent | Absent |

This test verifies the condition and ordering in an isolated context. It does not need to start a server or run the full application.

## 7. Why Must You Not Retrieve Bean Instances Inside a Condition?

`Condition` is evaluated during configuration processing, before all singleton beans are initialized. Spring requires conditions to follow the same restrictions as `BeanFactoryPostProcessor` and not interact with bean instances.

Do not do the following:

~~~java
@Override
public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata) {

    // Wrong: attempting to retrieve a bean instance while the condition is running.
    FeatureSettings settings =
            context.getBeanFactory().getBean(FeatureSettings.class);

    return settings.isEnabled();
}
~~~

Reasons:

- The bean may not be registered or initialized yet.
- Calling `getBean()` can trigger premature bean creation.
- The bean may depend on configuration or post-processing that is not yet complete.
- It can create a circular dependency between the condition and the bean it is deciding.
- The outcome depends on initialization order rather than early-checkable metadata/configuration.

If you need configuration values, read `Environment` or annotation metadata. If you need to know whether a bean was registered, read `BeanDefinitionRegistry` in `REGISTER_BEAN`. If you need to call a service or inspect runtime state, do it in a bean, application event listener, or business logic after the context has initialized.

## 8. Registration Order and Limits of REGISTER_BEAN

`REGISTER_BEAN` ensures configuration classes have been parsed, but it does not mean every bean definition from every configuration has been registered before your condition runs.

Therefore, if a condition depends on a specific auto-configuration:

1. Use `@AutoConfiguration(after = ...)` or `before` to declare appropriate ordering.
2. Check the exact bean name or bean type in the registry.
3. Avoid relying on accidental component-scan order or method declaration order.
4. Write tests both with and without the prerequisite.
5. Whenever possible, use Spring Boot's built-in conditions such as `@ConditionalOnBean` instead of writing a custom registry condition.

Do not use `@DependsOn` to solve this problem. `@DependsOn` controls bean instance initialization order, whereas a condition needs to determine whether a bean definition is registered. The two concepts belong to two different stages.

### 8.1. User Configuration and Auto-Configuration

Spring Boot typically processes user bean definitions before auto-configurations. Thus bean conditions in auto-configurations can yield to beans provided by the application.

However, a custom condition checking a specific bean name needs to clarify:

- Could the bean be declared under multiple names/aliases?
- Should bean definitions be checked by type instead of name?
- Does the parent context need to be considered?
- Should certain bean definitions be excluded?
- Is the auto-configuration supplying the prerequisite ordered before this one?

If you only need to check bean presence by type or name, `@ConditionalOnBean`/`@ConditionalOnMissingBean` are usually easier to read and require less code. Custom registry conditions are appropriate when domain rules are more complex or need to inspect definition metadata.

## 9. Which Data Is Safe to Observe in Each Phase?

| Data | PARSE_CONFIGURATION | REGISTER_BEAN | Notes |
|---|---|---|---|
| Environment property | Yes | Yes | Effective value prepared in Environment |
| Active profile | Yes | Yes | Use Environment |
| Classpath | Yes | Yes | Use ClassLoader; avoid loading optional classes via unguarded signatures |
| Resource | Yes | Yes | Use ResourceLoader |
| Annotation metadata | Yes | Yes | Metadata describing the class or method under evaluation |
| Bean definition registry | Accessible but incomplete | More suitable | Only rely on definitions already registered |
| BeanFactory metadata | May be incomplete | Can be useful | getBeanFactory() can return null |
| Bean instance | No | No | Conditions must not fetch or instantiate beans |
| Database/network/service response | No | No | Do not perform I/O or call services in conditions |

"Yes" in the table only means the API can be accessed; it does not mean the data is complete or sufficient to conclude everything in that phase. Choose the phase based on when the required data is truly ready.

## 10. Common Mistakes

- **Choosing PARSE_CONFIGURATION to check bean definitions:** the registry may not yet contain the bean the condition is looking for. Switch to REGISTER_BEAN if the rule genuinely depends on definitions.
- **Choosing REGISTER_BEAN for simple profile conditions:** no need to wait for the later phase; use PARSE_CONFIGURATION or built-in annotations like `@Profile`.
- **Thinking REGISTER_BEAN means bean instances already exist:** this phase concerns definition registration, not instance initialization.
- **Calling `getBean()` in `matches()`:** can create beans prematurely and cause dependency cycles.
- **Using `BeanFactoryPostProcessor` to fetch runtime data:** conditions and post-processors are not the place to call business services.
- **Assuming every bean definition is available during REGISTER_BEAN:** processing order still matters; declare auto-configuration ordering when needed.
- **Treating method order as a contract:** do not rely on one `@Bean` method accidentally being processed before another.
- **Not distinguishing class metadata from method metadata:** `AnnotatedTypeMetadata` can represent a configuration class or a bean method.
- **Using custom Condition for simple rules:** prefer `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnResource`, or `@Profile` when suitable.
- **Conditions with side effects:** do not write files, call APIs, connect to databases, mutate the registry, or log sensitive data inside `matches()`.
- **Returning results based on unstable data:** conditions should be fast, deterministic, and repeatable; do not depend on time, randomness, or fluctuating external state.
- **Not testing both sides:** include match and no-match tests to prove the chosen phase works properly.

## 11. Workflow for Choosing and Implementing a Phase

1. Write down the question the condition must answer, e.g., "is property app.mode production?" or "does bean definition acmePrerequisite exist?".
2. Identify the data to read: Environment, ClassLoader, ResourceLoader, annotation metadata, or bean registry.
3. Determine when that data becomes available. Environment/classpath/resources generally fit PARSE_CONFIGURATION; bean definitions require REGISTER_BEAN.
4. If standard logic suffices, look for built-in condition annotations before writing a new class.
5. Implement `ConfigurationCondition` and return the appropriate phase.
6. Inside `matches()`, read only context and metadata; do not fetch bean instances or perform I/O.
7. If depending on bean definitions from another auto-configuration, declare ordering explicitly.
8. Write match/no-match tests with `ApplicationContextRunner`.
9. Verify that the context starts and bean definitions appear or are skipped as expected.
10. When investigating, distinguish an unmatched condition from a bean-initialization failure: a condition returning false normally just skips a component and does not by itself fail the context.

## 12. Self-Check Questions

1. When is `PARSE_CONFIGURATION` evaluated? **When Spring parses a `@Configuration` class.**
2. What happens if a class-level condition does not match during PARSE_CONFIGURATION? **The configuration class is not added to processing.**
3. What is `REGISTER_BEAN` suitable for checking? **Whether a bean definition has already been registered in the registry, typically on a bean method condition.**
4. Does REGISTER_BEAN mean all bean instances have already been created? **No.** It is the bean-definition registration stage.
5. Which method on `ConditionContext` retrieves the Environment? **`getEnvironment()`.**
6. Which API checks a bean definition by name? **`context.getRegistry().containsBeanDefinition(name)`.**
7. Why must `getBean()` not be called inside `matches()`? **Conditions run before bean instances are initialized; fetching beans can trigger premature creation and cause dependency cycles.**
8. When auto-configuration B needs a bean definition from auto-configuration A, what must you do? **Declare ordering such as `@AutoConfiguration(after = A.class)` and test it.**
9. If you only check a boolean property, do you need a custom Condition? **Usually not.** Using `@ConditionalOnProperty` is more appropriate.
10. Which types of elements can `AnnotatedTypeMetadata` represent? **The configuration class or method currently being inspected.**
11. If you need to check a service's state after initialization, which phase should you choose? **Neither phase.** Move the check to a bean/event/runtime logic.
12. Does `@DependsOn` replace `@AutoConfiguration(after=...)` when a condition needs a bean definition? **No.** `@DependsOn` controls instance initialization; `after` controls auto-configuration/definition processing order.

## 13. Official References

- [Spring Framework 6.1 — ConfigurationCondition API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html): the getConfigurationPhase() contract and both phases.
- [Spring Framework 6.1 — ConfigurationPhase API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html): meaning of PARSE_CONFIGURATION and REGISTER_BEAN.
- [Spring Framework 6.1 — Condition API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html): matches(), registration conditions, and the restriction against interacting with bean instances.
- [Spring Framework 6.1 — ConditionContext API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html): Environment, BeanDefinitionRegistry, BeanFactory, ResourceLoader, and ClassLoader.
- [Spring Framework 6.1 — AnnotatedTypeMetadata API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotatedTypeMetadata.html): reading annotation metadata of classes and methods.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): auto-configuration conditions, bean conditions, and ordering.
- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): building isolated contexts to test conditions and bean registration.
