# Distinguishing context.stop and context.close in Spring Boot

## 1. The Most Important Conclusion

In Spring Boot, the `ConfigurableApplicationContext context` variable is typically obtained from `SpringApplication.run(...)`. The two methods `context.stop()` and `context.close()` **are not synonymous**:

- **`context.stop()`:** signals **stopping beans that participate in the `Lifecycle`/`SmartLifecycle` contract** via `LifecycleProcessor`. The context **remains alive**, and the bean factory and regular singletons **have not been destroyed**. You can call `context.start()` to restart components that support restarting.
- **`context.close()`:** ends **the lifecycle of the ApplicationContext itself**, publishes `ContextClosedEvent`, stops running lifecycle components, invokes destruction callbacks on context-owned singletons, and releases associated resources. After closing, **do not reuse the same context as a normal startable/refreshable runtime**.

An easy rule to remember:

~~~text
context.stop()  = pause the lifecycle of Lifecycle beans
context.start() = reactivate Lifecycle beans in a context that is still alive
context.close() = terminate the ApplicationContext and destroy managed resources
~~~

**Do not equate `Lifecycle` beans not running with the Spring context being closed.** A stopped context can still report `isActive() == true`. Conversely, after a successful `close()`, `isActive() == false` and singletons have been cleaned up according to contract.

This lesson belongs to the **Application Shutdown** section of the Spring Boot Application Runtime module. The goal is to clearly understand the APIs, events, resource durability, use cases, common mistakes, and Java 17+ practice.

## 2. Quick Comparison Table

| Question | `context.stop()` | `context.close()` |
| --- | --- | --- |
| Intent | Stop components participating in lifecycle | Terminate context, shutdown, and cleanup |
| Originating API | `Lifecycle.stop()` on the context | `ConfigurableApplicationContext.close()` |
| Central coordinator | `LifecycleProcessor.stop()` | `doClose()` and `LifecycleProcessor.onClose()` |
| Primary event | `ContextStoppedEvent` | `ContextClosedEvent` |
| Stops running `Lifecycle` beans? | Yes, per processor/phase | Yes, on the normal context closing path |
| Calls singleton `@PreDestroy` solely from this command? | **No** | **Yes**, when destroying eligible singletons |
| Calls `DisposableBean.destroy()` from this command? | **No** | **Yes**, when the bean is destroyed |
| Calls `@Bean(destroyMethod = "close")` from this command? | **No** | **Yes**, when the container-owned singleton is destroyed |
| Is the BeanFactory destroyed? | No | Yes, during context closure |
| `context.isActive()` upon completion | Usually still true if context was refreshed | False when close finishes |
| `context.isRunning()` upon completion | Usually false for LifecycleProcessor | Do not treat a closed context as a runtime for lifecycle calls |
| Can `context.start()` be called again? | **Yes**, if components support restart and context is active | **No** on the same closed context |
| Recreates all beans? | No | No; must create a new context for a new run |
| Reruns `ApplicationRunner`? | No | No |
| Re-publishes `ApplicationReadyEvent` on restart? | Not automatically | No |
| Suitable for terminating the process? | Insufficient | Context shutdown step, but does not guarantee JVM exit by itself |
| Best suited for | Pausing workers/consumers, controlled lifecycle management | Exiting the application, releasing resources, ending integration tests |

This table describes common implementations based on Spring Framework's `AbstractApplicationContext` and `DefaultLifecycleProcessor`. A bean running its own threads that does **not** implement `Lifecycle` can keep running after `stop()`. Therefore, "context stopped" does not guarantee every background task or request type has halted.

## 3. Related Interfaces

### 3.1. Lifecycle: start, stop, isRunning

Spring Framework declares `org.springframework.context.Lifecycle` with three methods:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

This is an **abbreviated signature excerpt for learning the API**, not an interface to redefine yourself. Any Spring bean implementing `Lifecycle` can be coordinated when the application context receives explicit start or stop signals.

`isRunning()` informs the lifecycle processor whether the component is currently running. It does not replace tracking actual resource state, especially for asynchronous work.

### 3.2. SmartLifecycle: Auto-Startup and Phased Stopping

`org.springframework.context.SmartLifecycle` extends `Lifecycle` and `Phased`. It adds:

- `isAutoStartup()`: whether the component starts automatically on context refresh. The default for SmartLifecycle is true.
- `getPhase()`: selects a phase; lower phases start first, higher phases stop first, taking dependencies into account.
- `stop(Runnable callback)`: notifies completion once the component **has finished stopping**; the lifecycle processor may need to wait for the callback during shutdown.

Distinguish parameterless `stop()` from `stop(Runnable)`. An asynchronous SmartLifecycle implementation must ensure the callback does not run before tasks/connections have stopped per contract. Do not invoke the callback right after `ExecutorService.shutdown()` if tasks are still running and the app requires graceful draining.

### 3.3. ConfigurableApplicationContext

`org.springframework.context.ConfigurableApplicationContext` extends `ApplicationContext`, `Lifecycle`, and `Closeable`. Hence it exposes `start()`, `stop()`, `isRunning()`, `close()`, as well as `isActive()` and `isClosed()`.

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

context.stop();   // Stop lifecycle components.
context.start();  // Allow restarting while context remains active.
context.close();  // Close context and destroy container-owned singletons.
~~~

This is an **illustrative snippet inside a Spring Boot program**, requiring a valid `MyApplication` class and imports, not a standalone Java file.

An important point: `isRunning()` and `isActive()` answer **two different questions**.

- `isRunning()`: whether the lifecycle processor is in running or stopped state.
- `isActive()`: whether the context has been refreshed at least once and has not yet been closed through its lifecycle.

Thus after `context.stop()`, you may observe:

~~~text
context.isActive()  -> true
context.isRunning() -> false
~~~

This is **not a contradictory state**.

## 4. What Happens Inside context.stop()?

With `AbstractApplicationContext`, calling `stop()` delegates to the lifecycle processor, and then Spring publishes `ContextStoppedEvent`. With the default processor, running `Lifecycle` beans receive stop signals by phase/dependency.

