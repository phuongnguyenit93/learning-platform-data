# Listeners Receiving ApplicationEvent in Spring Framework

## Objectives

In Spring Framework, `ApplicationEvent` is the base class for events published and dispatched within an `ApplicationContext`. When a business class extends `ApplicationEvent`, it can carry data about what happened while retaining `source` — the object that originated the event. A listener implementing `ApplicationListener<E>` can explicitly declare the event type it receives.

This lesson focuses on listeners receiving custom events that extend `ApplicationEvent`, how Spring uses the generic type `E` to select listeners, the meaning of `source`, and the differences between a custom event class and a POJO wrapped by Spring into `PayloadApplicationEvent`. At the end, there is a runnable Java 17 and Spring Framework 6.2 example built with Maven.

After this lesson, you will be able to:

- Create a custom event class extending `ApplicationEvent` and provide a valid source.
- Implement `ApplicationListener<CustomEvent>` to handle the right event type.
- Explain event type matching by class type and generic type.
- Distinguish custom `ApplicationEvent` from POJO payloads and the `PayloadApplicationEvent` wrapper.
- Choose between `ApplicationListener<E>` and method listeners using `@EventListener`.
- Understand the scope limits of application events within a single Spring process.

## 1. What Is ApplicationEvent?

`ApplicationEvent` is an abstract class in Spring that extends `java.util.EventObject`. Therefore, an event class extending it must invoke the superclass constructor with a non-`null` `source`.

`source` is the object that the event describes as the origin of the occurrence. For example, when a `CatalogService` changes a product's price, the event can receive that service instance itself as the source. Listeners access the source via `getSource()`.

A custom event typically contains:

- **Source:** the object that originated or owns the action producing the event.
- **Event data:** the values needed for listeners to understand what happened.
- **Timestamp:** `ApplicationEvent` records the creation time of the event and exposes it via `getTimestamp()`.

An event should describe something that has happened, such as `ProductPriceChangedEvent`, `OrderApprovedEvent`, or `CustomerRegisteredEvent`. Avoid putting an entire ORM-managed entity into an event if listeners only need a few values. IDs, before/after values, or immutable data generally make payloads easier to control.

### Creating a Custom Event Class

```java
import java.math.BigDecimal;

import org.springframework.context.ApplicationEvent;

public class ProductPriceChangedEvent extends ApplicationEvent {

    private final long productId;
    private final BigDecimal oldPrice;
    private final BigDecimal newPrice;

    public ProductPriceChangedEvent(
            Object source,
            long productId,
            BigDecimal oldPrice,
            BigDecimal newPrice) {
        super(source);
        this.productId = productId;
        this.oldPrice = oldPrice;
        this.newPrice = newPrice;
    }

    public long getProductId() {
        return productId;
    }

    public BigDecimal getOldPrice() {
        return oldPrice;
    }

    public BigDecimal getNewPrice() {
        return newPrice;
    }
}
```

The constructor accepts `Object source` because the source can be a service, aggregate, component, or another object meaningful to the application. `super(source)` passes the source to `EventObject`; if `null` is passed, the constructor throws `IllegalArgumentException`.

The data fields are declared `final` so the event cannot be modified after publishing. This allows multiple listeners to read the same snapshot without worrying about one listener mutating data before another listener runs.

## 2. ApplicationListener<E> Receives Events by Type

`ApplicationListener<E>` is Spring's core listener interface:

```java
public interface ApplicationListener<E extends ApplicationEvent> {
    void onApplicationEvent(E event);
}
```

The generic parameter `E` must be a type extending `ApplicationEvent`. When implementing `ApplicationListener<ProductPriceChangedEvent>`, the class explicitly declares that it handles events of type `ProductPriceChangedEvent`.

Example:

```java
import org.springframework.context.ApplicationListener;

public class ProductPriceChangedListener
        implements ApplicationListener<ProductPriceChangedEvent> {

    @Override
    public void onApplicationEvent(ProductPriceChangedEvent event) {
        System.out.printf(
                "Product %d changed from %s to %s; source=%s%n",
                event.getProductId(),
                event.getOldPrice().toPlainString(),
                event.getNewPrice().toPlainString(),
                event.getSource().getClass().getSimpleName()
        );
    }
}
```

