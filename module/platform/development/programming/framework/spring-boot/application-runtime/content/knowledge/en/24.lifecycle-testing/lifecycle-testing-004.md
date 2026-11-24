# Using ApplicationContextRunner and Understanding SpringApplication Milestones That Are Not Executed

## 1. Core question: does a refreshed context mean the application has finished startup?

**No.** This is a crucial distinction when testing the Spring Boot lifecycle.

`ApplicationContextRunner` in package `org.springframework.boot.test.context.runner` provides a way to construct, refresh, inspect, and auto-close **a minimal `ApplicationContext`** in tests. It is especially useful for verifying a group of beans, `@Conditional...` conditions, initialization/destruction ordering, and auto-configuration across different properties.

`SpringApplication.run(...)`, by contrast, is the **Spring Boot startup orchestrator**: beyond creating and refreshing the context, it prepares the environment/arguments, emits `SpringApplicationEvent`s, invokes `ApplicationRunner`/`CommandLineRunner`, updates liveness/readiness availability, and handles startup failures via Boot mechanisms.

Because `ApplicationContextRunner` **does not call `SpringApplication.run(...)`**, many `SpringApplication`-level milestones **do not happen automatically**, even when inside the test you already have an active context, injected beans, and started `SmartLifecycle` components.

A precise distinction:

> **ApplicationContextRunner verifies the semantics of a refreshed ApplicationContext; it does not simulate the full SpringApplication startup process of an application.**

Goals of this lesson: identify **which milestones run**, **which do not**, why `ApplicationReadyEvent` must not be inferred from `ContextRefreshedEvent`, how to write executable Java 17+ Spring Boot 3.3.13 tests, how to trigger controlled startup failures, and criteria for switching from context-runner tests to integration tests.

Example scope: **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1.x, JUnit Jupiter 5, AssertJ, Gradle**. This lesson does not rely on content from other lessons; examples are self-contained with sufficient configuration and classes for experimentation.

## 2. Two "run" mechanisms sharing a name but not the same job

### 2.1. ApplicationContextRunner.run(consumer)

Typical test code:

```java
new ApplicationContextRunner()
        .withUserConfiguration(DemoConfiguration.class)
        .withPropertyValues("demo.feature.enabled=true")
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DemoService.class);
        });
```

This is an **illustrative snippet**, not a standalone compilable file because it requires `DemoConfiguration`, `DemoService`, and imports. The `run` method here:

1. Creates **a new context** from the runner's configuration.
2. Registers bean definitions, property sources, initializers, and auto-configurations specified by the test.
3. Invokes the **context refresh** process.
4. Passes an `AssertableApplicationContext` into the lambda for the test to read beans and assert.
5. **Auto-closes the context after the callback completes**, including handling corresponding cleanup.

Per Spring Boot 3.3 APIs, `new ApplicationContextRunner()` uses `AnnotationConfigApplicationContext` by default — a **non-web context** and not a `SpringApplication.run` call. It does not automatically component-scan the whole project or activate all auto-configurations unless requested.

### 2.2. SpringApplication.run(...)

Main application code:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);
```

This snippet is also illustrative. `SpringApplication.run` is responsible for preparing many parts **beyond the context refresh itself**:

- Bootstrapping the environment and command-line arguments per Boot rules.
- Choosing the `ApplicationContext` type matching the web classpath/configuration.
- Registering initializers/listeners in the phase before bean definitions are loaded.
- Emitting dedicated `SpringApplicationEvent`s before and after context refresh.
- Calling `ApplicationRunner` and `CommandLineRunner` after refresh.
- Emitting `ApplicationStartedEvent`, `ApplicationReadyEvent`, and related `AvailabilityChangeEvent`s.
- Routing startup failures into the appropriate failure-handling pipeline.
- Returning the running context so the application continues serving or is closed by the caller.

**Not every step above is triggered merely by `context.refresh()`.** Spring Framework and Spring Boot use different hooks.

### 2.3. Quick comparison table

| Behavior / observation point | Default `ApplicationContextRunner.run` | Normal `SpringApplication.run` |
| --- | --- | --- |
| Create `ApplicationContext` | **Yes** | **Yes** |
| Register beans and inject dependencies | **Yes**, per test configuration | **Yes**, per application sources/auto-config |
| `@PostConstruct`, `InitializingBean` on created beans | **Yes** | **Yes** |
| `BeanFactoryPostProcessor` / `BeanPostProcessor` | **Yes**, if part of context | **Yes** |
| `SmartLifecycle.start()` during refresh if auto-start | **Yes** | **Yes** |
| Spring Framework `ContextRefreshedEvent` | **Yes** on successful refresh | **Yes** on successful refresh |
| Spring Boot `ApplicationStartingEvent` | **Not auto-emitted** | **Yes** |
| `ApplicationEnvironmentPreparedEvent` and `ApplicationPreparedEvent` | **Not auto-emitted** | **Yes** |
| Spring Boot `ApplicationStartedEvent` | **Not auto-emitted** | **Yes**, after refresh |
| `ApplicationRunner.run` / `CommandLineRunner.run` | **Not auto-invoked** | **Yes**, before ready |
| `ApplicationReadyEvent` | **Not auto-emitted** | **Yes**, after runners succeed |
| Liveness/readiness events emitted by SpringApplication | **Not auto-emitted** | **Yes**, per Boot startup sequence |
| `ContextClosedEvent` on normal context close | **Yes** at end of test `run` | **Yes** when closing context |
| `SmartLifecycle.stop` and singleton `@PreDestroy` | **Yes** when runner closes context normally | **Yes** when context closes normally |
| `ApplicationFailedEvent` when test refresh fails | **Not auto-emitted via SpringApplication mechanism** | **May be emitted** on startup failure |
| `FailureAnalyzer`/Boot startup failure reporting | Do not assume it ran | Part of `SpringApplication` failure handling |
| JVM process exit / exit code | **No** | `SpringApplication.run` does not automatically imply `System.exit` either |

The context runner column reflects the **standard runner** without custom code manually emitting Boot events. If a user intentionally calls `context.publishEvent(new ...)` or installs a custom initializer, behavior can differ; those are not **automatic** milestones of `SpringApplication`.

## 3. Timeline: context refresh vs. completing Spring Boot startup

### 3.1. ApplicationContextRunner

```text
JUnit @Test
   |
   +--> new ApplicationContextRunner()
   +--> withUserConfiguration(...), withPropertyValues(...)
   +--> runner.run(callback)
          |
          +--> create AnnotationConfigApplicationContext
          +--> prepare/register bean definitions
          +--> refresh()
          |      +--> BeanFactoryPostProcessors / BeanPostProcessors
          |      +--> create non-lazy singletons
          |      +--> dependency injection, @PostConstruct
          |      +--> LifecycleProcessor.onRefresh()
          |      |      +--> SmartLifecycle auto-start
          |      +--> ContextRefreshedEvent
          |
          +--> callback receives AssertableApplicationContext
          |      +--> assert bean/config/lifecycle state
          |      +--> ApplicationRunner has STILL NOT been called by Boot
          |      +--> ApplicationReadyEvent has NOT been emitted by Boot
          |
          +--> runner auto-closes context
                 +--> ContextClosedEvent
                 +--> LifecycleProcessor.onClose()
                 +--> @PreDestroy / destroy bean callbacks
   |
   +--> test method continues/completes