~~~text
Application code calls context.stop()
   |
   +-- AbstractApplicationContext.stop()
   |     +-- getLifecycleProcessor().stop()
   |           +-- Stop running Lifecycle / SmartLifecycle beans
   |           +-- Coordinate appropriate phases and stop callbacks
   |
   +-- publishEvent(ContextStoppedEvent)
   |
   v
stop() returns
   |
   +-- ApplicationContext remains active
   +-- BeanFactory remains alive
   +-- Managed singletons still exist
   +-- @PreDestroy / destroyMethod do not run solely from stop
~~~

This is the conceptual flow in Spring Framework. With asynchronous stop callbacks, the processor can wait up to the phase timeout; `stop()` returning does not guarantee external resources are closed if an implementation violates its contract.

### What Does Not Happen?

`context.stop()` **does not**:
- Remove all bean definitions or singleton beans.
- Create another BeanFactory.
- Re-run singleton `@PostConstruct` methods on restart.
- Destroy connection pools via `@PreDestroy`.
- Force-stop all threads spawned manually outside Spring's lifecycle.
- Shut down the JVM or invoke `System.exit`.
- Publish `ContextClosedEvent` on the normal stop path.
- Re-publish `SpringApplication.run` startup events.
- Transition Spring Boot readiness/liveness to a specific state merely by calling this method.

If a resource does not implement `Lifecycle`, do not assume it stops automatically just because the context received stop. For example, a thread created manually in a constructor without registering a stop callback can continue running.

## 5. What Happens Inside context.start() After stop?

`context.start()` calls `LifecycleProcessor.start()`, then publishes `ContextStartedEvent`. For beans supporting restart, this triggers them to run again, yet **does not refresh the ApplicationContext**.

~~~text
context.stop()  -> ContextStoppedEvent
     |
     | Singleton beans remain the same instances
     | Context remains active
     |
context.start() -> LifecycleProcessor.start()
                -> ContextStartedEvent
     |
     +-- Lifecycle beans restart by phase
     +-- @PostConstruct does not run again
     +-- ApplicationRunner.run() does not run again
     +-- ApplicationReadyEvent is not re-published automatically
~~~

This explains why `SmartLifecycle.start()` and `SmartLifecycle.stop()` should be written to be **idempotent**:
- Calling start when already running must not open duplicate consumers/sockets.
- Calling stop when already stopped must be safe.
- If a component supports restart, a successful stop followed by start can create a fresh resource generation.
- If a library does not support restarting after closing, the component must create a new object or fail clearly rather than pretending the old instance came back to life.

### ContextStartedEvent Differs from ApplicationStartedEvent

Similar names, different levels:

| Event | Package | When |
| --- | --- | --- |
| `ContextStartedEvent` | Spring Framework: `org.springframework.context.event` | When `ApplicationContext.start()` is called |
| `ContextStoppedEvent` | Spring Framework: `org.springframework.context.event` | When `ApplicationContext.stop()` is called |
| `ContextRefreshedEvent` | Spring Framework: `org.springframework.context.event` | When the context finishes refreshing |
| `ApplicationStartedEvent` | Spring Boot: `org.springframework.boot.context.event` | During `SpringApplication.run` after refresh, before runners |
| `ApplicationReadyEvent` | Spring Boot: `org.springframework.boot.context.event` | During `SpringApplication.run` after runners succeed |

**Calling `context.start()` is not equivalent to calling `SpringApplication.run(...)` again.** Therefore, it does not automatically generate a new `ApplicationStartedEvent → runner → ApplicationReadyEvent` sequence.

## 6. What Happens Inside context.close()?

`close()` is the termination path of `ApplicationContext`. According to `AbstractApplicationContext.doClose()`, on the normal close path:

~~~text
context.close() requested
   |
   +-- Mark start of context closure
   +-- Publish ContextClosedEvent
   |     +-- Listeners receive signal that context is closing
   |
   +-- LifecycleProcessor.onClose()
   |     +-- Ask running Lifecycle / SmartLifecycle beans to stop
   |     +-- Wait for stop callbacks per phase/timeout
   |
   +-- destroyBeans()
   |     +-- @PreDestroy
   |     +-- DisposableBean.destroy()
   |     +-- @Bean(destroyMethod = "close"/"shutdown"/...)
   |     +-- Clean up singletons owned by the context
   |
   +-- closeBeanFactory() and context onClose/finalization steps
   |
   v
Closed: context.isActive() == false
~~~

**Major note:** `ContextClosedEvent` is published **as the context begins closing**, before all singletons are destroyed. Thus inside a `ContextClosedEvent` listener, you can still observe a worker in RUNNING state and unclosed resources. Reading only the word "Closed" and assuming all connections are already closed is wrong.

There is no rule that calling `close()` automatically publishes `ContextStoppedEvent` as well. The close path uses `LifecycleProcessor.onClose()` to stop components, while the characteristic published event is `ContextClosedEvent`, rather than an explicit `context.stop()` call.

### Does close() Need to Be Called After stop()?

Normally **no**. `context.close()` already coordinates stopping running lifecycle beans before destroying singletons. Calling `context.stop()` followed by `context.close()` can be useful if you need to separate halting work intake from releasing resources, but it is not a required pattern.

If a component is already STOPPED beforehand, the lifecycle processor normally skips stopping an already stopped resource. Destruction callbacks still run when closing the context to release bean-owned resources.

### Can close() Be Called Twice?

`ConfigurableApplicationContext.close()` is designed to be safe if called multiple times; subsequent calls after closing are normally ignored without destroying singletons again. However, this **does not permit using beans after close**. An object reference held externally still exists on the heap, yet internal resources may be closed and the bean is no longer container-managed.

### Can a Closed Context Be Refreshed/Started Again?

You should not, and in standard Boot contexts **cannot**. Spring Framework describes a closed context as end-of-life, impossible to restart or refresh. To run the application again, you must create **a new ApplicationContext** via `SpringApplication.run` or the corresponding bootstrap mechanism.

