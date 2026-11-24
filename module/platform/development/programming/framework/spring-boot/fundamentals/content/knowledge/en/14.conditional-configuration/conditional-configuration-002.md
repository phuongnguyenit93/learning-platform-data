# Condition, ConditionContext, and Data Used to Evaluate Configuration

Spring Boot often creates beans based on what the application has at startup time: which libraries are on the classpath, which properties are enabled, whether the environment is a web application, and which beans have already been registered. This mechanism is called **conditional configuration**.

At the Spring Framework layer, a condition is represented by the `Condition` interface. During evaluation, Spring supplies a `ConditionContext` so the condition can read the environment and registry, as well as `AnnotatedTypeMetadata` so the condition knows which annotation is being processed and the attributes of that annotation.

Three components to distinguish:

- **`Condition`** contains the rule that decides whether a configuration is suitable or not.
- **`ConditionContext`** provides the data and services needed to evaluate the rule.
- **`AnnotatedTypeMetadata`** describes the class or method carrying `@Conditional` and provides annotation metadata.

Understanding them clearly helps you read how Spring Boot auto-configures an application, write custom conditions for internal libraries, and diagnose why a bean was registered or skipped.

## 1. What Is Conditional Configuration?

Not every application needs the exact same set of beans. For example:

- Only register `EmailSender` when a property enables email.
- Only create a Redis integration when the Redis library is present on the classpath.
- Provide a default `Clock` when the application has not declared another `Clock`.
- Only create a controller or service when the application runs in a suitable web environment.

Instead of writing a single configuration for every environment, Spring allows **registering configurations or beans when conditions are satisfied**.

Conceptual flow:

```text
Read configuration class / @Bean method
                 |
                 v
       Detect @Conditional
                 |
                 v
       Call Condition.matches(...)
                 |
                 v
      Read metadata + context data
                 |
                 v
          Condition true?
             /       \
           Yes        No
           |           |
           v           v
  Continue processing  Skip the corresponding
  configuration/bean   configuration or bean
```

Conditions are typically evaluated during configuration processing, **before the corresponding business beans are instantiated**. Therefore, conditions should not depend on calling a fully constructed business bean.

## 2. What Is `Condition`?

`Condition` is an interface in the `org.springframework.context.annotation` package. It requires implementing the method:

```java
boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
);
```

The method returns:

- `true`: the condition matches; Spring continues processing the configuration element under consideration.
- `false`: the condition does not match; the corresponding configuration element is excluded from processing.

A simple implementation:

```java
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class AlwaysEnabledCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        return true;
    }
}
```

The condition above always returns `true` and only serves to illustrate the API signature. In real applications, `matches()` typically reads properties, the classpath, resources, bean definitions, or annotation metadata to make a decision.

### 2.1. `Condition` Is Not a Business Bean

A condition class is typically instantiated by Spring to evaluate configuration. It is not used like a normal service and should not have business dependencies injected via its constructor.

Example of how not to design it:

```java
// Do not use a condition as a service requiring business bean injection.
public class BadCondition implements Condition {

    private final AccountService accountService;

    public BadCondition(AccountService accountService) {
        this.accountService = accountService;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        return accountService.hasAccounts();
    }
}
```

Reason: conditions are evaluated while Spring is still processing configurations and registering bean definitions. `AccountService` might not be registered or initialized yet. Calling a business bean at this stage can easily create circular dependencies, trigger premature initialization, or cause the condition result to depend on inappropriate runtime state.

Instead, a condition should rely on **metadata and available configuration state** in `ConditionContext`.

## 3. What Data Does `ConditionContext` Provide?

`ConditionContext` is an interface in `org.springframework.context.annotation`. It provides objects that help a condition evaluate configuration without having to create or look up infrastructure services itself.

Key methods:

| Method | Data returned | Common purpose |
| --- | --- | --- |
| `getRegistry()` | `BeanDefinitionRegistry` | Check or access the registry of bean definitions |
| `getBeanFactory()` | `ConfigurableListableBeanFactory` | Inspect bean factory info and bean configuration capabilities |
| `getEnvironment()` | `Environment` | Read properties, profiles, and environment information |
| `getResourceLoader()` | `ResourceLoader` | Locate or check resources |
| `getClassLoader()` | `ClassLoader` | Check the presence of classes and assist with type loading |

