# `@ConditionalOnExpression` and Limitations When Expressions Reference Beans Early

In Spring Boot, a configuration may only be activated when a certain condition is satisfied. For example, an application creates an email-sending bean only when the email feature is enabled, configures JDBC integration only when the JDBC library is present, or registers a default implementation only when the application has not provided a replacement bean.

`@ConditionalOnExpression` allows using **Spring Expression Language (SpEL)** to express a condition as an expression. This annotation is flexible because it can combine properties, boolean values, comparisons, and even reference beans in the Spring container.

That very ability to reference beans is also a major limitation: conditions are evaluated while building the application context, before all beans have initialized and completed every processing step. If an expression calls a bean, Spring may have to instantiate that bean **too early**. A prematurely created bean may not yet have had all `BeanPostProcessor`s applied, such as `@ConfigurationProperties` binding. Therefore, prefer using expressions mainly with configuration values and metadata; avoid using bean instances as a source for configuration decisions.

## 1. What Is `@ConditionalOnExpression` Used For?

The annotation belongs to the package:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
~~~

It accepts a SpEL expression. If the expression evaluates to `true`, the marked configuration or bean can be registered; if the result is `false`, Spring skips the corresponding configuration part.

Simple example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("true")
public class DemoConfiguration {

    @Bean
    DemoService demoService() {
        return new DemoService();
    }
}
~~~

In this example the condition is always true, so the configuration is considered for registering the `demoService` bean. A constant expression is for illustration only; in real code, an always-true condition normally does not need the annotation.

The condition can be placed on a configuration class:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${app.feature.audit:false}")
public class AuditConfiguration {
    // Beans belonging to the audit feature.
}
~~~

Or on a `@Bean` method:

~~~java
@Configuration(proxyBeanMethods = false)
public class IntegrationConfiguration {

    @Bean
    @ConditionalOnExpression("${app.integration.partner:false}")
    PartnerClient partnerClient() {
        return new PartnerClient();
    }
}
~~~

When a class-level condition is not satisfied, that configuration class does not contribute its beans. When a method-level condition is not satisfied, the bean declared by that method is not registered.

## 2. SpEL and Property Placeholders in Expressions

`@ConditionalOnExpression` uses SpEL to evaluate values. Spring Boot also resolves property placeholders of the form `${...}` inside the expression before evaluation.

### 2.1. Checking a Boolean Property

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${app.feature.audit:false}")
class AuditConfiguration {

    @Bean
    AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
~~~

In `application.yml`:

~~~yaml
app:
  feature:
    audit: true
~~~

The placeholder `${app.feature.audit:false}` is replaced with the property value. If the property does not exist, the default value after the colon is `false`. After resolution, SpEL evaluates the boolean expression.

### 2.2. String Comparison

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression(
        "'${app.environment:local}' == 'production'"
)
class ProductionIntegrationConfiguration {
}
~~~

In this expression:

- Single quotes wrap the placeholder value to create a SpEL string.
- The `==` operator compares the string against `production`.
- If the property is missing, the default is `local`, so the condition is false.

Configuration example:

~~~yaml
app:
  environment: production
~~~

### 2.3. Combining Conditions

SpEL supports logical operators such as `and`, `or`, and `not`:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression(
        "${app.feature.audit:false} and '${app.environment:local}' == 'production'"
)
class ProductionAuditConfiguration {
}
~~~

The expression is true only when audit is enabled and the environment is production.

For simple property conditions, `@ConditionalOnProperty` is usually easier to read and less risky. Do not pick SpEL just because you can write multiple logical operations on a single line; the more complex a condition gets, the harder it is to read, test, and diagnose.

## 3. What Is the Syntax for Referencing Beans in SpEL?

In SpEL, you can reference a bean in the `BeanFactory` using the `@beanName` notation:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("@featureSwitches.auditEnabled")
class AuditConfiguration {
}
~~~

Or invoke a method:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("@featureSwitches.isAuditEnabled()")
class AuditConfiguration {
}
~~~

Suppose the application has the bean:

~~~java
@Component("featureSwitches")
public class FeatureSwitches {

