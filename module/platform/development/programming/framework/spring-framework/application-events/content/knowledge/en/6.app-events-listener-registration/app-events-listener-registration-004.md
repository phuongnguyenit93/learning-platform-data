# Registering Listeners via ConfigurableApplicationContext

Spring allows registering an §ApplicationListener§ directly into the ApplicationContext using the §ConfigurableApplicationContext.addApplicationListener(...)§ method. This approach is useful when a listener is created dynamically during application configuration, when events need to be heard before context refresh, or when you want to add and remove a listener tied to the lifecycle of a specific context.

This is programmatic listener registration. You provide an object implementing §ApplicationListener§, then pass that object to the context. Spring brings the listener into the context's event distribution mechanism.

## 1. What is ConfigurableApplicationContext?

§ApplicationContext§ is the central interface of the Spring container. It provides capabilities to retrieve beans, read resources, resolve messages, and publish application events. §ConfigurableApplicationContext§ extends context lifecycle configuration capabilities, including operations such as:

- §refresh()§: initializes or refreshes the context.
- §close()§: closes the context and releases resources.
- §addApplicationListener(...)§: registers an additional listener.
- §removeApplicationListener(...)§: removes a listener registered through the corresponding method.

You do not instantiate this interface directly. Instead, use implementations such as §AnnotationConfigApplicationContext§, §GenericApplicationContext§, or §ClassPathXmlApplicationContext§.

Example of declaring a variable by the interface:

~~~java
ConfigurableApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class);
~~~

Writing it this way makes the code depend on Spring's general configuration contract rather than a specific implementation.

## 2. The addApplicationListener(...) method

The API in Spring Framework 6.2 has the signature:

~~~java
void addApplicationListener(ApplicationListener<?> listener);
~~~

The parameter is an object implementing §ApplicationListener§. This interface has the generic type §E extends ApplicationEvent§, so a listener can explicitly declare the kind of event it handles.

Example:

~~~java
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("New order: " + event.getOrderId());
    }
}
~~~

When registering the listener:

~~~java
context.addApplicationListener(new OrderCreatedListener());
~~~

Spring adds the listener object to the context's listener list. When a compatible event is published, the listener receives that event through §onApplicationEvent(...)§.

The generic type helps Spring filter events by type. A listener accepting §OrderCreatedEvent§ will not be called for an unrelated event such as §ContextClosedEvent§. As a result, the handler method is strongly typed and requires no manual casting.

## 3. Registering before context refresh

If the context is not yet active, a listener added with §addApplicationListener(...)§ will be applied when the context refreshes. This is the right approach when you want to listen to context lifecycle events emitted during initialization.

Example:

~~~java
var context = new AnnotationConfigApplicationContext();

context.addApplicationListener(
        new ApplicationListener<ContextRefreshedEvent>() {
            @Override
            public void onApplicationEvent(ContextRefreshedEvent event) {
                System.out.println("Context refreshed: "
                        + event.getApplicationContext().getId());
            }
        });

context.register(AppConfig.class);
context.refresh();
~~~

In this example:

1. Create the context using the no-arg constructor. The context has not refreshed yet.
2. Register a listener for §ContextRefreshedEvent§.
3. Register the configuration class.
4. Call §refresh()§. Spring creates beans and emits the event indicating the context has refreshed.
5. Since the listener was registered beforehand, it receives the event.

Registering before refresh matters if the listener needs to receive events emitted during initialization. If registered after refresh, the listener will not retroactively receive events emitted prior to registration.

## 4. Registering after the context is active

You can also add a listener to an already active context:

~~~java
try (var context =
             new AnnotationConfigApplicationContext(AppConfig.class)) {

    OrderCreatedListener listener = new OrderCreatedListener();

    context.addApplicationListener(listener);

    context.publishEvent(new OrderCreatedEvent(context, "ORD-200"));
}
~~~

The §AnnotationConfigApplicationContext(AppConfig.class)§ constructor already registered the configuration and refreshed the context. Therefore, the §addApplicationListener(...)§ call happens after refresh.

According to the §ConfigurableApplicationContext§ contract, a listener added while the context is already active is placed into the current event multicaster immediately. Events published after registration can be received by the listener if the event type matches.

The two registration timings can be summarized as follows:

| Call timing | How Spring handles registration |
|---|---|
| Before context is active | Stores the listener to apply during refresh |
| After context is active | Adds the listener to the running event multicaster |

Choose the timing based on the events you need to receive. A listener that needs to catch §ContextRefreshedEvent§ must be registered before calling §refresh()§.

## 5. Complete example with Java 17+ and Spring Framework 6.2

The following example creates a listener in Java, registers it directly with §ConfigurableApplicationContext§, and then publishes an event when creating an order.

**Project structure**

