# SmartLifecycle and Auto-Startup on ApplicationContext Refresh

**Module:** Spring Boot Application Runtime → **SmartLifecycle**. This lesson explains how Spring Framework uses `LifecycleProcessor` to automatically call `SmartLifecycle.start()` during `ApplicationContext.refresh()`, the difference between bean initialization and starting resources, the `isAutoStartup()`/`getPhase()` rules, stopping via `stop(Runnable)`, and how to verify ordering with an executable Spring Boot application.

**Example environment:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Spring MVC, Maven. When using Spring Boot 4.x or Spring Framework 7, cross-check APIs and configuration against the actual version. All lifecycle demonstration code lives in a locally runnable project; it does not open real consumers, brokers, or production resources.

## 1. Learning objectives

After completing this lesson, learners will be able to:

1. Distinguish **bean created**, **bean finished initialization**, **lifecycle component running**, and **application ready**.
2. Explain the relationship `Lifecycle` → `SmartLifecycle` → `LifecycleProcessor` → `DefaultLifecycleProcessor`.
3. Point out that the `LifecycleProcessor.onRefresh()` callback happens at the end of refresh, **before** `ContextRefreshedEvent`, and auto-starts eligible `SmartLifecycle` beans.
4. Know that `SmartLifecycle.isAutoStartup()` returns **true** by default and `SmartLifecycle.getPhase()` returns **Integer.MAX_VALUE** by default in Spring Framework 6.2.
5. Predict start order by phase (**smaller first**), stop order (**larger first**), and the impact of `depends-on`.
6. Implement `start()`, `stop()`, `isRunning()`, and `stop(Runnable callback)` properly without losing the shutdown callback.
7. Observe that an `isAutoStartup=false` component already exists as a bean but is not running after refresh, and can be started manually later.
8. Read logs, HTTP state, startup failure stack traces, and shutdown evidence.
9. Know why `@Lazy` is not a reliable mechanism to prevent `SmartLifecycle` auto-startup.
10. Choose the right hook for background workers: `@PostConstruct`, `SmartInitializingSingleton`, `SmartLifecycle`, runners, and `ApplicationReadyEvent`.

**Main idea:** `SmartLifecycle` is designed for a **Spring-managed component with a start/stop lifecycle**, especially a consumer, scheduler, listener, connector, or worker. `isAutoStartup()=true` makes Spring attempt to start the component on context refresh; it does **not** mean the constructor is called a second time, does not require calling `SpringApplication.run()` twice, and does not mean every external dependency is healthy.

## 2. API contracts: Lifecycle and SmartLifecycle

### 2.1. Basic Lifecycle

Spring Framework provides:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

This is an **abbreviated interface contract representation** in documentation, not a source file to add to your project. A bean implementing `Lifecycle` can participate in start/stop commands when the context is asked to start/stop. However, a plain `Lifecycle` **does not auto-start merely because the context just refreshed** by default. To have Spring auto-start a component during refresh, use `SmartLifecycle`.

### 2.2. SmartLifecycle

`org.springframework.context.SmartLifecycle` extends `Lifecycle` and `Phased`. Key methods:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
    int getPhase();
}
~~~

This is also a **documentation representation**, not to be copied into an interface shadowing the framework's. In Spring Framework 6.2, `SmartLifecycle` already has default methods for `isAutoStartup()`, `getPhase()`, and `stop(Runnable)`. You still must implement `start()`, `stop()`, and `isRunning()` required by `Lifecycle`.

Contract table:

| API | Meaning | Notable behavior |
|---|---|---|
| `start()` | Start the component's resources/process | Should be idempotent; do not open duplicate workers |
| `stop()` | Stop the component (direct call path) | Can be used for operations/manual stop |
| `isRunning()` | Return current running state | Must reflect start/stop, not merely bean existence |
| `isAutoStartup()` | Allow auto-start on context refresh | Default **true** for `SmartLifecycle` |
| `getPhase()` | Priority by phase | Default **Integer.MAX_VALUE**; lower phases start first |
| `stop(Runnable)` | Stop under lifecycle processor coordination | **Must invoke `callback.run()` after stopping completes** |

**Special point:** When closing the context, `DefaultLifecycleProcessor` uses `stop(Runnable)` for `SmartLifecycle`; do not merely override `stop()` and assume the processor will definitely call it if you overrode `stop(Runnable)` and forgot to delegate. The default implementation of `stop(Runnable)` can call `stop()` then the callback, whereas asynchronous shutdown requires implementing it properly yourself.

### 2.3. Who is LifecycleProcessor?

`org.springframework.context.LifecycleProcessor` extends `Lifecycle` and adds two methods:

~~~java
public interface LifecycleProcessor extends Lifecycle {
    void onRefresh();
    void onClose();
}
~~~

The framework provides the `DefaultLifecycleProcessor` implementation to coordinate lifecycle beans. A standard context creates/uses an appropriate processor during refresh. `onRefresh()` lets components auto-start; `onClose()` coordinates stopping when the context closes. This same processor also handles direct calls to `ConfigurableApplicationContext.start()` or `stop()`.

In a normal Spring Boot app, **you do not need to install `LifecycleProcessor` yourself**, do not need to call `onRefresh()` yourself, and do not need to call `start()` on every auto-start component from `main()`.

## 3. When does SmartLifecycle auto-start?

Main Spring Boot sequence with a web context:

~~~text
main(args)
  |
  v
