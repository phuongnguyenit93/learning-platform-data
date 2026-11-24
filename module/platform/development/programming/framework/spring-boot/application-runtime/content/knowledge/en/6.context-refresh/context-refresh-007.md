# Active, Running, and Closed States of ApplicationContext in Spring Boot

## 1. Why Must We Distinguish These Three States?

A Spring Boot application has many "operational milestones" that are easily lumped together as *running*: the JVM process exists, `ApplicationContext` has been created, Spring has finished `refresh()`, components managed via `Lifecycle` have started, `ApplicationRunner` tasks have completed, the application is ready to accept requests, and finally the context is closed. These milestones do not occur at the same time.

In Spring Framework, two APIs let you observe the state of a context:

- `ConfigurableApplicationContext.isActive()`: whether the context is still in the **active** state within the `refresh/close` lifecycle.
- `ConfigurableApplicationContext.isRunning()`: whether the context's `LifecycleProcessor` coordinator is currently in the **running** state.

Meanwhile, **closed** describes that `close()` has closed the context and released beans/resources. In the common `ConfigurableApplicationContext` API, **there is no symmetric `isClosed()` method** alongside the two methods above. From `isActive() == false` alone, you cannot tell whether the context was never refreshed, failed to refresh, or has already been closed.

These are three concepts of **Spring context lifecycle**; they are also distinct from Spring Boot's `LivenessState` and `ReadinessState`, or OS-level PID/HTTP server state.

**Lesson goal:** read and explain each state accurately, recognize the effects of `refresh()`, `start()`, `stop()`, and `close()`, know when beans are started/stopped/destroyed, and avoid misusing context state as a health check.

Technical context: **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**.

## 2. Lifecycle Map of a Typical Context

```text
SpringApplication creates ApplicationContext
                  |
                  v
       New context, not yet refreshed
       isActive()  = false
       isRunning() = false
                  |
                  v
       Prepare bean definitions
       context.refresh()
          | 
          +--> prepareRefresh() / process BeanFactory
          +--> create beans + post-processors
          +--> initialize LifecycleProcessor
          +--> auto-start eligible SmartLifecycle beans
          +--> ContextRefreshedEvent
                  |
                  v
       Normally active context
       isActive()  = true
       isRunning() = true (*) 
                  |
          +-------+--------+
          |                |
       stop()           close()
          |                |
          v                v
   isActive = true    ContextClosedEvent
   isRunning = false  stop Lifecycle beans
          |           destroy singletons, close factory
       start()             |
          |                v
          v           Closed context
   isActive = true    isActive = false
   isRunning = true   isRunning = false
```

`(*)`: `isRunning() == true` is the normal behavior after a successful `refresh()` with Spring's `DefaultLifecycleProcessor`, even if the application has no web server. A custom `LifecycleProcessor` or a failed/customized lifecycle can differ; inspect the actual value rather than treating the diagram as immutable for every implementation.

**Timing warning inside `refresh()`:** Spring may set the active flag during the refresh-preparation phase **before all beans are constructed**. Therefore, observing `isActive() == true` in the middle of `refresh()` callbacks **does not guarantee** startup succeeded or traffic can be served. The Javadoc contract describes active as "has been refreshed and has not been closed yet," while the internal flag transition explains why early callbacks require caution.

When we say "closed," we care about the result **after `close()` returns normally**. While publishing `ContextClosedEvent` or destroying beans, some states may still reflect a transition in progress rather than the final state.

## 3. `isActive()`: Is the Context Valid for Using Beans?

### 3.1. API Meaning

`ConfigurableApplicationContext.isActive()` indicates whether the context is currently active. In standard `AbstractApplicationContext` implementations, this flag is tied to the refresh and close lifecycle:

- **Before `refresh()`**: not yet active; the bean factory/bean definitions may not be ready.
- **While `refresh()` is executing**: the flag may be turned on from an early phase of refresh; beans may still not be finished creating.
- **After `refresh()` succeeds**: active is `true`; beans can be accessed according to the container contract.
- **After `stop()`**: active **remains `true`** because `stop()` only stops lifecycle-managed components.
- **After `close()`**: active is `false`; the context is no longer valid for retrieving and using beans.
- **After a failed refresh**: the implementation may reset active/clean up; never treat having once seen `true` as proof the application started cleanly.

In ordinary programs, you can use `isActive()` to check a `ConfigurableApplicationContext` you hold before interacting with the BeanFactory. However, checking state is a **point-in-time snapshot**; another thread could request closing the context immediately afterward. `isActive()` by itself does not replace concurrency design or resource management.

### 3.2. What `isActive() == true` Does Not Prove

It **does not prove**:

1. `ApplicationRunner`/`CommandLineRunner` instances have finished running.
2. `ApplicationReadyEvent` has been published.
3. `ReadinessState` is `ACCEPTING_TRAFFIC`.
4. The HTTP server is listening on the expected port or real requests will succeed.
5. Every `SmartLifecycle` bean is still running.
6. All external dependencies (database, cache, message broker) are healthy.
7. The application has not been asked to shut down by Kubernetes/the load balancer.

For example: the context has refreshed successfully, yet an `ApplicationRunner` spends several seconds synchronizing data. At that moment `isActive()` is typically `true`; Spring Boot has **not yet** published `ApplicationReadyEvent`, so readiness can still be `REFUSING_TRAFFIC`. Routing requests based solely on active would be premature.

## 4. `isRunning()`: Lifecycle of Started Components?

`ConfigurableApplicationContext` extends the `Lifecycle` interface, so it has:

```java
void start();
void stop();
boolean isRunning();
```

Inside `AbstractApplicationContext`, these calls are delegated to `LifecycleProcessor`. Spring normally uses `DefaultLifecycleProcessor` to coordinate beans implementing `Lifecycle`/`SmartLifecycle`.

**Practical meaning:** `context.isRunning()` reflects the container's lifecycle-management state. It does not measure "which JVM threads are alive," "whether the scheduler finished all jobs," "whether an HTTP endpoint responds," or "whether 100% of custom application services are healthy."

### 4.1. `Lifecycle` and `SmartLifecycle`

A bean implementing `Lifecycle` has `start()`, `stop()`, and `isRunning()`. That is the contract for a component that can be started/stopped without necessarily being destroyed.

`SmartLifecycle` adds key capabilities:

- `isAutoStartup()`: allows the bean to auto-start during refresh if it returns `true`.
- `getPhase()`: supports phased startup and shutdown ordering.
- `stop(Runnable callback)`: notifies the container when an asynchronous stop completes; **the callback must be invoked** once truly stopped.

`DefaultLifecycleProcessor` normally **auto-starts** `SmartLifecycle` beans that opt into auto-startup during the final phase of refresh. Plain `Lifecycle`-only beans are not automatically started by `onRefresh()` like an auto-starting `SmartLifecycle`; however, an explicit `context.start()` call can start eligible `Lifecycle` beans.

On `context.stop()`, the processor stops running lifecycle beans in phase order (shutdown reverses startup), and the processor's running state becomes `false`. Afterward, `context.start()` can start them again if the context **has not been closed**.

### 4.2. Do Not Equate Running with Ready

Under Spring Boot, a `SmartLifecycle` bean may already be running when `ContextRefreshedEvent` is published, before Boot invokes `ApplicationRunner`s. Hence you can observe:

```text
context.isActive()  == true
context.isRunning() == true

yet:

ApplicationReadyEvent has not occurred yet
ReadinessState == REFUSING_TRAFFIC
```

This case is **not contradictory**: the context and managed lifecycle components are running, while the readiness conditions for the entire application to accept traffic have not completed yet.

Conversely, you can see `isActive() == true` and `isRunning() == false` after `context.stop()`; many singletons still exist and can be invoked, while lifecycle components have stopped. That is not a "closed" context.