~~~text
spring-context-listener/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ListenerRegistrationDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-context-listener</artifactId>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ListenerRegistrationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ListenerRegistrationDemo.java**

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ListenerRegistrationDemo {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            OrderCreatedListener listener = new OrderCreatedListener();

            // Register the listener before context refresh.
            context.addApplicationListener(listener);

            // Register configuration and initialize the context.
            context.register(AppConfig.class);
            context.refresh();

            // Retrieve the Spring-created service and publish an event.
            context.getBean(OrderService.class).createOrder("ORD-100");

            // You can remove the listener if it no longer needs to receive events.
            context.removeApplicationListener(listener);
        }
    }

    @Configuration
    public static class AppConfig {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    public static class OrderCreatedEvent extends ApplicationEvent {

        private static final long serialVersionUID = 1L;

        private final String orderId;

        public OrderCreatedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static class OrderCreatedListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println("Listener received order: "
                    + event.getOrderId());
        }
    }

    public static class OrderService {

        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void createOrder(String orderId) {
            System.out.println("Publishing order created event: " + orderId);
            publisher.publishEvent(new OrderCreatedEvent(this, orderId));
        }
    }
}
~~~

**Running the program**

From the directory containing §pom.xml§, run:

~~~bash
mvn -q compile exec:java
~~~

Output:

~~~text
Publishing order created event: ORD-100
Listener received order: ORD-100
~~~

**Execution flow explanation**

1. The program creates §AnnotationConfigApplicationContext§ without refreshing it yet.
2. Creates the §OrderCreatedListener§ object and calls §context.addApplicationListener(listener)§.
3. Registers §AppConfig§, then calls §context.refresh()§.
4. Spring instantiates §OrderService§ and injects §ApplicationEventPublisher§.
5. The program calls §createOrder("ORD-100")§.
6. The service publishes §OrderCreatedEvent§.
7. The event multicaster selects the listener typed for §OrderCreatedEvent§ and invokes §onApplicationEvent(...)§.
8. The program removes the listener using the same registered object, then closes the context when exiting the §try§ block.

The listener in the example is a directly registered Java object. It does not need §@Component§ or §@Bean§ to be invoked by the event multicaster.

## 6. Removing listeners with removeApplicationListener(...)

Spring Framework 6.0 and later provides the method:

~~~java
void removeApplicationListener(ApplicationListener<?> listener);
~~~

This method removes a listener registered via §addApplicationListener(...)§ from the context. Keep a reference to the listener so you can remove the exact same object:

~~~java
OrderCreatedListener listener = new OrderCreatedListener();

context.addApplicationListener(listener);

// When the listener is no longer needed:
context.removeApplicationListener(listener);
~~~

Do not create a new listener object when trying to remove an old object. The following example is not reliable:

~~~java
context.addApplicationListener(new OrderCreatedListener());

// A different object is created here:
context.removeApplicationListener(new OrderCreatedListener());
~~~

The two §new§ calls create two distinct instances. Keep a reference variable and reuse the registered instance.

Removing a listener is useful when the listener only needs to be active for a phase, such as a plugin being toggled or a component tied to a context's lifetime. When the context closes, Spring also releases resources managed by the context; there is no need to keep the listener active after the context has closed.

## 7. Differences from registering a listener as a bean

There are multiple ways for Spring to learn about a listener. Direct registration via the context must be distinguished from listeners managed as beans.

| Registration approach | Object to provide | Does Spring manage a bean? |
|---|---|---|
| §context.addApplicationListener(listener)§ | An §ApplicationListener§ instance | Does not automatically turn that instance into a bean |
| Bean implements §ApplicationListener<E>§ | Bean registered in the context | Yes |
| Method with §@EventListener§ | Method of a managed bean | Yes |

### Direct registration

With §addApplicationListener§, you are responsible for creating the listener and passing dependencies to it. Spring uses that instance to distribute events, but this call does not register the object into the BeanFactory, does not auto-inject dependencies, does not apply BeanPostProcessors, and does not create proxies for the listener.

For example, if the listener needs a service, you can instantiate it with the dependency obtained from the context:

~~~java
AuditService auditService = context.getBean(AuditService.class);
AuditListener listener = new AuditListener(auditService);

context.addApplicationListener(listener);
~~~

### Registering as a bean

A bean implementing §ApplicationListener§ is detected and registered by the ApplicationContext during refresh:

~~~java
@Component
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Handle the event.
    }
}
~~~

This approach is suitable when the listener needs dependency injection, lifecycle callbacks, AOP proxies, or other bean management features.

### Using @EventListener

If you want to handle events with a method without implementing an interface, you can use the annotation:

~~~java
@Component
public class OrderNotificationHandler {

    @EventListener
    public void handle(OrderCreatedEvent event) {
        System.out.println("New order notification: " + event.getOrderId());
    }
}
~~~

The method must belong to a Spring-managed bean for Spring to detect and register it. You cannot pass a POJO object that merely has an §@EventListener§ method directly into §addApplicationListener§, because that method requires an object implementing §ApplicationListener§.

## 8. Event types and payload objects

§ApplicationListener<E>§ declares §E§ as a subtype of §ApplicationEvent§. This is suitable when you want to register a listener with a specific event type.

Since Spring 4.2, publishers can also emit a plain Java object without extending §ApplicationEvent§. Spring's infrastructure wraps that object in a §PayloadApplicationEvent§.

