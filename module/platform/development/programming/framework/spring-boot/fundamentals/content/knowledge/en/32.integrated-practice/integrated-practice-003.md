# Creating Multiple Implementations and Selecting with @Qualifier or @Primary

In a Spring Boot application, a single interface may have multiple valid implementations. For example, a payment system might support Stripe, bank transfers, and a sandbox gateway. All three implement the `PaymentGateway` contract, yet each use case may require a different implementation.

When Spring injects dependencies by type, the container must determine the right bean. If there is only one candidate, selection is straightforward. If multiple beans share the same type, Spring may throw `NoUniqueBeanDefinitionException`. Two common tools to resolve this situation are:

- `@Primary`: marks one bean as the preferred choice when an injection point expects a single candidate.
- `@Qualifier`: narrows the candidate bean set using a specific label at the injection point.

This lesson covers registering multiple implementations, selecting via `@Primary` and `@Qualifier`, injecting collections, selecting strategies from runtime data, creating custom qualifier annotations, testing the context, and handling common errors.

## 1. Why Does an Interface Have Multiple Implementations?

The interface describes a shared contract, while implementations decide how to fulfill that contract.

~~~java
package com.example.payment;

import java.math.BigDecimal;

public interface PaymentGateway {
    PaymentResult charge(String orderId, BigDecimal amount);
}
~~~

Result:

~~~java
package com.example.payment;

public record PaymentResult(
        String transactionId,
        String provider
) {
}
~~~

Implementations could be:

- `StripePaymentGateway`: calls the Stripe payment service.
- `BankTransferPaymentGateway`: creates a bank transfer request.
- `SandboxPaymentGateway`: simulates payments in development environments.

All three satisfy `PaymentGateway`, but they are not interchangeable in every situation.

### 1.1. Benefits of an Interface

The application service depends on the contract:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentResult checkout(String orderId, BigDecimal amount) {
        return gateway.charge(orderId, amount);
    }
}
~~~

The service does not need to know which provider receives the request. Swapping implementations, creating fakes, or mocking becomes straightforward.

### 1.2. Multiple Implementations Are Not Always an Error

Multiple beans of the same type are valid. A problem only arises when an injection point requires a single bean and the container lacks enough information to choose.

If a consumer needs all gateways, inject `List<PaymentGateway>` or `Map<String, PaymentGateway>`. If it only needs one gateway, a selection rule must be specified.

## 2. Registering Multiple Implementations

You can use component scanning:

~~~java
@Component
public class StripePaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(String orderId, BigDecimal amount) {
        // Call the Stripe API in a real implementation.
        return new PaymentResult("stripe-123", "stripe");
    }
}
~~~

~~~java
@Component
public class BankTransferPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(String orderId, BigDecimal amount) {
        // Create a bank transfer request in a real implementation.
        return new PaymentResult("bank-456", "bank-transfer");
    }
}
~~~

When component scan covers the package, Spring registers both beans.

### 2.1. Default Bean Names

Default bean names are typically derived from the class name in lower camel case:

| Class | Default bean name |
| --- | --- |
| `StripePaymentGateway` | `stripePaymentGateway` |
| `BankTransferPaymentGateway` | `bankTransferPaymentGateway` |

You can specify a name explicitly:

~~~java
@Component("stripeGateway")
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

Both `@Component` and `@Service` are stereotype annotations recognized by component scan. Use the annotation matching the class role and project conventions.

## 3. Why Does `NoUniqueBeanDefinitionException` Occur?

If Spring finds two beans implementing `PaymentGateway`, the following constructor has two candidates:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

The error message may look like:

~~~text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'com.example.payment.PaymentGateway'
available: expected single matching bean but found 2:
stripePaymentGateway, bankTransferPaymentGateway
~~~

This exception may be wrapped in `UnsatisfiedDependencyException` or `BeanCreationException` when Spring creates the service.

### 3.1. Why Doesn't Spring Automatically Pick the First Bean?

Component scan order or classpath class order is not a reliable business rule. If the container silently picked the first bean, behavior could change whenever a dependency is added or packages are restructured.

Spring requires an explicit choice to prevent accidental behavior.

### 3.2. Choosing the Right Tool