    public boolean isAuditEnabled() {
        return true;
    }
}
~~~

> When the expression is evaluated, SpEL needs to resolve the name `featureSwitches` through the `BeanFactory` and call the method on the instance. That can cause Spring to instantiate this bean right during condition evaluation.

Here is the difference between the two kinds of expressions:

~~~text
Property expression:
    ${app.feature.audit:false}
             |
             v
       Environment
             |
             v
        true / false

Bean expression:
    @featureSwitches.isAuditEnabled()
             |
             v
       BeanFactory resolves bean
             |
             v
       May instantiate bean early
             |
             v
       Invoke method on instance
~~~

Referencing a bean does not merely read bean definition metadata. It requires a **bean instance** to evaluate the expression. Therefore, do not use a business bean as a configuration switch for another configuration.

## 4. When Is the Condition Evaluated?

Spring processes configuration classes and conditions while building the application context. These decisions happen before all regular singletons are initialized and before the application finishes starting up.

General flow:

~~~text
SpringApplication.run(...)
        |
        v
Prepare Environment and BeanFactory
        |
        v
Read and parse configuration classes
        |
        v
Evaluate @Conditional conditions
        |
        v
Register matching bean definitions
        |
        v
Register and run BeanFactory/BeanPostProcessors
        |
        v
Instantiate eager singletons
        |
        v
Context refresh completes
        |
        v
Application ready
~~~

The diagram is a simplified sequence; Spring has finer-grained configuration processing and processor registration steps. The important point is that **conditions do not wait for the whole application to run steadily before being evaluated**.

If a condition references a bean, the `BeanFactory` must supply an instance so SpEL can access its property/method. Creating that instance can happen while configuration is still being parsed and registered.

## 5. Why Is Referencing Beans Early Dangerous?

Spring Boot warns that referencing beans in `@ConditionalOnExpression` has significant limitations. The bean is instantiated very early and may not be eligible for processing by all `BeanPostProcessor`s.

### 5.1. `BeanPostProcessor`s May Not Be Fully Applied

Spring uses `BeanPostProcessor`s to add behavior to beans, such as processing annotations, creating AOP proxies, or supporting configuration mechanisms. A bean instantiated before all processors are registered may miss certain processing steps.

A notable example is `@ConfigurationProperties` binding. If a bean is instantiated early because a condition expression references it, the bean might not yet have been processed by the processor performing binding as expected. As a result, properties remain at their default values or an incomplete state at the moment the condition reads the bean.

Do not assume every early-referenced bean definitely loses every `BeanPostProcessor`. The issue depends on registration order and processor types; the risk lies in not being able to guarantee the bean is processed as completely as one initialized at the proper stage.

### 5.2. Calling a Method While State Is Incomplete

Suppose:

~~~java
@Component
@ConfigurationProperties(prefix = "app.features")
public class FeatureSwitches {
    private boolean auditEnabled;

    public boolean isAuditEnabled() {
        return auditEnabled;
    }

