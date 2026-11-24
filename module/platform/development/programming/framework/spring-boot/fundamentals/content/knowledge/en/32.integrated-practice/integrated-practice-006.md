# Switching Implementations via Profile or Property

In Spring Boot, the same functionality can have multiple implementations. An application might send real emails in production, log notifications to the console during development, or disable an integration in test environments. A common approach is selecting beans using **Spring Profiles**; another is selecting via **properties**.

The two mechanisms are related but express different intents:

- **Profile** describes an activated configuration group or environment, such as local, test, staging, or prod.
- **Property** describes a specific choice or parameter, such as app.notification.provider=smtp, app.feature.invoice-export.enabled=false, or app.payment.timeout=3s.

Switching an implementation from a profile to a property is not just changing @Profile to @ConditionalOnProperty. First, determine whether the choice genuinely depends on the **deployment environment** or on an **independent capability/configuration**. If an environment can toggle a feature without changing the whole configuration set, a property usually expresses that better. If many beans and configuration files must change together per environment, a profile is usually a better fit.

This practice lesson uses a notification feature to walk through both designs, convert between them, test configuration branches, handle missing/duplicate beans, and choose the right mechanism for real applications.

## 1. Problem: One Interface, Multiple Implementations

Suppose the application needs to send a notification when an order is created. In local development, we only want to write the content to the console. In production, the application uses SMTP.

Define the contract:

~~~java
package com.example.notification;

public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

Local implementation:

~~~java
package com.example.notification;

public class ConsoleNotificationSender
        implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.printf(
                "[LOCAL] To=%s, message=%s%n",
                recipient,
                message);
    }
}
~~~

Production implementation:

~~~java
package com.example.notification;

public class SmtpNotificationSender
        implements NotificationSender {

    private final SmtpClient client;

    public SmtpNotificationSender(SmtpClient client) {
        this.client = client;
    }

    @Override
    public void send(String recipient, String message) {
        client.send(recipient, message);
    }
}
~~~

Here `SmtpClient` is a collaborator provided by the application or a mail library. The example focuses on implementation selection rather than implementing the SMTP protocol.

The business service depends only on the interface:

~~~java
package com.example.order;

import com.example.notification.NotificationSender;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationService {

    private final NotificationSender sender;

    public OrderNotificationService(NotificationSender sender) {
        this.sender = sender;
    }

    public void orderCreated(String email, String orderNumber) {
        sender.send(
                email,
                "Your order " + orderNumber + " has been created.");
    }
}
~~~

OrderNotificationService does not need to know which profile or property selected the implementation. This is a key principle: **wiring decisions belong to configuration**, while business services depend on stable contracts.

## 2. First Approach: Selecting Implementations with @Profile

@Profile restricts registration of a bean or configuration class to active profiles.

Example:

~~~java
package com.example.notification;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class NotificationProfileConfiguration {

    @Bean
    @Profile("local")
    NotificationSender consoleNotificationSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @Profile("prod")
    NotificationSender smtpNotificationSender(SmtpClient client) {
        return new SmtpNotificationSender(client);
    }
}
~~~

When the local profile is active, the console bean is registered. When the prod profile is active, the SMTP bean is registered.

### 2.1. Activating a Profile

Profiles can be activated via the command line:

~~~bash
java -jar order-api.jar --spring.profiles.active=local
~~~

Or an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Or in application.yml:

~~~yaml
spring:
  profiles:
    active: local
~~~

In real deployments, let the launcher/deployment supply the profile per environment. Do not hard-code prod in Java code.

### 2.2. Default Profile

If no profile is explicitly activated, Spring may use the default profile. @Profile("local") does not match automatically just because the app runs on a developer's machine.

If you want a bean selected when no profile is active, you can use:

~~~java
@Bean
@Profile("default")
NotificationSender consoleNotificationSender() {
    return new ConsoleNotificationSender();
}
~~~

However, do not use the default profile as an implicit way for production to fall back to local configuration. Critical environments should be declared explicitly.

### 2.3. Profile Expressions

@Profile supports profile expressions:

~~~java
@Profile("staging | prod")
~~~

The bean matches when either staging or prod is active.

~~~java
@Profile("!test")
~~~

The bean matches when the test profile is not active.

~~~java
@Profile("prod & !maintenance")
~~~

The bean matches when prod is active and maintenance is inactive.

You can use these expressions, but avoid overly complex conditions. If you have to read several profile expressions to figure out which bean gets created, the configuration is becoming hard to operate.

## 3. Using Profile-Specific Configuration Files

Profiles do more than select beans. They also allow loading environment-specific configuration files.

Example:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-test.yml
├── application-staging.yml
└── application-prod.yml
~~~

application.yml holds shared configuration:

~~~yaml
spring:
  application:
    name: order-api

app:
  notification:
    enabled: true
~~~

application-local.yml:

~~~yaml
app:
  notification:
    provider: console
~~~

application-prod.yml:

~~~yaml
app:
  notification:
    provider: smtp
~~~

When prod is active, Spring Boot loads the base configuration together with the corresponding profile-specific configuration according to Config Data and precedence rules.

### 3.1. Choosing a Profile and Choosing a Property Are Separate Concerns

Suppose:

~~~bash
java -jar order-api.jar --spring.profiles.active=prod
~~~

This command selects the prod profile. The value app.notification.provider=smtp may come from application-prod.yml, yet which bean actually gets created still depends on code/configuration conditions.

A profile does not automatically turn a class into an SMTP sender if that class lacks @Profile, @ConditionalOnProperty, or a matching registration mechanism.

### 3.2. Profile Groups

An environment may need to activate several sub-profiles together. Spring Boot supports profile groups:

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod-database
        - prod-notifications
        - observability
~~~

When production is activated, the profiles in the group are activated too.

Profile groups are helpful when one environment name represents multiple configuration slices that must be enabled together. Do not create a profile group just to set a single property.

### 3.3. spring.profiles.include

spring.profiles.include can add profiles to the active profile set:

~~~yaml
spring:
  profiles:
    include:
      - common-metrics
~~~

Inclusion follows Spring Boot's specific rules and can combine with profile groups. If used, verify the actual active profiles at startup; do not assume only a single profile is active.

### 3.4. Do Not Declare spring.profiles.active Inside a Profile-Specific Document

Properties like spring.profiles.active and spring.profiles.include govern profile selection and should not be placed arbitrarily inside documents already activated by a profile-specific condition.