```

Note: the word "`run`" in `runner.run(callback)` only means **execute a test run of the context**. It does not mean "run the Spring Boot startup runner beans".

### 3.2. SpringApplication.run

```text
SpringApplication.run(...)
   |
   +--> ApplicationStartingEvent
   +--> prepare Environment
   +--> ApplicationEnvironmentPreparedEvent
   +--> ApplicationContextInitializedEvent
   +--> load bean definitions
   +--> ApplicationPreparedEvent
   +--> context.refresh()
   |      +--> @PostConstruct / bean initialization
   |      +--> SmartLifecycle auto-start
   |      +--> ContextRefreshedEvent
   |
   +--> ApplicationStartedEvent
   +--> AvailabilityChangeEvent(LivenessState.CORRECT)
   +--> ApplicationRunner / CommandLineRunner
   +--> ApplicationReadyEvent
   +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
   +--> return running context
```

This is the **successful startup** timeline of Spring Boot 3.3. It condenses internal steps and **does not** claim an `@EventListener` bean can catch every early event: very early events occur before listener beans are instantiated, so listeners must be registered on `SpringApplication`/`spring.factories` if you need to observe them.

On the failure path, `ApplicationFailedEvent` may be sent and cleanup performed as available. Not every success-path step in the diagram will execute.

### 3.3. The easiest confusion: ContextRefreshedEvent is not ApplicationReadyEvent

`ContextRefreshedEvent` states that **a context's refresh** has completed per the Framework contract. In Spring Boot 3.3, however, `ApplicationStartedEvent` comes **after refresh**, then Boot invokes runners, and only then emits `ApplicationReadyEvent` and `ReadinessState.ACCEPTING_TRAFFIC`.

Therefore, in a test:

```java
assertThat(context.isActive()).isTrue();
```

is **insufficient** to conclude:

```text
Boot has emitted ApplicationReadyEvent
all ApplicationRunners have run
readiness has transitioned to ACCEPTING_TRAFFIC
the web server has opened a port and is serving real HTTP
```

These are conclusions at different lifecycle levels. To assert them, use the corresponding test type and assertions.

## 4. Which milestones actually execute in ApplicationContextRunner?

### 4.1. @PostConstruct and bean initialization

`AnnotationConfigApplicationContext.refresh()` is still a Spring Framework refresh. Non-lazy singletons are created and receive lifecycle initialization callbacks such as `@PostConstruct` or `InitializingBean.afterPropertiesSet()` where applicable.

This means `ApplicationContextRunner` is well-suited to test:

- Whether constructor injection has all required dependencies.
- Whether `BeanPostProcessor`s process annotations properly.
- Which beans are created under given conditions/properties.
- Whether `@PostConstruct` runs and validates internal input data.
- Whether a bean failing during init causes a **context startup failure** to be recorded.

However, avoid writing tests with heavy external side effects in `@PostConstruct` when the goal is only unit/auto-config testing; each `runner.run` can create/destroy its own context.

### 4.2. SmartLifecycle.start() and stop() are still invoked

`LifecycleProcessor` is part of Spring Framework context refresh/close. `SmartLifecycle` beans with `isAutoStartup() == true` are started on refresh; when the context closes normally, running lifecycle beans are stopped in phase order, optionally using `stop(Runnable callback)`.

This **does not require `SpringApplication.run`**. An `ApplicationContextRunner` test can observe:

```text
@PostConstruct
SmartLifecycle.start
ContextRefreshedEvent
... callback assertions ...
ContextClosedEvent
SmartLifecycle.stop
@PreDestroy
```

Yet start/stop here are **context/component milestones**, not that Boot has passed started/ready.

### 4.3. ContextRefreshedEvent and ContextClosedEvent

These are **Spring Framework** `ApplicationContextEvent`s, emitted by the context itself. A properly registered `@EventListener` bean can receive these events in a normal context runner test.

When the `runner.run(...)` lambda returns, the runner auto-closes the context. Thus `ContextClosedEvent`, `SmartLifecycle.stop`, and destruction callbacks belong to the **post-callback phase**. To assert them, keep a collector outside the test context and assert **after `run` returns**. Do not place an assertion claiming "`@PreDestroy` has run" **inside** the callback while the context is still alive.

### 4.4. You can customize the context, but it does not automatically become SpringApplication

The runner provides utilities:

- `withUserConfiguration(...)` adds user-selected configuration classes.
- `withConfiguration(AutoConfigurations.of(...))` adds specified auto-configuration classes.
- `withPropertyValues("x=y")` customizes the Environment per test case.
- `withBean(...)` adds a small test bean, including a supplier returning a collector/mock.
- `withInitializer(...)` adds an `ApplicationContextInitializer` that runs **while building the test context**.
- `withClassLoader(...)` simulates a filtered classpath to test `@ConditionalOnClass`.
- `withParent(...)` supplies a parent context when hierarchy conditions must be tested.
- `withSystemProperties(...)` adjusts test system properties per the runner's contract.

**Do not confuse `withInitializer(...)` with Boot auto-emitting `ApplicationContextInitializedEvent`.** Initializers run via the test runner mechanism, without a full `SpringApplication` instance traversing the Boot event pipeline.

## 5. SpringApplication milestones that do NOT auto-execute

### 5.1. Early events

Boot 3.3 includes SpringApplication-level events:

1. `ApplicationStartingEvent`.
2. `ApplicationEnvironmentPreparedEvent`.
3. `ApplicationContextInitializedEvent`.
4. `ApplicationPreparedEvent`.

They are emitted while `SpringApplication` prepares bootstrapping, not as an automatic byproduct of `AnnotationConfigApplicationContext.refresh()`. Thus `ApplicationContextRunner` does not auto-emit them.

To test an `ApplicationListener<ApplicationStartingEvent>`, register the listener **before `SpringApplication` runs**. Merely creating a listener bean in the context is too late to catch many early events.

### 5.2. ApplicationStartedEvent is not auto-emitted

`ApplicationStartedEvent` is emitted by Boot after context refresh, before runners. `ApplicationContextRunner` only invokes refresh per test setup, so no Boot component fires this event.

A test can pass every assertion on beans and `SmartLifecycle` and still **fail to prove** that an `ApplicationStartedEvent` listener will run properly when the real application starts.

### 5.3. ApplicationRunner and CommandLineRunner are not auto-invoked

Both are Spring beans; the context runner can **instantiate and inject** them. However, their `run(...)` methods are not default callbacks of Spring Framework `refresh()`.

Spring Boot has a dedicated step inside `SpringApplication.run(...)`:

```java
// Spring Boot interface signatures, not code you write yourself.
void run(ApplicationArguments args) throws Exception;
void run(String... args) throws Exception;
```

The snippet above illustrates `ApplicationRunner` and `CommandLineRunner` respectively. The container only creates the objects; **`SpringApplication`** orchestrates calling their methods during a successful startup.

In a context runner test, the runner bean can still exist:

```java
assertThat(context).hasSingleBean(ApplicationRunner.class);
```

yet the `ApplicationRunner.run` body has not been called by Boot. An assertion checking bean existence **is not** an assertion checking startup code inside the runner.

### 5.4. ApplicationReadyEvent and readiness do not occur automatically

Boot emits `ApplicationReadyEvent` **after** runners finish normally, then emits `AvailabilityChangeEvent<ReadinessState>` representing `ACCEPTING_TRAFFIC`. `ApplicationContextRunner` does not run that sequence.

Do not assume:

- `ApplicationAvailability.getReadinessState() == ACCEPTING_TRAFFIC`;
- readiness probes/Actuator health groups have transitioned to ready;
- container readiness orchestration has been updated;
- `@EventListener(ApplicationReadyEvent.class)` listeners have executed.

You should also not unconditionally assert "readiness == REFUSING_TRAFFIC" just because the runner did not emit ready, since **`ApplicationAvailability` itself may not even be registered in a minimal test context**. That is a limitation of which components are present in the context, not a published Boot state.

### 5.5. ApplicationFailedEvent and FailureAnalyzer do not auto-run

If `ApplicationContextRunner` refreshes a broken bean, it can pass a **failed context** to the callback along with `getStartupFailure()`. That **does not mean** Boot went through `SpringApplication.handleRunFailure(...)` to emit `ApplicationFailedEvent` and invoke `FailureAnalyzer`/`FailureAnalysisReporter`.

Distinguish the two:

- **Runner test failure**: failure occurs while building/refreshing the test context; the test directly asserts `getStartupFailure()`.
- **Boot startup failure**: `SpringApplication.run` executes its own startup failure pipeline; under appropriate conditions it can emit `ApplicationFailedEvent` and present analysis.

If you need to verify **failure analysis messages** or reporter registration via `spring.factories`, design a test booting with a real `SpringApplication` instead of merely checking that the context runner failed.

### 5.6. WebServerInitializedEvent and port binding

`new ApplicationContextRunner()` uses a non-web context. It does not start embedded Tomcat/Netty and emits no `WebServerInitializedEvent` from web server startup.

`WebApplicationContextRunner` / `ReactiveWebApplicationContextRunner` are suitable for simulating a **web application context** and testing web auto-configuration, yet they are also **not HTTP end-to-end tests that open real ports by default**. To assert socket binding, web server readiness, actual HTTP requests, or SSL, use the corresponding web/integration test.

## 6. When is ApplicationContextRunner the best choice?

| Test goal | Is context runner suitable? | What should be verified? |
| --- | --- | --- |
| `@ConditionalOnProperty` creates/omits bean | **Very suitable** | Bean presence/absence per property |
| `@ConditionalOnMissingBean` yields to user bean | **Very suitable** | Default bean backed off |
| ConfigurationProperties binding and validation | Suitable if required binder/annotations are registered | Bean properties and startup failure |
| `@PostConstruct` or init methods | Suitable | State right after refresh |
| `SmartLifecycle.start/stop` and `ContextRefreshedEvent` | Suitable | Context lifecycle relationships |
| `@PreDestroy` and close ordering | Suitable | Assert collector after `run` callback |
| `ApplicationRunner.run` runs properly in SpringApplication | **Insufficient** | Integration test via `SpringApplication.run` |
| `ApplicationStartedEvent`/`ApplicationReadyEvent` | **Insufficient** | Real Boot event listeners at startup |
| Readiness / liveness state transitions | **Insufficient** without running Boot pipeline | Test `ApplicationAvailability` in a Boot app |
| Embedded web server real port binding/HTTP | **Insufficient** | `@SpringBootTest(webEnvironment=RANDOM_PORT)` or process test |
| `FailureAnalysisReporter` on startup failure | Insufficient | Boot failure path/launcher test |
| Small startup dependency graph, context failure | **Suitable** | `getStartupFailure()` |
| Full application packages, scanning, and real auto-config | Not by default | Slice/full integration test as needed |

The goal is not to write as many full Boot tests as possible. You want **small, properly scoped tests**, plus **a few real Boot startup tests** for application-level milestones. Context runners are especially fast and clear for exploring many property/classpath combinations without opening databases/servers.

## 7. Complete example: four Java 17+ tests on lifecycle boundaries

The example has two key verification lines:

- **Test A:** context runner refreshes and closes the context; observes init/start/refreshed/closed/stop/destroy, but **does not** observe Boot-only events/runners.
- **Test B:** uses `SpringApplication.run(...)` in a separate test; observes Boot events and both runners executing, alongside context lifecycle milestones.
- **Test C:** uses context runner to test a property-based bean graph without bootstrapping the entire app.
- **Test D:** intentionally creates a failing bean during refresh, checking `getStartupFailure()` without confusing it with `ApplicationFailedEvent`.

The tests **do not depend on millisecond timings, `Thread.sleep`, or unguaranteed bean ordering**. The experiment uses an event collector passed into the context to observe exact ordering.

### 7.1. Project structure

```text
context-runner-lifecycle-lab/
├── build.gradle
├── settings.gradle
└── src/
    └── test/
        └── java/com/example/lifecycle/
            └── LifecycleBoundaryTest.java
