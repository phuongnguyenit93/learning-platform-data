# Testing Missing-Candidate and Multiple-Candidate Scenarios

When Spring creates a bean, the IoC container must locate the required dependencies to pass into constructors, fields, or factory methods. Two situations commonly cause bean selection to fail:

- **No candidate:** the context has no bean satisfying the injection point's type, qualifier, profile, or conditions.
- **Ambiguous candidates:** multiple beans match equally, leaving Spring without enough information to choose a single unique bean.

These two situations typically surface at application startup, when Spring creates beans and resolves dependencies. They can prevent the ApplicationContext from refreshing successfully, causing the Spring Boot application to fail to start.

To control bean selection reliably, you need to understand the corresponding exceptions, how Spring picks candidates, mechanisms like **@Primary** and **@Qualifier**, and how to write tests reproducing each scenario. This lesson uses a consistent payment-provider example throughout.

## 1. Starting from a single dependency

Suppose the application has an interface:

~~~java
package com.example.payment;

public interface PaymentProvider {
    String name();

    void charge(long orderId);
}
~~~

A service requires exactly one PaymentProvider:

~~~java
package com.example.payment;

public class CheckoutService {
    private final PaymentProvider provider;

    public CheckoutService(PaymentProvider provider) {
        this.provider = provider;
    }

    public void checkout(long orderId) {
        provider.charge(orderId);
    }

    public PaymentProvider provider() {
        return provider;
    }
}
~~~

Constructor injection expresses that **CheckoutService cannot operate without a PaymentProvider**. When Spring creates the CheckoutService bean, the container must find a bean of a compatible type to pass into the constructor.

~~~text
ApplicationContext
       │
       ▼
Create CheckoutService
       │
       ▼
Resolve PaymentProvider
       │
       ├── No candidate
       │       └── Cannot create CheckoutService
       │
       ├── One candidate
       │       └── Inject that bean
       │
       └── Multiple candidates
               ├── Clear selection rule exists
               │       └── Inject selected candidate
               └── No distinguishing rule
                       └── Ambiguous dependency
~~~

This is the **single-dependency resolution** problem. It differs from injecting a List or Map of multiple beans, where the consumer intentionally requests a set of candidates.

## 2. The no-candidate case

Suppose only CheckoutService is registered:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    CheckoutService checkoutService(PaymentProvider provider) {
        return new CheckoutService(provider);
    }
}
~~~

Yet the context has no bean implementing PaymentProvider. When Spring calls the checkoutService factory method, it cannot supply the provider parameter.

The result is typically a context startup failure with exceptions related to bean creation and dependency resolution. Exceptions you may see include:

- **UnsatisfiedDependencyException:** Spring could not satisfy a dependency of the bean being created.
- **NoSuchBeanDefinitionException:** no matching bean was found for the requested type or name.
- **BeanCreationException:** outer wrapper exception during bean creation; the specific reason usually lies in the cause chain.

An abbreviated log might look like:

~~~text
org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'checkoutService':
Unsatisfied dependency expressed through method 'checkoutService'
parameter 0
    ...
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.payment.PaymentProvider' available
    ...
~~~

The actual method name, parameter index, and log layout vary by bean declaration style and Spring version. What to recognize is that **CheckoutService is the affected bean, while PaymentProvider is the missing dependency**.

### 2.1. Common causes of having no candidate

An implementation may exist in source code yet be absent from the candidate set because:

1. The class is not registered as a bean.
2. The package containing the component is outside the component scan scope.
3. The configuration class containing the @Bean method has not been imported or scanned.
4. The active profile does not match the bean's @Profile.
5. An auto-configuration or @Conditional condition is not met.
6. The dependency containing the implementation class is missing from the runtime classpath.
7. The bean is excluded from autowiring by metadata such as autowireCandidate=false.
8. A qualifier at the injection point filters out all existing beans.
9. The dependency's generic type is incompatible with registered beans.

Example implementation:

~~~java
public class CardPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "card";
    }

    @Override
    public void charge(long orderId) {
        // Handle card payment.
    }
}
~~~

This class **does not automatically become a bean** without a registration mechanism. You can add @Component:

~~~java
@Component
public class CardPaymentProvider implements PaymentProvider {
    // ...
}
~~~

or register via @Bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {
    @Bean
    PaymentProvider cardPaymentProvider() {
        return new CardPaymentProvider();
    }
}
~~~

Both approaches can create the bean, provided the configuration is processed by Spring and any related dependencies can be initialized.

### 2.2. Missing bean vs failed bean creation

