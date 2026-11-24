# SmartLifecycle, autoStartup, and Phase Ordering in Spring Framework

## 1. The problem: multiple components must start and stop in order

The Spring IoC Container can manage beans serving only regular computation such as `PricingService` and `OrderRepository`, alongside actively operating beans such as consumers, schedulers, listeners, message receivers, or components maintaining connections. An actively operating bean usually must **start** after its required dependencies are ready, and must **stop** before those dependencies are stopped.

Example of a pipeline:
- `ConnectionManager` must be turned on first to open connection availability.
- `MessageConsumer` starts receiving messages only when connection infrastructure is ready.
- On shutdown, the consumer stops receiving messages and finishes in-flight items, and only then does the connection manager close.

Using only a constructor or `@PostConstruct` to spawn threads and start the consumer easily causes ordering bugs: they run during the creation of **each individual bean**, when other components may not yet have completed their lifecycle. `SmartLifecycle` provides a contract for Spring to manage start/stop operations at the ApplicationContext level with **autoStartup**, **phase**, and **asynchronous stop callbacks**.

### Core concepts

| Concept | Meaning |
| --- | --- |
| `Lifecycle` | Basic interface with `start()`, `stop()`, `isRunning()` |
| `SmartLifecycle` | Extends `Lifecycle` and `Phased`, adding `isAutoStartup()` and `stop(Runnable)` |
| `isAutoStartup()` | Whether Spring should automatically start the bean on context refresh |
| `getPhase()` | Integer value determining group and start/stop ordering |
| `LifecycleProcessor` | Infrastructure coordinating bean lifecycles |
| `DefaultLifecycleProcessor` | Spring's default implementation, supporting phases, dependency ordering, and stop timeouts |
| `ContextRefreshedEvent` | Event published after context refresh finishes; typically after auto-starting lifecycle beans |
| `ContextStartedEvent` / `ContextStoppedEvent` | Events tied to `context.start()` / `context.stop()` commands |
| `ContextClosedEvent` | Event when context closes; does not imply calling `stop()` again on already-stopped beans |

**Boundary:** `SmartLifecycle` manages lifecycles within **one Spring ApplicationContext**; it does not synchronize order across multiple JVMs/pods, does not automatically guarantee external dependencies are healthy, and does not replace transactions or concurrency control.

## 2. SmartLifecycle contract in Spring

The fully qualified name is `org.springframework.context.SmartLifecycle`. It extends `Lifecycle` and `Phased`:

```java
// Simplified API signatures for explanation; this is not a file redefining Spring.
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}

public interface Phased {
    int getPhase();
}

public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
}
```

The snippet above describes the interfaces; modern Spring has **default methods** for some methods in `SmartLifecycle`. Do not redeclare these interfaces in your application; import the official interfaces. A class implementing `SmartLifecycle` should clearly honor:

- `start()`: start the service, switching `isRunning()` to `true` when genuinely ready per the component's contract. Should be idempotent: calling it again while already running must not spawn duplicate threads/consumers.
- `stop()`: stop synchronously when called directly by a caller. If already stopped, the operation should produce no side effects.
- `isRunning()`: return a reliable current state. Do not keep returning `true` after a worker dies or the component has stopped.
- `isAutoStartup()`: defaults to `true` in Spring 6.2; can be overridden to `false` if waiting for an explicit start signal is desired.
- `getPhase()`: defaults to `SmartLifecycle.DEFAULT_PHASE` (equivalent to `Integer.MAX_VALUE` in Spring 6.2); can be overridden to an appropriate integer.
- `stop(Runnable callback)`: used by `LifecycleProcessor` to coordinate shutdown and enable async stopping. **Must invoke `callback.run()` after the component actually stops**; for synchronous stops, it can be called right after `stop()` finishes.

`SmartLifecycle` allows managing **a long-lived component**, such as a listener container or message consumer. It is not a good place to execute a business job that "runs exactly once system-wide" or a method used solely to validate properties.

### Why is stop(Runnable) necessary?

