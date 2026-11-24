# Listeners in Java Configuration

## Objectives

After this lesson, you will be able to register Application Listeners using Java configuration, distinguish listener beans implementing ApplicationListener from methods using @EventListener, understand when Spring discovers and registers listeners, add listeners programmatically when needed, and choose the right configuration approach for each situation.

## 1. Where are listeners configured in Spring?

Spring Application Events allow a publisher to announce an occurrence and listeners to react to it. For Spring to invoke a listener, the listener must be registered with an ApplicationContext or ApplicationEventMulticaster.

In applications using Java configuration, there are three common approaches:

1. Declaring a bean implementing ApplicationListener using @Bean.
2. Declaring an @EventListener method inside a Spring-managed bean, including an @Configuration class.
3. Registering a listener directly using the ConfigurableApplicationContext API when you need programmatic control over registration timing.

All three approaches use the same Spring event distribution infrastructure. The difference lies in how the listener is defined, how Spring discovers it, and when the listener is added to the context.

Java configuration lets you declare listeners right in configuration source code, making dependencies easy to search and inspect. The listener remains a Spring-managed object; placing the declaration inside a configuration class does not turn the listener into a separate event mechanism.

## 2. Approach 1: Declaring ApplicationListener with @Bean

ApplicationListener is an interface that accepts a specific event type. When a bean implementing this interface is registered in the ApplicationContext, Spring detects it and adds it to the listener list.

For example, the application publishes the OrderPlaced payload. Because OrderPlaced is a plain record, Spring wraps the payload in PayloadApplicationEvent<OrderPlaced>. The listener implements ApplicationListener<PayloadApplicationEvent<OrderPlaced>> to receive the wrapper and read the payload:

~~~java
@Configuration(proxyBeanMethods = false)
class EventConfiguration {

    @Bean
    OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }
}

@Order(1)
class OrderAuditListener
        implements ApplicationListener<PayloadApplicationEvent<OrderPlaced>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderPlaced> event) {

        OrderPlaced order = event.getPayload();

        System.out.println("Audit: " + order.orderId());
    }
}
~~~

In the example:

- @Configuration marks the configuration declaration class.
- @Bean registers an OrderAuditListener instance into the ApplicationContext.
- OrderAuditListener implements ApplicationListener with a generic type explicitly specifying the event wrapper type.
- onApplicationEvent is the entry point Spring calls when a compatible event occurs.
- @Order(1) specifies the relative order of the listener when multiple listeners receive the same event.

If a publisher emits a class extending ApplicationEvent, the listener can declare that event class directly:

~~~java
@Bean
ApplicationListener<OrderPlacedEvent> orderPlacedListener() {
    return event -> System.out.println(event.getOrderId());
}
~~~

Here OrderPlacedEvent must extend ApplicationEvent. ApplicationListener does not accept an arbitrary POJO as its generic event type; for plain payloads, use PayloadApplicationEvent<T> or an @EventListener receiving the payload directly.

### Preserving generic types in @Bean declarations

You should declare a concrete return type, for example:

~~~java
@Bean
ApplicationListener<PayloadApplicationEvent<OrderPlaced>> orderAuditListener() {
    return event -> System.out.println(event.getPayload().orderId());
}
~~~

Avoid declaring a raw ApplicationListener or ApplicationListener<?> return type if Spring needs to infer the exact event type from the generic signature. Specific generic types help Spring filter events accurately and enable compile-time type checking by the compiler.

If you need a dedicated listener class, you can declare that class and return it from @Bean. If the logic is short, a lambda is also a good option.

## 3. Approach 2: Using @EventListener in a Java configuration bean

@EventListener marks a method as a listener. The method can reside on any Spring-managed bean, including:

- @Component classes.
- @Service classes.
- @Configuration classes.
- An object created and registered via a @Bean method.

For example, declaring listeners directly inside the configuration class:

~~~java
@Configuration(proxyBeanMethods = false)
class EventConfiguration {

    @EventListener
    @Order(1)
    void auditOrder(OrderPlaced order) {
        System.out.println("Audit: " + order.orderId());
    }