| Symptom | Meaning |
|---|---|
| **NoSuchBeanDefinitionException** | No matching candidate found to satisfy the dependency. |
| **BeanCreationException** with a cause from constructor/factory method | The bean definition may exist, yet instance creation failed. |
| **UnsatisfiedDependencyException** | A bean could not be created because a dependency went unsatisfied; check the nested cause. |

For instance, if CardPaymentProvider is registered but its constructor throws IllegalStateException due to missing configuration, that is not simply "missing bean." Spring found the definition yet could not instantiate it.

When reading logs, do not stop at the first line like **Application run failed** or **Error creating bean**. Trace the **Caused by:** sections to pinpoint which layer holds the root error.

## 3. The multiple-candidates-of-same-type case

Now register two implementations:

~~~java
@Component
public class CardPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "card";
    }

    @Override
    public void charge(long orderId) {
        System.out.println("Charge by card: " + orderId);
    }
}
~~~

~~~java
@Component
public class WalletPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "wallet";
    }

    @Override
    public void charge(long orderId) {
        System.out.println("Charge by wallet: " + orderId);
    }
}
~~~

If CheckoutService still asks for:

~~~java
public CheckoutService(PaymentProvider provider) {
    this.provider = provider;
}
~~~

Spring finds two candidates:

~~~text
PaymentProvider
├── cardPaymentProvider
└── walletPaymentProvider

CheckoutService needs exactly one PaymentProvider
                 │
                 ▼
       Two equally matching candidates exist
                 │
                 ▼
       Cannot tell which bean to choose
~~~

Without a qualifier, primary candidate, or other sufficiently clear resolution rule, Spring reports **NoUniqueBeanDefinitionException**. During bean creation, this exception may be wrapped in UnsatisfiedDependencyException or BeanCreationException.

Abbreviated log:

~~~text
org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'checkoutService'
    ...
Caused by: org.springframework.beans.factory.NoUniqueBeanDefinitionException:
No qualifying bean of type 'com.example.payment.PaymentProvider'
available: expected single matching bean but found 2:
cardPaymentProvider,walletPaymentProvider
    ...
~~~

Bean names and candidate counts in the example are illustrative. The key point is that **multiple beans match a single dependency**, not that Spring failed to create any bean.

## 4. Using @Primary to pick a default candidate

If the application has one implementation that should be used as the default choice, mark it with **@Primary**.

~~~java
@Component
@Primary
public class CardPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "card";
    }

    @Override
    public void charge(long orderId) {
        System.out.println("Charge by card: " + orderId);
    }
}
~~~

WalletPaymentProvider remains a valid bean:

~~~java
@Component
public class WalletPaymentProvider implements PaymentProvider {
    // ...
}
~~~

When an injection point requires exactly one PaymentProvider and remaining candidates are otherwise equal, Spring can pick the bean marked @Primary.

~~~text
PaymentProvider candidates
├── cardPaymentProvider   @Primary
└── walletPaymentProvider
             │
             ▼
Single PaymentProvider dependency
             │
             ▼
      Select cardPaymentProvider
~~~

### 4.1. @Primary does not remove remaining beans from the context

After marking CardPaymentProvider as primary, both beans stay registered. If a consumer requests:

~~~java
public PaymentCatalog(List<PaymentProvider> providers) {
    this.providers = providers;
}
~~~

the goal is to retrieve all matching candidates. @Primary **does not reduce the List to only CardPaymentProvider**.

Similarly, Map<String, PaymentProvider> can still contain both beans. @Primary mainly resolves **a single dependency** when multiple candidates exist.

### 4.2. Do not mark multiple beans @Primary for the same type

If two candidates are both marked @Primary with no other rule distinguishing them, a single dependency remains ambiguous. @Primary is only useful when there is one clear preferred option in the matching candidate set.

### 4.3. @Primary does not replace qualifiers in every scenario

If a service must always use the e-wallet, even while CardPaymentProvider is primary, declare the requirement explicitly with a qualifier. That expresses intent more accurately than relying on the application-wide default.

## 5. Using @Qualifier to pick a specific bean

**@Qualifier** lets you filter candidates by metadata. For example:

~~~java
@Component
@Qualifier("card")
public class CardPaymentProvider implements PaymentProvider {
    // ...
}
~~~

~~~java
@Component
@Qualifier("wallet")
public class WalletPaymentProvider implements PaymentProvider {
    // ...
}
~~~

Consumer picks the exact group or implementation:

~~~java
@Service
public class CardCheckoutService {
    private final PaymentProvider provider;

    public CardCheckoutService(
            @Qualifier("card") PaymentProvider provider) {
        this.provider = provider;
    }
}
~~~

