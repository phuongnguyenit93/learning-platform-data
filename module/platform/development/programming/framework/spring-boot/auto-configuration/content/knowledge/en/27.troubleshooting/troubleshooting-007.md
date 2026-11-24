# NoUniqueBeanDefinitionException Due to Multiple Beans of the Same Type

## 1. Understanding the Error

`NoUniqueBeanDefinitionException` occurs when Spring needs to select **a single bean** of a requested type, yet finds multiple matching beans and cannot determine which candidate should be used.

For example, given an interface:

~~~java
public interface PaymentGateway {
    String provider();
}
~~~

The application registers two implementations:

~~~java
@Bean
PaymentGateway stripeGateway() {
    return new StripeGateway();
}

@Bean
PaymentGateway walletGateway() {
    return new WalletGateway();
}
~~~

A service requests a single `PaymentGateway`:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Spring sees both `stripeGateway` and `walletGateway` as candidates for the `PaymentGateway` parameter. Without a qualifier or suitable candidate-selection rule, Spring cannot decide and creating `CheckoutService` fails.

The error message typically looks like:

~~~text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'PaymentGateway' available:
expected single matching bean but found 2:
stripeGateway,walletGateway
~~~

The actual message may be wrapped inside `UnsatisfiedDependencyException` or `BeanCreationException`. Read the deepest `Caused by` clause to identify the root cause.

`NoUniqueBeanDefinitionException` is a subclass of `NoSuchBeanDefinitionException`, yet their meanings differ:

| Exception | Meaning |
| --- | --- |
| `NoSuchBeanDefinitionException` | No bean matching the requested type/name was found |
| `NoUniqueBeanDefinitionException` | Multiple matching beans exist where the injection point expects a single bean |
| `BeanDefinitionOverrideException` | Multiple bean definitions share the same name and overriding is disallowed |
| `BeanCreationException` | A bean could not be created; the root cause may be another error, including ambiguity |

Do not resolve `NoUniqueBeanDefinitionException` by enabling bean definition overriding. Two beans with different names and the same type are a candidate-selection issue; bean definition overriding is a duplicate-name issue.

## 2. Where Ambiguity Can Arise

This error does not happen only in constructor injection. Any operation requiring a single bean by type can hit it.

### 2.1. Constructor Injection

~~~java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

The constructor requires one `PaymentGateway`. If two equal candidates exist, Spring cannot complete creating the service.

### 2.2. `@Bean` Method Parameters

~~~java
@Bean
CheckoutService checkoutService(PaymentGateway gateway) {
    return new CheckoutService(gateway);
}
~~~

Parameters of `@Bean` methods are also autowired by Spring. Hence the error can lie inside a configuration class rather than a component class.

### 2.3. `@Autowired` Field or Setter

~~~java
@Autowired
private PaymentGateway gateway;
~~~

Field injection and setter injection use the same type-based candidate selection process. Constructor injection is usually easier to control and test, though the injection style itself does not eliminate ambiguity.

### 2.4. `BeanFactory.getBean` by Type

~~~java
PaymentGateway gateway =
        applicationContext.getBean(PaymentGateway.class);
~~~

This call requests a single bean by type. If multiple beans of that type exist with no unique candidate, `getBean(Class)` also throws `NoUniqueBeanDefinitionException`.

If the goal is retrieving a bean by name, use `getBean("stripeGateway", PaymentGateway.class)` or `@Resource(name = "stripeGateway")` depending on the call site.

### 2.5. Not Every Same-Type Dependency Causes an Error

When an application wants all implementations, declare a collection or provider:

~~~java
List<PaymentGateway> gateways;
Map<String, PaymentGateway> gatewaysByName;
PaymentGateway[] gateways;
ObjectProvider<PaymentGateway> gateways;
~~~

Spring injects all matching candidates into the collection. `@Primary` does not exclude beans from collection injection.

## 3. Approach 1: Use `@Primary` When There Is One Default Implementation

