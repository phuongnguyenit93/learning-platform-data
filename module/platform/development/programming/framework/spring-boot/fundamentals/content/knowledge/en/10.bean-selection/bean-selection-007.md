# `Ordered`, `@Order`, and Bean Ordering in Collections

In a Spring Boot application, sometimes you need to inject **multiple beans implementing the same interface** into a service. For example, an order might pass through multiple discount rules; a request might go through multiple business filters; or an application might need to run multiple `CommandLineRunner`s after startup.

In such cases, simply having all beans in the container is not enough. **Execution order** can also directly affect the result. Spring provides `Ordered` and `@Order` to express priority order for extension points that support sorting mechanisms.

Key things to remember right from the start:

- A **smaller order number means higher priority**, meaning it is placed earlier.
- `Ordered` is an interface allowing a bean to return its own order value.
- `@Order` is an annotation declaring the order value on a class or configuration method.
- When injecting a `List<T>` or array containing multiple matching beans, Spring can sort the elements by order.
- `@Order` **does not control singleton initialization order** and does not replace `@Primary` or `@Qualifier` when selecting a single unique bean.

## 1. Why is bean ordering needed?

Suppose a retail application has multiple pricing rules:

```text
Initial price
    |
    v
Member discount
    |
    v
Campaign discount
    |
    v
Partner price adjustment
    |
    v
Final price
```

Each rule is implemented by a separate bean. If a service accepts a collection of rules, the application needs a consistent order to apply them.

Without a clear order, results can depend on the order beans were discovered or how the collection was built. That makes code hard to read and prone to bugs when adding new implementations.

Spring supports ordering metadata so the container and framework components using order comparators can sort beans.

## 2. What is `Ordered`?

`Ordered` is an interface in `org.springframework.core`. A bean implementing this interface must provide the `getOrder()` method:

```java
public interface Ordered {
    int getOrder();
}
```

The return value is an integer. **The smaller the value, the higher the order precedence.**

For example:

```java
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;

@Component
public class UrgentTaskHandler implements Ordered {

    @Override
    public int getOrder() {
        return 1;
    }
}
```

The `UrgentTaskHandler` bean provides its order programmatically. This works well when order must be decided by bean logic, or when an implementation can naturally implement `Ordered`.

### 2.1. Two commonly used constants

Spring defines two handy constants:

| Constant | Value/meaning | Position |
| --- | --- | --- |
| `Ordered.HIGHEST_PRECEDENCE` | `Integer.MIN_VALUE` | Highest priority by order convention |
| `Ordered.LOWEST_PRECEDENCE` | `Integer.MAX_VALUE` | Lowest priority by order convention |

For example:

```java
import org.springframework.core.Ordered;

public class SecurityCheck implements Ordered {
    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
```

If no specific order value is provided, Spring normally treats an element without declared order as having the lowest priority (`LOWEST_PRECEDENCE`) in mechanisms using `OrderComparator`.

### 2.2. Both negative and positive numbers can be used

Order is not a 1-based index. You can use negative numbers, 0, or positive numbers:

```java
public int getOrder() {
    return -10;
}
```

Example ascending order:

| Bean | Order | Position |
| --- | ---: | ---: |
| `EmergencyHandler` | `-100` | 1 |
| `AuthenticationHandler` | `0` | 2 |
| `BusinessHandler` | `10` | 3 |
| `LoggingHandler` | `50` | 4 |

Leave gaps between values, such as 10, 20, 30, so you can insert another handler in between without renumbering everything.

## 3. What is `@Order`?

`@Order` is a Spring Core annotation located in package `org.springframework.core.annotation`. It lets you declare an order directly without having the class implement `Ordered`.

For example:

```java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class MemberDiscountRule {
}
```

Another class:

```java
@Component
@Order(20)
public class CampaignDiscountRule {
}
```

When these two beans are placed into a collection that Spring sorts by order, `MemberDiscountRule` comes before `CampaignDiscountRule` because 10 is less than 20.

### 3.1. Default value

If no value is specified, `@Order` defaults to `Ordered.LOWEST_PRECEDENCE`:

```java
@Component
@Order
public class DefaultPriorityHandler {
}
```

