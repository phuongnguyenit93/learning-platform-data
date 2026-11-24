# ContextClosedEvent and Distinguishing It from Startup Events in Spring Boot

## 1. What Is ContextClosedEvent?

`ContextClosedEvent` is a **Spring Framework lifecycle event** in the `org.springframework.context.event` package. Spring emits this event when an active `ApplicationContext` **begins closing**. In a Spring Boot application, this typically occurs when the app exits normally, receives a stop signal the JVM can handle, or when code explicitly calls `ConfigurableApplicationContext.close()`.

Crucially, the word **Closed** in the event name **does not mean all beans have already been destroyed before listeners are invoked**. Following `AbstractApplicationContext`'s closing sequence, the event is published **before** requesting `Lifecycle` beans to stop and before destroying managed singletons. Thus it is a "context is closing" signal, while `@PreDestroy`, `DisposableBean.destroy()`, or `@Bean(destroyMethod = "...")` handle per-bean resource cleanup in the subsequent step.

Example of an application that has finished serving and needs to stop:

~~~text
Running
   |
   +-- Request to close ApplicationContext
   |      context.close() or JVM shutdown hook
   |
   +-- Publish ContextClosedEvent
   |      Listeners observe the context beginning to close
   |
   +-- Stop Lifecycle / SmartLifecycle beans via lifecycle mechanism
   |
   +-- Destroy singletons in BeanFactory
   |      @PreDestroy / DisposableBean / destroy methods ...
   |
   +-- Close BeanFactory, finish context cleanup steps
   v
Context closed, no longer usable as an active context
~~~

This is the general order of a normal context close, **not an absolute order across all listeners, beans, or asynchronous threads**. Different Spring versions and context implementations may add specific steps. When shutdown encounters errors, some cleanup operations may not complete; the event is also not guaranteed to fire when a process is forcibly terminated.

### Key Meanings

- **Marks the closing milestone**: notifies listening components that the context is starting to end its lifecycle.
- **Allows scoped reactions**: audit logging, marking state to stop accepting work, emitting observability signals, or executing brief shutdown actions.
- **Bound to an `ApplicationContext`**: `event.getApplicationContext()` identifies the context that emitted the event. In multi-context systems, pay attention to the event source.

Do not use `ContextClosedEvent` as the sole way to release sockets, thread pools, datasources, or connections owned by beans. For bean-owned resources, prefer the bean's own **lifecycle and destruction callbacks** to avoid over-reliance on event listeners.

## 2. When Is ContextClosedEvent Emitted?

Per Spring Framework, `ContextClosedEvent` is emitted when closing a `ConfigurableApplicationContext`, such as:

1. **Explicit closing** via `context.close()`.
2. **JVM shutdown hook** registered by Spring Boot in normal applications, closing the context when the JVM exits via a path that runs hooks.
3. **Application orchestration** leading to context closure (for instance, CLI termination logic or lifecycle management in tests), when context close is genuinely invoked.

Example explicitly closing a running context:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

// After completing work, request context close.
context.close();
~~~

This is an **illustrative snippet inside `main()`**, not a standalone file; `MyApplication` and imports must be declared in a Spring Boot project. For a long-running web service, do not call `close()` right after `run()` unless you genuinely intend to stop the service.

Spring Boot normally registers a JVM shutdown hook to close the context when the process exits cleanly. Consequently, in web applications you usually do not need to add another shutdown hook yourself just to close the Spring context.

**The event cannot be guaranteed to fire** in cases such as:

- Process killed via `SIGKILL`, `kill -9`, `Runtime.halt(...)`, JVM crash, or power loss: JVM shutdown hooks may not run.
- Startup fails when the context has not been created yet or is not in an active state: there may be no valid context to publish the event.
- Application running in a container/orchestrator is forcibly killed before shutdown completes.
- Listener errors, misconfigured/unregistered listeners, or asynchronous handlers that do not finish before the process exits.

Therefore `ContextClosedEvent` is useful for **observing lifecycle**, yet is not a guaranteed delivery protocol for critical transactions. For durable data persistence or business events, use appropriate storage/queues/transactions before shutdown occurs.

## 3. Distinguishing Spring Framework Events from Spring Boot Events

