# Listeners in XML or Legacy Configuration

Spring Framework supports registering application event listeners in multiple ways. In traditional XML applications or older Spring codebases, the common approach is to declare a bean implementing **ApplicationListener<E>** in an XML configuration file. ApplicationContext automatically detects this bean and registers it with the event distribution system.

This approach still works in modern Spring applications. The core requirements are that the listener falls under ApplicationContext management, the event has a type compatible with the listener, and the publisher sends events to the right context.

## 1. What is a legacy-style listener?

Before the @EventListener annotation existed, the standard way to listen to application events in Spring was to implement the **ApplicationListener<E>** interface:

~~~java
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {

    void onApplicationEvent(E event);
}
~~~

The generic E must be ApplicationEvent or a subclass. Spring invokes onApplicationEvent(event) when a compatible event is published in the context.

Example:

~~~java
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Received order: " + event.getOrderId());
    }
}
~~~

This style is often called an interface-based listener or legacy listener because it existed since early Spring versions before @EventListener was introduced. The interface remains supported and is suitable when you want a class explicitly expressing the event-receiving contract.

With Java generics, you should declare a concrete type such as ApplicationListener<OrderCreatedEvent>. Older code may contain the raw ApplicationListener type, which loses type information and makes event filtering less clear. During maintenance, migrate gradually toward concrete generics if compatible with the APIs in use.

## 2. Registering ApplicationListener with XML

If the application uses XML bean configuration, declare the listener as an ordinary bean. Spring ApplicationContext automatically detects beans implementing ApplicationListener during refresh and registers them with ApplicationEventMulticaster.

Example applicationContext.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderCreatedListener"
          class="demo.OrderCreatedListener"/>

    <bean id="orderService"
          class="demo.OrderService"/>
</beans>
~~~

The two beans are declared directly by class name. No dedicated listener tag is required for ApplicationListener. During context initialization, Spring recognizes which bean implements the interface and registers that bean as a listener.

XML can also configure dependencies, constructor arguments, properties, scopes, or aliases just like any other bean. For instance, if the listener needs a repository, declare the repository and inject it via constructor or property using the existing configuration style.

### Registration lifecycle

The processing flow typically proceeds as follows:

1. GenericXmlApplicationContext reads the XML file and creates bean definitions.
2. The context instantiates beans and required infrastructure processors.
3. Spring detects beans implementing ApplicationListener and registers the listeners with the context.
4. Once context refresh completes, registered listeners are ready to receive events.
5. A publisher calls publishEvent(event); ApplicationEventMulticaster selects compatible listeners and invokes onApplicationEvent(event).

Therefore, listeners declared in XML still participate in the same internal event bus as listeners declared with @Component or @Bean. Only the bean registration mechanism differs; dispatching is still managed by ApplicationContext and the multicaster.

## 3. Creating legacy-style events

ApplicationListener<E> accepts a type extending ApplicationEvent. A custom event can carry the data needed by listeners:

~~~java
import org.springframework.context.ApplicationEvent;

public class OrderCreatedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderCreatedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Source is the object that originated the event. In the example, that could be OrderService. The orderId field holds the business data the listener needs.

Events should describe something that has happened, such as OrderCreatedEvent or PaymentCompletedEvent. Using past-tense naming helps listeners understand the meaning of the notification. Event data should remain stable after publishing; for payloads containing collections or mutable objects, consider defensive copying and immutable design.

### Distinguishing ApplicationEvent and POJO payloads

Since Spring Framework 4.2, ApplicationEventPublisher also supports publishing a plain POJO or record. Spring wraps the payload in PayloadApplicationEvent. However, ApplicationListener<E> still retains the constraint E extends ApplicationEvent.

If you want to keep using the interface for POJO payloads, the listener can accept the wrapper:

~~~java
public class OrderPayloadListener
        implements ApplicationListener<PayloadApplicationEvent<OrderCreated>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderCreated> event) {
        OrderCreated payload = event.getPayload();
        System.out.println(payload.orderId());
    }
}
~~~

If you want a method receiving OrderCreated directly, @EventListener is usually shorter. When maintaining legacy code using ApplicationListener<OrderCreatedEvent>, an event class extending ApplicationEvent remains the safest and most familiar option.

## 4. Publishing events from legacy beans

XML beans can emit events by receiving ApplicationEventPublisher. For traditional beans that do not use constructor injection or cannot easily inject the publisher through configuration, the **ApplicationEventPublisherAware** interface is a compatible option.

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;

public class OrderService implements ApplicationEventPublisherAware {

    private ApplicationEventPublisher publisher;

    @Override
    public void setApplicationEventPublisher(
            ApplicationEventPublisher eventPublisher) {
        this.publisher = eventPublisher;
    }

    public void createOrder(String orderId) {
        publisher.publishEvent(new OrderCreatedEvent(this, orderId));
    }
}
~~~

When Spring creates the bean, the aware callback supplies the publisher bound to the ApplicationContext managing the bean. The service can then call publishEvent without knowing which specific listeners will receive the event.

