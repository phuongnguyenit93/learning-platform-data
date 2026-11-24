# SpEL Access to Events and Payloads in Spring Framework

Spring supports filtering events right at the listener using the **condition** attribute of the **@EventListener** annotation. The value of `condition` is a Spring Expression Language (SpEL) expression. Spring only invokes the listener method when the expression evaluates to true.

To write conditions accurately, you need to understand which object SpEL sees. The event listener evaluation context provides the original event, the method argument array, and variables representing each parameter. The most commonly used variables are **#root.event**, **#root.args**, **#a0**, and **#p0**.

One point to remember: when publishing a plain Java object that does not extend `ApplicationEvent`, Spring wraps that object in **PayloadApplicationEvent**. Meanwhile, the listener method parameter can still accept the original payload directly. Therefore, the expression accessing the event wrapper and the expression accessing the payload can differ.

## 1. What Is condition Used For?

If a bean has an **@EventListener** method, Spring registers that method to receive the corresponding event type. The **condition** attribute adds a runtime filter.

For example, only process orders with a total amount of 1,000 or more:

```java
@EventListener(condition = "#a0.amount >= 1000")
public void handleLargeOrder(OrderPlacedEvent event) {
    System.out.println("High-value order: " + event.getOrderId());
}
```

Spring still recognizes this method as a listener for `OrderPlacedEvent`. Before invoking the method, Spring evaluates `condition`. If `amount` is less than 1,000, the method is not invoked.

If `condition` is left empty, the listener is invoked for every event matching the type the method registered for. `condition` must return boolean `true` or one of the strings Spring accepts as true: `"true"`, `"on"`, `"yes"`, or `"1"`. Usually, you should write an explicit boolean expression so it is easy to read.

`condition` performs filtering at the time the event is dispatched. It does not mutate the event, does not turn a listener into a database query, and does not handle retries by itself.

## 2. Evaluation Context of Event Listeners

Spring creates a dedicated evaluation context for each condition evaluation. The context provides the following data:

| Access form | Meaning |
|---|---|
| **#root.event** or **event** | The actual `ApplicationEvent` passed into the dispatch mechanism |
| **#root.args** or **args** | The argument array used to invoke the listener method |
| **#root.args[0]** or **args[0]** | The first parameter of the method |
| **#a0** | The first parameter by index |
| **#p0** | Another alias for the first parameter |
| **#a1**, **#p1** | The second parameter, if the method has one |
| **#paramName** | Parameter by name, if parameter names are present in bytecode |

Indices start at 0. Thus, `#a0` and `#p0` both refer to the first parameter.

### #root.event

This is the original event distributed by `ApplicationEventMulticaster`. If the application publishes a custom class extending `ApplicationEvent`, `#root.event` is the instance of that event class.

Example:

```java
@EventListener(condition = "#root.event.amount >= 1000")
public void handleLargeOrder(OrderPlacedEvent event) {
    // ...
}
```

SpEL accesses the `amount` property on the event through the corresponding getter, such as `getAmount()`.

### #root.args and #a0 / #p0

These variables access the arguments Spring prepares to invoke the listener method. For a listener taking a single parameter, `#root.args[0]`, `#a0`, and `#p0` all refer to the first parameter object.

```java
@EventListener(condition = "#root.args[0].region == 'EU'")
public void handleEuropeanOrder(OrderPlacedEvent event) {
    // ...
}
```

Using indices is a stable approach when you do not want to depend on parameter names being retained in bytecode. It is also useful when renaming method variables without wanting to modify the expression.

### Accessing by Parameter Name

If bytecode retains parameter names, you can use that name as a SpEL variable:

```java
@EventListener(condition = "#orderEvent.amount >= 1000")
public void handleOrder(OrderPlacedEvent orderEvent) {
    // ...
}
```

To ensure the Java compiler saves parameter names, enable the **-parameters** option. With Maven Compiler Plugin, configure **parameters=true**. If parameter names are not retained or Spring cannot discover them, use `#a0` or `#p0`.

## 3. Distinguishing ApplicationEvent and Payload Objects

Spring supports two kinds of published objects:

1. An event class extending `ApplicationEvent`.
2. A plain Java object, such as a POJO or record, without needing to extend `ApplicationEvent`.

### Event Extending ApplicationEvent

Example:

```java
public class OrderPlacedEvent extends ApplicationEvent {
    private final String orderId;
    private final BigDecimal amount;

    public OrderPlacedEvent(
            Object source,
            String orderId,
            BigDecimal amount
    ) {
        super(source);
        this.orderId = orderId;
        this.amount = amount;
    }

    public String getOrderId() {
        return orderId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
```

