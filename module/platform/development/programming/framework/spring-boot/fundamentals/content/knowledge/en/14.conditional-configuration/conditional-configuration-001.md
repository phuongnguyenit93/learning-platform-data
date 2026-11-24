# `@Conditional` and When a Configuration Is Decided to Be Registered

Spring Boot often has many configurations that should only be applied when a certain condition is satisfied. For example: only creating an email-sending bean when the email library is on the classpath; only configuring a database when the appropriate driver is present; or only creating a default bean when the application has not provided a replacement bean itself.

Spring accomplishes this using **conditional configuration**. The foundational annotation is Spring Framework's `@Conditional`. Spring Boot builds many specialized annotations on top of that mechanism, such as `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, and `@ConditionalOnWebApplication`.

The key point is not just knowing how to write conditional annotations, but understanding **when Spring evaluates conditions**. Conditions are checked during configuration parsing or bean definition registration, before the corresponding bean instance is created. They are not expressions that re-run on every request, nor do they automatically change after the application has started.

This lesson belongs to the **Conditional Configuration** chapter of **Spring Boot Fundamentals**. We will explore the `@Conditional` mechanism, the configuration processing phases, how Spring Boot uses conditions in auto-configuration, how to write custom conditions, and how to diagnose why a bean was or was not registered.

## 1. Why Do We Need Conditional Configuration?

Suppose an application has a notification-sending interface:

```java
package com.example.demo.notification;

public interface NotificationSender {
    void send(String message);
}
```

There may be multiple ways to send notifications:

```java
package com.example.demo.notification;

public class EmailNotificationSender implements NotificationSender {
    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}
```

```java
package com.example.demo.notification;

public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String message) {
        System.out.println("Console: " + message);
    }
}
```

In a development environment, we might want to use the console sender. In production, we might want to use the email sender if the email library has been configured. If both beans are always registered, a service injecting a single `NotificationSender` may encounter ambiguity.

One solution is to register only the bean that matches the environment's condition:

```text
                Read application configuration
                             │
                             ▼
                Condition "notification.mode"
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
             mode=console             mode=email
                 │                       │
                 ▼                       ▼
      Register ConsoleSender     Register EmailSender
                 │                       │
                 └───────────┬───────────┘
                             ▼
                   ApplicationContext
```

Conditional configuration is useful when a feature is optional, the application runs across multiple environments, an integration library is only present in some builds, users can replace a default bean, or a configuration should only be active when another property or bean exists.

## 2. Spring Framework's `@Conditional`

The foundational annotation is located in the package:

```java
import org.springframework.context.annotation.Conditional;
```

`@Conditional` accepts one or more classes that implement the `Condition` interface:

```java
@FunctionalInterface
public interface Condition {

    boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    );
}
```

A condition returns `true` when the condition matches; it returns `false` when the component under consideration should be excluded from the corresponding registration process.

`ConditionContext` provides information about the processing environment, such as the registry, bean factory, environment, resource loader, and class loader. `AnnotatedTypeMetadata` allows reading the annotation metadata of the class or method being checked.

### 2.1. Custom Condition Example

Suppose you only want to register a configuration when the property `feature.audit-enabled` has the value `true`.

```java
package com.example.demo.condition;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class AuditEnabledCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        String value = context.getEnvironment()
                .getProperty("feature.audit-enabled");

        return Boolean.parseBoolean(value);
    }
}
```

Using the condition:

```java
package com.example.demo.audit;

import com.example.demo.condition.AuditEnabledCondition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Conditional;

@Configuration(proxyBeanMethods = false)
@Conditional(AuditEnabledCondition.class)
public class AuditConfiguration {

    @Bean
    public AuditService auditService() {
        return new AuditService();
    }
}
```

Configuration:

```yaml
feature:
  audit-enabled: true
```

When the property has the value `true`, the condition returns `true` and `AuditConfiguration` is accepted for processing. When the property does not exist or has a value not considered true by `Boolean.parseBoolean`, the condition returns `false`.

The condition here is attached to a **configuration class**. If it does not match, Spring skips that configuration and the bean definitions declared inside the class.

### 2.2. A Condition Is Not a Regular Business Bean

A class implementing `Condition` is instantiated by the framework to evaluate the condition. A condition should not be treated like a business service that can be arbitrarily injected into the application context.

A condition should have small, deterministic, and easy-to-test logic; rely on data available during the evaluation phase; have no side effects; not open network connections or perform business operations; and not depend on application bean instances that have not yet been created.

In particular, you should not inject a regular service into a condition and call it to decide whether to register that service. The condition may be evaluated before such beans even exist.

## 3. Two Common Places to Put `@Conditional`

Spring allows conditions to be applied to a configuration class or a `@Bean` method.

### 3.1. Condition on a Configuration Class

```java
@Configuration(proxyBeanMethods = false)
@Conditional(AuditEnabledCondition.class)
public class AuditConfiguration {

    @Bean
    public AuditService auditService() {
        return new AuditService();
    }

    @Bean
    public AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
```

If the condition does not match, the entire configuration class is skipped. Neither bean definition inside it is registered from this configuration.

