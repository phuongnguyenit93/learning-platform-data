# ContextClosedEvent in the Spring Framework ApplicationContext Lifecycle

## 1. Concept and role

**ContextClosedEvent** is the lifecycle event Spring publishes when an **ApplicationContext** is closed according to the container's shutdown procedure. The class **org.springframework.context.event.ContextClosedEvent** extends **ApplicationContextEvent**; listeners can use **event.getApplicationContext()** to know the exact context that published the event.

This event answers the question **"A Spring ApplicationContext is starting to close; what do relevant components need to know?"**. It is useful for logging, telemetry, stopping acceptance of new tasks, or brief notifications about shutdown. However, merely receiving the event **does not mean** resources are already closed, asynchronous work has completed, or cleanup is guaranteed when the JVM is forcibly killed.

In standalone applications, the familiar closing path is **ConfigurableApplicationContext.close()** or **try-with-resources** on **AnnotationConfigApplicationContext**. In web or Spring Boot applications, the framework usually takes charge of coordinating the context lifecycle and publishes this event when the context actually closes.

This is a **container event**, not a business event like **OrderCancelled** or **UserLoggedOut**. You should not rely on ContextClosedEvent to record critical business transactions at the last moment, because process failures can prevent shutdown callbacks from running.

## 2. When does ContextClosedEvent occur?

A typical lifecycle:

~~~text
Create ApplicationContext
       |
       v
refresh()
  -> ContextRefreshedEvent
       |
       v
Context is active, processing business logic
  -> start() -> ContextStartedEvent (when calling start API)
  -> stop()  -> ContextStoppedEvent (when calling stop API)
       |
       v
close() or shutdown hook closes context
  -> ContextClosedEvent
  -> LifecycleProcessor.onClose(): stop Lifecycle/SmartLifecycle beans
  -> destroyBeans(): destroy singleton beans and invoke destroy callbacks
  -> close BeanFactory, clean up context state
       |
       v
Context is closed
~~~

In the **AbstractApplicationContext.doClose()** implementation, Spring publishes **ContextClosedEvent** in the early stage of the closing procedure, **before** asking the lifecycle processor to stop lifecycle beans and before destroying singleton beans. Therefore, a **synchronous** listener receiving ContextClosedEvent can often still observe some beans not yet destroyed. That does not guarantee every resource remains available for long tasks or pending async operations.

Points to distinguish:

- **Event has been published**: Spring has announced that the context is closing.
- **Synchronous listener has returned**: that listener's notification handling has completed.
- **Container has finished closing**: lifecycle stop and singleton destruction steps have been requested/executed.
- **Application has exited the process**: still depends on the JVM, server/container, and other threads.

Do not equate the four milestones above. **ContextClosedEvent** does not mean all beans have already been destroyed at the moment the listener is invoked.

## 3. Common ways the event is published

### 3.1. close() or try-with-resources

~~~java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Use Spring-managed beans.
}
// End of try block: AutoCloseable.close() is called.
~~~

This is an **illustrative snippet** requiring the application's **AppConfig** class. **AnnotationConfigApplicationContext** implements the **ConfigurableApplicationContext** contract and can be used in try-with-resources. When exiting the try block normally or via an exception, Java calls **close()** to close the context.

An application can also call **context.close()** directly. This is an action to close the entire container, not an API to pause a single business task.

### 3.2. Shutdown hook

For a program creating its own context, you can register:

~~~java
ConfigurableApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class);
context.registerShutdownHook();
~~~

This is an **illustrative snippet**, requiring **AppConfig** and appropriate imports. Spring registers a shutdown hook to call context close when the JVM performs a normal shutdown that runs hooks. Spring Boot usually already manages graceful shutdown/context closing according to framework configuration; do not duplicate hooks without reason.

**Limitation:** there is no guarantee hooks will run on **SIGKILL/kill -9**, power loss, severe crash, or when terminated by the runtime without sufficient time. "Must-complete" work needs durable state, retries, and idempotency while the application is still running.

