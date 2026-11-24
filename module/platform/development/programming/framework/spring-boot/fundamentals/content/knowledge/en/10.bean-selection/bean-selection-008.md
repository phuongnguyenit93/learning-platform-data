# Choosing Implementations Using Profiles or Configuration Properties

When a feature has multiple implementations, the application must decide which bean will be created in the ApplicationContext. Spring Boot provides two common ways: **profiles** with `@Profile` and **configuration properties** with `@ConditionalOnProperty`.

Both decide whether a bean is registered while Spring builds the ApplicationContext. The difference lies in the meaning of the condition: a profile describes the runtime context of the application, whereas a configuration property describes a specific choice the application or operator wants to enable.

## 1. When should you use profiles?

Profiles fit well when the set of beans to use changes by environment or runtime context, such as:

- A local environment using a mock service for development.
- A test environment using adapters or data dedicated to testing.
- A production environment connecting to real services.

Consider an example of an application with two ways of sending notifications. When running locally, the application writes notifications to logs; when running in production, it sends notifications through an external provider.

First, define the shared contract:

~~~java
public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

Create configurations providing each implementation:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class NotificationConfiguration {

    @Bean
    @Profile("local")
    NotificationSender logNotificationSender() {
        return (recipient, message) ->
                System.out.printf("To %s: %s%n", recipient, message);
    }

    @Bean
    @Profile("production")
    NotificationSender productionNotificationSender(
            ExternalNotificationClient client) {
        return (recipient, message) ->
                client.send(recipient, message);
    }
}
~~~

When the local profile is active, Spring registers the bean from the logNotificationSender method. When the production profile is active, Spring registers the bean from the productionNotificationSender method. Other components only need to depend on NotificationSender:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ReminderService {

    private final NotificationSender notificationSender;

    public ReminderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public void remind(String recipient) {
        notificationSender.send(recipient, "Your reminder is ready.");
    }
}
~~~

ReminderService does not need to know whether the application is running in local or production. Spring selects the matching bean before creating ReminderService and passes that bean into its constructor.

### Activating a profile

A profile can be activated using the spring.profiles.active property. For example, in application.yml:

~~~yaml
spring:
  profiles:
    active: local
~~~

When deploying, let the deployment environment decide the profile rather than hardcoding the production profile in shared configuration. You can pass the profile as a command-line argument:

~~~bash
java -jar application.jar --spring.profiles.active=production
~~~

Or set an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=production
~~~

Spring Boot also supports profile-specific configuration files. For example:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
└── application-production.yml
~~~

When the local profile is active, values in application-local.yml are loaded alongside the shared configuration. When the production profile is active, application-production.yml is loaded. This separates endpoints, log levels, and environment-varying values from the shared configuration.

If no active profile is declared, Spring uses a default profile named default. You can designate the default profile with spring.profiles.default. For example:

~~~yaml
spring:
  profiles:
    default: local
~~~

The default profile is used only when no profile is explicitly activated. Once another profile is activated, the default profile is not automatically added on top.

### Profile expressions

@Profile accepts a profile name or a profile expression. For example:

~~~java
@Bean
@Profile("local | test")
NotificationSender nonProductionSender() {
    return (recipient, message) -> System.out.println(message);
}
~~~

The expression above matches when either local or test is active. You can combine AND and NOT operators:

~~~java
@Bean
@Profile("production & !maintenance")
NotificationSender productionSender() {
    return createProductionSender();
}
~~~

In this example, the bean is registered only when production is active and maintenance is inactive. When using complex expressions, keep conditions readable so operators can tell why a bean was selected.

## 2. When should you use configuration properties?

Configuration properties fit well when operators need to pick an implementation or enable a specific integration without necessarily changing the environment profile.

For example, the application always runs in the production environment, yet can select the payment provider via the app.payment.provider property. The environment remains production; only the provider choice changes.