This approach is suitable when multiple beans form a configuration group and depend on the same condition together.

### 3.2. Condition on a `@Bean` Method

If only a single bean depends on the condition, place the annotation directly on the factory method:

```java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @Conditional(AuditEnabledCondition.class)
    public AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }

    @Bean
    public NotificationService notificationService() {
        return new NotificationService();
    }
}
```

The condition applies only to the bean definition from `auditPublisher()`. `notificationService` can still be registered.

However, if `NotificationService` requires `AuditPublisher` via its constructor and the publisher bean is not registered, that service may cause the context startup to fail. Conditional configuration must be designed alongside the dependency graph, not by looking at an annotation on a single method in isolation.

### 3.3. Scope Comparison

| Annotation location | Scope affected when the condition does not match |
|---|---|
| On a `@Configuration` class | The configuration class and the bean definitions declared within it |
| On a `@Bean` method | The bean definition provided by that method |
| On a component class | That component is not registered via component scanning if the condition does not match |
| On an imported configuration | The imported configuration branch can be excluded according to the corresponding mechanism |

A class-level condition does not automatically exclude other independent components in neighboring packages. It only affects the configuration/component to which the annotation is attached and the elements within its processing scope.

## 4. Condition Evaluation Timing: Parse and Register

This is the core part of the lesson.

Spring does not wait until a bean is called for the first time to decide whether to register the bean. Conditions are evaluated during configuration processing and bean definition registration.

Spring Framework has the `ConfigurationCondition` interface extending `Condition` so that a condition can specify the phase in which it should be evaluated:

```java
public interface ConfigurationCondition extends Condition {

    ConfigurationPhase getConfigurationPhase();

    enum ConfigurationPhase {
        PARSE_CONFIGURATION,
        REGISTER_BEAN
    }
}
```

The two phases mean:

- `PARSE_CONFIGURATION`: the condition is evaluated while Spring is parsing configuration classes. If it does not match, the configuration class is not processed further as a configuration source.
- `REGISTER_BEAN`: the condition is evaluated at the bean definition registration stage. This stage is suitable for conditions that need to observe the registry or bean definitions registered earlier.

For a condition that only implements `Condition` without specifying a phase via `ConfigurationCondition`, Spring handles it according to the default rules of the condition evaluation process, typically at the bean registration phase. Specialized conditions may choose another phase.

### 4.1. Simplified Timeline Diagram

```text
Spring startup / ApplicationContext refresh
                   │
                   ▼
   Read and process configuration sources
                   │
                   ▼
       PARSE_CONFIGURATION phase
       - Evaluate class-level conditions needed for parsing
       - Process @Import and related configurations
                   │
                   ▼
       REGISTER_BEAN phase
       - Register bean definitions
       - Evaluate corresponding bean/method conditions
       - Observe registry at processing time
                   │
                   ▼
     Complete configuration registration
                   │
                   ▼
   Create eager singletons and inject dependencies
                   │
                   ▼
        Initialization callbacks
                   │
                   ▼
       ApplicationContext ready
```

The diagram illustrates the main stages, not the complete internal order of every post-processor. Spring has many steps for processing metadata, import selectors, registrars, and bean factory post-processors.

Key point to remember: **a condition decides whether a configuration/bean definition is registered before the corresponding bean instance is created**.

### 4.2. Conditions on Configuration Classes Are Evaluated Early

```java
@Configuration(proxyBeanMethods = false)
@Conditional(AuditEnabledCondition.class)
public class AuditConfiguration {

    @Bean
    public AuditService auditService() {
        return new AuditService();
    }
}
```

Spring needs to know whether `AuditConfiguration` is accepted before parsing the configuration declarations inside it. If the condition does not match in the parse phase, the configuration class is skipped.

This matters if the class has `@Import`, `@ComponentScan`, or multiple `@Bean` declarations: skipping the class can exclude the entire configuration branch provided by that class.

### 4.3. Conditions on `@Bean` Methods Are Evaluated When Registering Bean Definitions

```java
@Configuration(proxyBeanMethods = false)
public class OptionalFeatureConfiguration {

    @Bean
    @Conditional(AuditEnabledCondition.class)
    public AuditService auditService() {
        return new AuditService();
    }
}
```

Spring parses the configuration class, and then evaluates the corresponding condition when registering the bean definition from `auditService()`. If it does not match, that bean definition is not registered.

You should not interpret this as Spring creating `AuditService` first and then checking the condition. The condition is used to decide **whether to register the definition that creates the bean**.

## 5. What Data Does a Condition Need in Each Phase?

`ConditionContext` provides access to different pieces of information depending on the timing:

| API | Available data |
|---|---|
| `getEnvironment()` | Loaded properties, profiles, and PropertySources |
| `getRegistry()` | Registry containing bean definitions registered up to the current point |
| `getBeanFactory()` | BeanFactory if ready in the corresponding phase |
| `getResourceLoader()` | Resource loading mechanism |
| `getClassLoader()` | Class loader to check classes/resources |

Not every API can be used with the same level of safety in every phase. In particular, when a condition runs early, you should not assume all bean definitions or bean instances of the application already exist.