`@Primary` marks a bean to be preferred when multiple candidates of the same type are injected into a single-valued dependency.

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway stripeGateway() {
        return new StripeGateway();
    }

    @Bean
    PaymentGateway walletGateway() {
        return new WalletGateway();
    }
}
~~~

The service needs no change:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

When injecting a single `PaymentGateway`, Spring picks `stripeGateway` because it is the sole candidate marked `@Primary`.

Use `@Primary` when:
- The application has a sensible default implementation.
- Normal injection points should use that same implementation.
- The other implementations still need to exist for explicitly selected flows.

Do not mark multiple beans of the same type as `@Primary`. If multiple primary candidates exist, Spring still lacks a single unique choice.

**Note:** `@Primary` affects only single-valued injection. When injecting `List<PaymentGateway>`, `Map<String, PaymentGateway>`, arrays, or `ObjectProvider` streams, Spring still returns all matching candidates.

## 4. Approach 2: Use `@Qualifier` When Each Injection Point Needs a Specific Implementation

If an application has multiple implementations and each service needs a different one, `@Qualifier` expresses the choice directly at each injection point.

Mark the beans:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @Qualifier("card")
    PaymentGateway stripeGateway() {
        return new StripeGateway();
    }

    @Bean
    @Qualifier("digital-wallet")
    PaymentGateway walletGateway() {
        return new WalletGateway();
    }
}
~~~

Select the bean in the constructor:

~~~java
@Service
public class CardCheckoutService {

    private final PaymentGateway gateway;