If a consumer needs to wait for in-flight messages to finish processing, a synchronous stop could block Spring's thread for a long time. Spring lets `stop(Runnable)` begin the process of ceasing new work, then invoke the callback once resources are released. `DefaultLifecycleProcessor` uses the callback to know a phase has completed and can transition to the next phase in shutdown order.

```text
Spring LifecycleProcessor
       |
       +-- stop(callback) on consumer phase 100
                    |
                    +-- mark to stop receiving new messages
                    +-- wait for in-flight messages to finish
                    +-- close subscription
                    +-- update running=false
                    +-- callback.run()  <-- Spring knows stop finished
       |
       +-- after phase 100 finishes, stop lower phases
```

**Do not invoke the callback too early** while the component still holds connections/workers, causing later phases to stop prematurely. **Do not forget to invoke the callback** when stopping finishes, because Spring will keep waiting until the phase timeout. Invoke the callback exactly once per `stop(Runnable)` request.

## 3. When does autoStartup actually run?

In a typical `ApplicationContext.refresh()`, Spring creates regular singletons in `finishBeanFactoryInitialization()`, and then in `finishRefresh()` invokes `LifecycleProcessor.onRefresh()` to auto-start eligible `SmartLifecycle` beans. Afterward, Spring publishes `ContextRefreshedEvent`.

```text
context.refresh()
     |
     +-- BeanFactoryPostProcessors
     +-- BeanPostProcessors
     +-- create regular singletons, inject dependencies
     +-- @PostConstruct / InitializingBean / initMethod
     +-- SmartInitializingSingleton.afterSingletonsInstantiated()
     |
     +-- LifecycleProcessor.onRefresh()
     |       +-- auto-start SmartLifecycle beans if isAutoStartup()==true
     |       +-- respect phase and depends-on
     |
     +-- publish ContextRefreshedEvent
     +-- refresh() returns
```

This sequence explains why auto-starting in `SmartLifecycle`'s `start()` is usually better than opening consumers inside a constructor or `@PostConstruct`. In `start()`, regular singletons have already been created and their initialization is complete. Even so, do not infer that all lazy/prototype beans have been created, all databases are reachable, or a newly launched async job is already ready by application criteria.

### isAutoStartup() == true

This is the default value of `SmartLifecycle`. When context refresh succeeds and the lifecycle processor processes beans, Spring calls `start()` for beans not yet running. There is no need to manually call `context.start()` to trigger auto-start components.

### isAutoStartup() == false

The bean is not automatically chosen by Spring to auto-start solely on refresh. It can be turned on later via `context.start()`, or by calling `start()` on the bean itself when designed appropriately. **Important exception:** a bean that is a dependency of an auto-start lifecycle component may still be started to satisfy a `depends-on` relationship; hence the `false` flag is not an absolute barrier across every dependency graph.

`context.start()` actively requests starting **all lifecycle beans that need starting**, including `SmartLifecycle` with `isAutoStartup()==false` and plain `Lifecycle`. Already-running beans should not be started redundantly. `context.stop()` requests stopping running lifecycle beans. Do not confuse `start()/stop()` with `refresh()/close()`: the first two do not recreate bean definitions or re-initialize the ApplicationContext.

| Action | Bean `SmartLifecycle(true)` | Bean `SmartLifecycle(false)` | Bean implementing only `Lifecycle` |
| --- | --- | --- | --- |
| On context refresh | Auto-starts (unless blocked by dependency/error) | Does not auto-start by default | Does not auto-start |
| `context.start()` | Starts if not running | Starts if not running | Starts if not running |
| `context.stop()` | Stops if running | Stops if running | Stops if running |
| `context.close()` | Stops during close if still running; destroys singleton | Same if running; destroys | Same |

Note on `@Lazy`: Spring needs to discover lifecycle beans for auto-startup, so a bean implementing `SmartLifecycle` may be created right during the startup phase even if its bean definition declares lazy. Spring documentation states `@Lazy` typically has **very limited effect** on `SmartLifecycle`. If a truly lazy-on-demand resource is required, actively design an appropriate BeanFactory/loader and lifecycle rather than relying solely on `@Lazy`.