When resolving the dependency, Spring filters candidates by matching qualifier. If only one candidate remains, injection can succeed even when multiple beans of the same type exist in the context.

### 5.1. Qualifiers can work with bean names

~~~java
@Component("cardPaymentProvider")
public class CardPaymentProvider implements PaymentProvider {
    // ...
}
~~~

~~~java
public CardCheckoutService(
        @Qualifier("cardPaymentProvider") PaymentProvider provider) {
    this.provider = provider;
}
~~~

Bean names can serve as qualifiers during autowiring when applicable. However, **@Qualifier** is designed to express selection criteria; it is not merely an alternate syntax for variable names.

### 5.2. Creating semantic custom qualifiers

In large applications, qualifier strings can become hard to manage. You can define an annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.METHOD
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface OnlinePayment {
}
~~~

Mark the implementation:

~~~java
@Component
@OnlinePayment
public class WalletPaymentProvider implements PaymentProvider {
    // ...
}
~~~

Inject:

~~~java
public OnlineCheckoutService(
        @OnlinePayment PaymentProvider provider) {
    this.provider = provider;
}
~~~

Custom qualifiers express business roles like **OnlinePayment**, **OfflinePayment**, **PrimaryRegion**, or **FallbackStorage** instead of scattering arbitrary strings.

### 5.3. Qualifiers can filter collections

Qualifiers are not limited to single dependencies. With:

~~~java
public OnlinePaymentCatalog(
        @OnlinePayment List<PaymentProvider> providers) {
    this.providers = providers;
}
~~~

Spring can provide all candidates with matching qualifiers. If multiple beans carry the OnlinePayment qualifier, the collection will contain those matching beans.

## 6. Combining @Primary and @Qualifier

These two annotations solve different problems:

- **@Primary:** default choice when a single dependency has multiple candidates.
- **@Qualifier:** filters candidates by specific criteria at the injection point.

For example:

~~~java
@Component
@Primary
@Qualifier("card")
public class CardPaymentProvider implements PaymentProvider {
    // ...
}
~~~

~~~java
@Component
@Qualifier("wallet")
public class WalletPaymentProvider implements PaymentProvider {
    // ...
}
~~~

An injection point:

~~~java
public CheckoutService(
        @Qualifier("wallet") PaymentProvider provider) {
    this.provider = provider;
}
~~~

explicitly specifies the wallet group. CardPaymentProvider's @Primary does not let that bean bypass the wallet qualifier.

A conceptual flow:

~~~text
All beans of compatible type
             │
             ▼
Filter by qualifier / candidate metadata
             │
             ▼
If one candidate remains: select that candidate
             │
             ▼
If multiple candidates remain:
             │
             ▼
Consider primary and other selection criteria
             │
             ▼
If still indistinguishable:
NoUniqueBeanDefinitionException
~~~

This is an easy-to-follow model, not a complete map of every internal branch in the autowiring algorithm. Spring also considers generic types, dependency names, priority, and other metadata depending on the situation.

## 7. Distinguishing @Order from @Primary

These two annotations are often misused:

| Annotation | Primary goal |
|---|---|
| **@Primary** | Choose the default bean for a single dependency when multiple candidates exist. |
| **@Qualifier** | Filter candidates by metadata at the injection point. |
| **@Order** | Sort elements at injection points receiving ordered collections, such as List or arrays. |

For example:

~~~java
@Component
@Order(1)
public class CardPaymentProvider implements PaymentProvider {
    // ...
}
~~~

~~~java
@Component
@Order(2)
public class WalletPaymentProvider implements PaymentProvider {
    // ...
}
~~~

@Order does not mean CardPaymentProvider will automatically be chosen for:

~~~java
public CheckoutService(PaymentProvider provider) {
    this.provider = provider;
}
~~~

If a single bean is needed, use @Primary or @Qualifier. If an ordered List<PaymentProvider> is needed, @Order is the appropriate mechanism.

## 8. When a dependency may not exist

An application does not always require an implementation. For instance, an email sending module may be optional; a local environment might not configure an email provider.

If you declare a required single dependency:

~~~java
public NotificationService(NotificationGateway gateway) {
    this.gateway = gateway;
}
~~~

then having no candidate can prevent the context from starting. If absence is valid, express optionality explicitly.

### 8.1. Using Optional<T>

~~~java
import java.util.Optional;

@Service
public class NotificationService {
    private final Optional<NotificationGateway> gateway;

    public NotificationService(Optional<NotificationGateway> gateway) {
        this.gateway = gateway;
    }

    public void notifyUser(String message) {
        gateway.ifPresent(value -> value.send(message));
    }
}
~~~

