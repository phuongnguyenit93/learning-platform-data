# Filtering by Event Properties

## Objectives

After this lesson, you can distinguish filtering events by type from filtering events by internal data, write SpEL conditions using `@EventListener(condition = "...")`, access event payloads and metadata, handle nested properties or null values safely, and verify that listeners only run when the event satisfies the condition.

## 1. What Is Filtering by Event Properties?

Spring Application Events allow one publisher to emit an event and multiple listeners to be interested in that event. Normally, Spring selects listeners based on the event type. However, sometimes multiple events share the same type, yet a listener only needs to process certain events that satisfy business criteria.

For example, an application publishes `OrderPlaced` for every order. Listeners might only want to receive:

- Orders coming from the `WEB` channel.
- Orders with a total amount of 50,000 or more.
- Orders from VIP customers.
- Orders using the `SPRING` promo code.
- Orders carrying the `priority` tag.

This is **filtering by event properties**. Spring still receives the event and identifies matching listeners by type first. Then, a runtime condition decides whether the listener method is invoked.

For annotation-based listeners, the most direct approach is using the `condition` attribute of `@EventListener`. The value of `condition` is a Spring Expression Language (SpEL) expression.

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void handleWebOrder(OrderPlaced event) {
    System.out.println("Web order: " + event.orderId());
}
~~~

In this example, the listener only runs when the `channel` property of the payload equals `WEB`.

## 2. Distinguishing Filtering by Type and Filtering by Properties

The two filtering steps answer two different questions:

| Mechanism | Question | Example |
|---|---|---|
| Event type | Does the listener accept this kind of event? | Accept only `OrderPlaced` |
| Event properties | Does this specific event satisfy the condition? | Accept only `OrderPlaced` with `channel = WEB` |

The event type is usually inferred from the method parameter:

~~~java
@EventListener
public void handleOrder(OrderPlaced event) {
    // Receive matching OrderPlaced
}
~~~

If a listener needs to handle multiple event types, you can declare `classes`:

~~~java
@EventListener(classes = {
        OrderPlaced.class,
        OrderCancelled.class
})
public void handleOrderLifecycle() {
    System.out.println("Order lifecycle event");
}
~~~

With multiple event types, if the method has a parameter, its type must be a common supertype compatible with the declared events. The `condition` attribute adds a runtime data-filtering step after the event type has matched.

Do not use a `condition` expression as a substitute for declaring the proper event type. Choosing explicit event types lets Spring eliminate unrelated listeners right at the dispatch step.

## 3. What Data Can SpEL Access?

Spring evaluates `condition` inside a dedicated evaluation context for event listeners. Key variables include:

| Variable | Meaning | Example |
|---|---|---|
| `#root.event` or `event` | Actual `ApplicationEvent` passed into the listener | `#root.event` |
| `#root.args` or `args` | Array of arguments passed to the listener method | `#root.args[0]` |
| `#a0`, `#p0` | First parameter, zero-indexed | `#a0.channel()` |
| `#a1`, `#p1` | Second parameter | `#a1` |
| `#paramName` | Parameter by name if retained in bytecode | `#order.channel()` |

For a method accepting a single payload:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void handle(OrderPlaced order) {
    // ...
}
~~~

`#a0` references the `OrderPlaced` object passed into the method. Using the `#a0` index does not depend on whether the compiler retains parameter names.

If you want to use a name like `#order`, enable the `-parameters` compiler option so parameter names are present in bytecode. Otherwise, Spring may not be able to resolve that name.

### Distinguishing #a0 from #root.event

When a publisher emits a plain object, Spring may wrap that object in `PayloadApplicationEvent`. In this case:

- `#a0` references the payload received by the listener method.
- `#root.event` references the actual `ApplicationEvent`, which may be the `PayloadApplicationEvent` containing the payload.

If the listener receives a custom class extending `ApplicationEvent`, `#a0` is typically that event instance itself. Use `#a0` when your goal is to read properties of the listener parameter; use `#root.event` when you need to access metadata of the `ApplicationEvent`.

## 4. Writing Conditions on Simple Properties

SpEL supports standard comparison and logical operators. Examples:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void handleWeb(OrderPlaced event) {
}

