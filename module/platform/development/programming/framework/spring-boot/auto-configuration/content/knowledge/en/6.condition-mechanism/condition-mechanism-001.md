# @Conditional and the Condition.matches Contract in Spring

## 1. Why Does Spring Need Conditional Bean Registration?

An application often has to change its configuration depending on the environment. For example: only registering a notification sender if a feature is enabled, only creating a default bean when the user has not defined their own bean, or only loading a configuration class when the corresponding library is present. Spring makes these decisions through **conditions at configuration processing time**.

The two core components of Spring Framework are:

- `@Conditional` (`org.springframework.context.annotation.Conditional`): an annotation attached to a configuration class, component class, or `@Bean` method to declare the condition that must be satisfied.
- `Condition` (`org.springframework.context.annotation.Condition`): an interface with a single method `matches(ConditionContext, AnnotatedTypeMetadata)` returning `boolean`.

**The most important contract:** a component is only *eligible to be registered* when every `Condition` applied to it returns `true`. A single condition returning `false` vetoes the registration of that component.

~~~text
Spring parses configuration metadata
            |
            v
Sees @Conditional(MyCondition.class)
            |
            v
Instantiates and calls MyCondition.matches(context, metadata)
            |
       +----+----+
       |         |
      true      false
       |         |
       v         v
Continue evaluating  Skip component
BeanDefinition       registration
       |
       v
Spring may create bean per scope/lifecycle
~~~

This is a **bean definition registration gate**, not an `if` statement executed every time a business method is called. Returning `true` also does not guarantee a bean instance already exists immediately: after the condition passes, the bean still depends on a valid definition, dependencies, scope, lazy initialization, and the context startup process.

### Connection to Spring Boot Auto-Configuration