- One default implementation for ordinary consumers: use `@Primary`.
- Consumer needs a specific implementation: use `@Qualifier`.
- Consumer needs all implementations: inject a collection.
- Choice depends on runtime data: use a registry/factory.

## 4. Using `@Primary` to Set a Default Implementation

Annotate one component:

~~~java
@Component
@Primary
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

When multiple `PaymentGateway` beans exist and an injection point requires a single bean, Spring prefers the `@Primary` bean.

The service keeps a simple constructor:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

### 4.1. `@Primary` Expresses the Application Default

Use `@Primary` when one implementation is genuinely the default choice in the context. For example, most checkouts use Stripe, while bank transfers are used in specific flows.

### 4.2. Placing `@Primary` on a `@Bean` Method

If beans are created via Java configuration:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway stripeGateway(StripeClient client) {
        return new StripePaymentGateway(client);
    }

    @Bean
    PaymentGateway bankTransferGateway(BankTransferClient client) {
        return new BankTransferPaymentGateway(client);
    }
}
~~~

The method name typically serves as the default bean name unless another name is specified.

### 4.3. `@Primary` Does Not Remove Other Beans

Both Stripe and bank transfer remain registered. `@Primary` only influences selecting a single candidate for a matching injection point. You can still inject both as a collection or choose specifically with a qualifier.

### 4.4. Do Not Mark Multiple Primaries of the Same Type

If multiple beans of the same type are primary candidates, Spring still lacks a unique choice. When each consumer needs a distinct implementation, use qualifiers instead of creating multiple defaults.

## 5. Using `@Qualifier` to Select a Specific Implementation

Annotate the beans:

~~~java
@Component
@Qualifier("stripe")
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Component
@Qualifier("bankTransfer")
public class BankTransferPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Inject the right bean:

~~~java
@Service
public class InternationalCheckoutService {

    private final PaymentGateway gateway;

