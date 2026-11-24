# Reverse Shutdown Order and `depends-on` Dependencies in `SmartLifecycle`

## 1. Goal: safely stopping components with dependencies

A Spring Boot application often has multiple components running throughout the process lifecycle:

- A **transport** opens connections or receives messages.
- A **consumer** reads messages through the transport and processes work.
- A **scheduler** triggers periodic jobs.
- A **publisher** uses a connection pool to send results.
- A **health/monitoring component** observes the status of other components.

At startup, you usually want foundational resources ready **before** components that use them: open the transport first, then run the consumer. At shutdown, the safe sequence must be **reversed**: stop the consumer first so it does not generate new work, and only then close the transport. Closing the transport too early can cause connection errors, lost messages, or unfinished in-flight tasks in the consumer.

Spring Framework provides `Lifecycle`, `Phased`, and especially `SmartLifecycle` so beans can coordinate **start/stop**. There are two crucial rules:

1. **Phase rule:** on startup, **lower phases start first**; on shutdown, **higher phases stop first**.
2. **`depends-on` dependency rule:** if bean `consumer` depends on bean `transport`, Spring must **start `transport` before `consumer`**, and **stop `consumer` before `transport`**, even when their phases suggest a different order.

Therefore, "stopping in reverse order" is not merely reversing an arbitrary bean list. It is a process coordinated by `LifecycleProcessor`, combining phases and the dependency relationships known to `BeanFactory`.

This lesson uses concepts and APIs from **Spring Framework 6.x / Spring Boot 3.x**, with **Java 17+** examples.

## 2. Three interfaces to distinguish

### 2.1. `Lifecycle`: knowing how to start and stop

`org.springframework.context.Lifecycle` defines three operations:

```java
void start();
void stop();
boolean isRunning();
```

A bean implementing `Lifecycle` can participate in `ApplicationContext.start()` and `ApplicationContext.stop()` calls when a suitable lifecycle processor is present. However, **do not infer that every plain `Lifecycle` bean is automatically started on context refresh**: automatically participating in the startup phase is a benefit of `SmartLifecycle`.

`isRunning()` must reflect the component's actual state; returning a hardcoded `true` can mislead Spring into thinking the component is still active or skipping a necessary step.

### 2.2. `Phased`: providing a phase

`org.springframework.context.Phased` declares `int getPhase()`.

A phase value is **an integer**, not a duration in seconds. Negative, zero, and positive values are all valid. When comparing, Spring does not require phases to be contiguous:

```text
phase -100  →  phase 0  →  phase 200
      start from left to right
      stop from right to left
```

Two independent beans with different phases have a relative order determined by phase. Two beans with the same phase **have no general guarantee of start/stop order within that group**; if ordering is a correctness requirement, declare real dependencies instead of relying on bean names, source declaration order, or component scan timing.

### 2.3. `SmartLifecycle`: lifecycle with auto-start and stop callback

`org.springframework.context.SmartLifecycle` extends `Lifecycle` and `Phased`, adding:

```java
boolean isAutoStartup();
void stop(Runnable callback);
```

`isAutoStartup()` indicates whether the component is started automatically on context refresh. In current Framework versions, `SmartLifecycle` defaults to auto-start; for components that must start manually, you can override it to `false`.

`stop(Runnable callback)` lets the lifecycle processor know **when stopping has actually completed**, even during asynchronous shutdown. The bean must call `callback.run()` **after finishing the work it needed to wait on**, and must ensure the callback is invoked on both the success path and handled error paths.

> `SmartLifecycle` has a default phase `SmartLifecycle.DEFAULT_PHASE`, equal to `Integer.MAX_VALUE` in Spring Framework 6.x. A plain `Lifecycle` not implementing `Phased` is treated by the lifecycle processor as phase `0`. Consequently, a `SmartLifecycle` that does not override phase usually starts very late and stops very early compared to a phase-0 bean; set explicit phases when ordering has business meaning.

### 2.4. Summary table

| Mechanism | Purpose | Defines its own ordering? |
| --- | --- | --- |
| `Lifecycle` | Provides `start`, `stop`, `isRunning` | No dedicated phase of its own |
| `Phased` | Places bean into a specific phase | Yes, relative to other phases |
| `SmartLifecycle` | Auto-start and stop callback, with phase | Yes, by phase and dependencies |
| `@DependsOn` | Declares that a bean depends on another bean | Yes, **takes precedence over phase** for the dependent pair |
| `@Order` / `Ordered` | Sorts certain Spring-managed collections/callbacks | **Does not replace** `SmartLifecycle`'s phase contract |
| `@PreDestroy` / `DisposableBean` | Destroys and releases bean after usage lifecycle | Not a phased start/stop mechanism |