SpringApplication.run(args)
  |
  +-- prepare Environment and ApplicationContext
  +-- load bean definitions
  +-- ApplicationContext.refresh()
  |    |
  |    +-- BeanFactoryPostProcessor/BeanPostProcessor
  |    +-- create non-lazy singletons
  |    |    +-- constructor, inject dependencies
  |    |    +-- @PostConstruct / init methods
  |    |
  |    +-- finishRefresh()
  |         |
  |         +-- LifecycleProcessor.onRefresh()
  |         |    +-- find lifecycle beans
  |         |    +-- auto-start SmartLifecycle by phase
  |         |    +-- call start() for eligible beans
  |         |
  |         +-- ContextRefreshedEvent
  |
  +-- ApplicationStartedEvent
  +-- ApplicationRunner/CommandLineRunner beans
  +-- ApplicationReadyEvent
  +-- readiness state transitions to ACCEPTING_TRAFFIC
  v
application is operational
~~~

**Crucial timing:** When `DefaultLifecycleProcessor.onRefresh()` executes, the normal singleton pre-instantiation stage has already finished. The processor auto-starts `SmartLifecycle` beans whose `isAutoStartup()` returns true (and handles related dependencies). For a successfully refreshed context, synchronous `start()` callbacks in the example finish **before** `ContextRefreshedEvent`. Boot startup milestones such as `ApplicationStartedEvent` and runners come afterward.

Do not confuse:

- **Constructor runs** ⇒ object exists; does not guarantee the worker is already active.
- **`@PostConstruct` runs** ⇒ the bean finished its own init step; does not guarantee `start()` was called.
- **`start()` has run** ⇒ the lifecycle component was asked to start and usually becomes running; does not guarantee the whole application is ready.
- **`ContextRefreshedEvent` arrives** ⇒ refresh completed; Boot runners and ready still remain.
- **`ApplicationReadyEvent` arrives** ⇒ Boot reached the ready milestone; readiness state is published after this milestone in the standard flow.

For applications with lazy beans, multiple contexts, custom asynchronous startup mechanisms, or special dependencies, the creation time of certain beans may differ; trust callback contracts and direct logs rather than inferring from class scanning order.

## 4. isAutoStartup(): auto-start condition, not bean-creation condition

`isAutoStartup()` tells Spring whether to automatically call the component's `start()` during the refresh phase.

| Situation | Could the bean already be created? | Auto-start on refresh? |
|---|---|---|
| `SmartLifecycle`, default `isAutoStartup()=true` | Yes | Yes |
| `SmartLifecycle` overriding `isAutoStartup()=false` | Yes | Does not auto-start if standalone and not required by another lifecycle dependency |
| Plain `Lifecycle`, not Smart | Yes | Not by Smart auto-startup rules |
| `SmartLifecycle` manually `start()`ed after refresh | Yes | Manual start, not auto-start |
| Bean not registered in Spring container | Possibly via external `new` | Not managed by `LifecycleProcessor` |
| `@Lazy` singleton implementing `SmartLifecycle` | May still be created during lifecycle discovery | Should not use lazy as an auto-startup off switch |

Important: `isAutoStartup=false` does not mean "cannot run". It only prevents auto-starting during refresh. A direct `start()` call, `context.start()`, or a lifecycle dependency handled by the processor can still make the component run, depending on configuration. Similarly, `isAutoStartup=true` does not mean the container calls `start()` repeatedly whenever someone reads the bean; it is the processor's decision at the appropriate lifecycle phase.

**Warning about @Lazy:** The `SmartLifecycle` Javadoc explicitly states the lazy-init flag **has very limited effect** because the lifecycle processor may proactively create the bean to discover/auto-start it. If a consumer needs to be disabled by configuration, use `isAutoStartup()` or `@ConditionalOnProperty` appropriately; do not merely mark it `@Lazy` and expect it not to start.

## 5. Phase determines start/stop ordering

`SmartLifecycle` is also `Phased`: `getPhase()` returns an integer representing the phase. Phases are ordered:

- **On start:** **smaller** phase first, **larger** phase later.
- **On stop:** **reverse** order, **larger** phase first, **smaller** phase later.
- Negative phases are commonly used for infrastructure that should open early and close late; positive phases are commonly reserved for components that rely on infrastructure.
- The default of **`SmartLifecycle` is `Integer.MAX_VALUE`**, whereas beans implementing **plain `Lifecycle`** are treated by the processor as phase **0** if no separate phase representation exists.
- Values can range from `Integer.MIN_VALUE` to `Integer.MAX_VALUE`; avoid picking extreme phase values yourself when other web/server/infrastructure components need distinct ordering.

Example with two independent components, `foundation` at phase -100 and `consumer` at phase +100:

~~~text
Refresh:
LAB_START foundation phase=-100
LAB_START consumer phase=100

Shutdown:
LAB_STOP consumer phase=100
LAB_STOP foundation phase=-100
~~~

The exact order between **two beans in the same phase** should not be treated as a business guarantee; if they depend on each other, express the dependency explicitly. Spring also honors **depends-on**: the dependent bean is started **after** its dependency and stopped **before** its dependency, even when phase ordering must also be considered. Do not use phase to replace every real dependency in the system.

**Be careful with the default value:** If you leave `SmartLifecycle.getPhase()` at its default `Integer.MAX_VALUE`, the bean tends to start very late and stop very early relative to phase 0. In a web app, Spring Boot also has web server and infrastructure lifecycle components with their own phases. Do not conclude an app listener will always start before the server just because it implements `SmartLifecycle`; check each component's actual phase.

## 6. Complete Java 17 / Spring Boot 3.5 project

### 6.1. Create with Spring Initializr

Create a Maven project:

- Group: `com.example`
- Artifact: `smart-lifecycle-lab`
- Package: `com.example.smartlifecycle`
- Java: **17**
- Spring Boot: **3.5.x**
- Dependencies: **Spring Web**
- Packaging: **Jar**