```

There is a single Java test file containing small configurations/beans as nested static classes. We **do not need an actual `@SpringBootApplication` file** for this test, because `SpringApplication` accepts a `@Configuration` class as its source; the beans in the example are self-contained.

### 7.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` provides Spring Boot Test, JUnit Jupiter, AssertJ, and related test tools. Because `ApplicationContextRunner` belongs to `spring-boot-test`, relying solely on runtime `spring-boot-starter` **will not** put this API on the production compile classpath. Keep context runner code under `src/test/java`.

File `settings.gradle`:

```groovy
rootProject.name = 'context-runner-lifecycle-lab'
```

### 7.3. Complete LifecycleBoundaryTest.java file

Create file **`src/test/java/com/example/lifecycle/LifecycleBoundaryTest.java`**:

```java
package com.example.lifecycle;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.junit.jupiter.api.Test;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

import static org.assertj.core.api.Assertions.assertThat;

class LifecycleBoundaryTest {

    @Test
    void contextRunnerRefreshesButSkipsBootOnlyMilestones() {
        Timeline timeline = new Timeline();

        new ApplicationContextRunner()
                .withBean(Timeline.class, () -> timeline)
                .withUserConfiguration(ProbeConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ObservedComponent.class);
                    assertThat(context).hasSingleBean(ApplicationRunner.class);
                    assertThat(context).hasSingleBean(CommandLineRunner.class);
                    assertThat(context.getBean(ObservedComponent.class).isRunning())
                            .isTrue();

                    // Passed refresh and SmartLifecycle.start,
                    // but not yet past SpringApplication.start/ready/runners.
                    assertThat(timeline.snapshot()).containsExactly(
                            "bean.init",
                            "smart.start",
                            "context.refreshed");
                });

        // ApplicationContextRunner automatically closes the context after the callback.
        assertThat(timeline.snapshot()).containsExactly(
                "bean.init",
                "smart.start",
                "context.refreshed",
                "context.closed",
                "smart.stop",
                "bean.destroy");
    }

    @Test
    void actualSpringApplicationInvokesBootRunnersAndEvents() {
        Timeline timeline = new Timeline();

        SpringApplication app = new SpringApplication(ProbeConfiguration.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        // Register a singleton before config beans are initialized.
        app.addInitializers(context ->
                context.getBeanFactory().registerSingleton(
                        "timeline", timeline));

        try (ConfigurableApplicationContext context = app.run()) {
            assertThat(context.isActive()).isTrue();

            List<String> events = timeline.snapshot();

            assertThat(events).contains(
                    "bean.init",
                    "smart.start",
                    "context.refreshed",
                    "boot.started",
                    "boot.applicationRunner",
                    "boot.commandLineRunner",
                    "boot.ready");

            // Do not assume order between two runners with the same order.
            assertThat(events.indexOf("context.refreshed"))
                    .isLessThan(events.indexOf("boot.started"));
            assertThat(events.indexOf("boot.started"))
                    .isLessThan(events.indexOf("boot.applicationRunner"));
            assertThat(events.indexOf("boot.started"))
                    .isLessThan(events.indexOf("boot.commandLineRunner"));
            assertThat(events.indexOf("boot.applicationRunner"))
                    .isLessThan(events.indexOf("boot.ready"));
            assertThat(events.indexOf("boot.commandLineRunner"))
                    .isLessThan(events.indexOf("boot.ready"));
        }

        assertThat(timeline.snapshot()).contains(
                "context.closed",
                "smart.stop",
                "bean.destroy");
    }

    @Test
    void contextRunnerCanTestPropertyDrivenBeanGraphs() {
        ApplicationContextRunner runner = new ApplicationContextRunner()
                .withUserConfiguration(ConditionalFeatureConfiguration.class);

        runner.withPropertyValues("feature.enabled=true").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(Feature.class);
            assertThat(context.getBean(Feature.class).name())
                    .isEqualTo("ENABLED");
        });

        runner.withPropertyValues("feature.enabled=false").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(Feature.class);
        });
    }

    @Test
    void failedContextIsInspectableWithoutBootFailureEvent() {
        new ApplicationContextRunner()
                .withUserConfiguration(BrokenConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure()).isNotNull();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(IllegalStateException.class);
                });
    }

    static final class Timeline {
        private final List<String> steps = new CopyOnWriteArrayList<>();

        void add(String value) {
            steps.add(value);
        }

        List<String> snapshot() {
            return List.copyOf(steps);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ProbeConfiguration {

        @Bean
        ObservedComponent observedComponent(Timeline timeline) {
            return new ObservedComponent(timeline);
        }

        @Bean
        EventProbe eventProbe(Timeline timeline) {
            return new EventProbe(timeline);
        }

        @Bean
        ApplicationRunner applicationRunner(Timeline timeline) {
            return args -> timeline.add("boot.applicationRunner");
        }

        @Bean
        CommandLineRunner commandLineRunner(Timeline timeline) {
            return args -> timeline.add("boot.commandLineRunner");
        }
    }

    static final class ObservedComponent implements SmartLifecycle {
        private final Timeline timeline;
        private volatile boolean running;

        ObservedComponent(Timeline timeline) {
            this.timeline = timeline;
        }

        @PostConstruct
        public void init() {
            timeline.add("bean.init");
        }

        @Override
        public void start() {
            running = true;
            timeline.add("smart.start");
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                timeline.add("smart.stop");
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

        @PreDestroy
        public void destroy() {
            timeline.add("bean.destroy");
        }
    }

    static final class EventProbe {
        private final Timeline timeline;

        EventProbe(Timeline timeline) {
            this.timeline = timeline;
        }

        @EventListener
        public void onRefreshed(ContextRefreshedEvent event) {
            timeline.add("context.refreshed");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            timeline.add("context.closed");
        }

        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            timeline.add("boot.started");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            timeline.add("boot.ready");
        }
    }

    record Feature(String name) {
    }

    @Configuration(proxyBeanMethods = false)
    static class ConditionalFeatureConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "feature",
                name = "enabled",
                havingValue = "true")
        Feature feature() {
            return new Feature("ENABLED");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BrokenConfiguration {

        @Bean
        Object brokenBean() {
            throw new IllegalStateException("intentional refresh failure");
        }
    }
}
```