## 5. Closed: What Happens When `close()` Is Called?

`ConfigurableApplicationContext` extends `Closeable` and provides `close()`. With `AbstractApplicationContext` and the standard shutdown sequence, closing covers these primary responsibilities:

1. Begin closing the context, publishing `ContextClosedEvent` to listeners.
2. Ask `LifecycleProcessor` to stop lifecycle beans that need stopping (such as `SmartLifecycle`).
3. Destroy singletons managed by the context, running callbacks like `@PreDestroy`, `DisposableBean.destroy()`, and configured destroy methods.
4. Close the BeanFactory/context infrastructure, release associated resources, and mark the context inactive.

Expected outcome when `close()` returns normally:

```text
context.isActive()  -> false
context.isRunning() -> false
```

That is the **post-close state**, distinct from the moment a listener receives `ContextClosedEvent`. The event is published during the close procedure, before full teardown finishes; do not write listeners assuming every bean has already been destroyed at that moment.

### 5.1. Can Beans Still Be Used After Close?

They should not be. Even if Java code still holds a **direct reference** to a bean retrieved earlier from the context, internal resources of that bean may already be closed (DataSource, thread pool, network connections...). A lingering reference **does not prove the bean is still safe to use**.

Calling `getBean(...)` after the context closes can throw `IllegalStateException` because the BeanFactory is no longer active. Do not write logic to "revive" a closed context by calling `start()`. `start()` only controls lifecycle components while the context is still valid; it **does not** recreate bean definitions or re-run `refresh()`.

### 5.2. `close()` Differs from JVM Termination

A program may use Spring Boot in a CLI, test, or service. When the context closes:

- Beans belonging to the context are cleaned up.
- The JVM **may remain alive** if non-daemon threads, other contexts, or other code remain running.
- If the application has a JVM shutdown hook registered by Boot, when the JVM receives a normal termination request, the hook can close the context.
- Power loss, JVM crash, `SIGKILL`, or `Runtime.halt()` can bypass orderly shutdown mechanisms.

Also do not treat `ContextClosedEvent` as proof the entire OS process has died: it is an event **of one context**, not an OS-wide process event.

## 6. Comparison Table of States in Practice

| Situation | `isActive()` | `isRunning()` | Meaning |
| --- | --- | --- | --- |
| Context just created, not yet `refresh()`ed | `false` | `false` | Bean container not yet fully built. |
| Early phase of `refresh()` | May be `true` | Usually `false` | Cannot yet conclude startup is done. |
| `refresh()` succeeded and lifecycle processor is running | `true` | `true` | Context and lifecycle components are active. |
| After `ApplicationStartedEvent`, runners not yet finished | `true` | Usually `true` | Not necessarily ready to accept traffic. |
| After `context.stop()` | `true` | `false` | Bean container still exists; managed lifecycle stopped. |
| After `context.start()` succeeds | `true` | `true` | Lifecycle beans restarted. |
| Handling `ContextClosedEvent` | May still be `true` | Depends on stage | Closing process is still underway. |
| After `context.close()` | `false` | `false` | Context is closed; beans must be treated as unusable. |
| Startup failed | No reliable state to rely on | No reliable state | Boot handles the failure and normally cleans up; inspect root exception. |

The table reflects typical behavior of `AbstractApplicationContext`, `DefaultLifecycleProcessor`, and a normal Spring Boot 3.3 application. Custom contexts or replacement lifecycle processors may behave differently. Do not build an entire runtime diagnostic suite from two booleans alone.

### 6.1. The Two-Boolean Matrix

```text
+----------------------+-----------------------+-------------------------------+
| isActive()           | isRunning()           | How to read it                |
+----------------------+-----------------------+-------------------------------+
| false                | false                 | Unrefreshed / closed / failed |
| true                 | false                 | Active but lifecycle stopped  |
| true                 | true                  | Active and lifecycle running  |
| false                | true                  | Not a normal combination after|
|                      |                       | a normal close/refresh        |
+----------------------+-----------------------+-------------------------------+
```

