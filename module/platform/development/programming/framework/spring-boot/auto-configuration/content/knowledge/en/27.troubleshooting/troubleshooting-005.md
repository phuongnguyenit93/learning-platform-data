# Default Bean Missing Because the Missing-Bean Condition No Longer Matches

> **Goal:** Diagnose why a Spring Boot auto-configuration's default bean is not registered when `@ConditionalOnMissingBean` stops matching. This lesson focuses on reading the Condition Evaluation Report, locating the bean definition causing back-off, checking type/name, `@Bean` method return types, auto-configuration ordering, context hierarchy, and testing with `ApplicationContextRunner`.

Examples use Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+, JUnit Jupiter, and AssertJ. The core scenario is that **Spring already sees a matching bean**, so the default bean backs off. This is often intentional overriding behavior, though it can also stem from an unexpected definition registration, unclear type metadata, or incorrect ordering.

## 1. What Does the Condition Actually Decide?

`@ConditionalOnMissingBean` is a Spring Boot bean condition. It matches only when the BeanFactory does not yet contain a bean meeting the declared criteria. If a matching bean is found, the condition does not match and the default bean guarded by the annotation is not registered.

~~~java
@AutoConfiguration
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

Decision flow:

~~~text
Spring processes auto-configuration
              |
              v
Evaluates @ConditionalOnMissingBean(PaymentGateway.class)
              |
       +------+------+
       |             |
       v             v
No matching      Matching bean
bean found       already found
       |             |
       v             v
MATCH            NO MATCH
       |             |
       v             v
Register default Skip default bean
bean definition  definition
~~~

This condition allows applications to replace the default implementation with their own bean. Therefore, the default bean disappearing after the application adds a bean of the same contract is usually expected behavior.

Distinguish three states:

- **No bean definition:** the condition can match and the default definition is registered.
- **Definition exists, but instance not yet created:** the condition can still see the definition; a lazy bean can still make the default back off.
- **Instance already created:** this is a later phase. The condition does not need to invoke constructors or fetch instances to decide.

`@ConditionalOnMissingBean` does not guarantee the application always has exactly one bean. It only decides whether to register an extra default. If one or more matching beans already exist, auto-configuration yields default registration.

## 2. Determine Whether the Condition Checks Type, Name, or Annotation

When placed on a `@Bean` method without specifying `value`, `type`, or `name`, Spring Boot defaults to using the method's declared return type as the type to check.

~~~java
@Bean
@ConditionalOnMissingBean
PaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

In this example, the default target type is `PaymentGateway`. Another bean implementing that interface can cause the default method to back off.

Commonly used attributes:

| Attribute | Meaning |
| --- | --- |
| `value` | Bean types specified via Class |
| `type` | Bean types specified via String class names |
| `name` | Bean names to check |
| `annotation` | Beans annotated with the specified annotation |
| `ignored` | Types ignored when determining matching beans |
| `ignoredType` | Type names ignored |
| `search` | Search scope in the context hierarchy |
| `parameterizedContainer` | Container whose generic parameter holds the target type |

When multiple criteria are specified, the condition matches only if all declared criteria are absent. Criteria do not all have to be matched by the same bean. Finding a bean for any single checked criterion can cause the condition not to match.

### 2.1. Checking by Type vs. Checking by Name

By type:

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

A bean named `customGateway` that implements `PaymentGateway` still causes the condition not to match.

By name:

~~~java
@Bean
@ConditionalOnMissingBean(name = "customPaymentGateway")
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Here the condition checks the name `customPaymentGateway`. A bean of the same type with a different name will not automatically satisfy a name check.

Choose criteria according to the starter's contract:

- Want applications to replace the implementation with any bean sharing the abstraction: check by type.
- Want to avoid registering a duplicate specific bean name: check by name.
- Want to apply based on a marker annotation: use `annotation`.

Do not combine type and name together unless the contract needs both. Each attribute changes the set of beans that can make the default back off.

### 2.2. Lazy and Primary Beans Still Count as Present Beans

~~~java
@Bean
@Lazy
CustomPaymentGateway customPaymentGateway() {
    return new CustomPaymentGateway();
}
~~~

`@Lazy` defers instance creation; it does not remove the bean definition. If a definition of matching type has already been processed, the condition can still see it.

Similarly, `@Primary` affects candidate selection when injecting among multiple beans; it does not hide a bean from existence checks. A `@Primary` bean can still cause the default to back off.

## 3. Why Bean Definition Processing Order Matters

Spring evaluates bean conditions while processing configuration classes and registering bean definitions. Conditions can rely only on definitions already processed at that point.