Put profile selection in an appropriate bootstrap configuration source such as command line, environment, or a profile-independent document.

## 4. When Is @Profile a Good Choice?

Profiles fit when an environment needs a **consistent bundle of configuration and wiring**.

For example:

| Profile | Database | Notification | External integrations |
|---|---|---|---|
| local | H2 or local database | Console/fake | Stub |
| test | Test database/container | Fake | Mock/stub |
| staging | Staging database | SMTP sandbox | Staging endpoints |
| prod | Production database | Real SMTP/provider | Production endpoints |

One profile can select multiple beans at once:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("test")
public class TestInfrastructureConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    NotificationSender notificationSender() {
        return new RecordingNotificationSender();
    }
}
~~~

Here the test profile represents a cohesive test infrastructure bundle. That makes more sense than adding separate properties for every fake bean if all of them must be enabled together during tests.

### 4.1. Profiles Should Not Represent Every Feature Flag

Suppose production can toggle invoice export without changing the database, mail server, or other settings. Creating prod-with-export and prod-without-export profiles would cause combinations to explode quickly.

For an independent option like that, a property is much easier to manage:

~~~yaml
app:
  invoice-export:
    enabled: false
~~~

### 4.2. Do Not Use Profiles for Per-Request Selection

Profiles are determined in the ApplicationContext's Environment, typically at startup. They are not a mechanism for each request to pick an implementation by user, tenant, or order type.

If one application serves multiple tenants with different providers inside the same process, use a factory/strategy registry, routing logic, or tenant-scoped configuration. Never mutate active profiles between requests.

## 5. Converting from @Profile to @ConditionalOnProperty

If implementation selection is genuinely an independent option, you can migrate bean registration to properties.

Spring Boot provides:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionalOnProperty
~~~

Example:

~~~java
@Configuration(proxyBeanMethods = false)
public class NotificationPropertyConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "console",
            matchIfMissing = true)
    NotificationSender consoleNotificationSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "smtp")
    NotificationSender smtpNotificationSender(SmtpClient client) {
        return new SmtpNotificationSender(client);
    }
}
~~~

Configuration:

~~~yaml
app:
  notification:
    provider: smtp
~~~

When provider is smtp, the SMTP bean is registered. If the property is absent, the console branch matches because matchIfMissing=true.

### 5.1. Meaning of havingValue

havingValue requires the property to have a matching value for the condition to match.

~~~java
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "enabled",
        havingValue = "true")
~~~

Matches only when app.notification.enabled=true.

If havingValue is omitted, the condition matches by default when the property exists and its value is not false. For readability, explicitly specify havingValue = "true" or "false" for boolean flags.

### 5.2. Meaning of matchIfMissing

By default, matchIfMissing=false. If the property is absent, the condition does not match.

~~~java
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "provider",
        havingValue = "console",
        matchIfMissing = true)
~~~

allows selecting console as a fallback when operators have not declared a provider.

Only use matchIfMissing=true when that default is safe and intentional. For integrations that send real emails, charge money, or write production data, an implicit default may be inappropriate.

### 5.3. Non-Matching Property May Result in No Bean

If:

~~~yaml
app:
  notification:
    provider: push
~~~

yet conditions only exist for console and smtp, no NotificationSender bean will be created from this configuration.

If OrderNotificationService requires injecting NotificationSender, context initialization will fail. That can be sensible fail-fast behavior, though the error message should help operators recognize an unsupported provider value.

Do not add an arbitrary default implementation just so the application starts with an invalid configuration.

## 6. Separating Feature Flags from Provider Selection

One property can answer "is the feature enabled?", while another answers "if enabled, which provider should be used?".

Example:

~~~yaml
app:
  notification:
    enabled: true
    provider: smtp
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "enabled",
            havingValue = "true")
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "smtp")
    NotificationSender smtpNotificationSender(SmtpClient client) {
        return new SmtpNotificationSender(client);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "enabled",
            havingValue = "true")
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "console")
    NotificationSender consoleNotificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

Here both conditions on the same bean method must match. When enabled=false, neither implementation is registered by these two methods.

If the business service still requires a NotificationSender, disabling the feature will cause the context to fail. In that case, decide on an explicit design:

- Do not create the service using NotificationSender when the feature is disabled.
- Provide a No-op implementation if "do not send" is valid behavior.
- Or keep the bean and have the service inspect feature state under a clear contract.

Do not let a feature flag create an un-bootable bean graph.

## 7. Using a No-op Implementation When Disabling the Feature Is Valid

If business requirements allow the application to keep running without sending notifications, you can provide an implementation with no side effects:

~~~java
package com.example.notification;

public class NoOpNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        // Intentionally do not send.
    }
}
~~~

Register the bean when the feature is disabled:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "enabled",
        havingValue = "false")
NotificationSender noOpNotificationSender() {
    return new NoOpNotificationSender();
}
~~~

Then OrderNotificationService still receives exactly one NotificationSender. The "do not send" behavior is represented by a concrete implementation rather than making the dependency disappear.

### 7.1. When Is No-op Inappropriate?

No-op is only valid if skipping the action is an acceptable business behavior. Do not use it to mask failures for:

- Payments or refunds.
- Mandatory audit logging.
- Required security alerts.
- Saving non-reconstructible data.
- State synchronization that must be guaranteed.

In those cases, disabling the feature must clarify whether the system is allowed to run. Either fail fast at startup or block the corresponding business flow.

### 7.2. Selection Matrix When `enabled` Is Used

| enabled | provider | Expected bean |
|---|---|---|
| true | console | ConsoleNotificationSender |
| true | smtp | SmtpNotificationSender |
| false | any/unused | NoOpNotificationSender |

If the provider property is unnecessary when enabled=false, avoid configurations that mislead operators into thinking a provider is still active.

## 8. Step-by-Step Conversion from Profile to Property

Suppose the current setup has:

~~~java
@Bean
@Profile("local")
NotificationSender consoleNotificationSender() {
    return new ConsoleNotificationSender();
}

@Bean
@Profile("prod")
NotificationSender smtpNotificationSender(SmtpClient client) {
    return new SmtpNotificationSender(client);
}
~~~

The new goal is allowing provider selection independent of environment:

~~~yaml
app:
  notification:
    provider: console
~~~

or:

~~~yaml
app:
  notification:
    provider: smtp
~~~

### Step 1 — Clarify the Meaning of the Choice

Ask: must local always use console and prod always use SMTP, or does production sometimes need a different provider, staging need its own provider, and test need a recording fake?

