# ApplicationEventPublisherAware

## 1. What Is ApplicationEventPublisherAware?

ApplicationEventPublisherAware is an interface in the org.springframework.context package. A bean implementing this interface is notified by Spring of the ApplicationEventPublisher of the ApplicationContext managing that bean via the setApplicationEventPublisher(...) callback.

ApplicationEventPublisher is the abstraction used to publish events in Spring. After receiving the publisher, the bean can call publishEvent(...) without holding a reference to the entire ApplicationContext or knowing which listeners will receive the event.

This interface belongs to Spring's group of Aware callbacks. Aware interfaces allow the container to supply specific services or environment information to a bean during initialization. For example, BeanNameAware receives the bean name, BeanFactoryAware receives the BeanFactory, and ApplicationEventPublisherAware receives the publisher used to publish application events.

Abbreviated declaration:

~~~java
package org.springframework.context;

public interface ApplicationEventPublisherAware extends Aware {
    void setApplicationEventPublisher(
        ApplicationEventPublisher applicationEventPublisher
    );
}
~~~

In typical applications, ApplicationEventPublisher is usually injected directly via constructor. ApplicationEventPublisherAware is an alternative way to receive the publisher through a lifecycle callback, suitable for components that need to integrate with the Aware mechanism or stay compatible with an existing bean design.

## 2. When Does Spring Invoke the Callback?

When an ApplicationContext creates a bean, Spring performs initialization and preparation steps before the bean is ready to serve the application. During this process, ApplicationContextAwareProcessor checks which Aware interfaces the bean implements.

For ApplicationEventPublisherAware, Spring calls setApplicationEventPublisher(...) and passes the publisher bound to the context managing the bean. The callback is invoked after normal bean properties have been populated and before initialization callbacks such as InitializingBean.afterPropertiesSet() or a custom init-method.

The relevant sequence can be pictured as follows:

1. Spring instantiates the bean.
2. Spring injects dependencies and sets bean properties.
3. Spring invokes the appropriate Aware callbacks, including setApplicationEventPublisher(...).
4. Spring runs initialization steps such as @PostConstruct, afterPropertiesSet(), and custom init-method according to the lifecycle.
5. The bean finishes initialization and is put into use.

The exact ordering among bean processing mechanisms also depends on BeanPostProcessors and the application configuration. The key point to remember is that the publisher is provided during the bean's initialization phase, before initialization callbacks that might need it.

The callback is not automatically invoked when creating an object with the new operator. The bean must be managed by an ApplicationContext for the context's Aware mechanism to supply the publisher. If you instantiate the object manually in a unit test, you must invoke the callback manually or pass the publisher via another constructor designed for testing.

## 3. How to Implement the Interface

A class implementing ApplicationEventPublisherAware must define setApplicationEventPublisher(...). Typically, the class stores the publisher in a field for other methods to use:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;

import java.util.Objects;

public class OrderEventPublisher implements ApplicationEventPublisherAware {
    private ApplicationEventPublisher eventPublisher;

    @Override
    public void setApplicationEventPublisher(
            ApplicationEventPublisher applicationEventPublisher) {
        this.eventPublisher =
            Objects.requireNonNull(applicationEventPublisher);
    }

    public void publishOrderCreated(String orderId) {
        if (eventPublisher == null) {
            throw new IllegalStateException(
                "ApplicationEventPublisher has not been initialized"
            );
        }

        eventPublisher.publishEvent(new OrderCreated(orderId));
    }

    public record OrderCreated(String orderId) {
        public OrderCreated {
            Objects.requireNonNull(orderId, "orderId");
        }
    }
}
~~~

Several points in this example:

- The implementing class must declare the exact signature setApplicationEventPublisher(ApplicationEventPublisher).
- Use @Override so the compiler verifies that the method matches the interface.
- The field holding the publisher is typically private so only the bean uses it.
- Checking for null helps catch cases where the container has not supplied a publisher to the bean, especially when the object is created outside Spring.
- The business method calls publishEvent(...) to publish a strongly typed event.

There is no need to call setApplicationEventPublisher(...) from application code when the bean is properly managed by the ApplicationContext. This callback is executed by the container.

## 4. Registering the Bean and Using the Publisher

A bean implementing ApplicationEventPublisherAware must be registered in the ApplicationContext, for example via @Component, @Bean, or component scan configuration. Once the context initializes the bean, the publisher is assigned and business methods can use it.

Java configuration example:

~~~java
@Configuration
public class EventConfiguration {
    @Bean
    public OrderEventPublisher orderEventPublisher() {
        return new OrderEventPublisher();
    }
}
~~~

After the context finishes refreshing, you can retrieve the bean and call:

~~~java
OrderEventPublisher publisher =
    applicationContext.getBean(OrderEventPublisher.class);

publisher.publishOrderCreated("ORD-1001");
~~~

Spring dispatches the event to matching listeners in the context. The publishing bean does not need to call listeners directly, nor does it need to know how many listeners are registered.

If the bean is declared with @Component, ensure its package is within the component scan scope. If declared with @Bean, the factory method must belong to a configuration loaded into the context. Simply adding implements ApplicationEventPublisherAware to a class is not enough for Spring to discover and manage that class.

## 5. Combining with @EventListener

A listener can receive the event via a method annotated with @EventListener:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {
    @EventListener
    public void handle(OrderEventPublisher.OrderCreated event) {
        System.out.println("Created: " + event.orderId());
    }
}
~~~

When OrderEventPublisher calls publishEvent(new OrderCreated(...)), Spring looks for listeners whose parameter type is compatible with the event type. In this example, the listener receives the OrderCreated record directly.

The listener bean must also be registered in the same ApplicationContext or in a context with an appropriate hierarchical relationship. If the listener is not invoked, check bean registration, component scanning, the parameter type, and the context where the publisher was provided.

ApplicationEventPublisherAware only handles receiving the publisher. It does not automatically register listeners and does not change how Spring selects listeners. Listening still relies on @EventListener, ApplicationListener, or the corresponding listener registration mechanism.

## 6. ApplicationEventPublisherAware vs. Constructor Injection

There are two common ways for a bean to receive ApplicationEventPublisher:

| Criterion | ApplicationEventPublisherAware | Constructor injection |
|---|---|---|
| Mechanism | Spring invokes a lifecycle callback | Spring passes the dependency to the constructor |
| Timing | During bean initialization | At instance creation |
| Field | Usually assigned via setter callback | Can be declared final |
| Dependency | Expressed via an Aware interface | Visible directly in the constructor |
| Unit testing | Requires calling the callback or preparing a context | Pass fake/mock directly when instantiating the object |
| Best suited for | Infrastructure, lifecycle integration, Aware-compatible code | Standard business services and components |

Constructor injection example:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void createOrder(String orderId) {
        eventPublisher.publishEvent(new OrderCreated(orderId));
    }

    public record OrderCreated(String orderId) {
    }
}
~~~

For new application code, constructor injection is generally the clearer choice: the dependency is declared right in the constructor, the field can be final, and the object cannot be instantiated without a publisher through the standard constructor.

ApplicationEventPublisherAware is useful when a component is designed around Aware callbacks, when integrating with Spring infrastructure, or when maintaining a bean abstraction that already uses the callback mechanism. You should not implement this interface just to replace constructor injection across all services, because it makes the publisher dependency less visible in the constructor API.

Both approaches receive the publisher provided by the ApplicationContext. The difference lies in how the dependency is delivered and how the bean expresses its lifecycle.

## 7. Testing Beans That Implement Aware

When testing with a real ApplicationContext, register the bean and let Spring invoke the callback as it does in production. This is the right way to verify both publisher delivery and event receipt by listeners.

For unit tests that do not start Spring, you can pass a fake publisher by calling the callback directly. Example:

~~~java
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;

import java.util.ArrayList;
import java.util.List;

public class OrderEventPublisherTest {
    public static void main(String[] args) {
        List<Object> publishedEvents = new ArrayList<>();

        ApplicationEventPublisher fakePublisher =
            event -> publishedEvents.add(event);

        OrderEventPublisher publisher = new OrderEventPublisher();
        publisher.setApplicationEventPublisher(fakePublisher);
        publisher.publishOrderCreated("ORD-TEST");

        if (publishedEvents.size() != 1) {
            throw new AssertionError("Expected exactly one event");
        }

        OrderEventPublisher.OrderCreated event =
            (OrderEventPublisher.OrderCreated) publishedEvents.get(0);

        if (!"ORD-TEST".equals(event.orderId())) {
            throw new AssertionError("Unexpected order id");
        }

        System.out.println("PASS: one OrderCreated event was published");
    }
}
~~~

The fake publisher in this example stores events in a list so the test can check the count and payload. In a project using JUnit or Mockito, you can replace these with the corresponding assertions and verifications.

