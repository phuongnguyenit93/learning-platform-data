# `@ConditionalOnProperty` with `havingValue` and `matchIfMissing`

In Spring Boot, not every bean or configuration needs to be registered in every environment. An application might enable email notifications only when operators allow it, create an integration with an external service only when a feature flag is enabled, or provide a default implementation only when the user has not declared a replacement bean.

`@ConditionalOnProperty` is Spring Boot's annotation used to **evaluate one or more properties in the Environment before applying a configuration or registering a bean**. The two most important attributes are:

- `havingValue`: specifies the property value that must match.
- `matchIfMissing`: specifies whether the condition is considered satisfied when the property does not exist.

Understanding these two attributes properly helps avoid a common mistake: assuming a property only needs to be "present" to enable a configuration, when its actual value might be `false`, or when the property has not been declared at all yet `matchIfMissing` causes the feature to run by default.

## 1. What Is Conditional Configuration?

A regular bean can be registered in the context whenever the configuration containing it is loaded. Sometimes, however, you want a bean to appear only when the environment meets a condition.

For example, an application has an email notification feature:

- When `notification.email.enabled=true`, register the email sender.
- When the property is `false`, do not register the email sender.
- If the property is not declared, you might choose to disable it by default so the application does not connect to SMTP unexpectedly.

Instead of checking the property inside every method:

```java
@Service
public class NotificationService {

    @Value("\${notification.email.enabled:false}")
    private boolean enabled;

    public void send(String message) {
        if (!enabled) {
            return;
        }
        // Send email...
    }
}
```

you can make the bean-registering configuration itself conditional:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "notification.email",
    name = "enabled",
    havingValue = "true"
)
public class EmailNotificationConfiguration {

    @Bean
    public EmailSender emailSender() {
        return new EmailSender();
    }
}
```

When the condition is not satisfied, this configuration is not applied and the `emailSender` bean is not registered from it. Other components can still start if they do not strictly require this dependency.

**Key difference:** `@Value` reads a value for an already-created bean to use; `@ConditionalOnProperty` decides whether a configuration/bean gets registered at all. The two mechanisms serve different purposes.

## 2. Where Is the Annotation Located and What Can It Be Used On?

`@ConditionalOnProperty` belongs to the package:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
```

It is provided by the Spring Boot auto-configuration module, not as a core Spring Framework annotation. Spring Boot applications normally get the appropriate dependency via starters and project dependency management.

The annotation can be placed on:

- **A configuration class**: the condition applies to the entire configuration class; if unsatisfied, the bean definitions declared inside that class are not applied.
- **A `@Bean` method**: the condition applies individually to the bean provided by that method.
- **An auto-configuration class**: common usage when writing starters or Spring Boot integration libraries.

Example of a bean method-level condition:

```java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "notification.email",
        name = "enabled",
        havingValue = "true"
    )
    public EmailSender emailSender() {
        return new EmailSender();
    }

    @Bean
    public SmsSender smsSender() {
        return new SmsSender();
    }
}
```

Here the condition only controls `emailSender`. `smsSender` is still declared if the configuration class is loaded normally.

If you place the annotation on the `NotificationConfiguration` class, the entire configuration class is subject to that condition.

## 3. `prefix` and `name`: Specifying Which Property to Check

Example:

```java
@ConditionalOnProperty(
    prefix = "notification.email",
    name = "enabled"
)
```

Spring Boot checks the property with the full name:

```text
notification.email.enabled
```

- `prefix` is the common prefix of the property name.
- `name` is the property name to check after the prefix.
- `value` is an alias for `name`; in new code, prefer `name` for readability.

Multiple properties can be checked:

```java
@ConditionalOnProperty(
    prefix = "notification",
    name = {"email.enabled", "provider"}
)
```

When multiple names are declared, **all listed properties must satisfy the condition** for the condition to match. This is AND logic, not just any single property matching.

Equivalent full property names:

```text
notification.email.enabled
notification.provider
```

If one property does not exist and `matchIfMissing` is false (the default), the overall condition fails.

### Prefix Writing Rules

A non-empty prefix should end logically without trailing ambiguity (Spring Boot handles dots cleanly, or you write the base prefix without a trailing dot, e.g., `app.integration.payment`). Example:

