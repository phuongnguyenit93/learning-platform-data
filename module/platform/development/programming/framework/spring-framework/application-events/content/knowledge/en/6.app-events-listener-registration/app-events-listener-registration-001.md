# Component Scan and Automatic Listeners

Spring Framework allows registering event listeners using the `@EventListener` annotation. When an object containing the method is managed by Spring as a bean in the ApplicationContext, Spring's annotation infrastructure can detect that method and register it with the event dispatch mechanism. As a result, a service only needs to publish an event; it does not have to find or call each listener itself.

For this mechanism to work, two steps must be distinguished:

1. **Bean discovery:** Spring finds and creates the bean containing the listener through component scan, `@Bean`, `@Import`, or another bean registration mechanism.
2. **Listener method registration:** Spring detects `@EventListener` methods on the managed bean and creates adapters so they receive events.

Component scan does not automatically turn every class with `@EventListener` into a bean. The annotation on a method is only processed when the object containing the method is already in the appropriate ApplicationContext.

## 1. A listener needs to be registered as a bean

Example:

~~~java
@Component
class ShipmentListener {
    @EventListener
    public void onShipmentCreated(ShipmentCreated event) {
        System.out.println("Shipment created: " + event.shipmentId());
    }
}
~~~

The two annotations have different roles:

- `@Component` marks the class as a bean candidate to be discovered by component scan.
- `@EventListener` marks the method as an event handler.

The `ShipmentCreated` parameter tells Spring what event type the method needs to receive. When the application publishes an object compatible with this type, Spring can invoke the method.

If a class only has `@EventListener` without being registered as a bean, Spring does not automatically create an instance for that class. Similarly, an object created with `new` outside the container does not automatically become a listener just because its method has the annotation.

~~~java
// This object is outside the ApplicationContext.
ShipmentListener listener = new ShipmentListener();
~~~

To have Spring manage the method, place the object into the container via component scan, a `@Bean` declaration, a configuration import, or an appropriate bean registration mechanism.

## 2. Default scan scope of @SpringBootApplication

In Spring Boot, `@SpringBootApplication` includes component scan functionality. When no package is specified, the scan scope starts from the package containing the application class and goes down into subpackages.

Example:

~~~text
com.acme.store
├── StoreApplication.java
├── order
│   ├── OrderService.java
│   └── OrderPlaced.java
├── listener
│   └── OrderPlacedListener.java
└── audit
    └── OrderAuditListener.java
~~~

If `StoreApplication` is in `com.acme.store`, the beans in `com.acme.store.order`, `com.acme.store.listener`, and `com.acme.store.audit` are within the default scan scope.

Placing the startup class in the root package of the application usually keeps the structure easy to follow. If the application class is in `com.acme.store.bootstrap`, sibling packages such as `com.acme.store.listener` may fall outside the default scan scope.

You can specify scan packages explicitly:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.acme.store",
        "com.acme.shared.events"
})
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

Or configure it with `@ComponentScan`:

~~~java
@Configuration
@ComponentScan(basePackages = {
        "com.acme.store",
        "com.acme.shared.events"
})
class StoreComponentConfiguration {}
~~~

For large codebases, you can use `basePackageClasses` to avoid string-based package names:

~~~java
@Configuration
@ComponentScan(basePackageClasses = {
        StoreApplication.class,
        SharedEventListenersMarker.class
})
class StoreComponentConfiguration {}
~~~

Each marker class represents the package to scan. This approach makes package refactoring safer because the IDE and compiler can track class references.

Component scan also supports include/exclude filters. Therefore, a class inside a scanned package can still be excluded by a filter or a bean registration condition.

## 3. Common stereotypes used for listeners

Stereotype annotations help Spring identify a class as a component candidate:

| Annotation | Common role |
|---|---|
| `@Component` | General-purpose bean |
| `@Service` | Bean containing business logic |
| `@Repository` | Data access bean |
| `@Controller` | Spring MVC handler bean |
| `@RestController` | Controller returning response body |
| `@Configuration` | Configuration bean, typically declaring other beans via `@Bean` |

Annotations such as `@Service`, `@Repository`, `@Controller`, and `@Configuration` have a meta-annotation relationship with `@Component`, so they are recognized by default component scan.