A unit test calling the callback directly verifies the bean's logic after receiving the publisher; it does not test whether ApplicationContextAwareProcessor automatically invokes the callback. To verify the actual lifecycle, add an integration test that creates the context and retrieves the bean from the context.

## 8. Complete Runnable Example

This example uses Java 17 and Spring Framework 6.2.0. OrderEventPublisher implements ApplicationEventPublisherAware, receives the publisher when the ApplicationContext initializes the bean, and then publishes a record. The listener receives the event with @EventListener.

Create the file src/main/java/demo/AwarePublisherDemo.java:

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

import java.util.Objects;

public class AwarePublisherDemo {
    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(OrderEventPublisher.class)
                .publishOrderCreated("ORD-1001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        OrderEventPublisher orderEventPublisher() {
            return new OrderEventPublisher();
        }

        @Bean
        OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }
    }

    public record OrderCreated(String orderId) {
        public OrderCreated {
            Objects.requireNonNull(orderId, "orderId");
        }
    }

    static class OrderEventPublisher
            implements ApplicationEventPublisherAware {
        private ApplicationEventPublisher eventPublisher;

        @Override
        public void setApplicationEventPublisher(
                ApplicationEventPublisher applicationEventPublisher) {
            this.eventPublisher =
                Objects.requireNonNull(applicationEventPublisher);
        }

        public void publishOrderCreated(String orderId) {
            if (eventPublisher == null) {
                throw new IllegalStateException(
                    "ApplicationEventPublisher has not been initialized"
                );
            }
            eventPublisher.publishEvent(new OrderCreated(orderId));
        }
    }

    static class OrderCreatedListener {
        @EventListener
        public void handle(OrderCreated event) {
            System.out.println("Received event for " + event.orderId());
        }
    }
}
~~~

Create the pom.xml file in the root directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>aware-publisher-demo</artifactId>
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
                    <mainClass>demo.AwarePublisherDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Expected stdout:

~~~text
Received event for ORD-1001
~~~

Execution flow:

1. AnnotationConfigApplicationContext loads AppConfig.
2. Spring creates OrderEventPublisher and OrderCreatedListener.
3. During OrderEventPublisher initialization, ApplicationContextAwareProcessor calls setApplicationEventPublisher(...).
4. The publisher is assigned to the eventPublisher field.
5. After context refresh completes, main retrieves the bean and calls publishOrderCreated(...).
6. The bean calls publishEvent(new OrderCreated(...)).
7. The listener receives the event synchronously and prints the order ID.
8. try-with-resources closes the context.

## 9. Common Errors and How to Handle Them

- Callback is not invoked: check whether the object is created and managed by the ApplicationContext. Objects created with new do not automatically receive the callback.
- eventPublisher remains null: verify that the callback method is implemented with the exact signature and that the bean is managed by the context. Do not invoke business methods before bean initialization completes.
- Listener does not receive the event: verify that the listener is a bean, belongs to the appropriate context, and that the @EventListener parameter is compatible with the event.
- Implementing Aware while still injecting ApplicationContext: if you only need to publish events, keeping ApplicationEventPublisher is sufficient; there is no need to depend on a broader API.
- Using the callback to hide dependencies: for new business services, constructor injection usually makes dependencies clearer.
- Creating a mutable event and modifying it after publishing: listeners may observe altered data. Use records, final fields, and immutable data.
- Assuming events are persisted and replayed: ApplicationEventPublisher does not provide persistence or retries. Use a message broker or outbox when delivery guarantees are needed.
- Calling the callback multiple times in business code: this is a container lifecycle responsibility. Do not use the callback as an ordinary configuration method.

## 10. Adoption Workflow

1. Confirm that the bean genuinely needs to receive ApplicationEventPublisher via a lifecycle callback.
2. Ensure the bean is registered in the ApplicationContext.
3. Implement ApplicationEventPublisherAware and setApplicationEventPublisher(...) with the exact signature.
4. Store the publisher in a private field and validate the input.
5. Call publishEvent only after the bean has completed initialization and the business operation has reached the state that requires notification.
6. Register listeners using @EventListener or ApplicationListener.
7. Test both the callback in a real ApplicationContext and the publishing logic with a fake publisher.

ApplicationEventPublisherAware acts as a bridge between a bean's lifecycle and Spring's event-publishing mechanism. When used in the right place, this interface helps a component receive the publisher from the context without having to look up listeners itself. For ordinary services, constructor injection remains the clearer choice because dependencies are expressed directly when the object is created.