If the choice is rigidly tied to environment bundles, keep profiles. If it is an independent decision, properties are more flexible.

### Step 2 — Define Key and Allowed Values

Pick a stable key:

~~~text
app.notification.provider
~~~

And values:

~~~text
console
smtp
~~~

Avoid unnecessary aliases like mail, email, smtp-mail, and real-mail pointing to the same implementation. Configuration values should have a small, documented vocabulary.

### Step 3 — Convert Bean Registration

~~~java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "console")
    NotificationSender consoleNotificationSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "smtp")
    NotificationSender smtpNotificationSender(SmtpClient client) {
        return new SmtpNotificationSender(client);
    }
}
~~~

In this strict migration example, matchIfMissing=true is omitted so a missing property leaves the context without a sender. You can choose an explicit default if product requirements allow; test that policy.

### Step 4 — Update Environment-Specific Configurations

application-local.yml:

~~~yaml
app:
  notification:
    provider: console
~~~

application-prod.yml:

~~~yaml
app:
  notification:
    provider: smtp
~~~

Profiles can still load environment configuration files while properties select implementations. This combined pattern is often clean: **profiles select the config bundle; properties within that bundle select individual capabilities**.

### Step 5 — Check Where Properties Are Overridden

A command-line argument can override files:

~~~bash
java -jar order-api.jar \
  --spring.profiles.active=prod \
  --app.notification.provider=console
~~~

Under default precedence, command-line properties override values in application-prod.yml. This is useful for intentional testing or operations, but can also cause production to use the wrong provider if a launcher passes a bad argument.

### Step 6 — Remove Old Annotations/Profiles

Once property-based configuration completely replaces profile-based bean registration, delete or stop importing the old configuration.

If both remain active:

- The local profile might register the console bean.
- Property provider=smtp might register the SMTP bean as well.
- A service injecting NotificationSender could hit NoUniqueBeanDefinitionException.

Do not rely on @Primary to mask two competing selector configurations. Each feature should have one clear source deciding the implementation.

### Step 7 — Test All Branches Before Deployment

At minimum, test:

- provider=console creates the console sender.
- provider=smtp creates the SMTP sender.
- Missing property behaves per the chosen policy.
- Unsupported provider does not silently select another implementation.
- Environment profiles still load the expected provider values.

## 9. When Should You Convert from Property to Profile?

Going the other direction can also make sense. Suppose a single property:

~~~yaml
app:
  integration:
    use-stub: true
~~~

is being used to select multiple fake clients together in tests:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.integration",
        name = "use-stub",
        havingValue = "true")
PaymentGateway fakePaymentGateway() {
    return new FakePaymentGateway();
}

@Bean
@ConditionalOnProperty(
        prefix = "app.integration",
        name = "use-stub",
        havingValue = "true")
NotificationSender recordingSender() {
    return new RecordingNotificationSender();
}
~~~

If the test profile always needs both fake payment and recording notification simultaneously, a profile expresses the configuration bundle more cleanly:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("test")
public class TestIntegrationConfiguration {

    @Bean
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    NotificationSender recordingSender() {
        return new RecordingNotificationSender();
    }
}
~~~

### 9.1. Signs a Property Is Simulating an Environment

- A boolean property was added solely to toggle a group of fake beans.
- Multiple properties must always change together for an environment to function.
- Each deployment uses a nearly fixed combination of properties.
- Configuration files are duplicated due to lack of profile grouping.

In such cases, profiles or profile groups may be a clearer model.

### 9.2. Do Not Convert Properties to Profiles If Choices Remain Independent

If production can toggle export, audit, or an individual integration without changing the rest of the configuration, keep properties. Do not create a profile for every combination of feature flags.

For instance, with 5 independent features, creating profiles for every combination could require up to 2^5 combinations. Properties let each choice be managed separately.

## 10. Combining Profiles and Properties in the Same Application

You do not need to force all configuration onto one mechanism. The two complement each other.

Example:

~~~yaml
# application.yml
spring:
  application:
    name: order-api

app:
  notification:
    enabled: true
~~~

~~~yaml
# application-local.yml
app:
  notification:
    provider: console
~~~

~~~yaml
# application-prod.yml
app:
  notification:
    provider: smtp
    enabled: true
~~~

Profiles select configuration files per environment. The provider property selects the bean. The enabled property toggles the capability.

### 10.1. Avoid Contradictory Selectors

An unclear example:

~~~java
@Bean
@Profile("prod")
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "provider",
        havingValue = "console")
NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}
~~~

The bean is only registered when **both** conditions match: prod is active and provider=console. That might be intentional in a special edge case, but if the goal is selecting a provider across all environments, @Profile("prod") unnecessarily restricts the bean.

When combining conditions, make it clear they act as AND conditions on the same bean/configuration. If OR logic is needed, express it with a profile expression or appropriate configuration/condition structure, and test each branch.

### 10.2. Using Profile-Specific Property Values to Avoid Profile Conditions in Code

A maintainable pattern:

- Java configuration only understands app.notification.provider.
- application-local.yml sets provider=console.
- application-prod.yml sets provider=smtp.
- No need to repeat @Profile on each implementation.

As a result, if staging needs console or an SMTP sandbox, you only change the property in the staging file without editing bean-selector code.

## 11. Grouping Related Properties with @ConfigurationProperties

When configuration has multiple fields, avoid scattering @Value across services. Use a configuration properties class to represent the configuration contract.

Example:

~~~java
package com.example.notification;

import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        @NotNull NotificationProvider provider,
        boolean enabled) {
}
~~~

Enum:

~~~java
package com.example.notification;

public enum NotificationProvider {
    CONSOLE,
    SMTP
}
~~~

Register properties:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationPropertyConfiguration {
    // Conditional @Bean methods here.
}
~~~

In application.yml:

~~~yaml
app:
  notification:
    enabled: true
    provider: SMTP
~~~

Spring Boot's Binder can convert the property value into the corresponding enum. If the value is invalid or provider is missing while annotated with @NotNull, binding/validation reports an error instead of passing an ambiguous configuration to services.

### 11.1. Validation Dependency

To use Jakarta Bean Validation annotations like @NotNull, the project needs a validation provider, typically via:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

Constraint annotations without a validation provider will not guarantee validation is enforced.

### 11.2. A Properties Class Does Not Select Beans by Itself

NotificationProperties only binds and validates values. Whether ConsoleNotificationSender or SmtpNotificationSender gets registered is still decided by configuration conditions.