### 5.1. Why Shouldn't You Call `getBean()` to Decide a Condition?

A condition like the following is an inappropriate design:

```java
@Override
public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
) {
    SomeService service =
            context.getBeanFactory().getBean(SomeService.class);

    return service.isEnabled();
}
```

Reasons:

- The condition may run before `SomeService` is created.
- `SomeService` might depend on the very configuration the condition is deciding.
- Creating a bean prematurely during configuration registration can disrupt the lifecycle.
- The condition becomes dependent on side effects and unstable runtime state.

Use properties, the classpath, bean definitions, or metadata appropriate for the phase instead of calling a business bean.

### 5.2. Bean Definition vs. Bean Instance

Registry-based conditions typically check **registered bean definitions**, not necessarily created instances.

For example, a condition can see the bean definition of `Clock` even if the `Clock` singleton has not been instantiated yet. This is an important point when using conditions based on bean existence.

You should not say `@ConditionalOnBean` always checks for a "running object" or an "already initialized bean". The mechanism primarily works with container information that can be determined at registration time.

## 6. `ConfigurationCondition`: Explicitly Choosing a Phase

If a custom condition depends on the timing of configuration processing, it can implement `ConfigurationCondition`.

Example of a condition that needs to inspect the registry during the bean registration phase:

```java
package com.example.demo.condition;

import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class AuditRegistryCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        return context.getRegistry()
                .containsBeanDefinition("auditInfrastructure");
    }
}
```

Usage:

```java
@Configuration(proxyBeanMethods = false)
@Conditional(AuditRegistryCondition.class)
public class AuditExtensionConfiguration {

    @Bean
    public AuditExtension auditExtension() {
        return new AuditExtension();
    }
}
```

In the example, the condition only matches when the registry already has a bean definition named `auditInfrastructure` at the time the condition is evaluated.

Note: whether a definition is present **before** or **after** also depends on configuration registration order. If the configuration containing `auditInfrastructure` has not been processed yet when the condition runs, the condition may return false even though that definition will be registered later.

### 6.1. When to Choose PARSE_CONFIGURATION?

Use the parse phase when deciding whether to process the entire configuration class and the condition does not need to rely on bean definitions registered at a later stage.

For example, a configuration that is only suitable for a specific classpath or environment. Class-level conditions can be evaluated early to skip an unnecessary configuration branch.

### 6.2. When to Choose REGISTER_BEAN?

Use the register phase when the condition depends on the registry or the state of bean definitions registered earlier.

For example:

- A default bean should only be registered if no other bean exists yet.
- An additional configuration only applies when the required infrastructure already has a definition.
- A condition needs to analyze bean factory information at the registration stage.

Do not use the register phase as a guarantee that all application beans already exist; it only allows the condition to observe the state of the registry at execution time.

## 7. Specialized Conditions Provided by Spring Boot

Spring Boot builds many annotations on top of `@Conditional` to handle common scenarios. They make configurations easier to read and reduce the need to write custom conditions for each feature.

| Annotation | Main condition |
|---|---|
| `@ConditionalOnClass` | The specified class is on the classpath |
| `@ConditionalOnMissingClass` | The specified class is not on the classpath |
| `@ConditionalOnBean` | A matching bean has already been registered |
| `@ConditionalOnMissingBean` | No matching bean has been registered yet |
| `@ConditionalOnSingleCandidate` | There is a single matching candidate or a clearly preferred primary candidate |
| `@ConditionalOnProperty` | A property has a value satisfying the condition |
| `@ConditionalOnResource` | The specified resource exists |
| `@ConditionalOnWebApplication` | The application is recognized as a web application of the specified type |
| `@ConditionalOnNotWebApplication` | The application is not a web application |
| `@ConditionalOnExpression` | A SpEL expression evaluates to a matching condition |
| `@ConditionalOnJava` | The Java version satisfies a range |
| `@Profile` | A profile is active |

These annotations are usually placed on configuration classes or bean methods. They provide a readable way to declare conditions; underneath, the mechanism is still Spring's condition evaluation process.

## 8. `@ConditionalOnClass` and `@ConditionalOnMissingClass`

### 8.1. Configure Only When a Library Is on the Classpath

Example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.mail.MailClient")
public class MailClientConfiguration {

    @Bean
    public MailNotificationSender mailNotificationSender() {
        return new MailNotificationSender();
    }
}
```

If the class `com.example.mail.MailClient` can be found on the classpath, the condition matches and the configuration is accepted.

If the mail library has not been added as a dependency, the configuration is skipped instead of trying to create a bean that depends on a nonexistent class.

You can use a class literal:

```java
@ConditionalOnClass(MailClient.class)
```

or a class name as a string:

```java
@ConditionalOnClass(name = "com.example.mail.MailClient")
```

A string class name is useful when you want to avoid forcing the JVM to resolve an optional type right when loading the configuration class. Especially in auto-configuration libraries, consider how classes are organized so that classes referencing optional types are not loaded when the dependency is absent.

### 8.2. Configure Only When a Class Does Not Exist

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingClass("com.example.legacy.LegacyClient")
public class DefaultClientConfiguration {

    @Bean
    public Client defaultClient() {
        return new DefaultClient();
    }
}
```