    @EventListener
    @Order(2)
    void sendConfirmation(OrderPlaced order) {
        System.out.println("Confirmation: " + order.orderId());
    }
}
~~~

The EventConfiguration class itself is a bean in the ApplicationContext. EventListenerMethodProcessor detects the @EventListener methods on this bean and registers corresponding adapters with ApplicationEventMulticaster.

The method parameter type is the event type the listener wants to receive. For payload objects, it can accept OrderPlaced directly. If you want to read the wrapper, declare PayloadApplicationEvent<OrderPlaced>:

~~~java
@EventListener
void inspectEnvelope(PayloadApplicationEvent<OrderPlaced> event) {
    System.out.println(event.getSource());
    System.out.println(event.getPayload().orderId());
}
~~~

There is no need to create an additional ApplicationListener class solely to receive a simple payload.

### Placing the listener in a bean created by @Bean

The listener method does not have to live inside the @Configuration class itself. You can separate responsibilities into its own class and declare a bean:

~~~java
@Configuration(proxyBeanMethods = false)
class EventConfiguration {

    @Bean
    OrderNotificationListener orderNotificationListener() {
        return new OrderNotificationListener();
    }
}

class OrderNotificationListener {

    @EventListener
    void notifyCustomer(OrderPlaced order) {
        System.out.println("Notify: " + order.orderId());
    }
}
~~~

When Spring creates the OrderNotificationListener bean, EventListenerMethodProcessor detects the method annotated with @EventListener and registers it. This style fits well when the listener has significant logic or needs its own injected dependencies.

## 4. When does Spring discover and register listeners?

Understanding the lifecycle helps avoid situations where a listener is written but Spring does not invoke it.

### ApplicationListener beans

When a bean implementing ApplicationListener is created and registered in the context, Spring recognizes it and adds it to the event distribution mechanism. Annotation-based contexts such as AnnotationConfigApplicationContext already install the infrastructure required to detect listener beans.

### @EventListener methods

Spring registers @EventListener methods through EventListenerMethodProcessor. This processor inspects beans and checks methods annotated with @EventListener, then creates ApplicationListener adapters to connect those methods to the multicaster.

Therefore, the key requirements are:

- The class containing the listener method must be a bean in the ApplicationContext.
- The method must be discovered by the annotation processing mechanism.
- Both the bean and the processor must be registered in the context publishing the event.
- The listener must be registered before the target event is published.

An object created with the new operator outside Spring does not automatically become a listener. If you instantiate the object yourself, you must register it via the corresponding API or place the object into the context as a bean.

### Why do listeners inside an @Configuration class work?

@Configuration is a kind of component registered as a bean. Therefore, @EventListener methods inside a configuration class are also detected by EventListenerMethodProcessor just like methods on other beans.

This is a valid style for small configurations. In larger applications, you can separate listeners into dedicated classes so the configuration class focuses solely on bean and dependency declarations.

## 5. Approach 3: Registering listeners programmatically

When you need to register a listener before ApplicationContext refreshes, or select listeners based on runtime configuration, you can use ConfigurableApplicationContext.addApplicationListener(...).

Example:

~~~java
public class ProgrammaticListenerDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {

            ApplicationListener<PayloadApplicationEvent<OrderPlaced>> listener =
                    event -> System.out.println(
                            "Programmatic: "
                                    + event.getPayload().orderId());

            context.addApplicationListener(listener);
            context.register(EventConfiguration.class);
            context.refresh();

            context.publishEvent(
                    new OrderPlaced("DH-7201", new BigDecimal("72000")));
        }
    }
}
~~~

Here:

1. Create the context in an unrefreshed state.
2. Create the ApplicationListener programmatically.
3. Call addApplicationListener to register the listener.
4. Register the configuration class and call refresh.
5. Publish the event after the context finishes initializing.

The advantage of this approach is that you can register a listener before refresh, including for events occurring during context startup. It is also useful when an application integrates optional plugins or modules and needs to decide at runtime which listeners are registered.