**You cannot determine "closed" from the matrix alone** without knowing whether `refresh()`/`close()` was ever called. For instance, `false/false` appears **both before refresh and after close**. If you need to track "closed" in a custom library, manage lifecycle state explicitly instead of inferring solely from `isActive()`.

## 7. How Do `refresh()`, `start()`, `stop()`, and `close()` Differ?

| Method | Primary work delegated to container | Creates/refreshes beans? | Destroys beans? | Context still usable after call? |
| --- | --- | --- | --- | --- |
| `refresh()` | Prepares BeanFactory, processors, singletons, and lifecycle | **Yes**, depending on context type | May clean up on re-refresh/failure depending on implementation | Yes, if successful. |
| `start()` | Invokes start on eligible `Lifecycle` beans | **No**, not a refresh | No | Yes, while not closed. |
| `stop()` | Invokes stop on eligible lifecycle beans | No | **No** in the sense of destroying singletons | Yes, context stays active. |
| `close()` | Stops lifecycle then destroys beans/closes container | No | **Yes** | No. |

### 7.1. `refresh()` Is Not `start()`

During `refresh()`, Spring can create singletons, perform dependency injection, run `BeanFactoryPostProcessor`/`BeanPostProcessor`, run init callbacks, and at the end call `LifecycleProcessor.onRefresh()`. After refresh, `isRunning()` is typically `true`.

During `start()`, Spring **does not re-run** the entire bean-creation chain or re-parse `@Configuration`. It only starts lifecycle beans through `LifecycleProcessor`.

### 7.2. `stop()` Is Not `close()`

`stop()` aims to **pause lifecycle-capable components**. A regular bean not implementing `Lifecycle` may remain intact and receive no stop command. `@PreDestroy` callbacks are not invoked merely because the context stops.

`close()` **terminates the context lifecycle**: lifecycle components are stopped if still running, and then singletons are destroyed. This is a major boundary in resource management.

### 7.3. Can a Context Be Refreshed Again?

Not by default. Some `AbstractApplicationContext` subclasses have strategies supporting multiple refreshes, whereas `GenericApplicationContext` and many modern application contexts enforce a single-refresh constraint. For contexts created by `SpringApplication`, do not use `refresh()` as a "restart service" API or as a way to recover after close. Major configuration changes or application restarts must follow supported runtime/deployment mechanisms.

## 8. Runnable Java 17+ Example: Stop, Start, and Close the Same Context

This is a **complete example in a single Java file**, without an HTTP server. It uses `spring-boot-starter`, Java 17+, and Spring Boot 3.3.x. It prints state directly from `ConfigurableApplicationContext` and creates a `SmartLifecycle` bean to observe when the component starts and stops.

**File:** `src/main/java/com/example/contextstate/ContextStateDemoApplication.java`

```java
package com.example.contextstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ContextStateDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ContextStateDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        app.addInitializers(context -> printState("INITIALIZER", context));

        ConfigurableApplicationContext context = app.run(args);
        try {
            printState("AFTER_RUN", context);

            context.stop();
            printState("AFTER_STOP", context);

            context.start();
            printState("AFTER_RESTART", context);
        } finally {
            context.close();
        }

        printState("AFTER_CLOSE", context);
    }

    private static void printState(
            String label, ConfigurableApplicationContext context) {
        System.out.println(
                label
                + " active=" + context.isActive()
                + " running=" + context.isRunning()
        );
    }

    @Bean
    SmartLifecycle exampleComponent() {
        return new SmartLifecycle() {
            private volatile boolean running;

            @Override
            public void start() {
                running = true;
                System.out.println("COMPONENT start");
            }

            @Override
            public void stop() {
                running = false;
                System.out.println("COMPONENT stop");
            }

            @Override
            public void stop(Runnable callback) {
                stop();
                callback.run();
            }

            @Override
            public boolean isRunning() {
                return running;
            }

            @Override
            public boolean isAutoStartup() {
                return true;
            }

            @Override
            public int getPhase() {
                return 0;
            }
        };
    }
}
```