    public InternationalCheckoutService(
            @Qualifier("stripe") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

~~~java
@Service
public class DomesticCheckoutService {

    private final PaymentGateway gateway;

    public DomesticCheckoutService(
            @Qualifier("bankTransfer") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Each consumer explicitly states the dependency it requires.

### 5.1. Qualifiers Must Be Used at the Injection Point

Putting a qualifier only on the bean without specifying the corresponding qualifier at the consumer will not necessarily resolve ambiguity. The constructor parameter is where the selection is expressed:

~~~java
public DomesticCheckoutService(
        @Qualifier("bankTransfer") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

### 5.2. Qualifier Values Do Not Have to Match Bean Names

A qualifier is metadata used to filter candidates. For instance, the bean name may be `stripePaymentGateway` while its qualifier is `stripe`. This allows renaming classes without updating every consumer.

Bean names can sometimes act as fallback qualifiers, but if the label is part of the selection contract, declare the qualifier explicitly.

### 5.3. A Bean Can Have Multiple Qualifiers

A bean can be categorized along multiple dimensions. When an injection point declares multiple qualifiers, the candidate must satisfy the matching metadata. Only create labels that genuinely clarify selection.

## 6. Comparing `@Primary` and `@Qualifier`

| Criterion | `@Primary` | `@Qualifier` |
| --- | --- | --- |
| Purpose | Designate default candidate | Select candidate by label |
| Where placed | Bean definition/component | Bean and/or injection point |
| Effect | Prioritized when one candidate is needed | Narrows the candidate set |
| Best suited for | One general default | Consumers needing a specific implementation |
| When adding implementations | Default remains preferred if only one primary exists | Qualified consumers continue selecting by label |
| Excludes other beans? | No | No |
| Use with collections | Does not exclude others from collections | Can filter collections by qualifier |

### 6.1. Can Both Annotations Be Combined?

Yes. `@Qualifier` narrows candidates by metadata; `@Primary` can help pick a preferred bean from the remaining candidates if multiple choices still exist.

If the qualifier already identifies a unique bean, `@Primary` is usually unnecessary at that injection point.

### 6.2. Selection Rule of Thumb

- "Which gateway is the application's default?" → `@Primary`.
- "Which gateway does this specific consumer require?" → `@Qualifier`.

Do not add `@Primary` merely to silence context errors. Decide based on business configuration.

## 7. Using `@Qualifier` with `@Bean` Methods

You can attach qualifiers to factory methods:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentGatewayConfiguration {

    @Bean
    @Qualifier("stripe")
    PaymentGateway stripeGateway(StripeClient client) {
        return new StripePaymentGateway(client);
    }

    @Bean
    @Qualifier("bankTransfer")
    PaymentGateway bankTransferGateway(BankTransferClient client) {
        return new BankTransferPaymentGateway(client);
    }
}
~~~

Consumer:

~~~java
@Service
public class BankCheckoutService {

    private final PaymentGateway gateway;

    public BankCheckoutService(
            @Qualifier("bankTransfer") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

You can use different bean names and qualifiers:

~~~java
@Bean("stripeGateway")
@Qualifier("cardPayment")
PaymentGateway stripeGateway(StripeClient client) {
    return new StripePaymentGateway(client);
}
~~~

The bean name is `stripeGateway`, and the qualifier is `cardPayment`. Consumers can request the `cardPayment` qualifier.

### 7.1. Avoiding Duplicate Bean Names

Two `@Bean` methods declaring the same bean name can cause conflicts or depend on bean overriding settings. Give distinct names to implementations and use qualifiers for selection.

Bean overriding is not an appropriate substitute for handling multiple candidates of the same type.

## 8. Multiple Beans Where Each Consumer Needs a Different Capability

An application might have `InternationalCheckoutService` needing Stripe, `DomesticCheckoutService` needing bank transfer, `RefundService` needing a gateway that supports refunds, and `ReconciliationService` needing all gateways.

If not every gateway supports refunds, consider a separate contract:

~~~java
public interface RefundGateway {
    RefundResult refund(String transactionId, BigDecimal amount);
}
~~~

Do not overuse qualifiers to mask an overly broad interface. If an implementation has to throw `UnsupportedOperationException` for several methods, the contract may need to be split by capability.

Qualifiers solve bean selection; they do not make two implementations share equivalent behavior.

## 9. Injecting All Implementations with `List`

If a consumer needs all gateways, inject a collection:

~~~java
@Service
public class PaymentGatewayRegistry {

    private final List<PaymentGateway> gateways;

    public PaymentGatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }

    public List<PaymentGateway> all() {
        return gateways;
    }
}
~~~

Spring resolves all beans matching type `PaymentGateway` and injects them as a list.

### 9.1. `@Primary` Does Not Exclude Beans from `List`

If Stripe is marked `@Primary`, the collection can still contain both Stripe and bank transfer. `@Primary` applies when picking a single candidate, not as a filter to remove other beans from collections.

### 9.2. Ordering Collections with `@Order`

If order matters, you can use `@Order` or `Ordered`:

~~~java
@Component
@Order(10)
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Component
@Order(20)
public class BankTransferPaymentGateway implements PaymentGateway {
    // ...
}
~~~

`@Order` affects ordering in certain collection injections and ordered streams; it does not replace `@Primary` for selecting a single bean in scalar injection.

## 10. Injecting a `Map` to Build a Name-Based Registry

Spring can inject a map keyed by bean name:

~~~java
@Service
public class PaymentGatewayRegistry {

    private final Map<String, PaymentGateway> gateways;

    public PaymentGatewayRegistry(Map<String, PaymentGateway> gateways) {
        this.gateways = Map.copyOf(gateways);
    }

    public PaymentGateway byBeanName(String name) {
        PaymentGateway gateway = gateways.get(name);

        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unknown payment gateway: " + name
            );
        }

        return gateway;
    }
}
~~~

The map may contain keys `stripePaymentGateway` and `bankTransferPaymentGateway` if those are the actual bean names.

### 10.1. Do Not Accept Arbitrary Bean Names from Requests

Bean names are internal wiring details, not your system's public API. Do not let HTTP clients send Spring bean names and pass them straight into `Map.get(name)`.

Map stable enum/domain keys such as `CARD` or `BANK_TRANSFER` to the corresponding implementation, while validating authorization to use that provider.

## 11. Selecting an Implementation from Runtime Input with a Strategy Registry

Qualifiers are resolved when Spring creates beans. If selection depends on runtime data such as payment method, use a registry/factory.

Enum:

~~~java
public enum PaymentMethod {
    CARD,
    BANK_TRANSFER
}
~~~

Strategy:

~~~java
public interface PaymentProcessor {

    PaymentMethod method();

    PaymentResult process(
            String orderId,
            BigDecimal amount
    );
}
~~~

Registry:

~~~java
@Component
public class PaymentProcessorRegistry {

    private final Map<PaymentMethod, PaymentProcessor> processors;

    public PaymentProcessorRegistry(List<PaymentProcessor> processorList) {
        EnumMap<PaymentMethod, PaymentProcessor> map =
                new EnumMap<>(PaymentMethod.class);

        for (PaymentProcessor processor : processorList) {
            PaymentProcessor previous =
                    map.put(processor.method(), processor);

            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate processor for " + processor.method()
                );
            }
        }

        this.processors = Map.copyOf(map);
    }

    public PaymentProcessor get(PaymentMethod method) {
        PaymentProcessor processor = processors.get(method);

        if (processor == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment method: " + method
            );
        }

        return processor;
    }
}
~~~

Use case:

~~~java
@Service
public class PaymentApplicationService {

