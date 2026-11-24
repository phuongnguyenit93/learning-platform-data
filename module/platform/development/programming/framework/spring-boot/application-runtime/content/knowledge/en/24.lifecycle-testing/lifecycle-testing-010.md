# Testing close, SmartLifecycle, and Resource Release Callbacks in Spring Boot

## 1. Goal: testing the **shutdown path**, not just startup

A Spring Boot application may start successfully yet fail during shutdown:
- a consumer keeps receiving messages even while the datasource is closing;
- a thread pool is not shut down, keeping the JVM alive;
- a `SmartLifecycle` forgets to call `callback.run()`, causing context closing to wait until timeout;
- a resource never receives `@PreDestroy` because it is not a Spring-managed bean;
- two beans stop in the wrong order, leaving a worker dependent on an already-released dependency;
- a test only checks that `context.close()` returns without verifying that resources were actually released.

This lesson guides designing **lifecycle tests runnable with JUnit 5**, focusing on three contracts:

1. **`ConfigurableApplicationContext.close()`**: closes the Spring context normally, emits `ContextClosedEvent`, stops lifecycle components, and destroys beans.
2. **`SmartLifecycle`**: auto-starts, stops by phase, and supports `stop(Runnable callback)` to wait for an asynchronous stop step.
3. **Resource release callbacks**: `@PreDestroy`, `DisposableBean.destroy()`, custom `@Bean(destroyMethod="...")`, `AutoCloseable`, and resource ownership.

This lesson uses **Java 17+**, **Spring Boot 3.5.16**, **Spring Framework 6.2.x**, Maven, AssertJ, and JUnit Jupiter. Part of it uses `AnnotationConfigApplicationContext` to test Spring contracts quickly without polluting the context cache; another part uses `SpringApplication` to observe real Boot behavior.

**Principle:** tests must measure an observable event with clear assertions: has the bean stopped? Was the callback invoked? Was the resource closed exactly once? Is the context still active? These checks are far more precise than merely matching a few log lines.

## 2. Lifecycle map to test

A normal successful `ApplicationContext` close follows this generalized path:

~~~mermaid
flowchart TD
  A["Context active; SmartLifecycle running"] --> B["context.close()"]
  B --> C["Publish ContextClosedEvent"]
  C --> D["LifecycleProcessor.onClose()"]
  D --> E["Stop lifecycle beans in descending phase order"]
  E --> F["SmartLifecycle.stop(callback)"]
  F --> G["Wait for callbacks within per-phase timeout"]
  G --> H["Destroy singleton beans"]
  H --> I["@PreDestroy / DisposableBean / custom destroy"]
  I --> J["Context inactive, resources released"]
~~~

This is a **model for the normal context-closing path**. A context failing mid-startup may only clean up already-created beans; `SIGKILL`/JVM crashes skip the cleanup sequence; failing or timed-out custom callbacks can leave some work incomplete. Tests must not assume every shutdown path behaves identically.

### Milestones to observe

| Milestone | API or signal | Testing significance |
| --- | --- | --- |
| Context refreshed | `context.isActive() == true` | Context is active |
| Lifecycle started | `SmartLifecycle.isRunning() == true` | Lifecycle bean auto-started |
| Closing begins | `ContextClosedEvent` | Spring started close handling |
| Phase-ordered stop | `stop(Runnable)`, `getPhase()` | Components stop in required order |
| Async stop completed | `callback.run()` | LifecycleProcessor may proceed |
| Bean destroyed | `@PreDestroy` | Container invokes callback before discarding bean |
| Custom destroy | `@Bean(destroyMethod="close")` | Closes declared resource |
| Context no longer active | `context.isActive() == false` | Do not treat context as still open |
| Process actually exits | JVM exit status | Beyond a single context close test |

`context.close()` **is not** `System.exit(...)`. A JVM can stay alive if non-daemon threads created outside Spring's lifecycle remain, even after the context is inactive.

## 3. How do close(), stop(), and JVM shutdown hooks differ?

### 3.1. context.close()

`ConfigurableApplicationContext.close()` closes the context. On a standard `AbstractApplicationContext`, it handles publishing the close event, stopping the lifecycle processor, destroying singleton beans, and releasing the bean factory.

After close, **do not keep fetching beans or sending requests** through that context. If you need a fresh environment in unit tests, create a **new context** instead of trying to re-refresh an already-closed `GenericApplicationContext`.

### 3.2. context.stop()

`ConfigurableApplicationContext.stop()` sends a **stop** signal to `Lifecycle` beans, yet **does not destroy all beans**. The context can remain active and may be `start()`ed again depending on state/implementation.

~~~java
context.stop();
boolean activeAfterStop = context.isActive();
context.start();
context.close();
~~~

This is a snippet inside a test with a properly typed `context` variable; it is not a standalone Java program. It is useful for proving "stopping workers" differs from "closing all resources".

### 3.3. JVM shutdown hook

`SpringApplication` registers a shutdown hook by default to close the context on normal JVM shutdown. However, **registering a hook does not mean running it yourself**. Hooks are not guaranteed to execute when the process receives `SIGKILL`, `Runtime.halt(...)`, or crashes severely.

**Never call `System.exit(...)` directly inside the JUnit test process** to test close; doing so can terminate the entire Maven Surefire/Test Runner. To test signals/PIDs/exit codes, spawn a **separate subprocess**, run integration tests in CI/staging, and enforce a watchdog timeout.

## 4. SmartLifecycle: critical contracts

`org.springframework.context.SmartLifecycle` extends `Lifecycle` and `Phased`. When managed by Spring, it lets components with their own start/stop (schedulers, consumers, connection listeners...) participate in the context lifecycle.