Listeners usually use `@Component` or `@Service`, depending on their responsibility:

~~~java
record OrderPlaced(String orderId) {}

@Service
class OrderAuditListener {
    @EventListener
    public void record(OrderPlaced event) {
        System.out.println("Audit order: " + event.orderId());
    }
}
~~~

There is no need to add multiple stereotypes to one listener. What matters is that the class is registered as a bean and the method is annotated properly.

## 4. Registering a listener via @Bean

Component scan is not the only way to create a bean. A `@Bean` method in a configuration class can also register a listener:

~~~java
record ShipmentCreated(String shipmentId) {}

@Configuration
class EventListenerConfiguration {
    @Bean
    ShipmentListener shipmentListener() {
        return new ShipmentListener();
    }
}

class ShipmentListener {
    @EventListener
    public void onShipmentCreated(ShipmentCreated event) {
        System.out.println("Shipment created: " + event.shipmentId());
    }
}
~~~

In this example, `ShipmentListener` does not need `@Component`, because the `shipmentListener()` method places the instance into the ApplicationContext. Spring can still detect the `@EventListener` method on that bean.

This declaration style is suitable when:

- The listener comes from an external library and you cannot add stereotypes to its source.
- You want to control the constructor or how the listener is instantiated yourself.
- The bean should only be created according to a profile or configuration condition.
- You want to group integration configuration for a module into a dedicated configuration class.

The configuration class must also be registered by Spring. You can let component scan find it or import it explicitly:

~~~java
@Configuration
@Import(EventListenerConfiguration.class)
class ApplicationConfiguration {}
~~~

If `EventListenerConfiguration` is not scanned, imported, or registered in another way, the `@Bean` methods inside it will not be processed.

## 5. How does Spring automatically register @EventListener methods?

When the annotation configuration infrastructure is active, Spring uses `EventListenerMethodProcessor` to detect methods annotated with `@EventListener` on container-managed beans. The processor runs during the ApplicationContext lifecycle after singleton beans have been instantiated.

At a conceptual level, the process consists of:

1. Spring reads configuration and creates bean definitions from component scan, `@Bean`, `@Import`, and other registration sources.
2. ApplicationContext creates the beans according to the container lifecycle.
3. `EventListenerMethodProcessor` inspects the beans and finds methods annotated with `@EventListener`.
4. Spring uses an appropriate `EventListenerFactory` to create an adapter for the method. The common adapter is `ApplicationListenerMethodAdapter`.
5. The adapter is registered with the ApplicationContext event mechanism to receive matching events.
6. When a publisher emits an event, `ApplicationEventMulticaster` dispatches it to the registered listeners.

Thanks to this mechanism, the application does not need to write reflection code to scan methods or manually call `addApplicationListener` for each annotated method.

A bean can have multiple `@EventListener` methods; each method is a separate handler. A method can also receive multiple event types using the annotation's `classes` attribute, if the method signature matches that declaration.

The key point to remember: the processor operates on container beans. Placing the annotation on an unmanaged class is not enough for Spring to register the listener.

## 6. Runnable example: component scan automatically finds the listener

The following example uses Java 17+ and Spring Boot. The classes are in the same `com.example.events` package; the startup class is in this package, so default component scan finds both the service and the listener.

~~~java
package com.example.events;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@SpringBootApplication
public class EventScanApplication {
    public static void main(String[] args) {
        SpringApplication.run(EventScanApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService orderService) {
        return args -> orderService.place("ORD-42");
    }
}

record OrderPlaced(String orderId) {}

@Service
class OrderService {
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void place(String orderId) {
        publisher.publishEvent(new OrderPlaced(orderId));
        System.out.println("Publisher returned");
    }
}

@Component
class OrderPlacedListener {
    @EventListener
    public void handle(OrderPlaced event) {
        System.out.println("Listener received: " + event.orderId());
    }
}
~~~

Output lines produced by the example:

~~~text
Listener received: ORD-42
Publisher returned
~~~

Explanation:

1. Spring Boot initializes the ApplicationContext and component-scans the `com.example.events` package.
2. `OrderService` is created because it has `@Service`.
3. `OrderPlacedListener` is created because it has `@Component`.
4. Spring detects the `handle` method and registers an adapter receiving `OrderPlaced`.
5. The service only calls `ApplicationEventPublisher.publishEvent`; the service does not need to know which listeners exist.
6. With the default `SimpleApplicationEventMulticaster` and a synchronous listener, the listener finishes processing before `publishEvent` returns.

Spring Boot startup logs are omitted. The project needs a Spring Boot dependency with context support, such as `spring-boot-starter`. You can run it with the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

The example demonstrates automatic registration within one ApplicationContext. If you move the listener to another package outside the scan scope, you need to adjust the scan packages or register the bean another way.

## 7. Spring selects listeners by event type

The method parameter type determines the event that the listener receives. Example:

~~~java
import org.springframework.context.ApplicationEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

record OrderPlaced(String orderId) {}

@Component
class OrderListeners {
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        System.out.println("Order: " + event.orderId());
    }