@EventListener(condition = "#a0.total() >= 50000")
public void handleHighValue(OrderPlaced event) {
}

@EventListener(condition = "#a0.vip() == true")
public void handleVip(OrderPlaced event) {
}
~~~

Some common condition forms:

~~~java
// Equality comparison
@EventListener(condition = "#a0.channel() == 'WEB'")

// Inequality comparison
@EventListener(condition = "#a0.channel() != 'STORE'")

// Numeric comparison
@EventListener(condition = "#a0.total() > 100000")

// Combining with AND
@EventListener(condition =
        "#a0.channel() == 'WEB' and #a0.total() >= 50000")

// Combining with OR
@EventListener(condition =
        "#a0.channel() == 'WEB' or #a0.vip()")
~~~

Prefer expressions that return a clear boolean. According to the Spring API, the listener is invoked when the expression returns `true` or one of the strings `"true"`, `"on"`, `"yes"`, `"1"`. The default `condition` is an empty string, meaning no additional filtering is applied and the listener is processed whenever the event type matches.

## 5. Filtering Nested Properties, Collections, and Null Values

Events often contain nested objects or collections. SpEL can access these members via object accessors or methods.

### Nested Properties

For example, a payload containing customer information:

~~~java
record Customer(boolean vip) {
}

record OrderPlaced(String orderId, Customer customer) {
}
~~~

You can filter orders from VIP customers:

~~~java
@EventListener(condition = "#a0.customer() != null and #a0.customer().vip()")
public void handleVipOrder(OrderPlaced event) {
    System.out.println("VIP: " + event.orderId());
}
~~~

The expression checks that `customer` is not null before reading `vip`. SpEL's `and` operator uses conditional evaluation, so the right-hand side does not need to be evaluated when the left-hand side is false.

### Collections

If an event contains a set of tags:

~~~java
record OrderPlaced(String orderId, Set<String> tags) {
}
~~~

You can filter events carrying the `priority` tag:

~~~java
@EventListener(condition =
        "#a0.tags() != null and #a0.tags().contains('priority')")
public void handlePriorityOrder(OrderPlaced event) {
    System.out.println("Priority: " + event.orderId());
}
~~~

### Potentially Null Values

Always check for null before accessing properties or calling methods on an optional value:

~~~java
@EventListener(condition =
        "#a0.couponCode() != null and #a0.couponCode() == 'SPRING'")
public void handleSpringCoupon(OrderPlaced event) {
    // ...
}
~~~

If the null check is omitted, the expression can fail when the event has no `couponCode`. For nested data, check each potentially null level before accessing the next level.

## 6. SpEL Conditions Should Be Simple and Easy to Test

`condition` is evaluated while Spring decides whether to invoke the listener. Therefore, keep expressions short, deterministic, and inexpensive.

Use `condition` for:

- Comparing event values.
- Checking business state or category.
- Combining a few boolean conditions.
- Checking the presence of an optional data field.
- Checking a tag or value in a small collection.

Avoid putting into `condition`:

- HTTP calls or database queries.
- Mutating object state.
- Performing business logic with side effects.
- Iterating over large collections or running expensive computations.
- Depending on time or constantly changing external state.

If a condition is complex, has many branches, or requires querying data, consider computing a clear property before publishing the event, or using a listener that receives the event and delegates to a service for business processing. This keeps conditions readable and easy to test.

Event payloads should be immutable after publishing. If the publisher mutates the object while listeners are processing it, filtering outcomes can become unpredictable, especially when listeners run asynchronously.

## 7. How Filtering in @EventListener Differs from Filtering Inside the Listener

You can write the condition yourself inside the method body:

~~~java
@EventListener
public void handle(OrderPlaced event) {
    if (!"WEB".equals(event.channel())) {
        return;
    }

    System.out.println("Web order: " + event.orderId());
}
~~~

This approach is still valid. However, the listener is invoked for every event of that type and then checks the condition itself.

Using `condition`:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void handle(OrderPlaced event) {
    System.out.println("Web order: " + event.orderId());
}
~~~

With `condition`, Spring decides whether to invoke the method right inside the event handling mechanism. The method only contains logic for events that already satisfy the condition.