When the publisher calls `publishEvent(new OrderPlacedEvent(...))`, Spring dispatches this exact instance. In `condition`, `#root.event.amount` and `#a0.amount` can both access the corresponding data: one variable views from the root event, and the other views from the listener parameter.

### POJO or Record Payload

Since Spring Framework 4.2, a publisher can emit any object:

```java
public class OrderPlacedPayload {
    private final String orderId;
    private final BigDecimal amount;

    public OrderPlacedPayload(String orderId, BigDecimal amount) {
        this.orderId = orderId;
        this.amount = amount;
    }

    public String getOrderId() {
        return orderId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
```

When `publishEvent(payload)` is called, Spring wraps this object in **PayloadApplicationEvent** to pass it into the event infrastructure. The listener can still declare its parameter as `OrderPlacedPayload`:

```java
@EventListener(condition = "#root.args[0].amount >= 1000")
public void handlePayload(OrderPlacedPayload payload) {
    // payload is the originally published object.
}
```

In the payload case, **#root.event** references the `ApplicationEvent` wrapper, while **#root.args[0]** references the payload resolved by Spring into the method parameter. If you need to access the payload through the wrapper, you can use the path **#root.event.payload**. In most listeners with a concrete parameter type, using `#a0` or `#root.args[0]` directly is simpler and easier to read.

## 4. Common SpEL Expressions

`condition` is a SpEL expression, so you can use comparison operators, logical operators, and property access.

### Numeric Comparison

```java
@EventListener(condition = "#a0.amount > 1000")
public void handlePremiumOrder(OrderPlacedEvent event) {
    // ...
}
```

Commonly used operators include `>`, `>=`, `<`, `<=`, `==`, and `!=`. For `BigDecimal`, Spring Expression Language supports numeric value comparisons; in business code that requires precise monetary calculations, you should still use `BigDecimal` instead of `double`.

### String Comparison

```java
@EventListener(condition = "#a0.region == 'EU'")
public void handleEuropeanOrder(OrderPlacedEvent event) {
    // ...
}
```

String literals in SpEL use single quotes. The `==` operator performs value comparison according to SpEL's semantics; there is no need to call `equals()` in this simple expression.

### Combining AND and OR Conditions

```java
@EventListener(
    condition = "#a0.amount >= 1000 && #a0.region == 'EU'"
)
public void handleLargeEuropeanOrder(OrderPlacedEvent event) {
    // ...
}
```

You can use **&&** or the keyword **and** for AND; use **||** or **or** for OR. Use parentheses to clarify operator precedence when an expression has multiple branches.

### Negation

```java
@EventListener(condition = "#a0.cancelled == false")
public void handleActiveOrder(OrderPlacedEvent event) {
    // ...
}
```

You can use **!** or **not** to negate a boolean expression. For boolean properties, a direct expression like `#a0.cancelled == false` is often easier to read.

### Accessing Potentially Null Properties

If a data branch can be null, the safe navigation operator **?.** helps avoid accessing properties on a null reference:

```java
@EventListener(condition = "#a0.customer?.vip == true")
public void handleVipCustomerOrder(OrderPlacedEvent event) {
    // ...
}
```

Check the property path and actual data types. Safe navigation only protects the access written with `?.`; it does not automatically protect every other property in the expression.

## 5. Complete Example with Java 17 and Spring Framework

This example uses plain Spring Context to demonstrate three access approaches:

- The first listener reads a custom `ApplicationEvent` via `#root.event`.
- The second listener reads the listener parameter via `#a0`.
- The third listener receives a POJO payload and reads the parameter via `#root.args[0]`.

An order is only processed by listeners whose `condition` matches. The example does not require Spring Boot.

### 5.1. Project Structure

```text
spring-event-spel/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── example/
                    └── spel/
                        └── Application.java
```

### 5.2. Maven Dependency

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>spring-event-spel</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.example.spel.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Source Code

Create the file `src/main/java/dev/example/spel/Application.java`:

