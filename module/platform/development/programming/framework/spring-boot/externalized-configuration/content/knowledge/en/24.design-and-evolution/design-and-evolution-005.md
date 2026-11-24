# Separating Feature Selection with @ConditionalOnProperty from Configuration Data

Spring Boot handles two configuration needs that are often conflated: **selecting whether a feature is active**, and **supplying parameters for that feature to run**. In small apps, both sometimes sit inside one `@ConfigurationProperties` record with an `enabled` field. Yet once a module owns an HTTP client, scheduler, listener, or database adapter, creating beans at the wrong time can cause side effects even if business logic later checks `enabled=false`.

In Spring Boot 3.3.x, those two responsibilities separate cleanly:

- `@ConditionalOnProperty`: controls **configuration/bean registration** based on values present in `Environment` while Spring builds the application context.
- `@ConfigurationProperties`: binds **typed data** such as `URI`, `Duration`, and `int`, supporting validation and defaults.

Convention example:

~~~yaml
features:
  delivery:
    enabled: false

app:
  delivery:
    endpoint: https://notify.example.org
    connect-timeout: 3s
    max-attempts: 3
~~~

`features.delivery.enabled` selects the operating mode only; `app.delivery.*` properties describe the adapter's data. This lesson uses Java 21, Spring Boot 3.3.x, Spring Test, and JUnit Jupiter, with application code, enable/disable cases, configuration precedence, testing, and refactoring guidance.

## 1. The Problem with Mixing `enabled` and Data in One Class

Common pattern:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        boolean enabled,
        URI endpoint,
        Duration connectTimeout,
        int maxAttempts) {
}
~~~

Then the service does:

~~~java
if (properties.enabled()) {
    sendToRemoteService(properties.endpoint());
}
~~~

Several drawbacks arise:

1. The service or client bean is still instantiated before the `if` runs.
2. Constructors may open connections or schedule background jobs even when disabled.
3. Records requiring `endpoint` can fail validation at startup even when the feature is unused.
4. Multiple services must repeat the conditional check.
5. Swapping the implementation for a No-op or alternate adapter is harder.
6. Testing the disabled path requires probing internal logic rather than checking the bean graph.
7. Having an endpoint or credentials can be mistaken for enabling the feature.

A clearer structure:

~~~text
features.delivery.enabled
            |
            v
   @ConditionalOnProperty
            |
       +----+----+
       |         |
      true      false / missing
       |         |
       v         v
Configured    Noop
Delivery      Delivery
Sender        Sender
       |         |
       +----+----+
            |
            v
    DeliveryService

app.delivery.*
     |
     v
@ConfigurationProperties
     |
     v
Data for ConfiguredDeliverySender
(bound only when the enabled branch is registered)
~~~

The point of this pattern is not "every boolean must become an annotation", but that **bean wiring decisions** differ from **parameter data**.

## 2. How Does `@ConditionalOnProperty` Work?

Import:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
~~~

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "enabled",
        havingValue = "true")
public class DeliveryEnabledConfiguration {
    // Bean definitions are considered only when the flag matches.
}
~~~

The property name is `features.delivery.enabled`, built from `prefix` and `name`. When Spring Boot processes configuration classes, `OnPropertyCondition` evaluates the value in `Environment`.

Annotation attributes:

| Attribute | Purpose |
| --- | --- |
| `prefix` | Namespace, e.g. `features.delivery` |
| `name` | Property name or array of names, e.g. `enabled` |
| `value` | Alias for `name` |
| `havingValue` | Expected string value |
| `matchIfMissing` | Whether to match when the property does not exist |

`@ConditionalOnProperty` can be placed on a `@Configuration` class or a `@Bean` method. It is **not a boolean validation annotation**, nor does it mutate `Environment` values.

### Default Matching Rules

Without `havingValue`, the property must **exist and not equal `false`**:

| Property Value | `havingValue=""` | `havingValue="true"` | `havingValue="false"` |
| --- | --- | --- | --- |
| `true` | Matches | Matches | No |
| `false` | No | No | Matches |
| `hello` | Matches | No | No |
| Empty string | May match | No | No |
| Missing | No, by default | No | No |

That is why **specifying `havingValue="true"` is recommended** when the intent is strictly a boolean switch. Setting only `name="enabled"` allows a value like `hello` to activate the feature.

### matchIfMissing

Default is `matchIfMissing=false`. If you want **omitting the flag to mean disabled**, define the No-op branch with:

~~~java
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true)
~~~

Conversely, for the branch that performs real deliveries, require the flag to be explicitly `true` to prevent accidental activation.

## 3. Distinguishing Feature Switches from Data Properties

Two groups in the same YAML file with distinct responsibilities:

~~~yaml
features:
  delivery:
    enabled: true

app:
  delivery:
    endpoint: https://sandbox.example.org
    connect-timeout: 2s
    max-attempts: 2
~~~

