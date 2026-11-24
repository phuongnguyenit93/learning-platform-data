# Creating Missing Bean, Duplicate Bean, and Misconfiguration Errors and Writing Reproducing Tests

A Spring Boot application may fail to start because a dependency has no matching bean, because multiple beans satisfy one injection point, or because configuration fails to bind or activate as intended. These failures usually appear as long stack traces starting with `Failed to load ApplicationContext`, `UnsatisfiedDependencyException`, or `BeanCreationException`.

An effective way to learn and troubleshoot is to **deliberately introduce a controlled error, write a test reproducing that failure, inspect the root exception, fix the configuration or dependency wiring, and keep the test to protect the desired behavior**.

This lesson belongs to the **Integrated Practice** chapter of **Spring Boot Fundamentals**. We will practice three failure categories:

1. **Missing bean:** Spring cannot find a dependency to inject.
2. **Duplicate bean:** multiple candidates of the same type exist and Spring does not know which one to pick.
3. **Misconfiguration:** properties are missing, mistyped, invalid, or conditional configuration fails to activate a required bean.

We use a small checkout/payment example throughout. Tests focus on the ApplicationContext and dependency injection, because the goal is reproducing configuration failures in isolation.

## 1. Setting Up the Test Project

Examples use Java 17 or newer and Spring Boot 3.x. The primary testing APIs are JUnit Jupiter, AssertJ, and `ApplicationContextRunner`.

With Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

If the lab uses Jakarta Bean Validation such as `@NotBlank` and `@Min`, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

`spring-boot-starter-test` provides JUnit 5, AssertJ, Mockito, and Spring Boot test support. Use Spring Boot dependency management so libraries match your project's Boot version.

### 1.1. Suggested Source Structure

```text
src/
├── main/
│   ├── java/com/example/shop/
│   │   ├── ShopApplication.java
│   │   ├── checkout/
│   │   │   ├── CheckoutService.java
│   │   │   └── PaymentGateway.java
│   │   └── config/
│   │       └── CheckoutConfiguration.java
│   └── resources/
│       └── application.yml
└── test/
    └── java/com/example/shop/
        ├── MissingBeanTests.java
        ├── DuplicateBeanTests.java
        └── InvalidConfigurationTests.java
```

In examples using `ApplicationContextRunner`, we declare static configuration classes inside tests to spin up lightweight contexts deliberately. This reproduces failures without booting the whole application or pulling in unintended component scans.

## 2. Sample Application Model

Create the payment gateway contract:

```java
package com.example.shop.checkout;

public interface PaymentGateway {
    String name();
    PaymentResult charge(long amountInCents);
}
```

Payment result:

```java
package com.example.shop.checkout;

public record PaymentResult(
        String transactionId,
        boolean approved
) {
}
```

Service requiring a bean implementing `PaymentGateway`:

```java
package com.example.shop.checkout;

public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public String selectedGateway() {
        return paymentGateway.name();
    }

    public PaymentResult checkout(long amountInCents) {
        if (amountInCents <= 0) {
            throw new IllegalArgumentException(
                    "amount must be positive"
            );
        }
        return paymentGateway.charge(amountInCents);
    }
}
```

Configuration creating the service:

```java
package com.example.shop.config;

import com.example.shop.checkout.CheckoutService;
import com.example.shop.checkout.PaymentGateway;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CheckoutConfiguration {

    @Bean
    CheckoutService checkoutService(PaymentGateway paymentGateway) {
        return new CheckoutService(paymentGateway);
    }
}
```

Spring must resolve the `PaymentGateway` parameter on the bean factory method. It searches for candidate beans by type:

```text
Create CheckoutService bean
          │
          ▼
Needs PaymentGateway parameter
          │
          ▼
Find beans with compatible type
          │
      ┌───┴────────┐
      │            │
      ▼            ▼
  0 candidates  1 candidate
      │            │
      ▼            ▼
    Error        Inject
                   │
                   ▼
             CheckoutService
```

If two or more candidates exist, Spring needs additional selection metadata. These three outcomes form the foundation for the labs below.

## 3. Error 1: Missing Bean Dependency

### 3.1. Introducing the Intentional Failure

Keep `CheckoutConfiguration` as above without registering any `PaymentGateway` bean.

The context configures `CheckoutService`, yet the constructor/factory method requires a dependency that does not exist.

The message typically looks like:

```text
Parameter 0 of method checkoutService required a bean of type
'com.example.shop.checkout.PaymentGateway' that could not be found.
```

Or:

```text
No qualifying bean of type 'PaymentGateway' available
```

The outer exception is typically `UnsatisfiedDependencyException`; the deeper cause may be `NoSuchBeanDefinitionException`.

### 3.2. Writing a Reproducing Test with `ApplicationContextRunner`

`ApplicationContextRunner` lets you assemble a test context from specified configuration classes and inspect its state after startup.

