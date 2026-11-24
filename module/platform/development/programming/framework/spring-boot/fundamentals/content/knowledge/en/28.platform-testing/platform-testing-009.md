# Testing Init, Runners, Events, and Resource Cleanup

A Spring Boot application is more than APIs or business-logic services. Before becoming ready to serve traffic, the application must **instantiate beans, configure infrastructure components, execute startup tasks, and publish lifecycle events**. When stopping, it must stop accepting new work and **release connections, threads, executors, and managed resources**.

Bugs in these phases may never appear in ordinary business-logic unit tests. For example:

- A bean passes only in the IDE because `@PostConstruct` depends on a local file.
- An `ApplicationRunner` exists in the context yet is never actually invoked by a minimal context test.
- A listener misses `ApplicationReadyEvent` because it was registered after Boot already emitted the event.
- A runner starts an async task and returns immediately, causing Boot to report ready before data is prepared.
- A singleton fails to shut down a thread pool when the context closes.
- A test expects `@PreDestroy` to run after every `@Test`, yet Spring keeps the context cached.

This lesson—**Spring Boot Fundamentals → Platform Testing → Testing Init, Runners, Events, and Resource Cleanup**—focuses on structuring purposeful tests: accurately verifying bean lifecycles, runners, startup events, failure paths, and shutdown.

## 1. Lifecycle map to test

A successful startup typically follows these general milestones:

~~~text
SpringApplication.run(args)
         |
         v
Prepare Environment
         |
         v
Create and refresh ApplicationContext
         |
         +-- Instantiate eager singletons
         +-- Inject dependencies
         +-- @PostConstruct / InitializingBean
         +-- @Bean(initMethod = ...)
         +-- SmartLifecycle.start()
         |
         v
ApplicationStartedEvent
         |
         v
ApplicationRunner / CommandLineRunner
         |
         v
ApplicationReadyEvent
         |
         v
Publish readiness to accept traffic
         |
         v
Application running
         |
         v
Close ApplicationContext
         |
         +-- ContextClosedEvent
         +-- SmartLifecycle.stop(...)
         +-- @PreDestroy / DisposableBean / destroy method
         |
         v
Resources released
~~~

The diagram highlights only the main milestones of a standard startup and shutdown path. Exact details of callbacks, listeners, bean scopes, context hierarchies, and execution threads depend on actual configuration.

Several crucial points:

1. **An initialized bean does not mean runners have run.**
2. **A refreshed context does not mean Spring Boot has emitted `ApplicationReadyEvent`.**
3. **`ApplicationReadyEvent` does not automatically guarantee async work has finished.**
4. **`ContextClosedEvent` does not signify that all destroy callbacks have completed.**
5. **Creating an object with `new` does not cause Spring to invoke its lifecycle callbacks.**

Proper testing picks the observation point matching what needs to be proven.

## 2. Choosing the right test level

| Goal | Suitable harness | Do not assume |
|---|---|---|
| Pure logic of runner, init, or cleanup | JUnit 5 unit test | Must boot a full Spring context |
| Bean init, dependency injection, destroy callbacks | `AnnotationConfigApplicationContext` or `ApplicationContextRunner` | Small context tests automatically run Boot runners |
| Bean registration conditions, auto-configuration | `ApplicationContextRunner` | Needs a real web server |
| Runner actually runs during startup | `SpringApplication` or `@SpringBootTest` | Bean existence means runner executed |
| Boot startup events | Listener registered early before `SpringApplication.run(...)` | Listener created in `@Test` catches already-published startup events |
| Cleanup at a deterministic moment | Test manually creates and calls `context.close()` | Spring TestContext closes the context after every method |
| Readiness, graceful shutdown, process exit | Integration/system test | Unit tests suffice to prove deployment behavior |

A broad test is closer to production yet slower and harder to control. A small test is fast yet proves only a narrow contract. **Have complementary test layers rather than cramming every condition into one `@SpringBootTest`.**

## 3. Spring Boot testing libraries

In Maven, if the project uses compatible Spring Boot version management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

In Gradle Groovy DSL:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The test starter typically provides JUnit Jupiter, Spring Test, AssertJ, and other useful libraries; exact contents depend on the Boot version and project setup.

In the examples, we use JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
~~~

For Spring Boot 3.x, `@PostConstruct` and `@PreDestroy` use the `jakarta.annotation` namespace. Older Spring Boot projects may use a different namespace; match your project's library set.

## 4. Testing @PostConstruct and @PreDestroy on real beans

Let's create a simple bean that records init and destroy counts.

File `LifecycleProbe.java`:

~~~java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

public class LifecycleProbe {

    private final String requiredValue;
    private final AtomicInteger initCalls = new AtomicInteger();
    private final AtomicInteger destroyCalls = new AtomicInteger();

    public LifecycleProbe(String requiredValue) {
        this.requiredValue = requiredValue;
    }

    @PostConstruct
    public void initialize() {
        if (requiredValue == null || requiredValue.isBlank()) {
            throw new IllegalArgumentException(
                    "requiredValue must be configured");
        }
        initCalls.incrementAndGet();
    }

    @PreDestroy
    public void destroy() {
        destroyCalls.incrementAndGet();
    }

    public int initCount() {
        return initCalls.get();
    }

    public int destroyCount() {
        return destroyCalls.get();
    }
}
~~~

File `LifecycleConfiguration.java`:

~~~java
package com.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LifecycleConfiguration {

    @Bean
    LifecycleProbe lifecycleProbe() {
        return new LifecycleProbe("configured");
    }
}
~~~

We manually create and close the context in the test:

~~~java
package com.example.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LifecycleProbeTest {

    @Test
    void callsInitOnRefreshAndDestroyOnClose() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        LifecycleProbe probe = null;

        try {
            context.register(LifecycleConfiguration.class);
            context.refresh();

            probe = context.getBean(LifecycleProbe.class);

            assertEquals(1, probe.initCount());
            assertEquals(0, probe.destroyCount());
        } finally {
            context.close();
        }

        assertEquals(1, probe.destroyCount());
    }
}
~~~