In practice, if multiple beans do not declare an order, do not rely on accidental or registration order to build business logic. When order matters, declare it explicitly and prefer distinct order values.

### 3.2. Placing `@Order` on `@Bean` methods

Not only component classes—you can also place `@Order` on `@Bean` factory methods:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class HandlerConfiguration {

    @Bean
    @Order(1)
    public TaskHandler validationHandler() {
        return new ValidationHandler();
    }

    @Bean
    @Order(2)
    public TaskHandler auditHandler() {
        return new AuditHandler();
    }
}
```

Spring can use metadata on the factory method to determine the order of the bean created from that method. This is useful when you do not own the implementation class, such as a class from an external library.

**Choose one clear place to declare order:** if both the class and the factory method carry order metadata, check the metadata lookup rules of the Spring version you use; do not set two conflicting values and expect readers to guess which takes effect.

## 4. Injecting multiple beans into `List<T>`

This is the most common use case. Suppose the application has an interface:

```java
package com.example.shop.discount;

import java.math.BigDecimal;

public interface DiscountRule {
    BigDecimal apply(BigDecimal price);
}
```

Two implementations:

```java
package com.example.shop.discount;

import java.math.BigDecimal;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class MemberDiscountRule implements DiscountRule {
    @Override
    public BigDecimal apply(BigDecimal price) {
        return price.multiply(new BigDecimal("0.90"));
    }
}
```

```java
package com.example.shop.discount;

import java.math.BigDecimal;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class CampaignDiscountRule implements DiscountRule {
    @Override
    public BigDecimal apply(BigDecimal price) {
        return price.subtract(new BigDecimal("5.00"));
    }
}
```

Service receiving all beans of matching type:

```java
package com.example.shop.discount;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PricingService {

    private final List<DiscountRule> rules;

    public PricingService(List<DiscountRule> rules) {
        this.rules = rules;
    }

    public BigDecimal calculate(BigDecimal originalPrice) {
        BigDecimal result = originalPrice;

        for (DiscountRule rule : rules) {
            result = rule.apply(result);
        }

        return result;
    }
}
```

Spring finds candidate beans of type `DiscountRule`, then under standard collection autowiring, sorts the `List` using the order comparator. With the two beans above, the list passed to the constructor follows the order:

```text
1. MemberDiscountRule   @Order(10)
2. CampaignDiscountRule @Order(20)
```

With an initial price of 100:

```text
100.00
  -> 10% member discount = 90.00
  -> minus 5.00 campaign = 85.00
```

Order can change the outcome:

```text
100.00
  -> minus 5.00 campaign = 95.00
  -> 10% member discount = 85.50
```

Therefore, for sequential business pipelines, order should be treated as part of the design and recorded explicitly in code.

## 5. Injecting arrays and other collection types

### 5.1. Arrays

Spring also supports injecting an array of beans of the same type:

```java
@Service
public class PricingService {
    private final DiscountRule[] rules;