```java
package com.example.shop;

import com.example.shop.config.CheckoutConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;

import static org.assertj.core.api.Assertions.assertThat;

class MissingBeanTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(CheckoutConfiguration.class);

    @Test
    void contextFailsWhenPaymentGatewayBeanIsMissing() {
        contextRunner.run(context -> {
            assertThat(context).hasFailed();

            assertThat(context.getStartupFailure())
                    .isNotNull()
                    .hasRootCauseInstanceOf(
                            NoSuchBeanDefinitionException.class
                    );
        });
    }
}
```

This test **expects the context to fail**. JUnit still passes if the context fails as predicted with the expected root cause type.

This is a helpful technique: instead of letting a startup failure crash the entire test suite, the runner captures the failure in `context.getStartupFailure()` for assertions.

### 3.3. Reading Exceptions Through the Cause Chain

Do not read only the first line `Failed to load ApplicationContext`. Look for:

- Which bean was being created?
- Which dependency failed to resolve?
- Which type was requested?
- Were candidate beans excluded by a profile or condition?
- Is the root cause a missing definition or another bean creation error?

A stack trace can span several layers:

```text
BeanCreationException
  └── UnsatisfiedDependencyException
        └── NoSuchBeanDefinitionException
```

Wrapper exceptions indicate the failing stage; the root cause normally pinpoints what must be fixed.

### 3.4. Fixing by Supplying an Implementation

Create an implementation:

```java
package com.example.shop.checkout;

public class SandboxPaymentGateway implements PaymentGateway {

    @Override
    public String name() {
        return "sandbox";
    }

    @Override
    public PaymentResult charge(long amountInCents) {
        return new PaymentResult("sandbox-transaction", true);
    }
}
```

Register the implementation:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentGatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new SandboxPaymentGateway();
    }
}
```

Add this configuration to the runner:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withUserConfiguration(
                        CheckoutConfiguration.class,
                        PaymentGatewayConfiguration.class
                );
```

Passing test:

```java
@Test
void contextStartsWhenPaymentGatewayIsProvided() {
    contextRunner.run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).hasSingleBean(PaymentGateway.class);
        assertThat(context).hasSingleBean(CheckoutService.class);

        assertThat(context.getBean(CheckoutService.class)
                .selectedGateway())
                .isEqualTo("sandbox");
    });
}
```

The test verifies the context succeeds, contains exactly one gateway bean, and the service receives the expected implementation.

### 3.5. Common Causes of Missing Beans

| Cause | Symptom | How to check |
|---|---|---|
| Class missing `@Component` | Implementation is not a bean | Check stereotypes or `@Bean` |
| Package outside component scan | Class is annotated yet undiscovered | Check `@SpringBootApplication` package |
| Configuration not imported | Bean declared in config is not loaded | Check `@Import` and component scan |
| Profile inactive | Bean with `@Profile` excluded | Check active profiles |
| Conditional property mismatch | Bean with `@ConditionalOnProperty` absent | Check property name and value |
| Dependency missing from classpath | Auto-configuration did not activate | Check runtime dependencies |
| Test slice excludes bean | Test context loads only part of the app | Import required test configuration |
| Bean definition excluded | Component scan/filter excludes class | Check scan filters and exclusions |

### 3.6. Missing Bean Due to Component Scan

Suppose the main application sits in:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

Default component scan starts from this class's package and its sub-packages. If a runner or adapter resides in `com.other.payment`, it falls outside the scan boundary.

Three common fixes:

1. Move the class into a sub-package under the application root.
2. Import the configuration/bean explicitly.
3. Configure component scan with matching base packages.

Do not widen scanning excessively if doing so could accidentally register classes from unrelated modules.

## 4. Error 2: Multiple Beans of the Same Type

Create two implementations for the same contract:

```java
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public String name() {
        return "card";
    }

    @Override
    public PaymentResult charge(long amountInCents) {
        return new PaymentResult("card-transaction", true);
    }
}
```

```java
public class BankTransferGateway implements PaymentGateway {

    @Override
    public String name() {
        return "bank-transfer";
    }

    @Override
    public PaymentResult charge(long amountInCents) {
        return new PaymentResult("bank-transaction", true);
    }
}
```

Register both:

```java
@Configuration(proxyBeanMethods = false)
class TwoPaymentGatewaysConfiguration {

    @Bean
    PaymentGateway cardPaymentGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    PaymentGateway bankTransferGateway() {
        return new BankTransferGateway();
    }
}
```

When creating `CheckoutService`, Spring sees two candidate beans of type `PaymentGateway`.

### 4.1. Error Message

The message typically looks like:

```text
No qualifying bean of type 'PaymentGateway' available:
expected single matching bean but found 2:
cardPaymentGateway,bankTransferGateway
```

The root cause is typically `NoUniqueBeanDefinitionException`; it may be wrapped in `UnsatisfiedDependencyException` or `BeanCreationException`.

### 4.2. Writing a Reproducing Test