`ContextClosedEvent` belongs to **Spring Framework** and describes the `ApplicationContext` lifecycle. By contrast, `ApplicationStartingEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent`, and `ApplicationFailedEvent` are events tied to a **Spring Boot** `SpringApplication` run.

| Event | Declared in | Main timing | What does it mean? |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | Spring Boot | Start of `SpringApplication.run`, before full `Environment`/context exist | Bootstrap sequence has begun |
| `ApplicationEnvironmentPreparedEvent` | Spring Boot | `Environment` prepared, before context creation | Early environment configuration can be observed |
| `ApplicationContextInitializedEvent` | Spring Boot | Context created and initializers called, before loading bean definitions | Context initially configured |
| `ApplicationPreparedEvent` | Spring Boot | Bean definitions loaded, before refresh | About to refresh context |
| `ContextRefreshedEvent` | Spring Framework | Context refreshed successfully | Container completed refresh |
| `ApplicationStartedEvent` | Spring Boot | After refresh, before `ApplicationRunner`/`CommandLineRunner` | Context active, runners not finished yet |
| `ApplicationReadyEvent` | Spring Boot | After runners execute successfully | Spring Boot completed startup per its lifecycle |
| `ApplicationFailedEvent` | Spring Boot | When startup fails | Startup run encountered an error |
| **`ContextClosedEvent`** | **Spring Framework** | **When an active context begins closing** | **Context shutdown phase begins** |
| `ContextStoppedEvent` | Spring Framework | When `ApplicationContext.stop()` is called | `Lifecycle` beans requested to stop; context not necessarily destroyed |

Two easiest points to confuse:

- **`ApplicationStartedEvent` does not mean the application shut down or is ready for traffic**. It happens during startup, before runners. `ApplicationReadyEvent` marks the later successful startup milestone.
- **`ContextStoppedEvent` is not synonymous with `ContextClosedEvent`**. `stop()` belongs to `Lifecycle` start/stop control; a stopped context can still be `start()`ed again in supported models. `close()` terminates the context lifecycle; you cannot treat a closed instance like a context that can be normally refreshed or restarted.

### Two-Stage Diagram: Startup and Shutdown

~~~text
JVM invokes main(...)
  |
  v
SpringApplication.run(...)
  |
  +-- ApplicationStartingEvent
  +-- ApplicationEnvironmentPreparedEvent
  +-- ApplicationContextInitializedEvent
  +-- ApplicationPreparedEvent
  |
  +-- ApplicationContext.refresh()
  |     +-- ContextRefreshedEvent
  |
  +-- ApplicationStartedEvent
  +-- Run ApplicationRunner / CommandLineRunner
  +-- ApplicationReadyEvent
  v
Application running
  |
  | Later, a stop request arrives
  v
ConfigurableApplicationContext.close() / shutdown hook
  |
  +-- ContextClosedEvent
  +-- Stop Lifecycle beans
  +-- Singleton destruction callbacks
  +-- Finish closing context
  v
Application stopped

Alternate path: startup failure -> ApplicationFailedEvent
(ContextClosedEvent may not occur, depending on failure phase).
~~~

The diagram does not imply every app always emits all events: startup can fail, programs can have multiple contexts, and abrupt termination can bypass shutdown hooks.

## 4. Receiving ContextClosedEvent with ApplicationListener or @EventListener

Because `ContextClosedEvent` is emitted **after a context has been created and is closing**, the listener can be a regular Spring bean. This differs from `ApplicationStartingEvent`, which happens too early for a component-scanned bean to catch.

### Approach 1 — @EventListener: Simple for Application Code

~~~java
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownObserver {

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println("Closing: "
                + event.getApplicationContext().getId());
    }
}
~~~

This is a complete Java class **inside a Spring project with proper dependencies and component-scan scope**, though without `main()` it does not run standalone. Spring invokes the registered method upon receiving the event in the matching context. `getId()` returns the context ID, which alone does not prove every bean's state.

Use `@EventListener` for brief reactions that do not block shutdown for long. Do not assume every singleton remains ready if listeners run concurrently or other threads are shutting down.

### Approach 2 — ApplicationListener<ContextClosedEvent>

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;

public final class ShutdownListener
        implements ApplicationListener<ContextClosedEvent> {

    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        System.out.println("Context closing: "
                + event.getApplicationContext().getId());
    }
}
~~~

