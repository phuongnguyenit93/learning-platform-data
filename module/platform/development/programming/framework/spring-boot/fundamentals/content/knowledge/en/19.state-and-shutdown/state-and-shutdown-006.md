# Lifecycle, SmartLifecycle, and Phased Start/Stop Ordering

When a Spring Boot application runs, not every component simply needs to be created and then used. Some components also need to **start** an activity with its own lifecycle—such as opening a message-receiving consumer, starting an event receiver, starting a self-managed scheduler, or activating a long-lived connection. When the application shuts down, these components must **stop accepting new work, finish in-flight work, and release resources** in an appropriate order.

Spring Framework provides the `Lifecycle` and `SmartLifecycle` contracts to model these `start()` and `stop()` operations. Spring manages them through `LifecycleProcessor`, typically `DefaultLifecycleProcessor`, and uses **phase** to determine which group of components starts earlier and stops later.

A common point of confusion is that **phase is not the constructor instantiation order**. Phase orders the start/stop calls of beans participating in lifecycle. Bean creation, dependency injection, `@PostConstruct`, and destruction callbacks still follow the separate bean lifecycle mechanism.

## 1. Why Does a Bean Need Its Own Lifecycle?

An ordinary bean can operate immediately once initialized by Spring:

~~~java
@Service
public class PricingService {
    public long total(long price, long shippingFee) {
        return price + shippingFee;
    }
}
~~~

`PricingService` does not need an independent "begin processing" command. It simply provides business methods.

By contrast, a message consumer may need to:

1. Create the object and receive dependencies.
2. Establish a connection or register a subscription.
3. Begin receiving messages from the broker.
4. Operate throughout the application's lifetime.
5. On shutdown, stop accepting new messages.
6. Complete or cleanly cancel in-flight messages.
7. Close connections and release resources.

If those steps are placed entirely in a constructor or `@PostConstruct`, it becomes difficult to coordinate start and stop ordering across multiple components. The `Lifecycle` contract separates **creating an object** from **enabling or disabling an active operation**.

Example:

~~~text
Bean creation             Runtime operation              Application close
   |                            |                              |
   v                            v                              v
constructor -> injection -> initialization -> start() -> ... -> stop() -> destroy
                                                 ^                 ^
                                                 |                 |
                                           Lifecycle             Lifecycle
~~~

The diagram illustrates milestones at a high level. Depending on scope and how the application runs, not every bean participates in every step.

## 2. Lifecycle: Spring's Basic Contract

`Lifecycle` is an interface in Spring Framework:

~~~java
import org.springframework.context.Lifecycle;
~~~

It has three main methods:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Meaning:

| Method | Responsibility |
|---|---|
| `start()` | Moves the component into an active running state |
| `stop()` | Halts activity and performs necessary stopping actions |
| `isRunning()` | Reports current active state per the component's contract |

Example of a simple component:

~~~java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.Lifecycle;
import org.springframework.stereotype.Component;

@Component
public class PollingController implements Lifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("Polling enabled");
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("Polling disabled");
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }
}
~~~

The example only represents toggle state; a real polling component must also manage workers, scheduling, exceptions, and I/O resources. `AtomicBoolean` makes the illustration safer when state may be accessed from multiple threads.

### 2.1. Lifecycle Does Not Automatically Start on Refresh by Default

A bean implementing only plain `Lifecycle` **does not automatically start simply because the context refreshes**, under standard `DefaultLifecycleProcessor` rules. It typically starts when `ApplicationContext.start()` is explicitly called, or when starting another dependent component forces related lifecycle processing.

Example:

~~~java
import org.springframework.context.ConfigurableApplicationContext;

ConfigurableApplicationContext context = /* already created context */;
context.start();  // Ask lifecycle processor to start Lifecycle beans.
context.stop();   // Ask lifecycle processor to stop Lifecycle beans.
~~~

Calling `start()` or `stop()` on the context is a lifecycle request. It **is not equivalent** to recreating/refreshing the application context or closing it completely.