```java
package com.example.shop;

import com.example.shop.config.CheckoutConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;

import static org.assertj.core.api.Assertions.assertThat;

class DuplicateBeanTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            CheckoutConfiguration.class,
                            TwoPaymentGatewaysConfiguration.class
                    );

    @Test
    void contextFailsWhenTwoGatewaysAreCandidates() {
        contextRunner.run(context -> {
            assertThat(context).hasFailed();

            assertThat(context.getStartupFailure())
                    .isNotNull()
                    .hasRootCauseInstanceOf(
                            NoUniqueBeanDefinitionException.class
                    );
        });
    }
}
```

The test verifies the ambiguity failure. If someone accidentally deletes one bean or alters the injection point, the test stops failing as expected and flags the regression.

## 5. Fixing Duplicate Beans with `@Primary`

If one implementation is genuinely the default choice, mark that bean with `@Primary`.

```java
@Configuration(proxyBeanMethods = false)
class PrimaryPaymentGatewayConfiguration {

    @Bean
    @Primary
    PaymentGateway cardPaymentGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    PaymentGateway bankTransferGateway() {
        return new BankTransferGateway();
    }
}
```

When injecting by type `PaymentGateway`, Spring prioritizes the primary candidate.

Test:

```java
@Test
void primaryGatewayIsSelected() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    CheckoutConfiguration.class,
                    PrimaryPaymentGatewayConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasBean("cardPaymentGateway");
                assertThat(context).hasBean("bankTransferGateway");

                assertThat(context.getBean(CheckoutService.class)
                        .selectedGateway())
                        .isEqualTo("card");
            });
}
```

Both beans still exist. `@Primary` simply lets Spring pick a default candidate for type-based injection.

### 5.1. When Should You Not Use `@Primary`?

If two implementations represent distinct capabilities and each consumer requires a specific choice, marking one primary can mask wiring the wrong bean.

For example, a bank transfer service should always use the bank gateway, while a card checkout service should always use the card gateway. Using `@Qualifier` expresses intent more clearly.

## 6. Fixing Duplicate Beans with `@Qualifier`

Annotate beans with qualifiers:

```java
@Configuration(proxyBeanMethods = false)
class QualifiedPaymentGatewayConfiguration {

    @Bean
    @Qualifier("card")
    PaymentGateway cardPaymentGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @Qualifier("bankTransfer")
    PaymentGateway bankTransferGateway() {
        return new BankTransferGateway();
    }
}
```

Select the bean at the injection point:

```java
public class CardCheckoutService {

    private final PaymentGateway paymentGateway;

    public CardCheckoutService(
            @Qualifier("card") PaymentGateway paymentGateway
    ) {
        this.paymentGateway = paymentGateway;
    }

    public String selectedGateway() {
        return paymentGateway.name();
    }
}
```

Register the service:

```java
@Bean
CardCheckoutService cardCheckoutService(
        @Qualifier("card") PaymentGateway paymentGateway
) {
    return new CardCheckoutService(paymentGateway);
}
```

Test:

```java
@Test
void qualifierSelectsCardGateway() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    QualifiedPaymentGatewayConfiguration.class,
                    CardCheckoutConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBean(CardCheckoutService.class)
                        .selectedGateway())
                        .isEqualTo("card");
            });
}
```

`@Qualifier` is a strong choice when consumers need a specific implementation. It documents intent right at the dependency injection point.

### 6.1. Bean Names and Qualifiers

A `@Bean` method's name also becomes its default bean name. Spring can use bean names as fallback qualifiers in some situations, though explicit qualifiers are recommended when selection carries architectural meaning.

### 6.2. Do Not Use `@Primary` to Mask Misconfiguration

If a bean is marked primary solely to make the application start, confirm it is truly the right implementation for that consumer. A green context does not prove the system calls the intended payment provider.

## 7. Error 3: Misconfigured Properties

Spring Boot commonly binds external configuration into objects using `@ConfigurationProperties`. If a property has the wrong type or violates validation constraints, bean creation can fail.

Create checkout properties:

```java
package com.example.shop.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "checkout")
@Validated
public record CheckoutProperties(
        @Min(1) int maxAttempts,
        @NotBlank String baseUrl
) {
}
```

Register properties:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CheckoutProperties.class)
class CheckoutPropertiesConfiguration {
}
```

### 7.1. Valid Configuration

```yaml
checkout:
  max-attempts: 3
  base-url: https://checkout.example.test
```

With this configuration, `max-attempts` binds to an integer of at least 1, and `base-url` must be a non-blank string. The properties bean is created only if both binding and validation succeed.

### 7.2. Creating a Validation Error

Invalid configuration:

```yaml
checkout:
  max-attempts: 0
  base-url: ""
```

`0` violates `@Min(1)` and the empty string violates `@NotBlank`.

### 7.3. Test Reproducing Misconfiguration

```java
package com.example.shop;

