# Managing Lifecycle, SmartLifecycle, and Closable Resources

> **Chapter:** Application Lifecycle  
> **Module:** SPRING_CLOUD_CORE

A Spring Cloud application does not merely instantiate controllers and services and wait for requests. It must also start consumers, schedulers, and connections to dependent systems, stop accepting new work on shutdown, and release resources in the right order. If the stopping order is wrong, a consumer might keep sending messages while connections are already closed; if the application exits too early, in-flight requests or messages could be lost.

Spring Framework provides the **Lifecycle**, **SmartLifecycle**, and **LifecycleProcessor** abstractions to coordinate components that can start and stop along the ApplicationContext lifecycle. Bean destruction callbacks such as **@PreDestroy**, **DisposableBean**, and destroy methods add the final resource-cleanup step. This lesson explains how to coordinate these mechanisms for controlled startup and shutdown in **SPRING_CLOUD_CORE** applications.

## 1. Two Lifecycle Layers to Distinguish

A Spring application's lifecycle can be viewed across two layers:

- **Bean lifecycle:** instantiating beans, injecting dependencies, invoking initialization callbacks, using the beans, and invoking destruction callbacks when the container closes.
- **Application lifecycle:** refreshing the ApplicationContext, starting background components, accepting work, stopping components in order, and closing resources.

A single bean can participate in both layers. For example, a message consumer is created by Spring as a bean, started by `LifecycleProcessor` when the context becomes ready, stopped when the context closes, and finally has its resources released.

~~~mermaid
flowchart TB
    A["SpringApplication.run()"] --> B["Create and refresh ApplicationContext"]
    B --> C["Create beans and inject dependencies"]
    C --> D["Initialization callbacks"]
    D --> E["LifecycleProcessor.onRefresh()"]
    E --> F["Lifecycle beans start in ascending phase order"]
    F --> G["Application serves requests / processes messages"]
    G --> H["SIGTERM or context.close()"]
    H --> I["ContextClosedEvent"]
    I --> J["LifecycleProcessor.onClose()"]
    J --> K["Lifecycle beans stop in descending phase order"]
    K --> L["Bean destruction callbacks"]
    L --> M["Close ApplicationContext"]
~~~

The diagram shows the overall order when closing the context. Integration details of the server, container, and framework version may introduce additional steps, but the core principle is stopping active work before releasing the dependencies that work requires.

## 2. Lifecycle: The Basic Start and Stop Contract

`org.springframework.context.Lifecycle` is a simple interface representing a component that can be started and stopped:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Meaning:

- `start()` begins the component's activity.
- `stop()` instructs the component to cease activity.
- `isRunning()` indicates whether the component is currently running.

Example of a simple scheduler:

~~~java
import org.springframework.context.Lifecycle;
import org.springframework.stereotype.Component;

@Component
public class ReportSchedulerLifecycle implements Lifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        if (running) {
            return;
        }

        // Start scheduler or register periodic jobs.
        running = true;
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }

        // Stop accepting and scheduling new jobs.
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
~~~

`Lifecycle` fits when a component only needs basic start/stop behavior. Spring provides `LifecycleProcessor` to manage beans implementing `Lifecycle` throughout the ApplicationContext lifecycle. Typically, `LifecycleProcessor` starts components during context refresh and stops them when the context closes.

For components needing ordering control or asynchronous shutdown completion, `SmartLifecycle` extends the contract.

## 3. SmartLifecycle Adds Phases and Shutdown Callbacks

`SmartLifecycle` extends `Lifecycle` and `Phased`. It adds:

- `isAutoStartup()`: indicates whether the bean starts automatically upon context refresh.
- `getPhase()`: determines the phase for ordering start/stop execution.
- `stop(Runnable callback)`: signals `LifecycleProcessor` when asynchronous stopping has finished.

A `SmartLifecycle` bean normally starts automatically once ApplicationContext refresh finishes if `isAutoStartup()` returns true. The default return value of this method is true. The default phase of `SmartLifecycle` is `Integer.MAX_VALUE`; declare an explicit phase whenever ordering between components matters.

### 3.1. Phases Determine Start and Stop Order

Spring orders lifecycle components by phase:

- On **start**, lower phases start first.
- On **stop**, higher phases stop first.