Spring Boot builds familiar annotations such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean` on top of Spring's condition mechanism. Because of this, an `@AutoConfiguration` class can be a **candidate** yet only register certain beans when the actual conditions match.

Do not conflate three distinct steps:

1. **Candidate discovery:** Boot finds auto-configuration classes from `AutoConfiguration.imports`.
2. **Condition evaluation:** `@Conditional` or Boot conditions decide whether the class/method is processed.
3. **Bean creation and usage:** the container registers the `BeanDefinition`, resolves dependencies, and creates instances according to scope/lifecycle.

This lesson dives into **step 2**, specifically the `Condition.matches` contract; the Spring Boot example is only an environment for observing the Spring Framework mechanism.

## 2. `@Conditional` Syntax and AND Semantics

Common form:

~~~java
@Conditional(MyCondition.class)
class MyConfiguration {
}
~~~

You can also declare multiple conditions at the same time:

~~~java
@Conditional({ConditionA.class, ConditionB.class})
class MyConfiguration {
}
~~~

When two conditions apply together, both must match: `A && B`. This is **logical AND**, not OR.

| `ConditionA.matches` | `ConditionB.matches` | Component allowed to register? |
| --- | --- | --- |
| `true` | `true` | Yes, proceed to evaluate other constraints |
| `true` | `false` | No |
| `false` | `true` | No |
| `false` | `false` | No |

If you want OR, you must design a composite condition that returns `true` when one of the criteria matches, or split the appropriate beans/configurations. You cannot put two condition classes inside the same `@Conditional` and assume they are joined by OR.

At the API level, `@Conditional` has a value of type `Class<? extends Condition>[]`. Spring may order condition evaluation using `Ordered` or `@Order`; **do not write conditions assuming they will run exactly once or in source order**. The result must be computed from appropriate state, not based on side effects of another condition.

### Where to Place `@Conditional`?

According to the Spring Framework contract, the annotation is used on:

- **Configuration classes (`@Configuration`)**: the condition applies to the entire configuration. `@Bean`, `@Import`, and `@ComponentScan` declarations attached to that configuration class are also governed by this result.
- **Component classes (`@Component`, `@Service`, etc., or corresponding stereotypes)**: the class is only eligible to be registered as a component if the condition passes.
- **`@Bean` methods**: the condition only targets the bean definition of that method; it does not automatically exclude other methods in the same class.
- **Meta-annotations**: define a domain-specific annotation containing `@Conditional` inside it for reuse and passing parameters when needed.

Class-level and method-level conditions have **different scopes** of effect. This is a common cause of situations where "one bean is missing while other beans still appear".

### No Inheritance Mechanism for `@Conditional`

`@Conditional` **is not marked with `@Inherited`**, and the Spring Framework documentation explicitly states that conditions from a superclass or overridden method are not automatically evaluated as conditions of the new component. When creating a composed annotation with `@Conditional`, **do not mark that composed annotation with `@Inherited`**; if a condition is needed, declare it explicitly on the target class or method.

## 3. The `Condition` Interface and the `matches` Signature

Important Java contract:

~~~java
package org.springframework.context.annotation;

import org.springframework.core.type.AnnotatedTypeMetadata;

@FunctionalInterface
public interface Condition {
    boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    );
}
~~~

*This is an excerpt of the contract structure for study, not a Spring Framework file you need to define yourself.*

A simple custom condition:

~~~java
package example.feature;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class FeatureEnabledCondition implements Condition {

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        String value = context.getEnvironment()
            .getProperty("example.feature.enabled", "true");
        return "true".equalsIgnoreCase(value);
    }
}
~~~

In this example:

- Property not declared: uses the default value `"true"`, condition returns `true`.
- `example.feature.enabled=true` or `TRUE`: returns `true`.
- `example.feature.enabled=false`: returns `false`.
- Any other value such as `yes` or `invalid`: returns `false` because of case-insensitive exact string comparison.

This is an intentional choice of this **specific custom condition**, not a general rule of `@Conditional`. The example does not read `metadata` because this condition only needs `Environment`; the `metadata` parameter is still a required part of the contract.

### What Does `true` Actually Mean?

A return value of `true` means **the condition does not veto** the registration of the component. If there are other conditions, they must still match; the bean could still hit dependency errors when created, or remain uninitialized due to `@Lazy`/scope.

### What Does `false` Actually Mean?

A return value of `false` tells Spring to **skip registering** the corresponding component. It does not delete an already running bean instance when a property changes, nor does it automatically execute "feature off" logic on an already created object.

In a typical application startup, conditions are evaluated while the container is processing configuration/registering definitions. Changing a property after the context has refreshed **does not automatically re-evaluate** all `@Conditional` annotations. If you need configuration that changes continuously at runtime, design a different mechanism rather than expecting `matches` to be called every time a business method runs.

## 4. What Does `ConditionContext` Provide?

`ConditionContext` is the context Spring supplies to a condition during evaluation. Main methods:

| Method | Purpose | Notes |
| --- | --- | --- |
| `getEnvironment()` | Read properties and profiles | Suitable for feature flags and environment configuration |
| `getRegistry()` | Inspect `BeanDefinitionRegistry` | Can view definitions already registered at that point in time |
| `getBeanFactory()` | Access `ConfigurableListableBeanFactory` | May be `null` in certain situations |
| `getClassLoader()` | ClassLoader for class lookup | Be careful of class-loading side effects/cost |
| `getResourceLoader()` | Look up resources on classpath or supported locations | Distinguish resource existence from a registered bean |

Example checking the environment:

~~~java
@Override
public boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
) {
    return context.getEnvironment()
        .acceptsProfiles(org.springframework.core.env.Profiles.of("prod"));
}
~~~

*This is an illustrative method body that needs to be placed inside a class `implements Condition` with corresponding imports.* When only checking an active profile, `@Profile("prod")` is usually simpler than writing a custom condition.

### Strictly Forbidden: Creating or Fetching Bean Instances Inside a Condition

The `Condition` documentation specifies that conditions must follow restrictions similar to `BeanFactoryPostProcessor`: **never interact with bean instances**. Do not do the following:

~~~java
// Wrong design approach: creating/fetching a bean instance while deciding registration.
Object service = context.getBeanFactory().getBean("myService");
return service != null;
~~~

This snippet is an **anti-pattern**, not code to use. Reading a bean instance can trigger premature initialization, run into circular dependencies, cause side effects, and also risks `getBeanFactory()` not being available.

If you genuinely need a condition based on definitions, use the appropriate **metadata/definition** inspection API and understand the evaluation timing. With Spring Boot, `@ConditionalOnBean`/`@ConditionalOnMissingBean` are usually more suitable than building a custom condition. These two Boot annotations also have constraints regarding **definition processing order**; do not assume all final bean definitions are already present at the moment the condition is checked.

### Conditions Must Be Simple and Repeatably Evaluable

Good:

- Reading stable properties from `Environment`.
- Checking classes/resources via appropriate APIs without instantiating business components.
- Reading annotation metadata on the element being evaluated.
- Returning a deterministic result for the same input state.

Should not:

- Call HTTP APIs, databases, or unstable external systems during startup.
- Write files, send messages, or mutate the registry as a "consequence" of `matches`.
- Rely on invocation counters, thread timing, or execution order.
- Fetch bean instances from the context to determine the result.
- Swallow all exceptions and pretend a configuration error is `false` if that hides a serious issue.

A condition is a tool for deciding **registration eligibility**, not an automated lifecycle for services.

## 5. What Is `AnnotatedTypeMetadata` the Metadata Of?

The second parameter of `matches` is `org.springframework.core.type.AnnotatedTypeMetadata`. It describes the annotations on **the class or method currently being evaluated by Spring**, allowing metadata to be read without needing to instantiate that type.

- When the condition is on a class: the metadata may be an `AnnotationMetadata`, providing class information.
- When the condition is on a `@Bean` method: the metadata may be a `MethodMetadata`, providing method information.
- The common API allows looking up annotations via `isAnnotated(...)`, `getAnnotationAttributes(...)`, and related methods.
- Do not confuse metadata of the component being evaluated with the **list of bean instances** in the container.

Example reading the element name (illustrative, not a standalone program):

~~~java
import org.springframework.core.type.AnnotationMetadata;
import org.springframework.core.type.MethodMetadata;

// metadata is the parameter Spring passes into matches(...)
String target;
if (metadata instanceof MethodMetadata method) {
    target = "method:" + method.getMethodName();
} else if (metadata instanceof AnnotationMetadata type) {
    target = "class:" + type.getClassName();
} else {
    target = "other";
}
~~~

This is a way to **inspect the metadata type** when debugging or writing a parameterized condition; it should not be used to print logs with side effects on every `matches` call.

## 6. Complete Example: Console Spring Boot App Without a Web Server

The example uses **Java 17+, Maven 3.9+, and Spring Boot 3.3.13**. We create a custom `Condition` that decides whether to register a `MessageService` bean based on the `lab.feature.enabled` property.

**Expected output:**

- Default or `true`: the `featureService` bean exists and returns `enabled`.
- `false` or a value other than `true`: the bean is not registered; optional lookup returns `null`.
- Regardless of the condition result: the application runs with `WebApplicationType.NONE`, without starting an embedded web server.

### 6.1. Directory Tree

~~~text
conditional-contract-demo/
├── pom.xml
└── src/main/java/lab/
    ├── app/
    │   └── ConditionDemoApplication.java
    ├── api/
    │   └── MessageService.java
    └── feature/
        ├── FeatureEnabledCondition.java
        └── FeatureConfiguration.java
~~~

Place the main class in `lab.app` and the configuration class in `lab.feature` (outside the app's scan scope), then use `@Import` to load the configuration explicitly. This lets you clearly observe **the effect of `@Conditional`**, without confusing it with a situation where the configuration class was never loaded by Spring.

### 6.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>lab</groupId>
    <artifactId>conditional-contract-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter` provides the Spring Framework context and Boot auto-configuration without requiring an HTTP server. There is no need to add a web dependency to learn conditions.