    @EventListener
    public void onApplicationEvent(ApplicationEvent event) {
        System.out.println("Application event: " + event.getClass().getSimpleName());
    }
}
~~~

A listener can accept a supertype or compatible interface. For events that are plain Java objects, Spring evaluates the published object's type and the method parameter type.

You can restrict a listener using a SpEL condition:

~~~java
import java.math.BigDecimal;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

record PaymentCompleted(String paymentId, BigDecimal amount) {}

@Component
class LargePaymentListener {
    @EventListener(condition = "#root.event.amount().compareTo(T(java.math.BigDecimal).valueOf(1000000)) >= 0")
    public void onLargePayment(PaymentCompleted event) {
        System.out.println("Large payment: " + event.paymentId());
    }
}
~~~

The condition only allows the method to run when the expression evaluates to true. The example assumes `PaymentCompleted` is a record with an `amount()` accessor returning `BigDecimal`.

If the method returns a non-null event object, Spring can publish that return value as a derived event. If it returns a collection, each element is published individually. For asynchronous listeners, do not rely on the return value to emit events; use `ApplicationEventPublisher` explicitly.

## 8. Listener ordering and additional mechanisms

You can use `@Order` to order listeners that receive the same event:

~~~java
@Component
class OrderedOrderListeners {
    @EventListener
    @Order(1)
    public void first(OrderPlaced event) {
        System.out.println("First listener");
    }

    @EventListener
    @Order(2)
    public void second(OrderPlaced event) {
        System.out.println("Second listener");
    }
}
~~~

A smaller order value takes precedence within the same dispatch. Do not rely on component scan order or file order to determine business execution order.

Several other mechanisms can be used together with listeners:

- `@Async` combined with `@EnableAsync` to run the listener on an executor. The publisher does not wait for an async listener to finish; executor configuration and exception handling must be configured separately.
- `@TransactionalEventListener` to tie processing timing to a transaction, such as `AFTER_COMMIT`.
- `condition` to filter events based on payload data.
- `@Profile` or `@Conditional` to decide whether the listener bean exists in the context.

These mechanisms do not replace the bean registration step. The listener still needs to be placed into the ApplicationContext for the annotated method to be detected.

## 9. Distinguishing @EventListener and ApplicationListener

Spring supports both listeners declared with annotations and listeners implementing an interface:

| Criterion | `@EventListener` | `ApplicationListener<E>` |
|---|---|---|
| Declaration | Annotation on a method | Class implementing an interface |
| Multiple handlers in one class | Can declare multiple methods | Usually split into separate listeners or branched manually |
| SpEL condition | Has the `condition` attribute | No built-in equivalent attribute |
| Container detection | Annotation processor creates an adapter | Bean implementing the interface is recognized as a listener |
| Suitable for | Concise handlers declared directly inside a bean | Explicit interface-based listeners |

Example:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedApplicationListener
        implements ApplicationListener<OrderPlaced> {

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        System.out.println("Interface listener: " + event.orderId());
    }
}
~~~

Do not register both approaches for the same task unless intentional. A bean that both implements `ApplicationListener<OrderPlaced>` and has an `@EventListener` method accepting `OrderPlaced` may handle the same event through two different paths.

## 10. Context lifecycle and publishing timing

Spring detects listener methods during ApplicationContext initialization. Therefore, you should not publish events from a constructor or `@PostConstruct` assuming all listeners are already ready.