    public PricingService(DiscountRule[] rules) {
        this.rules = rules;
    }
}
```

Under standard array autowiring, candidate beans are sorted using the order comparator before being placed into the array. The rule that smaller values come first still applies.

### 5.2. `List` is the right choice when order matters

If application logic needs to iterate over beans in a sequence, `List<T>` expresses intent clearly and Spring supports sorting this collection by order.

You can use:

```java
private final List<DiscountRule> rules;
```

to represent an ordered pipeline.

### 5.3. `Set` is not an ordering contract

`Set` is designed to represent a collection of unique elements. Depending on implementation and resolution, a Set's iteration order is not always a contract the application should rely on.

```java
public PricingService(Set<DiscountRule> rules) {
    // Do not assume iteration order matches @Order.
}
```

If execution order matters, inject `List<DiscountRule>` or explicitly convert and sort the data into a list with a clear rule.

### 5.4. `Map<String, T>` is useful for bean-name lookup

You can inject a map:

```java
public NotificationService(Map<String, NotificationChannel> channels) {
    // key is typically bean name, value is corresponding bean
}
```

A map is convenient when you need to select a bean by name such as `emailChannel`, `smsChannel`. However, the main purpose of map injection is mapping **bean name → bean instance**; do not treat the map's iteration order as an `@Order` contract. If you need to iterate in order, extract the values and sort them explicitly.

### 5.5. Comparison

| Injection type | Purpose | Should you rely on `@Order` for iteration? |
| --- | --- | --- |
| `List<T>` | Multiple beans in a sequence | Yes, with Spring's standard collection autowiring |
| `T[]` | Multiple beans in an array | Yes, with standard array autowiring |
| `Set<T>` | Set of unique beans | Do not rely on iteration order |
| `Map<String, T>` | Look up beans by name | Do not rely on iteration order |
| `ObjectProvider<T>.orderedStream()` | Retrieve beans in order | Yes, stream is explicitly requested ordered |

## 6. How do `Ordered` and `@Order` differ?

Both express order, yet their declaration styles and flexibility differ.

| Criterion | `Ordered` | `@Order` |
| --- | --- | --- |
| Kind | Interface | Annotation |
| Declaration | Implement `getOrder()` | Attach annotation with numeric value |
| Value | Can be computed in method | Static metadata value |
| Suited for | Beans with logic providing their own order | Components or `@Bean` methods needing declarative order |
| Can be used together? | Yes, though precedence rules must be understood | Yes, though `Ordered` takes precedence when the object implements the interface |

### 6.1. What if a class both implements `Ordered` and has `@Order`?

For example:

```java
@Component
@Order(100)
public class SpecialHandler implements Ordered {

    @Override
    public int getOrder() {
        return 5;
    }
}
```

When Spring uses `OrderComparator` to inspect an **instance**, the value from the `Ordered` interface takes precedence over the `@Order` metadata on the class. In this example, the order used is 5.

Do not declare two conflicting values without a special reason. Choosing one mechanism is enough to keep code readable.

### 6.2. Example of dynamically computed order

A bean can return its order from a configured property:

```java
@Component
public class ConfigurableHandler implements Ordered {

    private final int order;

    public ConfigurableHandler(
            @Value("${handler.order:50}") int order) {
        this.order = order;
    }

    @Override
    public int getOrder() {
        return order;
    }
}
```

In this example, `@Value` reads the `handler.order` configuration property, defaulting to 50. When the bean is sorted, `getOrder()` returns the injected value. Importing `org.springframework.beans.factory.annotation.Value` is required.

## 7. What is `PriorityOrdered`?

`PriorityOrdered` is an interface extending `Ordered`:

```java
public interface PriorityOrdered extends Ordered {
}
```

It represents a group with higher priority than objects implementing only `Ordered` in mechanisms using `OrderComparator`.

For example:

```java
@Component
public class InfrastructureHandler implements PriorityOrdered {
    @Override
    public int getOrder() {
        return 100;
    }
}
```

and:

```java
@Component
public class ApplicationHandler implements Ordered {
    @Override
    public int getOrder() {
        return -100;
    }
}
```

In an extension point applying `PriorityOrdered` grouping rules, `InfrastructureHandler` can be placed ahead of the regular `Ordered` group even though its order number is larger. Therefore, do not assume comparing integers alone suffices when a specific mechanism also inspects the `PriorityOrdered` marker interface.

`PriorityOrdered` is mainly useful in Spring infrastructure extensions, such as certain types of post-processors. For ordinary business collections, `Ordered` or `@Order` is usually sufficient; there is no need to use `PriorityOrdered` just to feel like giving higher priority.

## 8. `@Order` does not control bean initialization order

This is a very common misconception.

```java
@Component
@Order(1)
public class FirstService {
    public FirstService() {
        System.out.println("FirstService constructor");
    }
}