### 6.3. `src/main/java/lab/api/MessageService.java`

~~~java
package lab.api;

public interface MessageService {
    String message();
}
~~~

This interface does not carry `@Component`, so it is not automatically registered as a bean. A `@Bean` method in the configuration will create the concrete instance.

### 6.4. `src/main/java/lab/feature/FeatureEnabledCondition.java`

~~~java
package lab.feature;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class FeatureEnabledCondition implements Condition {

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        String configured = context.getEnvironment()
            .getProperty("lab.feature.enabled", "true");
        return "true".equalsIgnoreCase(configured);
    }
}
~~~

Key points to master:

1. `implements Condition` tells Spring this is a condition usable by `@Conditional`.
2. `@Override matches(...)` takes the exact two parameters Spring Framework passes in.
3. `ConditionContext` provides the environment for reading the property.
4. `metadata` is unused in this case because there are no custom annotation parameters; it must still be declared in the method signature.
5. Returning `boolean` **only decides bean registration**; it does not create objects itself or invoke business logic.

### 6.5. `src/main/java/lab/feature/FeatureConfiguration.java`

~~~java
package lab.feature;

import lab.api.MessageService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @Conditional(FeatureEnabledCondition.class)
    public MessageService featureService() {
        return () -> "enabled";
    }
}
~~~

