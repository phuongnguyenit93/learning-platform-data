# Outer class conditions and per-bean conditions

In Spring Boot, an auto-configuration typically registers multiple related beans. Some beans are needed only when an integration library is present, some only when a property is enabled, and default beans should be created only if the application has not already provided its own implementation.

Spring Boot allows placing conditions at two important scopes:

- **Condition on the configuration class**: decides whether the entire configuration is processed. If the condition is not met, the @Bean methods and configurations inside that class are not brought into the context through that configuration branch.
- **Condition on an individual @Bean method**: decides individually whether the bean declared by that method is registered. Other beans in the same configuration class can still be registered.

Understanding scope properly helps avoid two common design mistakes: disabling an entire group of configurations just because one optional bean is unnecessary, or accidentally registering part of a configuration when the integration's overall prerequisites are not met.

## 1. Starting from an auto-configuration with multiple beans

Suppose a library provides integration for a partner system. It might register:

- A PartnerClient to call the partner API.
- A PartnerService using that client.
- A PartnerHealthIndicator to check integration health.
- A PartnerMetricsCollector to collect metrics if the user enables the feature.

Not every application uses all components. We want to:

1. Enable the integration only when the client library is on the classpath and the overall property allows it.
2. Allow the application to replace the default PartnerService.
3. Create the health indicator only when health integration is enabled.
4. Create the metrics collector only when metrics are enabled.

A conceptual view:

~~~text
PartnerAutoConfiguration
        │
        ├── Overall conditions for the entire configuration
        │       ├── Is SDK on the classpath?
        │       └── partner.enabled = true?
        │
        ├── PartnerService
        │       └── No application-provided bean yet?
        │
        ├── PartnerHealthIndicator
        │       └── partner.health.enabled = true?
        │
        └── PartnerMetricsCollector
                └── partner.metrics.enabled = true?
~~~

The shared conditions placed on the configuration class form the **outer gate**. Conditions on `@Bean` methods form **individual gates** for each bean.

## 2. Conditions at the configuration class level

In Spring Boot 3, an auto-configuration is usually declared with **@AutoConfiguration**. This annotation acts as a configuration class discovered by Boot via the auto-configuration registration mechanism.

For example:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
public class PartnerAutoConfiguration {

    // @Bean methods belonging to this configuration.
}
~~~

The condition on the class requires the **partner.enabled** property to have the value true. If the property does not exist or has another value, the configuration class is not applied under this condition.

If the configuration class is excluded, the @Bean methods inside are not processed to register beans from that configuration. This has a broader scope of impact than a condition placed on a single method.

### 2.1. An outer condition can control an entire group of beans

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
public class PartnerAutoConfiguration {

    @Bean
    PartnerClient partnerClient(PartnerProperties properties) {
        return new PartnerClient(properties.getBaseUrl());
    }

    @Bean
    PartnerService partnerService(PartnerClient client) {
        return new PartnerService(client);
    }

    @Bean
    PartnerHealthIndicator partnerHealthIndicator(PartnerClient client) {
        return new PartnerHealthIndicator(client);
    }
}
~~~

This example illustrates an integration in which all three beans need the SDK and only operate when partner.enabled is turned on. Class-level conditions avoid registering the entire group when the SDK is absent or the feature is turned off.

If any class-level condition is not satisfied, this entire configuration is skipped. None of PartnerClient, PartnerService, or PartnerHealthIndicator is registered from this class.

### 2.2. Multiple conditions on the same class are combined

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
@ConditionalOnProperty(
        prefix = "partner",
        name = "mode",
        havingValue = "remote"
)
public class PartnerAutoConfiguration {
    // ...
}
~~~

All conditions must be satisfied for the configuration to apply. The logic can be read as:

~~~text
PartnerClient is present
        AND
partner.enabled = true
        AND
partner.mode = remote
        │
        ▼
Apply PartnerAutoConfiguration
~~~

If one condition is not satisfied, the entire configuration class is skipped. This is appropriate when all conditions are mandatory requirements for every bean in the configuration.

### 2.3. When should conditions be placed at the class level?