    public CardCheckoutService(
            @Qualifier("card") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Another service can pick wallet:

~~~java
@Service
public class WalletCheckoutService {

    private final PaymentGateway gateway;

    public WalletCheckoutService(
            @Qualifier("digital-wallet") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

`@Qualifier` filters the type-matched candidate set. Qualifier values should express meaningful roles or traits, such as `card`, `digital-wallet`, `read-only`, or `primary-region`.

A qualifier need not be unique in every situation. One qualifier can filter multiple beans when the injection point accepts a collection:

~~~java
@Autowired
@Qualifier("regional")
private List<PaymentGateway> regionalGateways;
~~~

### 4.1. `@Qualifier` Is Not the Same as `@Primary`

| Annotation | Question answered |
| --- | --- |
| `@Primary` | If a single default bean is needed among multiple candidates, which bean takes precedence? |
| `@Qualifier` | Which trait/label does this injection point require on its candidate? |

For example, `@Primary` can choose the default gateway for `CheckoutService`, while `@Qualifier("digital-wallet")` selects the wallet for a specialized service.

### 4.2. Using Custom Qualifiers When String Names Are Insufficient

In large codebases, you can define dedicated qualifier annotations:

~~~java
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface CardPayment {
}
~~~

Annotate the bean:

~~~java
@Bean
@CardPayment
PaymentGateway stripeGateway() {
    return new StripeGateway();
}
~~~

Inject:

~~~java
public CardCheckoutService(@CardPayment PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Custom qualifiers reduce typos and improve compiler/IDE search and refactoring support.

## 5. Approach 3: Use `@Fallback` in Spring Framework 6.2+

Spring Framework 6.2 introduces `@Fallback`, the counterpart to `@Primary`. This annotation marks a bean as a fallback candidate.

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway stripeGateway() {
        return new StripeGateway();
    }

    @Bean
    @Fallback
    PaymentGateway sandboxGateway() {
        return new SandboxGateway();
    }
}
~~~

When an injection point requires a single `PaymentGateway`, `stripeGateway` is chosen because it is the sole remaining regular candidate once fallback candidates are set aside.

Use `@Fallback` when:
- You want to provide a backup implementation.
- A regular bean should be preferred whenever one exists.
- The fallback bean should be selected only when no other regular candidate exists.

If all candidates are fallbacks or multiple equal regular candidates remain, Spring still cannot determine a single bean.

`@Fallback` affects only single-valued injection. Collection injection still receives all matching beans, including fallback beans.

Spring Boot 3.5 uses Spring Framework 6.2, so this annotation is available. If your project uses Spring Framework 6.1 or older, `@Fallback` does not exist yet; use `@Primary`, `@Qualifier`, or another suitable bean design.

## 6. Approach 4: Use Bean Name or `@Resource` When Identifying by Name

If the business requirement is genuinely "obtain the bean named `stripeGateway`", you can use `@Resource`:

~~~java
import jakarta.annotation.Resource;

@Service
public class CardCheckoutService {

    @Resource(name = "stripeGateway")
    private PaymentGateway gateway;
}
~~~

`@Resource` has bean-name selection semantics. It is an appropriate choice when the name is the primary identifier.

With constructor injection, prefer `@Qualifier` on the parameter:

~~~java
public CardCheckoutService(
        @Qualifier("card") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Spring Framework 6.1+ also supports using parameter names as hints when no other qualifier or primary exists. This mechanism requires the Java compiler to preserve parameter names with the `-parameters` flag. Spring Framework 6.2 has a fast shortcut when the parameter name matches the bean name.

Even so, for critical dependencies, explicit qualifiers are usually clearer and less dependent on compiler flags.

Do not confuse `@Qualifier("stripeGateway")` with pure bean-ID referencing: `@Autowired` still starts with type matching, then uses the qualifier to narrow candidates. When identifying a bean by name is the primary intent, `@Resource(name = "...")` expresses that intent more directly.

## 7. Approach 5: Receive Multiple Implementations via List, Map, or Array

If the application needs to support multiple gateways, do not force Spring to pick an arbitrary single implementation. Accept all candidates and let business logic choose based on input data.

### 7.1. Injecting a List

~~~java
@Component
public class PaymentGatewayRegistry {

    private final List<PaymentGateway> gateways;

    public PaymentGatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }

    public List<PaymentGateway> all() {
        return this.gateways;
    }
}
~~~

Spring injects every matching `PaymentGateway`. You can use `@Order` on beans to control ordering inside the collection:

~~~java
@Bean
@Order(1)
PaymentGateway stripeGateway() {
    return new StripeGateway();
}

@Bean
@Order(2)
PaymentGateway walletGateway() {
    return new WalletGateway();
}
~~~

`@Order` can affect collection injection order. It is not a mechanism for picking a single bean for a constructor parameter, nor does it dictate singleton initialization order.

### 7.2. Injecting a Map Keyed by Bean Name

~~~java
@Component
public class PaymentGatewayRegistry {

    private final Map<String, PaymentGateway> gateways;

    public PaymentGatewayRegistry(Map<String, PaymentGateway> gateways) {
        this.gateways = Map.copyOf(gateways);
    }

    public PaymentGateway get(String beanName) {
        PaymentGateway gateway = this.gateways.get(beanName);
        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unknown payment gateway: " + beanName);
        }
        return gateway;
    }
}
~~~

Spring creates a map whose keys are bean names and values are the corresponding instances.

This is useful when a factory or router needs to pick an implementation by configuration. For business-level selection such as `CARD`, `WALLET`, or `BANK_TRANSFER`, create a registry with a clear API rather than scattering bean-name strings across the application.

### 7.3. Injecting an Array

~~~java
public PaymentGatewayRegistry(PaymentGateway[] gateways) {
    this.gateways = List.of(gateways);
}
~~~

Arrays fit when an existing API requires an array type. `List` is usually more convenient in modern Java code.

## 8. Approach 6: Use `ObjectProvider` for On-Demand Bean Lookup

`ObjectProvider<T>` lets you request beans when needed and supports several ways to handle candidates.

~~~java
@Component
public class PaymentGatewaySelector {

    private final ObjectProvider<PaymentGateway> gateways;

    public PaymentGatewaySelector(
            ObjectProvider<PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public PaymentGateway getUniqueGateway() {
        return this.gateways.getIfUnique();
    }

    public List<PaymentGateway> allGateways() {
        return this.gateways.orderedStream().toList();
    }
}
~~~

Common methods:

| Method | Behavior |
| --- | --- |
| `getObject()` | Requires one bean; fails if none found or multiple unresolvable candidates exist |
| `getIfAvailable()` | Returns the bean if present; still fails if multiple candidates cannot be resolved |
| `getIfUnique()` | Returns the bean if a single unique candidate exists; returns `null` if absent or non-unique |
| `stream()` | Streams all matching candidates |
| `orderedStream()` | Streams matching candidates in Spring order |

If having multiple implementations is normal and selection depends on the request, tenant, or transaction type, use `Map`, `List`, or a dedicated registry. Do not call `getObject()` expecting Spring to guess a choice.

## 9. Auto-Configuration: Avoiding Default Bean Creation When the Application Provides Its Own

In starters, a common cause is auto-configuration creating a default bean even when the application registered its own implementation.

Problematic configuration:

~~~java
@AutoConfiguration
public class PaymentAutoConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

If the application also declares a `PaymentGateway`, both beans can exist and a single-valued injection point hits ambiguity.

The standard solution is `@ConditionalOnMissingBean`:

~~~java
@AutoConfiguration
public class PaymentAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

Meaning:
- If the context does not yet contain a `PaymentGateway` bean, auto-configuration registers the default implementation.
- If the application already supplies a matching bean, the default method does not register a bean.
- Applications can override default behavior without modifying the starter.

### 9.1. `@ConditionalOnMissingBean` Does Not Automatically Resolve Two User-Declared Beans

Suppose the application itself registers both Stripe and Wallet. Auto-configuration will back off because a `PaymentGateway` bean already exists. However, the two user beans still exist.

If a service still injects:

~~~java
CheckoutService(PaymentGateway gateway)
~~~

the dependency remains ambiguous without `@Primary`, `@Qualifier`, or another selection rule.

`@ConditionalOnMissingBean` resolves conflicts between an auto-configuration's default bean and application-provided beans. It does not replace designing injection points for intentionally multiple implementations.

### 9.2. Declare Return Types Specifically Enough

Spring Boot recommends declaring `@Bean` method return types as specifically as possible, especially when using bean conditions.

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

A specific return type gives condition evaluation and type matching more information. If injection points require the interface, the bean can still be injected as `PaymentGateway`.

Ensure the condition expresses the right contract: if the goal is skipping the default whenever any `PaymentGateway` exists, declare `@ConditionalOnMissingBean(PaymentGateway.class)` explicitly.

### 9.3. Auto-Configuration Ordering Matters

Bean conditions are evaluated based on bean definitions processed up to the moment the condition runs. Therefore:
- Use `@ConditionalOnMissingBean` and `@ConditionalOnBean` inside auto-configurations.
- Auto-configurations are designed to run after user-declared bean definitions.
- If a candidate can be created by another auto-configuration, declare ordering via `@AutoConfiguration(after = ...)` or the corresponding ordering mechanism.
- Do not place bean conditions arbitrarily inside component-scanned configurations processed too early.

## 10. `@ConditionalOnSingleCandidate`: Enable Configuration Only When One Bean Can Be Selected

Some auto-configurations require exactly one collaborator. If multiple implementations exist without a single resolvable candidate, that configuration should not activate.

Use `@ConditionalOnSingleCandidate`:

~~~java
@AutoConfiguration
public class PaymentHealthAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(PaymentGateway.class)
    PaymentGatewayHealthIndicator paymentGatewayHealthIndicator(
            PaymentGateway gateway) {

        return new PaymentGatewayHealthIndicator(gateway);
    }
}
~~~

This condition matches when:
- One matching bean exists; or
- Multiple matching beans exist, yet a single primary candidate can be determined.

If two equal gateways exist, the health indicator is not registered. That avoids an injection failure inside this auto-configuration itself.

The condition sees only bean definitions processed up to evaluation time. Therefore, place the condition in auto-configuration and ensure it runs after configurations that create candidates when candidates come from other auto-configurations.

Distinguishing the two annotations:

| Annotation | Purpose |
| --- | --- |
| `@ConditionalOnMissingBean` | Create a default bean only when no matching bean exists yet |
| `@ConditionalOnSingleCandidate` | Create a dependent bean only when a single matching candidate can be resolved |

## 11. Generic Types Can Also Disambiguate Candidates

Spring supports using generic types as implicit qualifiers.

For example:

~~~java
public interface Store<T> {
    T load();
}
~~~

Two implementations:

~~~java
@Bean
Store<String> stringStore() {
    return new StringStore();
}

@Bean
Store<Integer> integerStore() {
    return new IntegerStore();
}
~~~

Injection:

~~~java
public ReportService(
        Store<String> nameStore,
        Store<Integer> countStore) {
    this.nameStore = nameStore;
    this.countStore = countStore;
}
~~~

Spring can use the generic argument to tell `Store<String>` apart from `Store<Integer>`.

This is helpful when the type parameter expresses the dependency's actual role. Preserve explicit generic types across:
- The interface/class declaration.
- The `@Bean` method return type.
- The constructor parameter or field injection point.

If declared too coarsely such as `Store<?>` or raw `Store`, generic information may be insufficient to disambiguate candidates.

Generic qualifiers also apply to collections, maps, and arrays. For example, `List<Store<Integer>>` receives only beans compatible with that generic type.

## 12. Testing Errors and Fixes with `ApplicationContextRunner`

`ApplicationContextRunner` is well suited for testing auto-configuration and candidate resolution in a minimal Spring context.

The example below uses Spring Boot 3.5.16, Java 17, and JUnit 5.

### 12.1. Maven Dependencies

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

### 12.2. Complete Test Class

Create `src/test/java/example/NoUniqueBeanDefinitionExceptionTests.java`:

~~~java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Fallback;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

import static org.assertj.core.api.Assertions.assertThat;

class NoUniqueBeanDefinitionExceptionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void failsWhenTwoBeansMatchSingleValuedInjection() {
        runner.withUserConfiguration(AmbiguousConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();

                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    NoUniqueBeanDefinitionException.class);
                });
    }