`@Conditional` at the **method level** only controls the `featureService` bean. Spring can still process the `FeatureConfiguration` class when the method's condition returns `false`.

`@Configuration(proxyBeanMethods = false)` is a sensible choice in this example because the factory methods do not call each other. This attribute **does not change the semantics of `Condition.matches`**.

### 6.6. `src/main/java/lab/app/ConditionDemoApplication.java`

~~~java
package lab.app;

import lab.api.MessageService;
import lab.feature.FeatureConfiguration;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = "lab.app")
@Import(FeatureConfiguration.class)
public class ConditionDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 new SpringApplicationBuilder(
                     ConditionDemoApplication.class)
                     .web(WebApplicationType.NONE)
                     .bannerMode(Banner.Mode.OFF)
                     .run(args)) {

            MessageService service =
                context.getBeanProvider(MessageService.class)
                    .getIfAvailable();

            System.out.println("webServer=" +
                (context instanceof WebServerApplicationContext));
            System.out.println("featureBean=" +
                context.containsBean("featureService"));
            System.out.println("message=" +
                (service == null ? "none" : service.message()));
        }
    }
}
~~~

The application uses `@Import(FeatureConfiguration.class)` to ensure the configuration class is processed, even though package `lab.feature` is outside `lab.app` and is not included by default component scanning. The absence of the bean when property=false can therefore be attributed to the condition, not to "the configuration was not found".

`getBeanProvider(...).getIfAvailable()` does not throw an exception when the bean is missing. In this example there is at most one `MessageService` bean per run, because only one factory method provides that type.

### 6.7. Build and Run

From the directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q clean package
java -jar target/conditional-contract-demo-1.0.0.jar
~~~

Three lines **printed by the program itself** (Spring Boot logs may appear in addition):

~~~text
webServer=false
featureBean=true
message=enabled
~~~

When the property is omitted, the custom condition uses the default `"true"` and allows the bean to be registered.

Run with the property disabled:

~~~bash
java -jar target/conditional-contract-demo-1.0.0.jar --lab.feature.enabled=false
~~~

Output:

~~~text
webServer=false
featureBean=false
message=none
~~~

Run with an explicit true value:

~~~bash
java -jar target/conditional-contract-demo-1.0.0.jar --lab.feature.enabled=true
~~~

Output:

~~~text
webServer=false
featureBean=true
message=enabled
~~~

Run with a value other than true:

~~~bash
java -jar target/conditional-contract-demo-1.0.0.jar --lab.feature.enabled=other
~~~

The result is the same as the `false` case, because the logic of `FeatureEnabledCondition` only accepts the string `true`, not because `@Conditional` inherently has such a rule for interpreting properties.

### Comparison Table

| `lab.feature.enabled` | `matches` | `featureService` bean | `message` |
| --- | --- | --- | --- |
| Property omitted | `true` | Present | `enabled` |
| `true` | `true` | Present | `enabled` |
| `TRUE` | `true` | Present | `enabled` |
| `false` | `false` | Absent | `none` |
| `other` | `false` | Absent | `none` |

**Distinguishing the symptom:** `featureBean=false` means the bean is not in the context after startup. In this configuration, the explanation is that `@Conditional` on the method vetoed that `BeanDefinition`; it is not that the bean exists and simply returns an empty business result.

## 7. Moving the Condition from Method to Class: What Changes?