| Criterion | `condition` | `if` inside method |
|---|---|---|
| Filtering time | Before invoking the listener method | After the method has been invoked |
| Declaration | SpEL in annotation | Java code |
| Suitable for | Short conditions readable right on the listener | Multi-step logic or needing to call services |
| Debugging | Requires checking the SpEL expression | Can set breakpoints in Java |
| Testing | Test the condition and whether the method is called | Test processing branches inside the method |

For `ApplicationListener` implementing the interface, you can use `if` inside `onApplicationEvent()`. The `condition` annotation attribute is a convenient option for `@EventListener` methods.

## 8. Complete Example with Java 17 and Spring Framework 6.2.12

This example publishes two `OrderPlaced` events of the same type but with different data. The first event is a high-value `WEB` order from a VIP customer, with the `SPRING` coupon code and the `priority` tag. The second event is a low-value in-store order.

Five listeners use `condition` to filter individual properties. The second event is still published, yet none of the listeners in the example are invoked for it.

### Project Structure

~~~text
event-property-filter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── EventPropertyFilterDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-property-filter-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                    <mainClass>demo.EventPropertyFilterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### EventPropertyFilterDemo.java

~~~java
package demo;

import java.util.Set;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventPropertyFilterDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            context.publishEvent(new OrderPlaced(
                    "DH-7701",
                    "WEB",
                    75_000,
                    new Customer(true),
                    "SPRING",
                    Set.of("priority", "gift")));

            context.publishEvent(new OrderPlaced(
                    "DH-7702",
                    "STORE",
                    20_000,
                    new Customer(false),
                    null,
                    Set.of("standard")));
        }
    }

    record Customer(boolean vip) {
    }

    record OrderPlaced(
            String orderId,
            String channel,
            long total,
            Customer customer,
            String couponCode,
            Set<String> tags) {
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        EventListeners eventListeners() {
            return new EventListeners();
        }
    }

    static class EventListeners {

        @EventListener(condition = "#a0.channel() == 'WEB'")
        @Order(1)
        public void handleWebOrder(OrderPlaced event) {
            System.out.println("WEB order: " + event.orderId());
        }

        @EventListener(
                condition = "#a0.channel() == 'WEB' and #a0.total() >= 50000")
        @Order(2)
        public void handleHighValueWebOrder(OrderPlaced event) {
            System.out.println("High-value web order: " + event.orderId());
        }

        @EventListener(
                condition = "#a0.customer() != null and #a0.customer().vip()")
        @Order(3)
        public void handleVipOrder(OrderPlaced event) {
            System.out.println("VIP order: " + event.orderId());
        }

        @EventListener(
                condition = "#a0.couponCode() != null and #a0.couponCode() == 'SPRING'")
        @Order(4)
        public void handleSpringCoupon(OrderPlaced event) {
            System.out.println("Spring coupon order: " + event.orderId());
        }

        @EventListener(
                condition = "#a0.tags() != null and #a0.tags().contains('priority')")
        @Order(5)
        public void handlePriorityOrder(OrderPlaced event) {
            System.out.println("Priority order: " + event.orderId());
        }
    }
}
~~~

### Running the Program

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Output:

~~~text
WEB order: DH-7701
High-value web order: DH-7701
VIP order: DH-7701
Spring coupon order: DH-7701
Priority order: DH-7701
~~~

No line is printed for `DH-7702` because this event has channel `STORE`, low total, non-VIP customer, null coupon, and does not have the `priority` tag.

### Execution Flow Analysis

1. `AnnotationConfigApplicationContext` initializes `AppConfig` and registers `EventListeners` as a bean.
2. `EventListenerMethodProcessor` detects five methods annotated with `@EventListener`.
3. The publisher emits `OrderPlaced` with `orderId` `DH-7701`.
4. Spring identifies the listeners accepting type `OrderPlaced` and then evaluates each listener's `condition`.
5. All five conditions return `true` for `DH-7701`, so the five methods are invoked in `@Order` sequence.
6. The publisher emits `DH-7702`. The corresponding conditions return `false`, so these listener methods are not invoked.
7. The context is closed after both events have been processed.