## 3. Phase rule: ascending start, descending stop

Suppose three **independent** `SmartLifecycle` beans:

| Bean | `getPhase()` | Start | Stop |
| --- | ---: | ---: | ---: |
| `ConnectionPoolLifecycle` | -200 | 1 | 3 |
| `ConsumerLifecycle` | 0 | 2 | 2 |
| `MetricsLifecycle` | 100 | 3 | 1 |

When the context refreshes and beans auto-start:

```text
START:
  connection-pool (-200)
  consumer        (0)
  metrics         (100)

STOP:
  metrics         (100)
  consumer        (0)
  connection-pool (-200)
```

Why is reverse order helpful? If metrics depends on running logic, it may need to stop new measurements first; the consumer may need to stop accepting work before the pool closes. However, the bean names/roles in the table are just examples; **phase must reflect real lifetime dependencies**.

### 3.1. Phase is not thread priority

`getPhase() = 100` does not mean a thread uses priority 100 or waits 100 ms. It only supplies relative ordering for the lifecycle.

There is no Framework-enforced rule saying "negative phases are always infrastructure, positive phases are always business". That can only be an **internal project convention**, which should be documented and kept free of conflicts with Spring integration phases.

### 3.2. Phase is not bean creation order

Before starting a `SmartLifecycle`, Spring must instantiate the bean and resolve constructor dependencies. Bean definitions can be loaded/instantiated via mechanisms separate from phase: autowiring, bean factory post-processing, component scanning, singleton pre-instantiation, and auto-start discovery.

Therefore, do not use `getPhase()` as the sole tool to command **bean A's constructor must run before bean B's constructor**. When an initialization relationship is needed, use dependency injection and/or `@DependsOn` for its intended purpose.

### 3.3. Phase does not guarantee order within the same group

If `A` and `B` are both at phase 0, you should not rely on `@Bean` order in the source file to conclude A will definitely start before B in all environments. When `B` genuinely needs `A` to operate, express that relationship explicitly.

## 4. `depends-on`: dependency relationship takes precedence over phase

Suppose bean `consumer` uses bean `transport`. The true relationship is:

```text
consumer depends on transport
```

Expressed in Spring:

```java
@Bean("transport")
SmartLifecycle transport() {
    return new TransportLifecycle();
}

@Bean("consumer")
@DependsOn("transport")
SmartLifecycle consumer() {
    return new ConsumerLifecycle();
}
```

This is an **illustrative snippet**: you need to define both implementations and import `@Bean`, `@DependsOn`, and `SmartLifecycle`. A complete runnable example is in section 7.

When declaring `@DependsOn("transport")` on bean `consumer`, Spring knows:

- To create bean `consumer`, bean `transport` must be initialized first.
- During lifecycle startup, `transport` must start **before** `consumer`.
- During lifecycle shutdown, `consumer` must stop **before** `transport`.
- For singleton beans, during destruction, the dependent bean (`consumer`) is destroyed **before** the bean it depends on (`transport`).

**The direction is easy to get backwards:** `@DependsOn("transport")` goes on `consumer`, not `@DependsOn("consumer")` on `transport`.

### 4.1. What if phase conflicts with `depends-on`?

Example:

| Bean | Phase | Relationship |
| --- | ---: | --- |
| `transport` | 100 | Resource provider |
| `consumer` | -100 | `consumer` **depends on** `transport` |

Looking **only** at phase, a beginner might predict consumer starts before transport. However, that would start the consumer while its resource is not ready yet.

Once the `depends-on` relationship is registered in `BeanFactory`, **dependency beats phase**:

```text
Actual START:
  transport  (100)   ← must be ready first
  consumer  (-100)

Actual STOP:
  consumer  (-100)   ← no longer using transport
  transport  (100)
```

This rule is enforced by `DefaultLifecycleProcessor` when handling beans with dependency relationships. The goal is preserving invariants so phase cannot "force" a dependent to start before its dependency or stop after its dependency.

### 4.2. With multiple dependency levels

If:

```text
webConsumer depends-on messageRouter
messageRouter depends-on transport
```

the dependency-valid order is:

```text
START: transport → messageRouter → webConsumer
STOP:  webConsumer → messageRouter → transport
```

Even if all three are assigned confusing phases, Spring still honors the declared relationships. Nevertheless, a maintainable system should **choose phases aligned with the dependency graph**, instead of deliberately creating conflicts. The conflicting example in section 7 only serves to prove the precedence principle.