```java
@ConditionalOnProperty(
    prefix = "app.integration.payment",
    name = "enabled"
)
```

Property names should use canonical kebab-case in annotations and configuration files:

```text
app.integration.payment.enabled
```

Spring Boot supports relaxed binding for many kinds of property binding, yet you should not rely on writing arbitrary names in conditions. Using canonical names makes it easy to cross-reference between annotations, `application.yml`, environment variables, and configuration docs.

## 4. `havingValue`: Which Value Is Considered a Match?

`havingValue` specifies the property value required for the condition to match.

Example:

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "report",
    havingValue = "true"
)
```

The configuration matches only when the `feature.report` property has the value `true` according to the condition's comparison.

Common cases:

| Property value | `havingValue = "true"` | `havingValue = "false"` | `havingValue = ""` (default) |
|---|---:|---:|---:|
| `true` | Match | No match | Match |
| `false` | No match | Match | No match |
| `TRUE` | Match | No match | Match |
| `enabled` | No match | No match | Match |
| `smtp` | No match | No match | Match |
| Property missing | Depends on `matchIfMissing` | Depends on `matchIfMissing` | Depends on `matchIfMissing` |

When `havingValue` is not declared or is an empty string, the default rule is: **the property must exist and its value must not equal the string `false` (case-insensitive)**. Thus values like `enabled` or `smtp` can still match in default mode.

This is an easy point to misunderstand. If you want a feature flag to turn on only when the value is strictly boolean true, explicitly declare:

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "report",
    havingValue = "true"
)
```

Do not rely on an empty `havingValue` when a property can accept various strings.

### Example with Enum/String Values

Suppose the application selects a provider:

```properties
payment.provider=stripe
```

You can use:

```java
@ConditionalOnProperty(
    prefix = "payment",
    name = "provider",
    havingValue = "stripe"
)
```

The condition matches when the property value is `stripe`; if it is `bank`, it does not match. This works well when a property has a finite set of values and you want to register each implementation separately.

`havingValue` is a property value comparison, not a general conditional expression. If you need numeric comparisons, complex patterns, relationships across multiple properties, or dynamic logic, consider a custom condition.

## 5. `matchIfMissing`: What Happens When the Property Is Undeclared?

`matchIfMissing` has type boolean and defaults to `false`.

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "report",
    havingValue = "true",
    matchIfMissing = false
)
```

With this configuration:

- Property exists and is `true`: matches.
- Property exists and is `false`: does not match.
- Property does not exist: does not match because `matchIfMissing = false`.

If you set `matchIfMissing = true`:

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "report",
    havingValue = "true",
    matchIfMissing = true
)
```

then a missing property is treated as satisfying the condition. When the property is present, `havingValue` is still enforced as usual.

Summary table:

| Property | `havingValue="true"`, `matchIfMissing=false` | `havingValue="true"`, `matchIfMissing=true` |
|---|---:|---:|
| Missing | No match | Match |
| `true` | Match | Match |
| `false` | No match | No match |
| `enabled` | No match | No match |

**`matchIfMissing=true` does not mean every value is accepted.** It only changes how a missing property is handled. When the property is present, `havingValue` still decides whether the value is valid.

### When Should You Enable `matchIfMissing`?

- `false` (default): the feature must be enabled explicitly; suitable for optional integrations or external connections that could have side effects.
- `true`: you want the feature active by default when the user has not configured it; suitable when that is intentional, safe default behavior.

Do not choose `true` merely to avoid missing a property. Decide based on the desired behavior when the application is deployed without that configuration.

## 6. Combining `havingValue` and `matchIfMissing` Intentionally

The following four configurations have different behaviors.

### Case A — Disabled by Default, Enabled When `true`

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "export",
    havingValue = "true"
)
```

Because `matchIfMissing` defaults to false, the feature is enabled only when operators declare the property as true.

```properties
feature.export=true
```

A missing property or a property set to false will not register the bean.

### Case B — Enabled by Default, Disabled Only When `false`

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "export",
    havingValue = "true",
    matchIfMissing = true
)
```

If the property is missing, the feature is enabled. When the property is present, only `true` matches; `false` does not match.