```java
package dev.example.spel;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class Application {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);

            service.placeOrder(
                    "ORD-1001",
                    new BigDecimal("1500.00"),
                    "EU"
            );

            service.placeOrder(
                    "ORD-1002",
                    new BigDecimal("80.00"),
                    "US"
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public LargeOrderListener largeOrderListener() {
            return new LargeOrderListener();
        }

        @Bean
        public EuropeanOrderListener europeanOrderListener() {
            return new EuropeanOrderListener();
        }

        @Bean
        public PayloadOrderListener payloadOrderListener() {
            return new PayloadOrderListener();
        }
    }

    public static class OrderPlacedEvent extends ApplicationEvent {
        private final String orderId;
        private final BigDecimal amount;
        private final String region;

        public OrderPlacedEvent(
                Object source,
                String orderId,
                BigDecimal amount,
                String region
        ) {
            super(source);
            this.orderId = orderId;
            this.amount = amount;
            this.region = region;
        }

        public String getOrderId() {
            return orderId;
        }

        public BigDecimal getAmount() {
            return amount;
        }

        public String getRegion() {
            return region;
        }
    }

    // POJO payload does not need to extend ApplicationEvent.
    public static class OrderPlacedPayload {
        private final String orderId;
        private final BigDecimal amount;
        private final String region;

        public OrderPlacedPayload(
                String orderId,
                BigDecimal amount,
                String region
        ) {
            this.orderId = orderId;
            this.amount = amount;
            this.region = region;
        }

        public String getOrderId() {
            return orderId;
        }

        public BigDecimal getAmount() {
            return amount;
        }

        public String getRegion() {
            return region;
        }
    }

    public static class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void placeOrder(
                String orderId,
                BigDecimal amount,
                String region
        ) {
            // Publish custom ApplicationEvent.
            publisher.publishEvent(
                    new OrderPlacedEvent(this, orderId, amount, region)
            );

            // Publish POJO payload; Spring wraps it in PayloadApplicationEvent.
            publisher.publishEvent(
                    new OrderPlacedPayload(orderId, amount, region)
            );
        }
    }

    public static class LargeOrderListener {

        @EventListener(condition = "#root.event.amount >= 1000")
        public void onLargeOrder(OrderPlacedEvent event) {
            System.out.printf(
                    "Large order: %s, amount=%s%n",
                    event.getOrderId(),
                    event.getAmount()
            );
        }
    }

    public static class EuropeanOrderListener {

        @EventListener(condition = "#a0.region == 'EU'")
        public void onEuropeanOrder(OrderPlacedEvent event) {
            System.out.printf(
                    "EU order: %s, region=%s%n",
                    event.getOrderId(),
                    event.getRegion()
            );
        }
    }

    public static class PayloadOrderListener {

        @EventListener(
                condition = "#root.args[0].amount >= 1000 && "
                        + "#root.args[0].region == 'EU'"
        )
        public void onLargeEuropeanPayload(OrderPlacedPayload payload) {
            System.out.printf(
                    "Large EU payload: %s%n",
                    payload.getOrderId()
            );
        }
    }
}
```

### 5.4. Running the Program

In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java
```

Expected stdout:

```text
Large order: ORD-1001, amount=1500.00
EU order: ORD-1001, region=EU
Large EU payload: ORD-1001
```

Order ORD-1001 has an amount of 1,500 and region EU, so it satisfies all three conditions. Order ORD-1002 has an amount of 80 and region US, so none of the listeners in the example are invoked.

What the result demonstrates:

- **#root.event.amount:** reads `amount` from the custom `ApplicationEvent`.
- **#a0.region:** reads `region` from the first parameter of the listener method.
- **#root.args[0].amount:** reads `amount` from the payload parameter that the listener receives directly, even though the internal event in Spring's infrastructure is `PayloadApplicationEvent`.

## 6. Filtering by Event Type vs. Filtering by condition

The parameter type of the listener method determines which event types the listener can receive. `condition` adds a data filter at dispatch time.

Example:

```java
@EventListener(condition = "#a0.amount >= 1000")
public void onOrder(OrderPlacedEvent event) {
    // ...
}
```

There are two logical steps:

1. Spring determines whether the event matches the method's `OrderPlacedEvent` type.
2. If the type matches, Spring evaluates the SpEL `condition`. Only when the condition is true is the method invoked.

Therefore, `condition` does not replace declaring the proper event type. If a listener must accept multiple distinct event types, design the signature or the `classes` attribute appropriately and write the corresponding condition. When the annotation declares multiple event classes, the method must not declare parameters; in that case, you can access the event through the evaluation context.

Do not use a complex `condition` to substitute for a clear event type design. Event types should filter by event kind; `condition` should filter by simple event data or state.

## 7. Named Parameters and the -parameters Option

Some expressions are easier to read when using parameter names:

```java
@EventListener(condition = "#orderEvent.amount >= 1000")
public void handle(OrderPlacedEvent orderEvent) {
    // ...
}
```

For this access style to work reliably, ensure parameter names can be discovered from bytecode. With Maven Compiler Plugin, enable:

```xml
<configuration>
    <release>17</release>
    <parameters>true</parameters>