For example, a message consumer needs the connection manager active before it starts. The consumer must also stop before the connection manager closes:

| Component | Phase | Start order | Stop order |
| --- | ---: | ---: | ---: |
| Connection manager | 0 | First | Last |
| Message consumer | 100 | Second | Second |
| Background dispatcher | 200 | Last | First |

This rule ensures dependencies have appropriate lifetimes: foundational resources open first, components using them start later; during shutdown, components using resources stop first before foundational resources close.

Beans in the same phase should not rely on incidental ordering to satisfy dependencies. If a clear dependency exists, express it in Spring configuration or assign distinct phases.

A bean implementing only `Lifecycle` without providing a phase is handled at phase 0 by the default mechanism. `SmartLifecycle` has a default phase of `Integer.MAX_VALUE`, so it typically starts after plain `Lifecycle` beans and stops before them. If a different order is needed, override `getPhase()`.

### 3.2. Auto Startup

`isAutoStartup()` returns true if the bean should start automatically on context refresh. If it returns false, the bean is not started automatically by `SmartLifecycle`; the application needs a management component to invoke start when appropriate.

Example:

~~~java
@Override
public boolean isAutoStartup() {
    return false;
}
~~~

This can be used for a worker that should only run after the system completes a verification step or receives an administrative command. However, there must be an explicit startup procedure and safe handling of the unstarted state when the context closes.

## 4. stop(Runnable) and Asynchronous Shutdown

A crucial distinction of `SmartLifecycle` is the callback in `stop(Runnable)`. For a component with in-flight work, stopping can involve multiple steps:

1. Stop accepting new work.
2. Wait for in-flight work to finish or the drain timeout to expire.
3. Close the consumer or related resources.
4. Invoke the callback to report that stopping is complete.

If `stop` returns immediately while the component is still draining, `LifecycleProcessor` may misinterpret shutdown as complete and proceed to stop the next phase. Therefore, the callback must be invoked only after the stop process truly finishes.

### 4.1. Example of a Draining Message Consumer

Suppose a messaging library provides the following abstraction:

~~~java
import java.util.concurrent.CompletionStage;

public interface MessageConsumer {
    void start();
    void stopAccepting();
    CompletionStage<Void> drain();
    void close();
}
~~~

Bean managing the consumer:

~~~java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumerLifecycle implements SmartLifecycle {

    private final MessageConsumer consumer;
    private volatile boolean running;

    public OrderConsumerLifecycle(MessageConsumer consumer) {
        this.consumer = consumer;
    }

    @Override
    public void start() {
        if (running) {
            return;
        }

        consumer.start();
        running = true;
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }

        try {
            consumer.stopAccepting();
            consumer.drain().toCompletableFuture().join();
        } finally {
            try {
                consumer.close();
            } finally {
                running = false;
            }
        }
    }

    @Override
    public void stop(Runnable callback) {
        if (!running) {
            callback.run();
            return;
        }

        try {
            consumer.stopAccepting();
            consumer.drain().whenComplete((ignored, failure) -> {
                try {
                    if (failure != null) {
                        // Record drain error with an appropriate logger/metric.
                    }
                    consumer.close();
                } finally {
                    running = false;
                    callback.run();
                }
            });
        } catch (RuntimeException ex) {
            try {
                consumer.close();
            } finally {
                running = false;
                callback.run();
            }
            throw ex;
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
~~~

The example assumes `MessageConsumer` provides operations to stop intake, drain in-flight work, and close resources. In a real system, specify clearly what happens if draining fails, times out, or the callback fires while the consumer is already stopped.

Key principles when implementing the callback:

- Invoke the callback exactly once per stop request.
- Invoke the callback after the component has stopped intake and finished its committed stop steps.
- Ensure the callback is still invoked if cleanup throws an error; otherwise `LifecycleProcessor` may wait until timeout.
- Log drain/close failures so operations know whether shutdown completed cleanly or had to drop work.
- Make start/stop idempotent in case the framework or application invokes them multiple times.

Never invoke the callback immediately after scheduling the drain if actual work is still running. The callback is the synchronization signal between the component and `LifecycleProcessor`.

## 5. LifecycleProcessor Coordinates All Components

`LifecycleProcessor` is the abstraction managing lifecycle beans in the ApplicationContext. The default implementation is normally `DefaultLifecycleProcessor`.

Primary responsibilities:

- Start lifecycle components on context refresh.
- Order starts by phase.
- Stop lifecycle components when the context closes.
- Order stops in reverse phase order.
- For `SmartLifecycle`, wait for asynchronous stop callbacks within the phase timeout.

The processor configuration can be customized in special cases, though most applications should use the default implementation. Before writing a custom `LifecycleProcessor`, identify the specific requirement that standard phases, callbacks, and timeouts cannot meet.

### 5.1. Per-Phase Timeout

If a `SmartLifecycle` fails to invoke its callback, or draining hangs, shutdown cannot wait indefinitely. `DefaultLifecycleProcessor` enforces a timeout for stopping each phase. In Spring Boot, configure the wait duration via:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

This value applies per phase, not as a single total budget across the entire shutdown. If multiple phases must stop, total duration can exceed a single phase's timeout. Defaults and configuration APIs may vary by Spring Boot/Spring Framework version; consult the documentation for your release.

A timeout does not magically finish draining work. Once the timeout expires, the processor must proceed with shutdown per framework policy; components must enforce their own internal timeouts and handle unfinished work.

## 6. When to Use Lifecycle, SmartLifecycle, or Bean Destruction Callbacks?

Not every resource needs `SmartLifecycle`. Choose the mechanism based on the behavior the component requires.

| Need | Appropriate mechanism | Reason |
| --- | --- | --- |
| Component with simple start/stop | `Lifecycle` | Minimal contract |
| Needs auto-start, phases, and async stop | `SmartLifecycle` | Supports auto-startup, ordering, and callbacks |
| Only needs resource release on bean destruction | `@PreDestroy` or destroy method | No separate running/stopped model needed |
| Wants Spring to call interface-based destroy callback | `DisposableBean` | Explicit destruction contract |
| Needs to close resources after stopping work intake | `SmartLifecycle` combined with destruction callback | Separates graceful stop from final cleanup |

Examples:

- A message listener container typically has a start/stop lifecycle, making `Lifecycle` a good fit.
- A scheduler needing to stop scheduling and wait for running tasks may require `SmartLifecycle`.
- A file handle that only needs closing on bean destruction can use `@PreDestroy` or a destroy method.
- A shared HTTP client can be managed as a Spring bean with a close method; if it must close after consumers, configure phases/dependencies appropriately.

Many Spring libraries already provide lifecycle-managed beans out of the box. If using a message listener container, scheduler, or connection factory created by a starter, check its built-in shutdown mechanism before writing another `Lifecycle` wrapper.

## 7. Destruction Callbacks: @PreDestroy, DisposableBean, and Destroy Methods

After lifecycle components stop, Spring destroys singleton beans and invokes declared destruction callbacks.

### 7.1. @PreDestroy

`@PreDestroy` marks a method invoked when the bean is destroyed:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class LocalFileCache {

    private final FileCache cache;

    public LocalFileCache(FileCache cache) {
        this.cache = cache;
    }

    @PreDestroy
    public void close() {
        cache.close();
    }
}
~~~

In Spring Boot 3, the annotation belongs to the `jakarta.annotation` namespace. Boot 2 projects may use `javax.annotation` depending on version and dependencies. Do not mix the two namespaces.

`@PreDestroy` suits brief, synchronous cleanup. It provides no asynchronous callback to ask `LifecycleProcessor` to wait for a lengthy drain.

### 7.2. DisposableBean

A bean can implement `DisposableBean`:

~~~java
import org.springframework.beans.factory.DisposableBean;
import org.springframework.stereotype.Component;

@Component
public class TemporaryResourceHolder implements DisposableBean {

    private final TemporaryResource resource;

    public TemporaryResourceHolder(TemporaryResource resource) {
        this.resource = resource;
    }

    @Override
    public void destroy() {
        resource.close();
    }
}
~~~

Spring invokes `destroy()` when destroying the bean. This introduces a direct dependency on Spring APIs, so if you want domain classes or libraries decoupled from Spring, annotation callbacks or bean configuration are usually more flexible.

### 7.3. Destroy Method on @Bean

For beans declared via `@Bean`, you can specify a resource-closing method:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

Spring calls `close()` when destroying the bean. For many bean types, Spring can infer methods named `close` or `shutdown` under default destroy method rules. Declaring it explicitly makes intent clearer when multiple cleanup methods exist.

### 7.4. Avoid Cleaning Up the Same Resource Multiple Times

A bean can accidentally invoke the same close operation in `stop()`, `@PreDestroy`, and `DisposableBean.destroy()`. If multiple callbacks close the same socket or pool, double-close errors can occur or the first failure's diagnostics can be lost.

Assign one primary responsibility per stage:

- Lifecycle stop: cease work intake, drain, and stop the component.
- Destruction callback: release final underlying resources owned by the bean.

If close may be invoked via multiple paths due to library design, make close idempotent with explicit guard state.

## 8. Shutdown Order and Inter-Bean Dependencies

When closing the ApplicationContext, Spring publishes the context closed event and `LifecycleProcessor` stops lifecycle beans. After stopping lifecycle components, the container invokes bean destruction callbacks.

Phase ordering coordinates background components. Bean dependencies matter too: a bean using another bean's resource must stop before that resource closes.

Example:

~~~mermaid
flowchart TB
    A["Startup"] --> B["Phase 0: open connection manager"]
    B --> C["Phase 100: start message consumer"]
    C --> D["Phase 200: start dispatcher"]
    D --> E["Application running"]
    E --> F["Shutdown"]
    F --> G["Phase 200: stop dispatcher"]
    G --> H["Phase 100: stop consumer and drain"]
    H --> I["Phase 0: close connection manager"]
    I --> J["Destroy callbacks"]
~~~

In this example, the dispatcher depends on the consumer; the consumer depends on the connection manager. On start, infrastructure opens first before components using it run. On stop, the order reverses.

Do not pick phases as arbitrary numbers. Document actual dependencies and assign phases to reflect those relationships. For beans directly depending on one another, declare dependencies in Spring so the container knows the proper initialization and destruction order.

## 9. Graceful Shutdown in Spring Boot

A web application typically needs to stop accepting new requests and give in-flight requests time to complete. Spring Boot supports graceful shutdown for embedded web servers.

Configuration example:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

When the ApplicationContext begins closing, the embedded web server performs graceful shutdown according to its capabilities: stopping new requests and letting in-flight requests complete within the allowed period. Exact details can vary across Tomcat, Jetty, Reactor Netty, and Undertow as well as Boot versions.

### 9.1. Coordinating with the Deployment Platform

In Kubernetes or a container orchestration platform, a process typically receives `SIGTERM` before being forcibly terminated. The platform's termination grace period must give the application enough time to:

1. Stop receiving new traffic or update readiness according to the deployment strategy.
2. Stop listeners and consumers from accepting new work.
3. Drain in-flight requests and messages.
4. Close connections, pools, schedulers, and remaining resources.
5. Exit before the termination grace period expires.

Never configure Spring's timeout longer than the platform allows the process to remain alive. Leave headroom for JVM shutdown and final cleanup steps.

### 9.2. Graceful Shutdown Does Not Guarantee Every Task Completes

A request or message might exceed the timeout. The system must define:

- Can unfinished work be retried?
- Are messages acknowledged only after successful processing?
- Is there a visibility timeout or redelivery mechanism?
- Is work idempotent to prevent duplicate processing?
- If shutdown times out, is in-progress data checkpointed or returned to the queue?

Lifecycle coordinates shutdown timing; business correctness under interruption still requires dedicated retry, transaction, and idempotency mechanisms.

## 10. Testing Lifecycle and Destruction

Verify both start/stop ordering and destruction callbacks. A simple test can use `AnnotationConfigApplicationContext` to observe the lifecycle:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class ApplicationLifecycleTest {

    @Test
    void startsAndStopsLifecycleBeansByPhase() {
        List<String> events = new ArrayList<>();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {
            context.registerBean("connection", ConnectionLifecycle.class,
                    () -> new ConnectionLifecycle(events));
            context.registerBean("consumer", ConsumerLifecycle.class,
                    () -> new ConsumerLifecycle(events));

            context.refresh();

            assertThat(events).containsExactly(
                    "connection-start",
                    "consumer-start");

        }

        assertThat(events).containsExactly(
                "connection-start",
                "consumer-start",
                "consumer-stop",
                "connection-stop");
    }

    static class ConnectionLifecycle implements SmartLifecycle {
        private final List<String> events;
        private boolean running;

        ConnectionLifecycle(List<String> events) {
            this.events = events;
        }

        @Override
        public void start() {
            events.add("connection-start");
            running = true;
        }

        @Override
        public void stop() {
            events.add("connection-stop");
            running = false;
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public int getPhase() {
            return 0;
        }
    }

    static class ConsumerLifecycle implements SmartLifecycle {
        private final List<String> events;
        private boolean running;

        ConsumerLifecycle(List<String> events) {
            this.events = events;
        }

        @Override
        public void start() {
            events.add("consumer-start");
            running = true;
        }

        @Override
        public void stop() {
            events.add("consumer-stop");
            running = false;
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public int getPhase() {
            return 100;
        }
    }
}
~~~

The example uses phase 0 for connection and phase 100 for consumer. On start, connection starts first; on stop, consumer stops first. You can add tests for `stop(Runnable)` to verify the callback runs only after draining finishes.

### 10.1. Additional Scenarios to Test

| Scenario | What to verify |
| --- | --- |
| Context refresh | Auto-start beans start in the expected phase |
| Auto startup false | Bean does not auto-start and has an explicit start path |
| Repeated stop calls | Component handles already-stopped state safely |
| Asynchronous stop | Callback runs only after draining completes |
| Drain failure | Error is logged and callback is not forgotten |
| Phase timeout | Shutdown does not wait indefinitely |
| Destruction callback | Resource is closed exactly once |
| Dependency order | Consumer stops before the connection/pool it uses |
| SIGTERM | Server stops accepting new requests and in-flight requests drain within timeout |
| Forced shutdown | Incomplete messages/requests can be retried safely |

## 11. Common Pitfalls and How to Avoid Them

1. **Closing connections before stopping consumers:** assign phases so consumers stop before the dependencies they use.
2. **Forgetting to invoke the callback in stop(Runnable):** `LifecycleProcessor` waits until timeout; ensure the callback is called exactly once.
3. **Invoking the callback too early:** the component is still draining while the context proceeds to the next phase.
4. **Putting all beans in the same phase:** ordering does not reflect dependencies; separate phases according to start/stop relationships.
5. **Using @PreDestroy for asynchronous draining:** destruction callbacks do not offer a callback wait mechanism like `SmartLifecycle`.
6. **Cleaning up the same resource across multiple callbacks:** assign clear responsibilities and make close operations idempotent.
7. **Omitting timeout configuration:** shutdown may hang too long or get forcibly killed by the platform.
8. **Application timeout exceeding platform termination grace period:** the process lacks sufficient time to finish shutting down.
9. **Assuming graceful shutdown guarantees every message completes:** design retries, acks, transactions, and idempotency for interrupted work.
10. **Manually wrapping beans that already have built-in lifecycle:** check starter/framework support before writing redundant wrappers.

## 12. Lifecycle Design Checklist for a Spring Cloud Service

When adding a consumer, scheduler, or shared resource to a service, clarify:

1. Does the component need to auto-start on ApplicationContext refresh or require a separate start trigger?
2. Which resources does it depend on, and which components must it start after?
3. On shutdown, how should it stop accepting work, how long should it drain, and how should it handle errors?
4. Does it need `SmartLifecycle` phases or only simple `Lifecycle`?
5. Which resources close during `stop` and which are released in destruction callbacks?
6. Do per-phase timeouts and the deployment platform's total termination grace period align?
7. Do tests verify start/stop ordering, async callbacks, and resource closure?
8. Do metrics/logs report whether shutdown succeeded, timed out, or left unfinished work?

**Key takeaway:** `Lifecycle` provides basic start/stop; `SmartLifecycle` adds auto-startup, phases, and callbacks to coordinate asynchronous shutdown; `LifecycleProcessor` manages those components throughout the ApplicationContext lifecycle. After lifecycle components stop, `@PreDestroy`, `DisposableBean`, or destroy methods release remaining resources. Good design opens dependencies before consumers run, stops consumers before closing dependencies, and allocates enough time for graceful shutdown in **SPRING_CLOUD_CORE** deployment environments.