## 4. getPhase() rule: ascending on start, descending on stop

`getPhase()` returns an `int`. For `SmartLifecycle` beans without a `depends-on` relationship forcing special ordering:

- **Startup:** **lower phase runs before** higher phase.
- **Shutdown:** **higher phase stops before** lower phase.
- Two components in the **same phase** have no guaranteed order by contract; do not assume alphabetical order or `@Bean` order.
- Phases can be negative, 0, or positive. Consecutive integers are not required.

```text
START (low -> high):
    phase -100: connection
         |
    phase   0: base service
         |
    phase 100: message consumer
         |
    phase 200: serving endpoint

STOP (high -> low):
    phase 200: serving endpoint
         |
    phase 100: message consumer
         |
    phase   0: base service
         |
    phase -100: connection
```

| Bean | Phase | Start order | Stop order |
| --- | ---: | ---: | ---: |
| ConnectionManager | -100 | 1 | 4 |
| BaseLifecycleService | 0 | 2 | 3 |
| MessageConsumer | 100 | 3 | 2 |
| IngressEndpoint | 200 | 4 | 1 |

The table assumes all beans are started and no `depends-on` relationship reverses the order. Depending on application infrastructure, beans may not need many phases; phases should only be separated when real lifecycle dependencies exist.

### Important default phases

- Regular `Lifecycle` (not implementing `SmartLifecycle`) is treated by the lifecycle processor as having **phase 0**.
- `SmartLifecycle` in Spring 6.2 has `DEFAULT_PHASE = Integer.MAX_VALUE`. Thus if `getPhase()` is not overridden, a default SmartLifecycle component typically starts later than a phase-0 `Lifecycle` and stops earlier.
- Some Spring infrastructure beans have their own default phases, such as certain executors/schedulers at `Integer.MAX_VALUE / 2`. **Do not assume all infrastructure uses phase 0 or MAX_VALUE.**
- In Spring Boot/Web, web servers, messaging containers, schedulers, and task executors can have their own lifecycles/phases. When setting custom phases, check the Javadoc and actual dependency order of the version you deploy.

Do not use `@Order` as a replacement for `getPhase()` to coordinate `SmartLifecycle`. `@Order` can control collection injection order or sorting in specific facilities, whereas the lifecycle processor manages phases and `depends-on` according to its own contract.

## 5. depends-on relationships take precedence over phase

Spring allows declaring explicit dependencies, such as `@DependsOn("connectionManager")` or `@Bean` with `@DependsOn`. When two lifecycle beans have a dependency relationship, Spring enforces:

- Bean A **depends on** bean B → B must be **started before** A.
- When stopping → A must be **stopped before** B.

This holds even if their phase values suggest the opposite order. For example, A has phase -100 but depends-on B with phase 100: B still needs to run before A to satisfy the dependency.

```java
@Configuration(proxyBeanMethods = false)
class PipelineConfig {
    @Bean("connectionManager")
    SmartLifecycle connectionManager() {
        return new ConnectionManager();
    }

    @Bean("messageConsumer")
    @DependsOn("connectionManager")
    SmartLifecycle messageConsumer() {
        return new MessageConsumer();
    }
}
```

This is illustrative configuration code, **not independently runnable** because `ConnectionManager` and `MessageConsumer` are undefined and Spring imports are omitted. The key takeaway is the meaning of `@DependsOn`, not phase values in classes not shown here.

Distinctions:
- Constructor dependencies like `MessageConsumer(ConnectionManager manager)` ensure the **manager instance is created before** the consumer is created.
- `@DependsOn` expresses a dependency to the container and affects **lifecycle ordering**, not just creation order.
- `getPhase()` expresses ordering relationships across **groups** of components, very useful when there is no direct dependency or multiple components of the same kind must start first.
- If A must wait for B not merely for "`start` was called" but for **actually accepting healthy connections**, design an explicit readiness handshake; phase ordering alone does not prove an external service is healthy.

## 6. Complete Spring Core example (Java 17+): autoStartup and phase