### 4.3. Are `@DependsOn` and constructor injection the same?

Not completely.

```java
@Bean
ConsumerService consumerService(TransportClient transportClient) {
    return new ConsumerService(transportClient);
}
```

Constructor/factory-method injection expresses **needing an object**; Spring must resolve the dependency to create the consumer. `BeanFactory` can also track dependency relationships for lifecycle coordination.

```java
@Bean
@DependsOn("transportLifecycle")
ConsumerService consumerService() {
    return new ConsumerService();
}
```

`@DependsOn` expresses an **initialization/stop/destruction ordering relationship between beans by name** even when the consumer does not take a transport constructor parameter—for example when both interact through a singleton registry or out-of-JVM broker.

When there is an actual code dependency, prefer **constructor injection** so the compiler and tests see the contract. Use `@DependsOn` when there is a clear bean lifecycle requirement that injection does not express completely or directly.

`@DependsOn` **does not inject** an object into a field, does not create a communication channel, and does not prove the external system is healthy. It ensures the dependency bean is prepared/started in the order Spring knows, while "ready to receive messages" must be genuinely implemented by the component's `start()`.

### 4.4. Singleton scope of destruction ordering

In Spring Framework, `depends-on` relationships can affect **singleton bean destruction order**. Do not apply this assumption to every prototype: Spring does not manage prototype destruction lifecycles the way it manages singletons. If code creates resources outside the container on its own, Spring will not automatically close them merely because `@DependsOn` is present.

## 5. How does `DefaultLifecycleProcessor` coordinate ordering?

Spring Framework includes `DefaultLifecycleProcessor`, normally registered under the name `lifecycleProcessor` in `ApplicationContext`.

On the normal startup path:

1. Context refresh reaches its final stage.
2. `LifecycleProcessor.onRefresh()` finds eligible lifecycle beans and auto-starts `SmartLifecycle` beans with `isAutoStartup() == true`.
3. Beans are organized by phase; lower-phase beans are processed earlier on the start path.
4. When starting a bean, the processor checks that bean's **dependencies**: dependencies must start first.
5. The bean executes `start()` and updates its `isRunning()` state.

On the normal shutdown path:

1. `ApplicationContext.close()` calls the lifecycle processor to stop running components.
2. Phases are traversed **from highest to lowest**.
3. Before stopping a bean, the processor stops beans that depend on it (dependent beans).
4. For `SmartLifecycle`, the processor calls `stop(Runnable callback)` and waits for the phase's callbacks per the timeout policy.
5. After the stop stage, the context proceeds to destroy singletons and release container-managed resources.

This is an explanatory model, not a guarantee of every internal implementation step across all Spring Framework versions. The order of **a specific bean** also depends on whether the bean is running, whether it auto-started, whether its callback returns, and whether the context is shutting down normally or killed abruptly.

### 5.1. Distinguishing "stop" and "destroy"

A bean can go through two mechanisms:

```text
Active context
       |
       v
LifecycleProcessor.stop: stop work, threads, message intake
       |
       v
Destroy singletons: @PreDestroy / DisposableBean / destroyMethod
       |
       v
Closed context
```

`stop()` is for **stopping operation**. Destroy callbacks are for **releasing resources** when the bean is destroyed. A bean can support both; the design must be idempotent so double-closing resources never causes errors.

For example, a consumer needs to stop accepting messages and wait for in-flight processing to finish in `stop(Runnable)`, and then its destroy method releases a registry or thread pool if owned by the bean. If the consumer still uses the transport while `stop()` is running, the transport must not have closed yet.

### 5.2. Phased shutdown does not by itself guarantee the whole process finishes

For callbacks to run, the application must go through a proper shutdown: `ConfigurableApplicationContext.close()`, Spring Boot's shutdown hook when a signal is handled normally, or infrastructure-managed context stop/close.

If the process receives `kill -9`, crashes natively, or is force-killed by the container after exceeding the grace period, Spring **has no opportunity** to guarantee ordered shutdown. Lifecycle ordering is one part of safe design, not a substitute for timeouts, signal handling, idempotency, and failure recovery.

## 6. `stop(Runnable callback)` and stop deadlines

### 6.1. The callback is a completion signal, not a start signal

When a `SmartLifecycle` is stopped, the lifecycle processor can invoke:

```java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
```

The snippet above implements **synchronous stopping** when `stop()` actually finishes stopping work. If `stop()` merely sends a signal while the consumer is still running, invoking the callback right away is semantically wrong: the processor may let dependencies stop while the consumer has not stopped using them.