    private final PaymentProcessorRegistry registry;

    public PaymentApplicationService(PaymentProcessorRegistry registry) {
        this.registry = registry;
    }

    public PaymentResult pay(
            PaymentMethod method,
            String orderId,
            BigDecimal amount) {
        return registry.get(method).process(orderId, amount);
    }
}
~~~

### 11.1. Why Is a Registry Better Suited Than Qualifiers?

A registry picks a strategy when the method is called based on runtime data. If two strategies both declare `CARD`, the registry can detect the duplicate explicitly instead of depending on list order.

### 11.2. A Registry Is Not a Global Service Locator

The registry is still an explicit dependency injected via constructor. It manages a set of strategies for a specific contract, without granting arbitrary access to every bean in the ApplicationContext.

## 12. Custom Qualifier Annotations

When qualifier strings are repeated across many places, you can create a custom annotation meta-annotated with `@Qualifier`.

~~~java
package com.example.payment;

import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import org.springframework.beans.factory.annotation.Qualifier;

import static java.lang.annotation.ElementType.FIELD;
import static java.lang.annotation.ElementType.PARAMETER;
import static java.lang.annotation.ElementType.METHOD;
import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Target({FIELD, PARAMETER, METHOD, TYPE})
@Retention(RUNTIME)
@Documented
@Qualifier
public @interface CardPayment {
}
~~~

Annotate the bean:

~~~java
@Component
@CardPayment
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

Inject:

~~~java
@Service
public class CardCheckoutService {

    private final PaymentGateway gateway;