    public void setAuditEnabled(boolean auditEnabled) {
        this.auditEnabled = auditEnabled;
    }
}
~~~

And:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("@featureSwitches.auditEnabled")
class AuditConfiguration {
}
~~~

If `featureSwitches` is instantiated early before configuration-properties binding is applied, the expression may read the default value `false` even though the configuration file sets `app.features.audit=true`. The condition then decides based on an unbound state.

This is an example of a timing risk, not an inevitable result in every version or setup. The right approach is for the condition to read properties directly from `Environment` using `@ConditionalOnProperty` or a custom `Condition` that does not instantiate beans.

### 5.3. Triggering Early Initialization of an Entire Dependency Chain

A referenced bean may depend on many other beans:

~~~text
@ConditionalOnExpression("@featureSwitches.enabled")
                    |
                    v
             FeatureSwitches
                    |
                    v
              RemoteConfigClient
                    |
                    v
               HTTP client
                    |
                    v
         connection config / credentials
~~~

Just to evaluate a single condition, Spring may have to initialize an entire chain of dependencies. This can:

- Slow down startup.
- Trigger network connections or I/O operations too early.
- Cause an external service configuration error to fail the context before main configuration completes.
- Make initialization order unpredictable.

A condition should be a lightweight decision based on configuration and metadata, not a place to run business logic or initialize external clients.

### 5.4. Creating Circular Dependencies or Depending on Unregistered Configuration

For example, the `featureSwitches` bean might itself need a service registered only inside `AuditConfiguration`, while `AuditConfiguration` is activated only when the expression calls `featureSwitches`. This is a circular relationship:

~~~text
AuditConfiguration needs condition evaluation
             |
             v
   Create FeatureSwitches
             |
             v
 FeatureSwitches needs AuditService
             |
             v
 AuditService only exists if AuditConfiguration is enabled
~~~

Spring cannot resolve a conditional decision that depends on a bean that the condition itself enables. The result can be a missing bean error, a bean creation error, or a context initialization failure.

Additionally, conditions are evaluated when part of the configuration may not yet be registered. Do not reference beans declared only in a configuration that has not been processed at that time.

### 5.5. Conditions Are Not Runtime Feature Toggles

`@ConditionalOnExpression` decides configuration/bean definitions during context creation. It does not continuously watch the expression after the application is running.

If a property changes from `false` to `true` after the context has refreshed, a skipped configuration does not suddenly appear just because of the new value. If you need to toggle features at runtime, check feature flags inside services or use a dedicated refresh/configuration mechanism with clear semantics.

## 6. Preferred Approach: `@ConditionalOnProperty` for Configuration Conditions

If the condition only depends on properties, use `@ConditionalOnProperty`:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.feature",
        name = "audit",
        havingValue = "true"
)
public class AuditConfiguration {

    @Bean
    AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
~~~

Configuration:

~~~yaml
app:
  feature:
    audit: true
~~~

Spring checks the property in `Environment`, without needing to instantiate a `FeatureSwitches` bean to read this flag.

Important attributes:

- `prefix`: property prefix.
- `name`: one or more property names to check.
- `havingValue`: value that must match.
- `matchIfMissing`: whether a missing property counts as satisfying the condition.

If `havingValue` is omitted, the default condition typically matches when the property is present and its value is not the string `false` (case-insensitive). For clear behavior, especially with boolean feature flags, set `havingValue = "true"`.

### 6.1. Default Value When Property Is Missing

~~~java
@ConditionalOnProperty(
        prefix = "app.feature",
        name = "audit",
        havingValue = "true",
        matchIfMissing = false
)
~~~

With this configuration, if the property is missing, the condition does not match. You can set `matchIfMissing = true` if the design requires enabling by default when undeclared; choose the policy explicitly instead of relying on unexplained defaults.

### 6.2. Multiple Properties

~~~java
@ConditionalOnProperty(
        prefix = "app.integration",
        name = {"partner-enabled", "credentials-present"},
        havingValue = "true"
)
~~~

When declaring multiple names, property conditions are checked with an AND relationship: all must be satisfied. If you need OR logic or complex expressions, consider nested configurations, a custom `Condition`, or SpEL only when truly necessary; do not switch to bean references to do it.

Note that `@ConditionalOnProperty` is not suitable for reliably checking the existence of collection/indexed properties such as `app.values[0]`. For complex configuration structures, a custom `Condition` reading `Environment` or appropriate binding metadata can be clearer.

## 7. Use Specialized Conditions Instead of One Catch-All Expression

Spring Boot provides many condition annotations that directly describe intent:

| Need | Suitable annotation | What it checks |
|---|---|---|
| Toggle property | `@ConditionalOnProperty` | Value in `Environment` |
| Library/class on classpath | `@ConditionalOnClass` | Presence of class |
| Absence of specific class | `@ConditionalOnMissingClass` | Class does not exist |
| Matching bean already exists | `@ConditionalOnBean` | Bean definition/candidate in `BeanFactory` |
| No matching bean exists yet | `@ConditionalOnMissingBean` | No bean satisfies condition |
| Servlet or Reactive application | `@ConditionalOnWebApplication` | Web application type |
| Non-web application | `@ConditionalOnNotWebApplication` | Application type |
| Active profile | `@Profile` | Active profiles |

Example checking for a present dependency:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.audit.AuditClient")
class VendorAuditConfiguration {
    // Configuration only makes sense when client library is present.
}
~~~

Example providing a default implementation only if the application has no bean yet:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultPaymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

`@ConditionalOnBean` and `@ConditionalOnMissingBean` are designed to evaluate bean presence in configuration rather than calling methods on a bean instance. For auto-configuration, configuration ordering and conditions also matter: Boot provides auto-configuration ordering mechanisms so foundational beans can be registered before conditions depending on them are evaluated.

## 8. When Is `@ConditionalOnExpression` Truly Needed?

`@ConditionalOnExpression` is helpful when a concise SpEL expression expresses logic that specialized annotations do not express conveniently, such as combining multiple property values:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression(
        "${app.features.audit:false} and '${app.region:local}' matches 'prod|staging'"
)
class RegionalAuditConfiguration {
}
~~~

This expression only uses property values from `Environment`. No bean instance needs to be created to evaluate the condition.

Before using it, consider:

1. Can it be written with `@ConditionalOnProperty`?
2. Can it be split into multiple specialized conditions for clearer readability?
3. Does the expression depend on unexpected properties or lack defaults?
4. Is the result guaranteed to be boolean?
5. Can both the true and false branches be tested independently?

Avoid long expressions, multiple method calls, or business logic. A condition is a bean registration decision, not a replacement for the service layer.

## 9. For Complex Conditions, Write a Custom `Condition`

When logic cannot be expressed cleanly with built-in annotations, implement `Condition`. A custom condition receives `ConditionContext` and `AnnotatedTypeMetadata`, allowing it to read `Environment` and configuration metadata.

Example checking two properties without looking up a bean instance:

~~~java
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class ProductionAuditCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String environment = context.getEnvironment()
                .getProperty("app.environment", "local");
        boolean auditEnabled = context.getEnvironment()
                .getProperty("app.feature.audit", Boolean.class, false);