Depending on evaluation timing, some infrastructure may not be ready yet or may not contain all bean definitions. Therefore, when writing a condition, use the appropriate data source and do not assume the application context is complete.

### 3.1. `getEnvironment()`: Reading Properties and Profiles

`Environment` provides access to properties from configuration sources Spring has set up, such as:

- `application.properties` or `application.yml`.
- Operating system environment variables.
- Java system properties.
- Spring Boot command-line arguments.
- `PropertySource` instances added by the application.

Example:

```java
boolean enabled = context.getEnvironment()
        .getProperty("features.reports.enabled", Boolean.class, false);
```

If the property does not exist, the example above uses the default value `false`.

You can also check profiles:

```java
boolean devActive = context.getEnvironment()
        .acceptsProfiles(Profiles.of("dev"));
```

Active profiles can affect bean registration, but `Condition` does not activate profiles itself. It only reads the state provided by `Environment`.

### 3.2. `getRegistry()`: Inspecting Registered Bean Definitions

`BeanDefinitionRegistry` gives access to the list of bean definitions. Example:

```java
boolean hasDefinition = context.getRegistry()
        .containsBeanDefinition("paymentGateway");
```

This checks whether the registry contains a bean definition with that name. It does not mean an object has already been instantiated. The registry holds definition data; instances are created at the corresponding lifecycle stage.

If you need to check candidates by type, some conditions may use the bean factory or corresponding metadata. However, at early stages, note that the bean factory might not yet contain all definitions that will appear later.

### 3.3. `getBeanFactory()`: Container Information and Capabilities

`getBeanFactory()` returns `ConfigurableListableBeanFactory`, giving access to information such as bean definitions, aliases, types, and bean factory attributes.

Illustrative example:

```java
ConfigurableListableBeanFactory beanFactory = context.getBeanFactory();

boolean registered = beanFactory.containsBeanDefinition("appClock");
```

`getRegistry()` and `getBeanFactory()` serve closely related purposes, though they are not identical:

- `BeanDefinitionRegistry` focuses on registry operations/lookups.
- `ConfigurableListableBeanFactory` provides bean factory capabilities and definition lookups.

Do not call `getBean()` to instantiate a business service just to decide whether a condition is true or not.

### 3.4. `getResourceLoader()`: Checking Resources

A configuration may only need to be registered when a resource file exists:

```java
Resource resource = context.getResourceLoader()
        .getResource("classpath:features/report-template.json");

return resource.exists();
```

`ResourceLoader` helps Spring resolve resource locations by prefixes such as `classpath:`, `file:`, or an appropriate URL. The condition should handle the case where the resource does not exist and should not read/write files outside its evaluation goal.

### 3.5. `getClassLoader()`: Checking Libraries on the Classpath

An integration library may only work when a class from an optional library is present. Using the classloader helps a condition check availability:

```java
ClassLoader classLoader = context.getClassLoader();
boolean present = ClassUtils.isPresent(
        "com.example.optional.Client",
        classLoader
);
```

`ClassUtils.isPresent` belongs to Spring Core (`org.springframework.util.ClassUtils`). This check avoids directly instantiating the class or creating a client during the condition phase.

## 4. What Information Does `AnnotatedTypeMetadata` Provide?

`AnnotatedTypeMetadata` is in the `org.springframework.core.type` package. It represents the annotation metadata of an element being processed, typically:

- A configuration class.
- A method declared inside a configuration class, such as a method annotated with `@Bean`.

This metadata allows a condition to read annotations and annotation attributes without relying on creating bean instances.

Some important APIs:

| Method | Meaning |
| --- | --- |
| `isAnnotated(String annotationName)` | Checks if the metadata has the corresponding annotation |
| `getAnnotationAttributes(String annotationName)` | Retrieves annotation attributes as a `Map` |
| `getAllAnnotationAttributes(String annotationName)` | Retrieves all attribute values when an annotation may appear via multiple paths |
| `hasAnnotation(String annotationName)` | Checks for a direct annotation via the metadata API |
| `hasMetaAnnotation(String metaAnnotationName)` | Checks if the metadata has the corresponding meta-annotation |
| `getAnnotations()` | Accesses the merged annotations model |

`AnnotatedTypeMetadata` can describe either a class or a method; therefore, a condition should not assume all metadata represents a class. If a condition is placed on a `@Bean` method, the metadata can be that method's metadata.