You can inject properties into services if they need runtime settings, but do not write a service that instantiates implementations with new just because it received the properties object. Let Spring configuration wiring handle bean selection.

### 11.3. Avoid Two Sources of Truth

Do not simultaneously have:

~~~yaml
app:
  notification:
    provider: smtp
~~~

and a profile-based configuration that unconditionally registers ConsoleNotificationSender in prod. Two selectors will conflict.

One property key may be supplied by multiple property sources, but **the implementation selection rule must have one single contract**.

## 12. Putting Feature Flags in Properties and Selecting Beans Intentionally

You can split provider and enabled into two parts:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationBeansConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "enabled",
            havingValue = "true")
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "CONSOLE")
    NotificationSender consoleSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "enabled",
            havingValue = "true")
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "SMTP")
    NotificationSender smtpSender(SmtpClient client) {
        return new SmtpNotificationSender(client);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "enabled",
            havingValue = "false")
    NotificationSender noOpSender() {
        return new NoOpNotificationSender();
    }
}
~~~

This example uses uppercase enum text in properties to align with the enum. If you prefer lowercase configuration like smtp, you can use strings and normalize/validate per application conventions; do not assume every conversion/custom condition shares identical semantics.

Note: @ConditionalOnProperty can be repeated on the same method as a repeatable annotation. All conditions must match for the bean method to be registered.

### 12.1. Testing Unsupported Values

If provider=push and no bean condition matches, property validation should also catch the invalid value. An enum property lets the Binder report a conversion error when the value is not in the enum.

If using plain Strings, add explicit validation so unexpected values do not silently leave the context missing a bean.

### 12.2. Do Not Use Arbitrary Boolean Strings

Values such as:

~~~text
yes
on
enabled
1
~~~

can cause surprises when used with conditional properties expecting a specific havingValue. Use standard true/false consistently in configuration.

## 13. Property Precedence and Overrides When Selecting Implementations

Spring Boot has multiple property sources. A property with the same key can be placed in:

- application.yml.
- application-local.yml or application-prod.yml.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Other Config Data locations/imports.

Higher-precedence sources override lower-precedence values according to Spring Boot's property source precedence.

For example, application-prod.yml:

~~~yaml
app:
  notification:
    provider: smtp
~~~

Yet the process runs with:

~~~bash
java -jar order-api.jar \
  --spring.profiles.active=prod \
  --app.notification.provider=console
~~~

The command-line property can override the value in the profile-specific file. Therefore, having the prod profile active does not guarantee the provider is SMTP.

### 13.1. Environment Variable Mapping

The property app.notification.provider can typically be supplied via an environment variable:

~~~text
APP_NOTIFICATION_PROVIDER=SMTP
~~~

This is helpful in Docker/Kubernetes, where deployments inject environment variables or mount configs.

### 13.2. Verifying the Effective Property

You can read the final value through Environment:

~~~java
@Component
public class NotificationConfigurationLogger {

    private final Environment environment;

    public NotificationConfigurationLogger(Environment environment) {
        this.environment = environment;
    }

    public void logProvider() {
        log.info(
                "Notification provider: {}",
                environment.getProperty(
                        "app.notification.provider"));
    }
}
~~~

This example only logs provider because it is non-sensitive. Never log the entire Environment or credentials.

### 13.3. Do Not Infer Settings from Profile Names

Even when prod is active, properties can be overridden from the command line or environment. If operations strictly require SMTP in production, add startup validation/guards per deployment policy, explicitly defining what is allowed.

For example, if prod profile with provider=console is forbidden, add a dedicated startup check. Do not rely solely on the filename application-prod.yml as proof.

## 14. Multi-Document YAML and spring.config.activate.on-profile

Instead of creating separate files, you can place multiple documents inside one YAML file:

~~~yaml
app:
  notification:
    provider: console
---
spring:
  config:
    activate:
      on-profile: prod
app:
  notification:
    provider: smtp
~~~

The second document only applies when the prod profile is active.

This is still profile-based activation of a Config Data document. Bean selectors in Java can continue reading the app.notification.provider property.

### 14.1. When Is Multi-Document YAML Helpful?

- Small configuration with a few clear variants.
- Keeping related values close together in one file.
- Using spring.config.activate.on-profile to activate documents.

### 14.2. When Should Files Be Split?

- Each environment has extensive dedicated configuration.
- Files become long and hard to review.
- Ownership permissions or secret sources differ.
- Deployment mounts files per environment.

Organize config files to match how operations teams manage configuration, not so Java code has to know file paths.

## 15. What Are the Limitations of @ConditionalOnProperty?

@ConditionalOnProperty works well for scalar properties such as strings, booleans, or enums represented as text. However, the annotation is not a general-purpose query engine for every property structure.

### 15.1. Do Not Use It to Check Indexed Collections

Example:

~~~yaml
app:
  notification:
    recipients:
      - ops@example.invalid
      - support@example.invalid
~~~

Checking for the existence of app.notification.recipients with @ConditionalOnProperty may not behave as expected for indexed collections.

If conditions depend on collections or maps, bind them via @ConfigurationProperties and inspect them in an appropriate mechanism, or write a custom Condition when bean registration genuinely needs to be conditional.

### 15.2. Conditions Are Evaluated at Startup

@ConditionalOnProperty decides whether a bean definition is registered when the context is processed. Changing an environment variable or external file after startup will not cause Spring to automatically recreate or destroy beans.

If feature flags must change while the application is running:

- Use a properties/state service that updates via a designed mechanism.
- Have business services check the flag at execution time.
- Or use a dynamic configuration/refresh mechanism suited to the system.

Do not expect @ConditionalOnProperty to hot-swap implementations inside a running ApplicationContext.

### 15.3. Do Not Use @ConditionalOnProperty as Sole Validation

A non-matching condition simply skips bean registration. It does not always produce a clear message stating the user entered an invalid value.

Combine:

- @ConfigurationProperties for binding.
- Bean Validation to validate inputs.
- @ConditionalOnProperty for conditional wiring.
- Startup tests to protect all branches.

## 16. When a Property Selects an Implementation per Request

A choice that varies per user or tenant should not be represented by active profiles or conditional beans.

Example:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
~~~

Two implementations:

~~~java
public class CardPaymentGateway implements PaymentGateway {
    // ...
}

public class WalletPaymentGateway implements PaymentGateway {
    // ...
}
~~~

If one process serves both card and wallet simultaneously, register both beans and select via a factory:

~~~java
@Component
public class PaymentGatewayRegistry {

    private final Map<PaymentMethod, PaymentGateway> gateways;

    public PaymentGatewayRegistry(
            CardPaymentGateway card,
            WalletPaymentGateway wallet) {
        this.gateways = Map.of(
                PaymentMethod.CARD, card,
                PaymentMethod.WALLET, wallet);
    }

    public PaymentGateway forMethod(PaymentMethod method) {
        PaymentGateway gateway = gateways.get(method);
        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment method: " + method);
        }
        return gateway;
    }
}
~~~

Here selection happens based on request data. Profiles/properties only govern which providers are enabled or available in the application, not per-transaction routing logic.

If each tenant has its own endpoints and credentials, design a registry/tenant configuration with safe secret handling. Never create a separate profile for each tenant.

## 17. Testing Profile-Based Selection

One way to test profile-based configuration is creating a small context and activating the corresponding profile.

JUnit 5 example with ApplicationContextRunner:

~~~java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class NotificationProfileConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            NotificationProfileConfiguration.class);

    @Test
    void localProfileCreatesConsoleSender() {
        runner.withPropertyValues(
                    "spring.profiles.active=local")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);
                    assertThat(context.getBean(NotificationSender.class))
                            .isInstanceOf(
                                    ConsoleNotificationSender.class);
                });
    }

    @Test
    void prodProfileCreatesSmtpSender() {
        runner.withPropertyValues(
                    "spring.profiles.active=prod")
                .withBean(SmtpClient.class, TestSmtpClient::new)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);
                    assertThat(context.getBean(NotificationSender.class))
                            .isInstanceOf(
                                    SmtpNotificationSender.class);
                });
    }

    @Test
    void noMatchingProfileRegistersNoSender() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .doesNotHaveBean(NotificationSender.class);
        });
    }
}
~~~

The test fixture TestSmtpClient is a fake implementation of the SmtpClient collaborator in the example.

### 17.1. Why Does the Test Have No Sender Without a Profile?

The configuration only registers beans for local and prod. If no profile matches, both @Bean methods are skipped.

If the context also contained a service requiring NotificationSender, the context would fail. The test above omits that service because its goal is observing bean selection in isolation.

### 17.2. Multiple Profiles Can Be Active Simultaneously

Spring permits multiple active profiles at once. If you run:

~~~bash
java -jar order-api.jar \
  --spring.profiles.active=local,prod
~~~

both bean methods can match and register two NotificationSender beans. A service injecting a single unqualified NotificationSender can fail with NoUniqueBeanDefinitionException.

Do not assume local and prod automatically exclude each other. If two profiles are mutually exclusive choices, deployment must activate only one or configuration must validate allowed combinations.

### 17.3. Checking Active Profiles

You can inspect:

~~~java
environment.getActiveProfiles();
~~~

If profile groups or includes are used, the active list may contain more profiles than the name passed by the launcher. Inspect Environment instead of looking at a single environment variable.

## 18. Testing Property-Based Selection

With property-based configuration, ApplicationContextRunner makes testing each value in isolation easy.

~~~java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class NotificationPropertyConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            NotificationPropertyConfiguration.class);

    @Test
    void consolePropertyCreatesConsoleSender() {
        runner.withPropertyValues(
                    "app.notification.provider=console")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);
                    assertThat(context.getBean(NotificationSender.class))
                            .isInstanceOf(
                                    ConsoleNotificationSender.class);
                });
    }

    @Test
    void smtpPropertyCreatesSmtpSender() {
        runner.withPropertyValues(
                    "app.notification.provider=smtp")
                .withBean(SmtpClient.class, TestSmtpClient::new)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);
                    assertThat(context.getBean(NotificationSender.class))
                            .isInstanceOf(
                                    SmtpNotificationSender.class);
                });
    }

    @Test
    void unsupportedProviderCreatesNoSender() {
        runner.withPropertyValues(
                    "app.notification.provider=push")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(NotificationSender.class);
                });
    }
}
~~~

The third test has no business service requiring NotificationSender, so the context still starts even without a sender. In a real application, if the sender is a required dependency, startup can fail. This is a way to test the condition outcome in isolation.

### 18.1. Testing matchIfMissing

If the selector has:

~~~java
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "provider",
        havingValue = "console",
        matchIfMissing = true)
~~~

you can test:

~~~java
@Test
void missingProviderUsesConsoleFallback() {
    runner.run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context.getBean(NotificationSender.class))
                .isInstanceOf(ConsoleNotificationSender.class);
    });
}
~~~

Do not keep this fallback test if the contract changes to require declaring the provider. Tests must reflect the published configuration policy.

### 18.2. Testing enabled=false

If NoOpNotificationSender is the fallback when disabling the feature:

~~~java
@Test
void disabledFeatureUsesNoOpSender() {
    runner.withPropertyValues(
                "app.notification.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .hasSingleBean(NotificationSender.class);
                assertThat(context.getBean(NotificationSender.class))
                        .isInstanceOf(NoOpNotificationSender.class);
            });
}
~~~

This test assumes NotificationConfiguration has a condition registering the no-op bean and that provider beans do not match when disabled. It does not apply directly to the earlier configuration containing only the two provider conditions.

## 19. Testing Profile-Specific Properties Alongside Bean Selectors

The context runner can test active profiles and property selectors independently, but if you want to verify Spring Boot actually loads application-prod.yml from Config Data, you need a test that boots SpringApplication with controlled Config Data locations.

Distinguish these goals:

| Test | What it proves |
|---|---|
| Profile context test | @Profile selects beans based on active profiles |
| Property context test | @ConditionalOnProperty selects beans based on Environment properties |
| Config Data integration test | application-prod.yml or specified location is actually loaded |
| Deployment smoke test | Runtime environment/profile/config selects the expected implementation |

### 19.1. Do Not Use Test Properties to Pretend You Tested YAML Files

For example:

~~~java
runner.withPropertyValues(
        "spring.profiles.active=prod",
        "app.notification.provider=smtp");
~~~

This test verifies profile and property behavior inside the context runner's Environment. It **does not prove** that application-prod.yml was found or read.

When you need to test Config Data loading, create temporary config files and launch SpringApplication with the corresponding location, or use an integration test that actually reads the file.

### 19.2. Checking Active Profiles and Effective Provider

In the application, you can safely log:

~~~java
log.info(
        "Active profiles: {}",
        Arrays.toString(environment.getActiveProfiles()));