Keep `pom.xml`, Maven Wrapper, and versions from Spring Initializr. Create these files:

~~~text
smart-lifecycle-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/smartlifecycle/
    SmartLifecycleLabApplication.java
    DemoLifecycle.java
    LifecycleConfiguration.java
    LifecycleController.java
  src/main/resources/application.properties
~~~

Each `public class` must reside in a file matching its name, in the same package. When compiling, use `./mvnw`/`./mvnw.cmd` with Maven dependencies; calling `javac` on individual files without the Spring classpath will fail. All four Java files below are **complete code**, not pseudocode.

### 6.2. Main class: matching events against start()

File `src/main/java/com/example/smartlifecycle/SmartLifecycleLabApplication.java`:

~~~java
package com.example.smartlifecycle;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class SmartLifecycleLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SmartLifecycleLabApplication.class, args);
    }

    @Bean
    ApplicationRunner markerRunner() {
        return args -> System.out.println("LAB_RUNNER_DONE");
    }

    @EventListener(ContextRefreshedEvent.class)
    public void contextRefreshed() {
        System.out.println("LAB_CONTEXT_REFRESHED");
    }

    @EventListener(ApplicationStartedEvent.class)
    public void started() {
        System.out.println("LAB_APPLICATION_STARTED");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void ready() {
        System.out.println("LAB_APPLICATION_READY");
    }
}
~~~

`@EventListener` methods are discovered by Spring because the main class is also a configuration bean via `@SpringBootApplication`. They only print milestones and do not control starting. The runner is called by Boot after context refresh succeeds; if a `SmartLifecycle.start()` throws an error during refresh, the runner and ready event are not reached in the default flow.

### 6.3. DemoLifecycle: complete and safe implementation for the lab

File `src/main/java/com/example/smartlifecycle/DemoLifecycle.java`:

~~~java
package com.example.smartlifecycle;

import java.util.concurrent.atomic.AtomicBoolean;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.context.SmartLifecycle;

public final class DemoLifecycle implements SmartLifecycle {

    private final String name;
    private final int phase;
    private final boolean autoStartup;
    private final boolean failOnStart;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public DemoLifecycle(
            String name,
            int phase,
            boolean autoStartup,
            boolean failOnStart) {
        this.name = name;
        this.phase = phase;
        this.autoStartup = autoStartup;
        this.failOnStart = failOnStart;
        System.out.println("LAB_CONSTRUCT " + name);
    }

    @PostConstruct
    public void initialize() {
        System.out.println("LAB_POST_CONSTRUCT " + name);
    }