        return auditEnabled && "production".equals(environment);
    }
}
~~~

Attach the condition:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(ProductionAuditCondition.class)
class ProductionAuditConfiguration {
}
~~~

A custom `Condition` lets you give the logic a clear name and test it separately. Inside `matches()`, prefer reading `Environment`, classpath, and metadata/bean definitions through the appropriate APIs. **Do not call `context.getBeanFactory().getBean(...)` to retrieve bean instances**; doing so repeats the exact early-initialization risk covered in this lesson.

If a condition needs to know whether a bean definition exists, use the appropriate `BeanFactory`/registry metadata APIs and pay attention to the phase in which the condition is evaluated. You do not need to instantiate an object just to know a bean definition exists.

## 10. Comparing Ways to Express the Same Intent

Suppose the requirement is to register `AuditPublisher` only when `app.feature.audit=true`.

**Recommended approach:**

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.feature",
        name = "audit",
        havingValue = "true"
)
class AuditConfiguration {
    @Bean
    AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
~~~

**Works, yet unnecessary:**

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${app.feature.audit:false}")
class AuditConfiguration {
}
~~~

**Approach to avoid:**

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("@featureSwitches.isAuditEnabled()")
class AuditConfiguration {
}
~~~

In the last approach, the condition needs a bean instance to invoke a method. If that bean has binding, AOP, dependencies, or initialization side effects, the result can depend on startup order. The first two approaches rely on properties and therefore do not need to initialize a switch bean.

## 11. If You Need to Toggle Features While the Application Is Running

Conditions are not a dynamic feature flag mechanism. If the requirement is an operation whose result can change over time, keep the bean always registered and check the state at the moment business logic executes:

~~~java
@Service
public class AuditService {
    private final FeatureFlagService featureFlags;
    private final AuditPublisher publisher;

    public AuditService(
            FeatureFlagService featureFlags,
            AuditPublisher publisher) {
        this.featureFlags = featureFlags;
        this.publisher = publisher;
    }