The configuration is only processed when the specified class is not on the classpath.

This is useful when a library has multiple integrations and wants to select an implementation based on the dependencies present in the build.

### 8.3. Having a Dependency Does Not Mean a Bean Exists

`@ConditionalOnClass` only checks the classpath. It does not confirm that the library is configured properly, that a bean from the library has been created, that a connection to an external service succeeds, or that the business feature is usable.

If you need to check whether a bean has been registered, look at `@ConditionalOnBean` or an appropriate condition. If you need to check connection status, that is a health/readiness or startup validation concern and should not be stuffed into a classpath condition.

## 9. `@ConditionalOnProperty`: Configuration-Based Conditions

This is one of the most common conditions in Spring Boot.

Example:

```yaml
app:
  notification:
    enabled: true
    mode: email
```

Configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "enabled",
        havingValue = "true"
)
public class NotificationConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new EmailNotificationSender();
    }
}
```

When `app.notification.enabled=true`, the bean is registered. When the property has another value, the condition does not match.

### 9.1. Meaning of the Attributes

| Attribute | Meaning |
|---|---|
| `prefix` | Common prefix of the property |
| `name` | Name of the property to check |
| `havingValue` | Specific value that must match |
| `matchIfMissing` | Whether to match if the property does not exist |

Example:

```java
@ConditionalOnProperty(
        prefix = "app.feature",
        name = "audit",
        havingValue = "enabled",
        matchIfMissing = false
)
```

The condition only matches when the property has the value `enabled`; if the property is missing, the condition does not match.

If `havingValue` is not specified, the default rule of `@ConditionalOnProperty` is that the property must exist and its value must not be the string `false` (case-insensitive according to the comparison rules). Therefore, if the property has the value `anything`, the default condition can still match. When you want an explicit boolean, set `havingValue = "true"`.

### 9.2. Feature Toggle Example

```yaml
app:
  feature:
    audit: true
```

```java
@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.feature",
            name = "audit",
            havingValue = "true"
    )
    public AuditService auditService() {
        return new AuditService();
    }
}
```

Can be toggled via command line:

```bash
java -jar demo.jar --app.feature.audit=true
```

Or via an environment variable on Linux/macOS:

```bash
APP_FEATURE_AUDIT=true java -jar demo.jar
```

### 9.3. Note on Collection Properties

`@ConditionalOnProperty` is not suitable for checking the existence of an indexed collection property, such as `app.servers[0]`. In such situations, the property may be bound, yet the condition may not detect it in the way the author expects. If you need to check complex collections, use a custom condition or an appropriate binding/validation mechanism.

## 10. `@ConditionalOnBean`, `@ConditionalOnMissingBean`, and `@ConditionalOnSingleCandidate`

This group of conditions is especially important in auto-configuration.

### 10.1. Register Only When a Matching Bean Already Exists

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnBean(DataSource.class)
public class JdbcFeatureConfiguration {

    @Bean
    public JdbcReportRepository jdbcReportRepository(DataSource dataSource) {
        return new JdbcReportRepository(dataSource);
    }
}
```

The configuration only matches if the container has a bean matching `DataSource` at the time the condition is evaluated.

This condition checks bean definition information observable at processing time; it does not mean Spring must initialize and successfully connect to the database before the condition matches.

### 10.2. Register a Default Bean Only If No User Bean Exists

```java
@Configuration(proxyBeanMethods = false)
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock systemClock() {
        return Clock.systemUTC();
    }
}
```

If the application has already registered a bean matching type `Clock` before the condition is evaluated, the default bean is not registered. If no matching bean exists yet, Spring can register `systemClock`.

This is the common pattern of Spring Boot auto-configuration: **provide a default while allowing the application to replace it with its own bean**.

### 10.3. Single Candidate Condition

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnSingleCandidate(DataSource.class)
public class SingleDataSourceConfiguration {

    @Bean
    public DatabaseInspector databaseInspector(DataSource dataSource) {
        return new DatabaseInspector(dataSource);
    }
}
```

This condition matches when there is a single matching candidate, or when there is a candidate prioritized according to the corresponding rules (such as primary) so that the choice is unambiguous.

It is useful when a configuration needs a single dependency and wants to be active only when a suitable candidate can be determined.

### 10.4. Timing and Registration Order Matter Greatly

Suppose there are two configurations:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultClockConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock defaultClock() {
        return Clock.systemUTC();
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class CustomClockConfiguration {

    @Bean
    public Clock customClock() {
        return Clock.systemDefaultZone();
    }
}
```

If the default configuration's condition is evaluated **before** the custom bean definition is registered, it may see that no `Clock` exists yet and register the default bean. When the custom definition appears later, the application may end up with two beans of the same type and single-bean injection becomes ambiguous.

This is why Spring Boot auto-configuration has ordering rules and why conditions need to be used in the right context. `@ConditionalOnMissingBean` is primarily designed for auto-configuration, where user configuration is processed before auto-configuration under the normal bootstrap mechanism.