In the main example, the condition is placed only on the `featureService()` method. Try **moving** the annotation up to `FeatureConfiguration`:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(FeatureEnabledCondition.class)
public class FeatureConfiguration {

    @Bean
    public MessageService featureService() {
        return () -> "enabled";
    }
}
~~~

*This is a replacement for the `FeatureConfiguration` class body, keeping the corresponding package/imports; it is not a standalone Java file if you omit the imports from section 6.5.*

In the current demo, the three lines of output remain identical for each property value because the class has only one `@Bean`. However, the semantics have changed:

- `@Conditional` **on a method**: the configuration class is processed; only the individual bean method is gated by the condition.
- `@Conditional` **on a class**: when the condition returns `false`, the entire configuration is skipped, including `@Bean`, `@Import`, and `@ComponentScan` attached to that class.

Suppose you add another `@Bean` method providing an unrelated `Clock` type. With a method-level condition, `Clock` is still registered when the `MessageService` bean is skipped. With a class-level condition, both bean methods are blocked when the class condition fails. Therefore, place conditions at the smallest scope that fits the requirement.

### Note the Difference in Evaluation Timing

Spring has multiple phases when processing configuration classes, such as parsing configurations and registering bean definitions. The result of a class-level condition can affect parsing `@Import`/`@ComponentScan` inside it, whereas a condition on a `@Bean` method applies at the bean method registration step.

That is why you should not arbitrarily write a condition based on "bean X already exists" and apply it everywhere. At an early phase, expected bean definitions may not have been processed yet. If you need explicit phase control, learn about `ConfigurationCondition` in section 10.

## 8. Combining Multiple Conditions Properly

Suppose a bean should only be registered if:

- The feature flag is enabled.
- The system is running a suitable profile.

Define an additional profile-based condition:

~~~java
package lab.feature;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.env.Profiles;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class ProductionCondition implements Condition {
    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment()
            .acceptsProfiles(Profiles.of("prod"));
    }
}
~~~

Replace the annotation on the method in `FeatureConfiguration`:

~~~java
@Bean
@Conditional({
    FeatureEnabledCondition.class,
    ProductionCondition.class
})
public MessageService featureService() {
    return () -> "enabled";
}
~~~

**The two snippets above are extensions to the project in section 6**; place the `ProductionCondition` class in `src/main/java/lab/feature/ProductionCondition.java` and update the `featureService` method, rather than adding a second method with the same name.

Now both the matching feature flag **and** the `prod` profile must be present at the same time. You can run:

~~~bash
java -jar target/conditional-contract-demo-1.0.0.jar --spring.profiles.active=prod
java -jar target/conditional-contract-demo-1.0.0.jar --spring.profiles.active=prod --lab.feature.enabled=false
~~~

In the first command, if you rebuilt after changing the code, the bean is registered. In the second command, the bean is blocked because feature flag=false even though the profile matches. If you forget to rebuild, the old JAR still contains the single-condition version.

However, when only a profile is needed, `@Profile("prod")` is usually more direct and easier to maintain; there is no need to define `ProductionCondition` yourself.

### Multiple Conditions Are AND, but Do Not Rely on Order

Spring can use `Ordered`/`@Order` to sort condition evaluation. That **does not grant permission** for condition A to write state that condition B reads, or for single execution to become a business assumption. Conditions should be independent, stable checks with no side effects.

## 9. Using Metadata to Build a Custom Conditional Annotation

Why does `matches` also receive `AnnotatedTypeMetadata`, when the main example only reads `Environment`? The reason is that a general-purpose condition can **read parameters from the annotation** attached to the class or method.

For example, suppose we want to write:

~~~java
@EnabledWhenProperty("lab.feature.enabled")
@Bean
MessageService featureService() {
    return () -> "enabled";
}
~~~

Define the custom annotation:

### `src/main/java/lab/feature/EnabledWhenProperty.java`

~~~java
package lab.feature;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Conditional(PropertyEnabledCondition.class)
public @interface EnabledWhenProperty {
    String value();
}
~~~

### `src/main/java/lab/feature/PropertyEnabledCondition.java`

~~~java
package lab.feature;