Distinguish addApplicationListener from adding a listener bean. A directly registered listener is managed by the context as a listener instance, but does not automatically become a bean with full dependency injection, lifecycle callbacks, or proxies like a regular bean. If the listener needs dependencies, using a Spring-managed bean is usually better.

Do not register the same listener via both @Bean and addApplicationListener unless you want it invoked twice.

## 6. Comparing the three registration approaches

| Approach | How it is declared | When suitable |
|---|---|---|
| ApplicationListener bean | @Bean returning ApplicationListener<E> | Listener has an explicit event type, independent logic, or needs an interface |
| @EventListener | Method on a Spring bean | Concise listener, handles payloads directly, easy to group by domain |
| addApplicationListener | Programmatic instance registration | Need registration before refresh or runtime listener selection |

Some selection guidelines:

- Prefer @EventListener for most business listeners that need to receive payloads.
- Use ApplicationListener when you want to represent the listener as a standalone bean/interface or work directly with event wrappers.
- Use addApplicationListener for special lifecycle/runtime requirements.
- Do not mix multiple approaches just to create unnecessary intermediate layers.

## 7. Listener execution order in Java configuration

Multiple listeners can receive the same event. Spring supports @Order or Ordered to specify relative ordering.

For @EventListener methods, place @Order on the method:

~~~java
@EventListener
@Order(1)
void writeAudit(OrderPlaced order) {
    System.out.println("Audit");
}

@EventListener
@Order(2)
void sendEmail(OrderPlaced order) {
    System.out.println("Email");
}
~~~

For ApplicationListener beans, you can place @Order on the class:

~~~java
@Order(1)
class OrderAuditListener
        implements ApplicationListener<PayloadApplicationEvent<OrderPlaced>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderPlaced> event) {
        System.out.println("Audit");
    }
}
~~~

Smaller order values take precedence. If no order is specified, the listener uses the default priority.

Only rely on listener ordering when it is an explicit requirement. If an email-sending listener may only run after another business step succeeds and needs that step's result, consider orchestrating the steps inside a service. @Order does not create a shared transaction and does not guarantee atomic processing.

## 8. Conditions, multiple event types, and return values

Java configuration integrates seamlessly with @EventListener capabilities.

### Multiple event types

When an action does not need event-specific data, you can declare multiple types using classes:

~~~java
@EventListener(classes = {
        ContextRefreshedEvent.class,
        ContextStartedEvent.class
})
void onContextLifecycle() {
    System.out.println("Context lifecycle event");
}
~~~

When declaring multiple types in classes, the method takes no event parameter. If you need to read event data, declare separate listeners for each type or use an appropriate common supertype.

### SpEL conditions

You can use condition to filter event instances after the event type matches:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
void notifyWebOrder(OrderPlaced order) {
    System.out.println("Web order: " + order.orderId());
}
~~~

The condition above runs the listener only when the payload's channel is WEB. Using #a0 references the first parameter without depending on whether parameter names are retained in bytecode.

Conditions should be short and describe only the event acceptance rule. Core business logic belongs inside the method body.

### Return values emitting subsequent events

An @EventListener method can return a non-void object. Spring publishes the return value as a new event:

~~~java
@EventListener
OrderAudited audit(OrderPlaced order) {
    return new OrderAudited(order.orderId());
}
~~~

This is convenient for short event chains. If the method runs asynchronously with @Async, the return value is not used to publish a subsequent event; in that case, inject ApplicationEventPublisher and publish explicitly.

## 9. Complete example with Java 17 and Spring Framework

The example uses two forms of Java configuration together: an ApplicationListener declared via @Bean and an @EventListener method inside the @Configuration class. Both receive the same OrderPlaced payload.

### Project structure

~~~text
java-configured-listeners/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── JavaConfiguredListenerDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>java-configured-listeners</artifactId>
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
                    <mainClass>demo.JavaConfiguredListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### JavaConfiguredListenerDemo.java

~~~java
package demo;

import java.math.BigDecimal;

import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class JavaConfiguredListenerDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(EventConfiguration.class)) {

            context.publishEvent(
                    new OrderPlaced("DH-7201", new BigDecimal("72000")));
        }
    }
}