This is a syntactically complete Java class, yet it **must be registered** to take effect. In a Spring Boot app, it can be registered as a bean via `@Component`, `@Bean`, or added via `SpringApplication` APIs if a BeanFactory-independent listener is needed.

Comparing the two styles:

| Criterion | `@EventListener` | `ApplicationListener` |
| --- | --- | --- |
| Form | Method on a Spring bean | Interface with `onApplicationEvent` |
| Best suited for | Short, readable logic with dependency injection | Infrastructure/framework integration needing an object listener |
| Registration timing | When beans and event listener adapters are processed during refresh | Can be earlier if added directly to `SpringApplication`; can also be a bean |
| Receives `ContextClosedEvent` | Yes, if bean/listener was registered | Yes, if listener was registered |
| Receives `ApplicationStartingEvent` when only a bean | Unreliable: too early | Only when registered before `run`, not as a late bean |

**Note on using `@Async`:** if you configure the listener to run asynchronously, do not rely on the listener's task finishing before `destroyBeans()` executes. This lesson uses default synchronous listeners when explaining event and callback ordering.

## 5. Java 17+ Example: Proving the Close Event Precedes Destroy Callbacks

The following example runs on **Spring Boot 3.5.16 + Java 17**. It creates a non-web application (`WebApplicationType.NONE`), runs a runner, emits startup events, and then **explicitly calls `context.close()`** to produce reproducible results in any environment.

### 5.1. Project Structure

~~~text
context-closed-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/closedevent/
                └── ClosedEventApplication.java
~~~