import java.util.Map;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class PropertyEnabledCondition implements Condition {

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        Map<String, Object> attrs =
            metadata.getAnnotationAttributes(
                EnabledWhenProperty.class.getName()
            );

        if (attrs == null) {
            return false;
        }

        String propertyName = (String) attrs.get("value");
        String actual = context.getEnvironment()
            .getProperty(propertyName, "false");

        return "true".equalsIgnoreCase(actual);
    }
}
~~~

This is an **alternative/extension approach**; you should not simultaneously keep `@Conditional(FeatureEnabledCondition.class)` and add `@EnabledWhenProperty` on the same method if the goal is to compare the effect of each individually. If both are applied, they combine with AND, and the default values of the two conditions in these examples differ.

### Exact Explanation of Both Parameters' Roles

- `context` supplies the runtime environment data to read the **property value**.
- `metadata` allows reading the `@EnabledWhenProperty` annotation to determine the **property name to check**.
- `metadata.getAnnotationAttributes(...)` can return `null` if the annotation is not present; the code explicitly handles this case.
- `getProperty(propertyName, "false")` defaults to not registering when the property is missing. This differs from the main `FeatureEnabledCondition` in section 6, which defaults to `true`.

You do not need reflection to instantiate the class under check or invoke the bean method. Spring provides sufficient metadata for the example.

**Do not attach `@Inherited` to `@EnabledWhenProperty`.** Spring conditions do not support annotation inheritance as a general registration rule.

### When Should You Use a Meta-Annotation?

When multiple modules need to express the same condition with an easy-to-understand name, or need to accept specific annotation parameters. However, if you only want a property-based condition in Spring Boot, prefer `@ConditionalOnProperty` to reduce custom code and leverage Boot's existing rules.

## 10. `ConfigurationCondition` and the Two Processing Phases

Plain `Condition` suffices for environment, classpath/resource, and metadata checks. When a condition must depend on the **phase** of configuration class processing, Spring provides the `ConfigurationCondition` extension interface.

It adds one method:

~~~java
ConfigurationPhase getConfigurationPhase();
~~~

Two values you usually need to understand:

- `PARSE_CONFIGURATION`: the configuration parsing phase, which decides whether to parse `@Import`, `@ComponentScan`, and `@Bean` declarations associated with the class.
- `REGISTER_BEAN`: the phase of registering bean definitions from already parsed configurations, suitable for conditions that need to rely on definitions already registered under the corresponding rules.

Illustrative code skeleton:

~~~java
import org.springframework.context.annotation.ConfigurationCondition;

public final class RegistrationPhaseCondition
        implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
        ConditionContext context,
        org.springframework.core.type.AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment()
            .getProperty("lab.registration.enabled", Boolean.class, false);
    }
}
~~~

*The snippet above illustrates the method and phase; add the corresponding package/file declaration when putting it into a project.* This condition still only reads a property; specifying the phase alone does not make it "wait for all application beans to be initialized".

Spring Boot uses specialized conditions, sometimes with requirements around phases and auto-configuration ordering. Do not use `ConfigurationCondition` unless you genuinely understand the difference between the phases.

## 11. `@Conditional` in Spring Boot Auto-Configuration

Spring Boot auto-configuration classes are typically brought into the context after Boot discovers them from the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Conceptual example of a library:

~~~java
@AutoConfiguration
@ConditionalOnClass(RemoteClient.class)
public class RemoteClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RemoteClient.class)
    RemoteClient remoteClient() {
        return new RemoteClient();
    }
}
~~~

*This is an illustrative snippet assuming `RemoteClient` and proper imports/registration already exist; it is not a standalone runnable Java file.*

How it applies:

1. The auto-configuration class is a **candidate** because it is listed in `imports`.
2. `@ConditionalOnClass` decides whether to evaluate the class when the dependency is present.
3. `@ConditionalOnMissingBean` decides whether to contribute a default bean when no matching bean is visible to the condition.
4. The bean is created when the context actually processes/instantiates definitions, not simply because the `imports` file was read.

### Relationship Between Spring Annotations and Boot Annotations

