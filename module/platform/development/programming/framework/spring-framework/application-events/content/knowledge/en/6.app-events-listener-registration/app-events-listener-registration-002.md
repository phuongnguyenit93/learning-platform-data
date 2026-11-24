# Registering Listeners with @Bean

In Spring Framework, an event listener must be registered in the `ApplicationContext` to receive events emitted by the context. Besides marking a class with `@Component`, you can declare a listener using a `@Bean` method in a configuration class. Spring creates the object, manages the bean lifecycle, and adds the listener to the event distribution mechanism.

Registering with `@Bean` is useful when the listener comes from an external library, when you want to declare components explicitly in configuration, when you need to inject dependencies via factory method parameters, or when you want to enable/disable the listener based on profiles and configuration conditions.

There are two commonly used listener styles:

- A bean implementing `ApplicationListener<E>` to receive events of type `E`.
- A regular bean with one or more methods annotated with `@EventListener`.

After this lesson, you will be able to register both types with `@Bean`, understand how Spring discovers them, control ordering and registration conditions, and avoid mistakes involving generic types, bean lifecycle, and configuration.

## 1. How does @Bean register a listener?

`@Bean` marks a method in a configuration class so Spring calls it and registers the return value as a bean:

~~~java
@Configuration
public class EventConfiguration {

    @Bean
    OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }
}
~~~

In this example:

- `EventConfiguration` is a configuration class processed by Spring.
- `orderAuditListener()` is a factory method that creates the listener.
- The return value is registered as a bean with the default name `orderAuditListener`.
- The bean has singleton scope by default.
- Spring manages bean creation and injects dependencies if needed.

`@Bean` is a general-purpose bean declaration mechanism, not an event-specific annotation. Spring recognizes a listener based on the bean type or annotations on the bean's methods.

Merely creating an object with `new OrderAuditListener()` somewhere does not automatically register that object into the event system. The object must be managed by Spring in the context or registered using another explicit listener API.

## 2. Approach one: @Bean returning ApplicationListener

The direct approach is to create a bean implementing `ApplicationListener<E>`. The generic type `E` tells Spring which event the listener is interested in.

~~~java
public record OrderCreatedEvent(String orderId) {}

public class OrderAuditListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Audit: " + event.orderId());
    }
}
~~~

Registering the listener class:

~~~java
@Configuration
public class EventConfiguration {

    @Bean
    OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }
}
~~~

When a publisher emits `OrderCreatedEvent`, Spring selects listeners with a compatible event type and calls `onApplicationEvent`.

If the logic is short, you can use a lambda:

~~~java
@Bean
ApplicationListener<OrderCreatedEvent> orderAuditListener() {
    return event ->
        System.out.println("Audit: " + event.orderId());
}
~~~

Keep a specific generic type in the return type, such as `ApplicationListener<OrderCreatedEvent>`. Avoid the raw `ApplicationListener` type because the framework has less type information to resolve matching listeners.

If the listener needs dependencies, pass them through the constructor:

~~~java
public class OrderAuditListener
        implements ApplicationListener<OrderCreatedEvent> {

    private final AuditRepository repository;

    public OrderAuditListener(AuditRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        repository.record(event.orderId());
    }
}
~~~

The factory method can accept dependent beans as parameters:

~~~java
@Bean
OrderAuditListener orderAuditListener(AuditRepository repository) {
    return new OrderAuditListener(repository);
}
~~~

Spring resolves `AuditRepository` from the beans in the context when creating the listener. This keeps dependencies explicit and does not require the listener to look up the container itself.

Use `ApplicationListener<E>` when you want a dedicated class for events, want an explicit type contract, or need to also implement `Ordered` and related interfaces.

## 3. Approach two: @Bean returning a bean with an @EventListener method

A listener class is not required to implement `ApplicationListener`. A regular class can contain a method annotated with `@EventListener`:

~~~java
public class OrderNotificationListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Notify: " + event.orderId());
    }
}
~~~

Registering that class as a bean:

~~~java
@Configuration
public class EventConfiguration {

    @Bean
    OrderNotificationListener orderNotificationListener() {
        return new OrderNotificationListener();
    }
}
~~~

Spring detects `@EventListener` methods on managed beans and registers the corresponding listener adapters. When a matching event is emitted, the adapter invokes the bean's method. The class does not need to implement `ApplicationListener`.

Dependencies can be injected via constructor like other beans:

~~~java
public class OrderNotificationListener {

    private final NotificationService notificationService;

    public OrderNotificationListener(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        notificationService.sendOrderCreated(event.orderId());
    }
}
~~~

Factory method:

~~~java
@Bean
OrderNotificationListener orderNotificationListener(
        NotificationService notificationService) {
    return new OrderNotificationListener(notificationService);
}
~~~

A bean can declare multiple `@EventListener` methods to handle different event types. You should split methods or classes when tasks have distinct responsibilities so the configuration remains easy to read and test.

Do not place `@EventListener` on the `@Bean` factory method itself expecting Spring to register the return value as a listener. `@EventListener` marks the event-handling method inside a bean; the factory method's job is to create the bean.

## 4. Comparing the two listener styles

| Criterion | `ApplicationListener<E>` | Bean with `@EventListener` |
|---|---|---|
| How events are received | `onApplicationEvent(E)` | Method with an event parameter |
| Event type declaration | Generic type `E` | Method parameter type |
| Requires implementing an interface | Yes | No |
| One bean handling multiple event types | Can use multiple listeners or an appropriate structure | Can declare multiple methods |
| SpEL condition | No built-in equivalent condition annotation | Has `condition` |
| Suitable for | Dedicated listener class, explicit type contract | Concise handlers, multiple methods |

Both approaches are valid and can coexist in the same context. Choose one approach according to the listener's responsibility; there is no need to create both for the same task without a reason.

## 5. Bean name, scope, and lifecycle

The default bean name is the `@Bean` method name:

~~~java
@Bean
OrderAuditListener orderAuditListener() {
    return new OrderAuditListener();
}
~~~

The bean is named `orderAuditListener`. You can set an explicit name:

~~~java
@Bean("orderAudit")
OrderAuditListener orderAuditListener() {
    return new OrderAuditListener();
}
~~~

By default, the bean has singleton scope, meaning one instance is managed in the context. This is usually the right choice for listeners. If a listener holds mutable state in fields, multiple events may be processed on the same instance and create race conditions under concurrent execution. Prefer stateless listeners, keeping per-event data in local variables and letting dedicated services manage business state.

You can use dependency injection, lifecycle callbacks, and other bean features. However, avoid publishing business events from constructors or too early during context initialization, when other listeners may not be ready yet. Emit events after the context has refreshed and the required beans have been registered.

## 6. Listener registration conditions

One advantage of `@Bean` is that it can be combined with configuration annotations to decide whether the listener is created in the context.

For example, only register the audit listener in the `production` profile:

~~~java
@Configuration
public class EventConfiguration {

    @Bean
    @Profile("production")
    OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }
}
~~~

When the `production` profile is active, the bean is registered. If the profile is inactive, the factory method does not create the bean and that listener does not participate in event distribution.

`@Profile` can be applied to individual `@Bean` methods or to a configuration class. In Spring Boot, you can also use `@ConditionalOnProperty` if the appropriate Spring Boot dependency is included. `@ConditionalOnProperty` belongs to Spring Boot, not Spring Framework Core.

## 7. Listener execution order

If multiple listeners receive the same event, you can specify the order using `@Order` or by implementing `Ordered`.

For interface-based listeners, place the order on the class:

~~~java
@Order(1)
public class FirstOrderListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("First");
    }
}
~~~

For method-based listeners, place the order on the method:

~~~java
public class SecondOrderListener {

    @EventListener
    @Order(2)
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Second");
    }
}
~~~

The listeners above can still be created with `@Bean`. Smaller order values take precedence. If no order is declared, do not rely on factory method declaration order or bean names. If listeners run asynchronously, scheduling order does not guarantee completion order.

## 8. ApplicationEventMulticaster and listener detection

`ApplicationContext` uses `ApplicationEventMulticaster` to coordinate distributing events to matching listeners. In typical configurations, Spring uses `SimpleApplicationEventMulticaster` if the application does not provide its own multicaster bean named `applicationEventMulticaster`.

There are two listener detection mechanisms to distinguish:

- Beans implementing `ApplicationListener` are recognized by their interface and generic event type.
- `@EventListener` methods on beans are detected by `EventListenerMethodProcessor`, after which Spring registers adapters so the multicaster invokes the methods.

Therefore, registering a bean with `@Bean` ensures the listener is managed in the context; the bean type or method annotation determines how the listener is recognized.

With standard annotation configurations such as `AnnotationConfigApplicationContext`, the required processors are registered automatically. If building a low-level custom container, you must ensure annotation configuration processors are enabled so `@EventListener` is processed.

## 9. Complete example: registering two listeners with @Bean

The example below registers both listener styles in the same configuration:

- `OrderAuditListener` implements `ApplicationListener<OrderCreatedEvent>`.
- `OrderNotificationListener` is a regular bean with an `@EventListener` method.

The application uses Java 17 and Spring Context 6.2.0.

Directory structure:

~~~text
bean-event-listener-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanEventListenerDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>bean-event-listener-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BeanEventListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/BeanEventListenerDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class BeanEventListenerDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            service.create("ORD-3001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        OrderAuditListener orderAuditListener() {
            return new OrderAuditListener();
        }

        @Bean
        OrderNotificationListener orderNotificationListener() {
            return new OrderNotificationListener();
        }

        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    record OrderCreatedEvent(String orderId) {}

    @Order(1)
    static class OrderAuditListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println("Audit listener: " + event.orderId());
        }
    }

    static class OrderNotificationListener {

        @EventListener
        @Order(2)
        public void onOrderCreated(OrderCreatedEvent event) {
            System.out.println(
                "Notification listener: " + event.orderId()
            );
        }
    }

    static class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void create(String orderId) {
            System.out.println("Creating order: " + orderId);
            publisher.publishEvent(new OrderCreatedEvent(orderId));
            System.out.println("Service continues");
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Stdout result:

~~~text
Creating order: ORD-3001
Audit listener: ORD-3001
Notification listener: ORD-3001
Service continues
~~~

Both listeners are created and registered from `@Bean` factory methods. The interface listener is called via `onApplicationEvent`; the annotation listener is called via the adapter created by `@EventListener`. Both run synchronously, and the order is declared explicitly to determine execution sequence.

## 10. Testing listeners registered with @Bean

You can verify that the bean is registered in the context:

~~~java
try (var context =
         new AnnotationConfigApplicationContext(AppConfig.class)) {
    OrderAuditListener listener =
        context.getBean(OrderAuditListener.class);

    assert listener != null;
}
~~~

For important business logic, test the listener in isolation by calling its method or `onApplicationEvent` directly with mocked dependencies. Separate integration tests can confirm that the `@Bean` factory method creates the listener and that the multicaster actually distributes events.

Example of a listener with a dependency:

~~~java
class OrderAuditListener
        implements ApplicationListener<OrderCreatedEvent> {

    private final AuditRepository repository;

    OrderAuditListener(AuditRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        repository.record(event.orderId());
    }
}
~~~

In a unit test, instantiate the listener with a mock `AuditRepository` and call `onApplicationEvent` to verify behavior. This test does not need to start a Spring context. A separate integration test verifies the bean configuration and event distribution.

## 11. Common mistakes

| Mistake or misconception | Consequence | How to fix |
|---|---|---|
| Creating a listener with `new` without registering it as a bean | The context does not automatically detect that object. | Declare it with `@Bean` or an appropriate listener registration mechanism. |
| Placing `@EventListener` on a `@Bean` factory method | Confuses bean creation with event handling. | Place the annotation on the handling method inside the bean. |
| Using raw `ApplicationListener` | Lacks generic information about the event type. | Declare `ApplicationListener<SpecificEvent>`. |
| `@Bean` returning an overly generic type | Spring may lack type information during early listener detection. | Use a specific or fully parameterized return type. |
| Calling a factory method directly in a `proxyBeanMethods = false` configuration | May create a new object outside bean management. | Let the container inject dependencies via method parameters. |
| Listener holding mutable state without synchronization | Multiple events can cause race conditions. | Prefer stateless listeners or synchronize state properly. |
| Relying on `@Bean` declaration order | Execution order is not guaranteed by that assumption. | Use `@Order` or `Ordered`. |
| Publishing events too early during initialization | Other listeners may not be ready yet. | Publish after context refresh and once required beans are registered. |
| Thinking `@Bean` makes a listener asynchronous automatically | Listeners still run synchronously by default. | Configure async separately when appropriate. |

## 12. Checklist for registering listeners with @Bean

Before finalizing the configuration, check:

1. Is the factory method inside a configuration class processed by Spring?
2. Is the return value actually a listener class or a bean containing an `@EventListener` method?
3. If implementing `ApplicationListener`, is the generic event type specific?
4. If using `@EventListener`, is the method on a managed bean?
5. Are the listener's dependencies injected via constructor or factory method?
6. Do the profile or conditions match the deployment environment?
7. Is execution ordering via `@Order` needed?
8. Does the listener hold mutable state or run concurrently?
9. Should the listener run synchronously, asynchronously, or wait for transaction commit?
10. Has the configuration been verified with a context test or integration test?

Registering listeners with `@Bean` is an explicit way to bring event handlers into the application context. If you need a clear listener contract, create a bean implementing `ApplicationListener<E>`. If you want the handler to be a regular class with one or more methods, create a bean containing `@EventListener`. Spring manages both forms and registers them into `ApplicationEventMulticaster`. Keeping generic types specific, injecting dependencies explicitly, managing state safely, and declaring order when needed will keep listener configuration easy to understand and reliable.