Place conditions at the class level when:

- Every bean in the configuration needs the same optional library.
- Every bean only makes sense when an overall feature is enabled.
- A configuration only suits a specific application type or environment.
- You want to skip an entire auto-configuration group when baseline conditions are not met.

For example, if every bean in PartnerAutoConfiguration calls PartnerClient, the absence of the SDK is a valid reason to skip the entire class.

Do not place overly broad conditions if the same class also contains beans independent of that condition. In that case, a class-level condition can unintentionally block beans that are still useful.

## 3. Conditions on individual @Bean methods

A condition on a @Bean method decides only the bean created by that method.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class PartnerFeatureAutoConfiguration {

    @Bean
    PartnerService partnerService() {
        return new PartnerService();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "partner.health",
            name = "enabled",
            havingValue = "true"
    )
    PartnerHealthIndicator partnerHealthIndicator() {
        return new PartnerHealthIndicator();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "partner.metrics",
            name = "enabled",
            havingValue = "true"
    )
    PartnerMetricsCollector partnerMetricsCollector() {
        return new PartnerMetricsCollector();
    }
}
~~~

In this example:

- PartnerService is always declared if the configuration class is applied.
- PartnerHealthIndicator is registered only when the health property is enabled.
- PartnerMetricsCollector is registered only when the metrics property is enabled.

If partner.metrics.enabled is false, only the metrics bean is skipped. PartnerService and PartnerHealthIndicator can still exist if their own conditions are satisfied.

### 3.1. Scope of impact of a method condition

~~~text
PartnerFeatureAutoConfiguration is applied
        │
        ├── partnerService()
        │       └── No method condition
        │               └── Register bean
        │
        ├── partnerHealthIndicator()
        │       └── health.enabled = true?
        │               ├── Yes → Register bean
        │               └── No → Skip this bean
        │
        └── partnerMetricsCollector()
                └── metrics.enabled = true?
                        ├── Yes → Register bean
                        └── No → Skip this bean
~~~

This is the core difference: a method-level condition does not automatically disable the remaining @Bean methods in the same class.

### 3.2. When should conditions be placed on methods?

Place conditions on individual @Bean methods when:

- Beans in the same configuration have different requirements.
- A bean is an add-on feature that can be toggled independently.
- Only one bean depends on another bean.
- A default bean should exist only if the user has not provided one themselves.
- You want to avoid letting a minor property disable an entire group of beans.

Method-level conditions make configurations more modular, since each bean can have its own registration policy.

## 4. Direct comparison of class-level and method-level

| Criterion | Condition on configuration class | Condition on @Bean method |
|---|---|---|
| Scope | Entire configuration class and configurations processed from it | Only the bean declared by that method |
| When unmatched | Skips configuration at the class level | Skips the corresponding bean |
| Other @Bean methods | Not registered from the excluded configuration | Can still be registered |
| Suitable case | Shared baseline conditions for every bean in the group | Specific conditions for individual features/beans |
| Example | SDK mandatory for the entire integration | Enable metrics only when metrics property is on |
| Risk when misplaced | Disables too many beans | Registers dependent bean while baseline conditions are unprotected |

There is no rule that class-level is always better or method-level is always better. Place each condition at the smallest scope that still expresses the configuration requirement accurately.

## 5. Combining class-level and method-level conditions

A practical auto-configuration often uses both. Outer class conditions confirm the integration can operate; per-bean conditions decide which parts get registered.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
public class PartnerAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    PartnerService partnerService(PartnerClient client) {
        return new PartnerService(client);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "partner.health",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    PartnerHealthIndicator partnerHealthIndicator(PartnerClient client) {
        return new PartnerHealthIndicator(client);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "partner.metrics",
            name = "enabled",
            havingValue = "true"
    )
    PartnerMetricsCollector partnerMetricsCollector(PartnerClient client) {
        return new PartnerMetricsCollector(client);
    }
}
~~~

In the example:

1. The SDK must be on the classpath.
2. partner.enabled must be true.
3. Default PartnerService is created only if no matching bean exists yet.
4. Health indicator and metrics collector are enabled independently according to their properties.