For asynchronous stopping, `stop(Runnable callback)` must invoke `callback.run()` **only after stopping has finished**, even when stopping runs on another thread. Ensure the callback is invoked **once**, never lost on error paths or when an executor rejects the task.

Pseudocode illustrating the idea:

```java
@Override
public void stop(Runnable callback) {
    shutdownExecutor.execute(() -> {
        try {
            stopAcceptingNewMessages();
            waitForInFlightWorkToFinish();
        } finally {
            running = false;
            callback.run();
        }
    });
}
```

This **is not a standalone runnable example**: it requires designing `shutdownExecutor`, `stopAcceptingNewMessages`, `waitForInFlightWorkToFinish`, timeouts, and task-rejection handling. In production, do not let `waitForInFlightWorkToFinish()` block forever; task deadlines must be smaller than the shutdown budget.

### 6.2. Per-phase timeout in Spring Boot

Spring Boot allows configuring:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

This is the **per-phase wait budget of the lifecycle processor** during shutdown; it is not an individual per-bean timeout and does not turn your `stop()` into a method forcibly aborted after 20 seconds.

If a bean's callback does not arrive within the deadline, the processor may proceed with shutdown per framework mechanics; dependent resources risk being closed before background work ends. Therefore:

- `stop(Runnable)` must invoke the callback upon completion.
- I/O operations need their own timeouts.
- Running work needs a bounded drain/cancel mechanism.
- Web server graceful shutdown and infrastructure termination grace period must have compatible budgets.

A single timeout configuration line **cannot fix deadlocks** or un-timed blocking I/O calls in the implementation.

### 6.3. How does `server.shutdown=graceful` relate?

For supported web applications, you can use:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Web server graceful shutdown attempts to stop accepting new requests and give in-flight requests time to finish. That process cooperates with Spring Boot's lifecycle processor, but **does not automatically guarantee** MQ consumers, background jobs, or self-managed clients have drained properly.

Design `SmartLifecycle` beans for resources outside the web server and test the actual ordering interaction. Do not assign arbitrary phases matching Boot's infrastructure phases without reason and testing on your exact Servlet/Reactive stack.

## 7. Complete example: `@DependsOn` beats phase in start/stop

The example below uses **Java 17+, Spring Boot 3.3.x**, requiring only the `spring-boot-starter` dependency. The app runs in `WebApplicationType.NONE` mode to avoid web server effects, keeping the bean ordering output short and easy to verify.

We create three `SmartLifecycle` beans:

- `heartbeat`, phase `-200`, **no** dependencies.
- `transport`, phase `100`, provides resources.
- `consumer`, phase `-100`, declares `@DependsOn("transport")`.

Intentional verification point: phase `consumer=-100` is **lower** than phase `transport=100`. Looking solely at phase, consumer would start first. Because of `depends-on`, however, transport must start before consumer and stop after consumer.

### 7.1. Create the Maven project

Structure:

```text
smart-lifecycle-order-demo/
├── pom.xml
└── src/main/
    └── java/com/example/lifecycle/LifecycleOrderDemoApplication.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>smart-lifecycle-order-demo</artifactId>
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
```

### 7.2. Complete application code

Create `src/main/java/com/example/lifecycle/LifecycleOrderDemoApplication.java`:

```java
package com.example.lifecycle;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.DependsOn;

@SpringBootApplication
public class LifecycleOrderDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(LifecycleOrderDemoApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("main:context-ready");
        }
    }

    @Bean("heartbeat")
    SmartLifecycle heartbeat() {
        return new LoggingLifecycle("heartbeat", -200);
    }

    @Bean("transport")
    SmartLifecycle transport() {
        return new LoggingLifecycle("transport", 100);
    }

    @Bean("consumer")
    @DependsOn("transport")
    SmartLifecycle consumer() {
        return new LoggingLifecycle("consumer", -100);
    }

    static final class LoggingLifecycle implements SmartLifecycle {

        private final String name;
        private final int phase;
        private volatile boolean running;

        LoggingLifecycle(String name, int phase) {
            this.name = name;
            this.phase = phase;
        }

        @Override
        public int getPhase() {
            return phase;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("start:" + name);
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("stop:" + name);
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
    }
}
```

**Implementation explanation:**