### 3.3. Framework closing web/child contexts

In servlet/web applications, the framework/runtime may close the context when the application stops or redeploys. In systems with multiple parent/child contexts, **each context** has its own lifecycle and can publish its own close event.

An event published by a child context can propagate up to the parent context. Thus a parent listener can see **a child's ContextClosedEvent**. Just because a callback runs in the parent does not mean the event was published by the parent; use **event.getApplicationContext()** to tell them apart.

### 3.4. Does manually creating the event cause the context to close?

**No.** Calling **publisher.publishEvent(new ContextClosedEvent(context))** only sends an event object to listeners; it **does not replace** **ConfigurableApplicationContext.close()**, does not automatically stop the lifecycle processor, and does not destroy the bean factory. This sends a false signal to the system, so use the proper context-closing API.

## 4. Listening with @EventListener

A bean can receive the event:

~~~java
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ShutdownObserver {
    @EventListener
    public void onClosed(ContextClosedEvent event) {
        System.out.println("Context closing: "
                + event.getApplicationContext().getId());
    }
}
~~~

This is a **code snippet in an application with component scanning**, not a standalone program. Spring finds the **@EventListener** method, creates a listener adapter, and calls it when an event of the matching type is dispatched. **getId()** helps distinguish multiple contexts; it is not necessarily the process name or hostname.

Ordering can be declared when there are multiple listeners:

~~~java
@EventListener
@Order(10)
public void onClosed(ContextClosedEvent event) {
    // Brief, synchronous reaction if @Async is not used.
}
~~~

You need to import **org.springframework.core.annotation.Order** and place the method in a Spring-managed bean. Lower order numbers are prioritized first in multicasters that support ordering. **@Order** orders dispatch, not the **completion** order of asynchronous listeners.

For the default **SimpleApplicationEventMulticaster**, regular listeners run synchronously when called. If you configure a custom executor for the multicaster or use **@Async**, blocking behavior and exception handling change; shutdown may proceed before async tasks finish.

## 5. Listening with ApplicationListener<ContextClosedEvent>

An alternative is implementing the interface:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;

public class ExplicitCloseListener
        implements ApplicationListener<ContextClosedEvent> {

    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        System.out.println("Closing: "
                + event.getApplicationContext().getId());
    }
}
~~~

You must register this object as a bean or register it with the context using the appropriate API. Simply declaring the class outside Spring will not cause the listener to be called automatically.

| Style | Suitable when | Notes |
| --- | --- | --- |
| **@EventListener** | You want concise methods, one bean handling multiple event types | Bean must be Spring-managed; valid method signature |
| **ApplicationListener<ContextClosedEvent>** | You want the listener expressed explicitly by interface, easy explicit registration | Must register instance; event type is defined in generic type |

Using both for the same logic can cause shutdown handling to run twice. Choose one style and verify the invocation count in practice.

## 6. Compilable/runnable Java 17+ example: stop differs from close, event before destroy

The example uses **Spring Framework 6.2.9**, **Java 17+**, **Gradle 8.x**. No Spring Boot or external server is needed.

Directory structure:

~~~text
context-close-demo/
  build.gradle
  src/main/java/demo/ContextCloseDemo.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.ContextCloseDemo'
}
~~~

**src/main/java/demo/ContextCloseDemo.java**:

~~~java
package demo;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

public class ContextCloseDemo {

    public static class EventObserver {
        @EventListener
        public void onStopped(ContextStoppedEvent event) {
            System.out.println("event: stopped");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            System.out.println("event: closed");
        }
    }