Spring registers the listener bean with the context's `ApplicationEventMulticaster`. When an event is published, the multicaster selects listeners with matching types and invokes `onApplicationEvent`.

You can register the listener using Java configuration:

```java
@Configuration
class EventConfiguration {

    @Bean
    ProductPriceChangedListener productPriceChangedListener() {
        return new ProductPriceChangedListener();
    }
}
```

You can also use component scanning if the class is annotated with `@Component`. The important requirement is that the listener must be managed by Spring or registered directly with the context; merely instantiating the object with `new ProductPriceChangedListener()` outside the container does not make it automatically receive events.

## 3. Event Source vs. Publisher Source

Distinguish between two concepts:

- **Publisher:** where `publishEvent(...)` is called, i.e., the context or a bean injected with `ApplicationEventPublisher`.
- **Event source:** the value passed into the `ApplicationEvent` constructor when creating the event.

These two objects can be the same, but do not have to be. In a business flow, the context might be the publisher while `CatalogService` is the source:

```java
CatalogService catalogService = context.getBean(CatalogService.class);

context.publishEvent(
        new ProductPriceChangedEvent(
                catalogService,
                42L,
                new BigDecimal("100.00"),
                new BigDecimal("125.00")
        )
);
```

In this example:

- `context` performs the event publishing and dispatch.
- `catalogService` is stored in `event.getSource()`.
- Listeners can use the source for logging or tracing the origin of the change.

Do not use `source` as a way to pass all dependencies to the listener. A listener should depend on the event contract and its own injected dependencies. If the source is only used to identify the emitter, consider passing an explicit source identifier or code instead of a large object.

## 4. How Does Event Type Matching Work?

Spring does not invoke every listener for every event. When dispatching, Spring inspects the actual event type and the event type declared by the listener.

For generic listeners, Spring attempts to resolve the type `E` from the class's generic declaration or bean definition. The resolved type is used to decide whether the listener supports the event.

Example:

```java
class DomainEvent extends ApplicationEvent {
    DomainEvent(Object source) {
        super(source);
    }
}

class ProductPriceChangedEvent extends DomainEvent {
    ProductPriceChangedEvent(Object source) {
        super(source);
    }
}

class DomainEventListener
        implements ApplicationListener<DomainEvent> {
    @Override
    public void onApplicationEvent(DomainEvent event) {
        // Receives DomainEvent and compatible subclasses.
    }
}

class ProductPriceListener
        implements ApplicationListener<ProductPriceChangedEvent> {
    @Override
    public void onApplicationEvent(ProductPriceChangedEvent event) {
        // Receives only events in the ProductPriceChangedEvent branch.
    }
}
```

When a `ProductPriceChangedEvent` is published:

- `ApplicationListener<ProductPriceChangedEvent>` matches directly.
- `ApplicationListener<DomainEvent>` also matches because the actual event is a subclass of `DomainEvent`.
- A listener for an unrelated branch, such as `ApplicationListener<CustomerRegisteredEvent>`, does not match.

The class-type rule can be stated as: the event type declared by the listener must be able to accept an instance of the actual event type. In other words, a listener declaring a superclass can receive subclass events; a listener declaring a subclass does not receive an event that is only of the superclass type.

Spring uses resolved type information (internally backed by `ResolvableType`) to handle generic cases as well. This is useful when multiple listeners subscribe to an event family, yet each listener needs a specific type. If an event class has generic parameters whose type info is lost to type erasure and must be distinguished accurately at runtime, the event can implement `ResolvableTypeProvider` to supply the appropriate runtime type.

Do not rely on class names or bean names to route events. Declare generic types clearly and keep event inheritance hierarchies simple and meaningful.

## 5. How POJO Events and PayloadApplicationEvent Differ from Custom ApplicationEvent

Since Spring Framework 4.2, `publishEvent` can also accept objects that do not extend `ApplicationEvent`. When a POJO is published, Spring wraps it in `PayloadApplicationEvent<T>` to feed it into the event mechanism that expects `ApplicationEvent`.