1. `LoggingLifecycle` is a real `SmartLifecycle` implementation with `getPhase()`, `start()`, `stop()`, `stop(Runnable)`, and `isRunning()`. The example only logs so no executor or socket is needed.
2. The `@Bean` methods are registered by Spring under the exact names `heartbeat`, `transport`, and `consumer`.
3. `@DependsOn("transport")` is placed on the **consumer bean**, expressing that consumer needs transport.
4. `isAutoStartup()` returns `true`, so the lifecycle processor starts the components during refresh.
5. When `application.run(args)` returns, the context has already started; the `main:context-ready` line sits **after the start lines**.
6. `try-with-resources` closes `ConfigurableApplicationContext`. On close, Spring invokes `stop(Runnable)` for running lifecycle beans, so the stop lines appear.
7. `stop(Runnable)` invokes the callback right away **because synchronous stop already completed on that thread**. In real applications, invoke the callback only once the resource is no longer in use.

### 7.3. Build and run

In the directory containing `pom.xml`:

```bash
mvn package
```

Run:

```bash
java -jar target/smart-lifecycle-order-demo-0.0.1-SNAPSHOT.jar
```

If the project already has Maven Wrapper:

```bash
./mvnw package
```

Windows PowerShell with wrapper:

```powershell
.\mvnw.cmd package
```

The run commands assume Maven/JDK and dependencies are already downloaded. This is not a plain Java program that can be compiled directly with a single `javac` command lacking Spring libraries on the classpath.

### 7.4. Expected output

In an environment without extra lifecycle beans altering observation, the **lines printed by the demo code itself** are:

```text
start:heartbeat
start:transport
start:consumer
main:context-ready
stop:consumer
stop:transport
stop:heartbeat
```

The console may have additional logs from Spring Boot, Maven, or the logging system; this lesson guarantees only the **relative order of lines printed by the demo**.

Step-by-step explanation:

- `heartbeat` has phase `-200`, so it starts first because it is independent and has the lowest phase.
- `consumer` has phase `-100`, so it would be considered earlier than `transport` (phase `100`) if looking only at phase. However, dependencies are checked: the processor **starts `transport` first**, and only then starts `consumer`.
- At the end of the `try` block, the context closes and the processor starts stopping in descending phase order. It inspects `transport` at the high phase, discovers **`consumer` depends on `transport`**, and therefore stops `consumer` **before** `transport`.
- Finally, the independent `heartbeat` at phase `-200` is stopped.

Thus, the output shows both rules operating together: **phase** orders independent components, while **`depends-on`** protects order between beans that have a dependency relationship.

### 7.5. Control experiment: removing `@DependsOn`

To see the role of dependency clearly, try **on a copy of the project** removing only the `@DependsOn("transport")` annotation on the `consumer` bean. Build/run again with the three phases unchanged.

Once the two beans no longer have a dependency relationship known to `BeanFactory`, their relative order is based on phase alone:

```text
start:heartbeat
start:consumer
start:transport
main:context-ready
stop:transport
stop:consumer
stop:heartbeat
```

The output illustrates the risk: consumer starts before transport, and transport stops before consumer. In a system with a real message broker, this can cause startup errors or lose the ability to drain on shutdown. Therefore, do not merely set phases while **forgetting to express the actual dependency relationship**.

### 7.6. Second experiment: phases aligned with dependency

Keep `@DependsOn("transport")`, and change phases to:

```text
heartbeat = -200
transport = -100
consumer  = 100
```

Both phase and dependency now point in the same direction:

```text
START: heartbeat → transport → consumer
STOP:  consumer  → transport → heartbeat
```

This is the arrangement **recommended in production** whenever possible: phases reflect startup layers and `depends-on` states concrete constraints. Do not deliberately create conflicting phases like the API-testing demo.

## 8. Distinguishing three ordering mechanisms: phase, `depends-on`, `@Order`

A common design mistake is changing `@Order` on a bean and expecting shutdown order to change accordingly. Distinguish:

| Need | Suitable tool | Reason |
| --- | --- | --- |
| Order groups of components with a start/stop lifecycle | `SmartLifecycle.getPhase()` | LifecycleProcessor organizes phases |
| Force consumer to start after transport and stop before transport | `@DependsOn("transport")` or a dependency known to BeanFactory | Constrains start/stop and singleton destruction |
| Sort `ApplicationRunner` or sets of listeners | `Ordered` / `@Order` where API supports it | For callback execution order, does not coordinate the lifecycle graph |
| Order bean init based on class injection | Constructor/factory-method dependency | BeanFactory must resolve before creating dependent |
| Release connections at the end of lifecycle | `@PreDestroy`, `DisposableBean`, or destroy method | Resource destruction after proper stop |
| Ensure producer stops sending new work while draining | Producer stop/disable API and coordination protocol | Spring phase does not replace business logic |
| Prevent data loss when process is killed | Ack/retry/idempotency and consumer design | Lifecycle order cannot guarantee callbacks when process is killed |