Spring Boot provides @ConditionalOnProperty in the org.springframework.boot.autoconfigure.condition package. This condition inspects a property in the Environment before registering a configuration or bean.

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.payment",
            name = "provider",
            havingValue = "sandbox",
            matchIfMissing = true
    )
    PaymentProcessor sandboxPaymentProcessor() {
        return new SandboxPaymentProcessor();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.payment",
            name = "provider",
            havingValue = "stripe"
    )
    PaymentProcessor stripePaymentProcessor(
            StripeClient stripeClient) {
        return new StripePaymentProcessor(stripeClient);
    }
}
~~~

The corresponding configuration can be placed in application.yml:

~~~yaml
app:
  payment:
    provider: sandbox
~~~

When provider has the value sandbox, the SandboxPaymentProcessor bean is registered. When provider has the value stripe, Spring registers the StripePaymentProcessor bean and supplies StripeClient via dependency injection.

If the property is absent, matchIfMissing = true lets the sandbox condition match. If the property has a value other than sandbox or stripe, neither condition matches; the application may then fail when creating a bean that requires PaymentProcessor because no matching implementation exists. Therefore, clearly specify accepted values and provide an intentional default.

### Meaning of @ConditionalOnProperty attributes

- prefix: shared prefix part of the property name. In the example, prefix is app.payment.
- name: name of the property to check after the prefix. Combining both parts forms app.payment.provider.
- havingValue: the value the property must equal for the condition to match. Declare this explicitly when choosing among multiple implementations.
- matchIfMissing: determines whether the condition matches when the property is missing. The default value is false.

If havingValue is omitted, the condition matches whenever the property exists and its value is not false (case-insensitive). For properties used to select one implementation, use an explicit havingValue to prevent an unexpected value from also matching the condition.

Properties can come from any configuration source supported by Spring Boot, such as application.yml, command-line arguments, or environment variables. This allows the same application package to be configured to choose different implementations at launch.

For example, you can override the choice using an environment variable:

~~~bash
APP_PAYMENT_PROVIDER=stripe
~~~

Spring Boot's relaxed environment variable naming converts dot-separated property names into uppercase with underscores. Actual configuration values still need to be managed appropriately for the deployment environment; do not put payment provider secrets into committed configuration files.

## 3. Comparing the two selection approaches

| Criterion | @Profile | @ConditionalOnProperty |
|---|---|---|
| Condition | Active profile | Value of a configuration property |
| Common meaning | Runtime context or environment | Selected option or integration |
| How activated | spring.profiles.active | Application-defined property |
| Example | local, test, production | app.payment.provider=stripe |
| Scope | A group of configurations by context | A bean or configuration group by property value |
| When suitable | Configuration changes by environment | Choice changes independently of environment |

There is no mandatory rule that every choice must use one approach or the other. Ask about the meaning of the condition:

- If the question is "In which context is the application running?", a profile is usually the clear choice.
- If the question is "Which provider or implementation should the application use?", a configuration property is usually more suitable.

For instance, production can always remain the active profile, while app.payment.provider selects stripe or another provider. That way, choosing a provider does not require creating extra profiles like production-stripe, production-provider-b, test-stripe, and similar combinatorial profiles.

## 4. Can profiles and configuration properties be combined?

Multiple conditions can be placed on the same @Bean method or configuration class. When combined, all conditions must be satisfied for the bean to be registered.

~~~java
@Bean
@Profile("production")
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
PaymentProcessor productionPaymentProcessor(
        StripeClient stripeClient) {
    return new StripePaymentProcessor(stripeClient);
}
~~~

The bean above is created only when the production profile is active and app.payment.enabled equals true. This combination is useful when an integration is only allowed in certain environments and must also be enabled by a separate property.

However, each additional condition increases the number of configuration cases to manage. Combine them only when the two conditions express two independent, clearly meaningful requirements.

## 5. Common errors when selecting beans