import com.example.shop.config.CheckoutPropertiesConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.bind.validation.BindValidationException;

import static org.assertj.core.api.Assertions.assertThat;

class InvalidConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            CheckoutPropertiesConfiguration.class
                    );

    @Test
    void contextFailsWhenPropertiesViolateValidation() {
        contextRunner
                .withPropertyValues(
                        "checkout.max-attempts=0",
                        "checkout.base-url="
                )
                .run(context -> {
                    assertThat(context).hasFailed();

                    assertThat(context.getStartupFailure())
                            .isNotNull()
                            .hasRootCauseInstanceOf(
                                    BindValidationException.class
                            );
                });
    }
}
```

The test deliberately supplies invalid values and asserts that the context fails due to binding validation.

If the project lacks `spring-boot-starter-validation`, Jakarta Validation constraints may not be enforced as expected. Add a validation provider compatible with Spring Boot before running the test.

### 7.4. Testing Valid Configuration

```java
@Test
void contextStartsWithValidCheckoutProperties() {
    contextRunner
            .withPropertyValues(
                    "checkout.max-attempts=3",
                    "checkout.base-url=https://checkout.example.test"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();

                CheckoutProperties properties =
                        context.getBean(CheckoutProperties.class);

                assertThat(properties.maxAttempts()).isEqualTo(3);
                assertThat(properties.baseUrl())
                        .isEqualTo("https://checkout.example.test");
            });
}
```

This test protects two things: the configuration binds properly and the bound values match expectations.

## 8. Wrong Data Type in Configuration

Another failure mode is a value that cannot be converted to the target Java type.

```yaml
checkout:
  max-attempts: many
  base-url: https://checkout.example.test
```

`max-attempts` expects an integer, yet `many` cannot be converted.

Test:

```java
@Test
void contextFailsWhenIntegerPropertyCannotBeConverted() {
    contextRunner
            .withPropertyValues(
                    "checkout.max-attempts=many",
                    "checkout.base-url=https://checkout.example.test"
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull()
                        .hasStackTraceContaining("checkout.max-attempts");
            });
}
```

Depending on Boot version and conversion service, the exact exception in the cause chain may differ; asserting on the property path is often more durable than coupling tightly to a deep internal exception class.

### 8.1. Missing Properties and Default Values

Not every missing property causes startup to fail. For primitive fields or fields with defaults, the application may receive defaults like `0` or `false`.

If a property is mandatory, express that requirement with validation or a data type/contract that detects missing state. Never assume every missing property automatically throws an exception.

## 9. Conditional Configuration Failing to Activate a Bean

A bean may only be created when a property matches a condition.

```java
@Configuration(proxyBeanMethods = false)
class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "notifications",
            name = "enabled",
            havingValue = "true"
    )
    NotificationSender notificationSender() {
        return new SmtpNotificationSender();
    }

    @Bean
    NotificationService notificationService(
            NotificationSender notificationSender
    ) {
        return new NotificationService(notificationSender);
    }
}
```

If configuration specifies the wrong prefix:

```yaml
notification:
  enabled: true
```

while the condition expects `notifications.enabled`, the `NotificationSender` bean is never created. `NotificationService` cannot inject its dependency and the context fails.

### 9.1. Reproducing Test

```java
@Test
void contextFailsWhenConditionalPropertyUsesWrongPrefix() {
    new ApplicationContextRunner()
            .withUserConfiguration(NotificationConfiguration.class)
            .withPropertyValues("notification.enabled=true")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull()
                        .hasRootCauseInstanceOf(
                                NoSuchBeanDefinitionException.class
                        );
            });
}
```

### 9.2. Fixing the Property

```yaml
notifications:
  enabled: true
```

Test for valid configuration:

```java
@Test
void notificationBeanIsCreatedWhenPropertyMatches() {
    new ApplicationContextRunner()
            .withUserConfiguration(NotificationConfiguration.class)
            .withPropertyValues("notifications.enabled=true")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(NotificationSender.class);
                assertThat(context).hasSingleBean(NotificationService.class);
            });
}
```

### 9.3. `matchIfMissing`

`@ConditionalOnProperty` has a `matchIfMissing` attribute. By default, when a property is absent and a specific value is required, the condition does not match.

If you want a default enabled/disabled behavior, define the semantics explicitly in configuration and test both cases: property present and property missing. Never rely on implicit defaults when side effects such as sending emails or publishing messages are involved.

## 10. Using `ApplicationContextRunner` to Write Configuration Tests

`ApplicationContextRunner` is especially effective for testing auto-configuration or conditional beans.

A runner can configure:

- User configuration classes.
- Property values.
- Active profiles.
- Classpath filters.
- Appropriate context customizers.

Profile example:

```java
new ApplicationContextRunner()
        .withUserConfiguration(ProfiledGatewayConfiguration.class)
        .withInitializer(context ->
                context.getEnvironment()
                        .setActiveProfiles("sandbox"))
        .run(context -> {
            // Assertions
        });