    @Test
    void primaryResolvesSingleValuedInjection() {
        runner.withUserConfiguration(PrimaryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    CheckoutService checkout =
                            context.getBean(CheckoutService.class);

                    assertThat(checkout.provider()).isEqualTo("stripe");
                });
    }

    @Test
    void qualifierSelectsTheRequiredImplementation() {
        runner.withUserConfiguration(QualifierConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    CheckoutService checkout =
                            context.getBean(CheckoutService.class);

                    assertThat(checkout.provider()).isEqualTo("wallet");
                });
    }

    @Test
    void fallbackBeanIsNotSelectedWhenARegularCandidateExists() {
        runner.withUserConfiguration(FallbackConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    CheckoutService checkout =
                            context.getBean(CheckoutService.class);

                    assertThat(checkout.provider()).isEqualTo("stripe");
                });
    }

    @Test
    void collectionInjectionReceivesAllCandidates() {
        runner.withUserConfiguration(CollectionConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    GatewayRegistry registry =
                            context.getBean(GatewayRegistry.class);

                    assertThat(registry.providers())
                            .containsExactly("stripe", "wallet");
                });
    }

    @Test
    void autoConfigurationCreatesDefaultOnlyWhenMissing() {
        runner.withConfiguration(
                        AutoConfigurations.of(PaymentAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);

                    assertThat(context.getBean(PaymentGateway.class).provider())
                            .isEqualTo("default");
                });
    }

    @Test
    void userGatewayMakesAutoConfiguredDefaultBackOff() {
        runner.withConfiguration(
                        AutoConfigurations.of(PaymentAutoConfiguration.class))
                .withUserConfiguration(UserGatewayConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);

                    assertThat(context.getBean(PaymentGateway.class).provider())
                            .isEqualTo("custom");
                });
    }

    @Test
    void singleCandidateConditionDoesNotMatchWhenTwoBeansAreAmbiguous() {
        runner.withConfiguration(
                        AutoConfigurations.of(
                                PaymentHealthAutoConfiguration.class))
                .withUserConfiguration(TwoGatewayConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(PaymentGatewayHealthIndicator.class);
                });
    }

    @Test
    void singleCandidateConditionMatchesWhenPrimaryExists() {
        runner.withConfiguration(
                        AutoConfigurations.of(
                                PaymentHealthAutoConfiguration.class))
                .withUserConfiguration(PrimaryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(PaymentGatewayHealthIndicator.class);
                });
    }

    interface PaymentGateway {
        String provider();
    }

    static class StripeGateway implements PaymentGateway {
        @Override
        public String provider() {
            return "stripe";
        }
    }

    static class WalletGateway implements PaymentGateway {
        @Override
        public String provider() {
            return "wallet";
        }
    }

    static class DefaultGateway implements PaymentGateway {
        @Override
        public String provider() {
            return "default";
        }
    }

    static class CheckoutService {

        private final PaymentGateway gateway;

        CheckoutService(PaymentGateway gateway) {
            this.gateway = gateway;
        }

        String provider() {
            return this.gateway.provider();
        }
    }

    record GatewayRegistry(List<String> providers) {
    }

    record PaymentGatewayHealthIndicator(PaymentGateway gateway) {
    }

    @Configuration(proxyBeanMethods = false)
    static class AmbiguousConfiguration {

        @Bean
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }

        @Bean
        CheckoutService checkoutService(PaymentGateway gateway) {
            return new CheckoutService(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryConfiguration {

        @Bean
        @Primary
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }

        @Bean
        CheckoutService checkoutService(PaymentGateway gateway) {
            return new CheckoutService(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class QualifierConfiguration {

        @Bean
        @Qualifier("card")
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        @Qualifier("wallet")
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }

        @Bean
        CheckoutService checkoutService(
                @Qualifier("wallet") PaymentGateway gateway) {
            return new CheckoutService(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class FallbackConfiguration {

        @Bean
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        @Fallback
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }

        @Bean
        CheckoutService checkoutService(PaymentGateway gateway) {
            return new CheckoutService(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CollectionConfiguration {

        @Bean
        @Order(1)
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        @Order(2)
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }

        @Bean
        GatewayRegistry gatewayRegistry(List<PaymentGateway> gateways) {
            return new GatewayRegistry(
                    gateways.stream()
                            .map(PaymentGateway::provider)
                            .toList());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGatewayConfiguration {

        @Bean
        PaymentGateway customGateway() {
            return () -> "custom";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoGatewayConfiguration {

        @Bean
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }
    }

    @AutoConfiguration
    static class PaymentAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(PaymentGateway.class)
        PaymentGateway defaultPaymentGateway() {
            return new DefaultGateway();
        }
    }

    @AutoConfiguration
    static class PaymentHealthAutoConfiguration {

        @Bean
        @ConditionalOnSingleCandidate(PaymentGateway.class)
        PaymentGatewayHealthIndicator paymentGatewayHealthIndicator(
                PaymentGateway gateway) {
            return new PaymentGatewayHealthIndicator(gateway);
        }
    }
}
~~~

### 12.3. Running the Tests

~~~bash
mvn test -Dtest=NoUniqueBeanDefinitionExceptionTests
~~~

Expected result: **9 tests PASS**.

The tests prove:
- Two beans of the same type cause single-valued constructor injection to fail.
- `@Primary` picks a default implementation.
- `@Qualifier` picks the implementation by role.
- `@Fallback` keeps the backup implementation secondary.
- Collection injection receives both implementations and honors `@Order`.
- `@ConditionalOnMissingBean` creates the default when no bean exists yet.
- A user-supplied bean causes the auto-configured default to back off.
- `@ConditionalOnSingleCandidate` does not register the consumer when two equal candidates exist, and matches when one primary candidate exists.

Tests use isolated contexts, needing no database or external services.

## 13. Diagnosing in a Real Application

When encountering the error, follow this sequence to pinpoint the exact injection point and candidates.

### 13.1. Read the Bean Type and Candidate List in the Exception

`NoUniqueBeanDefinitionException` provides:
- `getBeanType()`: the requested type.
- `getNumberOfBeansFound()`: the count of matching candidates.
- `getBeanNamesFound()`: the names of matching beans, if available.

Example:

~~~java
try {
    PaymentGateway gateway =
            applicationContext.getBean(PaymentGateway.class);
}
catch (NoUniqueBeanDefinitionException exception) {
    System.err.println("Type: " + exception.getBeanType());
    System.err.println("Count: " + exception.getNumberOfBeansFound());
    System.err.println("Beans: " + exception.getBeanNamesFound());
}
~~~

In a real application, use a logger instead of `System.err`.

### 13.2. List Bean Names by Type

You can inspect candidates via `ListableBeanFactory`:

~~~java
String[] names =
        applicationContext.getBeanNamesForType(PaymentGateway.class);

for (String name : names) {
    System.out.println(name);
}
~~~

Example output:

~~~text
stripeGateway
walletGateway
~~~

`getBeanNamesForType` lets you inspect bean definitions by type. Avoid calling `getBeansOfType` solely for diagnostics if beans have expensive initialization or side effects, as retrieving instances can trigger bean creation.

### 13.3. Find the Injection Point Requesting a Single Bean

Check the stack trace to locate:
- Which constructor has a `PaymentGateway` parameter.
- Which `@Bean` method has a parameter of that type.
- Which field/setter is marked for autowiring.
- Which code calls `getBean(PaymentGateway.class)`.

Do not modify every bean of that type simply because it appears in the list. Identify which injection point truly requires a single implementation.

### 13.4. Check Whether Auto-Configuration Created a Duplicate Default

If candidates include an application-created bean and a starter bean:
1. Locate the `@Bean` method creating the default.
2. Verify `@ConditionalOnMissingBean` targets the right type.
3. Verify the factory method's return type provides sufficient information.
4. Check auto-configuration ordering.
5. Verify the user bean was registered before the condition ran.

With Spring Boot Actuator, the `beans` endpoint helps view registered beans and the `conditions` endpoint helps understand auto-configuration conditions. Expose only needed endpoints and secure them according to operational policy.

Running the application with `--debug` also prints the condition evaluation report. The report helps identify which auto-configurations matched or backed off; it does not replace inspecting specific injection points and candidates.

## 14. Anti-Patterns That Cause Trouble Later

### 14.1. Do Not Rename Beans Randomly

Renaming `walletGateway` to `walletGatewayV2` does not fix ambiguity when both still implement `PaymentGateway`.

Bean names help selection only when the injection point actually uses a name/qualifier or `@Resource`.

### 14.2. Do Not Put `@Primary` Everywhere

If every implementation is marked `@Primary`, Spring still lacks a unique primary candidate.

If each consumer needs a different gateway, use `@Qualifier` on each dependency.

### 14.3. Do Not Enable Bean Overriding to Fix Same-Type Errors

Bean overriding addresses bean-name collisions. `NoUniqueBeanDefinitionException` arises from multiple candidates of the same type. They are two separate issues.

### 14.4. Do Not Use `@Order` to Select a Single-Valued Bean

`@Order` is suited for ordering collection injection. It is not a substitute for `@Primary` or `@Qualifier` on a constructor expecting one bean.

### 14.5. Do Not Exclude a Bean with `@Profile` Just to Make Tests Pass

`@Profile` should reflect real deployment environments, such as an implementation existing only in `dev` or `production`. If a profile is added only to avoid ambiguity in tests while production still has multiple candidates, the bug remains.

### 14.6. Do Not Inject `Optional<T>` Expecting Automatic Single Selection

`Optional<PaymentGateway>` expresses that a dependency may be absent. If multiple candidates exist and none is uniquely resolvable, Spring still reports ambiguity.

Use `ObjectProvider<T>`, collections, or a registry when handling multiple candidates.

## 15. Solution Selection Matrix

| Situation | Appropriate approach |
| --- | --- |
| One default implementation for the whole application | `@Primary` |
| Each service needs a different implementation | `@Qualifier` |
| One bean is a backup choice | `@Fallback` (Spring 6.2+) |
| Need to select a bean by unique name | `@Resource(name = "...")` |
| Need to iterate over all implementations | `List<T>`, `T[]`, or `Map<String, T>` |
| Need on-demand bean lookup | `ObjectProvider<T>` |
| Starter creates default only if application has not provided one | `@ConditionalOnMissingBean` |
| Auto-configuration needs a single resolvable candidate | `@ConditionalOnSingleCandidate` |
| Multiple implementations of a generic interface | Use generic type as qualifier when appropriate |
| Need to order implementations in a collection | `@Order` |

## 16. Checklist for Resolving `NoUniqueBeanDefinitionException`

1. Read the root cause and identify the requested type.
2. Note the names of all candidates listed in the exception.
3. Find the constructor, field, setter, or `@Bean` method requesting a single-valued bean.
4. Determine whether multiple implementations are intentional or a duplicate default bean.
5. If a single shared default is needed, pick exactly one `@Primary`.
6. If each consumer needs a specific implementation, use `@Qualifier`.
7. If an implementation is merely a fallback, consider `@Fallback` on Spring Framework 6.2+.
8. If all implementations are needed, switch to `List`, `Map`, array, or `ObjectProvider`.
9. If the issue involves a starter, check `@ConditionalOnMissingBean`, return types, and ordering.
10. If auto-configuration should activate only with a unique candidate, use `@ConditionalOnSingleCandidate`.
11. Write tests covering single bean, multiple beans, primary, fallback, and user override.
12. Re-run tests and verify the right implementation is injected in each scenario.

## 17. Self-Check Questions

**Question 1.** When does Spring throw `NoUniqueBeanDefinitionException`?

**Answer:** When a point requires a single bean by type, yet multiple matching candidates exist and no single winning candidate can be determined.

**Question 2.** Does `@Primary` exclude other beans from `List<PaymentGateway>`?

**Answer:** No. Collection injection still receives all matching candidates. `@Primary` affects only single-valued dependencies.

**Question 3.** When should `@Qualifier` be used?

**Answer:** When a consumer requires a specific implementation by role or trait, such as a `card` or `digital-wallet` gateway.

**Question 4.** Which version introduced `@Fallback`?

**Answer:** Spring Framework 6.2. Spring Boot 3.5 uses Spring Framework 6.2 and therefore supports this annotation.

**Question 5.** Does `@ConditionalOnMissingBean` automatically resolve two same-type beans declared by the application?

**Answer:** No. It prevents auto-configuration from creating a default when a matching bean already exists. If the application registers two beans itself, single-valued injection still needs qualifiers or candidate-selection rules.

**Question 6.** What is `@ConditionalOnSingleCandidate` used for?

**Answer:** Enabling a bean/configuration only when a single candidate can be resolved, such as one matching bean or multiple beans with a primary candidate.

**Question 7.** Does `@Order` select an implementation for a single-valued constructor?

**Answer:** No. `@Order` primarily controls collection injection order; use `@Primary` or `@Qualifier` for single-valued dependencies.

**Question 8.** When selecting a bean explicitly by name, which annotation should be considered?

**Answer:** `@Resource(name = "...")` expresses bean-name selection semantics. For constructor injection, `@Qualifier` on the parameter is usually more suitable.

## 18. Official References

- Spring Framework 6.2 — Fine-tuning Annotation-based Autowiring with `@Primary` or `@Fallback`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html
- Spring Framework 6.2 — Fine-tuning Annotation-based Autowiring with Qualifiers: https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html
- Spring Framework 6.2 — Using Generics as Autowiring Qualifiers: https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/generics-as-qualifiers.html
- Spring Framework 6.2 API — `NoUniqueBeanDefinitionException`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/NoUniqueBeanDefinitionException.html
- Spring Framework 6.2 API — `Fallback`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Fallback.html
- Spring Boot 3.5 — Creating Your Own Auto-configuration, bean conditions, and auto-configuration ordering: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `ConditionalOnSingleCandidate`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html
- Spring Boot 3.5 API — `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