### Both implementations get registered

Suppose two beans implement PaymentProcessor and both conditions match. When a service requests PaymentProcessor, Spring cannot guess which bean to inject and may report NoUniqueBeanDefinitionException.

To avoid this error:

- Design mutually exclusive conditions if only one implementation is allowed.
- Check which profiles are activated simultaneously.
- Check property values and default conditions.
- Only use @Primary or @Qualifier when the application truly needs multiple beans coexisting with explicit bean selection rules.

@Primary and @Qualifier solve selecting among multiple already-registered beans. They do not replace bean registration conditions when the goal is to create only one implementation by configuration.

### No implementation gets registered

If the property matches no havingValue, or the required profile is inactive, Spring may register no bean. A service requiring that type via its constructor will not be created and startup will fail.

When encountering this error, check:

1. Which profiles are active at startup.
2. Whether the property exists in the Environment.
3. Whether the actual value matches havingValue.
4. Whether matchIfMissing matches the intended default policy.
5. Whether any higher-precedence configuration source overrides the expected value.

Do not enable matchIfMissing casually to mask configuration mistakes. Enable it only when that implementation is genuinely the safe, intended default choice.

### Confusing profiles with toggle properties

A profile such as production describes the runtime context. A property such as app.payment.enabled describes an application choice within that context. Using profiles for every small toggle causes the number of profiles to grow rapidly and become hard to manage.

Conversely, using dozens of properties to simulate an entire environment makes configuration hard to understand because there is no single profile name clearly expressing the active runtime context.

Keep profiles for environment-tied configuration groups; use properties for independent choices such as providers, integration modes, or feature toggles.

### Expecting beans to swap when properties change

These conditions are evaluated while Spring builds the ApplicationContext. Changing a value in a configuration file after the application has started does not automatically replace the bean in use. For another choice to take effect, the ApplicationContext or application must be restarted according to the appropriate deployment mechanism.

## 6. How to verify selection before deployment

When adding a new implementation, test the expected configuration scenarios by starting the application with each corresponding profile or property value. You can log the chosen implementation name during startup or inspect beans in an ApplicationContext test.

For example, running the application with the local profile:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

Running with the production profile and selecting Stripe:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=production --app.payment.provider=stripe'
~~~

In a real production environment, connection details and secrets must be supplied by the environment's secure configuration mechanism. The command-line examples above illustrate passing bean selection options, not storing or exposing credentials.

A minimal test matrix should include:

| Case | Configuration | Expected result |
|---|---|---|
| Local profile | spring.profiles.active=local | Bean for local is registered |
| Production profile | spring.profiles.active=production | Bean for production is registered |
| Sandbox property | app.payment.provider=sandbox | SandboxPaymentProcessor is registered |
| Stripe property | app.payment.provider=stripe | StripePaymentProcessor is registered |
| Missing property | app.payment.provider omitted | Intended matchIfMissing policy applies |
| Invalid value | app.payment.provider=unknown | Does not silently pick the wrong implementation |

When multiple conditions are combined, test both the case where all conditions match and the case where just one condition does not match. This helps catch missing-bean or multiple-bean issues early.

## 7. Workflow for choosing an implementation

When an interface has multiple implementations, you can follow these steps in order:

1. Identify the implementations and the shared contract the service will depend on.
2. Determine whether the selection condition represents a runtime environment or a configuration option.
3. Use @Profile if the implementation depends on the profile; use @ConditionalOnProperty if the implementation depends on a property value.
4. Ensure every valid configuration registers the exact number of beans required by dependent components.
5. Define behavior when a property is missing or receives an invalid value.
6. Start the application with representative configurations and verify the registered implementation.

When services depend only on interfaces, bean selection is centralized in Spring configuration. As a result, services do not have to read profiles, inspect properties, or contain conditional branches to decide which implementation to call. Configuration is responsible for selecting the right component; services focus on their business logic.