If a component must automatically start operating during normal Spring Boot startup, `SmartLifecycle` is usually more suitable.

## 3. SmartLifecycle: Extending Lifecycle for Auto-Startup and Coordinated Shutdown

`SmartLifecycle` resides in:

~~~java
import org.springframework.context.SmartLifecycle;
~~~

This interface extends `Lifecycle` and `Phased`, while adding these concepts:

- **Auto-startup:** whether the bean should automatically start during context refresh.
- **Phase:** relative priority order when starting and stopping multiple lifecycle beans.
- **Asynchronous stop callback:** allows signaling when stopping completes via `stop(Runnable callback)`.

With modern Spring Framework default behavior, `SmartLifecycle.isAutoStartup()` returns `true` and SmartLifecycle's default phase is `SmartLifecycle.DEFAULT_PHASE` (`Integer.MAX_VALUE`). You can override both methods to express your module's actual needs.

### 3.1. Complete SmartLifecycle Example

~~~java
package com.example.messaging;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class MessageIngressLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("Start accepting messages");
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("Stop accepting messages");
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
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
~~~

Here:

- When Spring processes startup and the lifecycle processor starts auto-start SmartLifecycle beans, it can invoke this component's `start()`.
- `isRunning()` reflects whether the component is currently enabled.
- `getPhase() = 100` places it in a relative lifecycle group.
- `stop(Runnable callback)` calls `stop()` and then signals completion via `callback.run()`.

The example stops synchronously, so the callback is called right after `stop()` finishes. If stopping message intake and waiting for in-flight messages takes time, do not invoke the callback immediately; implement asynchronous stopping properly as shown in the next section.

## 4. What Is Phase?

`SmartLifecycle` has `getPhase()` from the `Phased` interface:

~~~java
@Override
public int getPhase() {
    return 100;
}
~~~

**Phase is an integer expressing relative ordering across groups of lifecycle beans.**

Rule:

- **Start:** lower phases run **before** higher phases.
- **Stop:** higher phases are stopped **before** lower phases.

Example with three components:

| Bean | Phase | Responsibility |
|---|---:|---|
| `ConnectionInfrastructure` | -100 | Prepare connection infrastructure |
| `MessageProcessor` | 0 | Process messages |
| `InboundConsumer` | 100 | Begin receiving new messages |

On startup:

~~~text
START: ascending by phase

phase -100: ConnectionInfrastructure.start()
      |
      v
phase    0: MessageProcessor.start()
      |
      v
phase  100: InboundConsumer.start()
~~~

On shutdown:

~~~text
STOP: descending by phase

phase  100: InboundConsumer.stop(...)
      |
      v
phase    0: MessageProcessor.stop(...)
      |
      v
phase -100: ConnectionInfrastructure.stop(...)
~~~

This ordering is operationally useful: **infrastructure comes up before accepting work, and only shuts down after stopping intake**.

### 4.1. Why Does Stop Run in Reverse of Start?

Suppose the consumer needs the processor, and the processor needs the connection.

If shutdown ran in the same order as start, the connection could close before the consumer stopped accepting messages and the processor finished processing. The result would be I/O errors and dropped mid-flight work.

When shutting down in reverse:

1. Consumer stops pulling new messages.
2. Processor finishes or cleanly cancels remaining tasks.
3. Connections and supporting infrastructure are released last.

This principle is standard in systems with producers/consumers, listener containers, streaming pipelines, and resource pools.

### 4.2. Negative, Zero, and Positive Phases

Phase can be negative, zero, or positive:

~~~java
@Override
public int getPhase() {
    return -1000;
}
~~~

There is no requirement for phases to start at 0. You can use meaningful ranges such as:

~~~text
-1000  Foundational infrastructure
 -100  Runtime dependencies
    0  Processing processors
  100  Inbound consumers
 1000  Entry points that should start last
~~~

These are **project-chosen conventions**, not mandatory Spring values. The goal is leaving enough spacing to add new components without renumbering every phase.