`@DependsOn` can also be used at the `@Component` level:

```java
@Component
@DependsOn("transport")
class ConsumerLifecycle implements SmartLifecycle {
    // Implement start(), stop(), getPhase(), ...
}
```

This illustrates the annotation declaration; the class omits full methods. In production, constructor injection is commonly used if the consumer receives transport as an explicit Java dependency.

Do not treat phase as a transaction mechanism. Spring does not automatically roll back every side effect of an already-started component if a later component fails.

## 9. Designing shutdown for real-world systems

### 9.1. Producer → queue → consumer

Suppose we have:

```text
HTTP request → producer → local queue → consumer → external transport
```

If each component has its own lifecycle:

- On startup: prepare transport and consumer, and only then allow producer to create more work.
- On shutdown: producer **stops accepting/generating new work**, consumer **drains the queue and stops**, and then transport **closes connections**.

A possible phase plan:

| Component | Illustrative suggested phase | Real relationship |
| --- | ---: | --- |
| Transport | -200 | Longest-lived infrastructure |
| Consumer | -100 | `depends-on` transport |
| Producer | 100 | `depends-on` consumer |

Order:

```text
START: Transport → Consumer → Producer
STOP:  Producer  → Consumer → Transport
```

The numbers are purely an **illustrative convention**, not fixed phases recommended by Spring Boot for all bean types. In real web projects, Boot's server/lifecycle integrations also have their own phases; verify actual behavior to avoid colliding with HTTP graceful shutdown.

### 9.2. Do not stop a resource before its dependent finishes

A common bug:

```text
stop:transport
stop:consumer
```

By the time the consumer tries to flush results or ack messages, the transport is already closed. Even if logs show the JVM exiting "cleanly", business data is lost or external retries are triggered.

Better:

```text
stop:consumer (stop receiving, drain, and ack in-flight work)
stop:transport (close connection after consumer stops using it)
```

**Merely changing method call order is not enough** if `stop(consumer)` returns before in-flight processing finishes. The callback must reflect actual draining; otherwise the lifecycle processor may let transport stop too early.

### 9.3. Shutdown deadlines and guarantee levels

In containers/Kubernetes, shutdown usually proceeds in sequence: the orchestrator sends a stop signal, the app attempts graceful shutdown within the grace period, and then the process may be killed if it exceeds the limit.

Therefore:

- Keep each task's timeout smaller than the total shutdown budget.
- Stop accepting new work before draining.
- Use idempotency and retries to recover unfinished work if the process is killed.
- Check the Pod's `terminationGracePeriodSeconds` and `spring.lifecycle.timeout-per-shutdown-phase`.
- Do not assume a single `@DependsOn` guarantees every request or queue message finishes cleanly.

### 9.4. When `isAutoStartup()` is `false`

A `SmartLifecycle` bean can skip auto-starting on context refresh if it overrides:

```java
@Override
public boolean isAutoStartup() {
    return false;
}
```

It can be started by an explicit operation. At shutdown, the processor normally checks running state; a bean that has not started does not necessarily have `stop()` called. Therefore, expecting a stop log line for every registered bean is inaccurate.

If cleanup is mandatory even when the bean never started, design a dedicated destroy method with guards to avoid double cleanup.

## 10. Common errors and diagnostics

### Error 1 — "Set a high phase yet bean still stops after a lower-phase bean"

Check `@DependsOn` relationships and dependencies known to `BeanFactory`. Dependency relationships take precedence to protect dependents. This is correct behavior, not necessarily a `DefaultLifecycleProcessor` bug.

### Error 2 — "Consumer stops before transport yet still hits Connection closed"

The order was right **at the stop call point**, yet `consumer.stop()` might only have sent an async signal and returned immediately or called the callback too early. Wait for in-flight work to finish **before invoking the callback**, with deadlines and error handling.

### Error 3 — "Added `@Order(1)` yet shutdown order did not change"

`@Order` is not `SmartLifecycle`'s phase. Override `getPhase()` or declare dependency relationships if a real invariant exists.

### Error 4 — "`stop(Runnable)` did not seem to run when clicking Stop in the IDE"

The IDE/process may have been force-killed, the app bypassed Spring's shutdown hook, the context had not closed, or the bean was not in the running state. Test with `context.close()` in a test program and inspect the actual kill signal sent by your environment.

### Error 5 — "Shutdown waits forever and then other resources get stopped"