This expresses the policy "enabled by default, explicit false disables".

### Case C — Disabled by Default, Checks That Property Has a Value Other Than `false`

```java
@ConditionalOnProperty(
    prefix = "integration",
    name = "provider"
)
```

Because `havingValue` defaults to empty and `matchIfMissing` defaults to false:

- Missing `integration.provider`: does not match.
- Value `false`: does not match.
- Value `stripe`, `bank`, `enabled`, or any non-empty string other than `false`: matches.

This condition checks presence and a non-false value; it **does not** validate that the provider is in a valid list. If only `stripe`/`bank` are allowed, use separate `havingValue` checks or a custom condition.

### Case D — Enabled by Default with Any Non-`false` Property Value

```java
@ConditionalOnProperty(
    prefix = "integration",
    name = "provider",
    matchIfMissing = true
)
```

Property missing: matches. Property present and equal to `false`: does not match. Values other than `false`: match.

This is broad behavior; if the property is a provider name, treating every string other than `false` as valid might not be what you want. Use explicit values when a property represents a choice from a finite set.

## 7. Feature Flag Example: Enabling/Disabling Email Integration

Suppose an application has an interface:

```java
public interface NotificationSender {
    void send(String recipient, String message);
}
```

Email implementation:

```java
public class EmailNotificationSender implements NotificationSender {

    private final MailClient mailClient;

    public EmailNotificationSender(MailClient mailClient) {
        this.mailClient = mailClient;
    }

    @Override
    public void send(String recipient, String message) {
        mailClient.send(recipient, message);
    }
}
```

Conditional bean configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "notification.email",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class EmailNotificationConfiguration {

    @Bean
    public MailClient mailClient(MailProperties properties) {
        return new MailClient(
                properties.host(),
                properties.port(),
                properties.username(),
                properties.password()
        );
    }

    @Bean
    public NotificationSender emailNotificationSender(
            MailClient mailClient) {
        return new EmailNotificationSender(mailClient);
    }
}
```

When the property is enabled, both beans in the configuration are registered. When the property is disabled or missing, the configuration is not applied.

### `application.yml`

```yaml
notification:
  email:
    enabled: true
```

Disabling the feature:

```yaml
notification:
  email:
    enabled: false
```

If `notification.email.enabled` is not declared, `matchIfMissing=false` prevents the configuration from matching.

**Watch out for consumer dependencies:** if a service always requires `NotificationSender` via its constructor, when the email configuration is disabled and no other implementation exists, the application can fail with a missing bean error. Conditioning a producer without designing the consumer creates startup failures.

This can be resolved by providing a no-op implementation, conditioning the consumer as well, or injecting `ObjectProvider<NotificationSender>` if the dependency is genuinely optional. The right approach depends on business behavior.

## 8. Providing a Default Implementation with `@ConditionalOnMissingBean`

`@ConditionalOnProperty` and `@ConditionalOnMissingBean` are often used together in auto-configuration, yet they answer two different questions:

- `@ConditionalOnProperty`: has the user enabled this feature in configuration?
- `@ConditionalOnMissingBean`: has the user already provided the corresponding bean themselves?

Example of a notification library with a default implementation:

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "notification.email",
    name = "enabled",
    havingValue = "true"
)
public class EmailNotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationSender.class)
    public NotificationSender notificationSender(
            MailClient mailClient) {
        return new EmailNotificationSender(mailClient);
    }
}
```

When the property is enabled and no `NotificationSender` has been provided by the application, auto-configuration creates the default implementation. If the user registers their own `NotificationSender` bean, the missing-bean condition fails and the default bean backs off.

This can be illustrated as:

```text
notification.email.enabled == true?
          │
      ┌───┴────┐
     No       Yes
      │         │
      ▼         ▼
 Do not      Does NotificationSender already exist?
 create              │
 email bean      ┌──┴───┐
                Yes     No
                 │       │
                 ▼       ▼
             Use user  Create default
               bean      email bean
```

This combination fits starters well because applications control enabling the integration via properties while retaining the ability to replace the default implementation.

## 9. Placing Conditions on a Class vs. a `@Bean` Method

Where you place the annotation determines the scope of impact.