### 4.1. Reading Annotation Attributes

Suppose a custom annotation has a `feature` attribute:

```java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(
                ConditionalOnFeature.class.getName()
        );

String feature = (String) attributes.get("value");
```

The condition uses metadata to know which feature the annotation is requesting. This is useful when a single condition class can be reused across multiple configurations.

### 4.2. Why Use Metadata Instead of Direct Reflection?

Reflection on a runtime class usually requires the class to already be loaded. Meanwhile, Spring can read metadata from the class file before creating beans or even before fully initializing the configuration class.

`AnnotatedTypeMetadata` allows conditions to operate on annotation information already parsed by Spring. This supports conditional configuration processing and limits forcing unnecessary class initialization.

When working with composed annotations, Spring's merged annotation APIs also help read metadata across meta-annotation relationships and aliases according to framework rules.

## 5. Example: Writing a Property-Based `Condition`

Suppose an application has a reporting feature. Only when `features.reports.enabled=true` does Spring register the configuration providing `ReportService`.

### 5.1. Creating the `@ConditionalOnFeature` Annotation

```java
package com.example.demo.condition;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Conditional(FeatureEnabledCondition.class)
public @interface ConditionalOnFeature {
    String value();
}
```

This annotation:

- Can be placed on a class or method.
- Is retained at runtime.
- Connects to `FeatureEnabledCondition` via `@Conditional`.
- Accepts the feature name via the `value` attribute.

### 5.2. Writing the Condition

```java
package com.example.demo.condition;

import java.util.Map;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class FeatureEnabledCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Map<String, Object> attributes =
                metadata.getAnnotationAttributes(
                        ConditionalOnFeature.class.getName()
                );

        if (attributes == null) {
            return false;
        }

        String feature = (String) attributes.get("value");
        String propertyName = "features." + feature + ".enabled";

        return context.getEnvironment().getProperty(
                propertyName,
                Boolean.class,
                false
        );
    }
}
```

What the condition does:

1. Reads the `value` attribute from the annotation metadata.
2. If matching metadata cannot be retrieved, returns `false`.
3. Builds the property key from the feature name.
4. Reads the Boolean value from `Environment`.
5. Returns `true` only when the property has the value `true`; if missing, defaults to `false`.

The condition does not need to call `ReportService`, create business objects, or modify the registry.

### 5.3. Using the Annotation on a Configuration Class

```java
package com.example.demo.report;

import com.example.demo.condition.ConditionalOnFeature;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnFeature("reports")
public class ReportConfiguration {

    @Bean
    public ReportService reportService() {
        return new ReportService();
    }
}
```

When the configuration class's condition is not satisfied, Spring skips the configuration class during the corresponding processing; the `reportService()` method is not used to register a bean from that configuration.

### 5.4. Or Using It on a `@Bean` Method

```java
@Configuration(proxyBeanMethods = false)
public class OptionalFeatureConfiguration {

    @Bean
    @ConditionalOnFeature("reports")
    public ReportService reportService() {
        return new ReportService();
    }
}
```

Here the condition applies only to the bean definition provided by the `reportService()` method. Other configurations and bean methods in the class can still be processed.

### 5.5. Enabling or Disabling the Feature

In `application.properties`:

```properties
features.reports.enabled=true
```

When enabled:

```text
features.reports.enabled=true
        |
        v
FeatureEnabledCondition.matches() = true
        |
        v
ReportService is registered
```

When disabled or undeclared:

```properties
features.reports.enabled=false
```

or without the corresponding property:

```text
Condition returns false
        |
        v
ReportService is not registered from this configuration
```

If another bean requires injecting `ReportService` while the feature is disabled, the application may fail with a missing bean error. In that case, the bean using the feature also needs an appropriate condition, or the dependency must be designed as optional via `ObjectProvider`, `Optional`, or another mechanism.

## 6. Conditions Can Check the Classpath

A common use case is only registering an integration when an external library is present.

Example:

```java
package com.example.demo.condition;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;
import org.springframework.util.ClassUtils;

public class OptionalClientPresentCondition implements Condition {

    private static final String CLIENT_CLASS =
            "com.example.optional.OptionalClient";

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        return ClassUtils.isPresent(
                CLIENT_CLASS,
                context.getClassLoader()
        );
    }
}
```