    public CardCheckoutService(@CardPayment PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

### 12.1. Qualifier Annotations with Attributes

~~~java
@Target({FIELD, PARAMETER, METHOD, TYPE})
@Retention(RUNTIME)
@Qualifier
public @interface RegionalGateway {
    String value();
}
~~~

Annotate the bean and inject by region:

~~~java
@Component
@RegionalGateway("asia")
public class AsiaPaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
public AsiaCheckoutService(
        @RegionalGateway("asia") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Custom annotations are helpful when labels form a widely used domain vocabulary. For a single isolated choice, `@Qualifier("stripe")` is usually easier to read.

## 13. Generic Types Can Also Participate in Bean Selection

Spring can use generic type information during autowiring:

~~~java
public interface MessageEncoder<T> {
    byte[] encode(T message);
}
~~~

~~~java
@Component
public class JsonOrderEncoder implements MessageEncoder<OrderMessage> {
    // ...
}
~~~

~~~java
@Component
public class JsonInvoiceEncoder implements MessageEncoder<InvoiceMessage> {
    // ...
}
~~~

Consumers can inject `MessageEncoder<OrderMessage>` to specify the exact type.

If multiple beans implement `MessageEncoder<OrderMessage>`, Spring may still need a qualifier or primary. Use generics when the difference lies in the type contract; use qualifiers/strategies when the difference lies in provider, region, or behavior.

## 14. `@Primary` Is Not an Ordering Priority Inside `List`

Marking a bean with `@Primary` does not restrict `List<PaymentGateway>` to just that bean. Collection injection is intended to gather multiple candidates.

If you need one default, inject a single `PaymentGateway`. If you need all of them, inject a collection. If you need a subset, you can apply a qualifier to the collection:

~~~java
public PaymentAuditService(
        @Qualifier("auditable") List<PaymentGateway> gateways) {
    this.gateways = gateways;
}
~~~

Beans annotated with the `auditable` qualifier can be selected for this collection.

`@Order` orders collections; `@Primary` prioritizes one candidate for single-bean injection.

## 15. Optional Dependencies and `ObjectProvider`

Sometimes a bean is optional, such as a metrics adapter installed only in certain applications.

~~~java
@Component
public class PaymentMetricsBridge {

    private final ObjectProvider<PaymentMetrics> metricsProvider;

    public PaymentMetricsBridge(
            ObjectProvider<PaymentMetrics> metricsProvider) {
        this.metricsProvider = metricsProvider;
    }

    public void recordSuccess(String provider) {
        PaymentMetrics metrics = metricsProvider.getIfAvailable();

        if (metrics != null) {
            metrics.recordSuccess(provider);
        }
    }
}
~~~

`ObjectProvider` lets you resolve dependencies lazily and handle the absence of a bean.

If there are multiple optional beans, you can use `orderedStream()` or `stream()`. If a dependency is required and must have exactly one bean, direct constructor injection yields earlier, clearer startup errors.

## 16. Selecting Beans by Profile or Property Condition

You can register implementations selectively by profile:

~~~java
@Component
@Profile("dev")
public class SandboxPaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Component
@Profile("prod")
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

Profiles fit when the implementation depends on the deployment environment.

Spring Boot can also register beans based on properties:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentGatewayConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "payment.gateway",
            name = "provider",
            havingValue = "stripe"
    )
    PaymentGateway stripeGateway(StripeClient client) {
        return new StripePaymentGateway(client);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "payment.gateway",
            name = "provider",
            havingValue = "bank"
    )
    PaymentGateway bankGateway(BankTransferClient client) {
        return new BankTransferPaymentGateway(client);
    }
}
~~~

Configuration:

~~~yaml
payment:
  gateway:
    provider: stripe
~~~

### 16.1. Conditions and Qualifiers Solve Different Problems

- Conditions decide which beans get registered into the context.
- Qualifiers decide which bean gets injected at an injection point among registered candidates.
- Primary chooses a default among matching candidates.

If an application only wants to register one provider per configuration, conditions may be cleaner than creating all implementations and picking one. If multiple implementations must coexist, do not use a global property condition to exclude them.

## 17. `@Qualifier` Does Not Dynamically Pick Beans per Request

A constructor with `@Qualifier("stripe")` is resolved when Spring creates the bean. The qualifier does not change per HTTP request.

If a request carries a `paymentMethod` field, Spring does not swap the constructor argument with a corresponding qualifier on every method call.

Use an explicitly injected factory or registry. The application service retrieves a strategy by domain key, then checks whether that provider is permitted for the tenant, country, currency, or transaction type.

Do not call `ApplicationContext.getBean()` inside a controller using a bean name sent in the request. That hides dependencies and turns internal bean names into an external API.

## 18. Common Errors When Using `@Primary` and `@Qualifier`

### 18.1. `NoUniqueBeanDefinitionException` Still Appears

**Cause:** multiple candidates exist without a unique primary, or the qualifier does not match uniquely.

**Resolution:** check bean names, qualifier metadata, profiles, and component scanning. Read the exception message for candidate names.

### 18.2. `NoSuchBeanDefinitionException` After Adding `@Qualifier`

**Cause:** the qualifier does not match any bean, or the bean was not registered due to component scan, profile, or conditions.

**Resolution:** confirm the bean is present in the context first, then check the qualifier label.

### 18.3. Marked `@Primary` but Still Failing

**Cause:** multiple primary candidates exist, the bean was not scanned, or a qualifier filtered out the primary bean.

**Resolution:** inspect the candidate set at that exact injection point. `@Primary` cannot materialize a bean that does not exist.

### 18.4. `@Qualifier` Placed in the Wrong Location

**Cause:** placed only on a field not injected by Spring, or attached to an unregistered bean.

**Resolution:** place the qualifier on both the bean definition and the injection point. For constructor injection, place the annotation on the corresponding parameter.

### 18.5. Relying on Unstable Bean Names

**Cause:** consumer relies on the default name derived from the class name; refactoring the class name breaks selection.

**Resolution:** use explicit qualifier labels or explicit bean names when selection is part of the contract.

### 18.6. Two `@Primary` Beans

**Cause:** multiple beans of the same type are marked primary.

**Resolution:** mark only one default in the candidate set or require consumers to use qualifiers.

### 18.7. Expecting `@Primary` to Filter `List`

**Cause:** treating `@Primary` as a collection filter.

**Resolution:** collection injection gathers multiple candidates; use qualifiers, filters, or a registry for subsets.

### 18.8. Using `@Order` Instead of `@Primary`

**Cause:** confusing ordering with single-candidate selection.

**Resolution:** `@Order` orders collections; `@Primary` prioritizes a scalar dependency.

### 18.9. Using `@Qualifier` for Runtime Selection

**Cause:** qualifiers are resolved during bean creation, not at request execution time.

**Resolution:** use a strategy registry or factory accepting a domain key.

### 18.10. Bean Excluded by Profile or Condition

**Cause:** the qualifier is correct, but the bean does not exist in the context because its profile is inactive or its property condition did not match.

**Resolution:** check active profiles, property sources, and condition evaluation.

## 19. Testing Bean Selection with a Spring Context

Unit tests instantiating objects with `new` can verify business logic, but they do not verify Spring's bean selection via `@Primary` or `@Qualifier`.

To verify container behavior, use a Spring Test context or `ApplicationContextRunner`.

### 19.1. Minimal Test Configuration Example

~~~java
@Configuration(proxyBeanMethods = false)
static class TestConfiguration {