| API | Key contract |
| --- | --- |
| `start()` | Starts the component, transitioning to running once ready |
| `isRunning()` | Reports current lifecycle state |
| `stop()` | Standard `Lifecycle` stop path, generally worth supporting when called directly |
| `stop(Runnable callback)` | Callback-based stop path used by `LifecycleProcessor` for `SmartLifecycle` |
| `isAutoStartup()` | Defaults to `true` in Spring Framework 6.2; auto-starts on refresh |
| `getPhase()` | Governs start/stop ordering across phases |
| `SmartLifecycle.DEFAULT_PHASE` | `Integer.MAX_VALUE` in Spring Framework 6.2 |
| Plain `Lifecycle` not implementing `SmartLifecycle` | Generally treated as phase `0` for coordination |

**Do not guess `SmartLifecycle`'s default phase is `0`.** In Spring Framework 6.2, `SmartLifecycle`'s default phase is `Integer.MAX_VALUE`, whereas plain `Lifecycle` defaults to phase `0`. Certain infrastructure components (such as executors/schedulers) have **specific phases**, so verify the actual API/version when ordering matters.

### 4.1. Phase rules

~~~text
START: lower phase -> higher phase
STOP:  higher phase -> lower phase
~~~

Example:
- component `low` has phase `-100`;
- component `high` has phase `100`.

Expected normal order:

~~~text
start:low
start:high
... context.close() ...
stop:high
stop:low
~~~

When `depends-on` is present, the dependency graph also affects order. Never write assertions relying merely on component scan order when no explicit phase/dependency exists.

### 4.2. stop(Runnable): never forget the callback

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stopWorkers();
    } finally {
        callback.run();
    }
}
~~~

This is a snippet; `stopWorkers()` must be defined by the app. It illustrates **synchronous stop**: the callback runs after stopping finishes or after error handling. If `stopWorkers()` only sends an interrupt signal without waiting for workers to actually exit, invoking the callback right away **does not prove** work has finished draining.

For **asynchronous stop**, the callback must run **only when stopping truly reaches completion**:

~~~java
@Override
public void stop(Runnable callback) {
    stopAcceptingNewWork();

    drainExecutor.execute(() -> {
        try {
            awaitInflightWork();
        } finally {
            closeOwnedResources();
            callback.run();
        }
    });
}
~~~

This is an **illustrative snippet**, not a standalone runnable file; `drainExecutor` must exist with its own lifecycle. If the executor used for draining was already shut down beforehand, submission can be rejected. In production, provide fallback paths and bounded deadlines.

### 4.3. Per-phase timeout

Spring Boot provides the property:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=10s
~~~

Spring Boot 3.5 documents a default value of **30s**. The timeout applies **per group of `SmartLifecycle` beans sharing a phase**, not as an absolute deadline for the entire JVM.

When the callback is not invoked, the lifecycle processor can **wait until timeout and continue closing the remaining parts**. Context close completing does not confirm a component finished flushing/committing if its callback was forgotten or workers failed to cooperate.

### 4.4. Note on calling stop directly

Per `SmartLifecycle` Javadoc, `DefaultLifecycleProcessor` invokes the `stop(Runnable)` overload when closing the context; it does not necessarily invoke plain `stop()` beforehand. Thus implementing `stop()` while forgetting `stop(Runnable)` or misunderstanding default delegation can cause unexpected behavior.

## 5. @PreDestroy, destroyMethod, and callback ordering

Spring supports several resource-release hooks:

| Mechanism | Usage | Notes |
| --- | --- | --- |
| `@PreDestroy` | Method on a Spring-managed bean | Spring Boot 3 uses `jakarta.annotation.PreDestroy` |
| `DisposableBean.destroy()` | Bean implements Spring interface | Couples to Spring Framework |
| `@Bean(destroyMethod="close")` | Declares closing a bean on a factory method | Fits resources with a `close` method |
| Auto-detected destroy | On many `@Bean`s with `close`/`shutdown` or `AutoCloseable` | Depends on bean definition config; declare explicitly when testing specific behavior |
| `@EventListener(ContextClosedEvent.class)` | Receives event when context starts closing | Not proof that all resources were released |
| `SmartLifecycle.stop(callback)` | Stops live work before destruction | Does not automatically replace resource destruction |

When **the same bean** defines multiple destroy callbacks, Spring Framework specifies the order:
1. `@PreDestroy`;
2. `DisposableBean.destroy()`;
3. custom destroy method.

This lesson tests on **a single resource bean** having both `@PreDestroy` and custom `close`, so expected ordering does not depend on destruction ordering across different beans.

An object instantiated with `new` outside the container **does not automatically** receive `@PreDestroy`. A `@Lazy` bean never instantiated also does not necessarily have an instance to destroy. For prototype beans, the Spring container does not manage the full destruction lifecycle like singletons; the owner must enforce its own cleanup policy.

### Resource ownership

Explicitly specify:
- who creates the resource?
- who owns closing the resource?
- are any workers still using the resource during close?
- can a close be called idempotently multiple times?
- does the resource support timeouts/cancellation?
- must a flush/commit happen before close?

A unit test checking that `close()` was called **is insufficient** to confirm data committed cleanly to a database or broker. Those effects require integration tests at the external system boundary.

## 6. Architecture of the Java 17+ / Spring Boot 3.5.16 lab

To test **ordering** and **count invocations** of callbacks, we use an in-memory timeline recorder rather than relying on logging framework line ordering.

Project:

~~~text
lifecycle-close-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/lifecycle/
    │   ├── LifecycleLabApplication.java
    │   └── LifecycleFixtures.java
    └── test/java/com/example/lifecycle/
        ├── LifecycleCloseTest.java
        └── AsyncStopTest.java
~~~

The lab runs without a web server, database, or message broker. This keeps assertions deterministic and prevents tests from being disrupted by ports, networks, or uninitialized clients.

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-close-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and Spring TestContext via Boot's dependency management. The tests below do not need `@SpringBootTest` for every method: we explicitly create/close contexts to test the exact lifecycle.

### 6.2. LifecycleFixtures.java: recorder, lifecycle, and resource

File **`src/main/java/com/example/lifecycle/LifecycleFixtures.java`**:

~~~java
package com.example.lifecycle;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;

import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

public final class LifecycleFixtures {
    private LifecycleFixtures() {
    }