Using the condition:

```java
@Configuration(proxyBeanMethods = false)
@Conditional(OptionalClientPresentCondition.class)
public class OptionalClientConfiguration {

    @Bean
    public OptionalClientAdapter optionalClientAdapter() {
        return new OptionalClientAdapter();
    }
}
```

Meaning:

- If `OptionalClient` is present on the classpath, the condition can return `true`.
- If the optional library is not present, the configuration is skipped.

This is one way to build an optional integration module. In Spring Boot, you can usually use `@ConditionalOnClass` instead of writing a custom condition for this simple case.

**Important note:** if a configuration class directly references a type that only exists in an optional library, the classloader may encounter issues before the condition can protect the configuration, depending on how the class is loaded and how metadata is processed. For auto-configurations targeting optional libraries, organize configurations so that classes requiring the library are only loaded when the classpath condition matches, following the auto-configuration pattern supported by your Spring Boot version.

## 7. Conditions Based on Registered Beans

A default configuration often needs to step aside if the application has already provided a bean itself.

Example:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultClockConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

`@ConditionalOnMissingBean` is a Spring Boot annotation. It only allows the default bean to be registered when no matching bean is found according to the configured criteria at the time the condition is evaluated.

The application can provide its own bean:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean
    public Clock businessClock() {
        return Clock.systemDefaultZone();
    }
}
```

In properly ordered auto-configuration, the default clock can "back off" when a `Clock` bean is already provided by the application. This is how Spring Boot lets users customize defaults without needing bean definition overriding.

### 7.1. Evaluation Timing Matters

Bean-presence conditions check based on definitions visible at evaluation time. If you write two user configurations yourself without defining processing order, do not assume the condition will always see beans registered later.

Spring Boot organizes auto-configuration with ordering mechanisms and conditions to support the "default if user has not configured one" pattern. For custom auto-configuration, follow the ordering and registration mechanisms of the version in use.

### 7.2. Checking by Type vs. Checking by Name Differ

The following two configurations are not completely equivalent:

```java
@ConditionalOnMissingBean(Clock.class)
```

and:

```java
@ConditionalOnMissingBean(name = "appClock")
```

The first condition inspects beans by type `Clock`; the second inspects beans by the name `appClock`. When an application has multiple beans of the same type with different names, the choice of condition changes the outcome.

## 8. Conditions in Spring Boot: Built-in Annotations

Spring Boot provides many common conditions so you do not have to rewrite frequently used rules yourself.

| Annotation | Typical condition | Use case |
| --- | --- | --- |
| `@ConditionalOnClass` | One or more classes are on the classpath | Optional library integration |
| `@ConditionalOnMissingClass` | Specified class is not on the classpath | Choosing a fallback configuration |
| `@ConditionalOnBean` | A matching bean is already registered | Configuration needing an existing dependency |
| `@ConditionalOnMissingBean` | No matching bean exists yet | Providing a default bean |
| `@ConditionalOnSingleCandidate` | A single matching candidate can be selected per rules | Auto-configuring when a dependency is unambiguous |
| `@ConditionalOnProperty` | Property satisfies condition | Toggling features via configuration |
| `@ConditionalOnResource` | Specified resource exists | Enabling configuration when a file/resource is present |
| `@ConditionalOnWebApplication` | Application has matching web type | Web-specific configuration |
| `@ConditionalOnNotWebApplication` | Application does not run in a web environment | Configuration for command-line/background apps |
| `@ConditionalOnExpression` | SpEL expression evaluates to a matching result | Complex conditions requiring expressions |
| `@ConditionalOnJava` | Java version matches | Different support per Java runtime |
| `@ConditionalOnJndi` | Matching JNDI is available | Container/JNDI integration |

These annotations belong to `org.springframework.boot.autoconfigure.condition`. The exact list and attribute details depend on the Spring Boot version; use the API of your project's version.

### 8.1. `@ConditionalOnProperty`

This is a common choice to toggle a feature on or off:

```java
@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "features.metrics",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    public MetricsPublisher metricsPublisher() {
        return new MetricsPublisher();
    }
}
```

In `application.properties`:

```properties
features.metrics.enabled=true
```

Explanation:

- `prefix`: the beginning part of the property key.
- `name`: the property name part after the prefix.
- `havingValue`: the value that must match; here the string `true`.
- `matchIfMissing`: whether the condition matches if the property is missing; defaults to `false`.

With this example, the bean is only registered when `features.metrics.enabled=true`. If the property is missing or has another value, `metricsPublisher()` does not create a bean definition from that configuration.

### 8.2. `@ConditionalOnClass`

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.optional.OptionalClient")
public class OptionalIntegrationConfiguration {
    // Beans integrating the optional client
}
```