```

In real projects, use customizers compatible with your version to control the environment. Prefer explicit property/profile setup inside tests.

### 10.1. `AssertableApplicationContext`

Inside the `run` callback, the context provides assertion helpers:

```java
assertThat(context).hasNotFailed();
assertThat(context).hasBean("paymentGateway");
assertThat(context).hasSingleBean(PaymentGateway.class);
assertThat(context).doesNotHaveBean("legacyGateway");
```

When startup fails:

```java
assertThat(context).hasFailed();
assertThat(context.getStartupFailure()).isNotNull();
```

You can inspect the exception chain with AssertJ:

```java
assertThat(context.getStartupFailure())
        .hasRootCauseInstanceOf(NoSuchBeanDefinitionException.class);
```

Assert against the cause your test intends to guard. If the test only cares that the context fails to start, asserting `hasFailed()` and a stable message can be better than locking onto every wrapper exception.

### 10.2. Why Not Use `@SpringBootTest` for Every Negative Case?

`@SpringBootTest` is useful when testing an application context close to real app configuration. However, when context startup fails, failure occurs during test bootstrapping before JUnit enters the test method.

`ApplicationContextRunner` lets you exercise multiple small configurations in a single test class and assert both passing and failing outcomes. It is particularly suited for conditional beans and auto-configuration.

That does not replace all integration tests. A small runner test does not prove full production application wiring.

## 11. Using `@SpringBootTest` for a Full-Application Smoke Test

After fixing configuration bugs, keep a smoke test for the real application context:

```java
@SpringBootTest
class ShopApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

This test confirms the application can construct its context under the current test configuration.

To verify a specific bean:

```java
@SpringBootTest
class CheckoutWiringTests {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void checkoutServiceIsAvailable() {
        assertThat(checkoutService).isNotNull();
    }
}
```

However, this test does not prove the payment gateway points to the right provider or that HTTP requests succeed. Dedicated adapter tests are needed for those contracts.

### 11.1. Test Profile

```java
@SpringBootTest
@ActiveProfiles("test")
class ShopApplicationTests {
    @Test
    void contextLoads() {
    }
}
```

Keep in mind that `application-test.yml` can differ from production. A green context under the `test` profile does not prove the `prod` profile binds cleanly. If production configuration has critical conditional branches, test them via dedicated property/profile scenarios.

## 12. Reproducing a Component Scan Failure

This is a common missing-bean bug in real applications.

Main application:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

Implementation living in an unrelated package:

```java
package com.acme.gateway;

@Component
public class AcmePaymentGateway implements PaymentGateway {
    // ...
}
```

If component scan only starts from `com.example.shop`, `com.acme.gateway.AcmePaymentGateway` is not discovered.

### 12.1. Fixing Component Registration

```java
@Configuration(proxyBeanMethods = false)
@Import(AcmePaymentGateway.class)
class PaymentAdapterImportConfiguration {
}
```

You can use component scan, `@Import`, or `@Bean` depending on module layout. If the class has constructor dependencies, tests must supply those dependencies.

### 12.2. Choosing Component Scan vs. `@Import`

- Use component scan when package layout is part of normal component discovery.
- Use `@Import` when intentionally registering a configuration/adapter.
- Use `@Bean` when controlling construction or configuration of an implementation.
- Use auto-configuration when building a module/library with conditional bean registration.

Do not widen scan base packages arbitrarily just to turn tests green without understanding which classes will be picked up.

## 13. Reproducing an Inactive Profile Failure

Bean:

```java
@Component
@Profile("sandbox")
public class SandboxPaymentGateway implements PaymentGateway {
    // ...
}
```

If the `sandbox` profile is inactive, the bean will not exist.

Test both cases:

```java
@Test
void sandboxGatewayIsMissingWithoutSandboxProfile() {
    new ApplicationContextRunner()
            .withUserConfiguration(SandboxGatewayConfiguration.class)
            .run(context -> {
                assertThat(context).doesNotHaveBean(PaymentGateway.class);
            });
}
```

When activating the profile:

```java
@Test
void sandboxGatewayExistsWhenProfileIsActive() {
    new ApplicationContextRunner()
            .withInitializer(context ->
                    context.getEnvironment()
                            .setActiveProfiles("sandbox"))
            .withUserConfiguration(SandboxGatewayConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(PaymentGateway.class);
            });
}
```

Here `SandboxGatewayConfiguration` can register the class via `@Import` or `@Bean` so the test does not rely on full-app component scanning.

### 13.1. Profile Expressions

Spring supports profile expressions such as `@Profile("production & cloud")` or `@Profile("sandbox | local")`.

A single typo or inactive profile can make a bean disappear. Test important profile combinations rather than only a single default profile.

## 14. Reproducing Errors Involving `@ConditionalOnMissingBean`