This is a **context-level test**. Spring actually constructs the bean, processes init annotations, and destroys the bean when closing the context.

### What does this test prove?

- A singleton bean was initialized by the container.
- `@PostConstruct` ran before the bean was used.
- `@PreDestroy` had not yet run while the context remained open.
- After `context.close()` completed, the destroy callback ran.

### What does this test not prove?

- `ApplicationRunner` executed.
- `ApplicationReadyEvent` was published.
- A web server is serving requests.
- Async tasks submitted by the bean finished.
- Real external resources actually stopped if the callback only flips a flag.

Other tests are needed to prove those.

## 5. @PostConstruct differs from a plain Java method call

If a test writes:

~~~java
LifecycleProbe probe = new LifecycleProbe("configured");
probe.initialize();

assertEquals(1, probe.initCount());
~~~

it only confirms `initialize()` does what was coded. Spring does not participate. Thus, the test cannot catch forgetting to register the bean, misconfigured annotation processing, or a bean instantiated outside the container.

Both styles serve different roles:

- Direct unit method tests verify pure init logic.
- Context-level tests verify **framework wiring and lifecycle**.

Complex init logic should be extracted into a directly testable method, leaving the annotation simply to invoke that logic:

~~~java
@PostConstruct
void initialize() {
    validateConfiguration();
}

void validateConfiguration() {
    if (endpoint == null || endpoint.isBlank()) {
        throw new IllegalStateException(
                "Missing endpoint");
    }
}
~~~

Avoid putting heavy network operations, migrations, or long data loads inside `@PostConstruct` when the task belongs in a runner, dedicated background task, or an explicit readiness check.

## 6. Testing init failures with ApplicationContextRunner

`ApplicationContextRunner` is handy when booting a small context, inspecting beans, and observing errors. It builds a context for each callback and manages closing it afterward.

A bean that intentionally fails:

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;

public class BrokenBean {

    @PostConstruct
    void init() {
        throw new IllegalStateException(
                "simulated initialization failure");
    }
}
~~~

Test:

~~~java
package com.example.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class BrokenBeanTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BrokenConfig.class);

    @Test
    void reportsFailureWhenInitThrows() {
        runner.run(context -> {
            assertNotNull(context.getStartupFailure());
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class BrokenConfig {

        @Bean
        BrokenBean brokenBean() {
            return new BrokenBean();
        }
    }
}
~~~

`context.getStartupFailure()` exposes exceptions thrown while building the context. You can inspect the cause chain when asserting a specific root error.

**Important limitation:** `ApplicationContextRunner` does not automatically invoke `ApplicationRunner` or `CommandLineRunner` beans the way `SpringApplication.run(...)` does. Therefore, a startup failure in a context runner does not equate to Spring Boot emitting `ApplicationFailedEvent`.

## 7. Testing other init mechanisms

Beyond `@PostConstruct`, Spring offers other callbacks:

| Mechanism | Meaning | Testing approach |
|---|---|---|
| Constructor | Java object construction | Unit test |
| `@PostConstruct` | Post-injection callback | Context-level test |
| `InitializingBean.afterPropertiesSet()` | Spring callback after properties are populated | Context-level test |
| `@Bean(initMethod="...")` | Init method declared on bean definition | Context-level test |
| `SmartLifecycle.start()` | Starts operation when lifecycle processor starts bean | Context-level test |
| `ApplicationRunner.run(...)` | Task after context refresh in Boot startup | Unit test or full Boot startup test |

`InitializingBean` example:

~~~java
public class EndpointValidator
        implements InitializingBean {

    private final String endpoint;

    public EndpointValidator(String endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public void afterPropertiesSet() {
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException(
                    "endpoint is required");
        }
    }
}
~~~

`@Bean(initMethod)` example:

~~~java
@Bean(initMethod = "warmUp")
SearchIndex searchIndex() {
    return new SearchIndex();
}
~~~

`SearchIndex` is an assumed type with a `warmUp()` method. To verify Spring invoked the callback, use a context-level test with the bean definition above.

Avoid piling multiple init mechanisms onto the same bean unnecessarily. Having **one clear owner and one init contract** keeps code readable and tests clear.

## 8. Unit testing ApplicationRunner

`ApplicationRunner` receives `ApplicationArguments` and is commonly used for tasks running after the context refreshes.

Example of a runner that simply passes a mode to a service:

~~~java
package com.example.startup;

import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;

public class StartupModeRunner implements ApplicationRunner {

    public interface ModeTask {
        void execute(String mode);
    }

    private final ModeTask task;

    public StartupModeRunner(ModeTask task) {
        this.task = task;
    }

    @Override
    public void run(ApplicationArguments args) {
        String mode = resolveMode(args);
        task.execute(mode);
    }

    static String resolveMode(ApplicationArguments args) {
        if (!args.containsOption("mode")) {
            return "normal";
        }

        List<String> values = args.getOptionValues("mode");

        if (values == null || values.isEmpty() ||
                values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "--mode requires a value");
        }

        return values.get(0);
    }
}
~~~

`ModeTask` is kept as an interface so unit tests can substitute a fake easily.

~~~java
package com.example.startup;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StartupModeRunnerTest {

    @Test
    void passesModeToTask() throws Exception {
        AtomicReference<String> actual =
                new AtomicReference<>();

        StartupModeRunner runner =
                new StartupModeRunner(actual::set);

        runner.run(new DefaultApplicationArguments(
                "--mode=safe"));

        assertEquals("safe", actual.get());
    }

    @Test
    void defaultsWhenModeIsAbsent() throws Exception {
        AtomicReference<String> actual =
                new AtomicReference<>();

        StartupModeRunner runner =
                new StartupModeRunner(actual::set);

        runner.run(new DefaultApplicationArguments());

        assertEquals("normal", actual.get());
    }

    @Test
    void rejectsMissingModeValue() {
        StartupModeRunner runner =
                new StartupModeRunner(mode -> { });

        assertThrows(
                IllegalArgumentException.class,
                () -> runner.run(
                        new DefaultApplicationArguments("--mode"))
        );
    }
}
~~~

These tests prove the runner parses inputs and calls its dependency properly. They **do not prove Spring Boot discovers and executes the runner at startup**; the integration test below covers that.

### When should you unit test directly?

- Parsing `ApplicationArguments`.
- Validating startup options.
- Calling services in the right order inside runner code.
- Exception handling or fallback logic.
- Testing logic with fakes instead of real databases or networks.

Separating logic from the framework keeps these checks fast and deterministic.

## 9. Unit testing CommandLineRunner

`CommandLineRunner` receives the raw `String... args` array directly:

~~~java
package com.example.startup;

import org.springframework.boot.CommandLineRunner;

public class ArgumentCountRunner
        implements CommandLineRunner {

    private final java.util.function.IntConsumer sink;

    public ArgumentCountRunner(
            java.util.function.IntConsumer sink
    ) {
        this.sink = sink;
    }

    @Override
    public void run(String... args) {
        sink.accept(args.length);
    }
}
~~~

Test:

~~~java
@Test
void countsRawArguments() throws Exception {
    AtomicInteger actual = new AtomicInteger(-1);

    ArgumentCountRunner runner =
            new ArgumentCountRunner(actual::set);

    runner.run("--verbose", "source.csv");

    assertEquals(2, actual.get());
}
~~~

Both runner types participate in Spring Boot startup, but **`ApplicationRunner` receives an `ApplicationArguments` object**, whereas **`CommandLineRunner` receives raw argument strings**.

For CLI programs with structured options, `ApplicationRunner` is usually more convenient. For simple command-line arguments, `CommandLineRunner` works well too.

## 10. Integration: verifying Boot actually invokes the runner

A `@SpringBootTest` can boot a minimal configuration and confirm the runner executed.

~~~java
package com.example.startup;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = RunnerBootTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class RunnerBootTest {

    @Autowired
    Counter counter;

    @Test
    void runnerIsCalledAtStartup() {
        assertEquals(1, counter.calls.get());
    }

    static class Counter {
        final AtomicInteger calls = new AtomicInteger();
    }

    @SpringBootConfiguration
    static class TestApplication {

        @Bean
        Counter counter() {
            return new Counter();
        }

        @Bean
        ApplicationRunner runner(Counter counter) {
            return args -> counter.calls.incrementAndGet();
        }
    }
}
~~~

In a freshly started Spring Boot test context, the runner is invoked once `SpringApplication` finishes refreshing and runs its runners.

### Be careful with context caching

Spring TestContext caches contexts across tests sharing matching configurations:

- Never assume a runner executes once before **every `@Test` method**.
- Never assume `@PostConstruct` re-runs per method.
- A mutable singleton can retain state from an earlier test.
- Cached contexts also mean shutdown cannot be observed at `@AfterEach`.

If a test needs strict control over **one start and one close**, creating a `SpringApplication` directly inside the test is clearer.

## 11. Testing runner execution order

Spring Boot orders runners based on `@Order` or `Ordered`.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class RunnerOrderingConfiguration {

    @Bean
    @Order(10)
    ApplicationRunner validateSchema(StepRecorder recorder) {
        return args -> recorder.record("schema");
    }

    @Bean
    @Order(20)
    CommandLineRunner loadCache(StepRecorder recorder) {
        return args -> recorder.record("cache");
    }
}
~~~

`StepRecorder` is an illustrative bean:

~~~java
public final class StepRecorder {

    private final List<String> steps =
            new CopyOnWriteArrayList<>();

    public void record(String step) {
        steps.add(step);
    }

    public List<String> snapshot() {
        return List.copyOf(steps);
    }
}
~~~

After a successful Boot startup containing both runners, a test can assert:

~~~java
assertEquals(
        List.of("schema", "cache"),
        recorder.snapshot()
);
~~~

Notes:

- `@Order` governs **runner invocation order**, not bean instantiation order.
- For two runners with the same order, never rely on an implicit sequence.
- If the first runner spawns a background thread and returns, there is no guarantee that thread finishes before the second runner runs.
- If two tasks genuinely depend on each other, explicit orchestration is better than multiple runners coupled through ordered side effects.

## 12. Testing runner failures

If a runner checks for a mandatory resource that is missing, startup should fail rather than continuing to serve traffic in a broken state:

~~~java
@Bean
ApplicationRunner verifyCatalog() {
    return args -> {
        throw new IllegalStateException(
                "Catalog is required before startup completes");
    };
}
~~~

At the unit level:

~~~java
@Test
void runnerPropagatesFailure() {
    ApplicationRunner runner = args -> {
        throw new IllegalStateException("missing catalog");
    };

    IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> runner.run(
                    new DefaultApplicationArguments())
    );

    assertEquals("missing catalog", error.getMessage());
}
~~~

This test only proves invoking the runner throws an error. To verify **`ApplicationFailedEvent`**, you must go through `SpringApplication.run(...)`.

A failure integration test should verify:

1. The error escapes the runner.
2. `SpringApplication.run(...)` does not finish successfully.
3. A pre-registered listener receives the failure event.
4. The original error is not masked by a secondary error.
5. Container-managed resources are cleaned up per contract.

## 13. Spring Framework and Spring Boot events

Common events:

| Event | Origin | When to observe |
|---|---|---|
| `ContextRefreshedEvent` | Spring Framework | Context just finished refreshing |
| `ContextClosedEvent` | Spring Framework | Context begins closing |
| `ApplicationStartedEvent` | Spring Boot | Context refreshed, about to run runners |
| `ApplicationReadyEvent` | Spring Boot | Runners finished, Boot reaches ready milestone |
| `ApplicationFailedEvent` | Spring Boot | An error caused `SpringApplication`-managed startup to fail |
| `AvailabilityChangeEvent` | Spring Boot | Availability state changed |