Suppose there is a record:

```java
public record PriceQuote(long productId, BigDecimal amount) {
}
```

When calling:

```java
context.publishEvent(new PriceQuote(43L, new BigDecimal("19.99")));
```

the event actually dispatched is `PayloadApplicationEvent<PriceQuote>`, where:

- `getPayload()` returns the `PriceQuote` record.
- `getSource()` is the publisher context that wrapped the payload when publishing the POJO via `ApplicationContext`.

The key difference lies in the object type received by the listener:

| How Published | Dispatched Event Object | Matching Listener |
|---|---|---|
| `publishEvent(new ProductPriceChangedEvent(...))` | `ProductPriceChangedEvent` itself | `ApplicationListener<ProductPriceChangedEvent>` |
| `publishEvent(new PriceQuote(...))` | `PayloadApplicationEvent<PriceQuote>` | `ApplicationListener<PayloadApplicationEvent<PriceQuote>>` |
| Publish POJO and use annotation | Payload resolved by adapter | `@EventListener void onQuote(PriceQuote quote)` |

Because `ApplicationListener<E>` has the bound `E extends ApplicationEvent`, you cannot write `ApplicationListener<PriceQuote>` if `PriceQuote` is just a POJO record. You can listen to the wrapper using `ApplicationListener<PayloadApplicationEvent<PriceQuote>>`, or use `@EventListener` to receive the payload directly.

Example listener receiving the wrapper:

```java
class PriceQuoteWrapperListener
        implements ApplicationListener<PayloadApplicationEvent<PriceQuote>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<PriceQuote> event) {
        PriceQuote quote = event.getPayload();
        Object source = event.getSource();

        System.out.printf(
                "Payload from %s: product=%d, amount=%s%n",
                source.getClass().getSimpleName(),
                quote.productId(),
                quote.amount().toPlainString()
        );
    }
}
```

Example annotation receiving the resolved payload:

```java
class PriceQuoteAnnotationListener {

    @EventListener
    void onPriceQuote(PriceQuote quote) {
        System.out.printf(
                "Quote payload: product=%d, amount=%s%n",
                quote.productId(),
                quote.amount().toPlainString()
        );
    }
}
```

When you need to read wrapper metadata, such as the `source` of `PayloadApplicationEvent`, accept the wrapper with the appropriate listener. If you only need the payload contents, an `@EventListener` method with a POJO parameter is usually cleaner.

## 6. Comparing ApplicationListener<E> and @EventListener

Both participate in Spring's dispatch mechanism, but their declaration style and accepted event types differ.

| Criterion | `ApplicationListener<E>` | `@EventListener` |
|---|---|---|
| Declaration style | Implements an interface | Annotates a bean method |
| Accepted type | `E extends ApplicationEvent` | Can receive ApplicationEvent or POJO payload |
| Explicitness | Generic type is on the class | Method parameter type expresses the event |
| Best suited for | Dedicated listener classes needing a clear type contract | Concise handlers, multiple event methods in one bean |
| Wrapper/source access | Receives the event object directly | Can declare the appropriate event parameter; POJO methods typically receive the payload |
| Conditions | Filtering logic can be implemented in a specialized listener | Supports the `condition` attribute with SpEL |

Use `ApplicationListener<E>` when you want the class to express the event contract directly, handle events at the `ApplicationEvent` object level, or access `getSource()` and event metadata.

Use `@EventListener` when a handler only needs to process a payload type, when you want multiple listener methods in one bean, or when you need SpEL conditions:

```java
@EventListener(condition = "#quote.amount().doubleValue() > 100")
void onExpensiveQuote(PriceQuote quote) {
    // Only handle quotes with amount greater than 100.
}
```

In SpEL, default variable names depend on parameter names being discoverable; to avoid ambiguity, you can use `#a0` or `#p0` to reference the first parameter when needed. Conditions should align with the payload and should not contain complex business logic.