### 7.4. Why does Test A verify the exact boundary?

The beginning of Test A passes a `Timeline` object from **outside the context** using `withBean(Timeline.class, () -> timeline)`. By keeping a reference in the test, we can still read milestones **after the context runner has auto-closed the context**.

During a successful refresh:

1. `ObservedComponent` is created and `@PostConstruct` is called → `bean.init`.
2. `DefaultLifecycleProcessor.onRefresh()` calls `SmartLifecycle.start()` → `smart.start`.
3. Spring Framework emits `ContextRefreshedEvent` → `context.refreshed`.
4. Callback `runner.run(context -> ...)` is invoked; both `ApplicationRunner`/`CommandLineRunner` beans **exist**, yet their bodies **have not been called by Boot**.
5. There is no `ApplicationStartedEvent`/`ApplicationReadyEvent`, because there is no `SpringApplication.run`.

Thus `timeline.snapshot()` right **inside** the callback has the expected contents:

```text
[bean.init, smart.start, context.refreshed]
```

After the callback returns, the runner closes the context:

1. `ContextClosedEvent` → `context.closed`.
2. `SmartLifecycle.stop(Runnable)` → `smart.stop`, callback is notified.
3. Spring destroys singletons → `@PreDestroy` → `bean.destroy`.

Snapshot at that point:

```text
[bean.init, smart.start, context.refreshed, context.closed, smart.stop, bean.destroy]
```

These two lists are **assertion values on the collector**, not stdout printed by the Java program. The test file never calls `System.out.println`, so **do not promise that the Gradle console will print these two lists**. What can be verified is that the JUnit assertions pass under a compatible runtime/framework.

### 7.5. Why does Test B not assert the order of the two runners?

Test B **intentionally calls a real `SpringApplication`** with `ProbeConfiguration`. It does not use `new ApplicationContextRunner()`. At startup:

```text
bean.init
smart.start
context.refreshed
boot.started
boot.applicationRunner / boot.commandLineRunner (relative order not enforced)
boot.ready
```

Both runners have the **default order**, so the test **only asserts that both execute after started and before ready**. Never assert "`ApplicationRunner` always runs before `CommandLineRunner`" without explicit `@Order`/`Ordered`.

The `ApplicationContextInitializer` in Test B registers `Timeline` into the bean factory **before config beans are created**, so both the runners and the event probe share one collector outside the context. This is a way to pass a dependency into an integration test; **do not interpret** the initializer in Test B as meaning `withInitializer(...)` in a context runner runs the full Boot lifecycle.

When Test B exits `try-with-resources`, the context closes and `context.closed`, `smart.stop`, `bean.destroy` can be observed along the normal shutdown path.

### 7.6. Why is Test C important?

`@ConditionalOnProperty` executes at the bean definition/condition evaluation level during refresh. Thus:

```java
runner.withPropertyValues("feature.enabled=true")
        .run(context -> assertThat(context).hasSingleBean(Feature.class));
```

is the **right-level** way to test bean creation conditions without emitting `ApplicationReadyEvent`. The `false` test checks that the bean is not created.

This is one of the official uses recommended by Spring Boot for `ApplicationContextRunner`: exploring property and user configuration combinations of auto-configuration.

### 7.7. Why does Test D use getStartupFailure?

With `BrokenConfiguration`, the bean factory tries to instantiate `brokenBean` during refresh and the `@Bean` method throws `IllegalStateException`. Spring may wrap it in `BeanCreationException`, so the test asserts the **root cause type** rather than asserting that the top-level class is one exact exception type.

`ApplicationContextRunner` captures the failure for the callback to inspect:

```java
assertThat(context).hasFailed();
assertThat(context.getStartupFailure())
        .hasRootCauseInstanceOf(IllegalStateException.class);
```

This is an **excerpt from the full test file**. It tests failure during **context refresh**, not `SpringApplication`'s `ApplicationFailedEvent`. Keep this distinction clear in test names and QA reports.

### 7.8. Running tests

Requires a Java 17 compatible Gradle Wrapper. From the project directory:

macOS/Linux:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

To run only a single test file:

```bash
./gradlew test --tests "com.example.lifecycle.LifecycleBoundaryTest"
```

If the project is configured properly and all assertions pass, Gradle reports the test task as successful. **Do not claim fixed stdout like "4 tests passed" as a Java output**, because Gradle test report formatting depends on configuration/launcher version. Check details in `build/reports/tests/test/index.html` if the test runner generates HTML reports at the default location.

### 7.9. Limitations of the example

- This is **a test project**; `LifecycleBoundaryTest` lives in `src/test/java`.
- `ProbeConfiguration` contains minimal beans and does not trigger full `@SpringBootApplication` auto-configuration.
- Test B does use a real `SpringApplication` to demonstrate the lifecycle distinction, yet intentionally sets `WebApplicationType.NONE` to avoid creating a web server/port.
- Test A can verify Spring Framework context milestones; it **cannot replace** tests for Boot startup/ready events.
- When users add executors, async listeners, or other auto-config beans, exact callback ordering must be re-verified per dependency and thread policies.


## 8. Testing real auto-configuration with ApplicationContextRunner

The previous example used `withUserConfiguration(...)`. In an auto-configuration library or starter, the standard pattern is:

```java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MyFeatureAutoConfiguration.class));
```

This is an **illustrative snippet**, requiring imports for `org.springframework.boot.autoconfigure.AutoConfigurations`, `ApplicationContextRunner`, and a real `MyFeatureAutoConfiguration` class. `AutoConfigurations.of(...)` brings **specified** auto-configuration classes into the test following proper ordering rules; it does not auto-scan the entire classpath.

For an auto-configuration providing a default bean:

```java
runner.run(context -> {
    assertThat(context).hasSingleBean(MyService.class);
});

runner.withUserConfiguration(UserOverrideConfiguration.class)
        .run(context -> {
            assertThat(context).hasSingleBean(MyService.class);
            assertThat(context.getBean(MyService.class))
                    .isSameAs(context.getBean("customMyService"));
        });
```

These are **illustrative snippets**; matching class definitions are required. The goal is to test `@ConditionalOnMissingBean` backing off when the user defines their own bean.

### 8.1. Benefits of an immutable runner per customization

`with...` methods normally return **a new runner with additional configuration** for safe reuse across test cases. Declare a `private final ApplicationContextRunner baseRunner` and write each test using `baseRunner.withPropertyValues(...)`. Do not write code that relies on modifying properties in Test A affecting Test B.

In Test C, `runner.withPropertyValues("feature.enabled=true")` and `...false` create two **independent** test contexts. Each `run` has its own refresh/close; never reuse the same context from a previous test, avoiding state leaks.

### 8.2. withPropertyValues does not simulate the full config data pipeline

`withPropertyValues("feature.enabled=true")` adds properties to the test Environment. It works well for `@ConditionalOnProperty`/binding, yet you should not assume it proves:

- Full production-like profile activation.
- That the Config Data API loaded all `application.yml` files, environment variables, cloud config, and secret managers.
- That command-line arguments were fully parsed by `SpringApplication`.
- That placeholder resolution from all external sources executes identically to the deployed process.
- That system properties cannot be overridden out of order in a custom bootstrap.

If a bug involves **Config Data loading/profile activation/command-line precedence**, use an integration test with a real `SpringApplication` or a process test with real config sources.

### 8.3. withBean helps substitute real dependencies in tests

An auto-config class might need a `Clock`, `DataSource`, client service, or `SomeProperties`. With the runner, you can supply test beans:

```java
new ApplicationContextRunner()
        .withBean(Clock.class, () -> Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC))
        .withUserConfiguration(MyConfiguration.class)
        .run(context -> {
            // Assert bean needing Clock operates at the fixed time.
        });
```

This is a **snippet**, requiring imports for `java.time.Clock`, `Instant`, `ZoneOffset`, and `MyConfiguration`. It demonstrates deterministic testing, not a tool for simulating `SpringApplication` Ready events.

### 8.4. withClassLoader to simulate missing dependencies

`FilteredClassLoader` can hide specific classes/packages from the test context's view to test `@ConditionalOnClass` or `@ConditionalOnMissingClass`.

```java
new ApplicationContextRunner()
        .withClassLoader(new FilteredClassLoader(
                "com.example.optional"))
        .withConfiguration(AutoConfigurations.of(
                MyFeatureAutoConfiguration.class))
        .run(context -> {
            assertThat(context).doesNotHaveBean(OptionalFeature.class);
        });
```

This is an **illustrative snippet** requiring the corresponding classes and importing `org.springframework.boot.test.context.FilteredClassLoader`. It is useful when testing optional library auto-config, yet it is not equivalent to running a Java process with a classpath stripped of that dependency; critical startup integrations still require an appropriate process/classpath test.

### 8.5. ConditionEvaluationReport and diagnostic conditions

When a bean does not appear, do not jump to blaming the test runner. Check `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, and auto-config import order.

Spring Boot allows adding an initializer to log the condition evaluation report:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .withConfiguration(AutoConfigurations.of(
                MyFeatureAutoConfiguration.class))
        .run(context -> {
            // Read condition evaluation and beans upon refresh.
        });
```

This is a **snippet** based on official documentation, requiring imports for `org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener` and `org.springframework.boot.logging.LogLevel`. Inspecting the report clarifies auto-config conditions, yet **does not cause SpringApplication started/ready events to appear**.

### 8.6. Limitations when running native images

Spring Boot 3.3 documentation explicitly notes that `ApplicationContextRunner` **does not work when running tests inside a native image**. If a project must test GraalVM native executables, choose a dedicated test strategy for native images, AOT processing, and runtime; do not assume context runner tests fully reflect native startup.

## 9. WebApplicationContextRunner and ReactiveWebApplicationContextRunner

Beyond the default non-web runner, Spring Boot Test provides:

- `WebApplicationContextRunner`: constructs a servlet web application context in tests.
- `ReactiveWebApplicationContextRunner`: constructs a reactive web application context.
- `ApplicationContextRunner`: standard, non-web context.

Example using the web context runner:

```java
new WebApplicationContextRunner()
        .withUserConfiguration(MyMvcConfiguration.class)
        .run(context -> {
            assertThat(context).hasNotFailed();
            // Verify web MVC beans or auto-configuration present in the context.
        });
```

This is a **snippet**; web dependencies and appropriate configuration are required. It does not include a production-like HTTP server, does not emit `ServletWebServerInitializedEvent` like a real embedded server test, and **does not call `SpringApplication.run`**.

### 9.1. When you need to test WebServerInitializedEvent listeners

`WebServerInitializedEvent` is tied to successful embedded web server initialization, not a guaranteed milestone of every refreshed context. If a bean needs to know the dynamic port or an actual web server, use:

- `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)`.
- `TestRestTemplate` or `WebTestClient` depending on web stack/test scope.
- Or a process integration test launching the real JAR and sending HTTP requests.

Distinguish between a **mock MVC context** and an **actual LISTENING socket**. Both are useful, yet they verify different claims.

### 9.2. ApplicationReadyEvent and web server binding

In Spring Boot 3.3, the web server can be initialized during context refresh, while `ApplicationReadyEvent` arrives after runners finish. A server that has bound a port **does not automatically prove readiness of the entire application**. An `ApplicationContextRunner` test proves neither port binding nor the Boot ready event without a larger test design.

## 10. Verifying startup failures at the right layer

An application can fail at many different points:

| Failure location | Can context runner catch it? | When is real Boot startup needed? |
| --- | --- | --- |
| `@Bean` factory method throws during refresh | Yes: `getStartupFailure()` | FailureAnalyzer/boot failure event/exit semantics |
| `@PostConstruct` throws | Yes: refresh failure | Full Boot startup error reporting |
| `SmartLifecycle.start()` throws | Yes: refresh failure | How post-refresh Boot events are blocked |
| `ApplicationRunner.run()` throws | **Does not auto-call runners**, so does not trigger this | **Yes**: SpringApplication handles runner failures |
| `ApplicationReadyEvent` listener throws | Runner does not auto-emit the event | **Yes**, if tests must cover ready-phase error paths |
| Servlet port bind collision | Non-web runner does not simulate | **Yes**: real embedded server/port |
| Config Data import/profile error before refresh | Incomplete vs. Boot pipeline | **Yes**: SpringApplication environment preparation |
| Missing class auto-config condition | Can test condition with FilteredClassLoader | Runtime process/classpath if packaging must be verified |
| Exception in `@Scheduled` after app ready | Not a startup failure | Runtime async error/monitoring test |

### 10.1. A failed context is not ApplicationFailedEvent

If a test uses:

```java
new ApplicationContextRunner()
        .withUserConfiguration(BrokenConfiguration.class)
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
```

this asserts that **context refresh failed**. There is no basis to assert Boot's `ApplicationFailedEvent`, `ExitCodeGenerator`, or `FailureAnalysisReporter` ran solely from this code. For those behaviors, test the `SpringApplication` failure path or real process startup.

### 10.2. Do not manually call a runner bean and treat it as testing Boot lifecycle

An anti-pattern:

```java
new ApplicationContextRunner()
        .withUserConfiguration(MyConfiguration.class)
        .run(context -> {
            ApplicationRunner runner =
                    context.getBean(ApplicationRunner.class);

            runner.run(new DefaultApplicationArguments(new String[0]));
        });
```

This is an **illustrative snippet** requiring imports/classes and a callback that can throw exceptions; it is not standalone. It can test **the runner bean's logic** with a mocked `ApplicationArguments`. However:

- It does not prove Boot emitted `ApplicationStartedEvent` beforehand.
- It does not prove how Boot orders all runner beans via `@Order`.
- It does not prove `ApplicationReadyEvent` is emitted after the runner finishes.
- It does not prove Boot handles runner exceptions and updates readiness as in production.

If you only need to unit test logic inside `ApplicationRunner.run`, calling it directly is fine; just **never call it a SpringApplication lifecycle integration test**.

### 10.3. Be careful with SmartLifecycle side effects

`ApplicationContextRunner` really does call `SmartLifecycle.start()` when auto-starting. A message consumer whose `start` connects to a real broker can cause side effects or hang the test. This is a **critical caveat** if you thought the context runner "only builds bean definitions".

Mitigations:

- Override/inject a fake client bean via `withBean`.
- Set `isAutoStartup=false` in test config if the test does not need an active worker.
- Bound I/O timeouts and ensure stop callbacks finish.
- Do not rely on production credentials in unit tests.
- When testing a consumer's startup protocol, use an integration test with appropriate fake dependencies/containers.

## 11. Notes on using @SpringBootTest as a higher-level verification step

`@SpringBootTest` uses Spring Boot Test infrastructure to create an application context closer to the real application. It normally uses `SpringApplication` to load the app and can execute many Boot startup steps, including runners when the context initializes along the standard path. Still, understand:

- Context caching exists between tests; **`SpringApplication.run` is not guaranteed to re-run for every test method**.
- Mock beans, active profiles, and test properties can make startup differ from production.
- `webEnvironment=MOCK` does not necessarily start a web server binding a real port.
- Very early `SpringApplication` events can occur **before** regular listener beans are ready.
- `@RecordApplicationEvents`/`ApplicationEvents` helps test application events, yet you must check event capture scope and registration timing; never assume a listener bean can observe events before it is instantiated.

If a requirement needs to prove the full `ApplicationStartedEvent → runners → ApplicationReadyEvent` sequence, **Test B in the example is a clear pattern**: construct `SpringApplication` directly, register a collector, specify minimal application sources, and call real `run`. For HTTP/production packaging requirements, add a higher-level integration test accordingly.

### 11.1. Do not compare runner latency with production startup time

`ApplicationContextRunner` does not load all auto-configurations or external integrations by default, and skips part of `SpringApplication` bootstrapping. Faster test execution **does not prove** production startup is also fast.

To measure startup performance, use `ApplicationStartup`, `BufferingApplicationStartup`, the Actuator startup endpoint, or profiling/real process tests — never treat the timing of one context runner test as an absolute benchmark.

## 12. Common mistakes and fixes

| Misconception / symptom | Reason | Fix |
| --- | --- | --- |
| "Runner `run` is the same as `SpringApplication.run`" | Two APIs with different purposes | Distinguish context refresh from Boot bootstrap |
| "Context active = Boot ready" | Runners/availability occur after refresh | Check `ApplicationReadyEvent` in a Boot test |
| "`ContextRefreshedEvent` = `ApplicationStartedEvent`" | Different publisher and timing | Pick the right event |
| "Having an ApplicationRunner bean means it ran" | Bean was only created/injected | Assert body in Boot test, not mere presence |
| "Context runner refresh doesn't run `@PostConstruct`" | Refresh still calls bean init | Test state after init |
| "SmartLifecycle doesn't start without SpringApplication" | LifecycleProcessor belongs to Framework context | Check `isAutoStartup` and running state |
| "Runner keeps context alive after callback" | Runner auto-closes when callback returns | Assert `@PreDestroy` after `run` |
| "Context runner failure guarantees `ApplicationFailedEvent`" | Doesn't go through Boot failure pipeline | Assert `getStartupFailure`; test Boot separately |
| "`@EventListener(ApplicationReadyEvent)` in context runner must fire" | No Boot ready event | Invoke real Boot startup |
| "Using `withInitializer` triggers ApplicationContextInitializedEvent" | Customizer does not emit Boot events | Distinguish initializer callback from Boot event |
| "`withPropertyValues` simulates the full Config Data API" | Not full environment bootstrap | Use integration tests with real config sources |
| "WebApplicationContextRunner opens a real port" | Web test context is not an embedded server | Use RANDOM_PORT/process HTTP |
| "ApplicationAvailability must exist in the runner" | Boot availability bean is not auto-guaranteed | Assert only when registered/present |
| "Runner scans the entire app and all auto-configs by default" | Only explicitly loaded configs | Use explicit `withConfiguration`/`withUserConfiguration` |
| "Every auto-config must be tested with full `@SpringBootTest`" | Heavy tests, hard to isolate conditions | Use context runner for combinatorial tests |
| "Having Spring Boot test dependency means tests run in native image" | Runner has native image limitations | Choose native-specific testing |
| "Order between two CommandLineRunners without @Order is fixed" | Default ties promise no business order | Use `@Order` or `Ordered` |
| "Failure tests must assert top-level IllegalStateException" | Bean factory may wrap exceptions | Assert root cause |
| "Runner callback closes context before inner assertions" | Context remains open inside callback | Assert shutdown after callback |
| "Full Boot test once = every test restarts" | Context cache may reuse contexts | Understand cache scope; use `@DirtiesContext` when truly needed |
| "Safe to open network and leave workers open in runner tests" | SmartLifecycle auto-start is real | Fake resources, timeouts, cleanup |
| "SpringApplication.run always calls System.exit" | Boot run does not equal JVM exit | Process exit codes are a separate responsibility |

### 12.1. Checklist for testing a Spring Boot milestone

1. Does the milestone to verify belong to **Spring Framework context** or **SpringApplication**?
2. If it is bean init/`ContextRefreshedEvent`/`SmartLifecycle`, context runner suffices.
3. If it is Boot started/ready/runners/availability, use `SpringApplication.run`/integration tests.
4. Determine whether the listener registers **before or after** the event; early events require listeners outside the context.
5. Verify the bean under test is actually loaded via `withUserConfiguration`/`withConfiguration`.
6. Use `withPropertyValues` for conditional logic, keeping test environment scope in mind.
7. If the context failed, assert `getStartupFailure`; do not try to fetch beans when refresh failed.
8. For close/destroy, record markers in a collector outside the context and assert after the callback.
9. If `SmartLifecycle` starts an async task, wait for completion/cleanup properly; never guess timing with sleep.
10. Do not assert order among beans/runners lacking an `@Order`/phase/dependency contract.
11. Never treat `ContextRefreshedEvent` as proof that Boot published readiness.
12. When a real socket/network is needed, switch to a web server integration test.
13. Inspect the root cause/condition evaluation report when expected beans are missing.
14. If tests differ between local JVM and native image, check framework/test tool limits.
15. Never put secrets/production systems into a context runner test merely because it is "fast".