If the class-level conditions are not satisfied, no bean from this configuration is registered, regardless of what values method-level properties have.

If the class-level conditions are satisfied, Spring proceeds to evaluate each @Bean method's conditions.

## 6. Where should @ConditionalOnMissingBean usually be placed?

A common goal of auto-configuration is to provide default beans while letting the application replace them. This is the classic use case for **@ConditionalOnMissingBean**.

For example:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

If the application already registered GreetingService, the default bean is not created. If not, Boot provides DefaultGreetingService.

### 6.1. Why is @ConditionalOnMissingBean usually placed on each method?

Suppose a configuration class provides three beans:

- GreetingService.
- GreetingFormatter.
- GreetingMetrics.

The application wants to provide its own GreetingService while still using the default formatter and metrics.

If you write:

~~~java
@AutoConfiguration
@ConditionalOnMissingBean(GreetingService.class)
public class GreetingAutoConfiguration {

    @Bean
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new DefaultGreetingFormatter();
    }

    @Bean
    GreetingMetrics greetingMetrics() {
        return new DefaultGreetingMetrics();
    }
}
~~~

When the application has its own GreetingService, the **entire GreetingAutoConfiguration** is excluded. Default formatter and metrics are not registered either, even though they did not need to back off.

Usually, the right intent is:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }

    @Bean
    @ConditionalOnMissingBean(GreetingFormatter.class)
    GreetingFormatter greetingFormatter() {
        return new DefaultGreetingFormatter();
    }

    @Bean
    @ConditionalOnMissingBean(GreetingMetrics.class)
    GreetingMetrics greetingMetrics() {
        return new DefaultGreetingMetrics();
    }
}
~~~

When the application provides its own GreetingService, only the default GreetingService bean is skipped. The other two beans can still be registered.

### 6.2. Class-level @ConditionalOnMissingBean still has valid cases

If the entire configuration is a complete alternative implementation and none of the beans in the group should be used when the application already provides another integration, a class-level condition can be appropriate.

For example, a configuration containing only the internal beans of a default adapter; when the application has a higher-level adapter, the entire default group no longer makes sense. In that case, a class-level condition expresses the intent well.

However, when beans can be customized independently, method-level conditions are usually clearer and more flexible.

## 7. Evaluation order and limitations of @ConditionalOnBean/@ConditionalOnMissingBean

Not every condition checks only the classpath or properties. Some conditions inspect **bean definitions already registered in the context at the time the condition is evaluated**.

Specifically:

- **@ConditionalOnBean** checks whether a matching bean already exists.
- **@ConditionalOnMissingBean** checks whether no matching bean exists yet.

These conditions depend on the bean definitions Spring has processed up to that point. Thus, auto-configuration ordering can affect the outcome.

### 7.1. Example of a default bean depending on another bean

~~~java
@AutoConfiguration
public class PartnerMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(PartnerService.class)
    @ConditionalOnMissingBean(PartnerMetricsCollector.class)
    PartnerMetricsCollector partnerMetricsCollector(
            PartnerService partnerService) {
        return new DefaultPartnerMetricsCollector(partnerService);
    }
}
~~~

The metrics bean is registered only when:

1. PartnerService has been recognized as a matching bean.
2. No PartnerMetricsCollector has been provided by the application yet.

If PartnerService is registered by another auto-configuration, the processing order of the two auto-configurations must be designed appropriately so the condition sees the required bean definition.

### 7.2. Using @AutoConfiguration(after = ...)

Spring Boot supports relative auto-configuration ordering:

~~~java
@AutoConfiguration(after = PartnerCoreAutoConfiguration.class)
public class PartnerMetricsAutoConfiguration {
    // ...
}
~~~

This requests that PartnerCoreAutoConfiguration be processed before PartnerMetricsAutoConfiguration in auto-configuration order. When using bean-based conditions, such ordering allows the condition to see the definition already registered by the earlier configuration.

Related attributes include:

- **before**: process this auto-configuration before another configuration.
- **after**: process after another configuration.
- **beforeName/afterName**: use class names when you do not want to reference classes directly.

This is ordering between auto-configurations, not a general mechanism for ordering every bean across the entire application.

### 7.3. Why should @ConditionalOnBean not be used arbitrarily at the class level?

If you put @ConditionalOnBean on a configuration class, the entire class depends on beans recognized at the moment the class condition is evaluated. If the required bean is registered by a configuration processed later, the condition may not match even though the context ultimately has that bean.

In auto-configurations, Spring Boot documentation generally recommends placing bean conditions on @Bean methods when possible, because method-level conditions are evaluated during bean method registration and typically fit creating default beans better.

This does not mean class-level @ConditionalOnBean is always wrong. It is appropriate when the entire configuration genuinely only makes sense after a group of foundational beans exists and configuration order is clearly controlled. Consider ordering and scope of impact before using it.

## 8. Outer class conditions and nested configurations

Nested configurations are a useful technique for separating groups of beans that have different baseline conditions.

For example, a library has two independent integrations:

- Partner HTTP SDK.
- Partner messaging SDK.

Do not put both branches in an outer class with a @ConditionalOnClass requiring both libraries if applications might need only one integration.

You can structure it as:

~~~java
@AutoConfiguration
public class PartnerAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.http.PartnerHttpClient")
    static class HttpConfiguration {

        @Bean
        PartnerHttpService partnerHttpService(
                PartnerHttpClient client) {
            return new PartnerHttpService(client);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.messaging.PartnerMessageClient")
    static class MessagingConfiguration {

        @Bean
        PartnerMessagingService partnerMessagingService(
                PartnerMessageClient client) {
            return new PartnerMessagingService(client);
        }
    }
}
~~~

Each nested configuration has its own condition. If only the HTTP SDK is present, the HTTP branch can be applied while the messaging branch is skipped.

### 8.1. Outer class conditions still apply to nested classes

If you add a condition on the outer PartnerAutoConfiguration:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
public class PartnerAutoConfiguration {
    // Nested configurations...
}
~~~

then the overall property becomes a shared gate. When partner.enabled is not true, neither nested configuration is processed through that outer configuration.

The nested conditions can be pictured as:

~~~text
PartnerAutoConfiguration
    partner.enabled = true?
          │
          ├── No → Skip everything
          │
          ▼ Yes
    ├── HttpConfiguration
    │      PartnerHttpClient present?
    │
    └── MessagingConfiguration
           PartnerMessageClient present?
~~~

If two integrations need to be toggled completely independently, consider placing separate properties on each nested configuration instead of using an overly broad outer gate.

### 8.2. Nested configurations help isolate optional classes

When an SDK is optional, types from that SDK should not appear carelessly in an outer auto-configuration that is always loaded.

Safer example:

~~~java
@AutoConfiguration
public class PartnerAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
    static class PartnerClientConfiguration {

        @Bean
        PartnerService partnerService(PartnerClient client) {
            return new PartnerService(client);
        }
    }
}
~~~

Spring Boot can read the nested configuration's metadata and skip the branch containing the optional type when the class is absent. This avoids forcing the JVM to resolve an absent SDK type prematurely while processing the outer configuration.

Putting `name` in the class condition avoids referencing the SDK type directly in the annotation. More importantly, **method signatures and code using the SDK reside inside the guarded nested class**. Merely changing a class literal to a string does not protect other method signatures that reference the optional type.

## 9. Class-level vs. method-level conditions with @ConditionalOnClass

These two approaches have different scopes.

Condition on the class:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
public class PartnerConfiguration {

    @Bean
    PartnerService partnerService() {
        return new PartnerService();
    }

    @Bean
    PartnerMetrics partnerMetrics() {
        return new PartnerMetrics();
    }
}
~~~

If PartnerClient is absent, neither PartnerService nor PartnerMetrics is registered from this class.

Condition on the method:

~~~java
@Configuration(proxyBeanMethods = false)
public class PartnerConfiguration {

    @Bean
    PartnerService partnerService() {
        return new PartnerService();
    }