    @Bean
    @Primary
    PaymentGateway stripeGateway() {
        return (orderId, amount) ->
                new PaymentResult("stripe-test", "stripe");
    }

    @Bean
    @Qualifier("bank")
    PaymentGateway bankGateway() {
        return (orderId, amount) ->
                new PaymentResult("bank-test", "bank");
    }

    @Bean
    DefaultCheckout defaultCheckout(PaymentGateway gateway) {
        return new DefaultCheckout(gateway);
    }

    @Bean
    BankCheckout bankCheckout(
            @Qualifier("bank") PaymentGateway gateway) {
        return new BankCheckout(gateway);
    }
}
~~~

Test:

~~~java
@SpringJUnitConfig(TestConfiguration.class)
class PaymentGatewaySelectionTest {

    @Autowired
    DefaultCheckout defaultCheckout;

    @Autowired
    BankCheckout bankCheckout;

    @Test
    void usesPrimaryForUnqualifiedInjection() {
        assertEquals("stripe", defaultCheckout.charge().provider());
    }

    @Test
    void usesQualifierForSpecificInjection() {
        assertEquals("bank", bankCheckout.charge().provider());
    }
}
~~~

`DefaultCheckout` and `BankCheckout` are simple test classes accepting `PaymentGateway` via constructor. The context test proves bean selection is performed by Spring.

### 19.2. Checking Bean Names and Count

You can verify both implementations still exist:

~~~java
assertThat(context.getBeansOfType(PaymentGateway.class))
        .hasSize(2);
~~~

Then verify that retrieving the bean by type returns the primary candidate when a single matching primary exists.

### 19.3. Testing Intentional Ambiguity Errors

Another test can create a context with only two non-primary beans and a consumer injecting a scalar `PaymentGateway`. Verify that context startup fails with an ambiguity error.

This negative test is helpful for guarding configuration behavior, though you should assert the exception in a way that stays resilient across Spring versions rather than depending on the entire internal message.

## 20. Testing Auto-Configuration with `ApplicationContextRunner`

If a library provides auto-configuration, `ApplicationContextRunner` can verify bean selection in a lightweight context.

~~~java
class PaymentAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PaymentAutoConfiguration.class);

    @Test
    void backsOffWhenUserProvidesPrimaryGateway() {
        runner.withUserConfiguration(UserPaymentConfiguration.class)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(PaymentGateway.class);
                });
    }
}
~~~

`UserPaymentConfiguration` is a test configuration registering a custom implementation. Tests should verify:

- Is the default bean created when no user bean exists?
- Does a user bean cause the default auto-configuration to back off?
- If multiple user beans exist, do injection points have the right qualifiers/primary?
- Do property/profile conditions register the right set of beans?