In particular, `GenericApplicationContext` does not support multiple refreshes on the same instance even before closing. Do not assume that because some other Spring implementations support hot refresh, every context does.

## 7. Runnable Example Java 17+ / Spring Boot 3.5.16

We will build a program without a web server to observe independently:

1. On refresh, a `SmartLifecycle` auto-starts.
2. `ApplicationStartedEvent`, the runner, and `ApplicationReadyEvent` occur during the Spring Boot startup path.
3. Call `context.stop()`: the worker stops, `ContextStoppedEvent` appears, yet the singleton resource is not destroyed.
4. Call `context.start()`: the worker restarts, `ContextStartedEvent` appears, and the runner does **not** run again.
5. Call `context.close()`: `ContextClosedEvent` arrives before the final stop and before the destroy callback.
6. After close, the context is inactive, the worker is stopped, and the resource is closed.

The example uses an in-memory resource and marker prints, needing no database or HTTP port. Marker ordering can be verified directly, while framework logs may appear in between.

### 7.1. Project Structure

~~~text
stop-close-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/stopclose/
                └── StopVsCloseApplication.java
~~~

### 7.2. Maven pom.xml

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
    <artifactId>stop-close-demo</artifactId>
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

Spring Boot 3.5.16 has been released and is available on Maven Central. This is an illustrative version to keep APIs stable; the 3.5.x branch has reached OSS end-of-support, so for new production work prefer a supported Spring Boot branch and verify the corresponding packages/APIs.

### 7.3. Complete Java File

Save as `src/main/java/com/example/stopclose/StopVsCloseApplication.java`:

~~~java
package com.example.stopclose;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class StopVsCloseApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StopVsCloseApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = application.run(args);
        TrackedWorker worker = context.getBean(TrackedWorker.class);
        SharedResource resource = context.getBean(SharedResource.class);

        try (context) {
            System.out.println("07_BEFORE_STOP active="
                    + context.isActive()
                    + " running=" + worker.isRunning()
                    + " destroyed=" + resource.isClosed());

            context.stop();

            System.out.println("10_AFTER_STOP active="
                    + context.isActive()
                    + " running=" + worker.isRunning()
                    + " destroyed=" + resource.isClosed());

            context.start();

            System.out.println("13_AFTER_START active="
                    + context.isActive()
                    + " running=" + worker.isRunning()
                    + " destroyed=" + resource.isClosed());
        }

        // try-with-resources just closed the ApplicationContext.
        System.out.println("17_AFTER_CLOSE active="
                + context.isActive()
                + " running=" + worker.isRunning()
                + " destroyed=" + resource.isClosed());
    }

    @Bean(destroyMethod = "close")
    SharedResource sharedResource() {
        return new SharedResource();
    }

    @Bean
    TrackedWorker trackedWorker(SharedResource resource) {
        return new TrackedWorker(resource);
    }

    @Bean
    EventTimeline eventTimeline(
            TrackedWorker worker, SharedResource resource) {
        return new EventTimeline(worker, resource);
    }

    @Bean
    ApplicationRunner runner(
            TrackedWorker worker, SharedResource resource) {
        return args -> System.out.println("05_RUNNER running="
                + worker.isRunning()
                + " destroyed=" + resource.isClosed());
    }

    public static final class SharedResource implements AutoCloseable {
        private boolean closed;

        public SharedResource() {
            System.out.println("01_RESOURCE_CREATED");
        }

        public synchronized boolean isClosed() {
            return closed;
        }

        @Override
        public synchronized void close() {
            if (closed) {
                return;
            }
            closed = true;
            System.out.println("16_RESOURCE_DESTROYED");
        }
    }

    public static final class TrackedWorker implements SmartLifecycle {
        private final SharedResource resource;
        private boolean running;
        private int generation;

        public TrackedWorker(SharedResource resource) {
            this.resource = resource;
        }

        @Override
        public synchronized void start() {
            if (running) {
                return;
            }
            if (resource.isClosed()) {
                throw new IllegalStateException("resource destroyed");
            }
            running = true;
            generation++;
            System.out.println("WORKER_START generation=" + generation);
        }

        @Override
        public synchronized void stop() {
            if (!running) {
                return;
            }
            running = false;
            System.out.println("WORKER_STOP generation=" + generation);
        }

        @Override
        public void stop(Runnable callback) {
            // In the demo, stop is completely synchronous and performs no I/O.
            try {
                stop();
            } finally {
                callback.run();
            }
        }

        @Override
        public synchronized boolean isRunning() {
            return running;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 100;
        }
    }

    public static final class EventTimeline {
        private final TrackedWorker worker;
        private final SharedResource resource;

        public EventTimeline(
                TrackedWorker worker, SharedResource resource) {
            this.worker = worker;
            this.resource = resource;
        }

        @EventListener
        public void refreshed(ContextRefreshedEvent event) {
            System.out.println("03_CONTEXT_REFRESHED");
        }

        @EventListener
        public void bootStarted(ApplicationStartedEvent event) {
            System.out.println("04_APPLICATION_STARTED");
        }

        @EventListener
        public void ready(ApplicationReadyEvent event) {
            System.out.println("06_APPLICATION_READY");
        }

        @EventListener
        public void stopped(ContextStoppedEvent event) {
            System.out.println("09_CONTEXT_STOPPED");
        }

        @EventListener
        public void started(ContextStartedEvent event) {
            System.out.println("12_CONTEXT_STARTED");
        }

        @EventListener
        public void closed(ContextClosedEvent event) {
            System.out.println("14_CONTEXT_CLOSED running="
                    + worker.isRunning()
                    + " destroyed=" + resource.isClosed());
        }
    }
}
~~~

**Technical highlights of the code:**