- User-declared bean definitions are generally processed before auto-configuration.
- Beans provided by another auto-configuration are visible only if their definitions were processed earlier.
- A bean registered later cannot cause an earlier condition to re-evaluate itself.

This is why Spring Boot recommends placing `@ConditionalOnBean` and `@ConditionalOnMissingBean` primarily on auto-configurations. Auto-configuration applies after user-declared bean definitions, letting user overrides remain predictable.

### 3.1. Provider and Fallback Are Two Separate Auto-Configurations

Suppose one auto-configuration supplies the primary transport and another supplies a fallback transport.

~~~java
@AutoConfiguration
public class PrimaryTransportAutoConfiguration {

    @Bean
    PrimaryTransport primaryTransport() {
        return new PrimaryTransport();
    }
}
~~~

Fallback configuration:

~~~java
@AutoConfiguration(after = PrimaryTransportAutoConfiguration.class)
public class FallbackTransportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Transport.class)
    FallbackTransport fallbackTransport() {
        return new FallbackTransport();
    }
}
~~~

`after` ensures the provider is applied before the fallback. When `fallbackTransport`'s condition is evaluated, the `PrimaryTransport` bean definition is already visible via type `Transport`, so the fallback is not registered.

Do not use `@DependsOn` to fix this order. `@DependsOn` controls bean instance dependencies/lifecycle; it does not replace auto-configuration and bean definition processing order. Use `@AutoConfiguration(after = ...)` or `@AutoConfigureAfter` for ordering between auto-configurations.

### 3.2. Do Not Arbitrarily Place Bean Conditions on User Configurations

An application-declared `@Configuration` might be processed before the bean definition it expects from another auto-configuration. Placing `@ConditionalOnMissingBean` on user configuration can make outcomes depend on scan/import order.

Use bean conditions primarily in library auto-configurations. If you need to toggle user configuration, consider `@ConditionalOnProperty` or `@Profile` with clearer semantics.

## 4. Checking the Return Type of `@Bean` Methods

A subtle bug occurs when a method returns an overly generic type:

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
Object paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Returning `Object` makes the bean definition's type metadata unspecific. Spring Boot must rely on type information inferable from the method signature; it should not rely on invoking the method to obtain an instance before deducing its implementation.

Declare the type reflecting the real contract:

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Or let the default condition infer from the interface:

~~~java
@Bean
@ConditionalOnMissingBean
PaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

These two express different contracts:

- `@ConditionalOnMissingBean(PaymentGateway.class)` checks the explicitly specified abstraction.
- `@ConditionalOnMissingBean` without `value`, `type`, or `name` uses the method's declared return type.

Spring Boot recommends exposing as much type information as possible in `@Bean` method return types. When diagnosing, check:

1. Does the method return an interface or a concrete class?
2. Is `Object`, `FactoryBean`, or a generic wrapper obscuring the type?
3. Does the condition check the exact interface the user bean implements?
4. Does a String-based `type` attribute have a wrong package or class name?

Do not blindly switch every method to concrete classes. Choose return types and condition targets based on the API the starter intends to expose.

## 5. Context Hierarchy Can Let a Parent Bean Block the Default

The `search` attribute controls whether the condition searches parent contexts. The default is `SearchStrategy.ALL`, meaning it searches the entire hierarchy.

| SearchStrategy | Scope |
| --- | --- |
| `ALL` | Current context and the entire parent hierarchy |
| `CURRENT` | Only the current context |
| `ANCESTORS` | Only ancestor contexts, excluding the current context |

Example checking only the current context:

~~~java
@Bean
@ConditionalOnMissingBean(
        value = PaymentGateway.class,
        search = SearchStrategy.CURRENT)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Use `CURRENT` only when the contract genuinely requires a child context to have its own default despite the parent having a bean of the same type. Never use it solely to force a default back; the parent bean may be an intentional override.

During investigation, determine:

1. Does the application have a parent context?
2. Is the matching bean in the current context or the parent?
3. Does the condition use `ALL`, `CURRENT`, or `ANCESTORS`?
4. Would ignoring the parent break expectations of sharing beans between the root context and child web context?

## 6. Sources of Bean Definitions That Can Prevent Matching