You should not arbitrarily place bean-based conditions in independent configurations and assume all beans across the entire application have already been registered.

## 11. `@Profile` Is Also a Conditional

`@Profile` allows restricting beans/configurations based on the currently active profiles.

Example:

```java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
public class DevelopmentConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
public class ProductionConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new EmailNotificationSender();
    }
}
```

When the `dev` profile is active, the development configuration is registered. When the `prod` profile is active, the production configuration is registered.

Activating a profile:

```bash
java -jar demo.jar --spring.profiles.active=dev
```

Or via an environment variable:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar demo.jar
```

An application can have multiple active profiles at the same time. If both `dev` and `prod` are active, both configurations can be processed together; if they register the same bean name, a name collision may occur. Profiles do not guarantee by default that only a single profile is active.

`@Profile` is implemented on top of the `@Conditional` mechanism. It is a way to declare a profile-based condition, not a lifecycle callback.

## 12. `@ConditionalOnWebApplication` and Environment Conditions

Spring Boot can distinguish web applications from non-web applications.

Example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication
public class WebFeatureConfiguration {

    @Bean
    public RequestAuditFilter requestAuditFilter() {
        return new RequestAuditFilter();
    }
}
```

The configuration is only applied when Spring Boot identifies the environment as a matching web application.

If you want it to apply only in a non-web application:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
public class ConsoleFeatureConfiguration {

    @Bean
    public ConsoleReporter consoleReporter() {
        return new ConsoleReporter();
    }
}
```

Some related annotations:

- `@ConditionalOnWebApplication(type = ...)`: distinguishes among supported web environment types.
- `@ConditionalOnNotWebApplication`: not a web application.
- `@ConditionalOnJava`: restricts by Java version.
- `@ConditionalOnResource`: checks for a resource.
- `@ConditionalOnExpression`: uses a SpEL expression.
- `@ConditionalOnCloudPlatform`: conditions based on the detected cloud platform.

Environment conditions rely on information available during bootstrap. They do not replace checking server readiness or the health of an external service after the application is running.

## 13. `@ConditionalOnExpression` and When to Avoid It

You can use SpEL:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${app.feature.audit:false}")
public class ExpressionAuditConfiguration {
    // ...
}
```

This annotation is useful when an expression needs to combine several configuration values or simple expressions.

However, do not use SpEL for every condition. If you are only checking a single boolean property, `@ConditionalOnProperty` is easier to read and diagnose.

SpEL expressions may be evaluated during the configuration phase when many beans have not been created yet. You should not write expressions that assume business beans are ready or that cause side effects.

## 14. How Does Spring Boot Auto-Configuration Use Conditions?

Spring Boot auto-configuration is a set of conditional configurations aimed at reducing manual configuration.

For example, when the appropriate web dependency is on the classpath and the application is a web application, Boot can automatically register the foundational beans needed for the web stack. When the user has declared a replacement bean, the corresponding auto-configuration can back off.

An illustrative configuration:

```java
@AutoConfiguration
@ConditionalOnClass(MailClient.class)
public class MailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public MailClient mailClient(MailProperties properties) {
        return new MailClient(properties.host(), properties.port());
    }
}
```

This example illustrates a custom auto-configuration. To use it, the project needs the `MailClient` class and the auto-configuration registration mechanism appropriate for the Spring Boot version. In a Boot 3 library, auto-configuration classes are typically listed in the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

That file contains the fully qualified names of auto-configuration classes, one class per line:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
```

Spring Boot uses an import selector to discover the declared auto-configurations and then processes their corresponding conditions.

### 14.1. Three Commonly Combined Conditions

An auto-configuration can combine:

```java
@AutoConfiguration
@ConditionalOnClass(MailClient.class)
@ConditionalOnProperty(
        prefix = "app.mail",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class MailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MailClient.class)
    public MailClient mailClient() {
        return new MailClient();
    }
}
```

Meaning:

1. Only consider the configuration when the mail library class is on the classpath.
2. Only enable the feature if the property allows it; in the example, missing the property still matches because of `matchIfMissing = true`.
3. Only create the default bean when no matching `MailClient` bean exists yet.

Conditions on classes and methods have different scopes. If a condition on the class does not match, the entire auto-configuration is skipped. If the class condition matches but a method condition does not, only that corresponding bean method is not registered.

### 14.2. Why Must Auto-Configuration Be Conditional?

If Boot always registered every default bean regardless of what the application already had, users would find it hard to replace framework components. Conditional auto-configuration creates a contract:

- The framework provides default configurations.
- The application can customize or replace them.
- Optional dependencies are not required in every build.
- Configurations only appear when the classpath, properties, and bean registry match.

This is the foundation that lets Spring Boot operate in a convention-over-configuration style while remaining extensible.

## 15. Auto-Configuration Ordering and Bean Conditions

Conditions based on the classpath or properties usually depend very little on bean registration order. However, conditions based on the bean registry can depend significantly on order.

Spring Boot provides annotations for ordering auto-configurations:

- `@AutoConfigureBefore`
- `@AutoConfigureAfter`
- `@AutoConfigureOrder`

Example:

```java
@AutoConfiguration
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
public class JdbcAuditAutoConfiguration {
    // ...
}
```

This annotation requests that the auto-configuration be ordered after the specified configuration according to Boot's ordering mechanism.

### 15.1. Ordering Is Not the Same as Bean Initialization Order

| Concept | What it controls |
|---|---|
| Auto-configuration ordering | Processing order of auto-configuration classes |
| Bean definition registration | When a definition is added to the registry |
| Dependency graph | Which bean needs to be created before another |
| `@Order` on beans | Order in corresponding collection/order-aware scenarios |
| Singleton initialization | Instance creation process during context refresh |

`@AutoConfigureAfter` does not mean every bean from the other configuration has definitely been instantiated. It orders configuration processing, helping bean-based conditions observe the appropriate definitions.

### 15.2. Why Must `@ConditionalOnMissingBean` Be Used Carefully?

Suppose a custom auto-configuration wants to provide a default bean if the user does not have one:

```java
@Bean
@ConditionalOnMissingBean(Clock.class)
Clock applicationClock() {
    return Clock.systemUTC();
}
```

This is a reasonable pattern in auto-configuration. However, if multiple independent custom configurations all use this condition, the outcome may depend on registration order and whichever definitions already exist at the time of checking.

Prefer designing auto-configurations following Boot's conventions and check ordering when a condition depends on beans.

## 16. A Condition Is Not a Continuous On/Off Bean Toggle

A common misconception is thinking `@ConditionalOnProperty` will automatically create or destroy beans whenever a property changes.

Example:

```yaml
app:
  feature:
    audit: false