- `SharedResource` is a singleton with `@Bean(destroyMethod = "close")`. The Spring context owns this resource; `stop()` does not call the destroy method.
- `TrackedWorker` implements `SmartLifecycle`, with `isAutoStartup() == true` so Spring starts it during refresh; `getPhase() == 100` is an illustrative phase.
- `start()` and `stop()` no-op when already in the target state; they do not reopen or destroy the singleton resource.
- `stop(Runnable)` invokes the callback once the synchronous stop returns. With asynchronous resources, you must wait for real completion before invoking the callback.
- `EventTimeline` is a regular Spring bean. `@EventListener` receives events published at the corresponding milestones.
- `ApplicationRunner` is invoked by Boot **only once during `SpringApplication.run`**; `context.start()` does not run the runner a second time.
- `try (context)` is valid since Java 9 for effectively final variables and calls `close()` automatically. We keep references `worker` and `resource` solely to inspect state after close; in practice never use them to run business logic after the context is closed.

### 7.4. Run Commands

In the directory containing `pom.xml`:

~~~bash
mvn package
java -jar target/stop-close-demo-0.0.1-SNAPSHOT.jar
~~~

Or:

~~~bash
mvn spring-boot:run
~~~

Requires only JDK 17+, a compatible Maven installation, and dependencies from Maven Central. No `application.properties` or open HTTP port is needed.

### 7.5. Expected Output

Filter for the lines **printed by the example code itself**; the Spring Boot banner and other logs may appear in between. Expected order:

~~~text
01_RESOURCE_CREATED
WORKER_START generation=1
03_CONTEXT_REFRESHED
04_APPLICATION_STARTED
05_RUNNER running=true destroyed=false
06_APPLICATION_READY
07_BEFORE_STOP active=true running=true destroyed=false
WORKER_STOP generation=1
09_CONTEXT_STOPPED
10_AFTER_STOP active=true running=false destroyed=false
WORKER_START generation=2
12_CONTEXT_STARTED
13_AFTER_START active=true running=true destroyed=false
14_CONTEXT_CLOSED running=true destroyed=false
WORKER_STOP generation=2
16_RESOURCE_DESTROYED
17_AFTER_CLOSE active=false running=false destroyed=true
~~~

This ordering matches the illustrative program and synchronous listeners. Numbered labels skip 02/08/11/15 because those four lines print the action name with `generation`; numeric labels are not Spring APIs.

### 7.6. Interpreting Each Part of the Output

**Startup:**
1. `01_RESOURCE_CREATED`: container creates the SharedResource singleton, not yet destroyed.
2. `WORKER_START generation=1`: `DefaultLifecycleProcessor.onRefresh()` auto-starts SmartLifecycle during refresh.
3. `03_CONTEXT_REFRESHED`: context refresh completes.
4. `04_APPLICATION_STARTED`: Boot finished refresh, before runners.
5. `05_RUNNER ...`: Runner executes after started; the resource remains open.
6. `06_APPLICATION_READY`: Runner succeeded; Boot publishes ready.

**Explicit Stop:**
7. `07_BEFORE_STOP`: context is active, worker is running, resource is not destroyed.
8. `WORKER_STOP generation=1`: `context.stop()` asks the lifecycle bean to stop.
9. `09_CONTEXT_STOPPED`: the stop event is published.
10. `10_AFTER_STOP active=true running=false destroyed=false`: **key proof**: stop neither tears down the context nor destroys the singleton.

**Restart:**
11. `WORKER_START generation=2`: worker starts again after stop.
12. `12_CONTEXT_STARTED`: framework publishes the context started event.
13. `13_AFTER_START ...`: the same context remains active, the same SharedResource remains un-destroyed; the runner does not re-execute.

**Close:**
14. `14_CONTEXT_CLOSED running=true destroyed=false`: the close event arrives **before** the lifecycle processor stops the worker and destroys the resource.
15. `WORKER_STOP generation=2`: lifecycle processor stops the worker as the context closes.
16. `16_RESOURCE_DESTROYED`: singleton destroy method runs after the lifecycle stop step.
17. `17_AFTER_CLOSE active=false running=false destroyed=true`: the context has ended its lifecycle.

Notably, during close there is no extra `09_CONTEXT_STOPPED`; that is because `close()` uses its own closing path rather than calling `context.stop()` and publishing the same event as an explicit stop command.

## 8. Comparing Context and Bean States

Do not equate these three checks:

~~~java
context.isActive();
context.isRunning();
worker.isRunning();
~~~

- `context.isActive()`: whether the context as a whole is still considered active.
- `context.isRunning()`: state of `LifecycleProcessor` (representing lifecycle commands).
- `worker.isRunning()`: the **individual** state reported by a Lifecycle/SmartLifecycle bean.

In an application with many beans, `context.isRunning() == true` **does not prove every component is operating properly**. A bean may have failed, not implement Lifecycle, or maintain its own state.

Typical interpretation table:

| Milestone | Context active | Lifecycle processor running | Worker running | Singleton destroyed |
| --- | --- | --- | --- | --- |
| After normal startup | true | usually true | true | false |
| After `context.stop()` | true | false | false | false |
| After `context.start()` | true | true | true | false |
| Upon receiving `ContextClosedEvent` | In the process of closing | May still be running | May still be running | Usually not yet |
| After `context.close()` returns | false | No lifecycle runtime left to use | false if cleanup completed | true for singletons with destroy callbacks |

In the demo, `EventTimeline.closed(...)` logs `running=true` and `destroyed=false` when receiving `ContextClosedEvent`, because the event fires before the lifecycle stop and bean destruction phases. Do not apply this table blindly to every custom context or abnormal shutdown environment.

## 9. Which Event Serves Which Purpose?

| Event | When? | What can it be used for? |
| --- | --- | --- |
| `ContextRefreshedEvent` | After context refresh | Observing that the container has been initialized |
| `ContextStartedEvent` | After `context.start()` | Recording an explicit lifecycle start |
| `ContextStoppedEvent` | After `context.stop()` | Recording an explicit lifecycle stop |
| `ContextClosedEvent` | When context begins closing | Tracking shutdown / signaling halt of activity |
| `ApplicationStartedEvent` | Spring Boot startup, after refresh before runners | Boot app start milestone, not a lifecycle restart |
| `ApplicationReadyEvent` | After runners, at end of Boot-managed startup | Observing Boot readiness, not equivalent to ContextStarted |
| `ApplicationFailedEvent` | During Spring Boot startup failure | Observing startup failure; does not mean close always fires |
| `AvailabilityChangeEvent` | When Boot/app publishes liveness/readiness | Reporting availability state independently of context start/stop |