`@ConditionalOnMissingBean` is commonly used in auto-configuration to provide a default bean when the application has not supplied its own implementation.

```java
@Configuration(proxyBeanMethods = false)
class DefaultPaymentConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultPaymentGateway() {
        return new SandboxPaymentGateway();
    }
}
```

Test default bean appears:

```java
@Test
void createsDefaultGatewayWhenNoCustomGatewayExists() {
    new ApplicationContextRunner()
            .withUserConfiguration(DefaultPaymentConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(PaymentGateway.class);
                assertThat(context).hasBean("defaultPaymentGateway");
            });
}
```

Test custom bean replaces default:

```java
@Test
void backsOffWhenCustomGatewayExists() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    DefaultPaymentConfiguration.class,
                    CustomPaymentConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(PaymentGateway.class);
                assertThat(context).hasBean("customPaymentGateway");
                assertThat(context).doesNotHaveBean("defaultPaymentGateway");
            });
}
```

This is core auto-configuration behavior: default beans should step aside for user-defined beans under published conditions.

Conditions are evaluated during bean definition registration. When writing auto-configurations, follow Spring Boot's ordering/condition rules so user configurations can override as designed. Do not assume arbitrary class declaration order controls condition evaluation order as desired.

## 15. Distinguishing Common Exceptions

| Exception | Meaning | Investigation path |
|---|---|---|
| `NoSuchBeanDefinitionException` | No bean matches the requested type/name | Registration, scan, profile, condition, import |
| `NoUniqueBeanDefinitionException` | Multiple matching beans without a unique choice | Qualifiers, primary, injection point |
| `UnsatisfiedDependencyException` | Spring could not resolve a bean's dependency | Follow cause chain to missing/ambiguous dependency |
| `BeanCreationException` | Bean creation failed | Check bean name and nested cause |
| `ConfigurationPropertiesBindException` | Binding configuration properties failed | Property name, type conversion, validation |
| `BindValidationException` | Values bound, then failed validation | Constraints and property values |

The outermost exception normally names the failing bean; deeper exceptions explain why.

## 16. Writing Tests for Multiple Failure Modes Without Breaking the Suite

A reproducing test should **expect failure** and assert the exact condition. It is not a test left accidentally red.

```java
@Test
void missingDependencyIsReported() {
    new ApplicationContextRunner()
            .withUserConfiguration(CheckoutConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasRootCauseInstanceOf(
                                NoSuchBeanDefinitionException.class
                        );
            });
}
```

If the context fails for a different reason, the test must fail. That is what we want: the test checks not just "some error happened," but **the right error happened**.

### 16.1. Do Not Assert Entire Stack Traces

Stack traces vary across Spring/Boot versions, JDKs, and bean processing details. Avoid snapshotting full stack traces unless strictly necessary.

Prefer asserting:

- Whether the context failed.
- Root cause type.
- Involved bean/type/property.
- A stable message identifying the error.

### 16.2. Negative and Positive Tests Go Together

For each failure mode:

1. Write a test reproducing the bad configuration.
2. Write a test for the valid configuration.
3. Confirm the context boots.
4. Assert the selected bean or property.
5. Keep both tests to guard both the failure mode and the fix.

The negative test proves the error is caught; the positive test proves the fix yields the intended state.

## 17. Using `ConditionEvaluationReport` When Auto-Configuration Does Not Run

When a bean created by Spring Boot auto-configuration fails to appear, a condition may have failed to match.

Spring Boot provides `ConditionEvaluationReport` to record which auto-configuration conditions matched or did not match.

Enable the debug condition report when launching the application:

```properties
debug=true
```

Startup output can show:

- Which auto-configurations matched.
- Which auto-configurations were skipped.
- Which property/class/bean conditions failed.
- Why a configuration was not applied.

### 17.1. Do Not Guess Conditions from Class Names

An auto-configuration may require classpath dependencies, specific property values, absence of user-supplied beans, or a matching web application context type.

Read the condition report to see which condition failed. Then write a reproducing test for that exact condition using `ApplicationContextRunner`.

### 17.2. `ApplicationContextRunner` and Auto-Configuration

When testing auto-configurations, use `AutoConfigurations.of(...)` with `ApplicationContextRunner` per your Spring Boot version.

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                PaymentAutoConfiguration.class
                        )
                );