### 20.1. `@ConditionalOnMissingBean` and Multiple Implementations

Auto-configuration often uses `@ConditionalOnMissingBean(PaymentGateway.class)` to create a default when no bean of that type exists.

If the application wants multiple gateways, the auto-configuration needs an appropriate contract: it might create a default when no user-defined gateway exists while user configuration registers multiple implementations, or each provider might have its own condition and qualifier.

Do not accidentally create a third default bean that makes scalar injection ambiguous.

## 21. Tests Can Mask Production Configuration

If test configuration always marks a mock as `@Primary`, all tests can pass even if the production context has two real implementations and no primary.

### 21.1. Unit Tests Do Not Verify Bean Selection

~~~java
CheckoutService service = new CheckoutService(mockGateway);
~~~

This test verifies the service with a passed-in dependency; it does not verify `@Primary` or `@Qualifier`.

### 21.2. Context Tests Verify Container Rules

When behavior depends on bean metadata, use context tests with the corresponding bean definitions.

### 21.3. Integration Tests Verify Real Composition

If the application has multiple configuration modules, profiles, and auto-configurations, write at least one test scoped to represent production composition so conflicts are caught.

## 22. Naming and Qualifier Conventions

As the number of implementations grows, naming conventions help prevent confusion:

| Provider | Bean name | Qualifier |
| --- | --- | --- |
| Stripe | `stripePaymentGateway` | `stripe` |
| Bank transfer | `bankTransferPaymentGateway` | `bankTransfer` |
| Sandbox | `sandboxPaymentGateway` | `sandbox` |

Guidelines:

- Name by role/provider, not by registration order.
- Do not reuse the same qualifier on two beans if consumers expect a unique bean.
- Keep qualifiers stable across class renames.
- Create custom qualifier annotations when labels become shared domain vocabulary.
- Document which implementation serves as the default.
- If multiple contexts or profiles exist, document which beans exist in each context.

## 23. When to Use `@Primary`, `@Qualifier`, `List`, `Map`, or a Registry?

| Practical need | Mechanism to consider |
| --- | --- |
| One default for ordinary consumers | `@Primary` |
| A consumer needs a specific bean | `@Qualifier` |
| Consumer needs all implementations | `List<T>` or `Collection<T>` |
| Consumer looks up by internal bean key | `Map<String, T>` |
| Select strategy by runtime enum/domain key | Registry/factory |
| Register implementations only per environment | `@Profile` |
| Register conditionally by property/classpath | Conditional beans |
| Different capabilities | Split interfaces or strategies with clear contracts |

No single annotation solves every problem. Choose the mechanism that reflects the actual decision time and source: startup configuration or runtime business input.

## 24. Key Design Principles

1. **Constructor injection is a strong default.** Dependencies are visible and easy to test.
2. **Do not rely on component scan order.** Order is not a business rule.
3. **Use `@Primary` for genuine defaults.** Do not use it merely to suppress startup errors.
4. **Use `@Qualifier` for intentional selection.** Consumers explicitly state the implementation they require.
5. **Split contracts by capability.** Do not force overly broad interfaces onto every implementation.
6. **Use a registry for runtime selection.** Qualifiers are resolved when Spring creates beans.
7. **Define stable naming conventions.** Bean names and qualifiers are internal configuration to manage carefully.
8. **Test container behavior with a context.** Direct unit tests do not verify bean resolution.
9. **Manage profiles and conditions clearly.** A qualifier cannot select a bean that does not exist.
10. **Do not expose bean names as a public API.** Use enums/domain keys for external requests or configuration.

## 25. Practice Exercises

### Exercise A: Creating Two Implementations

Create `PaymentGateway`, `StripePaymentGateway`, and `BankTransferPaymentGateway`. Register both via component scanning. Inject `PaymentGateway` into a service and observe the ambiguity error.

### Exercise B: Using `@Primary`

Mark Stripe as `@Primary`. Boot the context and verify an unqualified consumer receives Stripe.

### Exercise C: Using `@Qualifier`

Annotate the bank gateway with `@Qualifier("bankTransfer")`. Create a service requesting this qualifier and verify it receives the right implementation.

### Exercise D: Defining Beans with `@Bean`

Create two beans via `@Configuration`. Use `@Primary` on one factory method and `@Qualifier` on the other. Inspect the default bean names derived from the methods.