In a Gradle application using Spring Boot plugin 3.3.x and dependency management, the example's dependency is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Run from the project directory with Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD uses `gradlew.bat bootRun`; PowerShell uses `.\gradlew.bat bootRun`. No `spring-boot-starter-web`, port 8080, or database is required.

### 8.1. Expected Status Lines

Ignoring environment-specific Spring Boot banners/logs, in a successful run with `DefaultLifecycleProcessor`, the lines printed by the program typically appear in order:

```text
INITIALIZER active=false running=false
COMPONENT start
AFTER_RUN active=true running=true
COMPONENT stop
AFTER_STOP active=true running=false
COMPONENT start
AFTER_RESTART active=true running=true
COMPONENT stop
AFTER_CLOSE active=false running=false
```

Explaining step by step:

1. **`INITIALIZER`** runs before refresh, with no active lifecycle processor yet: `false/false`.
2. During refresh, Spring sees `SmartLifecycle.isAutoStartup() == true` and calls `COMPONENT start`.
3. `app.run(args)` returns only after Boot completes its startup sequence, including runners and the ready event: typically `true/true`.
4. `context.stop()` causes managed lifecycle components to receive `stop()`, yet the context remains active: `true/false`.
5. `context.start()` starts the component again: `true/true`.
6. `context.close()` stops the component and closes the context. After close returns: `false/false`.

`SmartLifecycle.stop(Runnable)` in the example always invokes `callback.run()` after finishing stop. This is **mandatory if you implement asynchronous stop**: the processor needs a completion signal so it does not wait until the phase timeout. In the example we stop synchronously and invoke the callback immediately.

**Do not use this example to simulate recovering a real-world web server.** This is a `NONE` application meant to illustrate lifecycle. With web servers, broker listeners, and complex infrastructure, `stop()/start()` can disrupt request handling or networking; verify each component's contract and use proper orchestration.

### 8.2. Why Use `try/finally`?

`close()` sits inside `finally` so it is called if stop/start operations throw an exception after `run` returned the context. If **`app.run(...)` itself fails**, the context variable has not been assigned so this `finally` block will not run; Spring Boot has separate startup-failure handling. Do not interpret the example as meaning every JVM crash or power loss is cleaned up.

## 9. Mini Example: `@PreDestroy` Only on Bean Destruction, Not `stop()`

Create a regular bean:

```java
package com.example.contextstate;

import jakarta.annotation.PreDestroy;

public class ReportClient {

    @PreDestroy
    public void dispose() {
        System.out.println("ReportClient destroyed");
    }
}
```

Register that bean in a `@Configuration`/`@SpringBootApplication` class:

```java
@Bean
ReportClient reportClient() {
    return new ReportClient();
}
```

If you add the bean above to the `ContextStateDemoApplication` example and keep the `stop() → start() → close()` sequence, the `ReportClient destroyed` log appears when the context destroys beans during `close()`, not merely on `context.stop()`.

The two snippets above are **additions to the project in section 8**. Place `ReportClient` in the right package and import `@Bean` in the configuration class; do not run the two snippets individually as standalone Java programs. Spring Boot starter 3.3 already includes the Jakarta annotations infrastructure required for this model.

A bean can also have `@PostConstruct` or `InitializingBean.afterPropertiesSet()`. Those initialization callbacks occur when the bean is created during refresh, and **do not re-run** after `context.start()`. Destroy callbacks have their own contract and likewise are not invoked on `stop()` alone.

## 10. How Does Context State Differ from Boot Liveness/Readiness State?

Spring Boot provides the `ApplicationAvailability` abstraction with two axes:

- **`LivenessState`**: `CORRECT` or `BROKEN`, representing an assessment of the application's internal viability.
- **`ReadinessState`**: `ACCEPTING_TRAFFIC` or `REFUSING_TRAFFIC`, representing the decision whether to accept work/traffic.

During default startup:

```text
Context is created
     |
     v
refresh succeeds
  active=true
  lifecycle running (typically true)
     |
     v
ApplicationStartedEvent
     |
     v
LivenessState.CORRECT
     |
     v
ApplicationRunner / CommandLineRunner
     |
     v
ApplicationReadyEvent
     |
     v
ReadinessState.ACCEPTING_TRAFFIC
```

Therefore:

- `isActive()` answers a question about **Spring context lifecycle**.
- `isRunning()` answers a question about **LifecycleProcessor and its managed components**.
- `LivenessState`/`ReadinessState` are **Spring Boot operational signals** for restart/routing decisions.
- Whether an HTTP probe returns 200/503 also depends on the server, Actuator, routing, and health indicators.

**Point to remember:** `context.stop()` is not a universal protocol guaranteed to automatically publish `ReadinessState.REFUSING_TRAFFIC` to an orchestrator. Depending on the application and web components, a stop call may stop infrastructure from serving without meaning readiness has transitioned per a draining strategy. If you need controlled traffic draining, design readiness, instance withdrawal, and graceful shutdown explicitly.

With `spring-boot-starter-actuator`, Spring Boot can expose `/actuator/health/liveness` and `/actuator/health/readiness` when probes are enabled (Boot enables them automatically in Kubernetes, or you can set `management.endpoint.health.probes.enabled=true` elsewhere). **Do not** replace these endpoints with a health indicator that merely returns the result of `isActive()`.

## 11. When Does `ContextClosedEvent` Occur?

`ContextClosedEvent` is the Spring Framework event published when the context starts its closing process. It **does not** mean "all beans have finished being destroyed."

If you register:

```java
@EventListener
public void onClosing(ContextClosedEvent event) {
    System.out.println("Context is closing");
}
```

This is an **illustrative method** inside a `@Component` bean or `@Configuration` class, importing `org.springframework.context.event.ContextClosedEvent` and `org.springframework.context.event.EventListener`. The listener is invoked during `close()`, normally before lifecycle beans are stopped and singletons are destroyed.

Because the event is published while the context is still closing, **do not assert that `event.getApplicationContext()` will report `isActive() == false` right inside the callback**. The final state should be checked **after `close()` has returned**.

If you need structured infrastructure shutdown with guaranteed ordering, `SmartLifecycle`/`LifecycleProcessor` is usually a better fit than stuffing all teardown into a listener. If you need to release resources owned by a single bean, use `@PreDestroy` or a destroy method on that bean.

Note that contexts can have a parent/child relationship: events from a child can propagate to parent listeners. When writing event listeners in a multi-context system, check the identity of the event's source context to avoid accidentally running cleanup logic multiple times.

## 12. Can a Closed Context Be Reopened?

The answer for typical Spring Boot applications: **do not treat a closed context as an object that can be reopened with `start()`**.

- `start()` does not redo `refresh()` and does not recreate destroyed beans.
- `isActive() == false` after close reflects a terminated lifecycle; do not try calling `getBean(...)` to recover.
- Certain special context classes support multiple refreshes, but that is a **contract of the specific implementation**, not a general guarantee for every `ApplicationContext`.
- If you want a fresh application instance after the old one closes, use a workflow that creates a **new** context via SpringApplication or the appropriate deployment environment.
- For services in containers/Kubernetes, restarting the process/pod via deployment orchestration is generally cleaner than trying to reset a context while serving traffic.

### 12.1. Why Can Calling `refresh()` a Second Time Fail?

`GenericApplicationContext` has a contract to register bean definitions and refresh once; calling `refresh()` again can throw `IllegalStateException`. In Spring Boot, the corresponding web context implementations maintain their own internal policies and states. Do not assume "having a `refresh()` method means you can restart at will."