```

Exact APIs and packages must match the project's Boot version. Tests should cover both matching and non-matching cases.

## 18. Comprehensive Example: Three Failures in a Row

Suppose the checkout module requires:

- One `PaymentGateway` must exist.
- If multiple gateways exist, checkout must select one explicitly.
- `checkout.max-attempts` must be a positive integer.
- `checkout.base-url` must be non-blank.

You can organize tests as a matrix:

| Test | Input configuration | Expected outcome |
|---|---|---|
| Missing gateway | No `PaymentGateway` registered | Context fails with missing bean |
| Duplicate gateway | Card and bank registered, no qualifier/primary | Context fails due to ambiguity |
| Primary gateway | Two beans, one primary | Context passes and selects primary |
| Qualified gateway | Two beans, qualified injection | Context passes and selects right bean |
| Invalid attempts | `max-attempts = 0` | Context fails validation |
| Wrong type | `max-attempts = many` | Context fails conversion |
| Missing conditional bean | Wrong property prefix | Context fails with missing dependency |
| Correct configuration | Valid properties and unambiguous gateway | Context passes |

This small regression suite protects multiple critical failure modes.

## 19. When to Use `@MockBean`/`@MockitoBean` in Context Tests?

If you want to test service wiring without calling external integrations, you can replace a port with a mock bean.

In Spring Boot 3.4+/Spring Framework 6.2+, use `@MockitoBean`:

```java
@SpringBootTest
class CheckoutWiringTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void serviceCanBeCreatedWithMockGateway() {
        given(paymentGateway.name()).willReturn("test");

        assertThat(checkoutService.selectedGateway())
                .isEqualTo("test");
    }
}
```

In older Boot versions, projects may use Spring Boot Test's `@MockBean`. That API is deprecated in newer Boot lines in favor of Spring Framework's bean override support; use the annotation matching your version.

### 19.1. Mock Beans Can Mask Registration Bugs

If tests always mock `PaymentGateway`, they can pass even when the real production adapter was never scanned or has broken conditions.

Write separate tests verifying production wiring/adapter registration whenever that risk matters. Mock context tests only prove the service works with the injected mock.

## 20. Reading and Diagnosing Stack Traces in Practice

When launching the app and hitting a startup failure, follow this sequence:

1. Find the first bean reported as failing to be created.
2. Read that bean's dependency chain.
3. Find the final exception in the `Caused by` chain.
4. If missing bean, inspect where that bean was supposed to be registered.
5. If ambiguous, list candidate beans and choose qualifier/primary.
6. If binding error, read the property path, actual value, and target Java type.
7. If a condition did not match, enable the condition report.
8. Write a minimal context runner reproducing the failing configuration.
9. Fix the configuration or registration.
10. Add positive assertions confirming the intended bean or property.

Log example:

```text
APPLICATION FAILED TO START

Parameter 0 of method checkoutService required a bean
of type 'PaymentGateway' that could not be found.

Action:
Consider defining a bean of type 'PaymentGateway'
in your configuration.
```

The suggested Action is a starting clue, not always the full fix. Before blindly adding a bean, check whether an existing implementation was excluded by a profile, condition, package scan, or test slice.

## 21. Mistakes When Writing Reproducing Tests

### 21.1. Expecting Failure Without Asserting the Cause

Avoid:

```java
contextRunner.run(context -> {
    assertThat(context).hasFailed();
});
```

If a test is meant to guard against a missing bean, it should assert `NoSuchBeanDefinitionException` as root cause or check the specific type/bean. If the context fails due to a different bug, the bare assertion still passes falsely.

### 21.2. Using `@SpringBootTest` for Every Property Combination

Large applications take significant time to bootstrap. Use `ApplicationContextRunner` for small configurations and many property permutations; reserve `@SpringBootTest` for integration tests needing the full application context.

### 21.3. Creating Mock Beans Without Testing Real Beans

Mock beans replace real implementations. When the goal is proving production adapters are registered, never use mocks as sole evidence.

### 21.4. Fixing Just Enough for a Green Context

A context can start yet pick the wrong payment gateway. After adding `@Primary`, assert `selectedGateway()` returns the expected gateway.

### 21.5. Letting Test Profiles Hide Production Bugs

The `test` profile may supply fake beans while the `prod` profile lacks an adapter. Passing under `test` does not prove `prod` wiring is valid. Write tests for critical profiles and conditions.

### 21.6. Overly Brittle Exception Message Assertions

Messages change across versions. Assert root cause types and affected properties/beans rather than fragile full stack traces.

## 22. Workflow from Bug to Regression Test

For every configuration error, follow this loop:

```text
Introduce controlled error
        │
        ▼
Write reproducing test
        │
        ▼
Confirm test fails for the right reason
        │
        ▼
Fix bean/configuration
        │
        ▼
Write or update positive test
        │
        ▼
Verify context and dependencies
        │
        ▼