@Component
@Order(2)
public class SecondService {
    public SecondService() {
        System.out.println("SecondService constructor");
    }
}
```

Do not treat those two annotations as a guarantee that `FirstService`'s constructor is always called before `SecondService`'s constructor.

`@Order` primarily affects ordering when beans are **collected and sorted** at extension points that support ordering. Bean initialization order also depends on:

- Dependencies between beans.
- Scope and lazy initialization.
- How the container registers and creates singletons.
- Callbacks and post-processors.
- Specific framework lifecycle mechanisms.

If bean B strictly requires bean A to be initialized first due to a dependency relationship, express the dependency via constructor injection. If you only need to enforce earlier initialization without a direct dependency, consider `@DependsOn`.

For example:

```java
@Component
@DependsOn("databaseInitializer")
public class SearchIndexService {
}
```

`@DependsOn` requires the specified bean to be initialized before the annotated bean in applicable cases. This is a different mechanism from sorting collections with `@Order`.

### 8.1. `@Order` and `@DependsOn`

| Annotation | Question answered | Primary effect |
| --- | --- | --- |
| `@Order(10)` | Where should this element sit when sorted? | Order in supported collections/extension points |
| `@DependsOn("dataSourceInitializer")` | Which bean must be initialized first? | Initialization ordering relationship between beans |

If `ReportService` injects `DataSource`, the constructor dependency already expresses the dependency relationship. There is no need to add `@DependsOn` just to ensure DataSource exists before ReportService in that situation.

## 9. `@Order` does not replace `@Primary` and `@Qualifier`

The three annotations have different goals:

```text
Multiple beans of the same type
        |
        +--> Need to pick one bean to inject?
        |       @Primary / @Qualifier
        |
        +--> Need all beans in sequence?
                @Order / Ordered
```

### 9.1. `@Primary`: choosing a default candidate

```java
@Component
@Primary
public class EmailNotificationChannel implements NotificationChannel {
}

@Component
public class SmsNotificationChannel implements NotificationChannel {
}
```

If a bean needs to inject a single `NotificationChannel`, `EmailNotificationChannel` is the primary candidate when no qualifier or more specific selection rule exists.

### 9.2. `@Qualifier`: choosing by name/label

```java
@Service
public class AlertService {

    private final NotificationChannel channel;

    public AlertService(
            @Qualifier("smsNotificationChannel")
            NotificationChannel channel) {
        this.channel = channel;
    }
}
```

Qualifiers specify the required implementation.

### 9.3. `@Order`: receiving multiple beans and sorting them

```java
@Service
public class NotificationPipeline {

    private final List<NotificationChannel> channels;

    public NotificationPipeline(List<NotificationChannel> channels) {
        this.channels = channels;
    }
}
```

Here the service receives a collection of multiple matching channels. `@Order` decides element order when Spring sorts the list.

### 9.4. Summary table

| Tool | When to use? | Example |
| --- | --- | --- |
| `@Primary` | Multiple beans share a type, want one as default | Email as the default channel |
| `@Qualifier` | Want to specify an exact bean | Service sending SMS |
| `@Order` / `Ordered` | Want multiple beans processed sequentially | Discount rule pipeline |
| `@DependsOn` | Need another bean initialized first | Initializer before a service needing side effects |

## 10. `ObjectProvider.orderedStream()` to retrieve beans in order

You do not always want to inject the entire list directly in the constructor. `ObjectProvider<T>` allows retrieving beans on demand:

```java
import java.util.List;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class RuleExecutor {
    private final ObjectProvider<DiscountRule> rules;

    public RuleExecutor(ObjectProvider<DiscountRule> rules) {
        this.rules = rules;
    }

    public List<DiscountRule> orderedRules() {
        return rules.orderedStream().toList();
    }
}
```

`orderedStream()` asks Spring to supply beans using the order comparator. The regular `stream()` method should not be assumed sorted by `@Order`; when order matters, call `orderedStream()` or sort with an appropriate comparator yourself.

An example of immediate use:

```java
rules.orderedStream().forEach(rule -> {
    // Execute each rule in order
});
```

This API is useful when:

- You want to defer bean resolution until needed.
- You want to retrieve a set of beans from a provider and sort them by order.
- You want to use multiple implementations without directly injecting a fixed `List`.

## 11. Sorting collections with a comparator when needed

Outside autowiring, you can proactively sort collections in Java.

Spring provides `OrderComparator` and `AnnotationAwareOrderComparator`:

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.core.annotation.AnnotationAwareOrderComparator;

List<DiscountRule> ordered = new ArrayList<>(rules);
AnnotationAwareOrderComparator.sort(ordered);
```