```

If the condition does not match when the application context is refreshed, the `AuditService` bean is not registered from that configuration.

Later, if some component changes the property to `true` while the application is running, Spring **does not automatically re-evaluate the condition to register a new bean**.

A condition is a decision during configuration/registration, not an automatic runtime feature flag.

If you need to toggle behavior per request or based on runtime state, use an appropriate runtime mechanism:

- Read changeable properties through a configuration management service.
- Use a feature flag client.
- Use an already registered strategy/service and decide at processing time.
- Use events or a specialized refresh mechanism if the architecture supports it and bean lifecycles have been designed accordingly.

Do not use `@Conditional` to replace a feature flag that needs to change continuously after startup.

## 17. Complete Example: Toggling a Feature by Property and Allowing Default Bean Replacement

Let's create an audit feature that can be enabled/disabled by a property while allowing the application to provide its own implementation.

### 17.1. Interface

```java
package com.example.demo.audit;

public interface AuditService {
    void record(String action);
}
```

### 17.2. Default Implementation

```java
package com.example.demo.audit;

public class ConsoleAuditService implements AuditService {

    @Override
    public void record(String action) {
        System.out.println("[AUDIT] " + action);
    }
}
```

### 17.3. Auto-Configuration

```java
package com.example.demo.audit.autoconfigure;

import com.example.demo.audit.AuditService;
import com.example.demo.audit.ConsoleAuditService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditService.class)
    public AuditService auditService() {
        return new ConsoleAuditService();
    }
}
```

### 17.4. Registering the Auto-Configuration

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
com.example.demo.audit.autoconfigure.AuditAutoConfiguration
```

This is how auto-configurations are registered in the Spring Boot 3 ecosystem. If you only write an `@AutoConfiguration` class without adding it to the appropriate import mechanism, Boot will not automatically know to load that class.

### 17.5. Enabling the Feature

```yaml
app:
  audit:
    enabled: true
```

When the property condition matches and the application does not have an `AuditService` bean yet, Boot registers `ConsoleAuditService` as the `AuditService` bean.

### 17.6. Application Replacing the Default Implementation

The application can provide its own:

```java
package com.example.demo.config;

import com.example.demo.audit.AuditService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomAuditConfiguration {

    @Bean
    public AuditService auditService() {
        return action -> System.out.println("CUSTOM AUDIT: " + action);
    }
}
```

Because the custom bean is registered from user configuration through the normal flow before auto-configuration, `@ConditionalOnMissingBean(AuditService.class)` in the auto-configuration will see the matching bean and skip the default bean.

The custom bean can use a different name from the default method name, because the condition evaluates by **type `AuditService`**, not solely by name.

## 18. Custom Condition: Reading Properties and Annotation Metadata

When built-in annotations do not meet your requirements, you can write a custom condition.

Example condition checking a property and a class:

```java
package com.example.demo.condition;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class AdvancedFeatureCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        boolean enabled = context.getEnvironment()
                .getProperty("app.advanced.enabled", Boolean.class, false);

        if (!enabled) {
            return false;
        }

        try {
            context.getClassLoader()
                    .loadClass("com.example.advanced.AdvancedClient");
            return true;
        } catch (ClassNotFoundException ex) {
            return false;
        }
    }
}
```

Usage:

```java
@Configuration(proxyBeanMethods = false)
@Conditional(AdvancedFeatureCondition.class)
public class AdvancedFeatureConfiguration {
    // ...
}
```