| Source | Example | What to check |
| --- | --- | --- |
| User configuration | `@Bean PaymentGateway customGateway()` | Bean type and configuration's conditions |
| Component scan | `@Component` or `@Service` implementing interface | Whether package scan discovers the component |
| Another auto-configuration | Provider auto-configuration | Ordering between the two configurations |
| Direct import | `@Import(CustomGatewayConfiguration.class)` | Whether the imported configuration was processed |
| Parent context | Bean declared in root context | The `search` attribute |
| Lazy bean | `@Lazy @Bean` | Definition still exists even if instance is uncreated |
| Factory method | `@Bean` returning implementation or interface | Whether return type provides sufficient info |
| Test configuration | `@TestConfiguration` or `withBean` | Whether test inadvertently supplies a replacement bean |

Common points of confusion:

- `@Primary` does not exclude a bean from existence checks.
- `@Lazy` delays instance creation, not definition registration.
- A declared bean whose own condition does not match will not produce a definition to block the default.
- Parent beans count when `search = ALL`.
- Beans from another auto-configuration might already be registered before the fallback condition runs.

If multiple beans match the type, the condition can still back off. `@ConditionalOnMissingBean` is not a tool for picking a single candidate; injecting one versus many beans is a separate concern.

## 7. Reading the Condition Evaluation Report to Find the Cause

The fastest way to learn why a default bean was skipped is reading the Condition Evaluation Report.

Run the application with debug:

~~~bash
java -jar target/application.jar --debug
~~~

Locate the auto-configuration name and the missing bean method. `OnBeanCondition` records the match/no-match reason. An illustrative message when a matching bean is found:

~~~text
PaymentGatewayAutoConfiguration#paymentGateway:
@ConditionalOnMissingBean (types: com.acme.payment.PaymentGateway;
SearchStrategy: all) found beans of type 'PaymentGateway'
~~~

This is an explanatory example, not a fixed log string across every Boot version. Read the actual type, search strategy, and bean names returned by your report.

### 7.1. Printing the Report in an ApplicationContextRunner Test

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(PaymentGatewayAutoConfiguration.class))
        .run(context -> {
            // Assertions.
        });
~~~

Imports:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

The listener lets you inspect condition outcomes in tests without booting the full application.

### 7.2. Actuator Conditions Endpoint

If the application already uses Actuator and the endpoint is exposed/authorized, you can query:

~~~text
GET /actuator/conditions
~~~

The `conditions` endpoint returns positive and negative matches per context. Look for keys shaped like `AutoConfigurationClass#beanMethod` to see which bean's condition failed to match.

Do not expose diagnostic endpoints broadly in production without securing access. During local debugging, `--debug` or the test listener is usually enough.

## 8. Diagnostic Workflow

1. **Confirm the expected bean.** Note the bean name, type/interface, and auto-configuration class owning the method.
2. **Confirm the configuration loaded.** Check imports/discovery, exclusions, and class-level conditions.
3. **Read the condition report.** Find the method's `OnBeanCondition` and inspect type/name/annotation/search strategy.
4. **Find the bean causing no-match.** Check user configuration, component scan, imported configs, other auto-configurations, test configurations, and parent context.
5. **Check return types.** Verify what the default method declares and whether the target type is accurate.
6. **Check ordering.** If the backing-off bean comes from another auto-configuration, ensure the fallback runs after the provider.
7. **Check search strategy.** Confirm whether parent beans should be counted.
8. **Check remaining conditions.** Property, classpath, resource, or web conditions on the class/method can also block registration.
9. **Write a reproduction test.** Use `ApplicationContextRunner` with each combination of user beans and auto-configurations.

Do not delete the bean causing the condition to fail just to force the default to appear. First determine whether that bean is an intentional override, a dependency from another module, or an accidentally registered definition.

## 9. Complete Example: Default PaymentGateway Backs Off Automatically

### 9.1. Contract and Implementations

**`src/main/java/com/acme/payment/PaymentGateway.java`**

~~~java
package com.acme.payment;

public interface PaymentGateway {
    String provider();
}
~~~

**`src/main/java/com/acme/payment/DefaultPaymentGateway.java`**

~~~java
package com.acme.payment;

public final class DefaultPaymentGateway implements PaymentGateway {

    @Override
    public String provider() {
        return "default";
    }
}
~~~

**`src/main/java/com/acme/payment/CustomPaymentGateway.java`**

~~~java
package com.acme.payment;

public final class CustomPaymentGateway implements PaymentGateway {

    @Override
    public String provider() {
        return "custom";
    }
}
~~~

### 9.2. Auto-Configuration

**`src/main/java/com/acme/payment/autoconfigure/PaymentGatewayAutoConfiguration.java`**

~~~java
package com.acme.payment.autoconfigure;