**File `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>context-closed-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The project requires JDK 17+ and Maven 3.6.3+ (or the corresponding Maven Wrapper). The example code uses standard Spring Boot APIs and requires no database or HTTP port.

**File `src/main/java/com/example/closedevent/ClosedEventApplication.java`:**

~~~java
package com.example.closedevent;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ClosedEventApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ClosedEventApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);

        System.out.println("05_MAIN_BEFORE_CLOSE");
        context.close(); // Explicit close request.
        System.out.println("08_MAIN_AFTER_CLOSE");
    }

    @Bean(destroyMethod = "release")
    TrackedResource trackedResource() {
        return new TrackedResource();
    }

    @Bean
    ApplicationRunner demoRunner(TrackedResource resource) {
        return args -> System.out.println(
                "03_RUNNER_VALUE=" + resource.value());
    }

    @Bean
    EventObserver eventObserver() {
        return new EventObserver();
    }

    static final class EventObserver {

        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            System.out.println("02_APPLICATION_STARTED");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            System.out.println("04_APPLICATION_READY");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            System.out.println("06_CONTEXT_CLOSED_EVENT");
        }
    }

    static final class TrackedResource {

        TrackedResource() {
            System.out.println("01_RESOURCE_CREATED");
        }

        String value() {
            return "ready";
        }

        public void release() {
            System.out.println("07_RESOURCE_DESTROY_METHOD");
        }
    }
}
~~~

The example puts `main()` and helper classes in a single Java file; there is no need to create separate `EventObserver.java` or `TrackedResource.java` files. Spring manages `TrackedResource` as a regular singleton bean via the `@Bean` method. `EventObserver` is also a bean, so its `@EventListener` methods are registered by Spring during context initialization.

`@Bean(destroyMethod = "release")` instructs Spring to call `TrackedResource.release()` when destroying the bean. The method name matches exactly and can be verified in the code. This example omits `@PreDestroy` to avoid printing multiple callbacks that might distract from the main point.

### 5.2. Running and Reading Output

Inside the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Or package as an executable JAR:

~~~bash
mvn package
java -jar target/context-closed-demo-0.0.1-SNAPSHOT.jar
~~~

In the output (ignoring the banner, interleaved Spring Boot/Maven logs, or library logs), **the lines printed by the example code** appear in this order:

~~~text
01_RESOURCE_CREATED
02_APPLICATION_STARTED
03_RUNNER_VALUE=ready
04_APPLICATION_READY
05_MAIN_BEFORE_CLOSE
06_CONTEXT_CLOSED_EVENT
07_RESOURCE_DESTROY_METHOD
08_MAIN_AFTER_CLOSE
~~~

Explanation:

1. **`01_RESOURCE_CREATED`**: the singleton bean is instantiated during context refresh.
2. **`02_APPLICATION_STARTED`**: the context refreshed successfully, yet runners have not been invoked yet.
3. **`03_RUNNER_VALUE=ready`**: `ApplicationRunner` executes after the started milestone.
4. **`04_APPLICATION_READY`**: Boot emits the ready event once runners succeed.
5. **`05_MAIN_BEFORE_CLOSE`**: `SpringApplication.run()` returns the context; `main()` prepares to close it explicitly.
6. **`06_CONTEXT_CLOSED_EVENT`**: the context-closing event is emitted and observed by the listener.
7. **`07_RESOURCE_DESTROY_METHOD`**: Spring calls the singleton's destroy method after the close event publication stage.
8. **`08_MAIN_AFTER_CLOSE`**: `context.close()` returns; code in `main()` resumes.

This is the order **for the demo program and synchronous listeners**, not a guarantee that every Spring-based product emits the exact same eight lines or log names. In a production application with a web server, shutdown also involves stopping new request intake, draining connections, lifecycle beans, and deployment-platform signals.

### 5.3. Further Experiments

**Experiment 1 — switch to the shutdown hook:** Remove the `context.close()` and `08_MAIN_AFTER_CLOSE` lines, switch to a web application with an embedded web server, and then terminate the process with Ctrl+C. If the JVM allows shutdown hooks to run, Spring Boot closes the context and event listeners can receive `ContextClosedEvent`. This experiment requires setting up the web starter/configuration and **does not produce identical fixed output like the CLI demo**.

**Experiment 2 — check @PreDestroy:** Replace `@Bean(destroyMethod = "release")` with `@Bean`, then annotate `release()` with `@PreDestroy` (import `jakarta.annotation.PreDestroy`, available with appropriate Boot 3.x annotation dependencies). Observe that cleanup still happens when Spring destroys the bean. This is an instruction for modifying the example code, not a standalone file.

**Experiment 3 — distinguish stop and close:** On a live `ConfigurableApplicationContext`, try calling `context.stop()`, then `context.start()`, and finally `context.close()`. Watch `ContextStoppedEvent`/`ContextStartedEvent` with an appropriate listener, and compare with `ContextClosedEvent`. Do not assume `stop()` executes all destruction callbacks.

**Experiment 4 — startup failure:** Intentionally throw `IllegalStateException` from `ApplicationRunner`, then observe `ApplicationFailedEvent`. Because `run()` throws an exception, execution will not reach `05_MAIN_BEFORE_CLOSE` in this example. Do not assume `ContextClosedEvent` must also fire in every failure scenario.

## 6. ContextClosedEvent vs. @PreDestroy, DisposableBean, and SmartLifecycle

When designing shutdown, pick the **right mechanism by responsibility**:

| Mechanism | Where is it invoked? | Appropriate responsibility |
| --- | --- | --- |
| `@EventListener(ContextClosedEvent.class)` | Listener for a context-level event | Observing and reacting briefly when the context begins closing |
| `ApplicationListener<ContextClosedEvent>` | Object listener for a context-level event | Infrastructure/framework integration |
| `@PreDestroy` | Callback on the bean being destroyed | Releasing resources owned by the bean |
| `DisposableBean.destroy()` | Bean destruction callback via Spring interface | Cleanup logic for a bean needing a Spring contract |
| `@Bean(destroyMethod = "...")` | Destroy method declared in bean configuration | Cleaning up a bean with a custom method without Spring interfaces |
| `SmartLifecycle.stop(Runnable callback)` | While the lifecycle processor stops beans | Stopping consumers, workers, and timed processing threads |
| `ContextStoppedEvent` | When `stop()` is called on a supporting context | Reporting lifecycle stop state, not replacing close |

The single biggest difference is that **the close event is published before singleton beans are destroyed**, whereas `@PreDestroy`/destroy methods belong to that bean-destruction phase itself. So if a service owns a thread pool or connection pool, that service itself should close the resource in its destroy callback or lifecycle; a listener should only emit brief coordination signals when the context is about to end.

### Example of Proper Resource Cleanup

~~~java
@Component
public class CacheWorker {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    @PreDestroy
    public void shutdown() {
        executor.shutdown();
    }
}
~~~

This is an **illustrative snippet inside an application**, not standalone: it requires imports for `org.springframework.stereotype.Component`, `jakarta.annotation.PreDestroy`, `java.util.concurrent.ExecutorService`, and `java.util.concurrent.Executors`. In production, if tasks must finish, apply an `awaitTermination` policy, timeout, interruption handling, and fallback; a bare `shutdown()` merely stops accepting new tasks.

Do not call `ApplicationContext.close()` directly from `@PreDestroy` or `ContextClosedEvent` on the same context just to "make sure it stops": the context is already traversing the close flow, and recursively closing or creating new beans during teardown is rarely beneficial.

## 7. Practical Limitations of ContextClosedEvent

### 7.1. Does Not Mean Shutdown Is Already Finished

Because the listener runs as the event is emitted, other resources may still be undestroyed. Therefore do not log "all resources destroyed" immediately in `ContextClosedEvent`. To verify a resource closed, check that resource's own destroy callback or an external system condition.

Avoid instantiating new beans via `ApplicationContext.getBean()` inside a close listener. During shutdown, the bean factory may be disallowing new singleton creation and components are being stopped. Use dependencies injected earlier if genuinely needed, and avoid spawning new work.

### 7.2. Not the First Startup Event

In Spring Boot, `ApplicationStartingEvent` fires before `Environment` and `ApplicationContext` are created; catching it requires registering a listener before `run()`. `ContextClosedEvent` is the opposite: a regular `@EventListener` bean can receive it because the context already existed and initialized.

This also explains why the exact same `@Component` class can catch `ApplicationReadyEvent` and `ContextClosedEvent` while missing `ApplicationStartingEvent`. Do not confuse "did not see the event" with "the event was never emitted"; sometimes the listener was simply registered too late.

### 7.3. Not ApplicationFailedEvent

Spring Boot's `ApplicationFailedEvent` relates to **startup failures**. If an error happens very early, there may be no `ApplicationContext` to close. If an error happens after the context created some beans, the framework can clean up created beans, yet you cannot conclude `ContextClosedEvent` always fires identically to a normal close path.

Therefore, do not build logic assuming "if startup fails, ContextClosedEvent will definitely handle it" without verifying the specific lifecycle path. Choose startup-failure and cleanup mechanisms with explicit guarantees.

### 7.4. Context Hierarchies and Child Context Events

Complex applications may have a **parent context and child contexts**. Events emitted in a child context can propagate up to ancestor contexts. Consequently, a listener in a parent context can receive `ContextClosedEvent` from a child context; do not assume every received event means **the listener's own context** closed.

To filter for the right context, compare references:

~~~java
@EventListener
public void onClosed(ContextClosedEvent event) {
    if (event.getApplicationContext() != this.applicationContext) {
        return;
    }
    // React only to the context this bean belongs to.
}
~~~

This is an **illustrative, non-standalone snippet**: `applicationContext` must be injected or obtained via `ApplicationContextAware` before shutdown. Do not mutate the context inside the callback merely to filter events.

### 7.5. Default Listeners Are Synchronous, Yet Should Not Block Long

By default Spring event listeners execute synchronously via the default multicaster. A slow listener can prolong the closing process. A listener throwing an exception may be handled/logged by the context-closing mechanism, yet you must not rely on an event exception to abort shutdown.

Avoid:
- Making HTTP or database calls without timeouts.
- Flushing huge datasets at the last minute without prior checkpoints.
- Spawning new background tasks while the system is shutting down.
- Relying on an async thread to log "closed" and assuming it finishes in time.
- Blocking the shutdown hook longer than the infrastructure's termination grace period.

Better options are resource destroy callbacks with explicit timeouts, acknowledged queues, or proper service draining logic.

## 8. Web Server, Graceful Shutdown, and Readiness

In a web service, the context-closing event is only **one part** of the shutdown workflow. The system also involves:

1. Load balancer/orchestrator deciding to stop routing new requests.
2. Web server stopping new connections or coordinating graceful shutdown.
3. In-flight requests given time to complete per policy.
4. Bean lifecycles and resources being closed.
5. The JVM process exiting.

Spring Boot supports graceful shutdown for several embedded web servers. In Spring Boot 3.5, sample configuration:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

This is **reference configuration**, which must be evaluated against your web server, Spring Boot version, and deployment platform limits. It does not replace Kubernetes readiness probes or load-balancer draining. If a container receives an immediate `SIGKILL`, no Spring setting guarantees cleanup completes.

In Kubernetes, readiness and liveness probes serve different operational purposes from events:
- **Readiness**: indicates whether the instance should receive new traffic.
- **Liveness**: indicates whether the process is healthy enough to continue running or should restart.
- **`ContextClosedEvent`**: notifies of context-closing lifecycle inside the application.

There may be a window where the system already stopped routing new requests before the context actually closes. Do not use `ContextClosedEvent` as the sole source of truth for readiness. Pick signals suited to your orchestrator and business requirements.

### Does ContextClosedEvent Fire Without a Web Server?

**Yes, whenever an active context closes properly**. The complete example in Section 5 sets `WebApplicationType.NONE` and still receives `ContextClosedEvent`. The event belongs to Spring's `ApplicationContext`, not to any specific servlet container.

## 9. Observing and Diagnosing Shutdown

| Symptom | Possible cause | Check |
| --- | --- | --- |
| Close listener does not log | Listener not registered, context not closed via normal path, or process forcibly killed | Check `@Component`/`@Bean`, shutdown path, SIGTERM/SIGKILL, actual logs |
| Saw `ApplicationReadyEvent` yet no close event | App still running or exited outside normal close path | Check JVM shutdown hook, close code, signs of process crash |
| Saw `ContextClosedEvent` before destroy logs | Standard `AbstractApplicationContext.doClose()` behavior | Verify sequence close → lifecycle onClose → destroy singletons |
| `@PreDestroy` does not run | Bean not Spring-managed, different scope/lifecycle, or forced shutdown | Check bean definition, scope, instantiation, and exit path |
| Listener runs multiple times | Multiple contexts, context hierarchy, or multiple app create/close cycles | Print context ID, compare `getApplicationContext()` |
| `ApplicationFailedEvent` appeared without `ContextClosedEvent` | Startup failure occurred before an active context existed | Identify failed startup milestone, inspect stack trace |
| Slow context closing | `SmartLifecycle`, destroy method, or listener waiting on I/O/threads | Log durations, check timeouts, gather concrete timing data |
| Pod killed before cleanup finished | Unsuitable shutdown grace period or signal handling | Check terminationGracePeriodSeconds, shutdown hook, drain duration |
| Called `context.stop()` yet saw no close event | Stop and close are different APIs | Use `context.close()` when permanent closure is intended |
| Code after `context.close()` keeps running | `close()` returns to caller; JVM may not exit immediately | Check `main()` logic and remaining non-daemon threads |

### Practical Verification Steps

1. Identify the **stop path**: explicit close, Ctrl+C, SIGTERM, shutdown hook, test teardown, or crash.
2. Verify the exact **context ID and event type**. Do not infer from similar "Started/Stopped/Closed" names.
3. For listeners, check whether they were registered while the context was active and whether component scanning excluded them.
4. Measure separately when `ContextClosedEvent` arrives, how long `SmartLifecycle` stop takes, and how long key resource destroy callbacks take.
5. In web systems, separate request draining and readiness from bean destruction; inspect load-balancer or container logs when needed.
6. If forced shutdown occurs, use recovery mechanisms resilient to missed callbacks rather than just adding another listener.

## 10. Common Misconceptions

**Misconception 1: "`ContextClosedEvent` means all beans have already been cleanly destroyed."** No. The event is normally published before destruction callbacks run.

**Misconception 2: "`ContextStoppedEvent` and `ContextClosedEvent` are the same."** No. `stop()` belongs to start/stop lifecycle control; `close()` ends the context and destroys singletons.

**Misconception 3: "`ApplicationStoppedEvent` is Boot's standard shutdown event."** Do not invent or assume such an event name. Use actual public event types, such as Spring Framework's `ContextClosedEvent`.

**Misconception 4: "`ApplicationStartedEvent` already means all runners finished."** No. Runners execute after `ApplicationStartedEvent`; `ApplicationReadyEvent` comes later.

**Misconception 5: "I can catch `ApplicationStartingEvent` with `@EventListener` on a bean."** Not a reliable way for an event emitted before the context exists; listeners for ultra-early startup must be registered before `run()`.

**Misconception 6: "If startup fails, `ContextClosedEvent` definitely appears."** No. Very early failures may have no active context; `ApplicationFailedEvent` is Boot's event for startup failures.

**Misconception 7: "Shutdown hooks always run."** No—for instance, `SIGKILL` or a JVM crash can bypass all hooks.

**Misconception 8: "Use `ContextClosedEvent` to close every resource."** That easily creates cross-dependencies and makes ordering and timeouts hard to manage. Beans that own resources should own their lifecycle cleanup.

**Misconception 9: "Once the close event fires, all HTTP requests have finished."** You cannot conclude that from the event alone. Graceful shutdown, connection draining, and appropriate timeout policies are required.

**Misconception 10: "A `ContextClosedEvent` always belongs to the listener's own context."** With context hierarchies, a parent listener can see child context events. Always check `event.getApplicationContext()`.

## 11. Review Questions

**Question 1:** Is `ContextClosedEvent` emitted before or after `@PreDestroy` on regular singletons?

**Answer:** In `AbstractApplicationContext`'s standard closing flow, the event is published before `destroyBeans()`, so singleton destruction callbacks normally run afterward.

**Question 2:** Can an `@EventListener(ContextClosedEvent.class)` listener be a normal Spring bean?

**Answer:** Yes. The context already exists and the listener is already registered when closing begins, unlike ultra-early startup events such as `ApplicationStartingEvent`.

**Question 3:** Is `ApplicationReadyEvent` a shutdown event?

**Answer:** No. It indicates Spring Boot finished the startup phase and runners; shutdown is a different lifecycle stage.

**Question 4:** When running a CLI program with `WebApplicationType.NONE`, does closing the context emit `ContextClosedEvent`?

**Answer:** Yes, if an active context closes along the normal path. The event does not require an HTTP server.

**Question 5:** Can `context.stop()` replace `context.close()`?

**Answer:** No. Stop only controls lifecycle state, whereas close terminates the context and destroys singleton beans.

**Question 6:** Why should you not rely on `ContextClosedEvent` to guarantee writing a final order to the database?

**Answer:** The listener may not run or finish if the process is killed, times out, or crashes abnormally. Critical persistence must use durable/recoverable mechanisms in the business flow.

**Exercise:** Run the code in Section 5 and record all eight milestones. Try switching from explicit closing to shutdown-hook closing in a process that keeps the JVM alive; then add `@PreDestroy` to the resource and explain the order. Further distinguish `ContextStoppedEvent` using an appropriate listener and calling `context.stop()`. Finally, intentionally trigger a runner failure and compare the `ApplicationFailedEvent` path against normal closing.

## 12. Official Documentation

- [Spring Framework — ApplicationContext events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): semantics of `ContextClosedEvent`, `ContextStoppedEvent`, `@EventListener`, and the event mechanism.
- [Spring Framework — AbstractApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): `doClose()`, `destroyBeans()`, `registerShutdownHook()`.
- [Spring Framework — ContextClosedEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ContextClosedEvent.html): event type and context source.
- [Spring Boot 3.5 — SpringApplication: events, listeners, and exit](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): ordering of Boot events and shutdown hook.
- [Spring Boot 3.5 — Graceful shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): coordinating the web server during stop.

## 13. Takeaways

- `ContextClosedEvent` belongs to **Spring Framework** and signals **an active `ApplicationContext` is beginning to close**; it is not Spring Boot's `ApplicationStartedEvent` or `ApplicationReadyEvent`.
- Normal closing path: **publish ContextClosedEvent → stop lifecycle beans → destroy singleton beans → finish closing context**.
- `@EventListener` or `ApplicationListener<ContextClosedEvent>` is suited for observing; resources should clean up themselves via `@PreDestroy`, `DisposableBean`, destroy methods, or `SmartLifecycle`.
- `ContextStoppedEvent` is stop, which can be restarted in supported models; `ContextClosedEvent` is close, ending the context's lifecycle.
- `ApplicationStartingEvent` is startup start; `ApplicationStartedEvent` is post-refresh; `ApplicationReadyEvent` is post-runners; `ApplicationFailedEvent` is startup failure.
- Shutdown events **are not guaranteed** when the JVM is forcibly killed; combine graceful shutdown, timeouts, and recovery mechanisms to protect data and resources.