Using `name` as a string can be useful when the referenced type is not present on the classpath of every application. This avoids directly referencing the optional class in the annotation metadata of the outer configuration.

### 8.3. `@ConditionalOnMissingBean`

```java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
public PaymentGateway defaultPaymentGateway() {
    return new DemoPaymentGateway();
}
```

This is a typical auto-configuration pattern: provide a default implementation if the application has not registered a matching `PaymentGateway`.

### 8.4. Combining Multiple Conditions

You can place multiple conditional annotations on a class or method:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.optional.ReportClient")
@ConditionalOnProperty(
    prefix = "features.reports",
    name = "enabled",
    havingValue = "true"
)
public class ReportIntegrationConfiguration {
    // Report integration configuration
}
```

In normal usage, all applied conditions must be satisfied for the configuration to be processed. That means the library must be present **and** the feature must be enabled.

## 9. `ConfigurationCondition` and Evaluation Timing

Some conditions need to know which stage Spring is in during configuration processing. Spring provides `ConfigurationCondition`, an interface extending `Condition`.

It adds:

```java
ConfigurationPhase getConfigurationPhase();
```

Two phases:

| Phase | Meaning |
| --- | --- |
| `PARSE_CONFIGURATION` | While Spring is parsing configuration classes |
| `REGISTER_BEAN` | While Spring is registering bean definitions |

Conceptual example:

```java
public class ParsePhaseCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        return true;
    }
}
```

With `PARSE_CONFIGURATION`, the condition is evaluated during the configuration parsing stage. With `REGISTER_BEAN`, the condition is evaluated while Spring is handling bean definition registration. The phase choice affects what data is observable when the condition runs.

### 9.1. Why Shouldn't You Assume All Beans Already Exist?

In the parse phase, Spring may not yet have registered all bean definitions from other configuration classes. A condition checking the registry at this stage might not see a bean that will be registered at a later stage.

If a rule needs to evaluate the presence of bean definitions, choose the appropriate phase and consider processing order. Do not use a condition in an early phase to depend on a bean that is only registered later.

### 9.2. Do Not Confuse Phases with Object Initialization Lifecycles

`PARSE_CONFIGURATION` and `REGISTER_BEAN` are **configuration metadata processing** phases, not `@PostConstruct`, `InitializingBean`, or instance initialization callbacks.

Example:

```text
Parse configuration classes
          |
          v
Evaluate conditions in parse phase
          |
          v
Register bean definitions
          |
          v
Evaluate conditions in register-bean phase
          |
          v
Instantiate bean instances when needed
          |
          v
Initialization callbacks
```

This is a simplified diagram; Spring has additional processors and internal steps.

## 10. How Should a `Condition` Be Designed?

A good condition should have the following characteristics:

1. **Read only the necessary data:** properties, profiles, classpath, resources, registry, or annotation metadata.
2. **Produce no side effects:** do not open connections, write files, send requests, or register beans inside `matches()`.
3. **Do not depend on business beans:** the condition must run while the container is still processing configuration.
4. **Have deterministic results:** given the same metadata and environment, it should make the same decision.
5. **Handle missing data:** missing properties, absent classes, or missing resources should have clear behavior.
6. **Separate logic:** the condition only decides whether something is suitable; object creation belongs in the configuration or factory method.

Example of a condition reading a property:

```java
public class ExternalSearchEnabledCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        return context.getEnvironment().getProperty(
                "search.external.enabled",
                Boolean.class,
                false
        );
    }
}
```

A condition should not do the following:

```java
// Do not: call a business bean during condition evaluation.
SomeService service = context.getBeanFactory()
        .getBean(SomeService.class);
return service.isReady();
```

`getBeanFactory()` provides the bean factory, but calling `getBean()` can force object creation while configuration is still incomplete. That can cause circular dependencies or initialize beans at an unwanted time.

## 11. Conditions and Auto-Configuration in Spring Boot

Spring Boot uses conditions to apply configurations only when the required conditions are met.

Conceptual example:

```text
Is spring-webmvc on the classpath?
          |
          v