In a real application, if you only need to check a property and the classpath, use `@ConditionalOnProperty` and `@ConditionalOnClass` instead of rewriting the logic. Custom conditions are appropriate when you need to combine multiple criteria or inspect specialized metadata.

### 18.1. Reading Annotation Attributes

`AnnotatedTypeMetadata` lets you read the annotation metadata of the class or method being checked.

For example, a condition can inspect a custom annotation attribute:

```java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(FeatureFlag.class.getName());

if (attributes == null) {
    return false;
}

String featureName = (String) attributes.get("value");
```

Then use `featureName` to look up the corresponding property. This allows a single condition to be reused across multiple configuration classes instead of hard-coding the feature name in each condition.

When writing a custom annotation, ensure the metadata is given the appropriate target and retention so Spring can read it at runtime.

## 19. Condition Evaluation Report: Why Was a Configuration Enabled or Skipped?

When an auto-configuration does not create a bean as expected, just looking at `application.yml` is often not enough. Spring Boot can provide a **Condition Evaluation Report** showing which conditions matched or did not match.

Run the application with debug:

```bash
java -jar demo.jar --debug
```

Or when running Gradle:

```bash
./gradlew bootRun --args='--debug'
```

Depending on the version and how it is run, the logs may contain an auto-configuration report section with groups:

- **Positive matches:** configurations or conditions that matched.
- **Negative matches:** configurations that did not match, along with reasons.
- **Exclusions:** excluded auto-configurations.
- **Unconditional classes:** configurations that do not depend on typical conditions.

Illustrative example:

```text
Positive matches:
   MailAutoConfiguration matched:
      - @ConditionalOnClass found required class 'MailClient'

Negative matches:
   AuditAutoConfiguration:
      - @ConditionalOnProperty (app.audit.enabled=true)
        did not find property 'enabled'
```

Exact messages depend on the version and condition. Read the reported reason instead of guessing from the class name.

### 19.1. Diagnostic Questions

When a bean does not appear, ask:

1. Was the configuration class imported or component-scanned?
2. Did the class-level condition match?
3. Was the property loaded from the right source, with the right name and profile?
4. Is the dependency class actually on the runtime classpath?
5. Did a bean-based condition see the required definition at the time of evaluation?
6. Was the auto-configuration excluded?
7. Did the bean method condition match individually?
8. Are there multiple beans of the same type or a name collision causing startup to fail after registration?

A non-matching condition can be the intended behavior by design. Not every negative match is an error.

## 20. Configuration Sources Affecting Conditions

Property-based conditions depend on the Environment. The final value may come from:

- `application.yml` or `application.properties`.
- Profile-specific configuration files.
- Configuration files outside the JAR.
- Environment variables.
- Java system properties.
- Command-line arguments.
- PropertySources added by the application or framework.

Example:

```yaml
# application.yml
app:
  audit:
    enabled: false
```

Command line:

```bash
java -jar demo.jar --app.audit.enabled=true
```

In a typical Spring Boot configuration, command-line properties have higher precedence than config data, so the condition can see the value `true`.

If the IDE runs with the `dev` profile while the JAR runs with the `prod` profile, the two runs may load different properties. Check the active profiles and actual property sources when condition results differ.

### 20.1. Placeholders and Default Properties

Configuration:

```yaml
app:
  audit:
    enabled: ${APP_AUDIT_ENABLED:false}
```

If the environment variable does not exist, the placeholder provides `false`. Therefore the condition:

```java
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
```

does not match unless a true value is provided.

This is a way to create an explicit default for a feature flag. Distinguish a placeholder default from the condition's `matchIfMissing` attribute: one supplies a property value, while the other defines how the condition reacts when the property does not exist.

## 21. Common Mistakes and Misconceptions

| Symptom or thought | What actually happens | How to handle |
|---|---|---|
| Property changes after startup, but bean does not appear | Conditions do not automatically re-run continuously | Use a runtime feature flag mechanism or an appropriate refresh architecture |
| `@ConditionalOnMissingBean` still creates default bean despite user bean | User definition was not registered when condition was evaluated, or type/qualifier did not match | Check ordering, auto-configuration, and bean type |
| `@ConditionalOnClass` matches, but cannot connect to service | Classpath only proves the class is present, not that the service works | Check configuration and connectivity separately |
| Bean method is not called | Condition did not match, so bean definition was not registered | Read the Condition Evaluation Report |
| Class-level condition false removes multiple beans | The entire configuration class is skipped | Put the condition on the bean method if you only want to condition one bean |
| Calling a business service inside a condition | Bean may not exist yet and may cause circular dependencies/side effects | Use environment, metadata, registry, or specialized conditions |
| Two active profiles cause duplicate beans | Both configurations are registered | Design mutually exclusive profiles or use appropriate naming/selection |
| `@ConditionalOnProperty` does not recognize indexed collections | Annotation is not suitable for checking indexed collections | Use a custom condition or appropriate binding logic |
| Auto-configuration is not discovered | Imports file not registered or package/module not on classpath | Check `AutoConfiguration.imports` and artifacts |
| Enabling `allow-bean-definition-overriding` to fix a condition | Only affects duplicate-name registration, does not fix condition logic | Identify the actual conditions and bean definitions |