A callback may not have been invoked, or a drain step waited indefinitely. Inspect `stop(Runnable)`, network timeouts, thread dumps, and `spring.lifecycle.timeout-per-shutdown-phase`. Do not mask the bug by endlessly increasing timeouts.

### Error 6 — "`@DependsOn` points to the wrong bean"

The name in the annotation is the **bean name**, not a Java interface name or arbitrary variable name. For example, `@Bean("transport")` pairs with `@DependsOn("transport")`. A wrong name can make context creation fail or omit the intended relationship if the annotation is not attached to the right bean definition.

### Error 7 — "Circular dependency: A depends-on B, B depends-on A"

That is an invalid dependency cycle. Spring cannot find a linear start/stop order satisfying both; startup can fail when resolving bean definitions. Redesign ownership, extract an independent registry/mediator, or remove the cycle.

### Error 8 — "Stop callback runs twice"

If you manually invoke the callback in multiple branches and also invoke it in `finally`, the processor may receive inconsistent completion signals. Design the callback to run exactly once, including when the executor rejects the task or the task fails.

### Error 9 — "Bean does not auto-start despite implementing `SmartLifecycle`"

Check `isAutoStartup()`, whether the bean is registered in the real context, whether `start()` updates `isRunning()` properly, and whether an exception occurred at startup. If the bean belongs to a child context, do not assume the parent context lifecycle coordinates every child bean outside its API.

### Error 10 — "Changing phase leaves bean constructors running in the old order"

Phase coordinates **start/stop lifecycle**, not the total constructor/injection order. If bean B needs bean A at construction time, use dependency injection/`@DependsOn`; reserve phase for **operational activation** order.

### Error 11 — "`@PreDestroy` ran cleanly so messages definitely were not lost"

`@PreDestroy` typically runs during bean destruction, when many other components may already have stopped. To stop receiving messages, drain in-flight work, and only then close dependencies, use `SmartLifecycle.stop(Runnable)` with an accurate callback.

### Error 12 — "Test ran without a web server, production behaves differently"

Web servers, broker listener containers, schedulers, and framework integrations can register their own `SmartLifecycle` beans. In production, overall shutdown order may involve extra phases, callbacks, and contexts. Test with the real starters/dependencies and the same shutdown signals rather than extrapolating everything from a `WebApplicationType.NONE` demo.

## 11. Testing order and protecting against data loss

### 11.1. Unit testing `SmartLifecycle` logic

For a simple bean, verify:

1. After `start()`, `isRunning()` becomes `true`.
2. After `stop()`, `isRunning()` becomes `false`.
3. `stop(Runnable)` performs cleanup and then invokes the callback.
4. Repeated `start()`/`stop()` calls do not cause double-ack or double-close.

For multi-threaded components, use latches, stub clients, and managed executors to control completion timing instead of `Thread.sleep(...)` in tests.

### 11.2. Real integration testing on ApplicationContext

A unit test manually calling `consumer.start()` and then `transport.start()` **cannot verify** the order coordinated by Spring's lifecycle processor.

Create a context with the three beans from the section 7 example, record start/stop events into a thread-safe list, close the context, and assert the order:

```text
start:heartbeat
start:transport
start:consumer
stop:consumer
stop:transport
stop:heartbeat
```

If shutdown has async callbacks, the test must wait for context close to complete within a timeout contract and verify in-flight tasks finished. When testing Spring Boot, inspect additional lifecycle beans auto-registered by other starters to avoid accidentally relying on an unguaranteed global order.

### 11.3. Testing failure paths

At least three failures are worth proactively simulating:

- `transport.start()` throws an exception: `consumer` must not begin serving normally.
- `consumer.stop()` exceeds the allowed timeout: understand that the processor can proceed to stop dependencies, and design recovery.
- Process killed while draining: unacknowledged work must have out-of-process retry/idempotency mechanisms.

The goal is not merely pretty log lines, but ensuring **resources are not closed while dependents still need them**, within the guarantees normal shutdown can provide.

## 12. Practice questions and answers

**Question 1.** A has phase `-10`, B has phase `20`, with no dependency relationship. How do they start/stop?

*Answer:* Start A then B; stop B then A.

**Question 2.** `Consumer` has phase `-100`, `Transport` has phase `100`, yet `Consumer @DependsOn("transport")`. How do they start/stop?

*Answer:* Start Transport then Consumer; stop Consumer then Transport. `depends-on` takes precedence over phase.

**Question 3.** What does `@DependsOn("transport")` placed on the `Transport` bean mean?