## 13. Self-check questions

**Question 1.** Does `ApplicationContextRunner.run` call `SpringApplication.run`?

**Answer:** No. It creates/refreshes a context configured for testing and auto-closes it; thus it does not run the Boot startup pipeline.

**Question 2.** Is `ContextRefreshedEvent` emitted when the runner refreshes successfully?

**Answer:** Yes, it is a Spring Framework context event.

**Question 3.** Is a `SmartLifecycle(isAutoStartup=true)` bean started in the context runner?

**Answer:** Yes, because `LifecycleProcessor.onRefresh` is part of context refresh.

**Question 4.** Does `@PostConstruct` execute inside the context runner?

**Answer:** Yes, when the bean is instantiated by Spring via the appropriate mechanism, such as non-lazy singletons in the example.

**Question 5.** Does the existence of an `ApplicationRunner` bean mean its `run(ApplicationArguments)` body was called?

**Answer:** No. Inside the context runner, `SpringApplication` does not orchestrate calling startup runners.

**Question 6.** Is `ApplicationStartedEvent` automatically emitted by the context runner after refresh?

**Answer:** No. This event belongs to the `SpringApplication` pipeline.

**Question 7.** Is `ApplicationReadyEvent` automatically emitted when the runner callback starts?

**Answer:** No. The test callback is not a Boot readiness event.

**Question 8.** Why shouldn't you assert `ReadinessState.ACCEPTING_TRAFFIC` merely from an active context?

**Answer:** Because Boot publishes readiness after runners/ready events; the context runner does not traverse those milestones and may not even have the `ApplicationAvailability` bean.

**Question 9.** If a `@Bean` factory throws during context runner refresh, which API should be used?

**Answer:** `context.getStartupFailure()` and AssertJ assertions on startup failure/root cause.

**Question 10.** Does the runner test automatically emit `ApplicationFailedEvent` when context refresh fails?

**Answer:** Not per the `SpringApplication` contract; it is a test context failure.

**Question 11.** When is `ContextClosedEvent` emitted in the test?

**Answer:** When the runner closes the context after the callback on the normal closing path.

**Question 12.** How do you verify `@PreDestroy` without depending on an already-closed context state?

**Answer:** Use an external collector and assert after `runner.run(...)` returns.

**Question 13.** How do you test `@ConditionalOnProperty` with two values without loading the whole app?

**Answer:** Create a base `ApplicationContextRunner`, use `withPropertyValues` for each case, and assert the bean graph.

**Question 14.** If you need to test which port the HTTP server binds, which runner should you use?

**Answer:** A web integration test with a real embedded server, such as `@SpringBootTest(webEnvironment=RANDOM_PORT)`, rather than relying solely on `ApplicationContextRunner`.

**Question 15.** Does `withInitializer` automatically cause `ApplicationContextInitializedEvent` to fire?

**Answer:** No. A custom context initializer runs, yet it does not replace Boot's event pipeline.

**Question 16.** Why not assert the order of two runners sharing the default order?

**Answer:** Spring Boot coordinates via comparator/ordering, but ties are not a business contract; add `@Order` or `Ordered` if order matters.

**Question 17.** Is `ApplicationContextRunner` suitable for running inside a native image per Boot 3.3?

**Answer:** No, per the limitation noted in Spring Boot 3.3 docs; a separate native testing strategy is required.

**Question 18.** To prove `ApplicationStartedEvent` arrives before runners and `ApplicationReadyEvent` after runners, which approach should you choose?

**Answer:** Start a real `SpringApplication` with properly registered listeners/collectors and assert milestone ordering, as in Test B.

## 14. Summary and references

Core takeaways:

1. **`ApplicationContextRunner` is a context-layer test tool**: builds a small context, refreshes it, passes it to a callback for assertions, and auto-closes it.
2. **Context lifecycle still runs for real**: bean creation, injection, `@PostConstruct`, `SmartLifecycle.start()`, `ContextRefreshedEvent`, and close/stop/destroy callbacks when the runner closes the context.
3. **`SpringApplication` milestones do not auto-execute**: `ApplicationStartingEvent`, `ApplicationStartedEvent`, `ApplicationRunner`/`CommandLineRunner`, `ApplicationReadyEvent`, availability events, and Boot's `ApplicationFailedEvent`.
4. **`ContextRefreshedEvent ≠ ApplicationReadyEvent`**. An active context does not prove the app is ready or runners have completed.
5. **Context failure differs from Boot startup failure**: `getStartupFailure()` in the runner does not automatically trigger Boot's `FailureAnalyzer`/`FailureAnalysisReporter`.
6. **Separate test layers**: use context runner for conditions/beans/context lifecycle, then add `SpringApplication.run`/`@SpringBootTest`/process tests for events, runners, HTTP, availability, and real startup failures.
7. **The test auto-closes the context** after the callback; assert stop/destruction outside the callback via a collector. Never leave real background workers running/hanging inside a context runner.
8. **Correct dependency**: `ApplicationContextRunner` belongs to `spring-boot-test`, typically included via `spring-boot-starter-test` in `testImplementation`.

Official references corresponding to Spring Boot 3.3.13:

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `ApplicationContextRunner`, `AutoConfigurations.of`, properties, user config, FilteredClassLoader; native image note.
- [Spring Boot 3.3.13 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): non-web context and default `AnnotationConfigApplicationContext`.
- [Spring Boot 3.3.13 — AbstractApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html): `run`/`prepare`, `withBean`, `withConfiguration`, `withUserConfiguration`, `withPropertyValues`, and auto-close.
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): Boot events, started/ready, runners, availability, and startup failure.
- [Spring Boot 3.3.13 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): bootstrapping, context refresh, and `CommandLineRunner` callbacks.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, web environment, and test context cache.
- [Spring Framework 6.1 — AbstractApplicationContext](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): refresh/close, `ContextRefreshedEvent`, `ContextClosedEvent`, and lifecycle processor.

**Conclusion:** when reading the name `ApplicationContextRunner.run`, do not interpret the word "run" in the sense of `SpringApplication.run`. It proves **the context can refresh and beans honor their internal contracts**; to prove **the Boot application has started, executed runners, become ready, published availability, or reported startup failure**, you must run the `SpringApplication` orchestrator in an appropriate test.