    @Bean
    @ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
    PartnerMetrics partnerMetrics() {
        return new PartnerMetrics();
    }
}
~~~

Here, only PartnerMetrics is blocked when the class is absent; PartnerService can still be registered.

However, if a method-level condition checks a class while the method's own signature or return type references the optional class, there is a risk the class is resolved before the method condition can protect it. In that case, move the method into a nested configuration with a class-level condition.

## 10. Multiple conditions on the same bean

A @Bean method can have multiple conditions:

~~~java
@Bean
@ConditionalOnClass(name = "com.partner.metrics.MetricsClient")
@ConditionalOnProperty(
        prefix = "partner.metrics",
        name = "enabled",
        havingValue = "true"
)
@ConditionalOnMissingBean(PartnerMetricsCollector.class)
PartnerMetricsCollector partnerMetricsCollector() {
    return new DefaultPartnerMetricsCollector();
}
~~~

The bean is registered only when all conditions applying at that declaration point are satisfied:

1. MetricsClient is present on the classpath.
2. partner.metrics.enabled has the value true.
3. No matching PartnerMetricsCollector exists in the context at the time the condition is evaluated.

Diagram:

~~~text
MetricsClient present?
       │
       ├── No → Skip bean
       ▼ Yes
metrics.enabled = true?
       │
       ├── No → Skip bean
       ▼ Yes
PartnerMetricsCollector already exists?
       │
       ├── Yes → Skip default bean
       ▼ No
Register DefaultPartnerMetricsCollector
~~~

This combines classpath, property, and bean conditions at the exact bean scope.

## 11. A complete example: core bean and two optional features

Suppose an application has a core service that does not depend on the metrics SDK or health SDK. Only specific branches need the corresponding client.

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class PartnerAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    PartnerFacade partnerFacade() {
        return new DefaultPartnerFacade();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.health.HealthClient")
    @ConditionalOnProperty(
            prefix = "partner.health",
            name = "enabled",
            havingValue = "true"
    )
    static class HealthConfiguration {

        @Bean
        @ConditionalOnMissingBean
        PartnerHealthIndicator partnerHealthIndicator(
                HealthClient client) {
            return new PartnerHealthIndicator(client);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.metrics.MetricsClient")
    @ConditionalOnProperty(
            prefix = "partner.metrics",
            name = "enabled",
            havingValue = "true"
    )
    static class MetricsConfiguration {

        @Bean
        @ConditionalOnMissingBean
        PartnerMetricsCollector partnerMetricsCollector(
                MetricsClient client) {
            return new PartnerMetricsCollector(client);
        }
    }
}
~~~

In this design:

- partner.enabled is the shared gate of the integration.
- The default PartnerFacade can be replaced by the application.
- HealthConfiguration is considered only if the health SDK is present and the health property is enabled.
- MetricsConfiguration is considered only if the metrics SDK is present and the metrics property is enabled.
- Missing one optional SDK does not eliminate the core facade or the remaining integration branch.

PartnerFacade, HealthClient, MetricsClient, and their implementations are illustrative types; in real code you must supply the corresponding dependencies and beans.

## 12. Testing the scope of class-level conditions

When writing auto-configuration, do not check only whether one bean appears. Verify the **entire group of beans affected by a class condition**.

Suppose:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "feature",
        name = "enabled",
        havingValue = "true"
)
public class FeatureAutoConfiguration {

    @Bean
    CoreFeatureService coreFeatureService() {
        return new CoreFeatureService();
    }

    @Bean
    FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
~~~

Test using ApplicationContextRunner:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class FeatureAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(FeatureAutoConfiguration.class));

    @Test
    void registersAllBeansWhenOuterConditionMatches() {
        runner.withPropertyValues("feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CoreFeatureService.class);
                    assertThat(context).hasSingleBean(FeatureMetrics.class);
                });
    }

    @Test
    void registersNoBeansWhenOuterConditionDoesNotMatch() {
        runner.withPropertyValues("feature.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CoreFeatureService.class);
                    assertThat(context).doesNotHaveBean(FeatureMetrics.class);
                });
    }
}
~~~