| Key | Kind | Used By |
| --- | --- | --- |
| `features.delivery.enabled` | Feature selection | `@ConditionalOnProperty` |
| `app.delivery.endpoint` | Connection parameter | `DeliveryClientProperties` |
| `app.delivery.connect-timeout` | Timing parameter | `DeliveryClientProperties` |
| `app.delivery.max-attempts` | Retry parameter | `DeliveryClientProperties` |
| `app.delivery.api-key` | Adapter secret (if any) | Secure client configuration |

Why not use the presence of `app.delivery.endpoint` as the flag?

- An endpoint may be pre-populated in every environment while the feature must stay off.
- An endpoint may be valid while rollout policy forbids enabling it yet.
- An endpoint might be missing due to a bad deploy; that must not silently mean "disabled".
- Credentials may be mounted without granting permission to connect.
- Someday the adapter may change how it connects while the feature flag's meaning stays the same.

Splitting prefixes is an **architectural convention**. The framework does not mandate `features.*` and `app.*`; projects may choose other names as long as the boundary is documented.

## 4. Illustrative Project Structure

~~~text
delivery-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/delivery/
    │   │   ├── DeliveryDemoApplication.java
    │   │   ├── api/DeliverySender.java
    │   │   ├── impl/ConfiguredDeliverySender.java
    │   │   ├── impl/NoopDeliverySender.java
    │   │   ├── config/DeliveryClientProperties.java
    │   │   ├── config/DeliveryEnabledConfiguration.java
    │   │   ├── config/DeliveryDisabledConfiguration.java
    │   │   └── service/DeliveryWorkflow.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/delivery/
            └── DeliveryConfigurationTest.java
~~~

Core Maven dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Assume the project uses Spring Boot 3.3.x parent/BOM, Java 21, and standard build setup. `spring-boot-starter-validation` supplies the Jakarta Bean Validation provider required for typed-property constraints.

## 5. Creating the Business Interface

Create `DeliverySender.java`:

~~~java
package com.example.delivery.api;

public interface DeliverySender {
    void send(String message);
    String mode();
}
~~~

Create `DeliveryWorkflow.java`:

~~~java
package com.example.delivery.service;

import com.example.delivery.api.DeliverySender;
import org.springframework.stereotype.Service;

@Service
public final class DeliveryWorkflow {

    private final DeliverySender sender;

    public DeliveryWorkflow(DeliverySender sender) {
        this.sender = sender;
    }

    public void process(String message) {
        sender.send(message);
    }

    public String senderMode() {
        return sender.mode();
    }
}
~~~

This service does not inject `Environment` or `DeliveryClientProperties` just to inspect a flag. It depends on the **business contract `DeliverySender`**. Choosing the implementation belongs to the configuration layer.

Benefits:

- Easily unit-test `DeliveryWorkflow` with a fake sender.
- Swap implementations without modifying the service.
- No `if (enabled)` checks scattered before every call.
- Easy to prove in integration tests that the right bean was chosen.

## 6. Typed Configuration Holding Data Only

Create `DeliveryClientProperties.java`:

~~~java
package com.example.delivery.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryClientProperties(
        @NotNull URI endpoint,
        @DefaultValue("3s") Duration connectTimeout,
        @Min(1) @DefaultValue("3") int maxAttempts) {
}
~~~

Here:

- `endpoint` is required when the class is bound and Bean Validation is active.
- `connectTimeout` uses `Duration`, defaulting to three seconds.
- `maxAttempts` is an integer defaulting to three with a minimum of one.
- There is no `enabled` field because the record models **data**, not bean-creation decisions.

Spring Boot's Binder converts strings like `3s` into `Duration`. Validation checks values only after binding. A syntactically valid `URI` does not guarantee HTTPS, DNS resolution, or a reachable endpoint; if HTTPS is required, enforce an explicit rule.

### Data Can Be Present Even When the Feature Is Disabled

You can still keep `app.delivery.endpoint` in default config files for environments that will enable it later. However, **property presence does not decide bean registration**. Bean selection remains governed by `features.delivery.enabled`.

### Do Not Register the Record Unconditionally

A key point of this example is that the record is registered inside a `@Configuration` gated by the enabled condition below. If you place `@ConfigurationPropertiesScan` at the application root and scan the record unconditionally, Spring Boot may still create and bind this bean when the feature is off.

If the goal is to validate data only when the feature is enabled, make sure the typed config is not registered via another unconditional path.

## 7. Adapter Used When Enabled

Create `ConfiguredDeliverySender.java`:

~~~java
package com.example.delivery.impl;

import com.example.delivery.api.DeliverySender;
import com.example.delivery.config.DeliveryClientProperties;

public final class ConfiguredDeliverySender
        implements DeliverySender {

    private final DeliveryClientProperties properties;

    public ConfiguredDeliverySender(
            DeliveryClientProperties properties) {
        this.properties = properties;
    }

    @Override
    public void send(String message) {
        // Demo implementation does not perform real HTTP calls.
        // Do not log message payloads or credentials.
        System.out.println(
                "Demo sender configured for "
                        + properties.endpoint());
    }

    @Override
    public String mode() {
        return "configured";
    }
}
~~~