Is there a servlet web environment?
          |
          v
Has the application not provided the corresponding bean itself?
          |
          v
Register the appropriate default MVC configuration
```

A real auto-configuration can include multiple conditions and multiple bean methods. It can "back off" when the user configures custom beans or properties.

### 11.1. Auto-Configuration Is Not Component Scanning

The two mechanisms have different roles:

| Mechanism | Job |
| --- | --- |
| Component scanning | Finds application classes marked with stereotypes in scanned packages |
| Auto-configuration | Applies framework configurations based on classpath, environment, bean definitions, and conditions |

For example, your `@Service` is discovered via component scanning. A Spring Boot default configuration may be imported through the auto-configuration mechanism and only registers beans when the corresponding conditions match.

### 11.2. Auto-Configuration Can Yield to the User

A library starter typically provides a default bean:

```java
@Configuration(proxyBeanMethods = false)
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    public SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
```

The application can provide its own:

```java
@Configuration(proxyBeanMethods = false)
public class CustomSearchConfiguration {

    @Bean
    public SearchClient searchClient() {
        return new CompanySearchClient();
    }
}
```

When auto-configuration is processed in the proper order, `SearchAutoConfiguration` sees the `SearchClient` bean provided by the application and does not register the default bean. This is an important part of the "convention over configuration" model in Spring Boot.

### 11.3. Conditions Can Be Applied on a Class or Method

```java
@Configuration
@ConditionalOnProperty(
    prefix = "features",
    name = "audit",
    havingValue = "true"
)
public class AuditConfiguration {

    @Bean
    public AuditWriter auditWriter() {
        return new AuditWriter();
    }

    @Bean
    public AuditReporter auditReporter() {
        return new AuditReporter();
    }
}
```

A condition on the class affects the entire configuration class and its bean methods.

If only one bean needs a condition:

```java
@Configuration
public class AuditConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "features",
        name = "audit",
        havingValue = "true"
    )
    public AuditWriter auditWriter() {
        return new AuditWriter();
    }

    @Bean
    public AuditReporter auditReporter() {
        return new AuditReporter();
    }
}
```

In the second example, `AuditReporter` is still defined from the configuration class even if the audit property is not enabled. If the reporter strictly requires `AuditWriter`, an appropriate condition or dependency design is needed to avoid a missing bean.

## 12. Diagnosing Non-Matching Conditions

When an expected bean does not appear in the application context, the cause may be that a condition returned `false`. Spring Boot provides tools to inspect auto-configuration decisions.

### 12.1. Enabling the Condition Evaluation Report

Start the application with the argument:

```text
--debug
```

Or set:

```properties
debug=true
```

Spring Boot can print the **Conditions Evaluation Report**. The report shows which auto-configurations matched, did not match, and the corresponding reasons.

Informational example:

```text
Positive matches:
   SomeAutoConfiguration matched:
      - @ConditionalOnClass found required class ...

Negative matches:
   OtherAutoConfiguration:
      - @ConditionalOnProperty did not find property ...