    public static class ManagedResource implements DisposableBean {
        @Override
        public void destroy() {
            System.out.println("resource: destroyed");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        EventObserver eventObserver() {
            return new EventObserver();
        }

        @Bean
        ManagedResource managedResource() {
            return new ManagedResource();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            System.out.println("context: running");

            context.stop();
            System.out.println("after: stop");

            context.start();
            System.out.println("after: start");

            System.out.println("before: close");
        }

        System.out.println("after: close");
    }
}
~~~

In the **context-close-demo** directory, run with JDK 17+ and Gradle 8.x:

~~~bash
gradle --console=plain -q run
~~~

**Lines printed by the program** (ignoring other logs if added automatically by the environment):

~~~text
context: running
event: stopped
after: stop
after: start
before: close
event: closed
resource: destroyed
after: close
~~~

Analysis:

1. The **AnnotationConfigApplicationContext(Config.class)** constructor creates and refreshes the context, registering the **EventObserver** and **ManagedResource** beans.
2. **context.stop()** invokes the lifecycle stop mechanism and then publishes **ContextStoppedEvent**; the **onStopped(...)** listener prints **event: stopped**. It **does not** publish ContextClosedEvent, so the context can still be **start()**-ed again.
3. **context.start()** asks lifecycle beans to start and publishes **ContextStartedEvent**. The program does not register a log-printing listener for this event type.
4. Upon leaving try-with-resources, **close()** is called. Spring publishes **ContextClosedEvent**, hence **event: closed** is printed.
5. Afterward, the **ManagedResource** bean is destroyed and **DisposableBean.destroy()** prints **resource: destroyed**. **after: close** is only printed once the **close()** call has returned.

The demo intentionally uses **DisposableBean** to observe the destroy callback without adding a Jakarta annotations dependency. **@PreDestroy**, **destroyMethod**, or **SmartLifecycle** can also be used in real applications.

This is not an illustration of transactions, network handling, or guarantees when the JVM is killed. There is only one resource bean; in real applications, the destruction order of multiple beans is also affected by dependency relationships and container configuration.

## 7. Distinguishing lifecycle events and hooks

| Event or hook | Timing | Semantics |
| --- | --- | --- |
| **ContextRefreshedEvent** | After context is initialized/refreshed successfully | Container has been refreshed |
| **ContextStartedEvent** | When **start()** is called | Publishes the context lifecycle start signal |
| **ContextStoppedEvent** | When **stop()** is called | Stops lifecycle beans; can be started again if context remains open |
| **ContextClosedEvent** | When context begins the closing procedure | Notifies that the container is shutting down |
| **@PreDestroy / DisposableBean.destroy()** | When bean is destroyed | Cleans up resources managed by the bean |
| **SmartLifecycle.stop(Runnable)** | When lifecycle processor stops bean | Coordinates stopping task intake and completing shutdown |
| **ApplicationReadyEvent** *(Spring Boot)* | When Boot application finishes startup | Boot-specific event; not a context-closing event |

**stop() differs from close():** stop generally targets halting lifecycle components inside a still-living context. Close targets destroying the context and singleton beans. If you need to pause a scheduler/worker, use the stop API or the worker's own controls, do not close the entire context.

**Event listener differs from destroy callback:** ContextClosedEvent notifies of a lifecycle transition; a destroy callback is where resources owned by a bean are directly closed. A bean may receive the close event and still have a destroy callback afterward, yet the two hooks serve different purposes.

## 8. Choosing the cleanup approach with the right responsibility

### 8.1. Use ContextClosedEvent when you need to know the context is closing

Appropriate tasks:

- Recording a brief metric or audit of the shutdown start time, if the recording system is still available.
- Switching internal state to "shutting down" to reject new work requests.
- Emitting a brief signal to an internal coordination unit when the context closes.
- Inspecting and logging the context ID for debugging in multi-context systems.

Do not use a listener to wait on batches of long-running tasks, spawn unbounded new jobs, or send network requests without timeouts.

### 8.2. Use @PreDestroy / DisposableBean for bean-owned resources

If a bean opens a file handle, dedicated thread pool, socket, or connection, that bean should own how the resource is closed. Spring supports **@PreDestroy**, **DisposableBean.destroy()**, bean-configured destroy methods, or compatible close APIs. When a singleton is destroyed, Spring invokes the callback according to the bean's managed lifecycle.

For resources created by a bean, placing cleanup inside the resource-owning bean can be tested independently and avoids depending on whether an external observer receives an event.

### 8.3. Use SmartLifecycle for ordered stopping

**SmartLifecycle** fits background components that need to stop accepting work, drain existing tasks, and then report stopped. It supports **start()**, **stop(Runnable callback)**, **isAutoStartup()**, **getPhase()**, and **isRunning()**.

During shutdown, the lifecycle processor can use phase and dependencies to decide stop order; normally beans with higher phase stop before beans with lower phase. **stop(Runnable callback)** should invoke the callback when stopping has actually finished, so the container can coordinate the next step. Timeouts and time bounds for draining are needed; do not wait indefinitely.

| Need | Priority |
| --- | --- |
| Brief notification that the context is closing | **ContextClosedEvent** |
| Closing specific resources owned by a bean | **@PreDestroy**, **DisposableBean**, or destroy method |
| Stopping multiple workers in order and waiting for completion | **SmartLifecycle** |
| Recording work that must not be lost when the process dies | Persistent queue/outbox/checkpoint **before** shutdown |
| Pausing operations and restarting them later | **Lifecycle/SmartLifecycle** or dedicated mechanism, do not use close |

## 9. Risks when handling context closing

### 9.1. Executors and @Async shutting down

If a **ContextClosedEvent** listener uses **@Async**, calls to the executor may be queued, run late, or be rejected during the stop phase; resources serving the task may be destroyed prematurely. Therefore, do not equate "dispatched async" with "cleanup completed".

With a long-running synchronous listener, **close()** can block until the listener returns, causing graceful shutdown timeouts to be exceeded. The solution is to keep listeners short, set reasonable timeouts, and move coordinated stopping work into a lifecycle component.

### 9.2. Spring does not guarantee events when the process is forcibly killed

During **kill -9**, power loss, or when the container runs out of time, **ContextClosedEvent** may not occur. To avoid losing data, persist durably before shutdown, design retry/idempotency after restart, or use health/readiness mechanisms to shed load before stopping the service.

### 9.3. Exceptions in listeners are not a way to cancel shutdown

A listener may throw an exception during closing. **AbstractApplicationContext** attempts to continue cleanup even when publishing the close event encounters an error; an exception is not a rollback or a mechanism ensuring the application stays running. Error logs need enough detail to diagnose the root cause; avoid swallowing every **Throwable** and claiming cleanup succeeded.

### 9.4. Transactions are not automatically present in ContextClosedEvent

Closing an ApplicationContext does not happen inside a business transaction by default. A **@TransactionalEventListener(ContextClosedEvent)** method might not be invoked if there is no compatible transaction. To observe shutdown, use a regular **@EventListener**. If DB writes are needed during shutdown, account for the possibility that the transaction manager and data source may already be shut down or shutting down, close duration, and idempotency.

Do not handle mandatory financial business logic in **ContextClosedEvent**. Critical data must be committed and/or placed into an outbox during normal business transactions.

### 9.5. Presence of parent/child ApplicationContexts

Events published in a child can propagate to the parent. A listener in the parent can see a child's close event. If you only want to react to the context owning the bean, filter by object identity:

~~~java
@Component
class LocalContextObserver {
    private final ApplicationContext own;