    @Override
    public boolean isAutoStartup() {
        return autoStartup;
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public void start() {
        if (running.get()) {
            return;
        }

        if (failOnStart) {
            System.out.println("LAB_START_FAILURE " + name);
            throw new IllegalStateException(
                    "LAB_INTENTIONAL_START_FAILURE_" + name);
        }

        if (running.compareAndSet(false, true)) {
            System.out.println("LAB_START " + name
                    + " phase=" + phase);
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("LAB_STOP " + name
                    + " phase=" + phase);
        }
    }

    @Override
    public void stop(Runnable callback) {
        // Demo uses synchronous resources, no async I/O.
        stop();
        callback.run();
    }

    @PreDestroy
    public void destroy() {
        System.out.println("LAB_PRE_DESTROY " + name);
    }
}
~~~

**Line-by-line processing explanation:**

1. Constructor and `@PostConstruct` indicate the bean **has been created/initialized**, not that it is running.
2. `isAutoStartup()` returns a per-bean value, which can be false for components started manually by an operator.
3. `getPhase()` returns the phase for processor ordering.
4. `AtomicBoolean.compareAndSet(...)` prevents the demo from printing `LAB_START` a second time on repeated start calls on the same instance. This is only an in-JVM guard, not a replacement for external consumer or cluster coordination.
5. `stop()` sets running to false and prints the marker. It only does internal work with **no real network/resource operations**, so synchronous handling is sufficient.
6. `stop(Runnable callback)` calls `stop()` and then `callback.run()` **after stopping finishes**. Do not forget the callback, or the shutdown phase may wait until timeout.
7. `@PreDestroy` belongs to the bean destruction stage, occurring after normal lifecycle stop when closing the context; it is **distinct** from `stop()`.
8. `failOnStart` creates an intentional failure branch to observe startup failure; defaults to false.

**Practical limitation:** The `start`/`stop` methods above only flip a flag, so `isRunning()` accurately reflects the **demo's** state. A real connector should report running only after actually starting successfully; if `start()` fire-and-forgets an async task, setting the flag true right away may be premature. Design locks, state transitions, timeouts, and failure handling according to the real resource.

### 6.4. Creating 3 beans: two auto, one manual

File `src/main/java/com/example/smartlifecycle/LifecycleConfiguration.java`:

~~~java
package com.example.smartlifecycle;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LifecycleConfiguration {

    @Bean("foundation")
    DemoLifecycle foundation(
            @Value("${lab.fail.foundation:false}") boolean fail) {
        return new DemoLifecycle(
                "foundation", -100, true, fail);
    }

    @Bean("consumer")
    DemoLifecycle consumer() {
        return new DemoLifecycle(
                "consumer", 100, true, false);
    }

    @Bean("manualJob")
    DemoLifecycle manualJob() {
        return new DemoLifecycle(
                "manualJob", 200, false, false);
    }
}
~~~

- `foundation`: auto-start, phase **-100**, runs before consumer.
- `consumer`: auto-start, phase **+100**, runs after foundation.
- `manualJob`: `isAutoStartup()=false`, phase **+200**, **bean is created but does not auto-start** during a normal refresh. Afterward, a lab endpoint allows calling it manually.
- `lab.fail.foundation`: when true, makes `foundation.start()` throw an error during refresh; for experimentation only, not a production flag.
- All three beans are managed by Spring. Because the `@Bean` methods return type `DemoLifecycle implements SmartLifecycle`, the processor has full information to include them in lifecycle orchestration.

`@Configuration(proxyBeanMethods = false)` is suitable because the three factory methods do not call each other; Spring still registers standard bean definitions.

### 6.5. Controller to inspect state and manually start/stop

File `src/main/java/com/example/smartlifecycle/LifecycleController.java`:

~~~java
package com.example.smartlifecycle;

import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LifecycleController {

    private final DemoLifecycle foundation;
    private final DemoLifecycle consumer;
    private final DemoLifecycle manualJob;

    public LifecycleController(
            @Qualifier("foundation") DemoLifecycle foundation,
            @Qualifier("consumer") DemoLifecycle consumer,
            @Qualifier("manualJob") DemoLifecycle manualJob) {
        this.foundation = foundation;
        this.consumer = consumer;
        this.manualJob = manualJob;
    }

    @GetMapping("/lab/lifecycle")
    public Map<String, State> status() {
        return Map.of(
                "foundation", snapshot(foundation),
                "consumer", snapshot(consumer),
                "manualJob", snapshot(manualJob));
    }

    @PostMapping("/lab/manual/start")
    public State startManual() {
        manualJob.start();
        return snapshot(manualJob);
    }

    @PostMapping("/lab/manual/stop")
    public State stopManual() {
        manualJob.stop();
        return snapshot(manualJob);
    }

    private static State snapshot(DemoLifecycle component) {
        return new State(
                component.isRunning(),
                component.isAutoStartup(),
                component.getPhase());
    }

    public record State(boolean running,
                        boolean autoStartup,
                        int phase) {
    }
}
~~~

The controller only returns a snapshot and starts/stops **manualJob** so the lab has evidence. The two auto-start beans do not expose arbitrary start/stop endpoints. `@Qualifier` clarifies which bean is injected because three beans share the `DemoLifecycle` type; omitting the qualifier risks Spring failing to resolve dependencies safely or relying on parameter names rather than explicit rules.

**Do not deploy publicly:** POST endpoints allow affecting the lifecycle; if kept in a real project, they must have authentication, authorization, operational access control, and concurrency guards. This lesson is for local use only and involves no sensitive resources.

### 6.6. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=smart-lifecycle-lab
server.address=127.0.0.1
server.port=8080
lab.fail.foundation=false
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

`server.address=127.0.0.1` merely restricts the lab to localhost. In containers/Kubernetes, network binding must follow actual architecture. `spring.lifecycle.timeout-per-shutdown-phase=20s` makes the per-phase shutdown budget explicit. Spring Boot 3.5 enables graceful shutdown by default for supported embedded web servers; if a project overrides `server.shutdown=immediate` or uses a different version, check the active policy.

## 7. Experiment A — Auto-start on refresh

### 7.1. Running Maven Wrapper

On Linux/macOS, inside the project directory:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

The JDK must be Java 17 or a version validly configured for the project. If port 8080 is already used by another process, stop the old process before running, or change `server.port` in the lab and update the curl commands.

### 7.2. Observing logs by milestone

A **valid abbreviated sequence** of the markers:

~~~text
LAB_CONSTRUCT foundation
LAB_POST_CONSTRUCT foundation
LAB_CONSTRUCT consumer
LAB_POST_CONSTRUCT consumer
LAB_CONSTRUCT manualJob
LAB_POST_CONSTRUCT manualJob
LAB_START foundation phase=-100
LAB_START consumer phase=100
LAB_CONTEXT_REFRESHED
LAB_APPLICATION_STARTED
LAB_RUNNER_DONE
LAB_APPLICATION_READY
~~~

**Output caveat:** Constructors and `@PostConstruct` logs across the three independent beans are not guaranteed to print in that exact line-by-line order; they may interleave according to the dependency graph and bean factory ordering. Other Spring/Tomcat markers also interleave. What **must hold in the lab on a successful refresh**:

1. All three beans are created and PostConstruct runs during the bean initialization stage.
2. `LAB_START foundation` **before** `LAB_START consumer` according to phases -100 and +100.
3. Both start markers appear **before `LAB_CONTEXT_REFRESHED`**.
4. `LAB_CONTEXT_REFRESHED` precedes `LAB_APPLICATION_STARTED`, followed by runner and ready.
5. **`LAB_START manualJob` does not appear during startup** because `isAutoStartup()=false` (and no other lifecycle bean depends on it to trigger auto-start).

This is evidence distinguishing **bean created** from **started**: `manualJob` has constructor and init markers yet `isRunning()` remains false.

### 7.3. Verifying over HTTP

Open another terminal:

~~~bash
curl -i http://127.0.0.1:8080/lab/lifecycle
~~~

Expect HTTP 200 and JSON equivalent to:

~~~json
{
  "foundation": {
    "running": true,
    "autoStartup": true,
    "phase": -100
  },
  "consumer": {
    "running": true,
    "autoStartup": true,
    "phase": 100
  },
  "manualJob": {
    "running": false,
    "autoStartup": false,
    "phase": 200
  }
}
~~~

Map/JSON key ordering should not be treated as a contract; compare only the exact fields. The controller responds once Boot has started up; it provides log-independent proof that two beans are running and the manual bean has not started yet.

In PowerShell, if `curl` is an alias, use `curl.exe -i http://127.0.0.1:8080/lab/lifecycle` for standard curl output.

## 8. Experiment B — isAutoStartup=false does not forbid manual start

After `GET /lab/lifecycle` shows `manualJob.running=false`, call:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/manual/start
~~~

Expect a response body equivalent to:

~~~json
{"running":true,"autoStartup":false,"phase":200}
~~~

Console prints:

~~~text
LAB_START manualJob phase=200
~~~

This is a **direct call** to `manualJob.start()` from the controller after startup, not the framework re-running another `LifecycleProcessor.onRefresh()` pass. The `autoStartup=false` field stays unchanged because that property only specifies **whether to auto-start on refresh**; `isRunning()` is now true because it was manually started.

Call POST start a second time:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/manual/start
~~~

With the CAS-based implementation in the lab, no second `LAB_START manualJob` marker appears and the response still shows `running=true`. That is idempotency of `start()` **designed by us**, not a guarantee that every third-party `SmartLifecycle` is safe under duplicate calls.

Continue:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/manual/stop
curl -i http://127.0.0.1:8080/lab/lifecycle
~~~

Expect `manualJob.running=false` and log:

~~~text
LAB_STOP manualJob phase=200
~~~

If you want to see `manualJob` stopped automatically by the lifecycle processor when the context closes, **start it again and keep it running** until stopping the app (next section). An `autoStartup=false` component that is **currently running** still belongs to the lifecycle set that must stop when the context closes.

### 8.1. Comparing direct start() call vs. context.start()

- `manualJob.start()` affects only the single object called by code; it does not walk through all context phases.
- `ConfigurableApplicationContext.start()` delegates to the lifecycle processor to coordinate **lifecycle beans**; this can include beans that did not auto-start on refresh. Be careful because this is a context-level operation and should not be called from a public controller.
- `LifecycleProcessor.onRefresh()` is a special callback of the refresh stage; Spring invokes it automatically, not as an operational endpoint.
- `SpringApplication.run()` creates/refreshes the context for a startup run; it should **not** be called again just to start a paused job.

## 9. Experiment C — Phased stop and callback

Ensure `manualJob` **is running** via POST start, then stop the application process using Ctrl+C in the terminal running the JAR or Spring Boot Maven plugin. On supported environments, a valid SIGTERM also triggers shutdown hooks.

Expect the key stop markers of the three beans:

~~~text
LAB_STOP manualJob phase=200
LAB_STOP consumer phase=100
LAB_STOP foundation phase=-100
~~~

This is the **relative phase order among the three lab components**. Spring/Boot events and web server shutdown logs can interleave; do not compare the entire stdout byte-for-byte. `@PreDestroy` for each bean is called during destruction after normal lifecycle stop; the relative order among individual destroy markers does not necessarily match phase order.

If `manualJob` was already **stopped** when the context closed, there will be no second stop marker for it; that is the correct outcome of `isRunning()`. Do not claim the framework missed a callback just because `LAB_STOP manualJob` is absent when it was not running.

### 9.1. Why is stop(Runnable callback) so important?

In Spring Framework, `DefaultLifecycleProcessor` can stop beans within the same phase and wait for the confirmation callback as each bean finishes. For an asynchronous task, `stop(Runnable)` allows the process to stop asynchronously and then signal completion:

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            // Stop consumer, stop accepting new jobs,
            // handle in-flight work within deadline.
            shutdownConsumerSynchronously();
        } finally {
            callback.run();
        }
    });
}
~~~

