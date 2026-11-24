# Publishing Events from ApplicationContext

In Spring Framework, `ApplicationContext` is both the container managing beans and an implementation of the `ApplicationEventPublisher` contract. Therefore, whenever you have an application context, you can call `context.publishEvent(event)` directly to publish an event to matching listeners registered in the context.

This publication approach is useful at application startup, in integration code that manages the context, or when exploring Spring's event dispatch flow. In business services, you should generally inject `ApplicationEventPublisher` rather than depending on the entire `ApplicationContext`, because the service only needs the ability to publish notifications.

After this lesson, you will be able to:

- Explain the relationship between `ApplicationContext` and `ApplicationEventPublisher`.
- Publish events directly using `context.publishEvent(...)`.
- Distinguish events extending `ApplicationEvent` from POJO or record payloads.
- Register listeners using `@EventListener` and `ApplicationListener`.
- Describe the role of `ApplicationEventMulticaster` and dispatch scope in parent/child contexts.
- Recognize the default synchronous behavior and limitations of application events.
- Write a complete Java 17 program to publish events from `AnnotationConfigApplicationContext`.

## 1. Why Can ApplicationContext Publish Events?

`ApplicationContext` is the central interface of the Spring container. Beyond accessing beans, message sources, resources, and the environment, this interface also extends `ApplicationEventPublisher`. Consequently, every `ApplicationContext` implementation provides event-publishing methods.

Some key contracts:

| Contract | Role |
|---|---|
| `BeanFactory` and `ListableBeanFactory` | Accessing, looking up, and managing beans. |
| `MessageSource` | Resolving messages and supporting internationalization. |
| `ResourcePatternResolver` | Locating and reading resources using Spring's mechanism. |
| `EnvironmentCapable` | Accessing profiles and property sources. |
| `ApplicationEventPublisher` | Publishing events to matching listeners. |

Because it extends `ApplicationEventPublisher`, you can call:

~~~java
applicationContext.publishEvent(event);
~~~

`publishEvent` announces an occurrence to Spring's event mechanism. The publisher does not need to call listeners by name, know how many listeners exist, or receive an aggregated return value from listeners.

For example, after a report is generated, the application publishes `ReportGeneratedEvent`. One listener might record an audit entry, another might update metrics, and another might send a notification. The publisher simply publishes the event; each listener is responsible for its own task.

## 2. Publishing Events Directly from ApplicationContext

You can publish an event wherever you hold the context, such as in `main` after the context is initialized:

~~~java
var context = new AnnotationConfigApplicationContext(AppConfig.class);
context.publishEvent(new ReportGeneratedEvent("RPT-1001"));
context.close();
~~~

Prefer managing the context lifecycle with try-with-resources whenever possible:

~~~java
try (var context =
         new AnnotationConfigApplicationContext(AppConfig.class)) {
    context.publishEvent(new ReportGeneratedEvent("RPT-1001"));
}
~~~

The `AnnotationConfigApplicationContext` constructor accepting configuration classes registers the configuration, initializes the context, and performs a refresh. Once the context has refreshed, listener beans discovered during initialization can receive events.

Calling `context.publishEvent(...)` is appropriate when startup or integration code manages the context, an infrastructure component already holds the context, or when writing examples and tests to demonstrate the event mechanism. Do not pass `ApplicationContext` through multiple business layers solely to call `publishEvent`; that dependency is broader than necessary.

## 3. ApplicationContext and ApplicationEventPublisher

Both calls below use the same event-publishing contract:

~~~java
applicationContext.publishEvent(event);
~~~

~~~java
applicationEventPublisher.publishEvent(event);
~~~

Inside services, prefer injecting `ApplicationEventPublisher`:

~~~java
@Service
public class ReportService {

    private final ApplicationEventPublisher publisher;

    public ReportService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void generate(String reportId) {
        // Perform the report generation work.
        publisher.publishEvent(new ReportGeneratedEvent(reportId));
    }
}
~~~

This explicitly expresses the exact dependency the service requires, avoids coupling the service to the entire container API, and makes it easy to substitute a mock or stub publisher in unit tests.

Inject `ApplicationContext` only when a class genuinely needs other capabilities such as bean lookup, environment access, or resource loading. If the sole purpose is publishing events, `ApplicationEventPublisher` is the more appropriate dependency.