### 12.2. Do You Need a Separate "Closed" Flag?

Only if your application/library genuinely requires it. Your resource-management system can store an explicit enum `NEW → STARTING → RUNNING → STOPPING → CLOSED` to track transitions it controls itself. If you simply hold a `ConfigurableApplicationContext` reference, use `isActive()` and `isRunning()` to observe Spring state, without inferring arbitrary business phases from them.

## 13. Graceful Shutdown and Context Closing

In a Spring Boot 3.3 web application, graceful shutdown is a coordinated mechanism between the HTTP server and the context lifecycle. Explicit configuration:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

When the application receives a normally handled stop signal, `SmartLifecycle` components are stopped in phase order, the web server stops accepting new requests as supported by its implementation, and in-flight requests are given a chance to complete within the allotted time.

**Do not conflate:**

- **`context.stop()`**: requests stopping managed lifecycle components, normally keeping the context active.
- **`context.close()`**: completes context shutdown and destroys beans.
- **HTTP graceful shutdown**: server policy handling in-flight requests while the context stops/closes.
- **Container/pod termination**: platform deadline that can force-kill if the app stops too slowly.

`spring.lifecycle.timeout-per-shutdown-phase` is the time limit for **each stop phase**, not a guarantee that all background work finishes. A `KafkaListener`, scheduler, or custom thread has its own stop contract; ensure it stops picking up new work, releases resources, and respects the allotted budget.

### 13.1. Phase-Ordered Stopping

`DefaultLifecycleProcessor` starts lifecycle beans in ascending phase order and stops them in descending phase order. For example, if A has `phase=0` and B has `phase=100`:

```text
START: A -> B
STOP:  B -> A
```

The goal is that when B depends on A, A starts first, and B stops before A is torn down. Spring may also factor in bean dependency relationships. Do not pick phases simply as "higher number means more important"; determine real dependencies and required stop order.

With `SmartLifecycle.stop(Runnable)`, if shutdown is asynchronous, the callback **must** be invoked when the component has truly stopped; if omitted, the processor may wait until the phase timeout expires. That is the difference between a coordinated shutdown and an abrupt resource termination.

## 14. Common Diagnostic Scenarios

### Scenario A — isActive true, yet HTTP 503

The context may be active and running, yet readiness is currently `REFUSING_TRAFFIC` or an external system is failing. Check `ApplicationReadyEvent`, readiness probes, health indicators, server logs, and related dependencies. Do not assume the context is closed.

### Scenario B — isActive true, isRunning false

Someone may have called `context.stop()` or the lifecycle processor was stopped by orchestration. The bean container is still active; inspect the call site invoking stop and the state of each `Lifecycle` bean. If the app still receives traffic elsewhere, redesign the draining flow because these two flags are not a complete traffic gate.

### Scenario C — isActive false right inside an initializer

This is normal behavior: initializers receive the context before `refresh()`. Do not try calling `context.refresh()` from an initializer to "fix" the false flag; `SpringApplication` must control refresh sequencing.

### Scenario D — isActive false after calling close

That is the expected outcome. Do not hold onto old beans to keep sending requests to a closed connection pool. If downstream logic still needs the service, manage shutdown boundaries and create a new context/process as designed.

### Scenario E — shutdown waits for a long time

A `SmartLifecycle.stop(Runnable)` may have failed to invoke its callback, a stop phase may take too long, or a work queue is still draining. Check `spring.lifecycle.timeout-per-shutdown-phase`, thread dumps, and orchestrator deadlines. Do not look only at `isRunning()`, because it does not reveal *which component* has not finished.

### Scenario F — ContextClosedEvent logged yet JVM does not exit

`ContextClosedEvent` only proves the context closing sequence started, not that the process terminated. Check non-daemon threads, other shutdown hooks, clients/timers outside the context, and remaining containers. If the JVM received `SIGKILL`, the event might not even be published.