This is an **illustrative snippet** requiring a suitable `executor` and a `shutdownConsumerSynchronously()` definition; do not drop it straight into the sample project without those resources. The callback is invoked in `finally` once stop work has been **attempted to completion or failure**, avoiding blocking the lifecycle processor indefinitely due to a missed signal. In production systems, you also need to record errors, failed-to-stop state, and timeout policy; `callback.run()` alone does not prove every resource was freed.

**Very dangerous bug:** Implementing `stop(Runnable)` by calling `stop()` and **forgetting `callback.run()`**. The processor will keep waiting for the shutdown phase until timeout. This can cause a Pod to be killed when `terminationGracePeriodSeconds` expires even though business work has already stopped.

Do not invoke the callback **before** stopping has truly completed; if the callback arrives early, Spring may stop another dependency while the component is still processing in-flight messages.

### 9.2. Shutdown phase timeout

Spring Boot has the property:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

This timeout bounds the wait **per shutdown phase** during lifecycle processing; it is not a container-wide deadline, not a per-request maximum duration, and not synonymous with Kubernetes `terminationGracePeriodSeconds`. With multiple phases, total shutdown time can exceed a single phase timeout.

Spring Framework 6.2 allows `DefaultLifecycleProcessor` to configure distinct timeouts for specific phases. In the lab there is no need to override the processor; the Boot property above suffices to demonstrate a common operational setting. For real systems, measure consumer stop time, committing offsets/acks, draining workers, and graceful server shutdown before choosing a value.

### 9.3. Interaction with graceful web server shutdown

In Spring Boot 3.5, graceful shutdown is enabled by default for supported embedded web servers. This happens when closing the context, at an early phase in stop order (corresponding to a high phase), to stop accepting new requests while letting in-flight requests finish within the timeout. Therefore:

- Do not pick an overly high phase for a worker if you expect the server to still accept requests throughout that worker's stop.
- Do not assume a single bean's `SmartLifecycle.stop()` is equivalent to `context.close()` or blocks HTTP by itself.
- During context shutdown, Spring coordinates the web server and lifecycle components according to phases and dependencies.
- SIGKILL or JVM `halt` does not guarantee stop callbacks or `@PreDestroy` will run.