Spring Framework events can propagate across a parent/child context hierarchy. If a listener in the parent context receives an event from a child, check `event.getApplicationContext()` before concluding the listener's own context has stopped or closed.

### ContextStoppedEvent Does Not Replace ContextClosedEvent

A listener watching only `ContextStoppedEvent` may **not be called** when the JVM shutdown hook closes the context directly. If a task must release bean resources when the application exits, use destruction callbacks such as `@PreDestroy`, `DisposableBean`, configured destroy methods, and/or `SmartLifecycle.stop(Runnable)`.

### ContextClosedEvent Does Not Mean Cleanup Finished

Because the event arrives early, listeners should perform brief tasks like logging, observation, and necessary state flips without assuming every connection is closed. For bean-owned resources, final cleanup belongs in that bean's lifecycle/destroy callback.

## 10. Should You Call context.stop() to Pause an HTTP Service?

**Not by default.** `context.stop()` is a control signal for Spring `Lifecycle` beans. In a web application, some embedded server components or listener containers also participate in lifecycle and may be stopped. That is not the same as a traffic-pausing protocol **designed for load balancers and Kubernetes**.

For maintenance/rolling deployments, the typical steps are:

1. Transition the instance to stop receiving new traffic via readiness mechanisms.
2. Wait for routing/load balancers to update and new requests to taper off.
3. Let in-flight requests finish within a reasonable deadline.
4. Stop consumers/workers via their lifecycles.
5. When terminating the process, invoke close along the normal shutdown path.

Calling `context.stop()` alone **does not guarantee**:
- That kubelet has removed the pod from Service endpoints.
- Whether the HTTP server keeps serving requests or stopped completely; details depend on server/lifecycle.
- That all in-flight requests have completed.
- That `ReadinessState` transitioned to `REFUSING_TRAFFIC`.
- That Spring Boot will re-publish `ApplicationReadyEvent` upon `context.start()`.

If you want to pause message processing while keeping administrative HTTP APIs alive, it is often better to **stop only the specific listener container/consumer** rather than stopping the entire context. For example, use the lifecycle API of a Kafka listener container, JMS listener container, or a specific SmartLifecycle bean after verifying its contract and dependencies.

### Liveness and Readiness Are Not context.isRunning

In Spring Boot, `ApplicationAvailability` maintains `LivenessState` and `ReadinessState` based on availability events. Use Actuator probes when standard signals are needed for orchestration. Do not look only at `context.isRunning()` to infer actual readiness.

During normal startup, Boot publishes:
- After `ApplicationStartedEvent`, liveness `CORRECT`.
- After runners and `ApplicationReadyEvent`, readiness `ACCEPTING_TRAFFIC`.

An explicit `context.stop()` command **is not a full Spring Boot startup/shutdown cycle**, so do not assume it flips availability states the same way an official Boot lifecycle does. If business logic requires rejecting traffic while paused, design explicit readiness publication and routing coordination.

## 11. Graceful Shutdown and context.close()

In Spring Boot web applications, graceful shutdown executes along the `ApplicationContext` closing path and coordinates with `SmartLifecycle` stop phases. In Spring Boot 3.5, graceful shutdown is the default for supported embedded servers.

Reference configuration:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

`server.shutdown=graceful` specifies the mode explicitly; `spring.lifecycle.timeout-per-shutdown-phase` caps the wait time per phase. Some versions/distributions have different defaults, so always verify the actual version and configuration. External systems like Kubernetes also enforce their own `terminationGracePeriodSeconds` and load balancer drain timeouts.

**Limits to remember:**
- Phase timeout **does not force-kill** every thread or network task cleanly.
- When the JVM hits `SIGKILL` or crashes, shutdown hooks may not run.
- While the server stops accepting requests, readiness endpoints may **return no response at all** rather than a 503 JSON body.
- Long-running tasks need cancellation, timeouts, or appropriate checkpoint/retry mechanisms.
- Closing the context does not guarantee tasks external to the JVM have finished.

### Where Is Calling stop Then close Useful?

In a multi-step shutdown procedure, you can explicitly stop a group of consumers early to halt work intake, then close the context once the workload drains. However, calling `context.stop()` on the whole context may also stop infrastructure components needed for draining (servers, schedulers, listeners, etc.). Therefore prefer **component-level lifecycle** coordination when selective control is required.

## 12. Closing the Context, Ending the JVM, and SpringApplication.exit

These three things are different:

| Command | Primary behavior | Does the JVM exit immediately on its own? |
| --- | --- | --- |
| `context.stop()` | Stops lifecycle beans | No |
| `context.close()` | Closes ApplicationContext, destroys managed singletons | Not necessarily |
| `SpringApplication.exit(context)` | Computes exit code from `ExitCodeGenerator` and closes context per Boot API | Does not call `System.exit(...)` itself |
| `System.exit(code)` | Requests JVM shutdown process, may run shutdown hooks | Yes, if the JVM executes the shutdown path |
| `Runtime.getRuntime().halt(code)` | Forcibly terminates the JVM | Bypasses shutdown hooks, risks data loss |

Example of a CLI application wanting to close the Spring context and return an exit code to the caller:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

This is an **illustrative, non-standalone snippet**: it requires a `MyApplication` class. Only use `System.exit` at an appropriate application entry point, never arbitrarily inside services or libraries.

In a typical web server, let Spring Boot's JVM shutdown hook and container orchestration handle termination instead of calling `System.exit` from a controller. Calling exit is a **process-level** decision, far broader than stopping or closing a single context.

### Spring Boot's Shutdown Hook

Spring Boot registers a shutdown hook by default to close the context when the JVM terminates normally along JVM-supported paths. The shutdown hook leads to **close**, not a standalone `context.stop()` meant to be resumed later.

However, there is no guarantee shutdown hooks run on `kill -9`, power outages, or JVM halt. Operations requiring cross-process durability still need independent transactions/idempotency/leases/retries.