When no matching bean exists, Spring can inject **Optional.empty()**. When one matching candidate exists, Optional holds that bean.

If multiple candidates exist with no clear selection rule, Optional does not automatically resolve ambiguity. Optional expresses **a single dependency may be absent**, not "pick any bean out of many."

### 8.2. Using ObjectProvider<T>

**ObjectProvider** is useful when you want to defer lookup until the time of use:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class OptionalNotificationService {
    private final ObjectProvider<NotificationGateway> gatewayProvider;

    public OptionalNotificationService(
            ObjectProvider<NotificationGateway> gatewayProvider) {
        this.gatewayProvider = gatewayProvider;
    }

    public void notifyUser(String message) {
        NotificationGateway gateway =
                gatewayProvider.getIfAvailable();

        if (gateway != null) {
            gateway.send(message);
        }
    }
}
~~~

Some important methods:

| API | When no candidate exists | When multiple indistinguishable candidates exist |
|---|---|---|
| **getObject()** | Throws missing bean error. | Throws non-unique bean error. |
| **getIfAvailable()** | Returns null. | May throw NoUniqueBeanDefinitionException. |
| **getIfUnique()** | Returns null. | Returns null if there is no unique candidate per resolution rules. |
| **stream()** | Empty stream. | Returns stream of matching candidates. |
| **orderedStream()** | Empty stream. | Returns stream sorted by Spring's order rules. |

If the application needs all implementations, use a stream or collection. If it needs only one optional bean, getIfAvailable or getIfUnique distinguishes between "available to pick" and "a unique candidate exists."

### 8.3. Optional does not replace collections

**Optional<PaymentProvider>** represents at most one selected candidate. If all payment providers are needed, use **List<PaymentProvider>**, **Set<PaymentProvider>**, **Map<String, PaymentProvider>**, or **ObjectProvider<PaymentProvider>.orderedStream()**.

## 9. When multiple beans exist and you want all of them

If a service genuinely needs every implementation, do not force Spring to pick one single bean. Declare a collection:

~~~java
@Service
public class PaymentCatalog {
    private final List<PaymentProvider> providers;

    public PaymentCatalog(List<PaymentProvider> providers) {
        this.providers = providers;
    }
}
~~~

With both CardPaymentProvider and WalletPaymentProvider beans, the List can contain both. When no candidate exists, collection injection and dependency declarations can be subject to corresponding required-dependency rules; when having zero elements is a valid business scenario, **ObjectProvider.orderedStream()** more clearly expresses the intent to return an empty stream.

Map:

~~~java
public PaymentCatalog(Map<String, PaymentProvider> providersByBeanName) {
    this.providersByBeanName = providersByBeanName;
}
~~~

provides **bean names** as keys. Set fits when no order needs to be expressed. Do not use @Primary expecting a collection to hold only the primary bean; collections are meant to gather matching candidates.

## 10. Testing the no-candidate scenario

A focused way to test Spring Boot configuration is **ApplicationContextRunner**. This utility lets you spin up a lightweight ApplicationContext with chosen configuration, checking whether the context succeeds or fails without starting an entire web server.

The examples below use JUnit 5, AssertJ, and Spring Boot Test. An appropriate test dependency is required, for example:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Suppose the interface and service are:

~~~java
public interface PaymentProvider {
    String name();
}
~~~

~~~java
public class CheckoutService {
    private final PaymentProvider provider;

    public CheckoutService(PaymentProvider provider) {
        this.provider = provider;
    }

    public String providerName() {
        return provider.name();
    }
}
~~~

### 10.1. Missing-bean configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MissingProviderConfiguration {
    @Bean
    CheckoutService checkoutService(PaymentProvider provider) {
        return new CheckoutService(provider);
    }
}
~~~

No PaymentProvider bean is declared. Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class MissingProviderTest {
    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(MissingProviderConfiguration.class);

    @Test
    void contextFailsWhenRequiredProviderIsMissing() {
        runner.run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(NoSuchBeanDefinitionException.class);
        });
    }
}
~~~

This test confirms the context failed and its deepest root cause is of type NoSuchBeanDefinitionException. The outermost exception can be UnsatisfiedDependencyException or BeanCreationException depending on the bean creation path.

What must be verified is that **the context genuinely lacks a PaymentProvider**. If a bean accidentally exists from auto-configuration or another test configuration, the test will not accurately reproduce the scenario.

### 10.2. Testing with context runner for an optional provider

If the dependency is optional, the configuration can use ObjectProvider:

~~~java
import org.springframework.beans.factory.ObjectProvider;