This class **is not annotated with `@Component`**. It is instantiated solely via a conditional `@Bean` method, preventing component scanning from creating it unconditionally.

In production, implementations might use `WebClient`, `RestClient`, or a messaging SDK. HTTP clients must use proper timeouts and retries; do not mistake printing a demo line for making a real network call.

## 8. Adapter Used When Disabled

Create `NoopDeliverySender.java`:

~~~java
package com.example.delivery.impl;

import com.example.delivery.api.DeliverySender;

public final class NoopDeliverySender
        implements DeliverySender {

    @Override
    public void send(String message) {
        // Intentionally do nothing when the feature is disabled.
    }

    @Override
    public String mode() {
        return "disabled";
    }
}
~~~

No-op fits when "do not send" is an acceptable business behavior. It keeps `DeliveryWorkflow` wired and callable through an unchanged interface.

**Never use a No-op to mask a mandatory operation** such as compliance auditing, encryption, authorization checks, or transaction recording. When an operation is mandatory, let the bean be missing and fail fast rather than silently skipping it.

## 9. Configuration for the Enabled Branch

Create `DeliveryEnabledConfiguration.java`:

~~~java
package com.example.delivery.config;

import com.example.delivery.api.DeliverySender;
import com.example.delivery.impl.ConfiguredDeliverySender;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "enabled",
        havingValue = "true")
@EnableConfigurationProperties(DeliveryClientProperties.class)
public class DeliveryEnabledConfiguration {

    @Bean
    DeliverySender configuredDeliverySender(
            DeliveryClientProperties properties) {
        return new ConfiguredDeliverySender(properties);
    }
}
~~~

This is the main boundary:

1. The condition checks `features.delivery.enabled`.
2. If the value is `true`, the configuration class is processed.
3. `@EnableConfigurationProperties` registers `DeliveryClientProperties`.
4. Spring Boot binds and validates `app.delivery.*`.
5. `ConfiguredDeliverySender` receives the typed configuration object.

If the flag does not match, this configuration creates no real sender. Because `@EnableConfigurationProperties` sits inside the conditional configuration, the record is not required on the disabled branch—provided no other registration picks it up.

### Why Place the Condition on the Class?

When an entire group of beans—HTTP client, adapter, listener, and configuration properties—belongs to the enabled feature, placing the condition at the **class level** gates the whole group, reducing the risk of accidentally instantiating an unwanted bean.

If only one method is conditional while other beans are always needed, a method-level condition may fit better. In that case, carefully check where typed properties are registered.

## 10. Configuration for the Disabled Branch

Create `DeliveryDisabledConfiguration.java`:

~~~java
package com.example.delivery.config;

import com.example.delivery.api.DeliverySender;
import com.example.delivery.impl.NoopDeliverySender;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true)
public class DeliveryDisabledConfiguration {

    @Bean
    DeliverySender noopDeliverySender() {
        return new NoopDeliverySender();
    }
}
~~~

When the flag is `false` or absent, only the disabled branch matches. When `true`, the disabled branch does not match. Pairing `havingValue="false"` with `matchIfMissing=true` expresses **off by default**.

### Outcomes for Different Values

| `features.delivery.enabled` | Bean Created in This Example |
| --- | --- |
| Absent | `NoopDeliverySender` |
| `false` | `NoopDeliverySender` |
| `true` | `ConfiguredDeliverySender` |
| `invalid` | Neither branch matches |
| Empty string | Neither branch matches |

An `invalid` value is not automatically rejected by the annotation. If `DeliveryWorkflow` is a required bean needing `DeliverySender`, Spring fails due to the missing bean. If no mandatory consumer exists, the context might still start with no sender. If flags must strictly be valid booleans, add explicit flag validation or dedicated configuration tests.

## 11. Registering Configuration in the Application

Create `DeliveryDemoApplication.java`:

~~~java
package com.example.delivery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DeliveryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeliveryDemoApplication.class, args);
    }
}
~~~

Both configuration classes live in the subpackage `com.example.delivery.config`, so default component scanning discovers them.

**Do not add `@ConfigurationPropertiesScan` at the root across all packages in this example**, because doing so would register `DeliveryClientProperties` even when the feature is disabled, breaking the "validate only when enabled" guarantee.

### Do Not Annotate Implementations with `@Component`

For beans defined via `@Bean`, do not also annotate `ConfiguredDeliverySender` or `NoopDeliverySender` with `@Component` without matching conditions. Otherwise component scanning can register a second bean, triggering `NoUniqueBeanDefinitionException` or instantiating the real sender even when the flag is false.

### Do Not Confuse with Runtime Service Constructors

A service injecting `DeliverySender` via its constructor is instantiated after Spring processes bean definitions. If an invalid flag leaves no implementation registered, the missing-dependency error reflects an invalid policy/flag, not a `DeliveryClientProperties` conversion error.