### 4.3. Default Phase

In modern Spring Framework:

- Beans implementing `SmartLifecycle` have a default phase of `SmartLifecycle.DEFAULT_PHASE`, corresponding to `Integer.MAX_VALUE`.
- Beans implementing only `Lifecycle` without `Phased` are usually treated as phase 0 by the lifecycle processor when ordering.

Thus, a `SmartLifecycle` that does not override `getPhase()` typically starts quite late and stops quite early compared to beans with smaller phases.

Do not blindly assume all framework beans share the same default phase. Components such as web servers, message listener containers, or schedulers may declare their own phases. When coordinating precisely with a framework bean, check that component's phase in the library version you are using.

## 5. SmartLifecycle and Auto-Startup

`SmartLifecycle` defines:

~~~java
@Override
public boolean isAutoStartup() {
    return true;
}
~~~

When `isAutoStartup()` returns `true`, `DefaultLifecycleProcessor` attempts to start the bean during context refresh, following phase order and dependencies.

If you want a component **not to start automatically** at startup:

~~~java
@Override
public boolean isAutoStartup() {
    return false;
}
~~~

Then the component can be started explicitly via the lifecycle processor or when `context.start()` is called, depending on orchestration. Distinguish clearly: `isAutoStartup() = false` does not mean Spring skips creating the bean instance. It only controls whether **`start` is automatically invoked during lifecycle refresh**.

### 5.1. SmartLifecycle and @Lazy

Another misconception is that adding `@Lazy` alone prevents a `SmartLifecycle` from being created at application startup:

~~~java
@Lazy
@Component
class BackgroundConsumer implements SmartLifecycle {
    // ...
}
~~~

In many cases, the lifecycle processor must inspect `SmartLifecycle` beans to decide auto-startup, which can still cause the bean to be instantiated during refresh even with `@Lazy` on the bean definition. Spring Framework notes that auto-startup support limits the effect of lazy-init on `SmartLifecycle`.

If the business requirement is **only creating and running a component when a user actually requests it**, do not rely solely on `@Lazy` combined with `SmartLifecycle` auto-start. Consider a deliberate provider/factory with explicitly managed lifecycles.

## 6. How Does DefaultLifecycleProcessor Work?

`LifecycleProcessor` is the interface Spring's `ApplicationContext` uses to control lifecycle beans. The default implementation is typically `DefaultLifecycleProcessor`.

It has two major responsibilities:

1. Once context refresh finishes required initialization steps, invoke lifecycle startup for eligible beans.
2. When the context closes, coordinate lifecycle stopping by phase before the container destroys managed singletons.

At a high level:

~~~text
ApplicationContext.refresh()
           |
           v
Create/register beans and finish required refresh steps
           |
           v
LifecycleProcessor.onRefresh()
           |
           v
Select auto-start SmartLifecycle beans and related dependencies
           |
           v
Start in ascending phase order
           |
           v
Context finishes refresh
           |
           v
Spring Boot events and runners follow next
~~~

And when the context closes:

~~~text
ApplicationContext.close()
           |
           v
Publish ContextClosedEvent
           |
           v
LifecycleProcessor.onClose()
           |
           v
Stop in descending phase order
           |
           v
Destroy singletons and call destruction callbacks
           |
           v
Release context resources
~~~

Note that Spring has more intricate shutdown steps, and closing can be affected by errors or timeouts. The diagram highlights the key relationship: **Lifecycle stop runs before regular bean destruction** during a controlled shutdown.

### 6.1. context.start() vs. context.refresh()

~~~java
context.start();
~~~

is a request to start lifecycle beans in an already-prepared context. It does not create a new application context, nor does it re-run the entire bean definition registration process.

Similarly:

~~~java
context.stop();
~~~

asks lifecycle beans to stop, while the context can still remain alive. Only `context.close()` executes container closing and destruction lifecycle.

In other words:

| Action | Meaning |
|---|---|
| `refresh()` | Builds/refreshes the context per implementation contract |
| `start()` | Requests `Lifecycle` beans to start |
| `stop()` | Requests `Lifecycle` beans to stop |
| `close()` | Closes context and destroys context-managed resources/beans |

In Spring Boot, do not arbitrarily call `refresh()` on a running context just to "restart a service". Start/stop requirements for a component should be designed through that component's own lifecycle or an appropriate container.

## 7. @DependsOn and Real Dependencies Can Take Precedence Over Phase

Phase is an ordering rule for lifecycle, yet **explicitly declared dependency relationships carry important precedence**.

Suppose a consumer bean has a lower phase than a connection pool, yet the consumer declares a dependency on the pool:

~~~java
@Configuration(proxyBeanMethods = false)
class IntegrationConfiguration {

    @Bean("connectionManager")
    ConnectionManager connectionManager() {
        return new ConnectionManager();
    }

    @Bean("inboundConsumer")
    @DependsOn("connectionManager")
    InboundConsumer inboundConsumer(ConnectionManager manager) {
        return new InboundConsumer(manager);
    }
}
~~~

In the example:

- Bean `inboundConsumer` depends on `connectionManager`.
- Spring must resolve and create the dependency when instantiating the consumer.
- For lifecycle dependencies, the processor strives to ensure the dependency starts before the dependent and stops after the dependent, even if phases appear reversed.

To keep designs easy to understand, make **phases and the dependency graph consistent** instead of creating conflicting orders intentionally.

If B needs A as a normal dependency, prefer constructor injection or `@Bean` parameters:

~~~java
@Bean
InboundConsumer inboundConsumer(ConnectionManager manager) {
    return new InboundConsumer(manager);
}
~~~

`@DependsOn` is useful when enforcing initialization order by bean name without direct dependency injection—for instance, a side-effect resource setup. Do not use it to hide an unmodeled business dependency.

### 7.1. @Order Does Not Control Lifecycle Phase

`@Order` is normally used to sort beans inside collections or ordering-aware extension points:

~~~java
@Component
@Order(10)
class FirstHandler implements Handler {
}
~~~

That is not equivalent to:

~~~java
@Override
public int getPhase() {
    return 10;
}
~~~

| Mechanism | Primary scope |
|---|---|
| `SmartLifecycle.getPhase()` | Coordinates start/stop of lifecycle components |
| `@Order` or `Ordered` | Sorts collections, pipelines, or ordering-aware extension points |
| `@DependsOn` | Creates initialization dependency order by bean name |
| Constructor injection | Expresses real dependencies between beans |
| `@AutoConfiguration(before/after)` | Processing order of auto-configuration classes, not start/stop order |

Do not substitute `@Order` for phase when the goal is "consumer must stop before connection manager".

## 8. stop(Runnable callback): Stopping Asynchronously the Right Way

`Lifecycle.stop()` is synchronous per the base interface. `SmartLifecycle` adds:

~~~java
void stop(Runnable callback);
~~~

This means the container can ask the component to start shutting down, and then **be notified when stopping work actually finishes**.

`callback.run()` is the completion signal to the lifecycle processor. For synchronous stopping, the callback can be invoked right after `stop()`:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

### 8.1. Asynchronous Stopping Must Report Completion Only When Truly Stopped

Suppose a component has a stop API returning `CompletionStage<Void>`:

~~~java
public interface MessageReceiver {
    void startReceiving();
    java.util.concurrent.CompletionStage<Void> stopAndDrainAsync();
}
~~~

A `SmartLifecycle` can implement:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;

public final class ReceiverLifecycle implements SmartLifecycle {

    private final MessageReceiver receiver;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public ReceiverLifecycle(MessageReceiver receiver) {
        this.receiver = receiver;
    }

    @Override
    public void start() {
        if (!running.get()) {
            receiver.startReceiving();
            running.set(true);
        }
    }