The two tests verify that the class-level condition affects both beans. Checking only CoreFeatureService could miss FeatureMetrics still being registered unintentionally due to a flawed condition structure.

## 13. Testing the scope of method-level conditions

Suppose the class is always applied, while metrics has its own condition:

~~~java
@AutoConfiguration
public class FeatureAutoConfiguration {

    @Bean
    CoreFeatureService coreFeatureService() {
        return new CoreFeatureService();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "feature.metrics",
            name = "enabled",
            havingValue = "true"
    )
    FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
~~~

Test:

~~~java
@Test
void keepsCoreBeanWhenOptionalMethodConditionDoesNotMatch() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(FeatureAutoConfiguration.class))
            .withPropertyValues("feature.metrics.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CoreFeatureService.class);
                assertThat(context).doesNotHaveBean(FeatureMetrics.class);
            });
}
~~~

The test proves the condition on the method blocks only FeatureMetrics; CoreFeatureService is still registered.

### 13.1. Testing when the method condition matches

~~~java
@Test
void registersOptionalBeanWhenMethodConditionMatches() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(FeatureAutoConfiguration.class))
            .withPropertyValues("feature.metrics.enabled=true")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CoreFeatureService.class);
                assertThat(context).hasSingleBean(FeatureMetrics.class);
            });
}
~~~

Testing both sides proves the property controls the intended target bean accurately.

## 14. Testing @ConditionalOnMissingBean and override capability

Auto-configuration should allow the application to supply its own bean. For example:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

Testing the case without a custom bean:

~~~java
@Test
void createsDefaultWhenUserBeanIsMissing() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(GreetingAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context.getBean(GreetingService.class))
                        .isInstanceOf(DefaultGreetingService.class);
            });
}
~~~

Testing the case where the application provides an implementation:

~~~java
@Test
void backsOffWhenUserProvidesGreetingService() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(GreetingAutoConfiguration.class))
            .withBean(
                    GreetingService.class,
                    () -> new CustomGreetingService()
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context.getBean(GreetingService.class))
                        .isInstanceOf(CustomGreetingService.class);
            });
}
~~~

The second test proves that method-level @ConditionalOnMissingBean skips only the default bean; the test-provided bean remains and is used.

### 14.1. Why is testing both branches important?

If you test only without a custom bean, you know auto-configuration can create the default bean. You do not yet know whether it backs off properly when the consumer provides its own bean.

An auto-configuration test suite should confirm at least:

- The default bean is created when no user bean exists.
- The default bean is not created when a matching user bean already exists.
- Other independent beans are still created when one default bean backs off.

## 15. Auto-configuration ordering in tests and applications

When using @ConditionalOnBean or @ConditionalOnMissingBean, pay attention to registration order.

For example:

~~~java
@AutoConfiguration
public class PartnerCoreAutoConfiguration {
    @Bean
    PartnerService partnerService() {
        return new PartnerService();
    }
}
~~~

~~~java
@AutoConfiguration(after = PartnerCoreAutoConfiguration.class)
public class PartnerMetricsAutoConfiguration {
    @Bean
    @ConditionalOnBean(PartnerService.class)
    PartnerMetrics partnerMetrics(PartnerService service) {
        return new PartnerMetrics(service);
    }
}
~~~

PartnerMetricsAutoConfiguration is processed after PartnerCoreAutoConfiguration, so the bean condition can see PartnerService already registered.

Without declaring appropriate ordering, the condition could be evaluated before the expected bean appears during auto-configuration processing. This is especially important with @ConditionalOnMissingBean in starter libraries.

Do not try to fix ordering issues by manually instantiating beans inside conditions or calling ApplicationContext.getBean() inside configurations. Use supported condition metadata and auto-configuration ordering.

## 16. Outer class conditions and nested configuration processing order