| Annotation | Belongs to | Purpose |
| --- | --- | --- |
| `@Conditional` | Spring Framework | Attach a general list of `Condition` classes |
| `Condition` | Spring Framework | Contract for deciding true/false |
| `@Profile` | Spring Framework | Activate components by profile; built on the condition mechanism |
| `@ConditionalOnProperty` | Spring Boot | Check property configuration according to Boot rules |
| `@ConditionalOnClass` | Spring Boot | Check classpath condition |
| `@ConditionalOnBean` | Spring Boot | Check whether a bean is already present in the evaluation context |
| `@ConditionalOnMissingBean` | Spring Boot | Create a default bean only when a matching bean is missing |
| `@ConditionalOnWebApplication` | Spring Boot | Condition based on a web application |
| `@ConditionalOnNotWebApplication` | Spring Boot | Condition based on a non-web application |

For a simple property-based condition, you usually **do not need to write a `Condition` yourself**. Example:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "lab.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
MessageService featureService() {
    return () -> "enabled";
}
~~~

This is a replacement for the method in `FeatureConfiguration`; it requires importing `org.springframework.boot.autoconfigure.condition.ConditionalOnProperty`.

Although it behaves similarly to section 6 for `true`/`false`/missing property cases, `@ConditionalOnProperty` is a Boot API with its own semantics, not an automatic consequence of `String.equalsIgnoreCase` in a custom condition.

### Be Careful with Bean-Dependent Conditions

Conditions like `@ConditionalOnBean` and `@ConditionalOnMissingBean` only see definitions that have already been processed at the time they run. Spring Boot recommends using these conditions in auto-configurations, which are typically processed after user bean definitions. Do not write a custom `Condition` using bean names and assume the entire context has finished initializing.

## 12. Testing Conditions and Reading Evidence

### Three Layers of Evidence to Distinguish

- **Environment value:** did the property actually receive the expected value?
- **Condition evaluation:** did the specific condition return `true`/`false` at the moment Spring evaluated the component?
- **Bean state:** after refresh, which bean names/definitions/types are present in the context?

In the demo, `context.containsBean("featureService")` is direct evidence of the bean state after startup. You can inspect bean names like this:

~~~java
String[] names =
    context.getBeanNamesForType(MessageService.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
~~~

*The snippet above requires the `context` variable and `MessageService` import as in the complete program in section 6.*

### `--debug` and the Condition Evaluation Report Have Limits

Spring Boot provides a *Condition Evaluation Report* for Boot conditions, helping explain which auto-configurations and methods matched or did not match. However, **do not assume every custom Spring Framework `Condition` is automatically reported there with a custom message**. In particular, a custom condition that only `implements Condition` like `FeatureEnabledCondition` in the example **does not necessarily appear in Boot's report the same way a `SpringBootCondition` does**.

Gather evidence using the demo's bean states and property tests first. If you need rich reporting from a custom condition in Boot, look into `SpringBootCondition` and `ConditionOutcome` — that is a separate extension layer, not a required signature of `Condition.matches`.

### Repeatable Testing

For small exercises, running the application four times with different properties is enough to prove the contract. For larger libraries, you can use `ApplicationContextRunner` (Spring Boot test) to create contexts with different input properties and assert bean presence/absence. This is a testing technique and **does not change the contract** of `matches`.

Example assertion idea:

~~~java
// This is a test fragment; it requires test dependencies,
// ApplicationContextRunner, and appropriate test configuration.
runner.withPropertyValues("lab.feature.enabled=false")
    .run(context ->
        org.assertj.core.api.Assertions.assertThat(context)
            .doesNotHaveBean(MessageService.class));
~~~

These lines only illustrate how to verify state; **it is not a standalone runnable unit test**. If you want to use `ApplicationContextRunner`, you need to create a runner with `FeatureConfiguration` and declare the appropriate test dependencies.

## 13. Common Mistakes and How to Fix Them

| Symptom / assumption | Correct explanation |
| --- | --- |
| "`matches=true` means the bean is already created" | It only means registration was not vetoed; the bean still depends on scope, dependencies, and lifecycle |
| "`matches=false` means the business method is called and returns `null`" | Wrong: the bean definition is blocked at configuration time; the business method is never called |
| "Changing a property at runtime enables the bean immediately" | No; `@Conditional` is usually evaluated during configuration/registration, with no automatic refresh mechanism |
| "Two conditions in `@Conditional` use OR" | Wrong; all conditions must match (AND) |
| "A method-level condition excludes the entire configuration class" | Wrong; the class can still register other beans |
| "A class-level condition only blocks one method" | Wrong; it governs the configuration and its associated declarations |
| "Inside `matches`, you can call `getBean` normally" | You should not interact with bean instances before registration |
| "Just put `@Conditional` on a bean even if the configuration class isn't scanned/imported" | A condition does not help Spring discover an unloaded class |
| "`@Conditional` is inherited automatically" | Spring documentation does not support condition inheritance in that way |
| "Custom conditions always appear in the Boot report" | Not guaranteed; Boot's report focuses on its corresponding condition/reporting mechanism |
| "Every bean-based condition can see all definitions" | No; you must consider the phase and processing order |
| "If a condition throws an exception, Spring treats it as false by default" | Wrong expectation: an exception from a condition usually fails configuration/startup processing; fix the root error |

### Step-by-Step Debugging Approach

1. Confirm the class carrying `@Conditional` or `@Bean` is being processed by Spring (component scan, `@Import`, auto-configuration, etc.).
2. Confirm all properties/profiles/classpath entries the condition reads; verify exact names and data types.
3. Distinguish whether the condition is attached at the **class** or **method** level.
4. Check multiple AND-combined conditions to see which one fails to match.
5. If using a bean-dependent condition, inspect the phase and definition registration order.
6. Inspect the `ApplicationContext` after startup by bean name/type or `BeanDefinitionRegistry` as appropriate.
7. For Boot conditions with reporting, use `--debug`; for plain custom `Condition`s, prioritize tests and inspecting context results.
8. Only edit code once you have pinpointed the exact layer of failure; avoid altering component scanning or adding beans arbitrarily to "fix" condition=false.

## 14. Self-Check Exercises

1. **Concept:** describe the meaning of `true` and `false` from `Condition.matches`. Why is `true` not synonymous with an already initialized singleton instance?
2. **Scope:** how does placing `@Conditional` on a `@Bean` method differ from placing it on a `@Configuration` class?
3. **Two parameters:** when do you use `ConditionContext.getEnvironment()`, and when do you use `AnnotatedTypeMetadata.getAnnotationAttributes(...)`?
4. **Experiment:** run the project in section 6 with the property omitted, `true`, `false`, and `other`. Match all three output lines accurately.
5. **AND:** replace `@Conditional(FeatureEnabledCondition.class)` with the two conditions in section 8. Predict the result according to the `prod` profile and the property.
6. **Metadata:** create `@EnabledWhenProperty("lab.feature.enabled")` from section 9; remove the old direct annotation, rebuild, and test with the property omitted and with `true`. Explain the difference between defaulting to `false` in the composed annotation versus defaulting to `true` in the original demo.
7. **Class vs method:** add an independent `@Bean` of type `Clock` in `FeatureConfiguration`. Place the condition first on the method, then on the class; with property=`false`, explain which beans are blocked.
8. **What not to do:** write a counter-productive example where `matches` fetches a bean instance. Why can this approach initialize a bean prematurely or break the context?
9. **Auto-configuration:** why does a class listed in `AutoConfiguration.imports` whose condition returns `false` fail to contribute the corresponding bean?
10. **Reading reports:** when a custom condition does not appear in Boot's Condition Evaluation Report, what can and cannot be concluded?

**Completion criteria:** you know how to write a valid `Condition`, accurately explain `matches(context, metadata)`, recognize class vs. method scope, understand the AND semantics of multiple conditions, verify behavior via the context, and distinguish condition evaluation time from bean instantiation.

## 15. Official Documentation

- [Spring Framework 6.1 — `@Conditional` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Conditional.html)
- [Spring Framework 6.1 — `Condition` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html)
- [Spring Framework 6.1 — `ConditionContext` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html)
- [Spring Framework 6.1 — `ConfigurationCondition` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html)
- [Spring Framework — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