log.info(
        "Notification provider: {}",
        environment.getProperty(
                "app.notification.provider"));
~~~

Only log non-sensitive details. Never log all property sources if they contain credentials.

## 20. Direct Comparison of Profiles and Properties

| Criterion | Profile | Property |
|---|---|---|
| Primary meaning | Active environment/configuration group | A specific choice or value |
| Selecting multiple beans together | Very suitable | Possible, but requires repeating conditions |
| Selecting a single implementation | Possible | Usually clearer |
| Independent feature flags | Prone to profile combination explosion | Well-suited |
| Environment config files | application-{profile}.yml | Can reside in any property source |
| Multiple simultaneous selections | Multiple profiles can be active together | Each property has one effective value |
| Runtime changes | Does not re-wire context automatically | Conditions also do not re-wire after startup |
| Per-request/tenant selection | Inappropriate | Conditions also inappropriate; needs routing/service logic |
| Testing | Activate profile then inspect beans | Set property then inspect beans |

### 20.1. Quick Selection Rule

- If a name represents **an entire environment configuration bundle**, use a profile.
- If a key selects **a specific provider or feature**, use a property.
- If the choice varies per **request, user, or tenant**, use a strategy/factory/runtime routing.
- If the choice must change **while the application is running**, design dedicated dynamic state/configuration; do not expect @Profile or @ConditionalOnProperty to swap beans automatically.

## 21. Configuring Profiles and Properties in Docker and Kubernetes

A single image can be deployed across multiple environments. You should not build a different JAR just to swap implementations when code and dependencies are identical.

### 21.1. Docker Environment Variables

Example:

~~~bash
docker run --rm \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e APP_NOTIFICATION_PROVIDER=SMTP \
  -e APP_NOTIFICATION_ENABLED=true \
  order-api:latest
~~~

In this example:

- SPRING_PROFILES_ACTIVE selects the production configuration bundle.
- APP_NOTIFICATION_PROVIDER selects the provider.
- APP_NOTIFICATION_ENABLED turns on the capability.

If application-prod.yml also declares provider=smtp, environment variables can supply/override the value according to property source precedence.

### 21.2. Kubernetes Deployment

Example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: order-api
          image: registry.example.invalid/order-api:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: APP_NOTIFICATION_PROVIDER
              value: SMTP
            - name: APP_NOTIFICATION_ENABLED
              value: "true"
~~~

This is an illustrative manifest. In real systems, values and image references should be managed by your deployment pipeline/manifests.

### 21.3. Secrets Are Not Provider Selectors

Provider can be a non-sensitive value like SMTP, whereas passwords/tokens used to connect to the mail server must be managed via Secrets or a secret manager.

Example:

~~~yaml
app:
  notification:
    provider: smtp
    smtp:
      host: mail.example.invalid
      username: order-api
      # Supply app.notification.smtp.password from your deployment secret source.
~~~

Never commit real passwords to application-prod.yml. Deployment must supply the corresponding property and restrict access.

### 21.4. Profiles Are Not Security Boundaries

Activating the prod profile does not protect credentials, endpoints, or access permissions. Security must rely on secret management, network policies, identity, and authorization.

Do not treat @Profile("prod") as an access control mechanism for an API or sensitive data.

## 22. Default Implementations and @ConditionalOnMissingBean

A starter may want to supply a default NotificationSender if the application has not registered any bean. This is a different use case from choosing a provider via a property.

Example in auto-configuration:

~~~java
@AutoConfiguration
public class NotificationDefaultAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationSender.class)
    NotificationSender defaultNotificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

When the application provides its own NotificationSender bean, the auto-configuration backs off by type.

### 22.1. Distinguishing the Three Selectors

- @Profile: bean is registered when a profile matches.
- @ConditionalOnProperty: bean is registered when a property matches.
- @ConditionalOnMissingBean: bean is registered when no matching bean already exists.

They can be combined, but each condition should reflect a distinct reason.

### 22.2. Do Not Use a Default Bean to Mask Invalid Provider Values

If provider=push while only console/smtp are supported, creating a default console bean via @ConditionalOnMissingBean could let a broken configuration run silently.

Default beans make sense when supplying a fallback if the user did not customize, not for accepting arbitrary invalid property values.

### 22.3. Auto-Configuration Ordering

@ConditionalOnMissingBean is commonly used in auto-configuration because Boot processes auto-configurations in a controlled order so user configurations take precedence.

If you place this condition in an ordinary configuration class processed before user beans, results may not match expectations. Test with ApplicationContextRunner and AutoConfigurations.of when building starters.

## 23. Choosing a Default Policy When a Property Is Missing

Three common policies exist:

### 23.1. Require Explicit Declaration

Do not set matchIfMissing=true. If provider is missing, no matching bean is registered or property validation fails.

Appropriate when picking the wrong provider carries significant consequences.

### 23.2. Safe Default

Set matchIfMissing=true for a safe implementation such as console or no-op, if that is the documented contract.

Appropriate for local tools or libraries designed to run with minimal configuration.

### 23.3. Profile-Specific File Defaults

application-local.yml can set provider=console, and application-prod.yml can set provider=smtp. The Java selector requires the property to be present.

Appropriate when deployments have explicit profiles and every environment must specify its provider.

### 23.4. Do Not Let Defaults Silently Shift Between Environments

Dangerous example:

- Local missing provider → console.
- Production missing provider → also console because matchIfMissing=true.

If production requires SMTP, a console default can hide a missing configuration error and cause notifications to go unsent.

Choose one of the policies above and document it clearly in operations docs.

## 24. Common Pitfalls When Converting Between Profiles and Properties

### 24.1. Both Old Profile and New Property Selector Register Beans

**Symptom:** NoUniqueBeanDefinitionException because both console and SMTP exist.

**Cause:** old configuration is still imported or a profile is active alongside the new property selector.

**Resolution:** pick one place responsible for registering implementations; delete or disable the old selector once migration finishes.

### 24.2. Activating Mutually Exclusive Profiles Together

**Symptom:** multiple beans for the same interface even though each profile works alone.

**Cause:** Spring allows multiple active profiles. local,prod can match both @Profile methods.

**Resolution:** control the active profile list in launchers/deployments; add startup guards if such combinations are forbidden.

### 24.3. Assuming the prod Profile Always Dictates the Provider

**Symptom:** prod is active, yet the application uses console.

**Cause:** provider was overridden via command-line, environment variable, or a higher-precedence property source.