Important facts for testing:

- `AnnotationConfigApplicationContext.refresh()` publishes `ContextRefreshedEvent`.
- That call **does not automatically publish `ApplicationStartedEvent` or `ApplicationReadyEvent`**.
- `context.close()` publishes `ContextClosedEvent` and orchestrates shutdown.
- `ApplicationFailedEvent` must be tested via a failing `SpringApplication` startup.

A test using the wrong context type may conclude a listener is broken when the expected event was never emitted at all.

## 14. Testing an event listener by publishing an event

For business events unrelated to startup, a small context suffices.

Event:

~~~java
package com.example.events;

public record CatalogUpdatedEvent(int version) {
}
~~~

Listener:

~~~java
package com.example.events;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class CatalogListener {

    private final AtomicInteger lastVersion =
            new AtomicInteger(-1);

    @EventListener
    public void onCatalogUpdated(CatalogUpdatedEvent event) {
        lastVersion.set(event.version());
    }

    public int lastVersion() {
        return lastVersion.get();
    }
}
~~~

Test:

~~~java
@Test
void dispatchesBusinessEvent() {
    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

    try {
        context.registerBean(CatalogListener.class);
        context.refresh();

        context.publishEvent(new CatalogUpdatedEvent(7));

        assertEquals(
                7,
                context.getBean(CatalogListener.class)
                        .lastVersion()
        );
    } finally {
        context.close();
    }
}
~~~

With the default synchronous multicaster, the listener runs during `publishEvent`. If the application configures an async event multicaster, tests must await an explicit completion signal rather than asserting immediately.

This test verifies **wiring and the handler**; it does not prove Boot publishes `ApplicationReadyEvent` at the right moment.

## 15. @RecordApplicationEvents: use it for its intended scope

Spring Test offers `@RecordApplicationEvents` and `ApplicationEvents` to observe events published during test execution.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@RecordApplicationEvents
class CatalogEventRecordingTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    ApplicationEvents events;

    @Test
    void recordsEventPublishedInTest() {
        publisher.publishEvent(new CatalogUpdatedEvent(9));

        long count = events.stream(
                CatalogUpdatedEvent.class
        ).count();

        assertEquals(1, count);
    }
}
~~~

The example assumes the event class and a compatible Spring Boot application already exist.

**Limitation:** startup events like `ApplicationStartedEvent` and `ApplicationReadyEvent` may have already been published **before the test method begins**. Therefore, do not expect `@RecordApplicationEvents` to capture startup milestones on a cached `@SpringBootTest` context.

To test those, attach listeners directly **before** invoking `SpringApplication.run(...)`.

## 16. Testing ApplicationStartedEvent, runners, and ApplicationReadyEvent

Example of a test constructing a `SpringApplication` with minimal configuration. To keep the example simple, a `static` recorder is used in a **sequential test**; when enabling parallel tests, replace it with a recorder that does not share state unexpectedly.