## 12. `application.yml` for Safe Defaults

Example `src/main/resources/application.yml`:

~~~yaml
features:
  delivery:
    enabled: false

app:
  delivery:
    connect-timeout: 3s
    max-attempts: 3
~~~

No endpoint yet. When the flag is false, the enabled branch does not register typed properties, so no endpoint is required in this design.

To enable in dev:

~~~yaml
# application-dev.yml
features:
  delivery:
    enabled: true

app:
  delivery:
    endpoint: https://sandbox.example.org
    connect-timeout: 1s
    max-attempts: 2
~~~

To enable in prod:

~~~yaml
# application-prod.yml
features:
  delivery:
    enabled: true

app:
  delivery:
    endpoint: https://notify.example.org
    connect-timeout: 3s
    max-attempts: 4
~~~

These addresses are examples only, not real endpoints.

### Behavior When Enabled Without Data

If `features.delivery.enabled=true` yet `app.delivery.endpoint` is missing, the typed properties bean is bound and `@NotNull` validation fails startup when Bean Validation is configured. That is the intended behavior for a feature requiring an endpoint.

### Behavior When Disabled with Invalid Data

If the flag is false while `app.delivery.max-attempts=abc`, binding into the record does not occur in this model. However, **the YAML file must still be syntactically valid**, because Config Data is parsed before Spring evaluates conditions. Conditions do not hide broken YAML syntax.

## 13. Overriding via Environment and CLI

Spring Boot determines effective values according to `PropertySource` precedence.

Shared file example:

~~~yaml
features:
  delivery:
    enabled: false
~~~

Override via CLI:

~~~bash
java -jar delivery-demo.jar   --features.delivery.enabled=true   --app.delivery.endpoint=https://sandbox.example.org
~~~

Under standard precedence, CLI arguments take higher priority than YAML files, so the enabled branch is selected.

In a Linux shell:

~~~bash
export FEATURES_DELIVERY_ENABLED=true
export APP_DELIVERY_ENDPOINT=https://sandbox.example.org
export APP_DELIVERY_CONNECTTIMEOUT=2s
java -jar delivery-demo.jar
~~~

Environment variable naming rule:

~~~text
features.delivery.enabled  -> FEATURES_DELIVERY_ENABLED
app.delivery.endpoint      -> APP_DELIVERY_ENDPOINT
app.delivery.connect-timeout -> APP_DELIVERY_CONNECTTIMEOUT
~~~

Dots become underscores, hyphens are removed when mapping to env variable names, and names are uppercased under Spring Boot's relaxed binding rules.

**Note:** changing an environment variable outside an already-running Java process does not alter registered beans. Using `@ConditionalOnProperty` here is a **startup-time switch**.

## 14. Separating Feature Flags from Bean Validation

Distinguish three layers:

- **Condition:** Should the enabled configuration be registered?
- **Conversion:** Does `3s` convert to `Duration`?
- **Validation:** Does `maxAttempts=0` violate `@Min(1)`?

Example:

~~~text
features.delivery.enabled=false
app.delivery.max-attempts=0
~~~

The disabled branch does not bind `DeliveryClientProperties`, so the record's validation does not run.

Conversely:

~~~text
features.delivery.enabled=true
app.delivery.max-attempts=0
~~~

registers the typed config; after converting to `int`, Bean Validation rejects `0`.

If a company policy requires validating **all configs including disabled modules** in CI, build a standalone pre-deployment configuration validator. That is a different policy from validating only active beans at startup.

## 15. Why Does `@DefaultValue` Not Replace `matchIfMissing`?

On a data record:

~~~java
@DefaultValue("3s") Duration connectTimeout
~~~

means: if `app.delivery.connect-timeout` is absent during binding, the Binder uses the default three seconds.

On a condition:

~~~java
@ConditionalOnProperty(
    name = "features.delivery.enabled",
    havingValue = "false",
    matchIfMissing = true)
~~~

means: the condition matches when `features.delivery.enabled` is absent. It **does not insert `features.delivery.enabled=false` into `Environment`**.

The two defaults have different jobs. In this design, a missing flag selects No-op, while a missing timeout when enabled falls back to 3s.

## 16. Putting the Condition on the Class vs `@Bean` Method

Class-level:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "features.report",
    name = "enabled",
    havingValue = "true")
class ReportConfiguration {

    @Bean
    ReportExporter reportExporter(ReportProperties properties) {
        return new ReportExporter(properties);
    }
}
~~~

Method-level:

~~~java
@Configuration(proxyBeanMethods = false)
class ReportConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "features.report",
        name = "enabled",
        havingValue = "true")
    ReportExporter reportExporter(ReportProperties properties) {
        return new ReportExporter(properties);
    }
}
~~~

If only the method has the condition while the class carries `@EnableConfigurationProperties(ReportProperties.class)` unconditionally, the record can still be bound when the feature is off. Therefore, **put the condition on the entire registration boundary** if you want to isolate module data.