**Resolution:** check the effective property and its source; inspect process arguments and environment variables.

### 24.4. Typos in Property Keys

**Symptom:** no bean matches even though the YAML looks right.

**Cause:** prefix/name mismatch, such as app.notification.provider vs. app.notifications.provider.

**Resolution:** cross-check keys across annotations, YAML, and environment variable mappings. Use @ConfigurationProperties to centralize the contract.

### 24.5. Forgetting havingValue

**Symptom:** an unexpected property value still satisfies the condition.

**Cause:** havingValue was omitted; default semantics match if the property exists and is not false.

**Resolution:** for provider selectors, specify havingValue explicitly for every value.

### 24.6. Misusing matchIfMissing

**Symptom:** production runs a default even when deployment forgot to declare a provider.

**Cause:** matchIfMissing=true enabled an unsafe fallback for that environment.

**Resolution:** require the property or set explicit profile-specific values; test the missing-property case.

### 24.7. Unsupported Property Value

**Symptom:** no NotificationSender exists or startup fails on a downstream bean.

**Cause:** property has value push while conditions only handle console/smtp.

**Resolution:** use enums/validation or startup guards to clearly report valid values.

### 24.8. Disabling a Feature While a Service Still Requires the Bean

**Symptom:** context fails due to missing NotificationSender when enabled=false.

**Cause:** condition removed the provider bean while a consumer still has a required constructor dependency.

**Resolution:** provide a No-op implementation if valid, make the consumer conditional too, or model feature state explicitly.

### 24.9. No-op Hiding Business Failures

**Symptom:** payments/audits/alerts are skipped while the application reports success.

**Cause:** using an empty implementation for a mandatory capability.

**Resolution:** only use no-op when doing nothing is acceptable behavior. For mandatory capabilities, fail fast or block the use case.

### 24.10. Changing Properties After Startup Expecting Beans to Swap

**Symptom:** editing environment/config files leaves the running process on the old implementation.

**Cause:** conditions are evaluated when the context bootstraps.

**Resolution:** restart/roll out, or build a dedicated dynamic configuration mechanism. Do not expect @ConditionalOnProperty to swap beans at runtime.

### 24.11. Using @ConditionalOnProperty on Collections

**Symptom:** condition does not match even though YAML contains a recipients list.

**Cause:** the annotation is unsuited for checking indexed collection properties.

**Resolution:** bind collections via @ConfigurationProperties and check with appropriate logic.

### 24.12. Using Profiles to Select per Request

**Symptom:** attempting to switch active profiles per tenant or user.

**Cause:** profiles belong to the ApplicationContext's Environment, not the request context.

**Resolution:** use a factory/strategy registry or tenant-aware routing.

### 24.13. Testing with withPropertyValues and Thinking YAML Files Were Tested

**Symptom:** tests pass, yet deployment fails to load application-prod.yml.

**Cause:** test injected properties directly into the context, bypassing Config Data file loading.

**Resolution:** write a Config Data integration test or startup smoke test with actual files/locations.

### 24.14. Profile Tests Not Actually Activating Profiles

**Symptom:** @Profile bean is missing in tests.

**Cause:** set an arbitrary property instead of activating the profile, or the test context did not apply spring.profiles.active as expected.

**Resolution:** use a context initializer to call Environment.setActiveProfiles(...) or check active profiles on the context before asserting beans.

### 24.15. Checking Only the Injected Bean Without Counting Candidates

**Symptom:** test injects the custom sender, yet the default also exists.

**Cause:** @Primary or a qualifier made injection pick one bean while multiple candidates existed in the context.

**Resolution:** assert hasSingleBean and check bean names when the contract requires only one implementation.

### 24.16. Putting Secrets in Profile-Specific YAML in the Repository

**Symptom:** application-prod.yml contains SMTP passwords or API tokens.

**Cause:** treating profile files as secret stores.

**Resolution:** keep non-secret settings in config files; supply credentials via secret managers, Kubernetes Secrets, or approved secure sources.

### 24.17. Creating Profiles for Every Feature Combination

**Symptom:** profiles like prod-mail-on-export-off and prod-mail-off-export-on appear.

**Cause:** using profiles to govern independent toggles.

**Resolution:** profiles for environment bundles; properties for feature flags and provider options.

### 24.18. Putting @Profile at the Class Level Unintentionally

**Symptom:** multiple beans in a configuration disappear together when only one bean needed a condition.

**Cause:** @Profile on a @Configuration class applies to the whole configuration.

**Resolution:** place @Profile on individual @Bean methods if only one bean is conditional, or split configuration classes by group.

## 25. Safe Migration Plan

Switching a selector from profile to property alters the application's bean graph. Perform it in observable, reversible steps.

### Step 1 — Record Current Behavior

For each supported profile, identify:

- Which bean implementations are registered?
- Which dependencies are required?
- Which properties are loaded from profile-specific files?
- Are multiple profiles allowed to be active together?
- Which tests/integrations rely on the current beans?

This serves as the baseline for post-conversion comparison.

### Step 2 — Finalize the Property Vocabulary

Example:

~~~text
app.notification.provider = console | smtp
app.notification.enabled = true | false
~~~

Document default values, required values, unsupported cases, and how each environment provides the properties.

### Step 3 — Write the New Selector and Tests

Create the configuration using @ConditionalOnProperty. Test every provider, missing properties, invalid properties, and disabled feature state. If using a No-op implementation, test its semantics explicitly.

### Step 4 — Put Properties into Profile-Specific Files

Keep profiles to select configuration bundles:

- application-local.yml: provider=console.
- application-test.yml: provider=console or fake/recording.
- application-staging.yml: provider=smtp or sandbox.
- application-prod.yml: provider=smtp.

Actual values depend on your deployment contract; these are illustrative.

### Step 5 — Run Integration Tests for Each Profile

Boot the context with each profile and verify:

- Active profiles.
- Effective provider property.
- Registered bean type.
- No competing implementations.
- Required dependencies are satisfied.

### Step 6 — Remove the Old Selector

Once the property selector successfully replaces it, delete or stop importing the old @Profile bean methods. Never leave two configurations registering the same interface.

### Step 7 — Roll Out by Environment

Roll out to local/test first, then staging. Verify real providers and external dependencies before rolling out to production.

### Step 8 — Monitor and Roll Back

If startup fails or the wrong provider is active, inspect the effective property, source precedence, and bean registry. Rolling back must revert both the selector code and its corresponding property configuration.