## 4. Event Forms Supported by publishEvent

Spring supports events extending `ApplicationEvent` as well as plain objects. The publisher API can accept either an `ApplicationEvent` or an arbitrary object as a payload.

### Events Extending ApplicationEvent

This is the traditional approach. The event class extends `ApplicationEvent` and passes a source to its constructor:

~~~java
public final class LegacyReportGeneratedEvent extends ApplicationEvent {

    private final String reportId;

    public LegacyReportGeneratedEvent(Object source, String reportId) {
        super(source);
        this.reportId = reportId;
    }

    public String getReportId() {
        return reportId;
    }
}
~~~

Publishing the event:

~~~java
context.publishEvent(
    new LegacyReportGeneratedEvent(this, "RPT-1001")
);
~~~

`source` is the object that originated the event according to the application's semantics. It is stored in `ApplicationEvent` and can be read with `getSource()`.

A listener can receive the event by its specific type:

~~~java
public class LegacyReportListener
        implements ApplicationListener<LegacyReportGeneratedEvent> {

    @Override
    public void onApplicationEvent(LegacyReportGeneratedEvent event) {
        System.out.println("Report: " + event.getReportId());
    }
}
~~~

### Publishing POJOs or Records

In modern code, custom events do not have to extend `ApplicationEvent`. You can publish a POJO, plain class, or record:

~~~java
public record ReportGeneratedEvent(String reportId) {}
~~~

Publishing the event:

~~~java
context.publishEvent(new ReportGeneratedEvent("RPT-1001"));
~~~

When the published object is not an `ApplicationEvent`, Spring wraps it in a `PayloadApplicationEvent` before dispatching. With `@EventListener`, the method can declare the payload type directly:

~~~java
@EventListener
public void onReportGenerated(ReportGeneratedEvent event) {
    System.out.println(event.reportId());
}
~~~

Records are concise and keep payloads immutable. Events should contain the business data listeners need, such as a report ID, order ID, or completed status. There is no need to create a subclass just to satisfy the event mechanism when a plain payload suffices.

| Scenario | Recommended Choice |
|---|---|
| New code, simple payload | A POJO or record is usually the cleanest option. |
| Compatibility with legacy systems already using event classes | Continue using classes extending `ApplicationEvent`. |
| Need to preserve the event source per legacy contracts | Use `ApplicationEvent` and a constructor accepting source. |
| Listener uses `@EventListener` | Can directly accept a POJO payload or an event class. |
| Listener implements `ApplicationListener` | Use the event type matching the listener contract. |

## 5. Registering Listeners to Receive Events

Publishing an event only creates a notification within the context. To process that notification, the application must register listeners as Spring beans.

### Using @EventListener

Annotate a method inside a Spring-managed bean:

~~~java
@Component
public class ReportListener {

    @EventListener
    public void onReportGenerated(ReportGeneratedEvent event) {
        System.out.println("Report generated: " + event.reportId());
    }
}
~~~

The method can accept a POJO payload or an event extending `ApplicationEvent`. The bean must be registered via component scanning or a `@Bean` method; an object instantiated with `new` outside the container will not automatically have its listener methods detected by Spring.

A single bean can have multiple `@EventListener` methods. Multiple beans can also listen to the same event type. Spring selects matching listeners based on the event type and declared conditions.

You can use a SpEL condition when a listener should only handle a specific subset of payloads:

~~~java
@Component
public class FinancialReportListener {

    @EventListener(condition = "#a0.reportId().startsWith('FIN-')")
    public void onFinancialReport(ReportGeneratedEvent event) {
        System.out.println("Financial report: " + event.reportId());
    }
}
~~~

`#a0` references the method's first parameter. Conditions should stay short and readable. If data queries or complex logic are required, move that logic into a service invoked by the listener.

### Using ApplicationListener

You can implement the listener interface:

~~~java
public class ReportListener
        implements ApplicationListener<LegacyReportGeneratedEvent> {

    @Override
    public void onApplicationEvent(LegacyReportGeneratedEvent event) {
        System.out.println("Report: " + event.getReportId());
    }
}
~~~

Register this implementation as a bean:

~~~java
@Configuration
class EventConfiguration {

    @Bean
    ReportListener reportListener() {
        return new ReportListener();
    }
}
~~~

`ApplicationListener<E>` is suitable when you want to model a listener as a bean implementing a dedicated contract. `@EventListener` is often more convenient when a bean has multiple handler methods or wants to receive POJO payloads directly.

## 6. Dispatch Mechanism Inside ApplicationContext

When `context.publishEvent(event)` is called, the application context forwards the event to the context's `ApplicationEventMulticaster`. The multicaster finds compatible listeners and coordinates invoking them.

~~~mermaid
flowchart TD
    A["ApplicationContext.publishEvent(event)"] --> B["Normalize event"]
    B --> C["ApplicationEventMulticaster"]
    C --> D["Find compatible listeners"]
    D --> E["Listener A"]
    D --> F["Listener B"]
    E --> G["Complete local dispatch"]
    F --> G
    G --> H["Forward to parent context if present"]
~~~

Key components:

- `ApplicationContext`: provides the event publication entry point and manages listener beans.
- `ApplicationEventMulticaster`: coordinates event dispatch.
- `SimpleApplicationEventMulticaster`: the default implementation typically used when the application does not declare a custom multicaster.
- `ApplicationListener` or `@EventListener` method: processes the selected event.

Spring discovers listener beans during context initialization. For `@EventListener` methods, Spring's annotation infrastructure locates annotated methods and registers corresponding adapters with the multicaster.

The multicaster is not an event log. It dispatches events at the moment they are published; it does not store history so that listeners registered later can replay old events.

## 7. Event Scope in Parent and Child Contexts

An application can have multiple `ApplicationContext` instances arranged in a hierarchy. A child context can reference a parent context.

When an event is published from a child context, it is dispatched within the child context and forwarded up to the parent context. As a result, a listener in the parent can receive events from the child if the event type matches.

The reverse does not happen automatically: events published in a parent context are not dispatched down to child contexts.

~~~text
Parent ApplicationContext
    ├── ParentListener
    └── Child ApplicationContext
          ├── ChildListener
          └── ChildService
~~~

If `ChildService` publishes an event from the child context, `ChildListener` can receive it in the child and `ParentListener` can receive the event forwarded to the parent. Listeners in another independent context do not automatically receive the event.

Forwarding to the parent is not a broadcast to every context in the process. If an application has multiple independent contexts, each context has its own listener scope.

## 8. Lifecycle Events Published by Spring

In addition to application-defined events, Spring publishes several events reflecting the lifecycle of the application context.

| Event | Meaning |
|---|---|
| `ContextRefreshedEvent` | The context has finished refreshing. |
| `ContextStartedEvent` | The context was requested to start via the lifecycle API. |
| `ContextStoppedEvent` | The context was requested to stop. |
| `ContextClosedEvent` | The context is closing. |

You can listen to refresh and close events:

~~~java
@Component
public class ContextLifecycleListener {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println("Context refreshed");
    }

    @EventListener
    public void onClosed(ContextClosedEvent event) {
        System.out.println("Context is closing");
    }
}
~~~

Lifecycle events are useful when you need to react to container state. However, if your actual need is managing the lifecycle of a specific bean, consider dedicated callbacks such as `@PostConstruct`, `SmartLifecycle`, or `DisposableBean` rather than general-purpose events.

## 9. Synchronous, Asynchronous, and Processing Order

With the default `SimpleApplicationEventMulticaster` and no executor configured, listeners run synchronously on the thread calling `publishEvent`. The publisher waits for listeners to complete before executing the next statement.

Consequences:

- Long-running listeners increase the publisher's processing time.
- Exceptions from synchronous listeners can propagate back to the `publishEvent` call site.
- Listeners invoked in the same dispatch pass can be affected if one listener throws an exception and no `ErrorHandler` handles it.
- The publisher does not receive an aggregated result from all listeners.

You can use `@Order` to declare listener invocation priority when a specific order is required. Lower order values have higher priority. Do not rely on bean registration order or method order in source code when no ordering contract is declared.

You can use `@Async` with `@EnableAsync` or configure an executor on the multicaster to offload execution to threads managed by an executor. In that case, the publisher can continue before listeners complete. Dedicated configuration is needed for the executor, exceptions, transactions, retries, and completion observability.