import com.acme.payment.DefaultPaymentGateway;
import com.acme.payment.PaymentGateway;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    DefaultPaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

The return type is the concrete class, while the condition checks the `PaymentGateway` interface. Any previously processed bean definition of a matching implementation will make the default method back off.

### 9.3. Registering Auto-Configuration

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.acme.payment.autoconfigure.PaymentGatewayAutoConfiguration
~~~

### 9.4. Testing Default and User Override

**`src/test/java/com/acme/payment/autoconfigure/PaymentGatewayAutoConfigurationTests.java`**

~~~java
package com.acme.payment.autoconfigure;

import com.acme.payment.CustomPaymentGateway;
import com.acme.payment.PaymentGateway;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentGatewayAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    PaymentGatewayAutoConfiguration.class));

    @Test
    void createsDefaultGatewayWhenNoUserGatewayExists() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(PaymentGateway.class);
            assertThat(context).hasBean("paymentGateway");
            assertThat(context.getBean(PaymentGateway.class).provider())
                    .isEqualTo("default");
        });
    }

    @Test
    void backsOffWhenUserProvidesGateway() {
        runner.withUserConfiguration(UserGatewayConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                    assertThat(context).hasBean("customPaymentGateway");
                    assertThat(context).doesNotHaveBean("paymentGateway");
                    assertThat(context.getBean(PaymentGateway.class).provider())
                            .isEqualTo("custom");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGatewayConfiguration {

        @Bean
        CustomPaymentGateway customPaymentGateway() {
            return new CustomPaymentGateway();
        }
    }
}
~~~

Expected result:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

The two tests prove both states: without a user bean, the default is registered; with a user bean of the same contract, the default backs off and the user bean is used.

### 9.5. Testing Ordering Between Two Auto-Configurations

~~~java
interface Transport {
}

final class PrimaryTransport implements Transport {
}

final class FallbackTransport implements Transport {
}

@AutoConfiguration
class PrimaryTransportAutoConfiguration {

    @Bean
    PrimaryTransport primaryTransport() {
        return new PrimaryTransport();
    }
}

@AutoConfiguration(after = PrimaryTransportAutoConfiguration.class)
class FallbackTransportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Transport.class)
    FallbackTransport fallbackTransport() {
        return new FallbackTransport();
    }
}
~~~

Test:

~~~java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                PrimaryTransportAutoConfiguration.class,
                FallbackTransportAutoConfiguration.class))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(Transport.class);
            assertThat(context).hasBean("primaryTransport");
            assertThat(context).doesNotHaveBean("fallbackTransport");
        });
~~~

`after` ensures the provider applies before the fallback. The condition sees the provider definition and skips registering the fallback.

### 9.6. Dependencies and Run Commands

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}
~~~

~~~bash
./gradlew test --tests com.acme.payment.autoconfigure.PaymentGatewayAutoConfigurationTests
~~~

With Maven:

~~~bash
mvn -Dtest=PaymentGatewayAutoConfigurationTests test
~~~

The result above is expected output when tests pass; confirm using your module's actual build.

## 10. Advanced Attributes

### 10.1. Search Strategy

Example checking only the current context:

~~~java
@Bean
@ConditionalOnMissingBean(
        value = PaymentGateway.class,
        search = SearchStrategy.CURRENT)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Use when a child context needs its own default even if the parent has a bean of the same type. If the application expects children to inherit the gateway from the parent, keep the default `ALL`.

### 10.2. Ignored Types

`ignored` and `ignoredType` allow ignoring certain types when checking for matching beans:

~~~java
@Bean
@ConditionalOnMissingBean(
        value = PaymentGateway.class,
        ignored = LegacyPaymentGatewayAdapter.class)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Use only when the contract genuinely requires an adapter/compatibility bean not to count as a replacement implementation. Using `ignored` merely to force a condition to match can hide an existing bean and create two implementations simultaneously.

`ignoredType` accepts class names as Strings; it is useful when avoiding direct class references in the annotation.

### 10.3. Parameterized Container

When checking for a type inside a generic container, `parameterizedContainer` lets you declare the container type:

~~~java
@ConditionalOnMissingBean(
        value = PaymentGateway.class,
        parameterizedContainer = GatewayRegistration.class)
~~~

Use only when the library genuinely uses `GatewayRegistration<PaymentGateway>` as a provider registration wrapper. Be explicit about the generic structure to recognize.