~~~java
package com.example.startup;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StartupOrderIntegrationTest {

    private static final List<String> STEPS = new ArrayList<>();

    @Test
    void startedThenRunnerThenReady() {
        STEPS.clear();

        SpringApplication application =
                new SpringApplication(TestApp.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        application.addListeners(
            (ApplicationListener<ApplicationStartedEvent>)
                event -> STEPS.add("started"),
            (ApplicationListener<ApplicationReadyEvent>)
                event -> STEPS.add("ready")
        );

        try (ConfigurableApplicationContext context =
                application.run("--spring.main.banner-mode=off")) {

            assertEquals(
                List.of("started", "runner", "ready"),
                List.copyOf(STEPS)
            );
        }
    }

    @SpringBootConfiguration
    static class TestApp {

        @Bean
        ApplicationRunner recordRunner() {
            return args -> STEPS.add("runner");
        }
    }
}
~~~

What this test proves:

- Listeners were registered before startup.
- Boot emitted `started` once the context refreshed.
- Boot executed the runner after `started`.
- Boot emitted `ready` after the runner succeeded.

### Avoid static recorders in parallel suites

In a large suite, concurrent tests touching a `static` field cause nondeterministic results. A safer option is an instance recorder injected into configurations/runners with a reference held by the test, or isolating test processes/classes to eliminate shared state.

What matters is verifying **the relative ordering**, not whether the recorder is static or a bean.

## 17. Testing ApplicationFailedEvent when a runner throws an exception

To capture the failure event, register the listener early on `SpringApplication`.

~~~java
package com.example.startup;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.*;

class StartupFailureIntegrationTest {

    @Test
    void publishesFailedEventForRunnerException() {
        AtomicReference<Throwable> failure =
                new AtomicReference<>();

        SpringApplication application =
                new SpringApplication(FailingApp.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        application.addListeners(
                (ApplicationListener<ApplicationFailedEvent>)
                    event -> failure.set(event.getException())
        );

        assertThrows(
                Exception.class,
                () -> application.run(
                        "--spring.main.banner-mode=off")
        );

        assertNotNull(failure.get());
    }

    @SpringBootConfiguration
    static class FailingApp {

        @Bean
        ApplicationRunner failingRunner() {
            return args -> {
                throw new IllegalStateException(
                        "simulated startup failure");
            };
        }
    }
}
~~~

The test verifies `SpringApplication` handles the error and publishes `ApplicationFailedEvent`. The outer exception may be wrapped; when checking the root cause, inspect `getCause()` rather than coupling tightly to a specific wrapper class.

### Why not use ApplicationContextRunner for this test?

Because `ApplicationContextRunner` does not run Boot's full startup sequence and does not invoke runners through the same pipeline. It fits bean initialization errors, **not Boot startup failure events**.

### Why not just create a @Component listener?

A bean-based listener might not even be created yet when startup fails early. For startup failure events, registering the listener directly on `SpringApplication` beforehand is far more reliable.

## 18. Testing ContextClosedEvent

`ContextClosedEvent` is published when the context starts closing.

~~~java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextClosedEvent;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ContextClosedEventTest {

    @Test
    void publishesCloseEvent() {
        AtomicInteger received = new AtomicInteger();

        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        context.addApplicationListener(
            (ApplicationListener<ContextClosedEvent>)
                event -> received.incrementAndGet()
        );

        context.refresh();

        assertEquals(0, received.get());

        context.close();

        assertEquals(1, received.get());
    }
}
~~~

This checks the event. However, **publishing the event does not mean all beans have finished their destroy callbacks**.

General sequence:

~~~text
context.close()
      |
      v
Publish ContextClosedEvent
      |
      v
Stop lifecycle components
      |
      v
Destroy managed singleton beans
      |
      v
close() completes
~~~

If verifying that a resource closed, assert that state **after `context.close()` returns**, not inside the `ContextClosedEvent` listener.

## 19. Common resource cleanup callbacks

| Mechanism | Usage | What to observe |
|---|---|---|
| `@PreDestroy` | Bean cleanup method | Was the method called before bean destruction? |
| `DisposableBean.destroy()` | Bean implements Spring interface | Did the destroy callback execute? |
| `@Bean(destroyMethod="close")` | Factory method declares cleanup | Was the resource closed when the context closed? |
| `AutoCloseable` / `Closeable` | Java resource contract | Did the owner close the resource? |
| `SmartLifecycle.stop(...)` | Stop active running components | Did stopping and callback completion work properly? |
| `try-with-resources` | Short-lived resource scope | Are streams/files/sockets closed even on errors? |

A bean may use multiple callbacks, though if they close the same resource, avoid double-close bugs or design idempotency explicitly.

## 20. Testing @Bean(destroyMethod) with a fake resource

Create a fake connection with a closed flag:

~~~java
package com.example.resources;

import java.util.concurrent.atomic.AtomicBoolean;

public class FakeConnection implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean();

    public boolean isClosed() {
        return closed.get();
    }

    public void send(String message) {
        if (closed.get()) {
            throw new IllegalStateException(
                    "Connection already closed");
        }
    }

    @Override
    public void close() {
        closed.set(true);
    }
}
~~~

Register the bean with an explicit destroy method:

~~~java
package com.example.resources;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FakeConnectionConfiguration {

    @Bean(destroyMethod = "close")
    FakeConnection fakeConnection() {
        return new FakeConnection();
    }
}
~~~

Test:

~~~java
package com.example.resources;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class ConnectionCleanupTest {

    @Test
    void closesResourceWhenContextCloses() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        FakeConnection resource;

        try {
            context.register(FakeConnectionConfiguration.class);
            context.refresh();

            resource = context.getBean(FakeConnection.class);

            assertFalse(resource.isClosed());
        } finally {
            context.close();
        }

        assertTrue(resource.isClosed());
    }
}
~~~

This test is more meaningful than merely asserting `@PreDestroy` incremented a counter: it verifies the fake resource transitioned to the closed state.

### Note on ownership

If a resource is created by a Spring bean and owned by Spring, callers should not manually call `close()`. Conversely, if a method borrows or creates a short-lived resource, it must close it via `try-with-resources`.

Avoid having both Spring and callers close the same resource inconsistently. A fake resource can count `close()` calls if you need to test the ownership contract.

## 21. DisposableBean and destroy callbacks

Spring provides the `DisposableBean` interface:

~~~java
public class DisposableWorker
        implements DisposableBean {

    private final AtomicBoolean destroyed =
            new AtomicBoolean();

    @Override
    public void destroy() {
        destroyed.set(true);
    }

    public boolean isDestroyed() {
        return destroyed.get();
    }
}
~~~

When the bean is managed by the container as an ordinary singleton, Spring invokes `destroy()` when destroying the bean during context shutdown.

Equivalent test flow:

~~~text
Create context
  -> register bean
  -> refresh
  -> assert isDestroyed() == false
  -> close
  -> assert isDestroyed() == true
~~~

In real code, import `org.springframework.beans.factory.DisposableBean` and `java.util.concurrent.atomic.AtomicBoolean`.

`@PreDestroy`, `DisposableBean`, and destroy methods all solve cleanup with different declaration styles. Choose one fitting your project's style and the resource's nature.

## 22. SmartLifecycle: start and stop vs. destroy

A component may be a consumer or worker that needs to **start** when the context is ready and **stop** during shutdown.

`SmartLifecycle` lets Spring coordinate start/stop by phase.

~~~java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;

public class ControlledWorker implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean();

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public void stop(Runnable callback) {
        stop();
        callback.run();
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
        return 0;
    }
}
~~~

Test:

~~~java
@Test
void workerStartsAndStopsWithContext() {
    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

    context.registerBean(ControlledWorker.class);
    context.refresh();

    ControlledWorker worker =
            context.getBean(ControlledWorker.class);

    assertTrue(worker.isRunning());

    context.close();

    assertFalse(worker.isRunning());
}
~~~

### Why must stop(Runnable) invoke the callback?

In phased shutdown, Spring uses the callback to know when a component finished stopping. If stop logic is synchronous, call the callback immediately after stopping. If stop logic is asynchronous, invoke the callback **only once stopping actually completes**, not immediately upon submitting the stop request.

### Meaning of phase

Typically:

- Startup: lower phases start before higher phases.
- Shutdown: higher phases stop before lower phases.

When a consumer depends on a connection pool, choose phases so the consumer stops accepting work before the resource it needs is closed. Tests can use a recorder to verify ordering relationships.

## 23. Testing cleanup order with a recorder

A simple technique is creating a recorder:

~~~java
public final class LifecycleRecorder {