*Answer:* Transport depends on the bean named `transport` (if it carries that name itself, creating a wrong/cyclic relationship); it **does not** mean "consumer uses transport". The annotation must be placed on **consumer** and point to the dependency bean name.

**Question 4.** Given `@Order(1)` on Consumer and `@Order(2)` on Transport; can we omit `@DependsOn` and trust shutdown will be right?

*Answer:* No. `@Order` applies to APIs that support sorting; it does not replace `SmartLifecycle`'s phase/dependency mechanism.

**Question 5.** `stop(Runnable callback)` submits a background task and invokes the callback immediately before the task finishes draining the queue. What is wrong?

*Answer:* The callback reports stop completion too early. The lifecycle processor can proceed to close Transport while Consumer is still processing the queue.

**Question 6.** Why might a `SmartLifecycle` bean that never started not print a stop line?

*Answer:* The processor checks running state before stopping; a bean that is not active does not necessarily need `stop()`. Destroy callbacks are a separate mechanism.

**Question 7.** Does setting `spring.lifecycle.timeout-per-shutdown-phase=10s` guarantee every socket is cut right after 10 seconds?

*Answer:* No. The property controls how long the processor waits for callbacks per phase. Blocking I/O needs the library's own timeout/cancellation, and the process manager has its own kill policy.

**Question 8.** Why does `@DependsOn` not replace retries/idempotency when an MQ consumer shuts down?

*Answer:* It coordinates start/stop inside the context during normal shutdown. It does not guarantee the JVM always runs callbacks, does not prevent the process from being killed, and does not control message ack state on the broker.

**Question 9.** If three beans are all at phase 0, should you rely on Java file name order?

*Answer:* No. Declare real dependencies; phase 0 merely groups them in the same lifecycle bucket without creating a durable per-bean ordering rule.

**Question 10.** Bean Consumer has a constructor taking Transport, so is `@DependsOn` needed?

*Answer:* Constructor injection already expresses the real dependency and `BeanFactory` can track that relationship. Add `@DependsOn` only if you want to make a name-based initialization/destruction lifecycle constraint explicit that injection does not fully convey; verify with an integration test.

## 13. Implementation checklist

Before putting a `SmartLifecycle` pair into production:

- [ ] Clearly identify **who owns the resource** and who consumes it.
- [ ] Assign phases by convention, avoiding the default max phase when order matters.
- [ ] Declare real dependencies with DI and/or `@DependsOn`; **dependent starts after, stops before** its dependency.
- [ ] Make `start()` / `stop()` idempotent, with `isRunning()` reflecting real state.
- [ ] In `stop(Runnable)`, never invoke the callback before stopping intake and finishing drain.
- [ ] Set deadlines/timeouts for I/O and queue draining, including error paths.
- [ ] Choose `spring.lifecycle.timeout-per-shutdown-phase` compatible with the termination budget.
- [ ] If using a web server, coordinate with graceful shutdown; do not assume the same phase as starters.
- [ ] Test by **closing a real ApplicationContext**, not merely calling single methods.
- [ ] Test normal shutdown, startup errors, and force-kill; have retries/idempotency for work that cannot finish in time.

## 14. Official documentation

The following documents are foundational sources for Spring Framework 6.x and Spring Boot 3.x:

- [Spring Framework Javadoc — `SmartLifecycle`](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/context/SmartLifecycle.html): phases, `isAutoStartup`, `stop(Runnable)`, and `depends-on` precedence rules.
- [Spring Framework Javadoc — `DefaultLifecycleProcessor`](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): coordinating bean lifecycles by phase and shutdown callbacks.
- [Spring Framework Javadoc — `@DependsOn`](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/context/annotation/DependsOn.html): initialization-time dependencies and singleton destruction-time ordering.
- [Spring Framework Reference — Lifecycle callbacks and `SmartLifecycle`](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): bean lifecycles and the lifecycle processor.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): web server graceful shutdown and appropriate timeout settings.

## 15. Conclusion

**`SmartLifecycle` uses phases to order startup in ascending order and shutdown in descending order.** However, for beans with dependency relationships, `depends-on` takes precedence over phase: **a dependency must start before and stop after its dependent**.

This rule protects resources that must stay alive long enough for components using them to stop safely. Turning the right order into truly safe shutdown also requires timely `stop(Runnable)` callbacks, time bounds, draining capability, idempotency, and a policy for handling killed processes.

Design phases as a map of lifecycle layers, and `@DependsOn` as the dependency contract between beans. When both accurately express the architecture, shutdown becomes predictable and verifiable.