When nested configurations exist, conditions can be combined at multiple levels:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
public class PartnerAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.health.HealthClient")
    @ConditionalOnProperty(
            prefix = "partner.health",
            name = "enabled",
            havingValue = "true"
    )
    static class HealthConfiguration {

        @Bean
        @ConditionalOnMissingBean
        PartnerHealthIndicator partnerHealthIndicator(
                HealthClient client) {
            return new PartnerHealthIndicator(client);
        }
    }
}
~~~

For the health bean to appear, all three condition layers must be satisfied:

1. partner.enabled = true on the outer configuration.
2. HealthClient present on the nested configuration.
3. partner.health.enabled = true on the @Bean method (note: here in the nested class).

If the outer condition is not satisfied, Spring does not enter this nested configuration branch. If the outer condition matches yet the SDK is missing, the nested configuration is skipped. If both outer layers match while the health property is off, only the indicator bean/branch is skipped.

~~~text
partner.enabled = true?
       │
       ├── No → No Partner branch
       ▼ Yes
HealthClient present?
       │
       ├── No → No HealthConfiguration
       ▼ Yes
partner.health.enabled = true?
       │
       ├── No → No PartnerHealthIndicator
       ▼ Yes
Register PartnerHealthIndicator
~~~

This is how conditions are combined in nested scopes. Each condition layer has a clear responsibility.

## 17. Common design mistakes

### 17.1. Placing a minor feature's condition on the outer class

A metrics bean is optional, yet the metrics condition is placed at the class level. When metrics are turned off, the main service and health indicator vanish as well.

**Fix:** move the metrics condition down to the @Bean method or a separate nested configuration if an entire group of metrics depends on the same condition.

### 17.2. Placing a baseline condition on a method too late

A group of beans all need the SDK, yet only one method has @ConditionalOnClass. The remaining methods are still inspected and may reference the absent SDK.

**Fix:** place the class condition on a nested configuration wrapping every method that needs the SDK. If there are beans independent of the SDK, keep them in the outer configuration or a separate nested configuration.

### 17.3. Using class-level @ConditionalOnMissingBean and losing unrelated beans

The application supplies a custom service, causing the entire configuration class to be excluded, including formatter and metrics that the application still needs.

**Fix:** place @ConditionalOnMissingBean on each default bean that should allow independent overriding.

### 17.4. Using @ConditionalOnBean without controlling order

An auto-configuration depends on a bean from another auto-configuration, yet is processed first. The condition does not see the bean and the configuration is skipped.

**Fix:** check dependencies between auto-configurations and declare before/after appropriately. Verify order in context tests.

### 17.5. Using a method-level class condition when the signature references an optional type

A method has @ConditionalOnClass, yet a parameter or return type uses a class from a library that may be absent. The JVM may resolve that type prematurely.

**Fix:** move the method into a nested configuration with a class-level condition. Keep the outer class free of references to the optional type in fields, superclasses, interfaces, or method signatures.

### 17.6. Assuming a condition on a nested class skips all errors in the outer class

Nested configurations help isolate optional types, yet if the outer class still has a method or field directly referencing the SDK, class-loading issues can still occur.

**Fix:** inspect the entire outer class and the types it references. Keep optional APIs only inside the guarded branch.

### 17.7. Creating beans of the same type from multiple branches without rules

Two nested configurations both match and both register the same service type. Consumers injecting a single dependency may hit NoUniqueBeanDefinitionException or name collisions depending on naming.

**Fix:** ensure conditions are mutually exclusive, use @ConditionalOnMissingBean for default beans, or use qualifiers/collections if multiple implementations are truly intended.

## 18. Diagnosing conditions that did not apply

When a bean does not appear, do not inspect only the annotation on the method. Determine which condition blocked it.

### Step 1: Identify where the bean is declared

- Which configuration class contains the @Bean method?
- Is the bean inside a nested configuration?
- Is there a condition on the outer class?
- Is there a condition on the nested class?
- Is there a separate condition on the method?

A method condition cannot rescue a configuration class already excluded at the outer level.

### Step 2: Check properties and profiles

For @ConditionalOnProperty, verify the exact key, value, havingValue, and matchIfMissing. For @Profile, verify the actual active profiles.

### Step 3: Check the classpath