### Example of a Method Condition with Unwanted Binding

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ReportProperties.class)
class ReportsConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "features.report",
        name = "enabled",
        havingValue = "true")
    ReportExporter reportExporter(ReportProperties props) {
        return new ReportExporter(props);
    }
}
~~~

`ReportProperties` can still be created and bound even when `reportExporter` is skipped, because the properties registration annotation sits outside the condition.

This design bug is easy to miss when gradually migrating from `@ConfigurationProperties` to `@ConditionalOnProperty`.

## 17. `@Profile` vs `@ConditionalOnProperty`

`@Profile` selects beans by **environment/profile name**:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
class LocalTestAdapterConfiguration {
}
~~~

`@ConditionalOnProperty` selects by a **specific property**:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "enabled",
        havingValue = "true")
class DeliveryEnabledConfiguration {
}
~~~

Both conditions can be combined:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("!prod")
@ConditionalOnProperty(
        prefix = "features.debug",
        name = "enabled",
        havingValue = "true")
class DebugConfiguration {
}
~~~

The class applies only when both the profile expression and property condition match.

Do not create a dedicated profile per feature when all you need is an independent on/off toggle. Profiles describe **environment configuration sets**, whereas flags express **feature choices**. They complement each other without replacing one another.

## 18. `@ConditionalOnProperty` Is Not a Dynamic Runtime Toggle

Spring evaluates `@ConditionalOnProperty` while processing bean definitions. If a YAML file or ConfigMap changes after startup, the bean graph does not automatically rebuild just because this annotation is present.

For example:

~~~text
Startup: features.delivery.enabled=false
    -> NoopDeliverySender is registered.

10 minutes later: config file changes to true
    -> ConfiguredDeliverySender is NOT automatically created.
~~~

If toggling per request, tenant, user, or campaign is required, build a **runtime feature decision service**:

~~~java
public interface FeatureDecisions {
    boolean isDeliveryEnabled(String tenantId);
}
~~~

The service evaluates decisions at request time, with its own cache/TTL, auditing, and rollback mechanisms. Compare the two strategies:

| Need | Choice |
| --- | --- |
| Toggle across deploy/restart | `@ConditionalOnProperty` |
| Toggle per request/tenant | Runtime feature flag provider |
| Change bean parameters on restart | `@ConfigurationProperties` |
| Dynamic refresh while running | Dedicated refresh mechanism; verify compatibility |

Even if a project uses a dedicated refresh system, do not assume every bean gated by `@ConditionalOnProperty` is safely re-registered. Verify your stack's exact behavior.

## 19. Conditions Can Combine Multiple Names, Not OR

Example:

~~~java
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = {"enabled", "licensed"},
        havingValue = "true")
~~~

When multiple `name` entries are specified, **all** of them must match. That is an AND relationship.

~~~properties
features.delivery.enabled=true
features.delivery.licensed=false
~~~

→ The condition does not match.

If you need either of two keys to match, use a different conditional strategy or policy check—never list multiple names expecting OR semantics.

Similarly, `@ConditionalOnProperty` **is unreliable for matching collection properties**. A source containing `app.regions[0]` without a top-level `app.regions` key may not match a condition checking the parent key. For list-based decisions, use a converter/config object or an appropriate custom `Condition`.

## 20. Do Not Use Credentials or Endpoints as Feature Flags

Avoid writing:

~~~java
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "api-key")
~~~

to decide whether to register a payment client.

Reasons:

- Credentials may be mounted ahead of time while the feature is still prohibited.
- An expired credential is still a non-empty string.
- Someone entering a test token can accidentally activate real behavior.
- No explicit enable/disable intent is expressed.
- Without `havingValue`, the condition only checks presence and `!= false`.

Better:

~~~properties
features.payment.enabled=false
app.payment.api-key=...
app.payment.endpoint=...
~~~

When enabled, validate the data properly and instantiate the real adapter. When disabled, create no client or only a No-op if business semantics allow. Never log tokens, store secrets in metadata, or treat a flag as an authorization boundary.

## 21. No-op or No Bean Registered at All?

The delivery example uses a No-op so `DeliveryWorkflow` stays operational. Yet for some capabilities, registering **no bean** when disabled is cleaner.

Scheduler example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "features.cleanup",
        name = "enabled",
        havingValue = "true")
class CleanupScheduleConfiguration {

    @Bean
    CleanupScheduler cleanupScheduler(CleanupProperties props) {
        return new CleanupScheduler(props);
    }
}
~~~

When the flag is false, there is no reason to create the scheduler. Do not add a No-op branch unless consumers genuinely require a stable interface.

If an optional service consumes the bean, inject `ObjectProvider<CleanupScheduler>`; if a service strictly requires the scheduler, a missing bean should fail startup. Never introduce a No-op just to hide a required dependency.

## 22. When You Need More Modes Than True/False