## 13. Do Not Ignore Parent/Child Context Relationships

A single JVM can host multiple `ApplicationContext` instances, such as a parent sharing foundational services and children representing modules or web contexts.

Per the `ConfigurableApplicationContext.close()` contract, **closing a context does not automatically close its parent context**. Therefore:

- `child.close()` cleans up singletons owned by the **child**.
- Resources living in the parent must not be closed accidentally by the child.
- The parent can stay active after the child closes.
- Listeners in the parent may receive events propagated up from the child; filter by `event.getApplicationContext()`.
- `child.stop()` is a lifecycle command for that context and should not be assumed to stop the whole hierarchy without verifying the mechanism involved.

Resource ownership and context boundaries are two critical concerns. For instance, a child service injected with a parent-owned pool should not close that pool when the child stops or closes if the parent still serves other children.

### Is a Bean Outside the Context Stopped?

Not automatically. If you create an object with `new`, do not register it as a Spring bean, and do not attach it to the lifecycle processor, `context.stop()` or `context.close()` will not know to invoke lifecycle methods on it. Your code must either transfer resource ownership to a managed bean or clean it up in the proper scope.

## 14. Lifecycle, Destruction, and Resource Ownership

Not every bean implements Lifecycle. Choose the right extension point:

| Responsibility | Appropriate mechanism |
| --- | --- |
| Pause/restart a background worker | `Lifecycle` or `SmartLifecycle` |
| Stop a consumer with phases/async completion | `SmartLifecycle.stop(Runnable)` |
| Close a Spring-owned HTTP/JDBC pool | `@Bean(destroyMethod=...)`, `@PreDestroy`, or `DisposableBean` |
| Close a stream/response for a single operation | `try-with-resources` at the operation site |
| Signal that context is closing | `ContextClosedEvent` listener |
| Signal that context stopped from explicit command | `ContextStoppedEvent` listener |
| Change readiness for orchestrator | `AvailabilityChangeEvent<ReadinessState>` and Actuator probe |
| Run one-time work after refresh | `ApplicationRunner` / `CommandLineRunner` |
| Complete startup and accept traffic | `ApplicationReadyEvent` + readiness policy |

### Why Doesn't @PreDestroy Run on stop?

`@PreDestroy` is a bean **destruction** callback, not a `Lifecycle` stop. `stop()` does not destroy beans, so it does not run this callback. Spring retains the bean so it can be started again.

If a bean closes a client inside `@PreDestroy`, that fits end-of-context-life cleanup; it will not automatically "pause" the client every time `context.stop()` runs. If business logic requires pausing a client/worker, provide a dedicated stop API.

### Why Does close Invoke Both stop and destroy?

Because the two actions serve different purposes:
1. **Stop operations:** stop accepting new work, await in-flight work, or release subscriptions.
2. **Release ownership:** close pools/clients/files/sockets, destroy singletons, and terminate the context.

A SmartLifecycle consumer may use a shared DataSource. During a clean shutdown, the consumer must halt operations before the DataSource is destroyed. Spring coordinates this via lifecycle phases and dependencies; you must still test real behavior with asynchronous resources.

### Singleton/Prototype Limitations

Spring manages destruction for container-owned singletons. For a prototype bean once created and handed off, the container does not automatically invoke destroy callbacks for each prototype instance. Therefore, even `context.close()` is **not a guaranteed cleanup mechanism for all prototypes**. The owner of the prototype resource remains responsible for cleanup per contract.

## 15. Common Misconceptions

**Mistake 1 — "context.stop() shuts down the entire Spring Boot app."** No. It stops Lifecycle beans, while the context and many singletons remain alive.

**Mistake 2 — "context.stop() automatically triggers @PreDestroy."** No. `@PreDestroy` belongs to bean destruction, typically occurring on close.

**Mistake 3 — "context.close() is just a stronger stop and can be started again."** No. It marks the end of the context's lifecycle.

**Mistake 4 — "close will publish ContextStoppedEvent."** Not by default. Close emits `ContextClosedEvent`; lifecycle stop happens inside the close path, distinct from an explicit stop command.

**Mistake 5 — "ContextClosedEvent arrives after all resources are closed."** No. The event fires early, before singleton destruction on the standard close path.

**Mistake 6 — "ContextStartedEvent and ApplicationStartedEvent are the same."** No. One comes from Framework's `context.start()`, the other from Boot's `SpringApplication.run`.

**Mistake 7 — "context.start() reruns @PostConstruct and ApplicationRunner."** No. Start only coordinates lifecycle beans; it does not refresh the container or run runners again.

**Mistake 8 — "isActive() must be false after stop()."** No. Active indicates whether the context is alive, not whether lifecycle components are running.

**Mistake 9 — "context.isRunning() proves all requests and background jobs are safe."** No. It reflects only the lifecycle processor state; unmanaged threads or async workloads need separate contracts.

**Mistake 10 — "stop() is enough for Kubernetes to stop sending requests."** There is no such guarantee; proper readiness probes and routing orchestration are needed.

**Mistake 11 — "Closing the context guarantees the JVM exits."** No. Non-daemon threads, other contexts, or resources outside Spring can still keep the process alive.

**Mistake 12 — "Closing the context runs @PreDestroy on every prototype."** No. Spring does not automatically destroy handed-off prototypes.

**Mistake 13 — "A SmartLifecycle needs isAutoStartup=true for context.start() to run it."** No. isAutoStartup governs auto-start at refresh; explicit start can start lifecycle components.

**Mistake 14 — "Stopping once and restarting always works for every resource."** No. A library may forbid restarting once an internal client closes; a new generation or explicit policy is needed.

**Mistake 15 — "Closing a child context always closes its parent context."** No. Parents have independent lifecycles; avoid accidentally closing shared resources.

## 16. How to Verify in a Real Application

### 16.1. Separate Logs by Three Concerns

When debugging, log separately:

~~~text
eventType      = ContextStoppedEvent / ContextClosedEvent / ContextStartedEvent
contextId      = event.getApplicationContext().getId()
contextActive  = context.isActive()
workerRunning  = worker.isRunning()
resourceClosed = resource.isClosed()
~~~