Point to remember: `condition` does not cancel the event and does not prevent other listeners from processing that event. It only decides whether the listener method under evaluation is invoked.

## 9. How to Test Event Filters

A good test suite should include at least two cases:

- An event satisfies the condition and the listener must be invoked.
- An event does not satisfy the condition and the listener is not invoked.

You can test by injecting a recorder listener with a counter or a list of received events. Then publish each event and assert the results.

Example testing with a counter:

~~~java
AtomicInteger webOrderCount = new AtomicInteger();

@EventListener(condition = "#a0.channel() == 'WEB'")
public void handleWebOrder(OrderPlaced event) {
    webOrderCount.incrementAndGet();
}
~~~

After publishing one `WEB` event and one `STORE` event, the expected result is:

~~~java
assertEquals(1, webOrderCount.get());
~~~

Add boundary test cases:

- Optional properties are null.
- Monetary amount equals the threshold exactly.
- Empty or null collection.
- String values with different uppercase/lowercase casing.
- Event with missing nested properties.
- Multiple listeners with independent conditions receiving the same event.

If using `@Async`, wait for the listener to complete before checking the counter. With default synchronous listeners, you can assert immediately after `publishEvent` returns.

## 10. Common Mistakes

### Using a parameter name when the compiler does not retain parameter names

A condition like `#event.channel()` may fail to resolve if parameter names are not present in bytecode. Use `#a0.channel()` or `#p0.channel()`, or configure the compiler with `-parameters`.

### Confusing #root.event with the payload

When a publisher emits a plain object, Spring may wrap it in `PayloadApplicationEvent`. `#root.event` references the `ApplicationEvent` wrapper, whereas `#a0` references the payload parameter the method receives. Choose the right object before accessing properties.

### Skipping null checks

Accessing `#a0.couponCode().length()` when `couponCode` is null can cause the expression to fail. Check for null first before accessing properties or calling methods.

### Writing overly complex conditions

A long expression with many calls and branches makes the listener hard to read and debug. Extract complex business logic into a service or compute the property to filter on before publishing the event.

### Thinking condition blocks the entire event

A `false` condition only prevents the corresponding listener method from being invoked. The event is still published and other listeners can still process it.

### Using condition to perform side effects

A condition should only answer whether the event matches. Do not update databases, send HTTP requests, or mutate data inside a SpEL expression.

### Expecting async listeners to finish before publishEvent returns

With `@Async` listeners, the publisher does not wait for background work to finish. Design synchronization and separate testing for asynchronous processing.

### Using condition instead of security controls

`condition` is an in-application event handling filter. Do not use it as a security boundary or a replacement for service/API-layer authorization.

## 11. Best Practices

- Use event types to select listener groups, then use `condition` to filter runtime properties.
- Prefer `#a0` or `#p0` when you want to avoid depending on parameter names in bytecode.
- Write conditions that return an explicit boolean.
- Check for null before reading nested properties or calling methods.
- Keep payloads immutable and include the data needed by listeners.
- Keep conditions short, fast, and free of side effects.
- Use `@Order` when listener invocation order has clear meaning.
- Test matching cases, non-matching cases, and boundary data.
- If a condition requires querying a database or calling an external system, move that part to a service.
- If filtering at the publisher level is needed to avoid creating unnecessary events, decide whether to publish in business logic before calling `publishEvent`.

## 12. Key Takeaways

Filtering by event properties is an additional runtime check after Spring has identified matching listeners by event type. With `@EventListener`, the `condition` attribute takes a SpEL expression and only invokes the method when the expression returns a true value.

Use `#a0` or `#p0` to access the first parameter, `#root.args` to access the argument array, and `#root.event` to access the `ApplicationEvent`. You can filter on strings, numbers, nested properties, null values, and collections. Keep expressions simple, test both matching and non-matching events, and keep complex business logic in services so listeners remain easy to understand.

## Official References

- [EventListener — Spring Framework 6.2.12 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [Additional Capabilities of the ApplicationContext — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Expression Language (SpEL) — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/core/expressions.html)
- [EventListenerMethodProcessor — Spring Framework 6.2.12 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html)