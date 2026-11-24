# The condition Attribute in Spring Framework's @EventListener

## Objectives

`@EventListener` allows a bean to receive application events through a method. The `condition` attribute adds a filtering step using the Spring Expression Language (SpEL): Spring only invokes the listener method when the expression evaluates to `true`.

The condition is applied individually to each listener method whose event type matches. Therefore, multiple listeners can receive the same event type while only processing cases that match each listener's criteria.

This lesson focuses on how to write expressions, access event arguments, filter POJO payloads and custom `ApplicationEvent` classes, combine multiple listeners, and understand the limitations when using conditions in real-world applications.

After this lesson, you will be able to:

- Write `@EventListener(condition = "...")` using SpEL.
- Access listener arguments reliably using `#a0` or `#p0`.
- Use conditions with POJO payloads and classes extending `ApplicationEvent`.
- Distinguish the event type matching step from the condition evaluation step.
- Combine multiple listeners, `@Order`, null-safe expressions, and nested properties.
- Test accepted cases, filtered-out cases, and expression errors.

## 1. Condition as a Listener-Side Filter

When an object is published, Spring first determines which listeners match the event type and method signature. For a method annotated with `@EventListener`, if `condition` is declared, Spring evaluates the SpEL expression before invoking the method.

Overview of the processing flow:

1. The publisher calls `publishEvent(event)`.
2. Spring finds listeners whose event type is compatible with the actual event.
3. For each matching `@EventListener` method, Spring prepares the method arguments.
4. Spring evaluates `condition` in the listener's evaluation context.
5. If the expression returns `true`, the method is invoked. If it returns `false`, that method is skipped.
6. Other listeners continue to be evaluated independently according to the dispatch configuration.

For example, a `PriceQuote` can be sent to three listeners: a listener for high-value quotes, a listener for the Vietnam region, and a listener that logs every quote. The conditions of the first two listeners can differ; the listener that logs every quote needs no condition.

**Condition does not filter events at the publisher and does not block other listeners.** It only decides whether a specific listener method is invoked. If you need to reject a business action or check access permissions, implement that rule in the application/domain service; do not use `condition` as a security boundary.

## 2. Basic Syntax

The `condition` attribute takes a SpEL expression string:

```java
@EventListener(condition = "#a0.amount >= 100")
void onHighValueQuote(PriceQuote quote) {
    // Only process quotes whose amount satisfies the condition.
}
```

The expression must return a boolean. A value of `true` allows Spring to invoke the method; `false` causes the method to be skipped.

Commonly used operators:

| Category | Operator / Syntax | Meaning |
|---|---|---|
| Comparison | `==`, `!=`, `>`, `>=`, `<`, `<=` | Compare values |
| Logical | `and`, `or`, `not`, `&&`, `||`, `!` | Combine or negate conditions |
| Null | `== null`, `!= null` | Check for null values |
| String | `#a0.region == 'VN'` | Compare strings |
| Static type | `T(java.math.BigDecimal)` | Reference a Java class |
| Method call | `#a0.amount.compareTo(...)` | Call a method on an object |

Combined example:

```java
@EventListener(
    condition = "#a0.region == 'VN' and #a0.amount >= 100"
)
void onVietnamHighValueQuote(PriceQuote quote) {
    // Only process quotes from VN with a value of 100 or more.
}
```

When comparing monetary values with `BigDecimal`, use `compareTo` instead of direct numeric comparison operators to avoid confusion between arithmetic comparison and decimal representation:

```java
@EventListener(
    condition = "#a0.amount.compareTo(T(java.math.BigDecimal).valueOf(100)) >= 0"
)
void onHighValueQuote(PriceQuote quote) {
}
```

`compareTo` returns a negative number, 0, or a positive number. The expression above selects quotes whose amount is greater than or equal to 100.

## 3. Accessing Events and Method Parameters in SpEL

Spring provides reference variables for `@EventListener` expressions:

| Variable | Content |
|---|---|
| `#root.event` | The application event currently being processed |
| `#root.args` | Array of resolved arguments for the listener method |
| `#a0` | The first argument of the method |
| `#a1` | The second argument, if the method has a second argument |
| `#p0` | Alias for the first position, equivalent to `#a0` |
| `#p1` | Alias for the second position, equivalent to `#a1` |

For a single-parameter listener, `#a0` and `#p0` are short, positionally stable ways to reference the argument. You can use a parameter name such as `#quote` when Spring can discover parameter names from compilation metadata; if you want the expression not to depend on compiler configuration, prefer `#a0` or `#p0`.

Example:

```java
@EventListener(condition = "#a0.region == 'VN'")
void onVietnamQuote(PriceQuote quote) {
}

@EventListener(condition = "#root.args[0].amount >= 100")
void onLargeQuote(PriceQuote quote) {
}
```

With a custom event extending `ApplicationEvent`, the method can receive the event class itself and the condition accesses properties of the event:

```java
@EventListener(condition = "#a0.quantity < 0")
void onNegativeInventory(InventoryAdjustedEvent event) {
    // Only invoked when the adjusted quantity is negative.
}
```

If you need to inspect metadata of the original event, `#root.event` is the application event dispatched by Spring. With a custom `ApplicationEvent`, you can access the source via the `source` property or call `getSource()` using appropriate SpEL syntax. When a POJO is published, the root event is the `PayloadApplicationEvent` wrapper, while `#a0` in a method accepting the payload is the resolved payload itself.

## 4. Property Access and Null Checks

SpEL accesses Java properties through accessors. For a JavaBean, the `amount` property typically maps to the getter `getAmount()`; the `region` property maps to `getRegion()`.

```java
public class PriceQuote {
    private final BigDecimal amount;
    private final String region;

    public PriceQuote(BigDecimal amount, String region) {
        this.amount = amount;
        this.region = region;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getRegion() {
        return region;
    }
}
```

An expression can combine multiple properties:

```java
@EventListener(
    condition = "#a0.customer != null and #a0.customer.active == true"
)
void onActiveCustomerQuote(PriceQuote quote) {
}
```

Always check for null before accessing nested properties. SpEL uses short-circuit logical operators, so the right-hand side of `and` does not need to be evaluated when the left-hand side is already false.

It can be written more concisely:

```java
@EventListener(
    condition = "#a0.customer?.active == true"
)
void onActiveCustomerQuote(PriceQuote quote) {
}
```

The safe navigation operator `?.` returns null if the object on the left is null, helping avoid errors when accessing properties on null. Choose a style that is clear and consistent across your codebase.

Avoid writing overly long conditions with many method calls and nested branches. If a rule requires multiple steps or carries important business meaning, move the logic into a separately testable policy/service; the condition should only express a short filter.

## 5. Filtering POJO Payloads and Custom ApplicationEvent

Spring supports two common event forms.

### POJO Wrapped in PayloadApplicationEvent

Since Spring Framework 4.2, a publisher can emit a plain Java object that does not extend `ApplicationEvent`:

```java
context.publishEvent(new PriceQuote(101L, new BigDecimal("150.00"), "VN"));
```

Spring wraps the POJO in `PayloadApplicationEvent<PriceQuote>`. An `@EventListener` method with a `PriceQuote` parameter can receive the payload directly, and the condition accesses the payload via `#a0`:

```java
@EventListener(condition = "#a0.region == 'VN'")
void onVietnamQuote(PriceQuote quote) {
}

@EventListener(
    condition = "#a0.amount.compareTo(T(java.math.BigDecimal).valueOf(100)) >= 0"
)
void onHighValueQuote(PriceQuote quote) {
}
```

If the listener needs to read the wrapper itself, such as `getSource()` on `PayloadApplicationEvent`, it can declare a parameter matching the wrapper. In that case, be clear about the method argument type that the condition will receive.

### Custom Event Extending ApplicationEvent

A custom event can contain business properties and a source:

```java
public class InventoryAdjustedEvent extends ApplicationEvent {
    private final String warehouse;
    private final int quantityDelta;

    public InventoryAdjustedEvent(
            Object source,
            String warehouse,
            int quantityDelta) {
        super(source);
        this.warehouse = warehouse;
        this.quantityDelta = quantityDelta;
    }

    public String getWarehouse() {
        return warehouse;
    }

    public int getQuantityDelta() {
        return quantityDelta;
    }
}
```

The condition can filter directly on the event:

```java
@EventListener(
    condition = "#a0.warehouse == 'HCM' and #a0.quantityDelta < 0"
)
void onHcmStockReduction(InventoryAdjustedEvent event) {
}
```

Here `#a0` is the custom event object. It is not a payload wrapper because the event already extends `ApplicationEvent`.

| Characteristic | Custom ApplicationEvent | POJO payload |
|---|---|---|
| Base class | Extends `ApplicationEvent` | Plain Java object |
| Dispatched object | The custom event itself | `PayloadApplicationEvent<T>` |
| `@EventListener` can accept | Custom event class | Payload type |
| Condition on `#a0` | Properties of the custom event | Properties of the payload if the method accepts the payload |
| Source | Passed into `super(source)` | Source of the wrapper created by Spring when published via context |
| Listener interface | `ApplicationListener<CustomEvent>` | `ApplicationListener<PayloadApplicationEvent<T>>` if you want to receive the wrapper |

You cannot declare `ApplicationListener<PriceQuote>` when `PriceQuote` is just a POJO because the generic `E` must extend `ApplicationEvent`. For a POJO, use `@EventListener` accepting the payload or `ApplicationListener<PayloadApplicationEvent<PriceQuote>>` accepting the wrapper.

## 6. Condition Is Evaluated After Event Type Matching

Condition does not replace event type resolution. Spring first needs to know whether the listener method can accept that event; only then does the condition decide whether the method is invoked.

For example, two methods both accepting `PriceQuote`:

```java
@EventListener(condition = "#a0.amount >= 100")
void onLargeQuote(PriceQuote quote) {
}

@EventListener(condition = "#a0.region == 'VN'")
void onVietnamQuote(PriceQuote quote) {
}
```

For a quote with amount 150 and region VN, both conditions are true and both methods can be invoked. With amount 50 and region VN, only the second method is invoked. With amount 150 and region US, only the first method is invoked.

One method's condition does not alter another method's condition. Nor does it stop the event from continuing to other listeners.

You can use `@Order` to order listener methods when multiple methods process the same event. This ordering is useful when synchronous listeners have a clear ordering dependency, but it should not be used to build a complex business chain or to rely on completion order of asynchronous tasks.

## 7. Runnable Example with Java 17 and Spring Framework 6.2

The following example uses the `PriceQuote` POJO and two listener methods. The first listener only accepts quotes with amount 100 or higher; the second listener only accepts quotes in the VN region. `#a0` is used so the condition does not depend on compiler parameter names.

Structure:

```text
event-listener-condition-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── EventListenerConditionDemo.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-listener-condition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.EventListenerConditionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/demo/EventListenerConditionDemo.java**

```java
package demo;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventListenerConditionDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            QuotePublisher publisher = context.getBean(QuotePublisher.class);

            publisher.publish(new PriceQuote(
                    101L, new BigDecimal("150.00"), "VN"));
            publisher.publish(new PriceQuote(
                    102L, new BigDecimal("50.00"), "VN"));
            publisher.publish(new PriceQuote(
                    103L, new BigDecimal("200.00"), "US"));
            publisher.publish(new PriceQuote(
                    104L, new BigDecimal("80.00"), "US"));
        }
    }

    @Configuration
    static class AppConfig {

        @Bean
        QuotePublisher quotePublisher(ApplicationEventPublisher publisher) {
            return new QuotePublisher(publisher);
        }

        @Bean
        QuoteListeners quoteListeners() {
            return new QuoteListeners();
        }
    }

    static class QuotePublisher {
        private final ApplicationEventPublisher publisher;

        QuotePublisher(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void publish(PriceQuote quote) {
            publisher.publishEvent(quote);
        }
    }

    public static class PriceQuote {
        private final long quoteId;
        private final BigDecimal amount;
        private final String region;

        public PriceQuote(long quoteId, BigDecimal amount, String region) {
            this.quoteId = quoteId;
            this.amount = amount;
            this.region = region;
        }

        public long getQuoteId() {
            return quoteId;
        }

        public BigDecimal getAmount() {
            return amount;
        }

        public String getRegion() {
            return region;
        }
    }

    static class QuoteListeners {

        @EventListener(
            condition = "#a0.amount.compareTo(T(java.math.BigDecimal).valueOf(100)) >= 0"
        )
        @Order(1)
        void onHighValueQuote(PriceQuote quote) {
            System.out.printf(
                    "HIGH: quote=%d amount=%s%n",
                    quote.getQuoteId(),
                    quote.getAmount().toPlainString()
            );
        }

        @EventListener(condition = "#a0.region == 'VN'")
        @Order(2)
        void onVietnamQuote(PriceQuote quote) {
            System.out.printf(
                    "VN: quote=%d region=%s%n",
                    quote.getQuoteId(),
                    quote.getRegion()
            );
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Exact stdout:

```text
HIGH: quote=101 amount=150.00
VN: quote=101 region=VN
VN: quote=102 region=VN
HIGH: quote=103 amount=200.00
```

Result interpretation:

| Quote | Amount | Region | Listener invoked |
|---|---:|---|---|
| 101 | 150.00 | VN | HIGH and VN |
| 102 | 50.00 | VN | VN |
| 103 | 200.00 | US | HIGH |
| 104 | 80.00 | US | No listener |

Quote 104 is still published normally. It is simply that both conditions are false, so neither listener method in the class is invoked for that quote.

## 8. Combining condition with Custom ApplicationEvent

If your application already has a custom event class extending `ApplicationEvent`, `condition` can filter on properties of the event itself. For example:

```java
public class InventoryAdjustedEvent extends ApplicationEvent {
    private final String warehouse;
    private final int quantityDelta;

    public InventoryAdjustedEvent(
            Object source,
            String warehouse,
            int quantityDelta) {
        super(source);
        this.warehouse = warehouse;
        this.quantityDelta = quantityDelta;
    }

    public String getWarehouse() {
        return warehouse;
    }

    public int getQuantityDelta() {
        return quantityDelta;
    }
}
```

Listener:

```java
@Component
class InventoryListeners {

    @EventListener(
        condition = "#a0.warehouse == 'HCM' and #a0.quantityDelta < 0"
    )
    void onHcmStockReduction(InventoryAdjustedEvent event) {
        // React when the HCM warehouse reduces stock.
    }
}
```

Publisher:

```java
eventPublisher.publishEvent(
        new InventoryAdjustedEvent(this, "HCM", -3)
);
```

Here `#a0` is the `InventoryAdjustedEvent` instance. Spring has already selected the method based on the event type; the condition continues filtering by `warehouse` and `quantityDelta`. Events with a different warehouse or a non-negative delta will not invoke this method.

When the condition needs to inspect the source, you can access the event object via `#a0.source` or `#a0.getSource()` for a custom event. Only use `source` in a condition if `source` is truly a stable part of the filtering rule; avoid relying on the concrete class of the publishing service because that creates coupling between the listener and the implementation.

## 9. Condition, @Order, and Asynchronous Execution

### @Order

When multiple listeners receive the same event, `@Order` can determine the invocation order. Smaller values have higher priority:

```java
@EventListener(condition = "#a0.region == 'VN'")
@Order(1)
void notifyVietnam(PriceQuote quote) {
}

@EventListener(condition = "#a0.amount >= 100")
@Order(2)
void auditLargeQuote(PriceQuote quote) {
}
```

Each method's condition is still evaluated separately. `@Order` does not make one condition depend on a previous condition and does not change event publishing.

### @Async

You can combine `@Async` with `@EventListener` when it makes sense for the listener to run asynchronously and the application has `@EnableAsync` enabled:

```java
@Async
@EventListener(condition = "#a0.region == 'VN'")
void processVietnamQuote(PriceQuote quote) {
    // Secondary processing can run on an executor.
}
```

`condition` decides whether the method is selected to run; `@Async` decides that method execution is handed off to an executor. The publisher does not wait for the async listener to finish. Configure the executor, monitor exceptions, and avoid depending on completion order. Async does not make events durable: in-memory work can still be lost when the process stops.

## 10. Common Errors and How to Handle Them

| Error | Cause | Solution |
|---|---|---|
| Method always runs even though condition seems false | Expression always returns true or references the wrong argument | Check the actual value of `#a0` and write a clear boolean condition |
| Method does not run | Event type does not match or condition is false | Check the parameter type and the expression separately |
| SpEL error on publish | Wrong property name, method name, or data type | Use valid getters, check for null, and write tests for the expression |
| Using `#quote` fails to resolve | Parameter name metadata is unavailable | Use `#a0` or `#p0` |
| Comparing BigDecimal using double | Representation inaccuracy or unclear comparison | Use `compareTo` with a BigDecimal threshold |
| Accessing nested property when null | Left-hand side does not exist | Check for null first or use `?.` |
| Thinking condition blocks the event application-wide | Condition applies to a single listener method | Place business validation in the service/domain |
| Condition invokes heavy logic | Expression runs whenever a matching listener receives an event | Only filter simple properties; move complex policy into a separate component |
| Condition has side effects | SpEL is used as a place to execute business logic | Keep expressions pure with no state mutation |
| Async listener loses work on application shutdown | Executor is not durable storage | Use an outbox or message broker when reliable delivery is required |

If a condition has invalid syntax or accesses an invalid property, evaluation can throw an exception. With default synchronous dispatch, the exception can propagate back to the publishing thread and affect subsequent listeners. Test expressions with representative data, including null, boundary values, and non-matching cases.

## 11. Strategy for Testing Conditions

A good condition should have both true and false branches tested. For the quote example, verify:

- A quote of 150.00 in VN invokes both listeners.
- A quote of 50.00 in VN invokes only the VN listener.
- A quote of 200.00 in US invokes only the HIGH listener.
- A quote of 80.00 in US invokes neither conditional listener.

You can test through a real Spring context to confirm annotations are detected and SpEL is evaluated. Use a test listener or spy to count invocations instead of only checking logs. For async listeners, use a latch or synchronization mechanism with a timeout so tests do not rely on fixed sleep durations.

Include separate tests for:

1. Boundary conditions, such as amount equal to 100.
2. Null properties and null nested properties.
3. Unsupported regions or states.
4. Invalid condition syntax or accessing a non-existent property.
5. Multiple listeners receiving the same event and the expected `@Order`.

## 12. Design Principles

- Conditions should be short, readable, and return a clear boolean.
- Use `#a0`/`#p0` when you want positionally stable argument references.
- Do not put authorization rules or business invariants into SpEL conditions.
- Do not call external APIs, query databases, or perform side effects inside a condition.
- If an expression becomes complex, create more specific event types or extract the policy into a testable business component.
- Remember that `condition` applies individually per listener method, not as a global publisher filter.
- When durable communication across processes is needed, use integration events and an appropriate transport mechanism; `@EventListener` only handles events inside the Spring application.

## Conclusion

`@EventListener(condition = "...")` combines listener selection by event type with a SpEL expression to decide whether the method is invoked. `#a0` and `#p0` provide stable argument access; `#root.event` lets you inspect the original application event. When a POJO is published, the method can accept the payload while the internal event is wrapped by `PayloadApplicationEvent`; with a custom `ApplicationEvent`, the method accepts the event class and filters directly on its properties. Keep conditions pure, concise, and tested on both branches so listener filtering stays predictable.