`AnnotationAwareOrderComparator` understands `@Order` metadata and other order sources supported by the comparator. The basic `OrderComparator` works with `Ordered`; when annotations need to be read, choose the annotation-aware comparator.

If you want complete control:

```java
ordered.sort(
    Comparator.comparingInt(DiscountRule::customPriority)
);
```

In this example, `customPriority()` is a method defined by the `DiscountRule` interface. This is an application-specific rule; it does not automatically use `@Order`.

Do not both use `@Order` and manually sort by another property without documenting which order is the final source of truth.

## 12. Common extension points: `@Order` in Spring Boot

`@Order` is not limited to business bean lists. Several Spring and Spring Boot extension points also use order comparators to determine execution order.

### 12.1. `CommandLineRunner` and `ApplicationRunner`

Spring Boot invokes `CommandLineRunner` and `ApplicationRunner` beans after the application context starts up. You can use `@Order` to determine the invocation order of runners:

```java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class StartupTasks {

    @Bean
    @Order(1)
    CommandLineRunner loadReferenceData() {
        return args -> System.out.println("1. Load reference data");
    }

    @Bean
    @Order(2)
    CommandLineRunner verifyConfiguration() {
        return args -> System.out.println("2. Verify configuration");
    }
}
```

In this configuration, the runner with order 1 is called before the runner with order 2. This is the **runner invocation order after context startup**, not the object instantiation order of the two runners.

If the second runner requires data produced by the first runner, consider designing a dependency or a dedicated initialization flow so that relationship is explicit. Ordering runners alone may not suffice to express every operational prerequisite.

### 12.2. Spring AOP aspects

If an application has multiple aspects applying to the same join point, `@Order` can help determine precedence among aspects:

```java
@Aspect
@Component
@Order(1)
public class SecurityAspect {
    // Security check advice
}
```

```java
@Aspect
@Component
@Order(2)
public class LoggingAspect {
    // Logging advice
}
```

The exact execution order of before/after/around advice follows nesting rules: a higher-precedence aspect wraps around a lower-precedence aspect. Do not naively assume every log line runs in ascending order; consider the advice type and position in the call stack.

### 12.3. Infrastructure extension points

Spring has many ordered interfaces and callbacks, such as certain types of `BeanFactoryPostProcessor`, `BeanPostProcessor`, event listeners, or strategies. Each extension point can have its own collection and sorting rules. Check the documentation/API of that extension point to see whether it honors `Ordered` or `@Order`.

**Not every list in Spring is automatically sorted by `@Order`.** The annotation only takes effect where the corresponding mechanism reads and applies order metadata.

## 13. Equal orders and default values

For example:

```java
@Component
@Order(10)
public class FirstRule implements DiscountRule {
}

@Component
@Order(10)
public class SecondRule implements DiscountRule {
}
```

Both beans have the same order. The comparator has no business information to decide which bean should run first. In some cases, a stable sort may preserve input order, yet input order can depend on registration or bean discovery mechanisms.

If the order between two rules matters, assign distinct orders:

```java
@Order(10)
class FirstRule { }

@Order(20)
class SecondRule { }
```

If two rules are independent and need no before/after relationship, sharing an order can be acceptable. However, do not test or build business logic relying on accidental ordering among equal-priority elements.

## 14. How to verify bean ordering in an application

### 14.1. Printing the list from the constructor

In a service receiving a list:

```java
public PricingService(List<DiscountRule> rules) {
    this.rules = rules;

    rules.forEach(rule ->
        System.out.println(rule.getClass().getSimpleName())
    );
}
```

This is a simple way to observe injected implementations and their current order. If a bean is wrapped in a proxy, `getSimpleName()` may display the proxy class name; when the target class must be identified, use appropriate AOP utilities.

### 14.2. Using tests to verify business-critical order

Example with Spring Boot Test:

```java
@SpringBootTest
class PricingServiceTest {

    @Autowired
    private List<DiscountRule> rules;

    @Test
    void rulesAreOrdered() {
        assertThat(rules)
            .extracting(rule -> rule.getClass())
            .containsSubsequence(
                MemberDiscountRule.class,
                CampaignDiscountRule.class
            );
    }
}
```