A boolean is insufficient when you have:

~~~text
OFF
SIMULATION
REAL
~~~

You can use a mode flag:

~~~properties
features.delivery.mode=simulation
~~~

with conditional configurations:

~~~java
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "mode",
        havingValue = "simulation")
~~~

or:

~~~java
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "mode",
        havingValue = "real")
~~~

Be sure to specify the default and how unknown modes behave. For complex options, a typed enum configuration or strategy factory is far easier to maintain than conflicting booleans like `enabled`, `simulate`, and `real`.

If the mode dictates the entire bean graph, conditions fit well; if the mode changes at runtime, prefer a runtime strategy.

## 23. Does `@ConditionalOnMissingBean` Act Like a Flag?

No. `@ConditionalOnMissingBean` checks whether a matching bean is already registered; it does not read `features.delivery.enabled`.

Example:

~~~java
@Bean
@ConditionalOnMissingBean(DeliverySender.class)
DeliverySender fallbackSender() {
    return new NoopDeliverySender();
}
~~~

This fits auto-configuration when letting users supply their own bean. However, results can depend on bean-definition processing order, so Spring Boot advises caution and uses it primarily in auto-configuration.

For the problem "false creates No-op, true creates configured", two `@ConditionalOnProperty` blocks are more transparent and less order-sensitive.

If a starter needs both bean overriding and a feature switch, you can combine conditions while keeping responsibilities distinct: **is the feature enabled?** vs **does a bean already exist?**.

## 24. Testing with `ApplicationContextRunner`

`ApplicationContextRunner` creates lightweight contexts with varying properties, making it ideal for testing conditions.

Create `DeliveryConfigurationTest.java`:

~~~java
package com.example.delivery;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.delivery.api.DeliverySender;
import com.example.delivery.config.DeliveryEnabledConfiguration;
import com.example.delivery.config.DeliveryDisabledConfiguration;
import com.example.delivery.impl.ConfiguredDeliverySender;
import com.example.delivery.impl.NoopDeliverySender;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class DeliveryConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(
                    DeliveryEnabledConfiguration.class,
                    DeliveryDisabledConfiguration.class);

    @Test
    void missingFlagUsesNoop() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DeliverySender.class);
            assertThat(context.getBean(DeliverySender.class))
                    .isInstanceOf(NoopDeliverySender.class);
        });
    }

    @Test
    void falseFlagUsesNoop() {
        runner.withPropertyValues(
                "features.delivery.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBean(DeliverySender.class))
                    .isInstanceOf(NoopDeliverySender.class);
            });
    }

    @Test
    void trueFlagUsesConfiguredSender() {
        runner.withPropertyValues(
                "features.delivery.enabled=true",
                "app.delivery.endpoint=https://sandbox.example.org",
                "app.delivery.connect-timeout=2s",
                "app.delivery.max-attempts=2")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(DeliverySender.class);
                assertThat(context.getBean(DeliverySender.class))
                    .isInstanceOf(ConfiguredDeliverySender.class);
            });
    }

    @Test
    void unexpectedFlagMatchesNeither() {
        runner.withPropertyValues(
                "features.delivery.enabled=unexpected")
            .run(context -> {
                assertThat(context)
                    .doesNotHaveBean(DeliverySender.class);
            });
    }
}
~~~

Assumes `spring-boot-starter-test` provides JUnit Jupiter and AssertJ. The test starts neither a web server nor remote connections.

### Checking Missing Endpoint

With Bean Validation properly configured, if the flag is true while `app.delivery.endpoint` is absent, the `@NotNull` record fails validation. In a minimal test context, make sure validation infrastructure is actually provided before asserting specific validation failures.

`ApplicationContextRunner` tests individual configurations precisely; it does not replace integration tests verifying component scanning and full bootstrap.

## 25. Testing That the Disabled Branch Does Not Need Parameters

A useful test:

~~~java
@Test
void disabledDoesNotBindUnusedClientData() {
    runner.withPropertyValues(
            "features.delivery.enabled=false",
            "app.delivery.max-attempts=not-a-number")
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getBean(DeliverySender.class))
                .isInstanceOf(NoopDeliverySender.class);
        });
}
~~~

The expected outcome in this sample architecture is that the disabled branch does not bind `DeliveryClientProperties`, so unused module data does not become required.

If this test fails, check:

1. Is `@ConfigurationPropertiesScan` registering the record automatically?
2. Is `@EnableConfigurationProperties` placed on an unconditional class?
3. Does some bean inject the record even when disabled?
4. Did an implementation accidentally carry `@Component`?
5. Is another auto-configuration reading that key?

Do not disable module validation just to make this test pass. The goal is preserving the chosen boundary: data must be valid only when used.

### YAML Syntax Must Still Be Valid

If YAML has syntax errors, Spring Boot fails during Config Data parsing before evaluating conditions. `@ConditionalOnProperty` does not make Spring skip reading/parsing files containing malformed YAML.