    LocalContextObserver(ApplicationContext own) {
        this.own = own;
    }

    @EventListener
    public void onClose(ContextClosedEvent event) {
        if (event.getApplicationContext() != own) {
            return;
        }
        // The exact context owning this bean is closing.
    }
}
~~~

This is an **illustrative snippet**; you must import the corresponding Spring types and use it in an application with component scanning. In multi-context systems, test the closing order and the case where the parent receives the child's events separately to avoid duplicate handling.

## 10. Testing the lifecycle properly instead of only calling listener methods

To verify a **ContextClosedEvent** listener, run through a real **ApplicationContext**:

1. Create the context with the listener and resource bean.
2. Call **context.stop()**, verify **ContextStoppedEvent** is received and ContextClosedEvent is not yet received.
3. Call **context.start()**, verify the context is still active and the start event is not confused with close.
4. Call **context.close()**, verify the listener receives a ContextClosedEvent from the expected context.
5. Cross-check the log/event list order: **ContextClosedEvent** before the resource's **destroy()** in the default closing flow.
6. With a hierarchy, verify **event.getApplicationContext()** is the child or parent as expected.
7. With failing listeners or executors, verify log policies, timeouts, stop, and cleanup are appropriate.

You can record traces using a synchronized **List<String>** or **AtomicInteger** in integration tests, avoiding arbitrary **Thread.sleep(...)** calls to conclude a callback has finished. A unit test calling **onClosed(new ContextClosedEvent(...))** directly only tests method body logic and **does not prove** Spring published the event at the right phase.

## 11. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Waiting for ContextClosedEvent after only calling **stop()** | Close listener does not run | Distinguish ContextStoppedEvent from ContextClosedEvent |
| Thinking ContextClosedEvent occurs after all **@PreDestroy** calls | Wrong observation point and resource reasoning | Remember Spring publishes the close event before singleton destruction |
| Using the close event to clean up all resources | Unclear ownership, easy ordering bugs, and missing timeouts | Clean up in resource owner or SmartLifecycle |
| Using **@Async** for mandatory cleanup | Executor may stop before the task completes | Use coordinated lifecycle hooks with timeouts |
| Manually publishing **new ContextClosedEvent(...)** to shut down the app | Only sends a notification; context is still not closed | Call **ConfigurableApplicationContext.close()** |
| Not filtering events in parent/child contexts | Parent unintentionally handles child's close event | Check **getApplicationContext()** |
| Using default **@TransactionalEventListener** for shutdown events | Usually no transaction to bind to | Use regular **@EventListener** |
| Expecting shutdown hooks to run in all cases | Lost work when killed or crashed | Persist state durably before shutdown, retry on recovery |
| Listener blocks on network without timeout | Graceful shutdown hangs or gets cut short | Timeouts, metrics, and minimal work in listener |
| Catching exceptions and declaring cleanup complete | Masks errors and leaks resources | Log/alert, clear cleanup ownership, test actual failures |

## 12. Checklist for designing ContextClosedEvent listeners

Before adding a context close listener, confirm:

- **Is the goal to observe the close event or clean up resources?** Choose the right callback according to ownership.
- **Which context does the listener belong to?** Use **event.getApplicationContext()** when parent/child contexts exist.
- **Does it depend on an executor, DB, or HTTP?** Evaluate availability while the container is shutting down.
- **Can the listener run fast with explicit timeouts?** Avoid prolonging close().
- **Must it complete even if the JVM dies?** If yes, move to a durable mechanism before shutdown.
- **Have stop/close/destroy been tested with a real ApplicationContext?** Do not conclude from tests invoking methods directly.
- **Does a bean have multiple cleanup hooks causing repeated execution?** Specify clearly where resource-closing responsibility lies.

**Rule of thumb:** **ContextClosedEvent** is the notification that Spring is **starting to close an ApplicationContext**. In the normal closing path of **AbstractApplicationContext**, the event is published **before** stopping lifecycle components and destroying singleton beans. Use it to know the context is closing; use **SmartLifecycle** and destroy callbacks to clean up resources with clear ordering and responsibility.

### Official references

- Spring Framework Reference, *Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Javadoc, *ContextClosedEvent*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/ContextClosedEvent.html
- Spring Framework Javadoc, *AbstractApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework Javadoc, *ConfigurableApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Framework Reference, *Lifecycle Callbacks*: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework Javadoc, *SmartLifecycle*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/SmartLifecycle.html