For @ConditionalOnClass or @ConditionalOnMissingClass, verify whether the class is on the process's runtime classpath. The test classpath can differ from the executable JAR.

### Step 4: Check bean conditions

For @ConditionalOnBean or @ConditionalOnMissingBean, inspect which beans were already registered when the condition was evaluated and which auto-configurations needed to be processed first.

### Step 5: Read the Condition Evaluation Report

Run the application with the debug option:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot can print the condition report with positive match and negative match sections. Search for the relevant auto-configuration, configuration class, or condition name.

### Step 6: Confirm beans in the context

After the application starts, you can use ApplicationContext or Actuator /actuator/beans if the endpoint is properly exposed and secured. This distinguishes an unregistered bean from a bean that was registered yet failed initialization.

## 19. Testing a condition matrix

For an auto-configuration with multiple condition layers, write tests following a matrix. For example:

| SDK | partner.enabled | metrics.enabled | Expected outcome |
|---|---:|---:|---|
| Present | true | true | Core service and metrics bean can be registered. |
| Present | true | false | Core service present, metrics bean absent. |
| Present | false | true | Entire outer configuration skipped; metrics do not appear. |
| Absent | true | true | Branch requiring SDK is skipped. |

For classpath conditions, tests with and without the SDK must use corresponding runtime classpaths. You cannot simulate a missing class merely by changing properties.

For @ConditionalOnMissingBean, add a test branch supplying a user bean and confirm the default bean backs off while independent beans keep working.

With many conditions, you do not necessarily have to create every combination if the count grows too large. Prioritize testing:

- One matching test per condition.
- One non-matching test per condition.
- Outer and inner conditions combined properly.
- Unrelated beans not disabled unintentionally.
- User override of default beans.

## 20. Common misconceptions

**"If a condition on a @Bean method does not match, the entire configuration class is skipped."**  
No. Only the bean declared by that method is skipped; other methods can still be processed.

**"If a condition on a configuration class does not match, only one bean is skipped."**  
No. The entire configuration at the class level is excluded from processing along that branch, including @Bean methods and related configurations declared from that class.

**"Putting all @ConditionalOnMissingBean annotations on the configuration class is cleaner."**  
No. If beans can be overridden independently, placing conditions on individual methods preserves unrelated default beans.

**"@ConditionalOnBean always sees every bean that will eventually exist in the context."**  
No. Bean conditions are evaluated against bean definitions already processed at that moment. Auto-configuration order can affect the result.

**"@Order can replace before/after on auto-configurations."**  
No. @Order mainly sorts certain ordered collections; before/after control relative order between auto-configurations.

**"Method-level @ConditionalOnClass is always safe with optional classes in the signature."**  
No. Types in the method signature may be resolved by the JVM before the method condition can protect it. Use nested configurations to isolate optional types.

**"Using name instead of a class literal is enough to protect every reference to an optional type."**  
No. The name attribute only changes how the class is specified in the annotation. The outer class can still fail if fields, method signatures, or superclasses reference the absent class.

**"If a nested configuration has its own condition, the outer condition does not affect it."**  
No. If the outer configuration is excluded, nested configurations declared from that branch are not processed either.

**"A matching condition means the bean was created successfully."**  
No. Conditions decide whether to register a configuration/bean definition; constructors, factory methods, or dependencies can still fail during instantiation.

## Core takeaways

**Conditions on a configuration class** act as a shared gate: if unmatched, that entire configuration is skipped. **Conditions on individual @Bean methods** act as individual gates: only the bean declared by that method is skipped, while other beans in the same class can still exist.

In auto-configuration, place conditions at the smallest scope that accurately expresses the requirement. Use class-level conditions for shared baseline requirements of a group; use method-level conditions for optional beans or default beans that can be overridden independently. With @ConditionalOnBean and @ConditionalOnMissingBean, pay attention to auto-configuration order because conditions rely on bean definitions already processed. When a group of beans depends on an optional SDK, nested configurations help isolate classpath conditions and prevent loading types absent from the runtime classpath. Test matching, non-matching, and user bean override cases to ensure each condition affects only its intended scope.