### Condition on a Configuration Class

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "feature",
    name = "analytics",
    havingValue = "true"
)
public class AnalyticsConfiguration {

    @Bean
    public AnalyticsClient analyticsClient() {
        return new AnalyticsClient();
    }

    @Bean
    public AnalyticsService analyticsService(
            AnalyticsClient client) {
        return new AnalyticsService(client);
    }
}
```

If the condition fails, the configuration class is not applied; neither bean method inside the class provides a bean.

### Condition on Individual Methods

```java
@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "feature",
        name = "analytics",
        havingValue = "true"
    )
    public AnalyticsClient analyticsClient() {
        return new AnalyticsClient();
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "feature",
        name = "audit",
        havingValue = "true"
    )
    public AuditClient auditClient() {
        return new AuditClient();
    }
}
```

Each bean method has an independent condition. Analytics can be enabled without enabling audit.

However, if one bean method unconditionally requires a dependency provided conditionally by another method, ensure the conditions are consistent. For example, `AnalyticsService` should not unconditionally require `AnalyticsClient` if the client can be turned off.

## 10. Multiple Properties: All Conditions Must Be Satisfied

`name` can contain multiple properties:

```java
@ConditionalOnProperty(
    prefix = "app.integration",
    name = {"enabled", "provider"},
    havingValue = "true"
)
```

This style is unsuitable if `enabled` is boolean while `provider` is a name like `stripe`, because `havingValue` applies to every property. If `havingValue="true"` is set, both properties would have to equal `true`.

To express two conditions with different values, use separate condition annotations or split configuration classes:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "app.integration",
    name = "enabled",
    havingValue = "true"
)
public class IntegrationConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.integration",
        name = "provider",
        havingValue = "stripe"
    )
    public PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "app.integration",
        name = "provider",
        havingValue = "bank"
    )
    public PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

Here:

1. The configuration is only applied if integration is enabled.
2. Only one of the two provider beans is registered if the property has a matching value.
3. If provider is neither `stripe` nor `bank`, the configuration may be loaded, yet neither gateway bean is registered from those two methods.

If a consumer requires `PaymentGateway`, define behavior for invalid or missing providers.

## 11. `matchIfMissing` with Multiple Property Names

When declaring multiple `name`s, all must match. If `matchIfMissing=true`, missing properties are considered to satisfy their respective condition; present properties must still satisfy `havingValue`.

Example:

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = {"reports", "enabled"},
    havingValue = "true",
    matchIfMissing = true
)
```

For the condition to match, each listed property must:

- Have the value `true`; or
- Not exist while `matchIfMissing=true`.

If `feature.reports=false`, the condition does not match even if `feature.enabled` is missing. `matchIfMissing` does not override an existing value that fails to match.

Although valid, declaring multiple properties sharing `havingValue` can be hard to read if the properties represent different data types. Split conditions or use a custom condition so each condition has clear meaning.

## 12. Where Do Properties Come From?

`@ConditionalOnProperty` checks properties through Spring's `Environment`. Properties can come from many sources, such as:

- `application.properties`.
- `application.yml`.
- Profile-specific configuration files like `application-prod.yml`.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Property sources registered by the application or tests.

`application.properties` example:

```properties
feature.invoice.enabled=true
```

YAML example:

```yaml
feature:
  invoice:
    enabled: true
```

An environment variable on the deployment system can represent the property using Spring Boot's relaxed binding convention, for example:

```text
FEATURE_INVOICE_ENABLED=true
```

Command line:

```bash
java -jar app.jar --feature.invoice.enabled=true
```

Property sources have an order of precedence. If the same property appears in multiple sources, the effective value depends on `Environment` precedence. When a condition yields an unexpected result, check the **effective value at startup**, not just the configuration file you currently have open.

`@ConditionalOnProperty` is evaluated during configuration processing. Modifying configuration files after the context is initialized does not automatically register or unregister beans. Changing feature flags at runtime requires a different design, such as a dynamic configuration/feature flag service; conditions are mainly for context creation decisions.

## 13. Profile-Based Properties and Conditions

You can combine `@Profile` and `@ConditionalOnProperty`, with each annotation expressing a different condition dimension:

- `@Profile`: configuration applies only when the profile is activated.
- `@ConditionalOnProperty`: configuration applies only when the property has a matching value.

Example:

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
@ConditionalOnProperty(
    prefix = "payment.gateway",
    name = "enabled",
    havingValue = "true"
)
public class ProductionPaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

Both conditions must be satisfied: the `prod` profile is active and `payment.gateway.enabled=true`.

You can use profiles to choose environment-specific configuration groups and properties to toggle features within that environment. Avoid replacing all feature flags with profiles when the real need is toggling individual features independently.

## 14. `havingValue` Is a String Comparison, Not a General Boolean Expression

A property is often written like a boolean:

```properties
feature.cache.enabled=true
```

However, `@ConditionalOnProperty` checks property values as strings. It does not evaluate expressions such as:

- `count > 10`.
- `provider in (stripe, bank)`.
- `url startsWith https`.
- `enabled == true && region == ap-southeast-1`.

For complex conditions, you can:

1. Split into multiple configurations/bean methods with simple conditions.
2. Use `@ConditionalOnExpression` if a SpEL expression is truly appropriate and maintainable.
3. Write a custom condition implementing `Condition` or using `SpringBootCondition` for clear logic and helpful messages.

Do not write complicated SpEL just to avoid writing a small custom condition. Bean registration conditions should be easy to understand and diagnose.

## 15. Limitations with Collection or Indexed Value Properties

`@ConditionalOnProperty` is suitable for single scalar properties such as booleans, strings, or single values. The annotation **is not guaranteed to work properly to detect a collection property solely via indexed keys**.

Example configuration:

```properties
app.servers[0]=server-a
app.servers[1]=server-b
```

You may see keys `app.servers[0]` and `app.servers[1]`, without necessarily having a root `app.servers` property. A condition checking `name = "servers"` may not match as expected.

If you need to check collections/lists/maps, consider:

- Binding configuration with `@ConfigurationProperties`.
- Writing a custom `Condition` that reads the property structure appropriately.
- Using a separate scalar property, such as `app.servers.enabled`, as an on/off flag.

Keep this limitation in mind so you do not use `@ConditionalOnProperty` for data structures it was not designed to inspect.

## 16. Differences Between `@ConditionalOnProperty` and `@ConditionalOnMissingBean`

Both annotations can appear together in an auto-configuration, yet they inspect two different sources of information:

| Annotation | Checks | Question |
|---|---|---|
| `@ConditionalOnProperty` | Value in `Environment` | Has the operator enabled this configuration? |
| `@ConditionalOnMissingBean` | Matching bean definitions/beans in context | Has the application already provided a replacement bean? |
| `@ConditionalOnClass` | Classpath | Is the required library present? |
| `@ConditionalOnBean` | Matching bean already registered | Is the dependent integration available? |

Example auto-configuration for a client:

```java
@AutoConfiguration
@ConditionalOnClass(RemoteClient.class)
@ConditionalOnProperty(
    prefix = "remote.client",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class RemoteClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public RemoteClient remoteClient(RemoteClientProperties properties) {
        return new RemoteClient(properties.endpoint());
    }
}
```

The class-level conditions require the library on the classpath and the property enabled. The bean-method condition creates the default client only when the application does not already have a `RemoteClient` bean.

Auto-configuration ordering and condition evaluation timing matter, especially for bean-based conditions. When writing starters, follow Spring Boot conventions and inspect the report instead of assuming all user-declared beans are visible in every phase.

## 17. Safe and Operable Property Configuration

Feature flags and integration properties often affect external connections or operational costs. Design configurations clearly:

```yaml
app:
  notification:
    email:
      enabled: false
      host: \${MAIL_HOST:localhost}
      port: \${MAIL_PORT:1025}
```

Here email is disabled by default. When enabling it is needed, operators set:

```text
APP_NOTIFICATION_EMAIL_ENABLED=true
MAIL_HOST=smtp.example.net
MAIL_PORT=587
```

Placeholder usage in the example illustrates configuration structure; actual secrets should come from a secret manager or appropriate deployment environment, never committed as passwords in source repositories.

Some principles:

- Document defaults and sample configurations.
- For integrations with side effects, usually default to off if not fully configured.
- Use `havingValue="true"` to enable only on an explicit boolean value.
- Set `matchIfMissing` explicitly when default behavior matters.
- Do not confuse a "declared" property with a "validated" property.
- Validate configuration values using `@ConfigurationProperties`/validation when needed; conditions do not replace validation.

## 18. Verifying Behavior with Tests

You can use `ApplicationContextRunner` to test auto-configuration across property combinations. This is a clean approach when writing libraries or starters.

Example:

```java
class EmailNotificationAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            EmailNotificationAutoConfiguration.class
                    ));

    @Test
    void createsSenderWhenEnabled() {
        contextRunner
                .withPropertyValues(
                        "notification.email.enabled=true"
                )
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);
                });
    }

    @Test
    void doesNotCreateSenderWhenDisabled() {
        contextRunner
                .withPropertyValues(
                        "notification.email.enabled=false"
                )
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(NotificationSender.class);
                });
    }

    @Test
    void doesNotCreateSenderWhenPropertyIsMissing() {
        contextRunner.run(context -> {
            assertThat(context)
                    .doesNotHaveBean(NotificationSender.class);
        });
    }
}
```

The example assumes `EmailNotificationAutoConfiguration`, `NotificationSender`, and the appropriate dependencies and test libraries exist. `ApplicationContextRunner` spins up a lightweight context with specific properties without starting an entire web server.

If testing a `matchIfMissing=true` configuration, add a test for the missing property case and confirm the bean is present. Do not test only true/false while forgetting the missing case, since that is the exact distinction of this attribute.

### Testing with `@SpringBootTest`

In application integration tests, you can specify properties right on the test:

```java
@SpringBootTest(properties = {
    "feature.report.enabled=true"
})
class ReportFeatureTests {
    // ...
}
```

Or test the disabled case:

```java
@SpringBootTest(properties = {
    "feature.report.enabled=false"
})
class ReportFeatureDisabledTests {
    // ...
}
```

Each test context should be configured with the desired properties. Spring Test can cache application contexts by configuration; do not mutate the Environment after a context has refreshed and expect conditions to be re-evaluated.

## 19. Debugging Non-Matching Conditions

When a bean does not appear, do not immediately guess `havingValue` is wrong. Check in order:

1. **Was the configuration class loaded?** Did component scanning, imports, or auto-configuration metadata bring it into the context?
2. **Is the property name exact?** Combine `prefix` and `name`, checking dots, spelling, and canonical kebab-case.
3. **Does the property exist in Environment?** Profile files, environment variables, command-line arguments, and property source precedence can alter values.
4. **What is the actual value?** `true`, `false`, `enabled`, empty string, or missing?
5. **What does `havingValue` require?** If empty, the default matches any present value except `false`.
6. **Is `matchIfMissing` enabled?** When the property is missing, behavior may be the opposite of expectations.
7. **Are there multiple properties in `name`?** All must match.
8. **Is the condition on the class or method?** Identify the scope of affected beans.
9. **Is another condition blocking it?** `@Profile`, `@ConditionalOnClass`, `@ConditionalOnBean`, or `@ConditionalOnMissingBean` may affect the outcome.

### Enabling the Condition Evaluation Report

Run the application with `--debug`:

```bash
java -jar app.jar --debug
```

Or set:

```properties
debug=true
```

Spring Boot can print the **conditions evaluation report**, showing applied and non-applied auto-configurations along with the reason a condition did not match.

If the condition is on a regular application-written `@Configuration`, logs/reports might not display details as thoroughly as for auto-configuration. In that case, inspect the Environment, loaded configurations, and bean definitions directly in tests/context.

### Observing the Effective Property Value

In a runner or debug session, you can read the property:

```java
@Component
public class FeaturePropertyInspector implements ApplicationRunner {

    private final Environment environment;

    public FeaturePropertyInspector(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String enabled = environment.getProperty(
                "notification.email.enabled"
        );
        System.out.println("notification.email.enabled = " + enabled);
    }
}
```

This shows the value resolved by the Environment. Do not print secrets or the entire environment to production logs.

## 20. Common Pitfalls