    public static final class Timeline {
        private final CopyOnWriteArrayList<String> entries =
                new CopyOnWriteArrayList<>();

        public void add(String event) {
            entries.add(event);
        }

        public List<String> snapshot() {
            return List.copyOf(entries);
        }
    }

    public static final class PhaseProbe
            implements SmartLifecycle {

        private final Timeline timeline;
        private final String name;
        private final int phase;
        private final AtomicBoolean running =
                new AtomicBoolean(false);

        public PhaseProbe(
                Timeline timeline, String name, int phase) {
            this.timeline = timeline;
            this.name = name;
            this.phase = phase;
        }

        @Override
        public int getPhase() {
            return phase;
        }

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                timeline.add("start:" + name);
            }
        }

        @Override
        public void stop() {
            if (running.compareAndSet(true, false)) {
                timeline.add("stop:" + name);
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
    }

    public static final class ResourceProbe {
        private final Timeline timeline;
        private final AtomicInteger preDestroyCount =
                new AtomicInteger();
        private final AtomicInteger closeCount =
                new AtomicInteger();

        public ResourceProbe(Timeline timeline) {
            this.timeline = timeline;
        }

        @PreDestroy
        public void beforeDestroy() {
            preDestroyCount.incrementAndGet();
            timeline.add("predestroy:resource");
        }

        public void close() {
            closeCount.incrementAndGet();
            timeline.add("close:resource");
        }

        public int getPreDestroyCount() {
            return preDestroyCount.get();
        }

        public int getCloseCount() {
            return closeCount.get();
        }
    }

    public static final class CloseObserver {
        private final Timeline timeline;

        public CloseObserver(Timeline timeline) {
            this.timeline = timeline;
        }

        @EventListener
        public void handle(ContextClosedEvent event) {
            timeline.add("event:close");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Timeline timeline() {
            return new Timeline();
        }

        @Bean("low")
        PhaseProbe low(Timeline timeline) {
            return new PhaseProbe(timeline, "low", -100);
        }

        @Bean("high")
        PhaseProbe high(Timeline timeline) {
            return new PhaseProbe(timeline, "high", 100);
        }

        @Bean(destroyMethod = "close")
        ResourceProbe resource(Timeline timeline) {
            return new ResourceProbe(timeline);
        }

        @Bean
        CloseObserver closeObserver(Timeline timeline) {
            return new CloseObserver(timeline);
        }
    }
}
~~~

**Design explanation:**

- `Timeline` uses `CopyOnWriteArrayList` to also support the asynchronous stop case later; `snapshot()` returns an immutable list.
- Both `PhaseProbe`s have phases `-100` and `100`; Spring Framework 6.2's default `isAutoStartup()` is `true`, so they start on context refresh.
- `stop(Runnable)` invokes `stop()` inside `try` and runs the callback in `finally`; this is a short synchronous stop with no I/O.
- `ResourceProbe` has **two** callbacks to measure exact ordering: `@PreDestroy` and `close()`.
- `@Bean(destroyMethod="close")` instructs Spring to call custom `close` on the resource bean. We do not rely on destroy method inference.
- `CloseObserver` listens to `ContextClosedEvent`; it merely appends an entry without depending on a logger.
- Beans use default singleton scope and eager instantiation, suited for testing destruction.
- Timeline records have fixed names; with no random timestamps, tests can assert deterministically.

### 6.3. LifecycleLabApplication.java: running real Boot and closing the context

File **`src/main/java/com/example/lifecycle/LifecycleLabApplication.java`**:

~~~java
package com.example.lifecycle;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

public final class LifecycleLabApplication {
    private LifecycleLabApplication() {
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(
                LifecycleFixtures.Config.class);

        application.setWebApplicationType(
                WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        LifecycleFixtures.Timeline timeline;

        try (ConfigurableApplicationContext context =
                application.run(args)) {

            timeline = context.getBean(
                    LifecycleFixtures.Timeline.class);

            System.out.println("ACTIVE_BEFORE_CLOSE="
                    + context.isActive());

            LifecycleFixtures.PhaseProbe high =
                    context.getBean(
                            "high",
                            LifecycleFixtures.PhaseProbe.class);

            System.out.println("HIGH_RUNNING="
                    + high.isRunning());
        }

        System.out.println("EVENTS=" + timeline.snapshot());
    }
}
~~~

**Why use `SpringApplication` with an explicit `@Configuration`?** This is a minimal lab configuration without needing `@SpringBootApplication` to scan the entire project. Spring Boot still bootstraps the context and lifecycle like a normal app; there is no web server keeping the process alive after `main` returns.

`try-with-resources` invokes `context.close()` on exiting the block. The `timeline` variable retains an external reference to read milestones **after the context has closed**; in production you should not keep calling bean methods after close, yet here it is a simple recorder object holding no external resources and serving tests only.

### Build and run

In the directory containing `pom.xml`:

~~~bash
mvn -q test
mvn -q -DskipTests package
java -jar target/lifecycle-close-lab-0.0.1-SNAPSHOT.jar
~~~

Lines **proactively printed by the program** in expected order:

~~~text
ACTIVE_BEFORE_CLOSE=true
HIGH_RUNNING=true
EVENTS=[start:low, start:high, event:close, stop:high, stop:low, predestroy:resource, close:resource]
~~~

Depending on logging config, framework log lines may appear too. Never match raw stdout if log levels differ. The `EVENTS` line is recorder data designed by our code; the Spring container only provides coordination to invoke lifecycle methods.

### Output interpretation

1. `start:low` before `start:high`: starts in ascending phase order.
2. `event:close`: listener received `ContextClosedEvent`.
3. `stop:high` before `stop:low`: stops in descending phase order.
4. `predestroy:resource`: `@PreDestroy` was called.
5. `close:resource`: custom destroy method was called after `@PreDestroy` on the same bean.
6. Output does not individually tell whether an HTTP request drained or database data committed: the lab uses no such resources.

## 7. JUnit 5: testing close, phases, and invoking callbacks exactly once

File **`src/test/java/com/example/lifecycle/LifecycleCloseTest.java`**:

~~~java
package com.example.lifecycle;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class LifecycleCloseTest {

    @Test
    void closeStopsByDescendingPhaseThenDestroysResource() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        LifecycleFixtures.Config.class)) {

            LifecycleFixtures.Timeline timeline =
                    context.getBean(
                            LifecycleFixtures.Timeline.class);

            LifecycleFixtures.ResourceProbe resource =
                    context.getBean(
                            LifecycleFixtures.ResourceProbe.class);

            LifecycleFixtures.PhaseProbe low =
                    context.getBean(
                            "low",
                            LifecycleFixtures.PhaseProbe.class);

            LifecycleFixtures.PhaseProbe high =
                    context.getBean(
                            "high",
                            LifecycleFixtures.PhaseProbe.class);

            assertThat(context.isActive()).isTrue();
            assertThat(low.isRunning()).isTrue();
            assertThat(high.isRunning()).isTrue();

            assertThat(timeline.snapshot())
                    .containsSubsequence(
                            "start:low", "start:high");

            context.close();

            assertThat(context.isActive()).isFalse();
            assertThat(low.isRunning()).isFalse();
            assertThat(high.isRunning()).isFalse();

            List<String> afterClose = timeline.snapshot();

            assertThat(afterClose).containsSubsequence(
                    "event:close",
                    "stop:high",
                    "stop:low",
                    "predestroy:resource",
                    "close:resource");

            assertThat(resource.getPreDestroyCount())
                    .isEqualTo(1);
            assertThat(resource.getCloseCount())
                    .isEqualTo(1);

            // AbstractApplicationContext.close()
            // does not re-run full destruction multiple times.
            context.close();

            assertThat(timeline.snapshot())
                    .containsExactlyElementsOf(afterClose);
            assertThat(resource.getPreDestroyCount())
                    .isEqualTo(1);
            assertThat(resource.getCloseCount())
                    .isEqualTo(1);
        }
    }

    @Test
    void stopIsNotTheSameAsClose() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        LifecycleFixtures.Config.class)) {

            LifecycleFixtures.ResourceProbe resource =
                    context.getBean(
                            LifecycleFixtures.ResourceProbe.class);

            LifecycleFixtures.PhaseProbe high =
                    context.getBean(
                            "high",
                            LifecycleFixtures.PhaseProbe.class);

            context.stop();

            // stop() sends stop signal to Lifecycle;
            // context stays active and beans are not destroyed yet.
            assertThat(context.isActive()).isTrue();
            assertThat(high.isRunning()).isFalse();
            assertThat(resource.getPreDestroyCount())
                    .isZero();
            assertThat(resource.getCloseCount())
                    .isZero();

            context.start();
            assertThat(high.isRunning()).isTrue();

            // AutoCloseable in try will close the context when leaving scope.
        }
    }
}
~~~