Keep tests as regression protection
```

### 22.1. Express Assumptions Clearly in Test Names

Test names should describe the configuration state and expected outcome:

- `contextFailsWhenPaymentGatewayBeanIsMissing`.
- `contextFailsWhenMultipleGatewaysAreAmbiguous`.
- `primaryGatewayIsSelectedForUnqualifiedInjection`.
- `qualifierSelectsBankTransferGateway`.
- `contextFailsWhenMaxAttemptsIsZero`.
- `conditionalGatewayIsCreatedWhenPropertyIsEnabled`.

When a test fails in CI, readers immediately know which contract broke.

### 22.2. Keep Test Configuration Separate from Production Configuration

Place test fixtures in the test source set. Never put fake gateways into `src/main` just to make tests pass, unless it is genuinely an adapter designed for runtime use.

If production needs a default implementation, configure it explicitly with appropriate conditions, and test both default and custom override paths.

## 23. Practice Exercises

### Exercise 1 — Basic Missing Bean

Create `CheckoutService` needing `PaymentGateway` without registering any implementation. Write an `ApplicationContextRunner` test verifying the context fails with root cause `NoSuchBeanDefinitionException`.

### Exercise 2 — Fixing Missing Bean

Register `SandboxPaymentGateway` with `@Bean`. Write a positive test verifying the context passes and the service receives the expected implementation.

### Exercise 3 — Component Scan Package Mismatch

Place an implementation outside `@SpringBootApplication`'s root package. Write a test reproducing that the bean is not scanned. Fix it via package layout or `@Import` and verify the bean appears.

### Exercise 4 — Inactive Profile

Annotate a gateway with `@Profile("sandbox")`. Write tests with the profile inactive and active. Verify the difference in the bean registry.

### Exercise 5 — Conditional Property with Wrong Prefix

Use `@ConditionalOnProperty` for a notification sender. Intentionally misspell the property prefix, reproduce the missing dependency, then fix the property and add a positive test.

### Exercise 6 — Duplicate Bean

Register both card and bank gateways with the same type. Write a test verifying the context fails with `NoUniqueBeanDefinitionException`.

### Exercise 7 — `@Primary`

Mark the card gateway as primary. Write a test verifying both beans exist and checkout service selects the card gateway.

### Exercise 8 — `@Qualifier`

Remove primary and use qualifiers so a bank transfer service selects the bank gateway. Write a test verifying the exact injected implementation.

### Exercise 9 — `ConfigurationProperties` Validation

Create properties with `@Min` and `@NotBlank`. Test valid values, `0`, and blank strings. Verify validation failures are caught at context startup.

### Exercise 10 — Invalid Property Type

Pass a non-numeric string to an integer property. Write a test verifying binding fails and the failure mentions the property path.

### Exercise 11 — Missing Property

Omit a required property. Design validation or constructor contracts so startup fails with a clear message. Compare with a property having a default value.

### Exercise 12 — `ConditionalOnMissingBean`

Write a default gateway auto-configuration. Test that the default bean is created when no user bean exists and backs off when a custom gateway is present.

### Exercise 13 — Test Profile Masking Production Failures

Create a fake gateway only in the `test` profile while the production gateway has a broken condition. Write separate tests per profile and observe which context fails.

### Exercise 14 — Context Runner Across Multiple Property Scenarios

Create a test class with a shared runner and multiple property scenarios. Confirm each scenario gets an isolated context and matching assertions.

### Exercise 15 — Context Failure Cause Chains

Introduce two different failures in the same dependency graph. Inspect wrapper exceptions and root causes. Write assertions depending only on stable parts of the failure.

### Exercise 16 — Condition Evaluation

Create an auto-configuration with class/property/missing-bean conditions. Use the condition report to identify non-matching conditions, then write context runner tests for each case.

### Exercise 17 — Mock Beans and Production Adapters

Use `@MockitoBean` or `@MockBean` per version to test a service. Then write a separate test confirming the production adapter registers when its profile is active.

### Exercise 18 — Putting It All Together

Build a checkout app with two gateways, property validation, and a conditional notification sender. Intentionally introduce one missing bean, one ambiguous injection, and one invalid property. Write three negative tests, fix each error, and add positive tests protecting the final configuration.

## 24. Official References

- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring Boot testing tools and test contexts.
- [Spring Boot Reference — Developing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): developing and testing auto-configurations.
- [Spring Boot API — ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): building lightweight contexts and inspecting startup outcomes.
- [Spring Boot API — AssertableApplicationContext](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/assertj/AssertableApplicationContext.html): accessing startup failures and context assertions.
- [Spring Framework Reference — Autowiring](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): dependency injection, candidate resolution, qualifiers, and primary.
- [Spring Framework Reference — @Primary](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html): prioritizing a bean when multiple candidates exist.
- [Spring Framework Reference — Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html): filtering bean candidates with qualifiers.
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, binding, and environment configuration.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties` and type-safe binding.
- [Jakarta Bean Validation](https://beanvalidation.org/): constraint annotations such as `@Min` and `@NotBlank`.

**Key takeaway:** a missing bean means no matching candidate exists; a duplicate bean means multiple candidates exist without an explicit choice at the injection point; misconfiguration can cause binding/validation failure or keep conditional beans from registering. Deliberately create controlled errors with small context configurations, use `ApplicationContextRunner` to assert both startup failure and root cause, and add positive tests verifying the right beans and properties are chosen after fixing. That turns long stack traces into concrete, readable regression tests you can re-run on every configuration change.