| Symptom | Possible cause | How to handle |
|---|---|---|
| Property is `true` yet bean is missing | Wrong `prefix`/`name`, configuration not loaded, or another condition failed. | Check full property name, Environment, and conditions report. |
| Property is `false` yet configuration still matches | With default `havingValue`, `false` does not match; the bean likely comes from another registration source. | Find other components/configurations also registering a bean of the same type. |
| Property undeclared yet feature is still active | `matchIfMissing=true` or another condition registered the bean. | Check if default is intentional and inspect all bean sources. |
| `havingValue="true"` yet value `enabled` does not match | Property has a value other than `true`, such as `yes`, `1`, `enabled`, or empty string. | Use canonical `true`/`false` values or define explicit enums. |
| Condition has multiple properties yet only one is configured | All properties in `name` must satisfy the condition. | Supply missing properties or split conditions. |
| Missing bean causes application startup failure | Consumer unconditionally requires the bean even when feature is off. | Condition the consumer, provide a no-op bean, or use a provider for optional dependencies. |
| Collection property is not detected | Annotation is not designed to inspect indexed collections that way. | Use `@ConfigurationProperties` or a custom condition. |
| Property changes at runtime yet beans do not change | Conditions are evaluated during context construction. | Use dynamic configuration/runtime feature flags if needed. |
| Tests pass yet production condition differs | Different property sources, profiles, or precedence. | Inspect effective values in the actual deployment environment. |

## 21. Practice Exercises

### Exercise A — Testing `havingValue`

Create a `ReportClient` bean with:

```java
@Bean
@ConditionalOnProperty(
    prefix = "feature",
    name = "report",
    havingValue = "true"
)
public ReportClient reportClient() {
    return new ReportClient();
}
```

Try the properties:

- Undeclared.
- `feature.report=true`.
- `feature.report=false`.
- `feature.report=enabled`.

Record in which cases the bean is registered and explain using the `havingValue` rule.

### Exercise B — Testing `matchIfMissing`

Keep the condition above and set in turn:

- `matchIfMissing=false`.
- `matchIfMissing=true`.

Only remove the property without changing other values. Observe the difference in context when the property is missing.

### Exercise C — Default Empty `havingValue`

Omit the `havingValue` attribute. Try properties equal to `true`, `false`, `enabled`, `smtp`, and empty string. Compare with the table in section 4.

### Exercise D — Two Properties Together

Declare `name = {"email.enabled", "email.provider"}` and test various values. Explain why applying the same `havingValue` to both names may fail to express intent if one property is boolean and the other is a provider name.

### Exercise E — Combining with Missing Bean

Create an auto-configuration enabled only when `feature.client.enabled=true`, while only creating a default client when no `Client` bean exists yet. Declare a replacement bean in the application and observe the back-off behavior.

### Exercise F — Checking Property Precedence

Set the same property in `application.yml`, a profile-specific file, and the command line with different values. Run the application and determine which value Environment uses to evaluate the condition.

## 22. Principles to Remember

1. **`@ConditionalOnProperty` checks properties in Spring Environment** to decide whether a configuration or bean method should be applied.
2. **`prefix` + `name`** form the full property name; use canonical kebab-case and clear naming.
3. **Default empty `havingValue`** means the property must exist and not equal `false`; when you want explicit boolean true, write `havingValue="true"`.
4. **`matchIfMissing` defaults to false**; when enabled as true, a missing property is treated as satisfying the condition.
5. `matchIfMissing=true` does not make `false` or a value failing `havingValue` valid.
6. If multiple properties are in `name`, **all must match**.
7. A condition on a configuration class affects the entire configuration; a condition on a `@Bean` method affects only that bean method.
8. `@ConditionalOnProperty` does not replace `@ConfigurationProperties` validation and is not suited for checking indexed collections.
9. Conditions are evaluated during context construction; runtime property changes do not automatically register or unregister beans.
10. When writing auto-configuration, property conditions are often combined with `@ConditionalOnClass` and `@ConditionalOnMissingBean` to provide controlled defaults.

When using this annotation, clearly define three things upfront: **which property is checked, which values are accepted, and what the application should do when the property is missing**. Writing `havingValue` and `matchIfMissing` explicitly when default behavior matters will make Spring Boot configurations easier to read, test, and operate.