public class OptionalCheckoutService {
    private final ObjectProvider<PaymentProvider> providers;

    public OptionalCheckoutService(
            ObjectProvider<PaymentProvider> providers) {
        this.providers = providers;
    }

    public boolean hasProvider() {
        return providers.getIfAvailable() != null;
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class OptionalProviderConfiguration {
    @Bean
    OptionalCheckoutService optionalCheckoutService(
            ObjectProvider<PaymentProvider> providers) {
        return new OptionalCheckoutService(providers);
    }
}
~~~

Test:

~~~java
@Test
void contextStartsWhenOptionalProviderIsMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(OptionalProviderConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                OptionalCheckoutService service =
                        context.getBean(OptionalCheckoutService.class);
                assertThat(service.hasProvider()).isFalse();
            });
}
~~~

Here the context starts because the requested dependency is ObjectProvider; the provider itself can be injected even with zero PaymentProvider candidates. Calling getIfAvailable returns null.

## 11. Testing the multiple-candidate scenario

To reproduce ambiguity, register two differently named beans both implementing PaymentProvider:

~~~java
@Configuration(proxyBeanMethods = false)
class MultipleProviderConfiguration {

    @Bean
    PaymentProvider cardProvider() {
        return () -> "card";
    }

    @Bean
    PaymentProvider walletProvider() {
        return () -> "wallet";
    }

    @Bean
    CheckoutService checkoutService(PaymentProvider provider) {
        return new CheckoutService(provider);
    }
}
~~~

Test:

~~~java
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;

class MultipleProviderTest {
    @Test
    void contextFailsWhenSingleDependencyHasMultipleCandidates() {
        new ApplicationContextRunner()
                .withUserConfiguration(MultipleProviderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    NoUniqueBeanDefinitionException.class);
                });
    }
}
~~~

The context cannot create CheckoutService because the PaymentProvider parameter has two candidates: **cardProvider** and **walletProvider**. The test checks the deepest root cause instead of relying on the full exception message text, which can change across versions.

### 11.1. Testing the fix with @Primary

Mark one bean:

~~~java
@Configuration(proxyBeanMethods = false)
class PrimaryProviderConfiguration {

    @Bean
    @Primary
    PaymentProvider cardProvider() {
        return () -> "card";
    }

    @Bean
    PaymentProvider walletProvider() {
        return () -> "wallet";
    }

    @Bean
    CheckoutService checkoutService(PaymentProvider provider) {
        return new CheckoutService(provider);
    }
}
~~~

Test:

~~~java
@Test
void primaryCandidateIsInjected() {
    new ApplicationContextRunner()
            .withUserConfiguration(PrimaryProviderConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                CheckoutService service =
                        context.getBean(CheckoutService.class);
                assertThat(service.providerName()).isEqualTo("card");
            });
}
~~~

The test confirms that when multiple beans exist and one candidate is marked primary, a single dependency resolves according to that choice.

### 11.2. Testing the fix with @Qualifier

If the service specifically needs wallet, declare the qualifier at the injection point:

~~~java
@Configuration(proxyBeanMethods = false)
class QualifiedProviderConfiguration {

    @Bean("cardProvider")
    PaymentProvider cardProvider() {
        return () -> "card";
    }

    @Bean("walletProvider")
    PaymentProvider walletProvider() {
        return () -> "wallet";
    }

    @Bean
    CheckoutService checkoutService(
            @Qualifier("walletProvider") PaymentProvider provider) {
        return new CheckoutService(provider);
    }
}
~~~

Test:

~~~java
@Test
void qualifierSelectsWalletProvider() {
    new ApplicationContextRunner()
            .withUserConfiguration(QualifiedProviderConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                CheckoutService service =
                        context.getBean(CheckoutService.class);
                assertThat(service.providerName()).isEqualTo("wallet");
            });
}
~~~

Qualifiers make clear which implementation CheckoutService requires, regardless of which bean is marked primary elsewhere.

### 11.3. Testing a non-matching qualifier scenario

If the injection point requests:

~~~java
@Qualifier("bank") PaymentProvider provider
~~~

while the context only has card and wallet qualifiers, Spring has no remaining satisfying candidate. This case resembles **no candidate after filtering**. Tests should assert the context failed and inspect the cause to see which dependency type went unsatisfied.

Point to remember: having multiple beans of the same type does not mean every injection point is ambiguous; qualifiers can filter them down to zero, one, or multiple candidates.

## 12. Testing collections when multiple beans exist

If a consumer requests a List, Spring does not need to pick a single unique implementation:

~~~java
public class PaymentProviderCatalog {
    private final List<PaymentProvider> providers;