## 15. Misconceptions to Avoid

| Misconception | Accurate conclusion |
| --- | --- |
| "`isActive() == true` means the service is ready." | Active is a context state; readiness is a separate operational signal. |
| "`isRunning() == true` means all threads are healthy." | Running is managed by `LifecycleProcessor`; it does not measure every JVM thread/component. |
| "`stop()` closes all beans and invokes `@PreDestroy`." | Stop normally only stops managed lifecycle beans; destroy happens on close/destroy. |
| "`start()` after stop re-runs `ApplicationRunner`s." | Start does not re-run the entire SpringApplication startup. |
| "`false/false` always means the context is closed." | It can also mean a context that has never been refreshed. |
| "Seeing `ContextClosedEvent` means all resources are closed." | The event fires during close, before teardown completes. |
| "`close()` forces the JVM to stop immediately." | Other threads or contexts can keep the JVM alive. |
| "Calling `refresh()` again is how to restart Spring Boot." | Repeated refresh is not guaranteed; many contexts refresh only once. |
| "Enabling graceful shutdown guarantees every request/job finishes." | Depends on time limits and each component's stop implementation. |
| "A bean not implementing `Lifecycle` also receives stop." | Normally it receives no stop callback; it still gets destroy callbacks on close. |
| "`isActive()` equals having finished `ApplicationReadyEvent`." | Active can become true very early during refresh and before runners. |

## 16. Checklist for Applying in a Real Project

1. Identify **who owns** `ConfigurableApplicationContext` and who is allowed to call `close()`, avoiding closing from arbitrary request layers.
2. Observe `isActive()` and `isRunning()` at the right moments, but never substitute those two flags for readiness probes.
3. Inventory beans implementing `Lifecycle`/`SmartLifecycle`, especially listeners, schedulers, consumers, and web servers.
4. Check `isAutoStartup()` and `getPhase()`; do not assume every bean auto-starts the same way.
5. When writing `stop(Runnable)`, guarantee the callback is called **after** stopping finishes.
6. Configure shutdown timeouts, monitor cleanup callbacks, and avoid unbounded I/O work inside listeners.
7. Use `@PreDestroy`/destroy methods to release bean-owned resources when the context closes.
8. Avoid calling `refresh()`/`start()` to "revive" a closed context.
9. For web services, cross-check readiness, liveness, HTTP server, errors, and deployment deadlines during startup/shutdown.
10. When analyzing incidents, record event milestones (`ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent`, `ContextClosedEvent`) and root exceptions rather than guessing from one boolean.

## 17. Summary Model to Remember

**Active** indicates the context is in a lifecycle state permitting container operations; **running** indicates the lifecycle processor is operating managed components; **closed** indicates the context has finished closing and destroying beans. The three states are closely related yet **not interchangeable**.

```text
refresh succeeds -> active
lifecycle processor starts -> running
stop -> running=false, active remains true
start -> running=true, active remains true
close -> destroy + active=false, running=false

HTTP ready/healthy? -> check readiness/liveness/server separately
```

The single most important point for working safely with Spring Boot: **`stop()` and `close()` are not equivalent; `isActive()` and `isRunning()` are not equivalent; neither is equivalent to readiness**.

## Official Documentation

- [Spring Framework 6.1 — ConfigurableApplicationContext: refresh, close, isActive, Lifecycle](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [Spring Framework 6.1 — AbstractApplicationContext: isActive/isRunning and closing process](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [Spring Framework 6.1 — DefaultLifecycleProcessor: onRefresh, onClose, start, stop, and phase](https://docs.spring.io/spring-framework/docs/6.1.7/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html)
- [Spring Framework 6.1 — Lifecycle and SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/context/Lifecycle.html)
- [Spring Framework — Customizing the Nature of a Bean (Lifecycle, SmartLifecycle)](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Boot 3.3 — SpringApplication Events, Runners, Liveness, Readiness](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