This test illustrates the idea; if beans are proxied, inspect target classes with appropriate tools or test **execution behavior** instead of comparing runtime classes directly. You can also use fake rules that record invocation order to verify the pipeline.

A behavior-based test less sensitive to proxy types:

```java
@Test
void appliesRulesInConfiguredOrder() {
    BigDecimal result = pricingService.calculate(new BigDecimal("100.00"));

    assertThat(result).isEqualByComparingTo("85.00");
}
```

This result test only applies if the discount rules in the example use the stated calculations and no other rules exist in the context.

## 15. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "Order 100 runs before order 1." | Smaller numbers have precedence; 1 comes before 100. |
| "`@Order(1)` makes the bean initialize first." | It sorts beans at supported extension points; it does not generally control singleton initialization order. |
| "`@Order` selects the default bean to inject for an interface." | Use `@Primary` or `@Qualifier` for single-bean selection; `@Order` is for sorting multiple beans. |
| "Every `Set` and `Map` preserves annotation order." | Do not rely on Set/Map iteration order; use List or `orderedStream()` when sequence matters. |
| "Only classes can declare order." | `@Order` can be placed on both classes and appropriate `@Bean` methods. |
| "`Ordered` and `@Order` are always treated equally." | When an instance implements `Ordered`, `getOrder()` takes precedence over the annotation in standard comparators. |
| "Every list in Spring sorts automatically." | Only mechanisms using an order comparator apply order metadata. |
| "Two beans with equal order always have a deterministic business order." | If order matters, use distinct values or an explicit tie-breaker rule. |

## 16. Practice exercises

### Exercise 1 — Creating three implementations

Create an interface:

```java
public interface MessageHandler {
    void handle(String message);
}
```

Create three beans `EmailHandler`, `SmsHandler`, and `LogHandler` with `@Component` and orders 20, 10, and 30 respectively. Inject `List<MessageHandler>` into `MessageDispatcher` and print the handler names.

**Requirement:** predict the order before running, then compare with the actual output.

### Exercise 2 — Trying `Ordered`

Replace one implementation with a class implementing `Ordered`, returning `getOrder() = 5`. Also attach `@Order(100)` to the class.

**Question:** which value will the comparator use? Why?

### Exercise 3 — Comparing List, Set, and Map

Inject the same set of `MessageHandler`s into:

```java
List<MessageHandler>
Set<MessageHandler>
Map<String, MessageHandler>
```

Observe iteration order. Explain why List is the better choice when processing order is mandatory, whereas Map is useful for looking up by bean name.

### Exercise 4 — Distinguishing order from startup sequence

Create two components whose constructors print logs and attach `@Order(1)` and `@Order(2)`. Observe startup logs. Then inject both into a `List` and print the list.

**Question:** why is constructor log order not proof of list order?

### Exercise 5 — Ordering startup runners

Declare three `CommandLineRunner` beans via `@Bean` with orders 30, 10, and 20. Log when each runner is invoked.

**Requirement:** determine the execution order and explain why `@Order` takes effect here.

### Exercise 6 — Choosing one bean or multiple beans?

Given two `PaymentGateway` implementations: `CardGateway` and `BankGateway`.

- A `PaymentService` must use only one configured gateway: choose `@Qualifier` or `@Primary`.
- A `PaymentAuditPipeline` must invoke both gateways sequentially: inject `List<PaymentGateway>` and use `@Order`.

Explain why the two requirements call for two different mechanisms.

## 17. Key takeaways when building bean pipelines

`Ordered` and `@Order` tell Spring **a bean's precedence when a corresponding mechanism needs to sort multiple beans**. Smaller values come first; if omitted, the default order has the lowest precedence. For collection injection, `List<T>` and arrays are suitable choices when sequence matters; with `ObjectProvider`, use `orderedStream()` when an ordered stream is needed.

Choose the right tool for the right question: `@Order` to sort multiple beans, `@Primary`/`@Qualifier` to pick which bean to inject, and `@DependsOn` or dependency injection to express initialization relationships. When order affects business outcomes, set explicit orders and test the pipeline's actual behavior.