This is an **illustrative data schema**, not automatic Spring logging. With multiple contexts, do not infer from a child event that the parent has closed.

### 16.2. Measure Real Shutdown

For workers with in-flight tasks, measure:
- When new work intake is refused.
- Count of remaining active tasks.
- Wait duration inside `SmartLifecycle.stop(Runnable)`.
- When the resource owner closes pools/clients.
- Phase timeouts vs. actual stop callback completion.
- When `context.close()` returns.

If Spring waits until timeout, check whether the stop callback is invoked after resources finish. If stop reports done too early, check whether task executor threads remain alive after close.

### 16.3. Testing stop, start, close Independently

On a self-created test context, you can assert:

~~~text
after run():     isActive = true, workerRunning = true
after stop():    isActive = true, workerRunning = false
                 resourceDestroyed = false
after start():   isActive = true, workerRunning = true
                 resourceDestroyed = false
after close():   isActive = false, workerRunning = false
                 resourceDestroyed = true
~~~

That is the expected behavior for a resource/worker designed like the demo, not an absolute rule for every Spring bean.

### 16.4. Checking Call Counts

A ManagedWorker bean should have counts:
- Auto-start during refresh: 1.
- Explicit stop: 1.
- Restart: 2.
- Context close while running: second stop.

The ApplicationRunner count stays **one** because it is not invoked again on `context.start()`. Singleton destroy methods run on close, not on stop.

### 16.5. Testing Failures and Abnormal Shutdown

Test additionally:
- Stopping when bean is already STOPPED: no-op and valid callback.
- Asynchronous stop timeout: lifecycle processor waits as configured, without hanging forever.
- Starting when resource is already destroyed: must fail clearly without faking a running state.
- Closing when startup fails partway through: only a subset of beans may exist; do not assume events/stops follow the happy path.
- SIGKILL: cleanup may not run; verify recovery mechanisms outside the JVM.
- Multiple contexts: closing child does not close parent-owned resources.
- Web server: verify readiness and in-flight requests, not just lifecycle state.

## 17. Scenarios: Choosing stop vs. close

### Scenario A — Temporarily Pausing a Message Consumer

**Requirement:** halt message consumption for a while, then resume.

Control the lifecycle of the **specific message listener container/consumer** if the API supports stop/start, avoiding stopping the entire ApplicationContext. If the consumer is an independent SmartLifecycle, you can invoke `consumer.stop()` and then `consumer.start()` per contract while keeping DB pools and admin HTTP APIs alive.

Use `context.stop()` only if you genuinely want to stop **all** lifecycle beans in the context and have checked the impact on the web server, schedulers, and dependencies.

### Scenario B — Completing a CLI Batch Job and Exiting

**Requirement:** run the job, then close all application resources.

Use try-with-resources on `ConfigurableApplicationContext` or `SpringApplication.exit(context)` per contract. Calling `context.stop()` alone can leave datasources, HTTP clients, and singletons needing destruction open.

### Scenario C — Rolling Deployment on Kubernetes

**Requirement:** stop receiving new requests, let existing requests finish, then terminate the pod.

Use readiness, web server graceful shutdown, termination grace periods, and context close in operational order. Do not use `context.stop()` as the sole means to mark "pod unready".

### Scenario D — Pausing Background Processing for Maintenance

**Requirement:** stop workers while keeping status-query APIs running.

Stop the **worker bean**, with a restart policy. Stopping the context may halt other lifecycle beans too, causing unintended disruption.

### Scenario E — Integration Test Creating a Context Manually

**Requirement:** verify bean shutdown.

`context.stop()` fits testing the Lifecycle contract; `context.close()` fits testing destroy callbacks and ensuring context release. When Spring TestContext owns the context cache, do not manually close the context in every test if the framework needs to reuse it; use the supported test lifecycle mechanisms.

### Scenario F — Application with Parent/Child Contexts

**Requirement:** unload a child module without stopping shared parent resources.

Use `child.close()` to release child-owned beans per contract; do not automatically close parent pools. If you only want to pause the module's lifecycle, `child.stop()` may fit better, though you must check dependencies and which beans actually stop.

## 18. Self-Assessment Questions

**Question 1:** Does `context.stop()` destroy singleton beans?

**Answer:** No. It signals lifecycle stop, while the bean factory and singletons remain intact.

**Question 2:** Why is `context.isActive()` still true after `stop()`?

**Answer:** Because stop does not close the context. `isActive` reflects that the context remains alive after refresh, not that all workers are running.

**Question 3:** Does `context.start()` after stop re-run `ApplicationRunner.run()`?

**Answer:** No. Runners are a step inside `SpringApplication.run`, not a callback belonging to `LifecycleProcessor.start()`.

**Question 4:** Which event is associated with `context.start()`?

**Answer:** Spring Framework's `ContextStartedEvent`, not Spring Boot's `ApplicationStartedEvent`.

**Question 5:** Which event is associated with `context.close()`?

**Answer:** `ContextClosedEvent`. It is published when closing begins, before singleton destruction on the normal closing path.

**Question 6:** If calling close while a worker is running, must you call stop() first?

**Answer:** Not required. Close already coordinates lifecycle stop, though if long draining or staged separation is needed, you can coordinate earlier at the component level.

**Question 7:** Why mustn't you call start after close?

**Answer:** The context has ended its lifecycle and its bean factory/singletons may have been destroyed; restarting the app requires creating a new context.

**Question 8:** Does a bean not implementing Lifecycle automatically stop on `context.stop()`?

**Answer:** Not automatically just from the stop command. It must participate in lifecycle or be controlled by another component.

**Question 9:** Does `@PreDestroy` run on stop or close?

**Answer:** Destruction callbacks run when beans are destroyed, typically during context close, not simple stop.

**Question 10:** Once the context is closed, is the JVM guaranteed to exit?

**Answer:** No. Non-daemon threads or other contexts may remain alive; `close()` is not `System.exit`.

**Question 11:** Does calling close guarantee receiving an extra ContextStoppedEvent?