    public void record(AuditEvent event) {
        if (!featureFlags.isEnabled("audit")) {
            return;
        }
        publisher.publish(event);
    }
}
~~~

In this design, `FeatureFlagService` is a normal runtime dependency. Every time `record()` is called, the service reads the current state according to the feature flag provider's semantics. Caching, refreshing, and value synchronization are handled by the feature flag system.

If you only use `@ConditionalOnProperty` or `@ConditionalOnExpression`, the bean definition is decided when the context is built. Changing properties afterward does not automatically register or remove beans from the context. Changing context structure requires an explicitly designed refresh/restart mechanism; do not expect condition annotations to watch for changes automatically.

## 12. Testing Conditions and Startup Behavior

Configuration conditions should be tested for both enabled and disabled branches. With Spring Boot, `ApplicationContextRunner` is a useful tool to test auto-configuration or conditional configuration without starting the whole application.

Example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AuditConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(AuditConfiguration.class);

    @Test
    void registersAuditPublisherWhenEnabled() {
        contextRunner
                .withPropertyValues("app.feature.audit=true")
                .run(context ->
                        assertThat(context).hasSingleBean(AuditPublisher.class));
    }

    @Test
    void skipsAuditPublisherWhenDisabled() {
        contextRunner
                .withPropertyValues("app.feature.audit=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditPublisher.class));
    }
}
~~~

The example assumes `AuditConfiguration` uses `@ConditionalOnProperty` as in the previous section and `AuditPublisher` can be instantiated independently.

With `@ConditionalOnExpression`, you can write similar tests to check properties, string comparisons, and logical operators. If an expression references a bean, additionally check initialization order and related `BeanPostProcessor`s; however, the better fix is usually removing the bean reference from the condition.

### Checking SpEL Errors

Common errors:

- Invalid SpEL syntax in the expression.
- Missing placeholder without an appropriate default value.
- Strings not wrapped in quotes properly.
- Expression returning a type that cannot convert to boolean.
- Referenced bean does not exist or cannot be instantiated.

When an error occurs, check the root cause in startup logs. Do not assume every invalid expression evaluates to `false`; parse or resolution errors can cause context construction to fail.

## 13. Diagnosing Conditions in Spring Boot

Spring Boot can print the **Condition Evaluation Report** when running the application with `--debug` or configuring `debug=true`:

~~~properties
debug=true
~~~

The report shows whether auto-configurations/conditions matched or did not match and usually includes reasons. This helps answer:

- Was the configuration considered?
- Was the property condition satisfied?
- Was the required class on the classpath?
- Was the required bean registered conditionally?
- Was the auto-configuration excluded?

For `@ConditionalOnExpression` on application configurations, startup logs and SpEL errors can provide information about expressions that fail to evaluate. If you need to confirm which beans were registered, you can inspect `ApplicationContext` or the Actuator `conditions`/`beans` endpoints when enabled and properly secured.

The condition report does not replace testing. A matched condition only indicates configuration criteria were met; a bean can still fail during initialization due to dependencies or external connections.

## 14. Principles for Safe Usage

1. Use `@ConditionalOnExpression` for concise SpEL expressions based on simple properties/values when specialized annotations cannot express them directly.
2. Use `@ConditionalOnProperty` for feature flags and boolean configurations; declare defaults and `havingValue` clearly.
3. Use `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, and `@Profile` for their intended purposes instead of stuffing everything into a single expression.
4. Avoid referencing `@beanName` inside conditions. Beans may be instantiated early, before all `BeanPostProcessor`s are ready.
5. Do not call business services, access databases, or contact network services to decide whether to register a configuration.
6. If complex conditional logic is needed, write a custom `Condition` based on `Environment`, classpath, and metadata; do not call `getBean()` in `matches()`.
7. If you need runtime feature toggles, check flags inside services at operation time instead of using conditions to dynamically create/remove beans.
8. Test true, false, missing property, and replacement bean configurations.

`@ConditionalOnExpression` allows expressing flexible configuration conditions with SpEL, yet remember it is evaluated while Spring is building the application context. An expression reading only properties from `Environment` is usually predictable; an expression invoking `@beanName` can force Spring to create beans prematurely during configuration and leave them incompletely processed by `BeanPostProcessor`s. For most application configurations, prefer specialized or property-based conditions so bean registration remains clear, stable, and easy to test.