Do not register the same reaction using both mechanisms if doing so would cause the event to be handled twice. Choose one appropriate mechanism per handler and test the invocation count.

## 7. Complete Example with Java 17 and Spring Framework 6.2

This example publishes two kinds of events to clearly observe the difference:

1. `ProductPriceChangedEvent` extends `ApplicationEvent`, with the `CatalogService` bean as source, received by `ApplicationListener<ProductPriceChangedEvent>`.
2. `PriceQuote` is a POJO record. Spring wraps it into `PayloadApplicationEvent<PriceQuote>`; one listener receives the wrapper and an `@EventListener` method receives the payload directly.

Structure:

```text
application-event-listener-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventListenerDemo.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>application-event-listener-demo</artifactId>
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
                    <mainClass>demo.ApplicationEventListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/demo/ApplicationEventListenerDemo.java**

```java
package demo;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class ApplicationEventListenerDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            CatalogService source = context.getBean(CatalogService.class);

            context.publishEvent(
                    new ProductPriceChangedEvent(
                            source,
                            42L,
                            new BigDecimal("10.00"),
                            new BigDecimal("12.50")
                    )
            );

            context.publishEvent(
                    new PriceQuote(43L, new BigDecimal("19.99"))
            );
        }
    }

    @Configuration
    static class AppConfig {

        @Bean
        CatalogService catalogService() {
            return new CatalogService();
        }

        @Bean
        ProductPriceChangedListener productPriceChangedListener() {
            return new ProductPriceChangedListener();
        }

        @Bean
        PriceQuoteWrapperListener priceQuoteWrapperListener() {
            return new PriceQuoteWrapperListener();
        }

        @Bean
        PriceQuoteAnnotationListener priceQuoteAnnotationListener() {
            return new PriceQuoteAnnotationListener();
        }
    }

    static class CatalogService {
    }

    static class ProductPriceChangedEvent extends ApplicationEvent {
        private final long productId;
        private final BigDecimal oldPrice;
        private final BigDecimal newPrice;

        ProductPriceChangedEvent(
                Object source,
                long productId,
                BigDecimal oldPrice,
                BigDecimal newPrice) {
            super(source);
            this.productId = productId;
            this.oldPrice = oldPrice;
            this.newPrice = newPrice;
        }

        long getProductId() {
            return productId;
        }

        BigDecimal getOldPrice() {
            return oldPrice;
        }

        BigDecimal getNewPrice() {
            return newPrice;
        }
    }

    record PriceQuote(long productId, BigDecimal amount) {
    }

    static class ProductPriceChangedListener
            implements ApplicationListener<ProductPriceChangedEvent> {

        @Override
        public void onApplicationEvent(ProductPriceChangedEvent event) {
            System.out.printf(
                    "Custom ApplicationEvent: product=%d, source=%s, %s -> %s%n",
                    event.getProductId(),
                    event.getSource().getClass().getSimpleName(),
                    event.getOldPrice().toPlainString(),
                    event.getNewPrice().toPlainString()
            );
        }
    }

    @Order(1)
    static class PriceQuoteWrapperListener
            implements ApplicationListener<PayloadApplicationEvent<PriceQuote>> {

        @Override
        public void onApplicationEvent(
                PayloadApplicationEvent<PriceQuote> event) {
            PriceQuote quote = event.getPayload();

            System.out.printf(
                    "PayloadApplicationEvent: source=%s, payload=%s%n",
                    event.getSource().getClass().getSimpleName(),
                    quote
            );
        }
    }

    static class PriceQuoteAnnotationListener {

        @EventListener
        @Order(2)
        void onPriceQuote(PriceQuote quote) {
            System.out.printf(
                    "@EventListener payload: product=%d, amount=%s%n",
                    quote.productId(),
                    quote.amount().toPlainString()
            );
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Expected stdout:

```text
Custom ApplicationEvent: product=42, source=CatalogService, 10.00 -> 12.50
PayloadApplicationEvent: source=AnnotationConfigApplicationContext, payload=PriceQuote[productId=43, amount=19.99]
@EventListener payload: product=43, amount=19.99
```

Explanation:

- The custom event is published directly because it is already an `ApplicationEvent`. Spring does not wrap it in `PayloadApplicationEvent`.
- The generic listener `ApplicationListener<ProductPriceChangedEvent>` is selected by event type.
- The source of the custom event is the `CatalogService` bean, because that object was passed into `super(source)`.
- `PriceQuote` does not extend `ApplicationEvent`; the context wraps it in `PayloadApplicationEvent`.
- `ApplicationListener<PayloadApplicationEvent<PriceQuote>>` receives the wrapper, so it can read both `getPayload()` and `getSource()`.
- `@EventListener` with a `PriceQuote` parameter receives the payload already unwrapped by Spring, so the method does not need to open the wrapper manually.
- `@Order` determines the order of the two listeners handling the same payload in the example.

## 8. Common Pitfalls

| Pitfall | Why It Happens | How to Handle |
|---|---|---|
| Passing `null` as source | `EventObject` requires a non-null source | Pass a meaningful bean or source object |
| Using `ApplicationListener<PriceQuote>` for a POJO | Generic `E` is bounded to extend `ApplicationEvent` | Use `ApplicationListener<PayloadApplicationEvent<PriceQuote>>` or `@EventListener` |
| Assuming custom listener receives POJOs with matching fields | POJOs are wrapped in a different wrapper type | Declare a listener for the wrapper or a method accepting the payload |
| Listener is not invoked | Bean is not registered or event type does not match | Check generic type and bean configuration |
| Superclass listener does not receive subclass | Generic type declared too narrowly or type metadata is wrong | Declare the appropriate supertype and check runtime generics |
| Using source as a service locator | Listener becomes coupled to the emitter object | Put necessary data inside the event and inject dependencies separately |
| One event is processed twice | Same reaction is registered via multiple listeners | Choose one handler or explicitly control side effects |
| Sending ApplicationEvent to another service | Application events belong only to the current context/process | Use integration events and an appropriate broker/API |

## 9. Transaction and Reliability Notes

Application events are dispatched synchronously by default. If an event is published inside a transaction, regular listeners can run before commit. If the transaction subsequently rolls back, side effects already performed by the listener are not automatically rolled back with the database.

For listeners that must run after the transaction commits, you can use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. However, an after-commit listener still does not provide durable persistence guarantees: the process could stop after commit before the listener finishes. For critical integration messages that must not be lost, write to an outbox in the same transaction and forward via a relay/broker. Design consumers to be idempotent because messages may be redelivered.

Also remember that ApplicationEvent is not a message broker. It does not natively provide durable storage, acknowledgements, retries, replay, or cross-process delivery. Its scope is an internal event mechanism within a Spring application.

## 10. Implementation Checklist

- [ ] Custom event extends `ApplicationEvent` when an explicit event class is needed.
- [ ] Constructor calls `super(source)` with a non-null source.
- [ ] Event contains the necessary data, preferring immutable state.
- [ ] Listener declares the right `ApplicationListener<E>` and E is an appropriate ApplicationEvent.
- [ ] Listener is registered as a bean or added directly to the context.
- [ ] Event type matching between superclass and subclass is understood.
- [ ] POJO payloads are not confused with custom ApplicationEvents.
- [ ] `PayloadApplicationEvent<T>` is used when you need to receive the wrapper and source of a POJO.
- [ ] `@EventListener` is used when you need direct payload reception or concise handlers.
- [ ] The same side effect is not registered across multiple mechanisms causing duplicate processing.
- [ ] Appropriate transaction, sync/async, and error policies are defined.
- [ ] Integration mechanisms are used when cross-process communication is required.

## Conclusion

`ApplicationListener<E>` receives events according to its declared generic type, where `E` must extend `ApplicationEvent`. Custom event classes let you clearly define data and source; Spring uses resolved event types to select compatible listeners. When publishing a POJO, Spring wraps the payload in `PayloadApplicationEvent<T>`, so interface-based listeners receive the wrapper while `@EventListener` can receive the payload directly. Mastering these differences helps you choose the right listener contract, trace sources accurately, and avoid missed events due to type mismatches.