## 11. Common Issues and Fixes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Default disappears after adding custom `@Bean` | User bean of same type makes condition no-match | Confirm intentional override; inspect report |
| Default disappears even though custom bean is `@Lazy` | Definition already exists despite uncreated instance | Check definitions, not only singleton instances |
| Default disappears due to parent bean | Default `search` is `ALL` | Verify hierarchy; consider `CURRENT` if contract requires |
| Default still appears even though provider auto-config has bean | Fallback processed before provider | Add `after` or `@AutoConfigureAfter` |
| Condition checks wrong type | Overly generic return type or wrong target | Declare clear types and check signatures |
| Bean backs off despite multiple implementations | Condition only needs to find any matching bean | Check type/name/annotation criteria |
| Report lacks expected `OnBeanCondition` | Configuration not discovered or blocked by another condition/exclusion | Check imports, exclusions, and class-level conditions |
| Test passes, but real app behaves differently | Test lacks equivalent user config or parent context | Build a context reflecting real discovery and hierarchy |
| Used `@Primary`, yet default still backs off | `@Primary` does not exclude bean from existence check | Separate bean existence from injection selection |
| Used `ignored` to force default to appear | Condition ignores a bean that is a valid override | Fix the contract or remove the misregistered bean |

## 12. Review Checklist

- [ ] Identified the exact auto-configuration class and `@Bean` method.
- [ ] Read the Condition Evaluation Report for `OnBeanCondition`.
- [ ] Identified the type, name, or annotation checked by `@ConditionalOnMissingBean`.
- [ ] Found the bean definition causing back-off and its registration source.
- [ ] Checked `@Lazy` beans, test configurations, and component scanning.
- [ ] Checked return types and type metadata.
- [ ] Confirmed ordering if the provider comes from another auto-configuration.
- [ ] Checked `search` and parent contexts.
- [ ] Checked other class-level and method-level conditions.
- [ ] Wrote tests for both default and override.
- [ ] Did not remove valid providers or ignore bean types unintentionally.

## 13. Self-Check Questions

1. When does `@ConditionalOnMissingBean` match?  
   **Answer:** When the BeanFactory does not contain a bean matching the specified type, name, or annotation criteria.

2. Why does adding a user bean with the same interface make the default disappear?  
   **Answer:** The user bean already exists in the BeanFactory, so the condition does not match and the default method does not register a bean definition.

3. Does a `@Lazy` bean make the default back off?  
   **Answer:** Yes, it can. Lazy delays instantiation, yet the definition still exists and can be seen by the condition.

4. If no type is declared, which type does the condition on a `@Bean` method check?  
   **Answer:** The method's declared return type when `value`, `type`, and `name` are unspecified.

5. Why is `@AutoConfiguration(after = ...)` needed?  
   **Answer:** So the provider is processed before the fallback, allowing the condition to see the provider's bean definition.

6. What does `SearchStrategy.ALL` mean?  
   **Answer:** Search in the current context and across the entire parent hierarchy.

7. Does `@Primary` exclude a bean from being counted as an existing bean?  
   **Answer:** No. It affects candidate selection during injection, not existence checks.

8. Why is the condition report helpful?  
   **Answer:** It shows which conditions matched or did not match and why, helping pinpoint the bean or criterion causing back-off.

9. Should `@ConditionalOnMissingBean` be placed on arbitrary user `@Configuration` classes?  
   **Answer:** No. Spring Boot recommends using bean conditions primarily in auto-configurations because user definitions order more naturally ahead of them.

10. If another auto-configuration supplies a bean after the fallback, does the fallback condition re-evaluate?  
    **Answer:** No. Conditions rely on definitions processed at evaluation time; proper ordering is required.

## Official References

- [Spring Boot 3.3.13 — ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): type/name/annotation criteria, default return type, ignored types, and search strategy.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): bean conditions, definition processing order, `@Bean` return types, and testing back-off.
- [Spring Boot 3.3.13 — ConditionEvaluationReport API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): API storing condition outcomes for reporting.
- [Spring Boot 3.3.13 — ConditionEvaluationReportLoggingListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): initializer that logs the condition report.
- [Spring Boot 3.3.13 — Conditions Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): reporting positive/negative matches via `/actuator/conditions`.
- [Spring Boot 3.3.13 — SearchStrategy API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html): meaning of `ALL`, `CURRENT`, and `ANCESTORS`.

**Key takeaway:** A default bean disappears when `@ConditionalOnMissingBean` sees a matching bean definition at the time the condition is evaluated. Read the condition report, identify the type/name/search scope, check return types and ordering, and write tests for both default and override. This back-off mechanism is what makes auto-configuration customizable; accurate diagnosis tells you whether an existing bean is an intentional override or an unintended definition.