    public PaymentProviderCatalog(List<PaymentProvider> providers) {
        this.providers = providers;
    }

    public List<String> names() {
        return providers.stream()
                .map(PaymentProvider::name)
                .toList();
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class ProviderCollectionConfiguration {
    @Bean
    PaymentProvider cardProvider() {
        return () -> "card";
    }

    @Bean
    PaymentProvider walletProvider() {
        return () -> "wallet";
    }

    @Bean
    PaymentProviderCatalog catalog(List<PaymentProvider> providers) {
        return new PaymentProviderCatalog(providers);
    }
}
~~~

Test:

~~~java
@Test
void collectionReceivesAllMatchingProviders() {
    new ApplicationContextRunner()
            .withUserConfiguration(ProviderCollectionConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                PaymentProviderCatalog catalog =
                        context.getBean(PaymentProviderCatalog.class);
                assertThat(catalog.names())
                        .containsExactlyInAnyOrder("card", "wallet");
            });
}
~~~

The test uses **containsExactlyInAnyOrder** because no ordering contract was established. If ordering is a requirement, configure @Order and assert with **containsExactly**.

To handle the zero-elements case explicitly:

~~~java
public class OptionalProviderCatalog {
    private final ObjectProvider<PaymentProvider> provider;

    public OptionalProviderCatalog(
            ObjectProvider<PaymentProvider> provider) {
        this.provider = provider;
    }

    public List<PaymentProvider> all() {
        return provider.orderedStream().toList();
    }
}
~~~

orderedStream() can return an empty stream when no candidate exists. This makes the intent "the list may have zero elements" explicit and avoids depending on how a required collection dependency resolves at individual injection points.

## 13. Using @SpringBootTest to test the full application

ApplicationContextRunner fits a narrow slice of configuration. When you want to verify the actual application's configuration, you can use **@SpringBootTest**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest
class PaymentProviderContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void applicationHasExpectedPaymentProviders() {
        assertThat(context.getBeansOfType(PaymentProvider.class))
                .containsKeys("cardPaymentProvider", "walletPaymentProvider");
    }
}
~~~

This test initializes the context following application configuration and verifies which beans are actually present inside it. It is helpful when candidates depend on component scanning, profiles, auto-configuration, or multiple configuration classes.

However, @SpringBootTest may initialize many components, connect to external systems, or start an embedded web server depending on test configuration. For simple bean selection cases, ApplicationContextRunner is usually faster and better isolated.

### 13.1. Checking startup failures of the whole application

If the application genuinely fails to start due to ambiguity, a default @SpringBootTest can also fail right when building the context. In that case:

- Read the outermost exception to identify which bean is being created.
- Look for NoUniqueBeanDefinitionException or NoSuchBeanDefinitionException in the cause chain.
- Verify the candidate bean set in the context test.
- Avoid catching exceptions in production merely to make tests turn green.

Do not write tests that only assert "the context failed" without checking the cause. A context can fail due to a database, port, property, or unrelated error; tests should assert the specific exception or desired bean selection behavior.

## 14. Distinguishing ambiguity from duplicate bean names

These two errors are often confused:

### 14.1. Multiple differently named beans of the same type

~~~text
cardProvider   : PaymentProvider
walletProvider : PaymentProvider
~~~

Dependency:

~~~java
CheckoutService(PaymentProvider provider)
~~~

If there is no way to pick a candidate, the error is **NoUniqueBeanDefinitionException**.

### 14.2. Two definitions with the same bean name

Suppose two configurations both register:

~~~java
@Bean
PaymentProvider paymentProvider() {
    return new CardPaymentProvider();
}
~~~

and:

~~~java
@Bean
PaymentProvider paymentProvider() {
    return new WalletPaymentProvider();
}
~~~

If both definitions are registered into one context under the same name and overriding is disabled, Spring may report **BeanDefinitionOverrideException** during bean definition registration.

This is not type-based dependency ambiguity. The issue is **two definitions competing for the same bean name**.

| Situation | Common exception | Cause |
|---|---|---|
| No matching bean | NoSuchBeanDefinitionException or dependency-wrapping exception | Candidate set is empty. |
| Multiple beans of same type for single dependency | NoUniqueBeanDefinitionException or dependency-wrapping exception | Candidate set has multiple elements, cannot pick one. |
| Multiple bean definitions with same name | BeanDefinitionOverrideException when overriding is disallowed | Registration name collision. |
| Bean registered yet instance creation failed | BeanCreationException with specific cause | Constructor, factory method, or dependency threw an error during initialization. |