This example runs with **Java 17+, Maven 3.9+, and Spring Framework 6.2.19**, without Spring Boot, servlets, or a DB. Three beans implement `SmartLifecycle` with phases -100, 100, and 200. The first two auto-start on refresh; the third has `isAutoStartup() == false` and starts only when code calls `context.start()`. All stop in reverse phase order.

### Directory structure

```text
smart-lifecycle-demo/
├── pom.xml
└── src/main/java/edu/example/lifecycle/
    ├── AppConfig.java
    ├── PhaseComponent.java
    ├── ContextEvents.java
    └── Main.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>smart-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
                    <mainClass>edu.example.lifecycle.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/lifecycle/PhaseComponent.java**

```java
package edu.example.lifecycle;

import org.springframework.context.SmartLifecycle;

public final class PhaseComponent implements SmartLifecycle {
    private final String name;
    private final int phase;
    private final boolean autoStartup;
    private volatile boolean running;

    public PhaseComponent(String name, int phase, boolean autoStartup) {
        this.name = name;
        this.phase = phase;
        this.autoStartup = autoStartup;
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public boolean isAutoStartup() {
        return autoStartup;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return; // Prevent duplicate start.
        }
        // Example only toggles flag. Production must start real resources.
        running = true;
        System.out.println("start " + name + " phase=" + phase);
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        // Production must stop resources before updating running.
        running = false;
        System.out.println("stop " + name + " phase=" + phase);
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop(); // Synchronous stop in this example.
        } finally {
            callback.run(); // Signal completion to LifecycleProcessor.
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

The example uses `volatile` to ensure threads reading `running` see updates; `synchronized` prevents duplicate start/stop calls in this minimal class. It does not represent how to coordinate a complex async consumer. In production, set `running=true` only after resources **actually start**, and report stop completion only after draining/closing finishes.

**src/main/java/edu/example/lifecycle/AppConfig.java**

```java
package edu.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean("infrastructure")
    public PhaseComponent infrastructure() {
        return new PhaseComponent("infrastructure", -100, true);
    }

    @Bean("worker")
    public PhaseComponent worker() {
        return new PhaseComponent("worker", 100, true);
    }

    @Bean("manual")
    public PhaseComponent manual() {
        return new PhaseComponent("manual", 200, false);
    }

    @Bean
    public ContextEvents contextEvents() {
        return new ContextEvents();
    }
}
```

**src/main/java/edu/example/lifecycle/ContextEvents.java**

```java
package edu.example.lifecycle;

import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ApplicationContextEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;

public final class ContextEvents
        implements ApplicationListener<ApplicationContextEvent> {

    @Override
    public void onApplicationEvent(ApplicationContextEvent event) {
        if (event instanceof ContextRefreshedEvent) {
            System.out.println("event: refreshed");
        } else if (event instanceof ContextStartedEvent) {
            System.out.println("event: started");
        } else if (event instanceof ContextStoppedEvent) {
            System.out.println("event: stopped");
        } else if (event instanceof ContextClosedEvent) {
            System.out.println("event: closed");
        }
    }
}
```

**src/main/java/edu/example/lifecycle/Main.java**

```java
package edu.example.lifecycle;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class Main {
    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        context.register(AppConfig.class);

        try {
            context.refresh();

            PhaseComponent infra =
                    context.getBean("infrastructure", PhaseComponent.class);
            PhaseComponent worker =
                    context.getBean("worker", PhaseComponent.class);
            PhaseComponent manual =
                    context.getBean("manual", PhaseComponent.class);

            System.out.println("after refresh: infra=" + infra.isRunning()
                    + ", worker=" + worker.isRunning()
                    + ", manual=" + manual.isRunning());

            context.start();
            System.out.println("after start: manual=" + manual.isRunning());

            context.stop();
            System.out.println("after stop: infra=" + infra.isRunning()
                    + ", worker=" + worker.isRunning()
                    + ", manual=" + manual.isRunning());
        } finally {
            context.close();
        }

        System.out.println("after close: active=" + context.isActive());
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Output from the program's `System.out.println`:**

```text
start infrastructure phase=-100
start worker phase=100
event: refreshed
after refresh: infra=true, worker=true, manual=false
start manual phase=200
event: started
after start: manual=true
stop manual phase=200
stop worker phase=100
stop infrastructure phase=-100
event: stopped
after stop: infra=false, worker=false, manual=false
event: closed
after close: active=false
```

Logs from Maven or logging frameworks may differ by environment; the lines above are printed by the program itself. The result is deterministic because the three phases differ, there is no `depends-on`, and no extra custom lifecycle component is created. In `finishRefresh()`, the container created the singletons and invoked auto-start for infrastructure (-100) and worker (100); manual (200) has `autoStartup=false`, so it has not started yet. The refresh event appears **after** auto-start finishes.

`context.start()` starts manual, while infrastructure/worker are already running so `start()` is not run again. `context.stop()` invokes shutdown in phase order **200 → 100 → -100**, and the example `stop(Runnable)` calls the callback as soon as synchronous stop finishes. After all three have stopped, `context.close()` publishes `ContextClosedEvent`; there is no need to print stop again. `isActive()` is `false` after close.

**Verification:** Replace `context.start()` with a no-op and manual remains `false`; it will not be stopped if it was never running. Try changing worker's phase to -200: worker will start before infrastructure, demonstrating why phase settings must match real dependencies. Do not force a production consumer to start before connection infrastructure just to "test."

## 7. stop(Runnable): stopping asynchronously per contract

The example above stops synchronously, so `stop(Runnable)` can call `stop()` and then `callback.run()`. For a subscriber needing to drain a message queue, an alternative is stopping asynchronously and invoking the callback **after actually finishing**:

```java
@Override
public void stop(Runnable callback) {
    // PSEUDOCODE: taskExecutor and consumer are real dependencies
    consumer.stopAcceptingNewMessages();

    taskExecutor.execute(() -> {
        try {
            consumer.awaitInFlightTasks();
            consumer.close();
            running = false;
        } finally {
            callback.run();
        }
    });
}
```

This is **illustrative API pseudocode**, not a runnable standalone class; `consumer`, `taskExecutor`, and `running` must be defined, and `awaitInFlightTasks()` is not a default Spring API. The point: the callback must be invoked when the actual stop completes (including when errors are handled per the component's policy), and must not be invoked before async tasks finish. In production code, also handle cases where `taskExecutor.execute` rejects tasks or shutdown is cancelled so the callback is never dropped and errors are reported properly.

A sturdier approach for async shutdown must establish:
1. Immediately upon receiving stop, **cease accepting new work**.
2. Hold a "stopping" state so duplicate start requests do not race.
3. Give in-flight work a chance to finish within a policy deadline.
4. Close connections/subscriptions in a safe order.
5. Update `isRunning()` to `false` after releasing resources.
6. Invoke the callback exactly once as soon as complete, including cleaned-up error paths.

`DefaultLifecycleProcessor` waits for a phase's callbacks up to a timeout. If a component fails to invoke the callback, Spring may log a warning and proceed according to the processor's policy after timeout; do not treat the "context closed" event as a guarantee that all individual resources were cleaned up. When running multiple beans in the same phase, callbacks support parallel stopping **in coordination**, though exact execution timing depends on the implementation and stop work.

## 8. Phase timeouts and LifecycleProcessor configuration

`DefaultLifecycleProcessor` is the default processor for common contexts. Spring Framework **6.2** has a default timeout of **10 seconds per shutdown phase**, while documentation of other versions may use different values (for instance, Spring Framework 7.x notes 30 seconds). Therefore always check the Javadoc for the exact **version** when controlling stop duration.

You can register a bean named `lifecycleProcessor` to override the default processor, or use the config extension for the appropriate version. Example configuring a processor bean with a timeout:

```java
package edu.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.DefaultLifecycleProcessor;

@Configuration(proxyBeanMethods = false)
public class LifecycleTimeoutConfig {
    @Bean(name = "lifecycleProcessor")
    public DefaultLifecycleProcessor lifecycleProcessor() {
        DefaultLifecycleProcessor processor =
                new DefaultLifecycleProcessor();
        processor.setTimeoutPerShutdownPhase(20_000L);
        return processor;
    }
}
```

This is an **optional configuration file**, not part of the runnable project in section 6 unless you actively register `LifecycleTimeoutConfig`; the `setTimeoutPerShutdownPhase(long)` method exists in Spring Framework 6.2. Some versions also have an API to set per-phase timeouts, such as `setTimeoutForShutdownPhase(int, long)` in 6.2. Specify timeouts based on application deadline requirements and deployment environments, not solely on default values.

If container deployment sends SIGTERM with a termination grace period, actual shutdown duration must fit within the total time for stopping phases, callbacks, and other components. Configuring a timeout inside Spring **does not extend** the deadline before the orchestration layer kills the process.

Do not modify the `lifecycleProcessor` of a running application just to change a timeout without understanding Spring's infrastructure registration order; the processor config must be available at the right time in the context.

## 9. Differences between start/stop and init/destroy

A common mistake is using `@PostConstruct` to launch a thread and `@PreDestroy` to stop it, assuming phase ordering is achieved. In reality:

| Mechanism | When triggered | Suitable work |
| --- | --- | --- |
| Constructor | When bean is created | Establish invariants and required dependencies |
| `@PostConstruct` | After injection of that bean | Validate config, build immutable indexes, prepare lightweight resources |
| `SmartInitializingSingleton` | After eager regular singleton pre-instantiation | Aggregate validation/registry checks of created beans |
| `SmartLifecycle.start()` | During auto-start on refresh or explicit start | Start long-lived components: consumers, listeners, polling |
| `SmartLifecycle.stop(Runnable)` | Context stop/close via lifecycle processor | Graceful shutdown with completion callback |
| `@PreDestroy` | When destroying bean per scope/container | End-of-lifecycle resource cleanup |
| `ContextRefreshedEvent` | When context refresh succeeds | Receive context-level events |
| `ApplicationRunner` (Spring Boot) | In Boot startup workflow after context refresh | Application-level startup logic |

A component can simultaneously have `@PostConstruct` and `SmartLifecycle`, though responsibilities should remain cleanly separated:

```text
constructor:
    receive dependencies
@PostConstruct:
    validate and prepare config (do not start consumer yet)
SmartLifecycle.start():
    connect/subscribe/start processing
SmartLifecycle.stop(callback):
    stop accepting work, drain, close, callback
@PreDestroy:
    clean up any remaining state/resources
```

You can design `stop()` to be idempotent and have `@PreDestroy` run fallback cleanup; avoid closing resources twice and causing errors. Do not use `@PreDestroy` as the sole means to stop consumers when phase ordering and graceful draining are needed.

### Why is lifecycle phase important on shutdown?

When stopping a phase-100 consumer before a phase-(-100) connection, the consumer gets a chance to finish in-flight messages while the connection is still alive. If phases are reversed, the connection drops first and the consumer can fail mid-shutdown. Phases are a way to declare **timing relationships**; if backlog data remains, the consumer code itself must still ensure ACKs, retries, idempotency, and system invariants.

## 10. Special cases to understand

### 10.1. Same phase does not guarantee order

If two beans both have `getPhase() == 50`, Spring does not guarantee A starts before B in the API contract, even if on your dev machine A always runs first. If a real dependency exists, use explicit `depends-on` or separate phases.

### 10.2. @DependsOn alters phase order

This relationship has **higher priority** than phase numbers. Do not create a cycle `A depends-on B` and `B depends-on A`. If A's phase is lower than B's yet A needs B to start, consider adjusting the phase to express the logic accurately, even though the framework may prioritize depends-on.

### 10.3. @Lazy on SmartLifecycle

`@Lazy` usually does not prevent the lifecycle processor from instantiating a `SmartLifecycle` bean when evaluating auto-start. Do not use the lazy flag as a substitute for `isAutoStartup()`. If an auto-starting bean has heavy dependencies, consider designing explicit phased initialization rather than expecting the bean not to be created.

### 10.4. A SmartLifecycle bean running with multiple ApplicationContexts

Each context has its own lifecycle. Parent/child contexts can start and close independently; do not assume a `SmartLifecycle` in a child coordinates the root's lifecycle or vice versa. Do not attach genuinely global external singletons to multiple contexts and have each context stop the shared resource.

### 10.5. Auto-start does not mean the server is "ready"

`LifecycleProcessor.onRefresh()` typically runs before `ContextRefreshedEvent`. It is a start request milestone per contract; it does not automatically ping databases/Kafka or verify a consumer has attached its subscription if `start()` merely starts an async task and returns immediately. If real readiness is needed, expose the component's health/readiness signal, await handshakes with reasonable timeouts, and update health indicators.

### 10.6. Thread safety of running state

`isRunning()` can be called by a different thread than `start()/stop()`. If real concurrency exists, use `volatile`/`AtomicBoolean`, locks, or an explicit state machine. A `volatile boolean running` flag solves visibility for the flag, yet **does not** make the entire start/stop of sockets/threads atomic; multi-step sequences must be guarded.

### 10.7. Spring Boot and infrastructure phases

Spring Boot/web servers, message listener containers, schedulers, and executors can implement `SmartLifecycle` with specific phases. Interfering with custom bean phases can cause workers to accept traffic before dependencies start, or stop after required executors have shut down. Check documentation for the exact version of each component and set ordering reflecting real dependencies.

### 10.8. Restarting via context.start() after context.stop()

With an **unclosed** context, `context.stop()` followed by `context.start()` can re-drive `Lifecycle` beans if their `start/stop` logic truly supports restarting. Spring does not recreate beans on the second start. If component code closed a resource that **cannot be reopened**, `start()` must actively create a new resource or the contract must clearly state it is non-restartable.

### 10.9. Beans that were never started

If `isAutoStartup=false` and nobody calls `start()`, Spring does not need to invoke the stop callback for a bean that is not running under normal lifecycle management. However, that singleton bean can still receive destruction callbacks when the context closes (if any). Do not place critical cleanup **exclusively** in the stop callback assuming the bean was always started.

## 11. How to verify actual lifecycle order

An integration test can hold a thread-safe event list, register three lifecycle components with different phases, and run `context.refresh()`, `context.start()`, `context.stop()`. Verify:

- After refresh, `auto-start=true` beans are running; `false` beans are not running yet (unless forced by a dependency).
- Start markers of lower phases appear before higher phases.
- After explicit `start()`, the `false` bean transitions to running.
- On stop, higher phases finish **before** lower phases; for async stop, use a completion callback/latch instead of merely recording that `stop` was called.
- After close, context is inactive and resources are released, with no stray threads still running.
- Set reasonable timeouts so tests fail clearly if a callback is forgotten.

Do not use `Thread.sleep(100)` to guess that shutdown finished. Use synchronization primitives such as `CountDownLatch`/`Future` and a concrete deadline. When testing async stop, ensure the callback is invoked only after actual state transitions to stopped, because Spring may advance to the next phase as soon as the callback runs.

For production observability, log fields `component`, `phase`, `action=start|stop`, `elapsedMs`, and `outcome`; do not merely inspect statement order in source code. These logs help distinguish bean creation failures, slow starts, stop timeouts, or resources killed by the orchestration layer.

## 12. Common bugs and how to fix them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Consumer starts right at refresh without calling `context.start()` | `SmartLifecycle.isAutoStartup()` defaults to `true` | Override `isAutoStartup()` to `false` if explicit start is desired |
| `@Lazy` bean still created at startup | Lifecycle processor may initialize SmartLifecycle to auto-start | Do not use lazy as a start switch; design explicit lifecycle |
| Dependent resource not yet running when consumer starts | Phases reversed or missing dependency relationship | Lower phase for dependency; declare `depends-on` where appropriate |
| Connection stops before consumer | Shutdown phases misordered | Give consumer higher phase than connection so it stops first |
| Context close stalls until timeout | `stop(Runnable)` forgot callback or shutdown never finished | Invoke callback exactly once after completion, handling error paths too |
| Callback runs while tasks are still draining | Invoked callback immediately after scheduling async shutdown | Invoke inside completion handler after resources actually stop |
| Same phase runs in unstable order | API does not guarantee order within the same phase | Separate phases or declare dependencies |
| `@Order` does not control lifecycle | LifecycleProcessor uses phase/depends-on | Override `getPhase()` |
| Calling `start()` after closing context | Context has ended its lifecycle | Create a new context; manage start/stop before close |
| `isRunning()` stays false despite starting | State not updated or published properly | Synchronize state and reflect real resources |
| Calling `stop()` directly skips callback logic | Direct caller invoked different overload than lifecycle processor | Implement both `stop()` and `stop(Runnable)` consistently |
| Context refresh finishes yet external broker unavailable | `start` may return before handshake, or external system is down | Define separate readiness, retry/backoff/timeout |
| One bean runs multiple times across multiple pods | Each context has an independent lifecycle | Use distributed coordination if logic must run on only one instance |
| Shutdown lacks enough time to drain | Spring timeout or SIGTERM grace period too short | Configure multi-layer shutdown deadlines and stopping criteria |

## 13. Self-check and design exercises

1. A `SmartLifecycle` does not override `isAutoStartup()`. In a normal `ApplicationContext.refresh()`, is it started automatically or does it wait for `context.start()`?
2. Bean A has phase -20 and bean B has phase 30, with no explicit dependency. What is the start and stop order?
3. Why does setting `SmartLifecycle.DEFAULT_PHASE` to `Integer.MAX_VALUE` in Spring 6.2 affect phase-0 `Lifecycle` beans?
4. If both A and B have phase 100, does Spring guarantee A starts before B?
5. If A `depends-on` B, yet A has phase -100 and B has phase 100, how should startup order be understood?
6. Can a bean with `isAutoStartup()==false` be started when `context.start()` is called?
7. If a `@Lazy` bean implements `SmartLifecycle`, can `@Lazy` guarantee the bean is not created during startup?
8. `stop(Runnable)` is called while draining 10 messages. Can the callback be invoked right when draining starts?
9. A phase-200 consumer uses a phase-(-100) ConnectionManager. On shutdown, which bean stops first?
10. How does `@PostConstruct` differ from `SmartLifecycle.start()` in lifecycle timing and purpose?
11. How do `context.stop()` and `context.close()` differ?
12. How can you verify async stop actually completes before Spring proceeds to stop lower phases?
13. If a Spring Boot application has three replicas, how many times in total does an auto-start `SmartLifecycle` bean run?
14. When might Spring Framework 6.2's 10-second per-phase timeout be insufficient?
15. If a listener container's `start()` only enqueues an async task and returns, can you conclude the broker is ready?

**Suggested answers:** (1) Auto-starts because default is true. (2) Start A→B; stop B→A. (3) Default SmartLifecycle usually starts after Lifecycle 0 and stops before Lifecycle 0. (4) No. (5) Dependency B runs before A; depends-on takes precedence. (6) Yes. (7) Not guaranteed; lazy has limited effect. (8) No; invoke callback after draining/closing completes. (9) Consumer 200 stops before manager -100. (10) PostConstruct belongs to a single bean's init; SmartLifecycle coordinates component start/stop after bootstrap. (11) Stop does not destroy context; close terminates context and destroys singletons. (12) Use callback/latch with real resource invariants, checking that the next phase only proceeds after completion. (13) Typically three times, once per context/pod, unless configured otherwise. (14) When there are long tasks, many consumers, or slow transport draining; adjust timeout and grace period. (15) No; real readiness and external system checks are required.

## Official documentation

- Spring Framework 6.2 — `SmartLifecycle` Javadoc (default auto-start/phase, depends-on, stop callback): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.2 — `DefaultLifecycleProcessor` Javadoc (phase ordering, shutdown timeout): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework — Customizing the Nature of a Bean (Lifecycle and SmartLifecycle): https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — `Lifecycle` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/Lifecycle.html
- Spring Framework — `ConfigurableApplicationContext` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Framework — `ContextRefreshedEvent`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html