## 10. Experiment D — An error in start() blocks refresh

Stop the app normally and package the JAR:

~~~bash
./mvnw clean package
java -jar target/smart-lifecycle-lab-0.0.1-SNAPSHOT.jar --lab.fail.foundation=true
~~~

On Windows, run `./mvnw.cmd clean package` before running. The JAR name is only the default if artifact/version match `smart-lifecycle-lab` and `0.0.1-SNAPSHOT`; if the version differs, use the actual filename inside `target/`.

Because `foundation` has `isAutoStartup=true` and phase -100, `DefaultLifecycleProcessor.onRefresh()` will call `foundation.start()` during refresh. With `failOnStart=true`, the console shows the marker:

~~~text
LAB_START_FAILURE foundation
~~~

And the stack trace contains:

~~~text
LAB_INTENTIONAL_START_FAILURE_foundation
~~~

Expected result:

1. All three beans may already have been created and run `@PostConstruct`, yet that does **not** mean context refresh succeeded.
2. `foundation.start()` throws an error, and startup fails during the lifecycle phase.
3. `LAB_CONTEXT_REFRESHED`, `LAB_APPLICATION_STARTED`, `LAB_RUNNER_DONE`, and `LAB_APPLICATION_READY` do not appear during **this failed startup run**.
4. `LAB_START consumer` usually does not appear because the earlier phase failed; Spring may begin cleaning up already-created components.
5. The process exits with a failure status; do not treat the app as ready even if the log shows partial embedded server information.

This is not a constructor or `@PostConstruct` error. The stack trace must be read down to the root cause in `start()`. Do not blame ports/networking when the actual message is the intentional failure marker.

To recover, run again **without passing** `--lab.fail.foundation=true` or pass `--lab.fail.foundation=false`. Do not abandon `SmartLifecycle`, and do not throw exceptions out indiscriminately in production if an external failure is transient and a valid degraded-operation policy exists.

## 11. Choosing the right hook for the purpose

| Hook/API | When it runs | Good for | Not good for |
|---|---|---|---|
| Constructor | When Spring creates the object | Receiving dependencies, establishing invariants | Starting long-lived threads without a stop mechanism |
| `@PostConstruct` | When **the bean itself** has been injected | Lightweight configuration checks | Running long tasks, opening subscribers needing stop |
| `InitializingBean.afterPropertiesSet()` | Bean's own init callback | Setup depending on bean properties | Waiting for all singletons and web server ready |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | After normal singleton pre-instantiation stage | Building registries from existing singletons | Managing start/stop pairs, stop callbacks |
| `SmartLifecycle.start()/stop(...)` | When LifecycleProcessor auto-starts on refresh or explicitly started/stopped | Consumers, schedulers, workers, connectors with a lifecycle | Replacing business request/transaction semantics |
| `ContextRefreshedEvent` | After the context's lifecycle `onRefresh()` | Knowing the context refreshed | Assuming runners have already finished |
| `ApplicationRunner` / `CommandLineRunner` | After refresh, before ready | Post-context tasks that must finish before ready | Self-managed long-running start/stop pairs |
| `ApplicationReadyEvent` | After runners | Recording that Boot completed startup | Starting work required before ready without a readiness policy |
| `@PreDestroy` | When the bean is destroyed | Final cleanup, releasing resources | Coordinating structured phased shutdown |

### 11.1. SmartLifecycle vs SmartInitializingSingleton

These two interfaces are often confused because both start with "Smart" and occur around bootstrap:

- `SmartInitializingSingleton` has a single method `afterSingletonsInstantiated()` after singleton pre-instantiation; suitable for validation/registry building during the init stage.
- `SmartLifecycle` has `start()`, `stop()`, and running state; managed by `LifecycleProcessor` during refresh, context start/stop, and close.
- `SmartInitializingSingleton` has no phases or shutdown callbacks; `SmartLifecycle` supports phases and asynchronous stopping.
- If you need both registry building and a consumer worker, you can use separate beans to separate responsibilities or combine them under control, without implementing every interface for a small task.

### 11.2. Is @Scheduled the same as SmartLifecycle?

`@Scheduled` declares a task triggered on a schedule when scheduling infrastructure is enabled (for example `@EnableScheduling`); it is not an arbitrary `start()` call on a `SmartLifecycle` you wrote. Spring's scheduler/task executor has its own lifecycle and phase. If a worker needs pausing, draining, connection switching, or exception coordination, inspect the lifecycle of the scheduler or consumer in use rather than manually mixing multiple phase-unaware mechanisms.

### 11.3. Real consumers and message brokers

With RabbitMQ/Kafka/JMS, the framework or library usually provides a listener container implementing `SmartLifecycle` or an equivalent mechanism. **Prefer configuring that container directly** (`autoStartup`, `phase`, `concurrency`, `ack`, `pause`/`resume`, `shutdown timeout`) instead of writing a custom `SmartLifecycle` wrapper that calls the container's `start`/`stop` again. Having two owners for the same resource increases the risk of double start or double stop.

## 12. Production operational pattern: designing a clear state machine

A real `SmartLifecycle` should have distinct states:

~~~text
NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED
                   |
                   +-> FAILED
~~~

`isRunning()` should generally be true when the component has started and is actually capable of doing work; exact semantics depend on the resource type. Several principles apply:

1. **Idempotent start:** repeated calls do not spawn duplicate threads/consumers; if already STARTING, explicitly handle wait/ignore/error.
2. **Idempotent stop:** calling stop when not running does not raise errors; stopping multiple times does not double-close resources.
3. **Avoid deadlocks:** do not block `start()` waiting for a bean or callback that only runs after `ContextRefreshedEvent`. Since `start` runs **before** that event, waiting indefinitely hangs refresh.
4. **Timeouts:** every network operation has time bounds and a retry policy; do not stall startup in phase -100 indefinitely.
5. **Failure semantics:** if startup fails, decide whether to throw and fail startup or remain in degraded mode per readiness policy; never always report `running=true` when no connection exists.
6. **Dependencies:** start infrastructure before workers, stop workers before infrastructure; use explicit phases and dependencies.
7. **Resource cleanup:** `stop` must stop accepting new work and finish/mark in-flight work; `@PreDestroy` is the final cleanup layer, not a replacement for the phase coordinator.
8. **Callback termination:** when `stop(Runnable)` is called, the callback must fire after shutdown completion or best-effort cleanup with error logging.
9. **Observability:** log/record `start_requested`, `started`, `stop_requested`, `stopped`, `failure`, and duration events; do not log secrets.
10. **Multi-replica:** `SmartLifecycle` coordinates **within one context/process**, not guaranteeing only a single consumer instance across the cluster; for cluster-wide singletons, use leader election, broker consumer groups, distributed locks, or an appropriate mechanism.

Any custom background thread should be managed by an executor with a lifecycle and shutdown policy; do not run `new Thread(...).start()` in a constructor and forget cleanup.

## 13. Special cases and common misconceptions

### 13.1. "Once the bean is created, start has already run"

**False.** `manualJob` in the lab has constructor and `@PostConstruct` markers, yet `isRunning=false` until POST start is called. Bean initialization and lifecycle startup are two different concepts.

### 13.2. "SmartLifecycle auto-starts after ApplicationReadyEvent"

**False in the default flow.** `LifecycleProcessor.onRefresh()` is called **before `ContextRefreshedEvent`**, while Boot started/runner/ready come later. Therefore do not write `start()` to wait for an `ApplicationReadyEvent` to be processed first if the ready listener must run on the same startup thread.

### 13.3. "isAutoStartup=false means it can never run"

**False.** It only disables auto-starting on refresh. Code can call `start()` directly, or the lifecycle processor can start it in other cases, including explicit context start or lifecycle dependencies.

### 13.4. "@Lazy definitely prevents SmartLifecycle from being created on refresh"

**False.** The Javadoc states lazy-init has limited effect because the processor discovers lifecycle beans to manage start/stop. To disable by profile/property, use conditional registration or `isAutoStartup`.

### 13.5. "Without overriding getPhase, phase=0"

**False for modern `SmartLifecycle`.** The default is `Integer.MAX_VALUE`, unlike phase 0 typically used for plain `Lifecycle`. If you want explicit dependency ordering, override `getPhase()`.

### 13.6. "Higher bean phase means earlier start"

**False.** On start: smaller numbers first. On stop: larger numbers first. However, `depends-on` relationships can prioritize a dependency ahead of its dependent on start.

### 13.7. "Overriding stop() is enough even if stop(Runnable) does not invoke the callback"

**False.** If you override `stop(Runnable)`, the processor uses it and requires the callback after stopping completes; forgetting the callback can delay shutdown until timeout.

### 13.8. "Stop callback always means all resources closed successfully"

**Not necessarily.** The callback signals completion of the stop processing stage to the processor. If an exception or timeout occurred in external infrastructure, you must log state/cleanup, evaluate retries, and respect deadlines; do not treat the callback as blind proof of business success.

### 13.9. "Calling context.refresh() again will restart the job"

**Do not do this.** `SpringApplication` already coordinates refresh. Some contexts do not allow re-refreshing; the right approach is calling the component's `start()` or `context.start()` when semantics fit, not using refresh as an operational command.

### 13.10. "A SmartLifecycle guarantees only one consumer system-wide"

**False.** Each replica/JVM/ApplicationContext can create and auto-start its own instance. Ensuring a single consumer cluster-wide requires out-of-process coordination, not `getPhase()`.

## 14. Diagnostic troubleshooting table

| Symptom | Hypothesis to check | Verification steps |
|---|---|---|
| `LAB_START foundation` missing | Bean not registered, `isAutoStartup=false`, refresh failed before onRefresh | Check bean definitions, error logs, and properties |
| Bean ran PostConstruct yet not running | Auto-start disabled or onRefresh not reached yet | Inspect `isAutoStartup()`, phase, event markers |
| `start()` ran but `ContextRefreshedEvent` missing | A later-phase component threw an exception or start hung | Read stack trace, latest phase, timeout |
| Manual job auto-started unexpectedly | Another Lifecycle bean depends on it or app called `context.start()` | Check dependencies, `start()` calls, logs |
| Start order reversed from expectation | Wrong `getPhase()`; dependency override; misread instance | Log each bean's phase and identity |
| Shutdown waits until full timeout | `stop(Runnable)` didn't invoke callback, callback too late, or task didn't stop | Log phase stop begin/end/callback; measure timeout |
| `stop()` not called on SmartLifecycle | Processor called `stop(Runnable)`; custom method failed to delegate | Read `stop(Runnable)` implementation |
| Consumer still takes jobs while app closing | Stop phase, race, broker ack/pause wrong | Inspect order vs. infrastructure, in-flight policy |
| Startup fails in `start()` | Resource connection error or component exception | Root `Caused by`, property, marker |
| `@Lazy` bean still created early | LifecycleProcessor needs to discover SmartLifecycle | Use `isAutoStartup=false` / conditional |
| Ready arrived yet consumer not running | Component disabled auto-start or swallowed failure | Compare `isRunning()` API with business health/readiness |
| Spring Boot stops slower than one phase timeout | Multiple phases and non-lifecycle shutdown work | Measure each phase and total termination budget |
| Two listeners/consumers run on two replicas | Auto-start is per context, not cluster singleton | Check pod count, broker group, coordinator |
| HTTP test cannot reach `/lab/lifecycle` | Port in use, loopback/container bind, wrong path | Read port logs, `server.address`, curl |
| SIGKILL used and no stop marker appears | Process was forcefully killed | Test with Ctrl+C/SIGTERM; do not infer a lifecycle bug |