    @Override
    public void stop(Runnable callback) {
        if (!running.get()) {
            callback.run();
            return;
        }

        try {
            receiver.stopAndDrainAsync().whenComplete((ignored, failure) -> {
                try {
                    if (failure != null) {
                        // Record stop error using the application's logger.
                    }
                    running.set(false);
                } finally {
                    callback.run();
                }
            });
        } catch (RuntimeException ex) {
            running.set(false);
            callback.run();
            throw ex;
        }
    }

    @Override
    public void stop() {
        // Direct stop path must have its own synchronous policy.
        receiver.stopAndDrainAsync().toCompletableFuture().join();
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 100;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

`MessageReceiver` is an application-defined abstraction; this snippet illustrates **when the callback should be invoked**, not a full message broker implementation.

Key points:

- Do not call `callback.run()` immediately after scheduling an async stop task if the task is still running.
- Ensure the callback is invoked after the receiver stops accepting messages and draining completes or ends under the error policy.
- On the synchronous `stop()` path, ensure the state is actually stopped before returning.
- Stop operations should be idempotent because shutdown, failure handling, or manual control can encounter the same component in multiple states.

In real systems, `stop()` and `stop(Runnable)` should share a state machine or a controlled stop operation to avoid double stopping, invoking the callback twice, or race conditions.

### 8.2. What Happens If You Forget to Call the Callback?

The lifecycle processor uses the callback to learn when a `SmartLifecycle` has finished stopping. If a component fails to call the callback, shutdown may have to wait until **the phase timeout expires** before moving on.

Observable symptoms:

- Slow application shutdown.
- Timeout warnings logged for a phase group.
- Lower-phase dependencies held open longer than expected.
- Kubernetes or the orchestration system running out of allowed time before shutdown completes.

Therefore, an async-stopping `SmartLifecycle` must design **success, failure, and cancellation** paths so the callback is always notified promptly. Never let an exception on a worker thread silently drop the completion signal.

## 9. Timeout per Shutdown Phase in Spring Boot

Stopping components can take time, especially when waiting for in-flight requests or messages. Spring Boot provides the property:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Or YAML:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

This property sets the maximum wait time for **each phase during shutdown**, within the scope of the corresponding lifecycle processor. It does not mean "the entire application is guaranteed to exit in exactly 20 seconds".

For example, with three phases:

~~~text
phase 100: wait for InboundConsumer stop (up to phase timeout)
phase   0: wait for MessageProcessor stop
phase -100: wait for ConnectionInfrastructure stop
~~~

If a phase contains multiple beans stopping asynchronously, the lifecycle processor coordinates waiting for callbacks in that phase within the phase time budget. Other phases still get their own stop windows.

Timeouts should be chosen based on business characteristics:

- How long does a normal task take to complete?
- Can new messages be stopped before awaiting in-flight tasks?
- On timeout, can tasks be canceled, rolled back, or redelivered?
- How long does the deployment platform allow a process to shut down?
- Do brokers or external services have their own timeouts?

**Do not just increase the timeout to mask a forgotten callback or an unstoppable component.** Timeouts are only a bound on waiting; components still need proper stop logic.

## 10. Combining with Web Server Graceful Shutdown

Lifecycle stop is helpful for message consumers, schedulers, and resource managers. For HTTP servers, Spring Boot also has **graceful shutdown** to stop accepting new requests per web server capabilities while giving in-flight requests time to complete.

Example configuration:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Distinguish clearly:

- `server.shutdown=graceful` selects graceful web server shutdown behavior supported by Spring Boot.
- `spring.lifecycle.timeout-per-shutdown-phase` governs the wait budget per phase during lifecycle shutdown.
- A custom consumer's `SmartLifecycle` must still implement its own intake stop, drain, and callback logic; graceful HTTP settings do not stop a message broker on the consumer's behalf.

Desired architecture example:

~~~text
Startup:
    create beans and resources
           |
           v
    start infrastructure
           |
           v
    start processors
           |
           v
    start traffic/message intake

Shutdown:
    stop accepting new traffic/messages
           |
           v
    wait for in-flight work to finish
           |
           v
    stop processors
           |
           v
    release infrastructure and resources
~~~

When mixing a web server with custom `SmartLifecycle` beans, check the web server lifecycle's phase on your Boot version to coordinate accurately. Do not guess that the web server is always at phase 0.

When the JVM receives SIGTERM, how the application context closes, and how long the orchestration platform allows are separate operational factors. If the environment only allows 10 seconds for process shutdown while the system has multiple phases with longer timeouts, lifecycle configuration cannot extend the deployment platform's hard deadline.

## 11. How Does SmartLifecycle Differ from @PostConstruct and @PreDestroy?

Both API groups relate to bean lifecycle, yet their timing and purpose differ.

| Mechanism | Execution milestone | Typical purpose |
|---|---|---|
| Constructor | When creating instance | Initialize basic state |
| Dependency injection | Before bean initialization finishes | Supply dependencies |
| `@PostConstruct` | After dependency injection | Prepare internal bean state |
| `SmartLifecycle.start()` | When lifecycle processor starts component | Start long-lived runtime activity |
| `SmartLifecycle.stop(Runnable)` | When lifecycle processor requests stop | Stop activity in order and report completion |
| `@PreDestroy` | When Spring destroys managed bean | Release final lifecycle resources |
| `DisposableBean.destroy()` | During destruction callbacks | Clean up at destroy stage |

Example of a bean that both prepares state and runs a consumer:

~~~java
@Component
public class JobConsumer implements SmartLifecycle {

    private boolean running;

    @PostConstruct
    void prepareResources() {
        // Internal initialization; do not start consuming messages yet.
    }

    @Override
    public void start() {
        running = true;
        // Start consuming.
    }

    @Override
    public void stop() {
        running = false;
        // Stop consuming.
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
~~~

In this example, `@PostConstruct` does not replace `start()`. Conversely, `@PreDestroy` also does not fully replace phased stopping when a component must yield to other components.

For modern Spring Boot based on Jakarta APIs, import:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

In Spring Boot 2.x versions based on Spring Framework 5.x, lifecycle annotation imports typically use the `javax.annotation` namespace. This change does not alter the semantics of `Lifecycle` or `SmartLifecycle`, which are Spring Framework interfaces.

## 12. Start/Stop Timing Compared to Startup Events and Runners

Spring Boot provides several startup milestones:

~~~text
Create and configure ApplicationContext
           |
           v
Refresh context and initialize required singletons
           |
           v
LifecycleProcessor.onRefresh() / SmartLifecycle.start()
           |
           v
Context refresh completes
           |
           v
ApplicationStartedEvent
           |
           v
ApplicationRunner / CommandLineRunner
           |
           v
ApplicationReadyEvent
~~~

This shows that an auto-starting `SmartLifecycle` is usually started **during context refresh**, before `ApplicationStartedEvent` and before runners execute.

If a component needs the application to have finished runners or be ready for traffic before starting a business job, using auto-start `SmartLifecycle` alone may hit the wrong milestone. Consider `ApplicationReadyEvent` or an appropriate startup orchestration mechanism.

At the same time, do not use `ApplicationReadyEvent` as a substitute for ordered stopping. A bean with long-lived runtime work may still need `SmartLifecycle` so Spring can coordinate it during shutdown.

## 13. Example with Three SmartLifecycle Beans

Suppose an application pulls messages from a queue and processes them using a shared resource. We separate three layers:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;

public abstract class AbstractPhasedComponent implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean();
    private final String name;
    private final int phase;

    protected AbstractPhasedComponent(String name, int phase) {
        this.name = name;
        this.phase = phase;
    }

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("START " + name);
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("STOP " + name);
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return phase;
    }
}
~~~

Declare the beans:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ProcessingLifecycleConfiguration {

    @Bean
    AbstractPhasedComponent connectionInfrastructure() {
        return new AbstractPhasedComponent("connection", -100) {};
    }

    @Bean
    AbstractPhasedComponent messageProcessor() {
        return new AbstractPhasedComponent("processor", 0) {};
    }

    @Bean
    AbstractPhasedComponent inboundConsumer() {
        return new AbstractPhasedComponent("consumer", 100) {};
    }
}
~~~

When Spring refreshes the context and auto-starts `SmartLifecycle` beans, expected order:

~~~text
START connection
START processor
START consumer
~~~

When the context closes cleanly:

~~~text
STOP consumer
STOP processor
STOP connection
~~~

This illustrates phase relationships. In real applications, components should have clear names and types, combined with dependency injection for the resources they use rather than just logging.

If two beans share the **same phase**, do not rely on registration order to enforce a required relationship between them. Use dependencies or distinct phases if a real start/stop relationship exists.

## 14. Testing Phases and Shutdown

You can test start/stop order using a small context to observe callbacks without starting a web server.

### 14.1. Bean Recording Lifecycle Events

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;

final class RecordingLifecycle implements SmartLifecycle {

    private final String name;
    private final int phase;
    private final List<String> events;
    private final AtomicBoolean running = new AtomicBoolean();

    RecordingLifecycle(String name, int phase, List<String> events) {
        this.name = name;
        this.phase = phase;
        this.events = events;
    }

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            events.add("start:" + name);
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            events.add("stop:" + name);
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

### 14.2. Test Configuration

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class LifecycleTestConfiguration {

    @Bean
    List<String> events() {
        return new CopyOnWriteArrayList<>();
    }

    @Bean
    RecordingLifecycle infrastructure(List<String> events) {
        return new RecordingLifecycle("infra", -100, events);
    }

    @Bean
    RecordingLifecycle consumer(List<String> events) {
        return new RecordingLifecycle("consumer", 100, events);
    }
}
~~~

### 14.3. Assertions Before and After Close

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class LifecyclePhaseTest {

    @Test
    void startsAscendingAndStopsDescending() {
        var context = new AnnotationConfigApplicationContext(
                LifecycleTestConfiguration.class);

        List<String> events = context.getBean("events", List.class);

        assertThat(events).containsExactly(
                "start:infra",
                "start:consumer"
        );

        context.close();

        assertThat(events).containsExactly(
                "start:infra",
                "start:consumer",
                "stop:consumer",
                "stop:infra"
        );
    }
}
~~~

The test creates the context, observes auto-start after refresh, then closes the context and verifies stopping occurs in reverse phase order. Because the sample callbacks are synchronous, the test can check ordering directly.

In real systems, add tests verifying:

- `isAutoStartup() = false` does not auto-start along the normal refresh path.
- `start()` and `stop()` can be called repeatedly without unintended side effects.
- `stop(Runnable)` only calls the callback after draining completes.
- Failure paths when draining fails still emit the completion signal per policy.
- Timeouts are handled when a component is unresponsive.
- `@DependsOn` dependencies are respected even when phases need coordination.
- After `close()`, the component stops accepting new work.

Unit testing `getPhase()` alone does not prove the container actually coordinates lifecycle properly. Test with a real `ApplicationContext` for critical start/stop constraints.

## 15. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Bean created yet never started | Only implemented `Lifecycle` or `isAutoStartup() = false` | Choose `SmartLifecycle` with proper auto-start; check `context.start()` calls |
| Listener/consumer starts too early | Phase too low or starts before resource is ready | Identify dependencies and raise phase appropriately |
| Resource closed before consumer stops | Phase and dependencies do not reflect usage relationship | Give consumer higher phase than resource; declare dependencies clearly |
| Application shuts down very slowly | `stop(Runnable)` never invokes callback or drain hangs | Ensure callback runs on all completion paths; set appropriate timeout |
| `isRunning` stays true after `stop` | State not updated properly | Design a state machine and update flag after stopping finishes |
| `@Order` does not change start order | Confusing collection ordering with lifecycle phase | Use `getPhase()` |
| `@Lazy` yet bean still created at startup | `SmartLifecycle` auto-start forces processor to inspect bean | Use true lazy architecture instead of relying on the annotation |
| `@PreDestroy` runs while tasks still receive messages | Missing lifecycle stop to block work intake | Implement stop, drain, and callback properly |
| Same phase for mutually dependent beans | Missing necessary dependency declaration | Use dependency injection or `@DependsOn` |
| Shutdown fails only in deployment | Platform timeout is smaller than drain time | Align operational deadlines with shutdown-phase timeout |

### 15.1. Observing Lifecycle via Logs

You can enable detailed logging for lifecycle infrastructure in development environments:

~~~properties
logging.level.org.springframework.context.support.DefaultLifecycleProcessor=DEBUG
~~~

Exact log messages depend on Spring version. Logs reveal which components are starting/stopping and aid in diagnosing timeouts. Avoid overly verbose logging in production if it generates excessive volume or exposes internal structure.

Beyond framework logs, critical components should log milestones such as "stop requested", "no longer accepting work", "in-flight work drained", and "callback completed", without logging secrets or sensitive payloads.

## 16. When Should You Use SmartLifecycle?

`SmartLifecycle` is useful for beans with **long-lived runtime activity that need separate start/stop control and coordination with other beans**:

- Consumers or listeners pulling messages from a broker.
- A self-managed scheduler loop or polling system.
- Components continuously reading data from sockets/streams.
- Multi-stage pipelines that must stop ingress before closing workers.
- Long-lived connections or subsystems with distinct activate/deactivate phases.
- Infrastructure needing controlled shutdown so the application closes safely.

`SmartLifecycle` is usually unnecessary for:

- Stateless services simply exposing methods to controllers.
- Standard repositories, JPA entities, or DTOs.
- Objects needing only destruction cleanup with no long-lived start/stop activity.
- **One-off** tasks after startup, which fit `ApplicationRunner` or `CommandLineRunner` better.
- Tasks needing to begin only after Boot is fully ready, where `ApplicationReadyEvent` is the right milestone.

Many framework integrations already implement lifecycle for listener containers, web servers, or schedulers. Do not wrap them in an extra `SmartLifecycle` just "to be sure it has a lifecycle"; first check whether the component already has its own start/stop mechanism and phase configuration.

## 17. Principles to Remember

1. **Distinguish bean creation from component start.** Constructors/`@PostConstruct` handle object initialization; `Lifecycle.start()` activates runtime work.
2. **Use `SmartLifecycle` when auto-start and phases are needed.** Plain `Lifecycle` does not auto-start on refresh by default.
3. **Lower phases start earlier, stop later.** Higher phases start later, stop earlier.
4. **Dependencies outrank phase numbers.** Express real relationships with constructor injection and `@DependsOn` where appropriate.
5. **Do not use `@Order` to coordinate start/stop.** That is a different ordering mechanism.
6. **Async stopping must invoke the callback.** Call `callback.run()` after stopping completes; do not report completion while tasks are still running.
7. **Set appropriate timeouts.** `spring.lifecycle.timeout-per-shutdown-phase` bounds wait time per phase; it does not replace proper stop logic.
8. **Coordinate with environment shutdown.** Graceful web shutdown, broker acknowledgments, and SIGTERM/orchestration limits must be considered alongside lifecycle.
9. **Test with a real context.** Start/stop order, auto-start flags, callbacks, and error scenarios should be verified through the lifecycle processor.
10. **Keep behavior idempotent, observable, and bounded.** Startup and shutdown are failure-prone phases; unclear states make applications hard to operate.

`Lifecycle` provides the minimal `start()`, `stop()`, and `isRunning()` contract. `SmartLifecycle` adds auto-start, phases, and asynchronous stop completion signaling. Spring coordinates components in **ascending phase order on start and descending phase order on stop**, while the dependency graph still ensures dependent components are handled properly. Understanding this distinction helps organize consumers, workers, and infrastructure in Spring Boot for orderly startup and safe shutdown.