In typical Spring Boot configurations, bean definition overriding is disabled by default; do not enable overriding just to hide duplicate-name errors. Assign clear names and decide which implementation should be registered.

## 15. Candidate sets also depend on profiles and conditions

Two environments can have different bean sets even from the exact same source code.

~~~java
@Component
@Profile("development")
public class FakePaymentProvider implements PaymentProvider {
    public String name() {
        return "fake";
    }
}
~~~

~~~java
@Component
@Profile("production")
public class RealPaymentProvider implements PaymentProvider {
    public String name() {
        return "real";
    }
}
~~~

If the development profile is active, FakePaymentProvider can be a candidate. If production is active, RealPaymentProvider can be registered instead.

Similarly, auto-configuration can register beans based on **@ConditionalOnClass**, **@ConditionalOnProperty**, **@ConditionalOnBean**, or **@ConditionalOnMissingBean**.

When encountering no candidate, check:

1. Which profile is actually activated.
2. Whether properties are loaded from files, environment variables, or other sources.
3. Whether the dependency is on the runtime classpath.
4. Whether auto-configuration was excluded or did not match.
5. Whether the bean definition is registered in the context under inspection.

Do not add @Primary before confirming candidates actually exist. @Primary cannot resolve an empty candidate set.

## 16. Diagnosing with ApplicationContext and Actuator

In code or a debugger, you can inspect matching beans:

~~~java
String[] names =
        context.getBeanNamesForType(PaymentProvider.class);

for (String name : names) {
    System.out.println(name);
}
~~~

Or:

~~~java
Map<String, PaymentProvider> providers =
        context.getBeansOfType(PaymentProvider.class);
~~~

The second API retrieves instances and may trigger initialization of matching beans. If you only want candidate names, using the name-by-type API is more appropriate.

In Spring Boot, **Actuator /actuator/beans** helps observe running beans if Actuator is added and endpoints are exposed per configuration. The **/actuator/conditions** endpoint shows why auto-configurations were applied or skipped.

Example of restricted exposure configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,beans,conditions
~~~

Management endpoints can reveal internal structure. In real environments, protect them with authentication/authorization and restrict network access; do not expose them publicly merely for debugging convenience.

### 16.1. Condition report helps find why no candidate exists

Run the application with the option:

~~~bash
java -jar app.jar --debug
~~~

Boot can print a **Condition Evaluation Report** in the startup log. If the expected bean comes from auto-configuration, the report can indicate:

- A required class is missing from the classpath.
- A property is missing or its value does not match.
- A dependent bean is missing.
- The auto-configuration was excluded.
- A default bean was not created because the application already supplied a matching bean.

A positive match at the auto-configuration level does not prove every bean inside initialized successfully; combine the report with the bean list and stack trace.

## 17. Choosing the right testing strategy

| Testing goal | Suitable approach |
|---|---|
| Required bean missing, context must fail | ApplicationContextRunner and check NoSuchBeanDefinitionException in the cause chain. |
| Two beans for a single dependency, context must fail | ApplicationContextRunner and check NoUniqueBeanDefinitionException. |
| @Primary chooses default implementation | Set up two candidates, mark one primary, verify injected dependency. |
| @Qualifier chooses right implementation | Set up multiple candidates, add qualifiers on beans and injection point, verify behavior. |
| Collection receives all implementations | Inject List/Map and verify elements. |
| Dependency may be absent | Optional or ObjectProvider, verify empty/null/empty stream per API. |
| Candidates vary by profile/property | Run context with different profiles/properties. |
| Real full-application configuration | @SpringBootTest when verifying component scan, auto-configuration, and overall wiring. |

A good test should describe the **bean selection contract** rather than relying solely on full exception message strings. Messages can change across Spring versions; checking exception types and bean behavior is generally more stable.

## 18. Design mistakes that make bean selection hard to control

### 18.1. Using @Primary to mask ambiguity

If a system has multiple implementations and each service needs a different one, marking one bean globally primary can cause some consumers to receive the wrong implementation.

Use @Qualifier at the consumer when a dependency has a specific meaning. @Primary should only express a sensible default choice for the application.

### 18.2. Relying on bean declaration order to pick one candidate

Do not assume the first-declared bean will always be injected. If a single unique candidate is needed, use @Primary or @Qualifier. @Order is for collection ordering, not a substitute to solve single-dependency ambiguity.

### 18.3. Using bean names as business codes

Map<String, PaymentProvider> uses bean names as keys. If an external API sends the code `"wallet"`, do not assume the bean name is always `"wallet"`. You can build a registry keyed by PaymentProvider.name() and explicitly check for duplicate keys.

### 18.4. Instantiating objects with new to dodge injection errors