## 26. Testing Full Wiring with `@SpringBootTest`

Disabled example:

~~~java
package com.example.delivery;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.delivery.service.DeliveryWorkflow;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "features.delivery.enabled=false"
})
class DeliveryDisabledIntegrationTest {

    @Autowired
    DeliveryWorkflow workflow;

    @Test
    void usesNoopSender() {
        assertThat(workflow.senderMode()).isEqualTo("disabled");
    }
}
~~~

Enabled example:

~~~java
@SpringBootTest(properties = {
        "features.delivery.enabled=true",
        "app.delivery.endpoint=https://sandbox.example.org"
})
class DeliveryEnabledIntegrationTest {

    @Autowired
    DeliveryWorkflow workflow;

    @Test
    void usesConfiguredSender() {
        assertThat(workflow.senderMode()).isEqualTo("configured");
    }
}
~~~

The second test file needs matching imports and annotations just like the first. `@SpringBootTest` verifies app component scanning, conditional configurations, and dependency injection working together.

Once an app adds databases, queues, or external clients, integration tests may need fake or embedded infrastructure. When only testing conditions, `ApplicationContextRunner` is smaller and faster to iterate with.

## 27. Diagnosing Missing Beans When Toggling

If you hit:

~~~text
No qualifying bean of type 'DeliverySender'
~~~

check:

1. Is the full property name really `features.delivery.enabled`, or is the `s` missing?
2. Is the value `true`, `false`, missing, or an unexpected string?
3. Are `havingValue="true"` / `havingValue="false"` exact?
4. Does the disabled branch have `matchIfMissing=true`?
5. Are the configuration classes scanned or imported?
6. Is a new dependency requiring a sender when neither branch matches?
7. Is a higher-precedence source (env/CLI) altering the flag?
8. Is another `@ConfigurationPropertiesScan` or `@Component` creating duplicate beans?

Run with:

~~~bash
java -jar delivery-demo.jar --debug
~~~

so Spring Boot prints the condition evaluation report. In the report, inspect the configuration class name, matched/unmatched conditions, and related details.

If using Spring Boot Actuator, the `conditions` endpoint can inspect active conditions when configured and properly access-controlled. Never expose internal diagnostics or secrets publicly.

## 28. Why Does a Condition Match Yet Bean Creation Still Fail?

A matching condition only lets Spring **attempt to create the bean**. It does not prove bean creation succeeds.

Common causes:

- `app.delivery.endpoint` is missing and `@NotNull` fails.
- `app.delivery.connect-timeout=abc` fails to bind to `Duration`.
- `app.delivery.max-attempts=0` violates `@Min(1)`.
- An HTTP client constructor throws an exception.
- A dependency such as a connection factory was not created.
- Misconfigured TLS or credentials.
- Another bean of the same type causes ambiguous injection.

These are **binding, validation, or bean-creation errors**, distinct from a condition not matching.

Separate three questions:

~~~text
Did the condition match?
    |
    v
Was the Configuration/Bean definition registered?
    |
    v
Was the bean created and initialized successfully?
~~~

If you do not yet know which layer failed, do not blindly add `matchIfMissing=true` hoping to "fix" everything.

## 29. `@ConditionalOnProperty` Does Not Evaluate Against a Bound Record

Misconception:

~~~java
@ConditionalOnProperty(
        name = "features.delivery.enabled",
        havingValue = "true")
~~~

does not cause Spring to call:

~~~java
deliveryFeatureProperties.enabled()
~~~

on a record bean before picking the condition. Spring checks the **`Environment` property**.

This means:

- The property simply needs to exist in a configuration source evaluated at the right time.
- You do not need a `@ConfigurationProperties` class just to read a single flag.
- A validator placed on a record holding `enabled` will not run before the condition is evaluated.
- Mismatches between property names in `Environment` and record bean names are not magically healed by arbitrary relaxed binding.

If feature policy requires logic more complex than string comparison, design an explicit custom condition or feature-selection layer.

## 30. Feature Flags and Security

Never treat `features.delivery.enabled=true` as a security authorization mechanism.

Flags control **bean registration** only. They do not authenticate users, authorize API calls, or safeguard secrets. When instantiating the real adapter, ensure:

- Environment-appropriate credentials.
- Least-privilege connection permissions.
- TLS/HTTPS where required.
- Bounded timeouts and retries.
- No payload or token logging.
- Tests proving production endpoints are never called in test environments.
- Controlled rollout and restart processes.

If a feature performs sensitive transactions, enforce CI/deployment guardrails to prevent accidental activation.

## 31. Migrating from the Combined Design

Suppose a module previously used:

~~~properties
app.delivery.enabled=true
app.delivery.endpoint=https://sandbox.example.org
~~~

with record:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
record DeliveryProperties(boolean enabled, URI endpoint) {}
~~~

Upgrade path:

1. Define the **default policy** for `enabled`; typically false for features with external side effects.
2. Introduce a new canonical flag, e.g., `features.delivery.enabled`.
3. Create a data record containing only endpoint/timeout/retry.
4. Extract a sender interface from the service.
5. Place real sender registration and typed config inside the enabled configuration.
6. Decide whether disabled creates a No-op or registers no bean.
7. Update Config Data, env vars, Helm charts, Docker Compose, and CI.
8. Write tests for missing/false/true/invalid flags and missing data when enabled.
9. Audit component scans/`@ConfigurationPropertiesScan` so data does not bind when disabled.
10. Plan deprecation of `app.delivery.enabled` before removing it.

If both old and new keys coexist, do not assume they act as aliases. Specify which wins, whether to warn, and when to remove the old key. Two `@ConditionalOnProperty` annotations on the same class do not create an OR condition.

## 32. Docker Compose and Kubernetes

Docker Compose:

~~~yaml
services:
  app:
    image: delivery-demo:latest
    environment:
      FEATURES_DELIVERY_ENABLED: "true"
      APP_DELIVERY_ENDPOINT: "https://sandbox.example.org"
      APP_DELIVERY_CONNECTTIMEOUT: "2s"
~~~

In a Kubernetes Deployment:

~~~yaml
env:
  - name: FEATURES_DELIVERY_ENABLED
    value: "false"
~~~

When the flag is false, you do not need to supply endpoints or credentials used solely by the real sender. When true, supply complete typed config from ConfigMaps, Secrets, or appropriate sources.

Updating a ConfigMap does not cause a standard Spring Boot process to rebuild its bean graph. A rollout/restart or a dedicated, tested refresh mechanism is normally required.

## 33. Hands-On Exercises

### Exercise 1 — Separating Data from Selection

A record has `enabled`, `directory`, and `batchSize`. Create a separate `features.export.enabled` flag and an `ExportProperties(directory, batchSize)` record.

### Exercise 2 — Off by Default

Create two conditional configuration branches with `havingValue="true"` and `havingValue="false", matchIfMissing=true`. A missing key must select No-op.

### Exercise 3 — Checking Unexpected Values

Set `features.export.enabled=maybe`. Why do neither of the two conditions match, while an annotation without `havingValue` could match? **Answer:** the default condition checks only that the property exists and does not equal `false`.

### Exercise 4 — Conditional Validation

Feature false with endpoint missing vs feature true with endpoint missing. Where should `@EnableConfigurationProperties` be placed so only the second case fails validation?

### Exercise 5 — Config Data Precedence

Base file sets `enabled=false`; CLI sets `--features.delivery.enabled=true`. Predict which branch is chosen when no higher source overrides it.

### Exercise 6 — Multiple Names

With `name={"enabled","licensed"}` and `havingValue="true"`, how many keys must match? **Answer:** both.

### Exercise 7 — Never Use Endpoints as Flags

Why does the presence of an API key or endpoint not prove a feature is permitted to run?

### Exercise 8 — Unit Testing

Use `ApplicationContextRunner` for the four cases—missing, false, true, invalid—and assert bean type or absence.

### Exercise 9 — Runtime Toggle

If decisions must vary per user and change immediately, why is `@ConditionalOnProperty` insufficient? Design a `FeatureDecisions` interface evaluated in the request flow.

### Exercise 10 — Avoiding Duplicate Beans

If `ConfiguredDeliverySender` carries `@Component` while also being created by a conditional `@Bean`, what risk arises? Fix it with a single registration path.

### Exercise 11 — Diagnostics

Condition is true yet startup fails because `app.delivery.max-attempts=0`. Is the error in condition, conversion, or validation? **Answer:** conversion to `int` succeeds; the value is rejected by Bean Validation.

### Exercise 12 — Rollout

Propose a rollout plan for a new feature so production defaults to off, tests enable it against sandbox, secrets are never logged, and rollback is tested.

## 34. Summary

- **`@ConditionalOnProperty`** selects which configuration or bean definitions are registered based on `Environment` values during Spring context initialization.
- **`@ConfigurationProperties`** models typed data supporting conversion, defaults, and validation.
- Separate `features.delivery.enabled` from `app.delivery.endpoint`, `connect-timeout`, and `max-attempts` to reduce coupling.
- Use `havingValue="true"` for strict boolean switches; otherwise any present value other than `false` can match.
- `matchIfMissing` is a **condition** default, not a property default written into `Environment`.
- To avoid binding or validating a disabled feature's data, register the record inside the enabled-conditional configuration and avoid unconditional scanning elsewhere.
- No-op fits optional features; for mandatory operations, fail fast rather than skipping silently.
- Conditions do not provide hot reload when environment variables or files change.
- Use `ApplicationContextRunner` to test on/off branches and `@SpringBootTest` to verify full wiring.
- When debugging, separately inspect effective properties, the condition report, component scanning, typed config registration, and bean creation errors.
- Feature flags do not replace security controls, Bean Validation, or per-user runtime decision providers.

## References

- [Spring Boot 3.3 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