### What do the assertions actually verify?

- `containsSubsequence` verifies **relative ordering** across key milestones without forcing all framework logs to match.
- `context.isActive()` before/after close confirms context state.
- `isRunning()` proves both lifecycle probes stopped.
- Counters prove release callbacks ran **once** on the normal close path.
- Calling `close()` twice confirms **idempotency of `AbstractApplicationContext.close()` in the lab**, without implying every resource API is inherently idempotent in all situations.
- `stopIsNotTheSameAsClose` confirms resources are not destroyed when only `context.stop()` is called and components can start again.

**Do not assert "all beans destroy in bean registration order"**: destruction order across multiple beans depends on dependency relationships and container implementation. This lesson tests explicit ordering **within one bean** and across **specified phases**.

## 8. JUnit 5: testing asynchronous SmartLifecycle.stop(Runnable)

A real-world bug is `stop(Runnable callback)` sending a stop signal and then **forgetting the callback**, forcing `LifecycleProcessor` to wait until timeout. To prove the callback matters, we build a component that completes shutdown only when the test permits; then we call `context.close()` from another thread.

File **`src/test/java/com/example/lifecycle/AsyncStopTest.java`**:

~~~java
package com.example.lifecycle;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AsyncStopTest {

    static final class AsyncStopProbe implements SmartLifecycle {
        private final LifecycleFixtures.Timeline timeline;
        private final CountDownLatch stopEntered =
                new CountDownLatch(1);
        private final CountDownLatch allowStopToComplete =
                new CountDownLatch(1);
        private final AtomicBoolean running =
                new AtomicBoolean(false);

        AsyncStopProbe(LifecycleFixtures.Timeline timeline) {
            this.timeline = timeline;
        }

        @Override
        public void start() {
            running.set(true);
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
        public void stop() {
            running.set(false);
        }

        @Override
        public void stop(Runnable callback) {
            timeline.add("stop:requested");
            stopEntered.countDown();

            Thread thread = new Thread(() -> {
                try {
                    allowStopToComplete.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    running.set(false);
                    timeline.add("stop:completed");
                    callback.run();
                }
            }, "async-stop-lab");

            thread.setDaemon(true);
            thread.start();
        }

        boolean awaitStopStart(long timeout, TimeUnit unit)
                throws InterruptedException {
            return stopEntered.await(timeout, unit);
        }

        void releaseStop() {
            allowStopToComplete.countDown();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AsyncConfig {

        @Bean
        LifecycleFixtures.Timeline timeline() {
            return new LifecycleFixtures.Timeline();
        }

        @Bean
        AsyncStopProbe asyncStopProbe(
                LifecycleFixtures.Timeline timeline) {
            return new AsyncStopProbe(timeline);
        }

        @Bean(destroyMethod = "close")
        LifecycleFixtures.ResourceProbe resource(
                LifecycleFixtures.Timeline timeline) {
            return new LifecycleFixtures.ResourceProbe(timeline);
        }
    }

    @Test
    void closeWaitsForAsyncStopCallbackBeforeDestroy()
            throws Exception {

        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        AsyncConfig.class);

        AsyncStopProbe probe =
                context.getBean(AsyncStopProbe.class);

        LifecycleFixtures.Timeline timeline =
                context.getBean(LifecycleFixtures.Timeline.class);

        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        Future<?> closing = executor.submit(context::close);

        try {
            assertThat(probe.awaitStopStart(
                    5, TimeUnit.SECONDS)).isTrue();

            // Stop has started, yet the test has not allowed it to complete.
            assertThat(closing.isDone()).isFalse();

            probe.releaseStop();
            closing.get(10, TimeUnit.SECONDS);

            List<String> events = timeline.snapshot();

            assertThat(events).containsSubsequence(
                    "stop:requested",
                    "stop:completed",
                    "predestroy:resource",
                    "close:resource");

            assertThat(context.isActive()).isFalse();
        } finally {
            // Prevent worker from hanging forever if an assertion fails.
            probe.releaseStop();
            executor.shutdownNow();
        }
    }
}
~~~

### Why does this test depend little on timing?

- `CountDownLatch stopEntered` synchronizes so the test does not guess whether the close thread reached `stop(Runnable)`.
- `allowStopToComplete` keeps the stop path incomplete while checking `closing.isDone() == false`.
- `callback.run()` is called inside `finally` only after the worker records `stop:completed`.
- `closing.get(10, SECONDS)` guarantees the test has a **finite** wait deadline.
- `Timeline` is thread-safe so events can be read from the test thread.
- `releaseStop()` in `finally` prevents the worker from blocking forever if an assertion fails.

### Limitations to state clearly

- `Future.get(10, ...)` is the **test** deadline; `DefaultLifecycleProcessor` also has its own **per-phase** timeout. Intentionally omitting the callback triggers test failure/phase timeout rather than hanging forever.
- The illustrative component spawns a raw daemon thread solely for testing. Production code should manage worker/drain threads with timeouts, interruption, metrics, and dedicated executor lifecycles.
- If a worker hits its deadline while still holding external resources, invoking the callback in `finally` means **the stop or cancel policy completed**, not that every business operation committed.
- If a test uses a context with additional lifecycle beans, callbacks and phases must be evaluated across the entire dependency/phase graph.
- Tests should avoid long external I/O; on ultra-slow CI, adjust 5 and 10 seconds per test policy while keeping finite timeouts.

## 9. When to test with AnnotationConfigApplicationContext vs. SpringApplication?

| Testing approach | Use when | Does not automatically cover |
| --- | --- | --- |
| `new AnnotationConfigApplicationContext(Config.class)` | Fast, isolated verification of lifecycle bean contracts and destroy callbacks | Spring Boot auto-configuration, web server, external brokers |
| `new SpringApplication(Config.class).run(...)` | Need to confirm real Boot context startup/shutdown | OS signals, container PID 1, real web traffic |
| `@SpringBootTest` | Integration testing with Boot wiring/properties | Destruction callbacks inside the same test method if context stays cached |
| `@DirtiesContext` | Need TestContext to evict cache and close after test/class | Not a direct post-close assertion tool if callbacks run after the method |
| Java subprocess with TERM | Need to confirm JVM hooks, exit codes, OS signals, container behavior | Does not replace unit tests of cleanup methods |

### Why shouldn't you manually close a context injected from @SpringBootTest?

Spring TestContext **caches `ApplicationContext`s** across tests sharing the same configuration. If a test calls:

~~~java
@Autowired
ConfigurableApplicationContext context;

@Test
void stopIt() {
    context.close();
}
~~~

this is an **anti-pattern snippet** in a `@SpringBootTest` suite if other tests expect that cached context to stay active: the test can leave other methods/test classes using a closed context, causing collateral failures and execution-order-dependent results.

Instead:
- For **tests needing to observe close right inside the method**, create a dedicated `AnnotationConfigApplicationContext`/`SpringApplication` as in this project.
- For **integration tests wanting the framework to evict the context from cache**, use `@DirtiesContext` matching the desired lifecycle.
- Do not slap `@DirtiesContext` on every test mechanically: reloading contexts is expensive and can mask state leakage issues.

Example using `@DirtiesContext` at the class level:

~~~java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class IntegrationLifecycleTest {
    @Test
    void contextStarts() {
        // Test code can assert @Autowired beans are running.
        // Context will be closed by TestContext after the class.
    }
}
~~~

This is a **snippet**, requiring imports for `SpringBootTest`, `DirtiesContext`, and `Test`, plus a suitable Spring Boot main configuration in the project. It illustrates test context policy, **not** a standalone runnable file inside section 6's minimal lab without adding Boot test config. Do not rely on `@PreDestroy` having run inside the body of `contextStarts()`.

## 10. Precisely analyzing "stop callback" in tests

A proper `SmartLifecycle` must answer:

1. **When does it start?** If `isAutoStartup() == true`, Spring auto-starts it on context refresh when the bean is managed and auto-startup applies.
2. **When does it stop?** `context.stop()` or `context.close()` triggers the lifecycle processor when the component is running.
3. **Which callback path?** `stop(Runnable callback)` is used by the lifecycle processor; not solely plain `stop()`.
4. **How is completion signaled?** Call the callback strictly after stop/cleanup reaches its committed state.
5. **Called once or multiple times?** On the normal context close path, avoid duplicate stops/closes unless idempotency is designed in.
6. **What if errors/timeouts occur?** Record errors, enforce deadlines, and let the resource owner decide retry/cancel/compensation.

### Why should the callback be inside finally?

~~~java
@Override
public void stop(Runnable callback) {
    try {
        performStop();
    } finally {
        callback.run();
    }
}
~~~

This is the basic synchronous pattern. It avoids skipping the callback if `performStop()` throws an exception, yet **does not make the exception vanish** or work magically finish. Log/propagate failures appropriately. If cleanup fails severely, report degraded/failure status to monitoring even while invoking the callback so the lifecycle processor can proceed.

### When should the callback NOT be invoked immediately?

If `stop()` merely sends `interrupt()` to a worker without waiting for the worker to exit, calling `callback.run()` immediately tricks the container into believing the component stopped. Example:

~~~java
@Override
public void stop(Runnable callback) {
    worker.interrupt();
    callback.run(); // May be too early if the worker has not finished.
}
~~~

This snippet is risky if the worker still uses a DB/client that Spring is about to destroy. Use `join(timeout)`, `Future.get(timeout)`, or bounded `awaitTermination` inside an appropriate stop mechanism.

### Never invoke the callback too early or twice

If the callback runs before resources release, stop ordering can break. If invoked multiple times, lifecycle processor implementations may handle duplicate callbacks differently; never rely on the framework ignoring duplicate callbacks. Use `AtomicBoolean` or state management when multiple async completion/cancellation branches exist.

## 11. Testing real resources: executors, files, sockets, databases

### 11.1. ExecutorService

A manually created `ExecutorService` can keep **non-daemon threads** alive after context close if not shut down. Minimum tests should confirm:

- no new tasks accepted once closing starts;
- in-flight tasks are awaited or cancelled per deadline;
- `executor.isShutdown()` or `executor.isTerminated()` reaches the expected state;
- no worker threads belonging to the resource owner remain after the deadline;
- `@PreDestroy` does not close connections while workers still use them if draining first is required.

Executor management snippet:

~~~java
@PreDestroy
public void destroy() throws InterruptedException {
    executor.shutdown();

    if (!executor.awaitTermination(
            5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
}
~~~

This is a **snippet**, requiring an `executor` variable of type `ExecutorService`, importing `TimeUnit`, and proper interruption handling. `shutdownNow()` **only attempts interrupts**; it does not guarantee every task stops immediately if tasks ignore interrupts or block on I/O without timeouts.

In Spring Boot, auto-configured executors can use termination-wait policies, yet do not confuse them with arbitrary raw thread pools:

~~~properties
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=10s
~~~

These properties only affect matching Boot-managed executor infrastructure. If the app manually calls `Executors.newFixedThreadPool(...)` outside the container, manage that pool's lifecycle yourself.

### 11.2. File resources

For file streams, tests can:
- create a temp file via `@TempDir`;
- have the bean open the resource;
- close the context;
- assert the stream no longer permits writes/reads;
- assert data requiring flushing exists per contract.

Do not treat closing a file as proof all durable data was `fsync`ed to storage; that is a different level of guarantee.

### 11.3. Socket / HTTP clients

HTTP client close tests should verify:
- connection pools/resource managers closed;
- new requests are rejected after close;
- in-flight requests are handled per policy;
- no unbounded network I/O runs inside `@PreDestroy`.

Do not test against an unreliable Internet endpoint. Prefer local test servers or mock transports with short timeouts.

### 11.4. Database transactions

For databases:
- stop consumers/workers using the datasource before destroying the datasource;
- verify rollbacks/commits and connection release;
- if Testcontainers is needed, document the Docker environment, wait strategy, and cleanup;
- never infer DB commit solely from connection pool `close()` being called.

### 11.5. Message brokers

A consumer typically needs to:
1. stop receiving new messages;
2. let in-flight handlers finish or mark retries;
3. commit/ack per broker semantics;
4. close the consumer and client;
5. verify no lost/duplicated work outside at-least-once policy.

This is a messaging integration test, **not** a single `@PreDestroy` assertion.

## 12. Shutdown testing vs. startup failure

Not every initialization error traverses normal `ContextClosedEvent` and `SmartLifecycle.stop(Runnable)`. If a bean throws in `@PostConstruct` before the context finishes refreshing, Spring may destroy already-created singleton beans, yet you must not assume all lifecycle components started or a regular `ContextClosedEvent` always fires.

Therefore separate three test groups:

| Group | Action | Assertions |
| --- | --- | --- |
| Normal close | Refresh succeeds then `close()` | events, stop phases, destroy callbacks |
| Partial startup failure | A bean intentionally throws on init | initialized resources cleaned up per contract; no promise of all stop callbacks |
| Forced process termination | Subprocess hit with `SIGKILL`/OOMKill | recovery/idempotency; do not expect JVM hooks |

### Startup failure tests can use assertThatThrownBy

~~~java
assertThatThrownBy(() -> {
    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                    BrokenStartupConfig.class)) {
        // Not reached if refresh fails.
    }
}).hasRootCauseInstanceOf(IllegalArgumentException.class);
~~~

This is a **snippet**, requiring `BrokenStartupConfig` defined to throw an `IllegalArgumentException` during bean init and static importing `assertThatThrownBy`. It is a pattern for startup failure tests, **not** normal context close tests. When checking resource cleanup on partial startup, track pre-failure created resources via a separate recorder outside the failing context.

### Shutdown hooks do not run on SIGKILL

Do not write a JUnit test in the same JVM calling `Runtime.getRuntime().halt(...)` just to "verify" callbacks: it kills the test process and skips cleanup. To test behavior under `SIGTERM`/`SIGKILL`, run the app as a subprocess and observe it from an external harness. Use deadlines, cleanup, and isolated environments — never in production.

## 13. Debugging when a lifecycle test fails

### Test does not see ContextClosedEvent

Check:
- was the listener registered with Spring and the bean created;
- did the test call `close()` on the **exact same context instance**;
- is the test using a `@SpringBootTest` cached context that has not closed yet;
- did a startup error occur before the event listener was ready;
- were logs filtered, or was the recorder reset/GC'd?

Do not jump to blaming `@EventListener` if the test never closed the context.

### Test sees stop() but not stop(Runnable)

Check whether the component genuinely implements `SmartLifecycle`, whether `isRunning() == true` at stop time, and whether the test called `probe.stop()` **directly** instead of `context.close()`/`context.stop()`.

When application code calls `probe.stop()` directly, it bypasses `LifecycleProcessor`; behavior may differ from the context-closing contract.

### Test calls stop() and resources were destroyed

If the test actually called `context.close()` instead of `context.stop()`, destruction is expected. `context.stop()` by itself does not destroy the context. Check the exact API called.

### Callback not invoked: test waits until timeout

Inspect `stop(Runnable)` and verify every success/error/cancel branch invokes the callback. Check whether the drain executor still accepts tasks during shutdown, whether a worker deadlocked waiting on an already-closed resource, and whether the per-phase deadline is too short.

### Test passes on dev machine yet flakes in CI

Typical sources of flakiness:
- `Thread.sleep(100)` used instead of synchronization conditions;
- assertions running before workers had a chance to execute;
- JUnit methods running in parallel while sharing a static recorder;
- port or database container not yet ready;
- tests relying on absolute 10 ms timings;
- Spring context cache closed by another test;
- shutdown hooks running after Surefire already reported tests finished.

Use `CountDownLatch`, `Future.get(timeout)`, `awaitTermination`, and per-test contexts. When using Awaitility, use it only for genuinely eventual conditions rather than replacing synchronous design altogether.

### Test stops in the wrong order

Check:
1. `getPhase()` of each component;
2. bean dependencies and `depends-on`;
3. which components are using the executor/datasource;
4. whether one stop invokes its callback **before** its worker truly stopped;
5. whether multiple same-phase components run/stop concurrently.

For same-phase components, avoid asserting strict absolute order without explicit dependencies; the lifecycle processor may allow async stops whose callbacks finish in a different order than started.

## 14. Test evidence and guarantee boundaries

Timeline milestones are useful yet bounded:

| Observation | What can be asserted | What is not yet proved |
| --- | --- | --- |
| `event:close` | Listener invoked when context starts closing | All resources have closed |
| `stop:high` before `stop:low` | Phase ordering tested for these two probes | All other beans follow the same order |
| `stop:completed` before `predestroy:resource` | LifecycleProcessor awaited callback in test | All transactions committed |
| `predestroy:resource` | `@PreDestroy` called on managed bean | External buffers flushed cleanly |
| `close:resource` | Custom destroy method invoked | Resource implementation has no internal bugs |
| `context.isActive() == false` | Context is inactive | JVM has no remaining non-daemon threads |
| Process exit code `0` | OS saw process exit cleanly per code | No data remains needing retry |
| No Java exception | Observed test path ran without throwing | System works under all load levels |

To protect production data, add I/O integration tests, retry/idempotency tests, timeouts, and failure controls. Never write fake tests claiming "close released everything" solely because a void method was invoked.

## 15. Anti-patterns that cause false confidence

**Anti-pattern 1 — Asserting only that `context.close` throws no exception.**  
The goal is verifying callbacks/worker states/resource counters. A `close` returning after a phase timeout can still leave unstopped tasks behind.

**Anti-pattern 2 — Fixed sleep waiting for async stop.**  
`Thread.sleep(1000)` is flaky; replace with latches and futures with timeouts.

**Anti-pattern 3 — Forgetting `callback.run()`.**  
The container may wait until the phase timeout, masking resource-stop bugs and slowing deployment shutdowns.

**Anti-pattern 4 — Calling the callback before task draining finishes.**  
The container proceeds to destroy dependencies prematurely, causing "connection closed" errors in still-running workers.

**Anti-pattern 5 — Testing with `@SpringBootTest` and closing the cached context manually.**  
Other tests may receive an already-closed context; use dedicated contexts or `@DirtiesContext` appropriately.

**Anti-pattern 6 — Putting `@PreDestroy` on a `new`-ed object unregistered with Spring.**  
There is no container-managed destruction for that object.

**Anti-pattern 7 — Confusing `ContextClosedEvent` with `@PreDestroy`.**  
The event marks the **start** of closing, while `@PreDestroy` runs in the destruction phase; logging the event is not proof of cleanup.

**Anti-pattern 8 — Testing `SIGKILL` inside the same JUnit JVM.**  
It kills the runner instead of testing assertions. Use a subprocess with a watchdog in a safe environment.

**Anti-pattern 9 — Forcing every bean's phase to `MAX_VALUE`.**  
Order must follow dependencies and stopping intake before releasing resources; phases are not a blanket ordering hack for all code.

**Anti-pattern 10 — Closing the executor too early.**  
Workers may need the executor to perform cleanup, causing rejected submissions or missed completion callbacks.

**Anti-pattern 11 — Assuming `executor.shutdownNow()` forcefully kills tasks.**  
It typically only attempts interruption; uncooperative tasks can keep running.

**Anti-pattern 12 — Asserting full stdout logs with hardcoded strings.**  
Framework startup logs depend on versions and environments. Use a dedicated recorder and check required milestones.

## 16. Extending to web applications and Kubernetes

When the application is an HTTP service, add a testing layer:

- run `@SpringBootTest(webEnvironment=RANDOM_PORT)` or a subprocess with a random port;
- send a request with a barrier/latch to confirm the request actually started;
- trigger `context.close` or send `SIGTERM` from an out-of-process harness;
- measure whether in-flight requests can finish under `server.shutdown=graceful`;
- verify new traffic is rejected during draining;
- ensure background consumers/task executors stop cleanly and resource callbacks execute;
- compare total TERM→process-exit time against `terminationGracePeriodSeconds`.

In Spring Boot 3.5, graceful shutdown is enabled by default for Tomcat, Jetty, Reactor Netty, and Undertow, with new-request rejection behavior depending on the server. It executes in an **early phase** of `SmartLifecycle`; you can configure:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

**Do not confuse** HTTP graceful shutdown with all custom message consumers/workers being drained. Keep in-flight HTTP tests and `SmartLifecycle` tests independent first, then add a combined integration test confirming stop ordering with dependencies.

### Kubernetes termination

Kubernetes has its own `terminationGracePeriodSeconds`. If Java needs 20 seconds to drain yet the Pod is killed after 10 seconds, callbacks are not guaranteed to finish. `preStop` also consumes part of the termination budget. Unit tests for `@PreDestroy` do not substitute for cluster rollout scenarios with TERM, endpoint draining, and SIGKILL.

### Principle for process lifecycles

`ApplicationContext.close()` is an API within the **current process**. If code leaves a non-daemon thread alive after close, `main` can return while the process stays running. To verify the JVM actually exits, use a harness running a child process with a timeout and observe exit code/PID rather than inferring from `context.isActive()`.

## 17. Checklist for test authors

- [ ] Identify whether you are testing **stop**, **close**, **startup failure**, or **process termination**.
- [ ] Use a dedicated context for tests that must proactively call close.
- [ ] Register a thread-safe recorder and keep a reference past close when assertions need it.
- [ ] Have lifecycle beans running before testing stop.
- [ ] Specify explicit phases for components whose ordering is compared.
- [ ] Assert ascending-phase start and descending-phase stop.
- [ ] Assert `ContextClosedEvent` occurs before destruction in normal close.
- [ ] Assert `SmartLifecycle.stop(Runnable)` invoked its completion callback once stopped.
- [ ] For async stop, use latches/futures and finite timeouts rather than sleep.
- [ ] Assert `@PreDestroy` and custom destroy callbacks execute exactly once.
- [ ] Assert callback order only **within the same bean** or when dependencies/phases guarantee it.
- [ ] Assert `context.stop()` does not mean resource destruction.
- [ ] Assert `context.isActive()` turns false after close.
- [ ] If testing repeated close, specify the idempotency contract of the context/resource clearly.
- [ ] Never close cached `@SpringBootTest` contexts arbitrarily.
- [ ] Never call `System.exit`/`Runtime.halt` directly inside the JUnit runner.
- [ ] Test real resources (executors, files, DB, brokers) at the appropriate integration level.
- [ ] Keep closing deadlines explicit to prevent tests from hanging forever.
- [ ] Test logging/exception paths and partial startup failures separately.
- [ ] When testing Docker/Kubernetes, check PID 1, SIGTERM, and termination grace.
- [ ] Never use mock resource results to claim database transactions committed.

## 18. Self-check questions

**1. How does `context.stop()` differ from `context.close()`?**  
Stop signals `Lifecycle` beans to stop while the context normally stays active and singleton beans are not destroyed; close initiates the full shutdown/destruction sequence.

**2. During normal context close, which event signals closing has begun?**  
`ContextClosedEvent`.

**3. What is `SmartLifecycle.isAutoStartup()`'s default in Spring Framework 6.2?**  
`true`.

**4. Is `SmartLifecycle`'s default phase `0`?**  
No; `SmartLifecycle.DEFAULT_PHASE` is `Integer.MAX_VALUE` in Spring Framework 6.2. Plain `Lifecycle` is typically treated as phase `0`.

**5. In what order do phases `-100` and `100` start and stop?**  
Start: `-100` then `100`; stop: `100` then `-100`, unless specific dependencies alter it.

**6. Who calls `stop(Runnable)` during shutdown?**  
Spring's `LifecycleProcessor` when managing `SmartLifecycle` and coordinating shutdown.

**7. When should `callback.run()` be called?**  
When the component has completed its stop step per contract and the lifecycle processor may proceed.

**8. What happens if the callback is forgotten?**  
The phase may wait until timeout, slowing shutdown and masking still-running workers.

**9. Why use `CountDownLatch` in async tests?**  
To synchronize the test with the stop callback on real conditions, avoiding flakiness from sleep/timing.

**10. Does `@PreDestroy` apply to objects created with `new` outside Spring?**  
Not automatically; objects must be container-managed or have an owner invoking cleanup explicitly.

**11. When the same bean has `@PreDestroy` and a custom `destroyMethod`, what is the order?**  
`@PreDestroy` before the custom destroy method, per the Spring bean destruction contract.

**12. Why shouldn't you manually close an autowired context from `@SpringBootTest`?**  
It may be cached and reused across tests, leaving other tests seeing a closed context.

**13. What is `@DirtiesContext` used for?**  
Instructs TestContext to evict the context from cache and recreate it for subsequent tests according to the specified mode.

**14. Does an inactive context guarantee the JVM process exited?**  
No. A non-daemon thread outside the context can keep running.

**15. Does `SIGKILL` guarantee `@PreDestroy` runs?**  
No; design recovery independently of shutdown callbacks.

**16. If async stop finishes and invokes its callback while DB changes haven't committed, is testing complete?**  
No. Test transactions/acks at the business integration layer.

**17. What does calling `close()` twice in the lab prove?**  
The context's close path did not re-invoke the observed callbacks; it does not prove every resource API in the system is safe to call twice.

**18. When startup fails before refresh completes, can you claim every `SmartLifecycle` stopped?**  
No. Only components already created/started can participate in stop; init failure paths do not necessarily match normal close.

## 19. Official documentation

- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): lifecycle, destroy callbacks, stop phases, `@PreDestroy`, and `SmartLifecycle`.
- [Spring Framework 6.2 — SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/SmartLifecycle.html): `isAutoStartup`, `getPhase`, `stop(Runnable)`, and default phase.
- [Spring Framework 6.2 — AnnotationConfigApplicationContext](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/annotation/AnnotationConfigApplicationContext.html): manually created test contexts.
- [Spring Framework — TestContext caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache lifecycle, eviction, and `@DirtiesContext`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `webEnvironment`, and context reuse.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): JVM shutdown hook and context closing.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): web-server phase and timeout.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.lifecycle.timeout-per-shutdown-phase`.
- [Oracle Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `awaitTermination`, and interruption.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle and assertions.
- [AssertJ Assertions](https://assertj.github.io/doc/): `containsSubsequence`, `containsExactlyElementsOf`, and scalar assertions.

**Conclusion:** solid shutdown testing must prove **the context closed, lifecycle components stopped in order, async callbacks completed within bounds, and resources were released exactly once**. Use explicitly created contexts in JUnit to observe close paths without breaking the cache; use `CountDownLatch`/`Future` for async synchronization; keep stop, close, startup failure, and process kill separate. A test merely observing `@PreDestroy` run is insufficient to guarantee business resources or data were handled safely.