### Exercise E: Combining Primary and Qualifier

Create one primary default and one consumer with a specific qualifier. Verify the two consumers receive different implementations.

### Exercise F: Injecting `List`

Inject `List<PaymentGateway>`. Verify the collection contains both beans even though one is primary.

### Exercise G: Injecting `Map`

Inject `Map<String, PaymentGateway>`. Inspect the bean names and build an internal registry.

### Exercise H: Strategy Registry

Create a `PaymentMethod` enum, a `PaymentProcessor` interface, and a method-keyed registry. Test missing-strategy and duplicate-strategy cases.

### Exercise I: Custom Qualifier Annotation

Create `@CardPayment` or `@PaymentRegion`. Apply the annotation on beans and constructor parameters.

### Exercise J: Conditional Provider

Register Stripe only when `payment.gateway.provider=stripe` and bank when the value is `bank`. Test both property values using a context runner.

### Exercise K: Context Test vs. Unit Test

Write a unit test passing a fake gateway directly and a context test verifying `@Primary`/`@Qualifier`. Explain what each test protects.

### Exercise L: Selecting with Authorization Checks

Build a registry taking `PaymentMethod`, then add checks for allowed providers per tenant/currency. Do not use bean names directly from the request.

## 26. Self-Check Questions

**1. Why does Spring throw `NoUniqueBeanDefinitionException`?**

Because an injection point expects a single bean, yet multiple matching candidates exist without a unique selection rule.

**2. Does `@Primary` make other beans disappear?**

No. It only marks the preferred candidate for certain single-bean injections.

**3. What is `@Qualifier` used for?**

Narrowing candidates by qualifier metadata so a consumer receives the intended implementation.

**4. Can `@Primary` be placed on a `@Bean` method?**

Yes. The annotation can be placed on bean definitions produced by factory methods.

**5. Must a qualifier match the bean name?**

No. A qualifier is separate metadata; bean names may be used in some fallback cases, but that is not the only mechanism.

**6. What happens if two beans are marked `@Primary`?**

Spring may still fail to determine a single primary candidate.

**7. Does `@Primary` filter `List<PaymentGateway>`?**

No. Collection injection still includes all matching candidates.

**8. How does `@Order` differ from `@Primary`?**

`@Order` relates to ordering within collections/ordered resolution; `@Primary` prioritizes one candidate for single-bean injection.

**9. Does `@Qualifier` choose implementations per request?**

No. Qualifiers are resolved when Spring creates beans. Runtime selection requires a registry/factory or appropriate strategy.

**10. When should you use a custom qualifier annotation?**

When a qualifier label is meaningful domain vocabulary reused across many places and you want to avoid repeating raw strings.

**11. Should you use `ApplicationContext.getBean()` in a controller to pick a gateway?**

No. Use an explicitly injected registry/factory and a validated domain key.

**12. When should you inject a `List` instead of a single bean?**

When the consumer genuinely needs to process all implementations, such as a registry, aggregator, or plugin pipeline.

**13. What if the qualifier is right, but the bean does not exist?**

Spring still cannot resolve the dependency. Check component scan, profiles, conditions, and runtime classpath.

**14. Does a unit test instantiating a service directly verify `@Primary`?**

No. It only verifies the service with directly passed dependencies; a context test is needed to verify bean resolution.

**15. Which mechanism should you pick when the provider is chosen per request?**

Use a strategy registry/factory keyed by an enum or domain key, with validation and authorization checks.

## 27. Conclusion

When an interface has multiple implementations, Spring needs an explicit selection rule at each injection point. `@Primary` fits when the application has one default implementation; `@Qualifier` fits when a consumer requires a specific implementation. Neither removes the remaining beans, and both can be combined when candidates must be narrowed before picking a default.

If a consumer needs all implementations, inject a collection. If selection depends on runtime data such as a payment method, use a registry or factory with a domain key instead of trying to make qualifiers dynamic. If an implementation only belongs in one environment, profiles or conditional bean registration can govern which beans are created.

Keep constructor dependencies explicit, never rely on scan order, maintain stable names/qualifiers, and test bean resolution with a Spring context. When selection reflects the true meaning of each dependency, the application can add new providers without making existing consumers ambiguous.