    private final List<String> events =
            new CopyOnWriteArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

Beans record milestones:

~~~text
consumer-start
connection-open
consumer-stop
connection-close
~~~

After `context.close()` returns, the test can check:

~~~java
List<String> timeline = recorder.snapshot();

assertTrue(timeline.contains("consumer-stop"));
assertTrue(timeline.contains("connection-close"));

assertTrue(
        timeline.indexOf("consumer-stop") <
        timeline.indexOf("connection-close")
);
~~~

Only assert ordering if it is an **architectural requirement**. Avoid asserting the full internal sequence of Spring events or any order not guaranteed by the framework, as tests become brittle across upgrades.

Crucially, `ContextClosedEvent` fires before many stop/destroy actions, so do not record `context-closed` assuming it is the final marker in the timeline.

## 24. Asynchrony and the "runner returned, work unfinished" risk

Consider a runner:

~~~java
@Bean
ApplicationRunner prepareCatalog(
        Executor executor,
        CatalogService catalogService
) {
    return args -> {
        executor.execute(catalogService::prepare);
    };
}
~~~

`CatalogService` is an illustrative service. Once `executor.execute(...)` accepts the task, the runner returns right away.

Consequence:

~~~text
ApplicationStartedEvent
        |
        v
Runner submits prepare()
        |
        v
Runner returns
        |
        v
ApplicationReadyEvent
        |
        v
Background task may still be running
~~~

A test verifying only `ApplicationReadyEvent` **does not prove the task finished**.

Test separately:

- Was the task submitted?
- Did the task succeed or fail?
- Does readiness report unready while the task is still incomplete?
- When the task fails, does the system retry or fail fast?
- During shutdown, is the task canceled or awaited per policy?

### Use futures or latches instead of Thread.sleep

An interface can model completion state:

~~~java
public interface CatalogPreparation {
    CompletableFuture<Void> prepareAsync();
}
~~~

In a test using a fake:

~~~java
CompletableFuture<Void> completion =
        new CompletableFuture<>();

// Fake prepareAsync() returns completion.
CompletableFuture<Void> actual = fake.prepareAsync();

assertFalse(actual.isDone());

completion.complete(null);

assertTrue(actual.isDone());
~~~

`fake` is just a placeholder for a concrete test double. The point is that the test **actively controls completion** instead of waiting an arbitrary duration.

When using `@Async`, remember that self-invocation inside the same bean bypasses the Spring proxy and will not switch threads. An integration test should verify the call path through the proxy whenever asynchrony is a requirement.

## 25. Testing asynchronous event listeners

If a listener uses `@Async` or the application configures an async event multicaster, `publishEvent(...)` can return before the listener finishes processing.

Example:

~~~java
@Component
public class CatalogNotificationListener {

    private final CountDownLatch processed =
            new CountDownLatch(1);

    @Async
    @EventListener
    public void onCatalogUpdated(CatalogUpdatedEvent event) {
        try {
            // Handle event.
        } finally {
            processed.countDown();
        }
    }

    public boolean awaitProcessed(Duration timeout)
            throws InterruptedException {
        return processed.await(
                timeout.toMillis(),
                TimeUnit.MILLISECONDS
        );
    }
}
~~~

This assumes `@EnableAsync` is enabled, an executor is configured, and the relevant types are imported. It demonstrates tracking event completion.

Test:

~~~java
publisher.publishEvent(new CatalogUpdatedEvent(11));

assertTrue(
        listener.awaitProcessed(Duration.ofSeconds(2))
);
~~~

If a listener can receive multiple events, a single-use latch is insufficient to distinguish each handling; use counters, queues, or event-ID-keyed futures.

**Do not call `Thread.sleep(500)` and then assert**, because results depend on CI speed or CPU load, producing flaky tests.

## 26. TestContext cache and @DirtiesContext

Spring TestContext caches contexts across tests with compatible configurations to save startup time.

Consequences:

| Wrong assumption | What actually happens |
|---|---|
| Every `@Test` runs `@PostConstruct` | Bean comes from an earlier cached context |
| Every test method runs the runner | Runner executes only during actual Boot startup |
| `@AfterEach` means context closed | Context may stay alive in cache |
| Listener in method catches ready event | Event already fired before the test method ran |
| Mutable singleton resets between methods | State may persist across tests |

`@DirtiesContext` asks Spring to evict the context from cache:

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
@SpringBootTest
class SpecialIntegrationTest {
    // ...
}
~~~

Yet do not overuse it:

- Slows down the suite by forcing context rebuilds.
- Not the best tool for observing close within **a single method**.
- Can hide a test design relying on shared mutable state.

When you need **create → refresh → assert → close → assert**, manage a dedicated context directly inside the test.

## 27. Notes on prototype, lazy beans, and init counts

Lifecycle callback counts depend on bean scope and instantiation timing:

- Eager singletons are usually created once per context.
- Lazy singletons may not initialize until first use.
- Prototypes create a new instance on each request.
- Parent/child contexts can propagate events along the hierarchy.
- A fresh context created after closing creates fresh bean instances.

Notably, **Spring does not manage full destroy lifecycles for prototype instances the way it does for singletons**. Callers requesting prototype resources must track ownership and perform appropriate cleanup.

Therefore, when asserting `initCount() == 1` or `destroyCount() == 1`, state the scope clearly: **a singleton in a fresh context created and closed once by the test**.

Do not generalize a condition true in that test into a rule for all bean scopes.

## 28. What if shutdown happens after partial initialization?

A tricky failure is when a context builds several beans and then fails on the next one:

~~~text
Create connection pool  -> success
Create catalog bean     -> success
Create payment client   -> failure
SpringApplication.run   -> failed
~~~

In that scenario, distinguish:

1. Resources already registered as Spring-managed beans.
2. Objects constructed locally inside a factory method that never returned as beans.
3. Async tasks already launched outside Spring's lifecycle.

Spring cleans up already-created singletons when a context refresh fails. However, if a constructor or factory method opens a resource and throws before returning the resource as a managed bean, **the application itself may need to close it in a `try/finally`**.

A well-controlled test can:

- Create a fake resource with a `closed` flag.
- Register the resource as a bean.
- Register a subsequent bean that throws during init.
- Boot the context and assert failure.
- Verify the resource was cleaned up per contract.

Never assume Spring automatically detects and closes every `new` object, especially objects never handed to the container.

## 29. Testing cleanup failures and idempotency

Cleanup can fail due to network errors, timeouts, or already-closed resources.

Cleanup design should decide:

- If called twice, is the operation safe?
- If the resource never finished initializing, does cleanup handle it?
- Should cleanup exceptions be logged or reported?
- Is a timeout needed so shutdown cannot hang?
- Must data be flushed or committed before closing?
- Must active tasks stop before closing dependencies?

Example:

~~~java
@PreDestroy
public void shutdown() {
    if (!closing.compareAndSet(false, true)) {
        return;
    }

    try {
        client.close();
    } catch (Exception error) {
        log.warn("Client shutdown was not clean", error);
    }
}
~~~

Fields `closing`, `client`, and `log` belong to the illustrative implementation, not Spring APIs.

Do not assume `context.close()` will rethrow every exception raised inside `@PreDestroy`. Spring may log it and continue destroying remaining beans. Tests should check the resource's actual contract and error reporting rather than an internal wrapper exception.

## 30. Releasing executors and threads

A common hazard:

~~~java
public void process() {
    ExecutorService executor =
            Executors.newSingleThreadExecutor();

    executor.submit(this::doWork);

    // Executor is not shut down.
}
~~~

Every call spawns a new thread with no owner responsible for stopping it.

In a Spring Boot application, you can:

- Use a Spring-managed executor bean.
- Declare matching destroy lifecycle hooks.
- Stop accepting new tasks on shutdown.
- Await or cancel running tasks per policy.
- Bound wait times with timeouts.
- Test with fake executors or `CompletionStage` instead of guessing threads stopped.

If using `SmartLifecycle` to stop a consumer, call `stop(Runnable callback)` once stopping actually finishes. If using a self-managed executor with its own shutdown, test directly that the executor shut down and key tasks finished or canceled.

**`context.close()` returning does not prove all application-spawned threads stopped.**

## 31. Testing with CountDownLatch instead of sleep

A helpful Java utility is `CountDownLatch`:

~~~java
public final class CloseSignal {