If you want to create a listener for a payload while still registering directly with §ApplicationListener§, Spring provides the §ApplicationListener.forPayload(...)§ factory since Spring 5.3:

~~~java
ApplicationListener<PayloadApplicationEvent<String>> listener =
        ApplicationListener.forPayload(
                payload -> System.out.println("Payload: " + payload));

context.addApplicationListener(listener);
context.publishEvent("Hello Spring");
~~~

When publishing the string §"Hello Spring"§, the listener receives the payload through the consumer. If using this approach, also import:

~~~java
import org.springframework.context.PayloadApplicationEvent;
~~~

For business events with multiple fields and dedicated behavior, a concrete event class is usually easier to read. For simple payloads, §forPayload§ avoids writing a listener class solely to unwrap the payload.

## 9. Ordering, synchronicity, and reception scope

### Synchronous by default

With the default event multicaster, listeners normally run synchronously on the thread calling §publishEvent(...)§. The publisher waits for listeners to finish before continuing. However, §ConfigurableApplicationContext.addApplicationListener(...)§ only registers the listener; execution behavior also depends on the §ApplicationEventMulticaster§ and listener configuration.

If the context uses an executor for the multicaster or the listener supports asynchronous execution, the event may be handled on another thread. In that case, do not assume every listener finishes before §publishEvent§ returns.

### Context scope

A listener registered on a context belongs to that context's event multicaster. In applications with parent and child contexts, determine which context publishes the event and where each listener is registered. Events from a child context can propagate up to the parent according to the ApplicationContext hierarchy; events from a parent do not automatically propagate down to children.

### Listeners receiving context lifecycle events

Common context events include:

- §ContextRefreshedEvent§: the context has been refreshed.
- §ContextStartedEvent§: the context was asked to start.
- §ContextStoppedEvent§: the context was asked to stop.
- §ContextClosedEvent§: the context is closing.

If you want to listen to a lifecycle event, declare the exact generic type, such as §ApplicationListener<ContextClosedEvent>§. Register the listener before refresh if you need to receive §ContextRefreshedEvent§.

## 10. Common mistakes

- **Using the wrong context type:** §ApplicationContext§ only provides read and event-publishing APIs; §addApplicationListener§ belongs to §ConfigurableApplicationContext§. Use an implementation supporting the configurable interface.
- **Registering after refresh expecting past events:** Listeners only receive events from the time they are registered onward.
- **Calling refresh twice:** Some context implementations only allow refreshing once. With §AnnotationConfigApplicationContext§ using the constructor taking a configuration class, the context has already refreshed automatically; do not call §refresh()§ again.
- **Passing an object not implementing ApplicationListener:** §addApplicationListener§ requires the proper listener type. For annotated methods, register a bean with §@EventListener§.
- **Expecting Spring to auto-inject dependencies into a listener created with new:** Directly registered objects do not automatically become beans. Pass dependencies via constructor or use a listener bean.
- **Not keeping a reference when intending to remove the listener:** Store the instance in a variable and pass that exact instance to §removeApplicationListener§.
- **Confusing listener registration with event publishing:** §addApplicationListener§ only registers the recipient; publishers must still call §publishEvent(...)§.
- **Assuming listeners always run synchronously:** Check the multicaster configuration and listener async support before relying on completion order.

## 11. When should you use this approach?

Use §ConfigurableApplicationContext.addApplicationListener(...)§ when:

- You need to register a listener before refresh to receive context lifecycle events.
- The listener is created dynamically based on configuration or tied to a context's lifecycle.
- A module or plugin needs to register and remove its own listener when enabled/disabled.
- You need to attach a pre-constructed listener instance to a specific context.

Use a listener bean or §@EventListener§ when the listener is a fixed part of the application and needs Spring to manage dependencies, proxies, lifecycle, or transaction integration.

## 12. Implementation checklist

Before finalizing a programmatically registered listener, check:

1. Does the context implementation support §ConfigurableApplicationContext§?
2. Does the listener implement §ApplicationListener<E>§ with the right event type?
3. Is registration before or after refresh appropriate for the events to be received?
4. Was the listener created with all required dependencies?
5. Does the event publisher actually emit an event of a compatible type?
6. Did you keep the listener reference if removal is needed?
7. Have synchronous/asynchronous configuration and parent/child context scope been checked?
8. Is the context closed properly when no longer in use?

## 13. Key takeaways

§ConfigurableApplicationContext.addApplicationListener(...)§ registers an §ApplicationListener§ instance directly with the context. If called before refresh, Spring applies the listener during refresh; if the context is already active, the listener is added to the current event multicaster. Spring Framework 6.0+ also has §removeApplicationListener(...)§ to remove a registered listener.

This approach fits listeners created dynamically or needing to observe context lifecycle events. If a listener is a fixed part of the application and requires dependency injection or AOP, registering it as a bean is usually easier to manage.

## References

- [Spring Framework 6.2 — Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2.0 — ConfigurableApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [Spring Framework 6.2.0 — ApplicationListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring Framework 6.2.0 — ApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