## 15. Exercises with acceptance criteria

### Exercise A — Confirm auto-start on refresh

Run the app with defaults and record the markers `LAB_START foundation phase=-100`, `LAB_START consumer phase=100`, `LAB_CONTEXT_REFRESHED`. Conclude when the order matches: components are auto-started during refresh **before** the context publishes the refresh event.

### Exercise B — isAutoStartup=false

Use `GET /lab/lifecycle` to show `manualJob.running=false` while the bean already has its constructor marker. Call `POST /lab/manual/start` and observe `running=true`. Call `POST /lab/manual/stop` and observe `running=false`. Repeat POST start to verify idempotency.

### Exercise C — Phase and stop callback

Ensure all three components are running, then stop the JVM gracefully. Compare the order `LAB_STOP manualJob` → `LAB_STOP consumer` → `LAB_STOP foundation`. Read `stop(Runnable)` and explain why the callback must be invoked after `stop()` in the demo.

### Exercise D — Start error during refresh

Run the JAR with `--lab.fail.foundation=true`. Confirm the root message `LAB_INTENTIONAL_START_FAILURE_foundation` and the absence of ready. Explain why having executed `@PostConstruct` does not mean refresh succeeded. Restore the property so startup succeeds.

### Exercise E — Changing phase

In a copy of the lab, try changing `foundation.getPhase()` from -100 to 300 (by modifying the bean constructor argument) while keeping `consumer.getPhase()=100`. Record the new start order if the two beans are independent: `consumer` phase=100 before `foundation` phase=300. Analyze why placing `foundation` after `consumer` is dangerous **if the consumer actually depends on that infrastructure**, and fix the design using valid phase/depends-on.

### Exercise F — Designing a production worker

Describe a background consumer with asynchronous start/stop and callback. Write a checklist: open connection, register handler, confirm running, stop accepting new messages, finish/roll back in-flight work within timeout, close connection, invoke callback, update readiness. You do not need a real broker if environment/credentials are unavailable; what matters is the contract and evidence.

### Summary table of expectations

| Practice task | Condition | Evidence | Lesson |
|---|---|---|---|
| Normal startup | 2 auto + 1 manual | 2 STARTs before refreshed, manual running=false | Auto-start is conditional |
| Manual lifecycle | POST manual start/stop | running true then false | isAutoStartup does not forbid manual |
| Graceful stop | 3 running | Stop in phase order 200,100,-100 | Stop reverses start |
| Startup failure | fail.foundation=true | Start failure, no ready | Start is part of refresh |
| Phase inversion | Explicit phase change | Reversed START order | Phase is an ordering contract |
| Lazy bean | Inspect interface/Javadoc | Lazy flag is insufficient to disable auto-start | Use the right control |

## 16. Completion checklist

- [ ] Can explain the methods of `Lifecycle` and `SmartLifecycle`.
- [ ] Know that `LifecycleProcessor.onRefresh()` auto-starts `SmartLifecycle` when context refreshes.
- [ ] Know default `isAutoStartup=true` and default phase `Integer.MAX_VALUE` (Framework 6.2).
- [ ] Distinguish bean creation/`@PostConstruct` from running.
- [ ] Observed the 2 auto beans starting in phase order -100 then +100 before `ContextRefreshedEvent`.
- [ ] Observed `manualJob` created without auto-starting when `isAutoStartup=false`.
- [ ] Can call the HTTP endpoints to read and change `manualJob` state.
- [ ] Know the rule that higher-phase stop runs before lower-phase stop, accounting for `depends-on`.
- [ ] Understand the meaning of `stop(Runnable callback)` and the consequence of forgetting the callback.
- [ ] Understand why `@Lazy` does not reliably turn off lifecycle auto-start.
- [ ] Distinguish `SmartInitializingSingleton`, `@PostConstruct`, runners, and `SmartLifecycle`.
- [ ] Can trigger an intentional `start()` failure and analyze startup failure.
- [ ] Can state the limits of phase shutdown timeout and graceful web server stop.
- [ ] Do not use `SmartLifecycle` as a cluster-wide singleton or business transaction guard.

## 17. Official documentation

1. Spring Framework 6.2 — `SmartLifecycle` Javadoc, auto-start/phase defaults, stop callback: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
2. Spring Framework 6.2 — Bean lifecycle, startup/shutdown callbacks, and phases: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
3. Spring Framework 6.2 — `DefaultLifecycleProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
4. Spring Framework 6.2 — `LifecycleProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/LifecycleProcessor.html
5. Spring Boot 3.5 — Application lifecycle and events: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
6. Spring Boot 3.5 — Graceful shutdown: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html

**Summary:** When `ApplicationContext` refreshes, `LifecycleProcessor` automatically starts `SmartLifecycle` beans that require auto-start, according to phase and dependencies; that process completes before the refresh event in the standard flow. `isAutoStartup` decides auto-starting, `isRunning` reflects state, and `stop(Runnable)` is the callback-based stop contract. Use a demo with both auto and manual beans and verify both logs and HTTP state before applying this mechanism to real consumers or workers.