If a listener must run after a transaction commits, use `@TransactionalEventListener` with an appropriate phase, typically `TransactionPhase.AFTER_COMMIT`. Application events do not by themselves provide a durable queue or retry mechanism after a process crash.

## 10. Complete Example: Publishing Events Directly from ApplicationContext

This example uses Java 17 and Spring Context 6.2.0. The program creates an `AnnotationConfigApplicationContext`, registers a listener via `@Bean`, publishes a record event directly from the context, and then closes the context.

Directory structure:

~~~text
application-context-event-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationContextEventDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>application-context-event-demo</artifactId>
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
                    <mainClass>demo.ApplicationContextEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/ApplicationContextEventDemo.java

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ApplicationContextEventDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            context.publishEvent(
                new ReportGeneratedEvent("RPT-1001")
            );

            System.out.println("ApplicationContext.publishEvent returned");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        ReportListener reportListener() {
            return new ReportListener();
        }
    }

    record ReportGeneratedEvent(String reportId) {}

    static class ReportListener {

        @EventListener
        public void onReportGenerated(ReportGeneratedEvent event) {
            System.out.println(
                "Listener received report: " + event.reportId()
            );
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Expected stdout with the default synchronous multicaster:

~~~text
Listener received report: RPT-1001
ApplicationContext.publishEvent returned
~~~

The listener is registered by Spring from the `ReportListener` bean. When `context.publishEvent` is called, Spring wraps the record in `PayloadApplicationEvent` and dispatches it to the method taking `ReportGeneratedEvent`. The listener runs synchronously, so the listener's output appears before the next line in `main`.

## 11. Common Mistakes

| Mistake or Misconception | Consequence | Resolution |
|---|---|---|
| Thinking ApplicationContext cannot publish events | Overlooking the context's built-in API. | Remember that `ApplicationContext` implements `ApplicationEventPublisher`. |
| Passing ApplicationContext into every service | Services depend on unnecessary container capabilities. | Inject `ApplicationEventPublisher` when only publishing events. |
| Listener is not a Spring bean | `@EventListener` methods are not registered. | Register via `@Bean` or component scanning. |
| Event payload does not match listener parameter | Listener is not selected to receive the event. | Check both the event type and listener parameter type. |
| Assuming event publication stores history | Listeners registered later do not receive past events. | Use persistence or a message broker if replay is needed. |
| Assuming events reach every context | Independent or child contexts do not receive events as expected. | Understand context scope and upward forwarding to parents. |
| Assuming publishEvent always runs asynchronously | Default listeners may block the publishing thread. | Configure async when business rules allow. |
| Assuming publishEvent confirms all listeners succeeded | Publisher receives no aggregated business result. | Design separate logging, monitoring, and error handling. |
| Using application events for cross-process communication | Events only operate within the application's context mechanism. | Use a message broker or inter-process API. |
| Not managing context lifecycle | Associated resources or threads may not close cleanly. | Close the context via proper lifecycle management or try-with-resources. |

## 12. Checklist When Publishing Events from ApplicationContext

Before implementing, verify:

1. Does the publishing code genuinely need `ApplicationContext`, or only `ApplicationEventPublisher`?
2. Does the event have a clear, stable payload with sufficient data for listeners?
3. Is the listener registered as a bean in the appropriate context?
4. Are the event type and listener parameter type compatible?
5. Should the listener run synchronously or asynchronously?
6. Are there listener ordering requirements or exception-handling policies?
7. Does the event need to wait for a transaction commit?
8. Are there parent/child contexts and dispatch scope considerations to account for?
9. Are persistence, retries, or event replay required?
10. Is the context closed properly according to its lifecycle?

`ApplicationContext` publishes events through the `ApplicationEventPublisher` contract. The context receives the event, normalizes the payload when necessary, and hands it to `ApplicationEventMulticaster` for dispatch to matching listeners. Use `context.publishEvent(...)` where interacting directly with the context; inside business services, inject `ApplicationEventPublisher` to keep dependencies lean. Understanding payloads, listeners, context scope, and the execution model ensures events are published and handled in alignment with the application lifecycle.