    private final CountDownLatch closed =
            new CountDownLatch(1);

    public void markClosed() {
        closed.countDown();
    }

    public boolean awaitClosed(Duration timeout)
            throws InterruptedException {

        return closed.await(
                timeout.toMillis(),
                TimeUnit.MILLISECONDS
        );
    }
}
~~~

After requesting shutdown:

~~~java
context.close();

assertTrue(
        closeSignal.awaitClosed(Duration.ofSeconds(2))
);
~~~

Benefits:

- Waits for the exact signal under observation.
- Wastes no fixed sleep time when the event occurs early.
- Enforces a finite timeout if shutdown hangs.
- Expresses what "closed" means clearly.

If cleanup is synchronous, no latch is needed; asserting right after `close` is simpler and more reliable.

## 32. @Timeout: preventing a hung test suite

JUnit 5 provides `@Timeout`:

~~~java
@Test
@Timeout(5)
void startupCompletesWithinReasonableLimit() {
    // Boot small context with fake dependencies.
}
~~~

`@Timeout` does not replace timeouts on HTTP clients, database queries, or shutdown callbacks. It only prevents a test from running past a chosen upper limit.

A test involving networking or background threads still needs:

- Timeouts on real operations.
- Cleanup in `finally`.
- Suitable fake or sandbox dependencies.
- Task cancellation on timeout.
- Generous bounds to avoid CI flakiness.

Never rely on random network failures to "test retries"; configure fake dependencies to throw errors deterministically.

## 33. Cleaning up test-created resources

If a test opens a stream or file, it must close it even when an assertion fails.

~~~java
@Test
void readsTestFixture() throws Exception {
    InputStream input = getClass()
            .getResourceAsStream("/fixtures/message.txt");

    assertNotNull(input);

    try (InputStream stream = input) {
        String content = new String(
                stream.readAllBytes(),
                StandardCharsets.UTF_8
        );

        assertFalse(content.isBlank());
    }
}
~~~

`getResourceAsStream(...)` can return `null` if the fixture is missing, so the test checks before reading.

For temporary files:

~~~java
@TempDir
Path temporaryDirectory;
~~~

JUnit `@TempDir` manages a temporary directory for the test. For other resources such as sockets, consumers, or executors, tests still need explicit cleanup.

## 34. Never test shutdown via System.exit in JUnit

A test like this is inappropriate:

~~~java
@Test
void shutdownHookRuns() {
    System.exit(0);
}
~~~

It can terminate the JVM running the entire test suite.

To test the Spring lifecycle, use:

~~~java
SpringApplication app =
        new SpringApplication(TestApplication.class);

app.setWebApplicationType(WebApplicationType.NONE);

try (ConfigurableApplicationContext context =
        app.run("--spring.main.banner-mode=off")) {

    // Assertions while app is running.
}
// Context closed by try-with-resources.
~~~

If you need to test an application receiving `SIGTERM` and performing real graceful shutdown, launch the executable artifact in a **child process** in a separate system test, send a controlled signal, and inspect the exit code and cleanup. Do not expect shutdown hooks to run when a process receives `SIGKILL` or loses power.

## 35. Graceful shutdown: also test in-flight work

For a Spring Boot web app, you can configure:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

A system test can:

1. Start the server.
2. Initiate a request taking long enough to stay in flight.
3. Trigger shutdown.
4. Confirm the server stops accepting new requests per server behavior.
5. Verify the in-flight request completes or times out as configured.
6. Verify background consumers and workers stop per policy.
7. Verify the process exits and resources closed.

**Web server graceful shutdown does not automatically manage all custom background tasks.** Test workers and executors separately if they are critical parts of the application.

## 36. Common mistakes when testing init, runners, and cleanup

| Symptom | Common cause | Fix |
|---|---|---|
| `@PostConstruct` does not run | Instantiated via `new`, bypassing Spring | Context-level test or call pure init logic |
| Runner bean exists yet never runs | Used a simple context runner | Test via `SpringApplication` |
| `ApplicationReadyEvent` never reaches listener in test | Registered after startup | Attach listener before `run(...)` |
| `@RecordApplicationEvents` misses startup events | Events fired before test method ran | Use an early listener in a Boot startup integration test |
| `@PreDestroy` has not run after `@Test` | Cached context still open | Create and close a dedicated context |
| `ContextClosedEvent` arrives before destroy | Event marks start of close | Assert resource state after close finishes |
| Flaky tests | Sleeps or async races | Latches, futures, fake executors |
| Test hangs on shutdown | Threads or network calls lack timeouts | Design clean stop and bounded waits |
| Startup failure tested improperly | Called runner directly | Test `SpringApplication.run(...)` |
| Tests pass alone yet fail in full suite | Shared singleton or static state | Isolate contexts, reset state, avoid parallel conflicts |
| Cleanup reports success yet resource stays open | Only incremented counter instead of closing | Check fake resource state |
| Prototype not destroyed on context close | Prototype destruction not fully container-managed | Caller takes ownership of cleanup |

Each symptom can have multiple causes; tests should report clear messages naming the violated contract rather than generic "context failed" errors.

## 37. Practical test scenario for a startup pipeline

Suppose a service requires:

~~~text
Validate config
      |
      v
Initialize connection pool
      |
      v
Load required catalog
      |
      v
Ready for traffic
      |
      v
Process messages
      |
      v
Shutdown and release resources
~~~

You can split tests into groups:

### A. Config / unit tests

- Missing mandatory config throws a clear validation error.
- Invalid values are rejected before use.
- Runner options are parsed accurately.

### B. Bean lifecycle tests

- Fake connection initializes properly.
- If a later bean fails, already-registered resources clean up.
- `@PreDestroy` or destroy methods close resources on context close.

### C. Runner tests

- Runner invokes catalog loader.
- Success transitions state to `READY`.
- Failures are not swallowed.
- When multiple runners exist, dependent ordering holds.

### D. Event tests

- Started fires before runners.
- Ready fires after successful runners.
- Failed fires when a runner throws.
- Close event fires when the context enters shutdown.

### E. Async / shutdown tests

- Readiness fails while catalog loading is unfinished.
- On shutdown, consumers stop accepting new tasks.
- In-flight tasks are handled per policy.
- Connections and executors are closed.

Not every scenario requires a large `@SpringBootTest`. Layering tests appropriately makes pinpointing test failures much faster.

## 38. Hands-on practice exercise

Try building a small Boot application with three beans:

1. `LifecycleProbe` with `@PostConstruct` and `@PreDestroy`.
2. `StartupModeRunner` accepting `ApplicationArguments` and calling a fake task.
3. `ControlledWorker` implementing `SmartLifecycle`.

Then write the tests:

- **Test 1:** verify init runs on context refresh and destroy runs after close.
- **Test 2:** verify the runner parses `--mode=safe` properly and has a fallback.
- **Test 3:** Boot startup actually invokes the runner.
- **Test 4:** early listeners record `started` and `ready`, with the runner in between.
- **Test 5:** a failing runner causes Boot to emit the failed event.
- **Test 6:** `SmartLifecycle` starts and stops with context transitions.
- **Test 7:** fake resource `isClosed()` flips to true after close.
- **Test 8:** readiness stays false while an async task is incomplete.
- **Test 9:** intentionally use a cached context and observe why the runner does not re-run for every method.
- **Test 10:** replace sleeps with latches or futures to check completion.

The most important lesson is not writing as many assertions as possible, but ensuring **each assertion maps to a well-defined lifecycle contract**.

## 39. Checklist before finishing the test suite

1. Is the test proving method behavior or Spring container behavior?
2. Does the test use `SpringApplication` when Boot startup events or runners are needed?
3. Were listeners registered before the event fired?
4. Is the context fresh or pulled from cache?
5. Do assertions run before or after refresh/runner/ready/close?
6. Are any async tasks running?
7. If so, which completion signal does the test await?
8. Who owns resource management?
9. When an assertion fails, are resources and contexts guaranteed to close?
10. Are waits and network operations bounded by finite timeouts?
11. Are there real side effects on databases, brokers, or email services?
12. Can the test run safely in parallel?
13. Does the test assume an ordering not guaranteed by Spring?
14. On startup failure, does the test check both root cause and cleanup?
15. When a test fails, can readers tell exactly which contract broke?

## Conclusion

Spring Boot platform testing covers more than services and controllers. **Init callbacks, runners, startup events, and resource cleanup** represent distinct contracts in the application lifecycle.

- Use **unit tests** to verify logic inside runners, handlers, and cleanup routines.
- Use **`ApplicationContextRunner` or manually managed contexts** to verify bean init, refresh failures, and destroy callbacks.
- Use **`SpringApplication` or `@SpringBootTest`** when proving runners actually execute.
- Attach listeners before `run(...)` to observe **`ApplicationStartedEvent`, `ApplicationReadyEvent`, and `ApplicationFailedEvent`**.
- Call `context.close()` explicitly to verify `ContextClosedEvent`, `@PreDestroy`, destroy methods, and `SmartLifecycle.stop(...)`.
- Never confuse **context refresh**, **runner completion**, **ready**, **async completion**, and **shutdown completion**.
- Manage resource ownership, using fakes and completion signals rather than relying on `Thread.sleep(...)` or timing luck.

A strong test suite proves not only that **the application can start**, but that **it starts properly, fails properly, and stops without leaking unmanaged resources**.