</configuration>
```

If parameter names cannot be guaranteed, use `#a0`, `#p0`, or `#root.args[0]`. Index-based approaches do not depend on variable names in source code.

A helpful rule of thumb is to use `#a0` for short expressions, and use parameter names when the project consistently compiles with `-parameters` and the expression needs to read multiple fields. Do not rename a parameter variable while forgetting to update the `condition` if it references by name.

## 8. Common Errors and How to Handle Them

| Symptom | Common Cause | Solution |
|---|---|---|
| Listener does not run even though the event is the right type | Condition returns false | Check actual field values and comparison operators |
| SpEL reports parameter name variable not found | Bytecode does not retain parameter names | Use `#a0`/`#p0` or enable `-parameters` |
| Cannot access property on `#root.event` | Event is a `PayloadApplicationEvent` wrapper or wrong property path | Use `#root.args[0]` to read the payload parameter; if you need the wrapper, check `#root.event.payload` |
| Cannot access payload property | Getter does not exist or property name is misspelled | Use JavaBean getters like `getAmount()` and check property spelling |
| Condition fails when data is null | Expression accesses property on a null value | Use safe navigation `?.` and explicit null checks |
| Listener receives event but skips certain payloads | Payload is incompatible with parameter type or condition is not satisfied | Check payload type, listener type, and condition |
| Condition becomes hard to maintain | Expression contains many business branches or deep nested accesses | Extract business logic into a service/listener and keep condition simple |

## 9. Condition Design Principles

- Only use `condition` for simple, readable filters that can be evaluated from event data.
- Prefer accessing parameters with `#a0` or `#root.args[0]` if you are not certain parameter names are retained in bytecode.
- Use `#root.event` when you need to access the actual `ApplicationEvent`.
- With POJO payloads, remember that Spring wraps the payload in `PayloadApplicationEvent`; the method parameter can still be the original payload.
- Ensure property names correspond to accessible getters or property accessors.
- Use the safe navigation operator when intermediate properties may be null.
- Do not place database queries, external service calls, or side-effecting logic inside a SpEL condition.
- Do not build SpEL expressions directly from user input or untrusted configuration.
- Keep conditions short; if business logic requires multiple steps, move the evaluation into tested Java code.

`condition` only decides whether the listener is invoked. Important business rules such as permissions, limits, transaction state, and data validity still need to be validated in the business service.

## 10. Condition When Listeners Run Asynchronously

You can combine `@EventListener` with `@Async` to run the listener on a separate executor:

```java
@Async
@EventListener(condition = "#a0.amount >= 1000")
public void handleLargeOrder(OrderPlacedEvent event) {
    // Asynchronous processing.
}
```

Enable async with `@EnableAsync` and ensure the listener is a Spring-managed bean. `condition` remains an event listener filter; enabling async does not turn the SpEL condition into a retry mechanism or guarantee completion order.

With asynchronous listeners, exceptions do not propagate back to the caller of `publishEvent` as they do with regular synchronous listeners. If error handling is needed, configure an `AsyncUncaughtExceptionHandler` or an appropriate observability and retry mechanism. An async listener also cannot use its return value to automatically publish a follow-up event; if you need to emit another event, inject `ApplicationEventPublisher` and call `publishEvent` explicitly.

Do not use `@Async` just to make a condition run faster. A condition should be a small expression that performs no I/O.

## 11. Checklist When Writing SpEL for Events

- The listener declares the right event type or payload type.
- You have identified what `#root.event` is as the root event.
- You have identified what `#root.args[0]` is as the object the listener actually receives.
- Use `#a0`/`#p0` when you want to avoid depending on parameter names.
- If using `#paramName`, bytecode must retain parameter names, e.g. by enabling `-parameters`.
- Properties in SpEL have valid getters or accessors.
- Potentially null branches are protected with safe navigation or explicit checks.
- Condition returns a clear boolean.
- Condition contains no queries, I/O, or side effects.
- Both matching and non-matching condition cases have been tested.
- If the listener is async, exception monitoring is in place and it does not rely on a return value to publish a follow-up event.

## 12. References

- Spring Framework 6.2 Reference: Additional Capabilities of the ApplicationContext, section Annotation-based Event Listeners.
- Spring Framework 6.2 Javadoc: `EventListener`, the `condition` attribute, and metadata provided in the SpEL evaluation context.

Once you understand the difference between the root event and the payload parameter, you can write concise, safe, and easy-to-test conditions. Use `#root.event` for `ApplicationEvent`, `#root.args` or `#a0`/`#p0` for listener parameters, and remember that a POJO payload is wrapped by Spring in `PayloadApplicationEvent` before passing through the event multicaster.