**Answer:** No. Close uses ContextClosedEvent; lifecycle stop executes through the processor without an explicit stop() call.

**Question 12:** Does `isAutoStartup() == false` mean explicit context.start will not run the bean?

**Answer:** No. That flag controls auto-start on refresh; explicit start can activate Lifecycle beans.

**Question 13:** Why does a `ContextClosedEvent` listener still see the worker running?

**Answer:** Because the event is published before lifecycle stop and singleton destruction on the standard closing path.

**Question 14:** Is a prototype bean guaranteed to be destroyed on close?

**Answer:** No. Spring does not automatically manage destruction of prototypes after handoff; the caller is responsible for cleanup.

**Question 15:** To stop a consumer while keeping APIs active, what should you do?

**Answer:** Prefer controlling the lifecycle of the specific consumer rather than stopping the entire context.

## 19. Practice Exercises

### Exercise 1 — Run the Demo and Verify the Comparison Table

Run the code from section 7 and mark:
- The `context.stop()` and `ContextStoppedEvent` milestones.
- The `context.start()` and `ContextStartedEvent` milestones.
- The `ContextClosedEvent`, final `WORKER_STOP`, and `RESOURCE_DESTROYED` milestones.
- The `active/running/destroyed` values after each operation.

Explain why destroy appears only when the context closes, not when it stops.

### Exercise 2 — Toggle isAutoStartup

Change `TrackedWorker.isAutoStartup()` to false. Predict `worker.isRunning()` inside the runner; next try calling `context.start()` and check whether the worker starts running. With this change, the marker lines/expected stdout of the original example will differ—record and explain them.

### Exercise 3 — Call stop Twice

In `main`, add a second `context.stop()` before start. Verify the worker does not release resources twice. Observe whether ContextStoppedEvent is published again under your context implementation, distinguishing event count from actual resource stop count.

### Exercise 4 — Add a @PreDestroy-Only Bean

Create a singleton `AuditSink` with `@PreDestroy` (Boot 3 uses `jakarta.annotation.PreDestroy`). Log on destroy. Verify stop does not run the regular bean's destroy callback, whereas close does.

### Exercise 5 — Distinguish from SpringApplication Events

Count occurrences of `ApplicationStartedEvent`, `ApplicationReadyEvent`, and `ContextStartedEvent`. After the stop → start sequence, do the Boot events repeat? Explain why.

### Exercise 6 — Observe Parent/Child

Create a parent context holding a resource and a child context holding a consumer. Close the child and verify the parent resource is not yet destroyed. Only when closing the parent afterward is the parent-owned resource released.

### Exercise 7 — Design Graceful Stop

Replace the in-memory worker with an executor having an in-flight task; implement `SmartLifecycle.stop(Runnable)` to invoke the callback only once the task finishes, with a timeout. Verify that during `context.close()`, Spring waits for the phase and closes the resource after the stop step. Do not ship fake sleeps to production.

### Exercise 8 — Inspect Readiness

In a web app with Actuator, compare `ApplicationAvailability`, `/actuator/health/readiness`, and `context.isRunning()` before and after a coordinated stop call. Do not guess readiness from stop: inspect actual states, note which beans/web server are affected, and choose component-level stop if you need to keep APIs up.

## 20. Official Documentation

Use the documentation below to verify Spring Framework/Spring Boot contracts. For different dependency versions, cross-check the corresponding release branch:

- [Spring Framework 6.2 — Standard ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): defines `ContextStartedEvent`, `ContextStoppedEvent`, `ContextClosedEvent`, and restarting a stopped context.
- [Spring Framework 6.2 — Lifecycle and Shutdown Callbacks](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): `Lifecycle`, `SmartLifecycle`, `LifecycleProcessor`, auto-start, and destroy.
- [Spring Framework — ConfigurableApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): `start`, `stop`, `close`, `isActive`, and lifecycle notes.
- [Spring Framework — AbstractApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): `doClose`, `destroyBeans`, context lifecycle, and events.
- [Spring Framework — DefaultLifecycleProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): phase coordination of Lifecycle beans, start, and stop.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): ApplicationStartedEvent, ApplicationReadyEvent, runners, and availability.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): shutdown during context closure and per-phase timeout.
- [Spring Boot 3.5.16 Released](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/): confirms the demo version.

## 21. Checklist and Summary

Before deciding whether to call `stop()` or `close()`, ask yourself:

1. Do I want to **pause** or **permanently end** the runtime?
2. Do I need to **restart the same beans/context** or not?
3. Which beans implement `Lifecycle`/`SmartLifecycle`, and which only have destroy callbacks?
4. If stopping the entire context, which HTTP server/schedulers/consumers could be affected?
5. Which resources must **stay alive** during a pause, and which should close at termination?
6. Are there in-flight tasks requiring graceful draining and stop callbacks?
7. Does readiness routing from Kubernetes/load balancers need separate coordination?
8. Are listeners watching the right `ContextStoppedEvent` vs. `ContextClosedEvent`?
9. Does the context have a parent/child relationship, and who owns shared resources?
10. Are there mechanisms for startup errors, forced shutdowns, and timeouts?

**Final takeaways:**

- `context.stop()` only stops lifecycle components; it **does not destroy singletons** and **does not make the context inactive**.
- `context.start()` after stop can restart components that support restarting; it **does not refresh the container** or rerun runners or the Spring Boot Ready event.
- `context.close()` ends the lifecycle: publishes `ContextClosedEvent`, stops Lifecycle beans, **destroys singletons**, and closes the BeanFactory/context.
- `ContextStoppedEvent` and `ContextStartedEvent` are Framework events for explicit stop/start commands, distinct from Boot's `ApplicationStartedEvent` and `ApplicationReadyEvent`.
- `ContextClosedEvent` occurs **before** destruction callbacks; do not assume every resource is already closed inside the event listener.
- To pause a workload, consider controlling the **specific bean**; to shut down an application, use proper close/graceful shutdown.
- `stop()` is not readiness, and `close()` does not guarantee the JVM has exited; orchestration and resource ownership must be designed separately.