If the context reports a missing bean, writing:

~~~java
private final PaymentProvider provider =
        new CardPaymentProvider();
~~~

might let code slip past a simple case, yet it bypasses Spring's configuration, lifecycle, proxies, and implementation-swapping capabilities. Fix the registration source or bean selection rules if the dependency truly belongs to the container.

### 18.5. Swallowing exceptions when the context fails to resolve dependencies

Do not catch broad exceptions inside constructors/factory methods and return an incomplete object. An unsatisfied required dependency is a configuration error that should be caught early, not turned into a NullPointerException on a later request.

### 18.6. Over-relying on external configuration in tests

If a selection test only needs two fake beans, do not boot up an entire database or call real services. Use ApplicationContextRunner with a tiny configuration to isolate the problem. Save @SpringBootTest for when whole-application wiring needs verification.

## 19. Scenario reading exercises

### Scenario A: No candidate

Log:

~~~text
No qualifying bean of type 'PaymentProvider' available
~~~

The context only registers CheckoutService.

**Interpretation:** the required PaymentProvider dependency has no candidate. Check bean registration, component scan, profile, condition, and runtime classpath. There is no basis to add @Primary because no bean exists to prioritize.

### Scenario B: Two candidates

Log:

~~~text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
~~~

The context has cardProvider and walletProvider.

**Interpretation:** multiple beans match a single dependency equally. The business decision is to pick a default with @Primary, pick specifically with @Qualifier, or switch the consumer to a collection if all are genuinely needed.

### Scenario C: Qualifier mismatch

Context has:

~~~text
cardProvider   @Qualifier("card")
walletProvider @Qualifier("wallet")
~~~

Consumer requests:

~~~java
@Qualifier("bank") PaymentProvider provider
~~~

**Interpretation:** before candidate selection rules apply, the qualifier filtered out every bean. This is no candidate after filtering, not ambiguity.

### Scenario D: Name collision

Two configurations both register the bean name **paymentProvider**.

**Interpretation:** this is a bean definition name conflict. Inspect both registration sources and rename or remove one definition per design. @Primary does not resolve name collisions.

## 20. Common misconceptions

**"When there is no candidate, Spring automatically picks the closest bean."**  
No. Spring needs a candidate matching by type and metadata. If none is found, a required dependency will fail to resolve.

**"When there are multiple candidates, the first bean gets selected."**  
Do not rely on registration order. Declare @Primary or @Qualifier if a single unique bean is required.

**"@Primary deletes the remaining beans."**  
No. The beans remain in the context and can still be injected via collections or other qualifiers.

**"@Qualifier is only for bean names."**  
No. Qualifiers are metadata for filtering candidates; strings or custom qualifier annotations can be used.

**"@Order selects a bean for a single dependency."**  
No. @Order primarily sorts ordered collections/arrays.

**"Optional<T> handles both missing beans and multiple beans."**  
Optional handles the possible absence of a single dependency; it does not resolve ambiguity when multiple candidates match equally.

**"ObjectProvider.getIfAvailable always returns null if multiple beans exist."**  
No. If multiple candidates exist and cannot be uniquely chosen, this method can throw NoUniqueBeanDefinitionException. Use getIfUnique when you want null in the absence of a unique candidate.

**"NoSuchBeanDefinitionException and BeanDefinitionOverrideException are the same error."**  
No. One error means no matching candidate exists; the other means a registration collision on the same bean name when overriding is disallowed.

**"Collection injection is always equivalent to a single dependency."**  
No. List/Set/Map express the need to receive multiple candidates. When the list may be empty, ObjectProvider makes optionality explicit.

**"A failing test context alone proves ambiguity."**  
No. You must verify the specific cause is NoUniqueBeanDefinitionException; a context can fail due to a database, property, or another bean.

## Core takeaway

When Spring needs to inject **a single bean**, an empty candidate set typically leads to **NoSuchBeanDefinitionException** (possibly wrapped in a bean-creation/dependency exception), whereas a candidate set with multiple indistinguishable elements leads to **NoUniqueBeanDefinitionException**. **@Primary** chooses a default; **@Qualifier** filters candidates by specific requirements. **Optional** and **ObjectProvider** express dependencies that may be absent; collections fit when consumers need multiple implementations.

To test, build a lightweight context with **ApplicationContextRunner**, intentionally omit a bean or register two candidates, and assert the exception type and expected behavior. When full real-application configuration needs verification, use **@SpringBootTest**. Clearly distinguishing missing beans, ambiguity, duplicate bean names, and initialization failures lets you fix the true configuration source rather than masking bugs with arbitrary choices.