Another older approach is implementing ApplicationContextAware and calling applicationContext.publishEvent(...). However, if the bean only needs to publish events, ApplicationEventPublisherAware expresses a narrower and clearer dependency. Only use ApplicationContextAware when the bean genuinely needs other context APIs.

In new code, constructor injection is usually easier to test:

~~~java
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }
}
~~~

You can use constructor injection in XML via constructor arguments if the publisher is provided explicitly through configuration. ApplicationEventPublisherAware is helpful for compatibility with existing legacy bean structures.

## 5. Combining XML beans with annotation listeners

An application may declare beans in XML while still wanting to use @EventListener on methods. In that case, enable annotation processing using the context namespace:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

    <bean id="orderListener"
          class="demo.OrderAnnotationListener"/>
</beans>
~~~

The class can declare:

~~~java
public class OrderAnnotationListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Received: " + event.getOrderId());
    }
}
~~~

<context:annotation-config/> registers the annotation post-processors needed for annotation configuration on already declared beans. It does not scan packages to find beans. If you want component scanning, use context:component-scan with an appropriate base-package.

Distinguish two steps:

- Declaring the bean in XML makes the object belong to the ApplicationContext.
- Annotation processing detects and registers @EventListener methods on that bean.

If a bean already implements ApplicationListener, the context can register it by interface without needing context:annotation-config just for an interface-based listener.

## 6. Configuring the event multicaster in XML

Each ApplicationContext has an ApplicationEventMulticaster to distribute events. If no custom bean is declared, Spring uses the default SimpleApplicationEventMulticaster.

You can declare a bean with the conventional name applicationEventMulticaster to customize dispatch behavior:

~~~xml
<bean id="applicationEventMulticaster"
      class="org.springframework.context.event.SimpleApplicationEventMulticaster"/>
~~~

When asynchronous processing is needed, you can supply an executor to the multicaster. The example below illustrates wiring a ThreadPoolTaskExecutor:

~~~xml
<bean id="applicationEventExecutor"
      class="org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor">
    <property name="corePoolSize" value="2"/>
    <property name="maxPoolSize" value="4"/>
    <property name="queueCapacity" value="100"/>
    <property name="threadNamePrefix" value="app-event-"/>
</bean>

<bean id="applicationEventMulticaster"
      class="org.springframework.context.event.SimpleApplicationEventMulticaster">
    <property name="taskExecutor" ref="applicationEventExecutor"/>
</bean>
~~~

This is optional configuration. With default dispatch, listeners run synchronously on the event-publishing thread. When using an executor, listeners can run on another thread; the publisher does not necessarily wait for listeners to finish. Thread safety, completion order, and exception handling must be reviewed. Do not enable async merely because events are referred to as an event bus.

If an error handler is needed, you can configure SimpleApplicationEventMulticaster's errorHandler property with a bean implementing ErrorHandler. Define clear logging, retry, or error-ignoring policies; an in-process event multicaster does not provide durable persistence and retries like a message broker.

## 7. Complete example with XML and Java 17

The following example uses XML to register OrderService and OrderCreatedListener. OrderService obtains the publisher via ApplicationEventPublisherAware, creates an event extending ApplicationEvent, and publishes it. The listener implements ApplicationListener<OrderCreatedEvent>.

### Directory structure

~~~text
legacy-xml-event-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LegacyXmlEventDemo.java
        └── resources/
            └── applicationContext.xml
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>legacy-xml-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.0</spring.version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### applicationContext.xml

Place the file at src/main/resources/applicationContext.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderService"
          class="demo.LegacyXmlEventDemo$OrderService"/>

    <bean id="orderCreatedListener"
          class="demo.LegacyXmlEventDemo$OrderCreatedListener"/>
</beans>
~~~

XML declares two beans. OrderCreatedListener is automatically recognized by ApplicationContext because the class implements ApplicationListener. No separate listener registry declaration is needed.

### LegacyXmlEventDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;
import org.springframework.context.ApplicationListener;
import org.springframework.context.support.GenericXmlApplicationContext;

public class LegacyXmlEventDemo {

    public static void main(String[] args) {
        try (var context = new GenericXmlApplicationContext(
                "classpath:applicationContext.xml")) {

            OrderService service =
                    context.getBean("orderService", OrderService.class);

            service.createOrder("ORD-2001");
        }
    }

    public static class OrderCreatedEvent extends ApplicationEvent {

        private final String orderId;

        public OrderCreatedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static class OrderService
            implements ApplicationEventPublisherAware {

        private ApplicationEventPublisher publisher;

        @Override
        public void setApplicationEventPublisher(
                ApplicationEventPublisher eventPublisher) {
            this.publisher = eventPublisher;
        }

        public void createOrder(String orderId) {
            System.out.println("Created order: " + orderId);
            publisher.publishEvent(
                    new OrderCreatedEvent(this, orderId));
        }
    }

    public static class OrderCreatedListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println(
                    "Received OrderCreatedEvent: " + event.getOrderId());
        }
    }
}
~~~

### Compiling and running

Run in the directory containing pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.LegacyXmlEventDemo
~~~

Stdout result:

~~~text
Created order: ORD-2001
Received OrderCreatedEvent: ORD-2001
~~~

Explanation:

1. GenericXmlApplicationContext reads applicationContext.xml and creates the two beans.
2. When creating OrderService, Spring calls setApplicationEventPublisher and supplies the context's publisher.
3. The context recognizes OrderCreatedListener because the bean implements ApplicationListener<OrderCreatedEvent>.
4. main retrieves OrderService and calls createOrder.
5. The service publishes OrderCreatedEvent.
6. The default SimpleApplicationEventMulticaster distributes the event synchronously to OrderCreatedListener.
7. The listener receives the OrderCreatedEvent type directly and prints the order ID.

The nested classes are declared static so XML can reference them using binary names with the $ sign. In real projects, events, services, and listeners are typically placed in separate classes for a clearer package structure.

## 8. Listener ordering, errors, and transactions

### Execution ordering

If multiple ApplicationListeners receive the same event, you can use Ordered or @Order to specify priority order. Smaller order values have higher priority in ordered dispatch.

~~~java
@Order(1)
public class AuditListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Record audit.
    }
}
~~~

Only use ordering when business logic truly depends on it. If listeners are independent, do not create dependencies on incidental invocation order.

### Exceptions and async

With the default SimpleApplicationEventMulticaster, listeners run synchronously. Exceptions from a listener can propagate back to the publishEvent call if no ErrorHandler handles them. Slow listeners also increase the duration of the publisher's thread.

When an executor is configured, listeners can run asynchronously. The publisher may proceed before listeners finish; completion order is no longer guaranteed like synchronous dispatch. Dedicated logging and error handling are required for async tasks.

### Transaction-aware listeners

A regular ApplicationListener does not automatically tie callbacks to transaction phases. If you only want to process after a transaction commits, use @TransactionalEventListener with the AFTER_COMMIT phase when appropriate. This can be used on XML beans if annotation processing is enabled. An active transaction must exist at publish time for the listener to bind to that transaction.

Application events are an in-process mechanism. If requirements include retries, replay, durable persistence, or cross-service communication, use a message broker and appropriate persistence design instead of treating an XML listener as a durable queue.

## 9. When to keep XML or migrate to annotations?

| Situation | Appropriate choice |
|---|---|
| Application has stable existing XML configuration | Continue declaring listener beans in XML |
| Need compatibility with legacy interface listener classes | Keep ApplicationListener<E> |
| Want to handle events with methods and receive POJOs directly | Use @EventListener |
| Bean already declared in XML but want to use @EventListener | Enable context:annotation-config |
| Want to emit events from legacy beans | Use ApplicationEventPublisherAware |
| New code can design explicit dependencies | Prefer constructor injection with ApplicationEventPublisher |
| Need to handle events after transaction commit | Use @TransactionalEventListener with an appropriate transaction |

You do not need to convert the entire XML configuration to annotations just to use application events. XML beans, interface listeners, and annotation listeners can coexist in one context when annotation processing is configured properly.

## 10. Common mistakes

| Error | Cause | How to fix |
|---|---|---|
| Listener is not invoked | Class is not declared as a bean in the context | Add a bean definition or component scan |
| XML bean implements interface but does not receive events | Bean belongs to a different context from the publisher or event type is incompatible | Check the context managing the bean and the event type |
| Using raw ApplicationListener | Loses generic information and makes event filtering harder | Use ApplicationListener<OrderCreatedEvent> |
| Using a POJO as generic E | E must extend ApplicationEvent | Use PayloadApplicationEvent<Payload> or @EventListener |
| @EventListener on XML bean does not work | Annotation processing is not enabled | Add context:annotation-config or component scan |
| Calling publisher before context is ready | Listeners may not be fully registered yet | Publish from business flows after context refresh |
| Using ApplicationContextAware just to publish | Broader dependency than needed | Use ApplicationEventPublisherAware |
| Assuming listeners run in the background by default | SimpleApplicationEventMulticaster is synchronous by default | Configure an executor when justified |
| Using application events as a broker | No cross-process persistence/retry by default | Use an appropriate broker |

## 11. Checklist when maintaining XML/legacy applications

- Identify which XML file creates the ApplicationContext managing both publisher and listener.
- Verify the listener is declared as a bean and implements ApplicationListener with a concrete type.
- Ensure the event extends ApplicationEvent and carries the required data.
- Use ApplicationEventPublisherAware if legacy beans need to obtain the publisher from the context.
- Avoid publishing events inside constructors or before context refresh completes.
- If using @EventListener on XML beans, enable annotation processing.
- Check whether the multicaster has a custom executor or error handler configured.
- Test that events are published to the right context and listeners receive the right types.
- Keep existing XML configuration if it still meets requirements; migrate to annotations incrementally when there is a clear benefit.

**ApplicationListener<E> in XML/legacy remains a supported way to register listeners in Spring.** As long as the listener is declared as a bean in ApplicationContext, uses a compatible event type, and events are published through the context, the multicaster mechanism distributes events just as it does for listeners registered via annotations or Java configuration.