### 21.1. A False Condition Is Not Always a Bug

If the audit feature is configured to default to false, `AuditConfiguration` not being registered is the correct result. Only when the application expects audit to work and the condition is still false should you investigate the property or phase.

### 21.2. A True Condition Does Not Guarantee Startup Success

A condition only decides whether a configuration/bean definition is accepted. The bean can still fail afterward because its constructor throws an exception, another dependency does not exist, multiple beans of the same type cause ambiguity, an init callback fails, external configuration is invalid, or a dependent service is unavailable.

Therefore, distinguish **condition match**, **bean definition registration**, **bean instantiation**, and **application readiness**.

## 22. Condition Design and Diagnostic Workflow

When adding a conditional configuration, you can follow these steps:

### Step 1 — Identify What Kind of Condition It Is

- Classpath: `@ConditionalOnClass` / `@ConditionalOnMissingClass`.
- Property: `@ConditionalOnProperty`.
- Bean registry: `@ConditionalOnBean` / `@ConditionalOnMissingBean`.
- Profile: `@Profile`.
- Web/environment: corresponding specialized conditions.
- Specific logic: custom `Condition`.

### Step 2 — Determine the Scope

Does the condition apply to the entire configuration class or only one bean method? If the whole group of beans depends on the condition together, place it on the class. If only one bean is optional, place it on the method.

### Step 3 — Determine the Phase

Does the condition need to run when parsing configuration or when registering beans? If an explicit phase is needed, implement `ConfigurationCondition`. Avoid assuming the registry already contains all beans when the condition is called.

### Step 4 — Check the Dependency Graph

If the condition skips a bean, do other beans require it via constructor injection? You may need to put a corresponding condition on the dependent group of beans, or design another default implementation.

### Step 5 — Check Ordering

If using `@ConditionalOnBean` or `@ConditionalOnMissingBean` in auto-configuration, ensure user configuration and auto-configuration are processed according to the appropriate conventions. Review `@AutoConfigureBefore` and `@AutoConfigureAfter` when needed.

### Step 6 — Observe Reports and the Registry

Use `--debug` to view the condition report. If necessary, inspect bean names/types after the context initializes successfully. Do not call business beans inside a condition for diagnostics.

### Step 7 — Distinguish Registration from Runtime Behavior

If a feature needs to be toggled on or off while the application is running, a condition is not the right tool. Choose a runtime mechanism that can change behavior without expecting Spring to re-register bean definitions.

## 23. Practice Exercises

### Exercise 1 — Property-Based Condition

Create `AuditConfiguration` with `@ConditionalOnProperty`. Run the application with `app.audit.enabled` set to `true`, `false`, and undeclared. Observe whether the bean appears in the context.

### Exercise 2 — Conditions on Class and Method

Place a condition on an entire `@Configuration` with two `@Bean` methods, then move the condition down to only one method. Compare the number of bean definitions registered when the condition is false.

### Exercise 3 — Classpath Check

Create a configuration using `@ConditionalOnClass` with a class from an optional dependency. Run with the dependency present and absent from the runtime classpath. Observe the condition report.

### Exercise 4 — Default Bean and Custom Bean

Create `@ConditionalOnMissingBean(Clock.class)` for a default bean. Then add a user configuration providing a `Clock` bean. Observe the auto-configuration backing off when the custom definition is registered in the proper order.

### Exercise 5 — Bean Registry Condition

Write a `ConfigurationCondition` in the `REGISTER_BEAN` phase that checks for a bean definition with a specific name. Try changing the configuration processing order and observe why the registry at the time the condition runs affects the result.

### Exercise 6 — Profiles

Create two configurations for `dev` and `prod`. Run with each profile individually and then enable both. Explain why profiles are not mutually exclusive by default.

### Exercise 7 — Reading the Condition Report

Run the application with `--debug`. Find one positive match and one negative match. Rewrite the reason why the condition matched or did not match in your own words.

### Exercise 8 — Distinguishing Conditions from Runtime Feature Flags

Create a bean that is only registered when `app.feature.audit=true`. After the context has started, change the property value in a Java object and observe whether the bean definition appears automatically. Then design a service that reads feature state at runtime to compare the two mechanisms.

## 24. Official References

- [Spring Framework Javadoc — Condition](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Condition.html): condition evaluation contract.
- [Spring Framework Javadoc — ConfigurationCondition](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html): parse and register phases.
- [Spring Framework Reference — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): Java configuration and bean registration.
- [Spring Boot Reference — Developing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): how to build auto-configuration and use conditions.
- [Spring Boot Reference — Auto-configuration classes](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): registering and ordering auto-configuration.

The core takeaway is that `@Conditional` decides whether a configuration or bean definition is included in the container during bootstrap. `PARSE_CONFIGURATION` and `REGISTER_BEAN` determine when a condition can observe metadata/the registry; once bean definitions are registered and the context enters runtime, conditions do not automatically re-run whenever properties or application state change. Understanding this timing helps you write extensible auto-configurations, avoid unintended registration-order dependencies, and accurately diagnose why a bean is present or absent in Spring Boot.