```

This is illustrative output; condition names and formatting depend on the Spring Boot version.

### 12.2. Distinguishing Non-Matching Conditions from Bean Creation Failures

| Symptom | Interpretation |
| --- | --- |
| Condition returns `false` | The corresponding configuration/bean method was skipped |
| Condition returns `true`, but bean creation fails | Configuration was selected, but constructor/factory/dependency or lifecycle encountered an error |
| Bean definition does not appear | Condition may not have matched, configuration was not imported/scanned, or excluded by another mechanism |
| Bean exists, but cannot be injected | Wrong type, qualifier, primary, or multiple candidates |
| Property is set, but condition is still false | Check key, property source, profile, type conversion, and expected value |

Do not fix a bean creation error by changing a condition to always return `true`. First determine whether the configuration was skipped or the bean was selected and failed during creation.

### 12.3. Checking the Effective Property

If a condition depends on `Environment`, verify:

- Does the property name have the right prefix and spelling?
- Is the configuration file on the classpath and loaded?
- Is the desired profile active?
- Is an environment variable or command-line argument overriding the file value?
- Does `havingValue` match the exact value?
- Is `matchIfMissing` `true` or `false`?

For example, with:

```java
@ConditionalOnProperty(
    prefix = "features.reports",
    name = "enabled",
    havingValue = "true"
)
```

the matching property is:

```properties
features.reports.enabled=true
```

`features.report.enabled=true` (missing the letter `s`) is a different key so the condition may not match.

## 13. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "A Condition is a normal service bean." | Conditions are used during configuration processing; they should not depend on business beans |
| "`ConditionContext` already contains all bean instances." | Context provides evaluation infrastructure; registry/bean factory may be incomplete |
| "`getRegistry().containsBeanDefinition()` proves a bean has been initialized." | It only confirms a bean definition with that name exists |
| "`AnnotatedTypeMetadata` always describes a class." | It can describe a class or a method, depending on where `@Conditional` is placed |
| "Conditions only read `application.properties`." | They can read environment, profiles, classpath, resources, registry, and metadata |
| "If a condition is true, the bean is guaranteed to initialize successfully." | The condition only allows registration to proceed; bean creation can still fail |
| "`@ConditionalOnMissingBean` always sees all beans that will be registered later." | It evaluates definitions visible at the time the condition runs |
| "`@Conditional` creates beans by itself." | It only decides whether to process the configuration/bean method; beans are created by the configuration mechanism |
| "All bean lists are filtered by conditions." | Conditions apply at the specified configuration point, not as a general runtime filter for every collection |

## 14. Practice Exercises

### Exercise 1 — Toggling a Feature with a Property

Create `@ConditionalOnFeature` and `FeatureEnabledCondition` as in section 5. Create `ReportConfiguration` providing `ReportService`.

Run the application with:

```properties
features.reports.enabled=true
```

Then change it to:

```properties
features.reports.enabled=false
```

Observe whether `ReportService` is registered or not. Explain the default value when the property is left blank.

### Exercise 2 — Reading Profiles from `ConditionContext`

Write a condition that matches only when the `dev` profile is active:

```java
return context.getEnvironment()
        .acceptsProfiles(Profiles.of("dev"));
```

Attach the condition to a configuration class. Start the application with the `dev` and `prod` profiles in turn, then observe the bean.

### Exercise 3 — Checking the Classpath

Write a condition using `ClassUtils.isPresent(...)` to check for an optional library class. Run the project when the dependency is present, then remove the dependency from the build configuration and observe the result. Explain why the condition should avoid directly referencing an absent type.

### Exercise 4 — Distinguishing Registry and Instance

In a condition, use `getRegistry().containsBeanDefinition("appClock")` to check for the definition. Compare this with looking up the bean in the application context after startup.

Explain why having a definition in the registry does not mean the instance has already been created.

### Exercise 5 — Conditions Based on Annotation Metadata

Create an annotation with a `value` attribute and use `AnnotatedTypeMetadata.getAnnotationAttributes(...)` to read the value. Place the annotation on a configuration class and on a `@Bean` method. Observe the corresponding metadata inside `matches()`.

### Exercise 6 — Using Spring Boot's Built-in Conditions

Try the annotations:

- `@ConditionalOnProperty`
- `@ConditionalOnClass`
- `@ConditionalOnMissingBean`

For each annotation, describe what data determines the outcome and what happens when the condition is not satisfied.

### Exercise 7 — Viewing the Condition Evaluation Report

Start the application with `--debug`. Find one auto-configuration with a positive match and one auto-configuration with a negative match. Explain which specific condition determined the result.

## 15. Takeaways

`Condition` holds the rule that answers the question: **does this configuration fit the current environment?** `ConditionContext` provides data such as the environment, registry, bean factory, resource loader, and classloader. `AnnotatedTypeMetadata` provides information about the class or method carrying the annotation, allowing the condition to read attributes and related metadata.

Spring Boot builds many auto-configurations on these conditions. When customizing, prefer built-in annotations such as `@ConditionalOnProperty`, `@ConditionalOnClass`, and `@ConditionalOnMissingBean`; only write a custom `Condition` when your application's rule truly requires it.

A condition should read metadata and configuration state, return a clear result, produce no side effects, and avoid calling business beans during configuration processing. Understanding how data is evaluated will help you see why Spring Boot registers or skips a bean, while building more predictable starters and custom configurations.