record OrderPlaced(String orderId, BigDecimal total) {
}

@Configuration(proxyBeanMethods = false)
class EventConfiguration {

    @Bean
    OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }

    @EventListener
    @Order(2)
    void sendConfirmation(OrderPlaced order) {
        System.out.println("Confirmation: " + order.orderId());
    }
}

@Order(1)
class OrderAuditListener
        implements ApplicationListener<PayloadApplicationEvent<OrderPlaced>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderPlaced> event) {

        OrderPlaced order = event.getPayload();

        System.out.println(
                "Audit: " + order.orderId()
                        + ", total=" + order.total().toPlainString());
    }
}
~~~

### Running the program

In the directory containing pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Result:

~~~text
Audit: DH-7201, total=72000
Confirmation: DH-7201
~~~

### Execution flow analysis

1. AnnotationConfigApplicationContext receives EventConfiguration and initializes the context.
2. The @Bean method creates OrderAuditListener. Spring registers this bean as an ApplicationListener.
3. EventListenerMethodProcessor detects the sendConfirmation method annotated with @EventListener in EventConfiguration.
4. When publishEvent receives OrderPlaced, Spring wraps the payload into PayloadApplicationEvent<OrderPlaced>.
5. ApplicationEventMulticaster selects both OrderAuditListener and the sendConfirmation method because both listeners match the OrderPlaced payload.
6. @Order(1) causes audit to run first; @Order(2) causes confirmation to run second.
7. The context is closed after processing finishes via try-with-resources.

The key takeaway is that both listeners are configured in Java and automatically registered by Spring. The publisher does not need to call listener methods directly.

## 10. Common mistakes and how to fix them

### Declaring a listener without registering the bean

A class implementing ApplicationListener that is not placed into the ApplicationContext will not be invoked automatically by the context. Register it via @Bean, component scan, or the listener registration API.

### Placing @EventListener on an object not managed by Spring

The annotation does not automatically register an object created with new. Methods are only detected when the object is a bean in the context and EventListenerMethodProcessor processes that bean.

### Losing the generic type of ApplicationListener

Declaring a raw ApplicationListener or an overly broad return type can prevent Spring from inferring the exact event type. Preserve generic types in @Bean declarations and listener classes.

### Registering duplicate listeners

If the same instance is added with addApplicationListener and also registered as a bean, it can be called repeatedly. Choose a single appropriate registration mechanism per listener.

### Registering listeners too late

If an event was already published before a listener is registered, the listener does not retroactively receive the past event. Application Events do not store history for replay by default. For listeners that need events during refresh, consider registering before refresh with addApplicationListener.

### Putting business logic in the configuration class

An @Configuration class should focus on bean configuration. If a listener has complex logic, needs dependencies, or needs separate testing, extract it into a dedicated listener class and declare it via @Bean. This keeps configuration readable and gives the listener a clear responsibility.

### Expecting listeners to run asynchronously automatically

Java configuration only determines how listeners are registered. It does not automatically make listeners asynchronous. To process asynchronously, configure @Async/@EnableAsync or a task executor for ApplicationEventMulticaster and design appropriate error observation, thread context handling, and ordering.

## 11. Key takeaways

In Java configuration, you can register listeners via @Bean returning ApplicationListener, declare @EventListener methods in configuration beans, or call addApplicationListener when programmatic registration is needed.

ApplicationListener is suitable when you want a listener bean with an explicit event type. @EventListener is suitable for business methods receiving payloads directly. addApplicationListener is useful when registration is needed before refresh or based on runtime conditions. All three approaches connect to Spring's ApplicationEventMulticaster.

For listeners to work properly, the bean must be registered in the right ApplicationContext, generic types must be preserved clearly, and the listener must exist before relevant events are published. Use @Order when explicit ordering is required; use service orchestration when steps have mandatory business dependencies.

## Official references

- [ApplicationListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationListener.html)
- [EventListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [EventListenerMethodProcessor — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html)
- [ConfigurableApplicationContext — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [ApplicationEventMulticaster — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