If work needs to run after the context has refreshed, you can listen for `ContextRefreshedEvent`. In Spring Boot, `ApplicationReadyEvent` is often suitable when logic needs to wait until the application completes its main startup steps:

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ApplicationStartupListener {
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
~~~

`ApplicationReadyEvent` is a Spring Boot event, not a core Spring Framework class. Be sure to import the correct package `org.springframework.boot.context.event.ApplicationReadyEvent`.

Do not use startup events to replace dependency injection. If a bean needs another dependency, declare it through the constructor. Startup events are only suitable for work that makes sense at the point when the context or application is ready.

## 11. Diagnosing a listener not being invoked

When a publisher emits an event but the listener does not run, check in order:

1. **Package not scanned:** the listener is outside the root package of `@SpringBootApplication`. Adjust `scanBasePackages`, `@ComponentScan`, or use `@Import`.
2. **Missing bean registration:** the class lacks a stereotype and is not declared with `@Bean` or another bean registration mechanism.
3. **Bean excluded by conditions:** `@Profile`, `@Conditional`, or a scan filter prevents the bean from existing in the current environment.
4. **Object outside container:** the class was instantiated with `new` and not registered as a bean.
5. **Wrong event type:** the method parameter is incompatible with the published object.
6. **SpEL condition not satisfied:** the `condition` expression returns false.
7. **Published too early:** the event was emitted before annotation listeners were fully discovered and registered.
8. **Wrong ApplicationContext:** the publisher and listener belong to different contexts.
9. **Listener runs but throws an exception:** check the logs and stack trace; distinguish synchronous dispatch from async listeners.

You can check beans in the context by injecting `ApplicationContext` and querying by type:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

// Assumes OrderPlacedListener has been declared in the application.
@Component
class ListenerDiagnostics {
    ListenerDiagnostics(ApplicationContext context) {
        String[] names = context.getBeanNamesForType(OrderPlacedListener.class);
        System.out.println("OrderPlacedListener beans: " + names.length);
    }
}
~~~

If the bean count is 0, check the scan packages and registration conditions before checking event dispatch.

## 12. Avoiding registering the same listener twice

A class can be created as multiple beans if it is both component-scanned and declared again via `@Bean`:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId) {}

@Component
class OrderPlacedListener {
    @EventListener
    public void handle(OrderPlaced event) {
        System.out.println("Handled: " + event.orderId());
    }
}

@Configuration
class DuplicateListenerConfiguration {
    @Bean
    OrderPlacedListener anotherOrderPlacedListener() {
        return new OrderPlacedListener();
    }
}
~~~

If both beans exist, the listener method can be registered on both instances and both will handle the same event. The consequence could be sending emails twice, recording duplicate audits, or updating metrics repeatedly.

How to prevent this:

- Choose a single bean creation source for each listener.
- Do not re-declare a class that is already scanned unless you intentionally want a second instance.
- Do not invoke manual registration again when the annotation infrastructure already registers the method automatically.
- Use clear bean names and check the bean count by type when in doubt.
- For critical business side effects, design idempotency so repeated processing does not corrupt data.

## 13. Configuration checklist

- [ ] Is the listener class registered as a bean in the ApplicationContext that needs to receive the event?
- [ ] Is the listener package within the scan scope or imported/declared via `@Bean`?
- [ ] Is the application class placed in an appropriate root package?
- [ ] Does the method have `@EventListener` and declare a compatible event type?
- [ ] Are there any `condition`, `@Profile`, `@Conditional`, or scan filters preventing the listener from running?
- [ ] Is the event published after the listener is ready?
- [ ] Is a duplicate listener bean created via both component scan and `@Bean`?
- [ ] Is the same task registered with both `@EventListener` and `ApplicationListener`?
- [ ] If using async or transactional listeners, are the executor/transaction and error handling configured?
- [ ] Have the correct ApplicationContext and actual logs been verified?

Component scan finds eligible classes and registers them as beans. The `@EventListener` infrastructure detects methods on those beans and connects them to the event multicaster. By clearly separating bean discovery from listener method registration, an application can organize listeners by module while keeping control over scan scope, bean creation conditions, and the risk of duplicate registration.