## 26. Pre-Run Configuration Checklist

For each environment, you should be able to answer:

| Question | Example check |
|---|---|
| Which profiles are active? | Environment.getActiveProfiles() |
| What is the provider property value? | app.notification.provider |
| Where did that value come from? | application-prod.yml, environment, or command line |
| Is there exactly one NotificationSender? | getBeansOfType(NotificationSender.class) |
| What is the actual implementation? | Bean class/type |
| Do external clients have required dependencies? | SMTP client/credentials/endpoint |
| Where are secrets supplied from? | Secret manager or deployment secret |
| Does feature-disabled state have valid behavior? | No-op or consumer not registered |
| Does changing the property require a restart? | Conditional beans normally require a fresh context startup |
| Are there tests for this config branch? | Profile/property context tests |

In production, never log credentials to answer these questions. You can safely log the provider, active profiles, and validated configuration state without printing secrets.

## 27. Practice Exercises

### Exercise 1 — Choosing the Mechanism

An application has three environments: local, staging, and production. Each environment has its own database URL, log level, and endpoints.

**Question:** Should you use profiles or create three separate properties for each component?

**Guided Answer:** Profiles fit well for selecting an environment configuration bundle. Individual settings remain properties inside the corresponding files.

### Exercise 2 — Selecting an Independent Provider

Production defaults to SMTP, yet some deployments need a push provider. Database and other settings remain unchanged.

**Question:** Should you create prod-smtp and prod-push profiles?

**Guided Answer:** If only the provider varies independently, the app.notification.provider property expresses it more clearly. Only use separate profiles if the two choices represent distinct environment configuration bundles.

### Exercise 3 — Predicting Beans

Configuration:

~~~java
@Bean
@Profile("local")
NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}

@Bean
@Profile("prod")
NotificationSender smtpSender(SmtpClient client) {
    return new SmtpNotificationSender(client);
}
~~~

Process runs with:

~~~text
SPRING_PROFILES_ACTIVE=local,prod
~~~

**Question:** How many NotificationSender beans can be registered?

**Answer:** Both bean methods match. If a service injects a single unqualified/non-primary NotificationSender, the context can fail due to multiple candidates.

### Exercise 4 — Predicting Property Conditions

Condition:

~~~java
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "provider",
        havingValue = "smtp",
        matchIfMissing = false)
~~~

**Question:** What happens for values smtp, console, push, and a missing property?

**Guided Answer:** Only smtp matches. console, push, and missing do not match this condition.

### Exercise 5 — Overridden Property

application-prod.yml:

~~~yaml
app:
  notification:
    provider: smtp
~~~

Command line:

~~~bash
java -jar order-api.jar \
  --spring.profiles.active=prod \
  --app.notification.provider=console
~~~

**Question:** Which provider is selected if command-line properties have higher precedence?

**Answer:** console. The prod profile remains active, yet does not guarantee provider=smtp.

### Exercise 6 — Disabled Feature

OrderNotificationService has a required constructor dependency NotificationSender. When enabled=false, neither provider bean is registered.

**Question:** Why can the context fail? What design options exist?

**Guided Answer:** The service lacks a required dependency. You can provide a No-op if "do not send" is valid, make the consumer/service conditional as well, or keep the service while designing feature state explicitly.

### Exercise 7 — Selecting per Tenant

One process serves two tenants: tenant A uses SMTP server A, tenant B uses SMTP server B.

**Question:** Should you activate tenant-a/tenant-b profiles per request?

**Answer:** No. Profiles belong to the ApplicationContext. Use tenant-aware routing, a registry, or a client factory with securely managed tenant configuration.

### Exercise 8 — Writing Tests

Write two ApplicationContextRunner tests:

1. app.notification.provider=console creates ConsoleNotificationSender.
2. app.notification.provider=smtp creates SmtpNotificationSender.

**Requirement:** assert the context does not fail, has exactly one NotificationSender, and the implementation has the right type. Supply a fake SmtpClient in the SMTP branch.

### Exercise 9 — Finding a Migration Bug

After migration, configuration still has both the @Profile("local") console bean and the @ConditionalOnProperty provider=smtp SMTP bean. When local is active and provider=smtp, the context has two NotificationSenders.

**Question:** Should you fix it with @Primary or remove one selector?

**Answer:** Decide which selector is the primary decision source and remove/disable the old selector. @Primary only picks a candidate during injection; it does not eliminate the extra bean.

### Exercise 10 — Dynamic Feature Flags

Operations wants to switch providers without restarting the process.

**Question:** Does merely editing the app.notification.provider property make Spring swap the bean automatically?

**Answer:** No. @ConditionalOnProperty is evaluated when the context processes bean definitions. You need dynamic configuration/strategy routing with explicit lifecycle and concurrency contracts.

## 28. Principles to Remember

1. **Profiles describe active configuration/environment bundles.** Use them to select databases, endpoints, infrastructure, or multiple beans that change together.
2. **Properties describe specific choices or values.** Use them for provider selectors, feature flags, timeouts, limits, and independent parameters.
3. @Profile can be placed on configuration classes or individual bean methods. If multiple profiles are active at once, multiple bean methods can match together.
4. @ConditionalOnProperty should explicitly specify prefix, name, havingValue, and matchIfMissing per contract.
5. Non-matching properties can leave a bean unregistered. Inspect the bean graph and fail fast on invalid configuration.
6. No-op implementations are only appropriate when taking no action is valid business behavior.
7. Profile-specific YAML can supply properties for bean selectors. Profiles select files; properties select implementations.
8. Command-line/environment variables can override configuration files. Always check the effective property rather than inferring from profile names.
9. @ConditionalOnProperty does not auto-hot-swap beans after startup and is unsuited for checking indexed collections.
10. If choices vary per request/tenant, use strategy/factory/routing; never swap active profiles.
11. When switching selectors, remove the old configuration to avoid registering two implementations simultaneously.
12. Test every profile/property branch and verify a single candidate exists when services expect one implementation.

**Conclusion:** Choose profiles when activating an environment configuration bundle, and choose properties when controlling an independent capability or implementation. In many applications, the clearest design combines both: profiles select application-local.yml or application-prod.yml, and properties inside those files select the provider via @ConditionalOnProperty. Business services continue depending on interfaces while configuration handles registering the right implementation. During migration, control property precedence, default behavior, co-active profiles, and the bean graph; test every branch before rollout to avoid missing beans or duplicate implementation registrations.
