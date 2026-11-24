# ApplicationStartingEvent in Spring Boot Application Events

## 1. What Is ApplicationStartingEvent?

`ApplicationStartingEvent` is a **very early** lifecycle event published by `SpringApplication` when starting a Spring Boot application run. It resides in package:

```java
org.springframework.boot.context.event.ApplicationStartingEvent
```

The event is published **after the required `ApplicationListener`s and initializers have been registered**, but **before the `Environment` and `ApplicationContext` are created or prepared for use**. Therefore, it allows recording the bootstrap start milestone or setting up some very early support, but it is not the place to interact with beans/services, read bound `@ConfigurationProperties`, query repositories, or check whether an HTTP server is ready.

Three easily confused names must be distinguished:

- **`ApplicationStartingEvent`**: Spring Boot has just begun the `SpringApplication.run(...)` cycle. The context is not ready yet, and the environment has not been prepared.
- **`ApplicationStartedEvent`**: the context has successfully called `refresh()` and has **not yet run** `ApplicationRunner`/`CommandLineRunner`.
- **`ContextStartedEvent`**: belongs to **Spring Framework**, published by calling `ConfigurableApplicationContext.start()`. It is a separate operation on `Lifecycle` beans, not a "shorthand" for the two Boot events above.

If you write a listener for `ApplicationStartingEvent` inside a `@Component` class or as an `@EventListener` method on an ordinary bean, in most cases **that listener will not see the event**: when Boot publishes the event, the bean has not been created yet and has not been registered with the context's multicaster.

**Core usage:** register the listener with `SpringApplication` itself before calling `run(...)`, or declare the startup listener where Boot can load it from the classpath before creating the context.

## 2. Where Does the Event Appear in the Startup Sequence?

With Spring Boot 3.3, the main milestones in the `SpringApplication.run(...)` lifecycle can be visualized as follows:

```text
main(String[] args)
    |
    | new SpringApplication(App.class)
    | register listeners / initializers
    v
SpringApplication.run(args)
    |
    +--> ApplicationStartingEvent            <-- Environment not ready yet
    |
    +--> prepare ConfigurableEnvironment
    +--> ApplicationEnvironmentPreparedEvent
    |
    +--> create ApplicationContext
    +--> run ApplicationContextInitializer
    +--> ApplicationContextInitializedEvent
    |
    +--> load bean definitions
    +--> ApplicationPreparedEvent
    |
    +--> refresh ApplicationContext
    |       +--> ContextRefreshedEvent
    |       +--> WebServerInitializedEvent (if web server present)
    |
    +--> ApplicationStartedEvent
    +--> AvailabilityChangeEvent(LivenessState.CORRECT)
    |
    +--> ApplicationRunner / CommandLineRunner
    |
    +--> ApplicationReadyEvent
    +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
    |
    v
SpringApplication.run(...) returns ConfigurableApplicationContext
```

This is the general sequence for a successful startup. Not every application has a web server; web-server-related events are only published when an appropriate server exists. `ApplicationFailedEvent` may be published when startup fails and should not be placed at a fixed position in the success branch.

| Event | Usable `Environment`? | Usable `ApplicationContext`? | Learning Takeaway |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | **Not yet** | **Not yet** | Earliest starting point of a `run` execution |
| `ApplicationEnvironmentPreparedEvent` | **Yes**, prepared | Not yet | Observe/adjust the environment before creating the context |
| `ApplicationContextInitializedEvent` | Yes | Yes, just initialized | Initializers have run, definitions not yet loaded |
| `ApplicationPreparedEvent` | Yes | Yes, not yet refreshed | Definitions loaded, preparing for refresh |
| `ApplicationStartedEvent` | Yes | Yes, refreshed | Before startup runners |
| `ApplicationReadyEvent` | Yes | Yes | After runners, milestone where app is considered ready |

The word "started" here refers to a **milestone in Boot's lifecycle**; it does not guarantee that the database, message broker, or all external systems are healthy. To know whether the application is ready to accept traffic, rely on readiness and appropriate health checks rather than inferring it from `ApplicationStartingEvent`.

## 3. Data Actually Available in ApplicationStartingEvent

In Spring Boot 3.3, `ApplicationStartingEvent` extends `SpringApplicationEvent`, and through it extends `ApplicationEvent`. Useful APIs include:

| API | Value/Meaning | Things to Note |
| --- | --- | --- |
| `getSpringApplication()` | The `SpringApplication` instance bootstrapping | Internal state can still change as startup progresses |
| `getArgs()` | Raw `String[]` arguments passed into `run(...)` | Not yet the `ApplicationArguments` bean; may contain sensitive data |
| `getBootstrapContext()` | `ConfigurableBootstrapContext` for the bootstrap phase | **Not** `ApplicationContext`; different lifecycle |
| `getSource()` | Source of the event, typically `SpringApplication` | Not a bean or context |
| `getTimestamp()` | Timestamp when the event object was created | Not a measurement of total startup time |

Example listener method:

```java
import java.util.Arrays;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class StartingObserver
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("BOOT STARTING");
        System.out.println(
                "ARG_COUNT=" + event.getArgs().length);
        System.out.println(
                "HAS_BOOTSTRAP_CONTEXT=" + (event.getBootstrapContext() != null));
    }
}
```

This is a syntactically complete Java listener class; for **Spring Boot to invoke it**, it must be registered early using one of the approaches in section 4. It is not automatically activated merely because the Java file exists.

### Do Not Confuse the Two "Contexts"

- `ConfigurableBootstrapContext`: a registry/context supporting early bootstrapping; it can store objects serving this stage according to the bootstrap contract. It does not manage all beans like `ApplicationContext`.
- `ConfigurableApplicationContext`: the Spring IoC container created **after** the starting event; it manages bean definitions, singletons, context event listeners, lifecycle, and dependency injection.

Therefore, the following snippet is **invalid with respect to timing**:

```java
// Design error: the event does not provide a ready ApplicationContext.
public void onApplicationEvent(ApplicationStartingEvent event) {
    // There is no event.getApplicationContext() on this event type.
    // Cannot autowire a context repository/service into an early listener
    // and expect them to be initialized at the STARTING milestone.
}
```

If you need the `Environment`, switch to `ApplicationEnvironmentPreparedEvent`; if you need a refreshed context, choose a later startup milestone.

## 4. Three Ways to Register a Listener Early Enough

### 4.1. SpringApplication.addListeners(...) — Best Fit for a Single Entry Point

```java
SpringApplication application = new SpringApplication(DemoApplication.class);
application.addListeners(new StartingObserver());
application.run(args);
```

This is an illustrative snippet, assuming `DemoApplication` is the Boot configuration class and `StartingObserver` is as shown above. Registering **before** `run(...)` is the essential condition.

Advantages: explicit at the entry point, easy to debug and test, and does not affect other applications merely because they share the same dependency.

### 4.2. SpringApplicationBuilder.listeners(...) — Suitable When Using the Builder

```java
new SpringApplicationBuilder(DemoApplication.class)
        .listeners(new StartingObserver())
        .run(args);
```

Requires importing `org.springframework.boot.builder.SpringApplicationBuilder`. This approach also registers the listener on `SpringApplication` before Boot creates the context.

### 4.3. META-INF/spring.factories — Early Loading from a Library/Module

A starter or library that wants a listener loaded automatically can place a file at:

```text
src/main/resources/META-INF/spring.factories
```

Example contents:

```properties
org.springframework.context.ApplicationListener=\
demo.StartingObserver
```

The listener class must have a suitable way to be instantiated by Boot from the classpath; a no-arg constructor as in `StartingObserver` is the simplest option. If there are multiple listeners, list the full class names according to the factories file syntax.

**Do not confuse this mechanism with auto-configuration registration**: in newer Spring Boot versions, listing auto-configurations moved to `AutoConfiguration.imports`, whereas declaring **ApplicationListener** via `spring.factories` remains a case documented by Boot. The two metadata types serve different purposes.

### Why @Component / @Bean / @EventListener Are Not Suitable?

```java
@Component
class TooLateObserver {

    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        // Does not receive early startup events this way in a normal Boot flow.
    }
}
```

Spring only scans/instantiates components and registers `@EventListener` methods while the context is being created/refreshed, **after** the starting milestone. Similarly, an `@Bean ApplicationListener<ApplicationStartingEvent>` created from a normal context is also too late to receive an already-published event.

This does not mean `@EventListener` cannot be used for **any** Spring Boot event: events after the context has refreshed, such as `ApplicationReadyEvent`, can be handled by ordinary bean listeners.

## 5. Runnable Maven Example with Java 17 and Spring Boot 3.3

This example clearly demonstrates three milestones:

1. An early listener attached to `SpringApplication` before `run(...)`.
2. An `ApplicationRunner` running after the context has refreshed.
3. An `@EventListener` method on a bean receiving `ApplicationReadyEvent`.

It intentionally uses `WebApplicationType.NONE` so no web server, database, or controller is needed; the lines printed by the program have a clear order. Example versions: **Java 17+ and Spring Boot 3.3.13**.

Structure:

```text
boot-starting-event/
├── pom.xml
└── src/main/java/demo/StartingEventDemo.java
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

    <groupId>demo</groupId>
    <artifactId>boot-starting-event</artifactId>
    <version>1.0.0</version>

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

File `src/main/java/demo/StartingEventDemo.java`:

```java
package demo;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication(proxyBeanMethods = false)
public class StartingEventDemo {

    @Bean
    ApplicationRunner runner() {
        return args -> System.out.println("RUNNER");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("READY");
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(StartingEventDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        application.addListeners(
                (ApplicationListener<ApplicationStartingEvent>) event -> {
                    System.out.println("STARTING");
                    System.out.println(
                            "ARGS=" + Arrays.toString(event.getArgs()));
                    System.out.println(
                            "HAS_BOOTSTRAP=" + (event.getBootstrapContext() != null));
                    System.out.println(
                            "SAME_APP=" + (event.getSpringApplication() == application));
                });

        try (ConfigurableApplicationContext context =
                     application.run("--sample=ok")) {
            System.out.println("CONTEXT_ACTIVE=" + context.isActive());
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

Lines **printed by the program itself** in order (excluding environment-dependent system/logging messages):

```text
STARTING
ARGS=[--sample=ok]
HAS_BOOTSTRAP=true
SAME_APP=true
RUNNER
READY
CONTEXT_ACTIVE=true
```

Explanation:

1. `SpringApplication` is created and configured **before** calling `run`; the listener is added to this specific application's early listeners list.
2. When `application.run("--sample=ok")` begins, Boot publishes `ApplicationStartingEvent`. The `Environment` and context do not exist yet; the listener reads `getArgs()`, `getBootstrapContext()`, and `getSpringApplication()` without needing beans.
3. `getArgs()` returns raw arguments, so `Arrays.toString(...)` prints `[--sample=ok]`. `SAME_APP=true` proves the event belongs to the exact running instance.
4. After the context is refreshed, Boot runs the `ApplicationRunner` bean and prints `RUNNER`.
5. Boot publishes `ApplicationReadyEvent` after runners finish. The bean containing `@EventListener` is already registered, so it prints `READY`.
6. `run(...)` returns the active context. The example prints `CONTEXT_ACTIVE=true`, and then the `try-with-resources` block closes the context.

`@EnableAsync` is not needed in the example. Listeners run synchronously by default, making milestone ordering easy to observe. In real applications, logging configuration and instrumentation may produce additional log lines; distinguish them from the lines printed by the code above.

**One thing to remember:** `@EventListener(ApplicationReadyEvent)` receives its event because that is a **late** milestone; it does not prove that a bean can receive the early `ApplicationStartingEvent`.

## 6. Comparing "Starting", "Started", "Ready", and ContextStarted Events

This is a major source of confusion because the names are similar while their timing is completely different.

| Event | Where Declared | What Just Happened? | Can Use Beans/Repositories? |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | `org.springframework.boot.context.event` | `SpringApplication.run` has just begun, before preparing the environment | **Not yet** (no context) |
| `ApplicationEnvironmentPreparedEvent` | Spring Boot | Environment has been prepared; before context | No beans yet |
| `ApplicationStartedEvent` | Spring Boot | Context has refreshed; before runners | Context is ready with beans, but app has not finished runners |
| `ApplicationReadyEvent` | Spring Boot | Runners have finished; app is considered ready | Can access beans in the context |
| `ContextStartedEvent` | `org.springframework.context.event` | Explicit call to `ConfigurableApplicationContext.start()` | Belongs to container lifecycle, independent of Boot startup events |

If you need to read configuration from profiles or property sources after Boot has gathered data from the environment, **do not** try to get it at `ApplicationStartingEvent`. If you need to initialize data via services, prefer `ApplicationRunner`/`CommandLineRunner` or an appropriate milestone after context refresh. If you need to signal startup completion and readiness for traffic, rely on `ApplicationReadyEvent` or the availability/readiness mechanism.

### ApplicationStartingEvent Is Not ContextStartedEvent

These two lines are not interchangeable:

```java
// Boot automatically publishes ApplicationStartingEvent inside SpringApplication.run(...).
SpringApplication.run(DemoApplication.class, args);

// Spring Framework publishes ContextStartedEvent when start() is explicitly called.
configurableApplicationContext.start();
```

The snippet only illustrates the two call paths; `DemoApplication` and `configurableApplicationContext` must be defined in an application to compile. Boot does not need an explicit `ConfigurableApplicationContext.start()` call to publish `ApplicationStartingEvent`.

## 7. Reasonable Use Cases for ApplicationStartingEvent

### 7.1. Marking the Start of a Bootstrap Run

A listener can record an early measurement milestone in in-process memory:

```java
public final class StartupMarker
        implements ApplicationListener<ApplicationStartingEvent> {

    private volatile long startNanos;

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        startNanos = System.nanoTime();
    }

    public long getStartNanos() {
        return startNanos;
    }
}
```

This is a helper class; you must retain **the exact listener instance** if you want to read the milestone later, or design an appropriate storage/state-transfer path. `System.nanoTime()` is only for measuring **elapsed time within the same JVM**, not as a wall-clock timestamp to exchange across processes. It records when the listener was invoked, not when the JVM process started or when the class loader loaded the main class.

If you want structured startup metrics and stage observation, consider `ApplicationStartup` / `BufferingApplicationStartup` or tracing tools rather than manually stitching timestamps from multiple hooks without exact definitions.

### 7.2. Preparing Bootstrap Support Independent of Spring Beans

Some infrastructure libraries need to participate early to prepare the bootstrap registry or record state. `ApplicationStartingEvent.getBootstrapContext()` provides access to `ConfigurableBootstrapContext` very early. However, you must respect the bootstrap registry lifecycle and avoid treating early-registered objects as initialized beans.

If the sole goal is **registering bootstrap objects**, a dedicated API such as `BootstrapRegistryInitializer` usually expresses intent better; there is no need to overuse listeners for every customization.

### 7.3. Observing Minimal Input Parameters

You can use `event.getArgs()` to count arguments, classify launch modes by a defined technical flag, or attach a startup correlation ID. However:

- Raw CLI args may contain paths, tokens, or sensitive data; **never print arguments verbatim in production logs**.
- This is not the `Environment` yet: property sources, environment variables, config files, and profiles have not been fully prepared by Boot.
- If logic needs final values after precedence/config binding, wait for `ApplicationEnvironmentPreparedEvent` or a bean after context refresh.

The example in section 5 intentionally uses `--sample=ok` to stay safe and illustrate non-sensitive data.

### 7.4. Shared Listener in a Startup Library

With `META-INF/spring.factories`, a library can self-register an early listener for applications that use it. This is reasonable when the work truly requires a very early milestone, such as setting up bootstrap observability. If the listener has side effects, document them clearly in the library documentation and avoid unexpected global state mutations.

## 8. Important Limitations Before Environment and ApplicationContext Exist

### 8.1. Standard Dependency Injection Is Not Available Yet

`@Autowired`, `@Value`, `@ConfigurationProperties`, `@Transactional`, repositories, and service beans all rely on the context, or at least infrastructure initialized at later milestones.

A manually created early listener:

```java
application.addListeners(new StartingObserver());
```

is a plain Java object supplied directly to `SpringApplication`. It does not automatically turn into a bean with injected dependencies at starting time. If it relies on an unassigned `@Autowired` field, it may encounter `null`.

**Solution:** pass only dependencies that can genuinely be created early via constructor, or move to another lifecycle milestone. Avoid calling `SpringApplication.run` on a second application inside the listener just to obtain a context.

### 8.2. Logging Infrastructure Is Still Being Configured

Spring Boot uses dedicated startup listeners to initialize and configure logging in stages. At `ApplicationStartingEvent`, logging may still be in setup and may not yet reflect full configuration from the environment.

If very early messages are needed, log only small amounts of data; do not depend on profiles, log levels, or appenders that will later be read from `application.yml`. `System.out.println` is only suitable for demonstration, not as a complete logging solution.

### 8.3. The Listener Must Execute Quickly

Startup events are dispatched by default on the thread launching the application. A listener performing slow I/O, network queries, or lock waiting can **slow down or hang the entire startup**, before the context and Actuator are ready for diagnostics.

If work can run after the application is ready, move it to a runner, a ready listener, or a managed background task. Do not spawn manual executors at the starting milestone without a plan for shutdown, error observation, and context propagation.

### 8.4. Exceptions in Listeners Can Break Startup

If an early listener throws an exception, it can abort the startup flow and Boot may report failure. Do not use this event to run error-prone, non-essential work, because at that point the system lacks normal recovery mechanisms or health endpoints.

If you need to block startup due to **invalid configuration**, pick an extension point with appropriate semantics, log clear errors, and test failure detection. Do not push all validation into `ApplicationStartingEvent` when the information to validate does not exist yet.

## 9. SpringApplicationEvent and Event Filtering

`ApplicationStartingEvent` is a subtype of `SpringApplicationEvent`. When writing one listener covering multiple startup events, you can register `ApplicationListener<SpringApplicationEvent>` upfront and branch on runtime type.

Illustrative example:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class BootLifecycleObserver
        implements ApplicationListener<SpringApplicationEvent> {

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            System.out.println("starting");
        } else if (event instanceof ApplicationReadyEvent) {
            System.out.println("ready");
        }
    }
}
```

This is a standalone listener class, yet it must be registered early to receive all desired milestones. If you do not need to listen to multiple events, **prefer a specifically typed listener**:

```java
ApplicationListener<ApplicationStartingEvent>
```

A broad listener must check the subtype on every invocation. Do not treat callback ordering across multiple child/parent applications or multiple startup runs as a single global sequence without designing identification per `SpringApplication`.

### Event Source Is SpringApplication

`getSpringApplication()` lets you distinguish the running instance at the bootstrap level. A shared listener can check instance identity if needed, but avoid relying on unstable state of the `SpringApplication` object. Javadoc emphasizes that the application's internal state may still change in subsequent stages.

Do not rely on `ApplicationContext.getId()` at this step because the context has not been created yet.

## 10. Security and Reliability in Early Startup Listeners

Important practical principles:

1. **Do not log secrets**: command-line arguments may contain passwords, access tokens, or internal URLs; if measurement is needed, log counts or allowlisted flag names.
2. **Avoid non-idempotent side effects**: a single JVM can call `SpringApplication.run(...)` multiple times in tests or run multiple contexts; do not assume the listener runs strictly once per JVM.
3. **Do not make mandatory HTTP/database calls**: there are no reliable connection-managing beans, circuit breakers, or transaction contexts yet.
4. **Do not read the Environment before it is prepared**: creating your own `StandardEnvironment` can yield values different from Boot's final environment.
5. **Do not distort failure semantics**: an exception at an early milestone can block startup without guaranteeing all infrastructure components were cleaned up like a complete context.
6. **Be careful with global static state**: starting multiple contexts can overwrite each other's milestones or data; prefer state tied to a single `SpringApplication`/bootstrap.
7. **Keep callbacks fast and deterministic**: this event suits a quick recording milestone or very small adjustment, not a stage for running heavy migrations.
8. **Verify against the exact Spring Boot version**: constructors and bootstrap APIs can change across Boot releases; examples use Boot 3.3 APIs and Java 17.

## 11. Testing ApplicationStartingEvent

Because the listener runs before the context exists, a test using only `@SpringBootTest` and looking up an `ApplicationListener<ApplicationStartingEvent>` bean after startup is insufficient to prove the listener received the event. You must register the listener before running the application in the test, or use a listener from `spring.factories` along with an observable way to store results.

Example test strategy, without needing a web server:

```java
AtomicInteger startingCount = new AtomicInteger();

SpringApplication app = new SpringApplication(StartingEventDemo.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.setBannerMode(Banner.Mode.OFF);
app.addListeners((ApplicationListener<ApplicationStartingEvent>) event ->
        startingCount.incrementAndGet());

try (ConfigurableApplicationContext context = app.run()) {
    assertEquals(1, startingCount.get());
}
```

This is an **illustrative snippet inside a JUnit test**, requiring imports for `AtomicInteger`, `SpringApplication`, `WebApplicationType`, `Banner`, `ApplicationListener`, `ApplicationStartingEvent`, `ConfigurableApplicationContext`, `assertEquals`, and the configuration class `StartingEventDemo`. It is not the standalone program from section 5.

Test cases worth having:

| Scenario | Data/Setup | Expected Result |
| --- | --- | --- |
| Listener registered before run | `app.addListeners(listener)` before `app.run(...)` | Receives exactly one STARTING milestone for a normal run |
| Not registered early | Listener defined only as a bean | Bean does not catch the event already published before context creation |
| Passing arguments | `app.run("--sample=ok")` | `getArgs()` contains the exact raw string `--sample=ok` |
| Bootstrap context present | `event.getBootstrapContext()` | Non-null in the API version used |
| Context not ready yet | Callback right at STARTING | Cannot obtain context via `ApplicationStartingEvent` API |
| Later milestones | Runner + ready listener present | RUNNER before READY |
| Multiple startup tests | Two `SpringApplication` creations/runs | Per-run listener can be invoked on each run |
| Listener throws exception | Intentional exception | Startup fails along Boot's exception path; observe result rather than just logs |
| Listeners from classpath | `spring.factories` | Listener class is discovered early enough during runtime bootstrap |

Do not assert against the exact full Spring Boot log output, because logo/banner/log levels can change by dependencies and environment. For the example in section 5, verify **the lines printed by the code** and their order.

## 12. Common Mistakes

1. **Registering a listener with `@EventListener` on a `@Component`** and wondering why STARTING is missed: too early for the context to create beans.
2. **Confusing with `ApplicationStartedEvent`**: STARTED has already refreshed the context, while STARTING has neither context nor prepared environment.
3. **Confusing with `ContextStartedEvent`**: this Framework event is tied to an explicit `ConfigurableApplicationContext.start()`.
4. **Using `ApplicationStartingEvent` to signal "ready"**: the event happens at the start of startup, before runners, server, and readiness.
5. **Reading `application.yml` and profiles via beans at STARTING**: `Environment` has not been prepared for access via the event yet.
6. **Autowiring a repository into a manually created early listener**: the instance has not gone through standard dependency injection.
7. **Logging full `getArgs()` in production**: inadvertently exposes secrets from the command line.
8. **Starting long tasks on the startup thread**: slows down or hangs context creation.
9. **Treating `getBootstrapContext()` as `ApplicationContext`**: the two contexts have different lifecycles and roles.
10. **Using `spring.factories` to declare auto-configuration and listeners under the same key**: auto-configuration and listener loading mechanisms differ.
11. **Assuming static `run` + an early `@Bean` works like `addListeners`**: the bean is created after the STARTING milestone.
12. **Confusing the event timestamp with total startup duration**: you need two measurement milestones and exact definitions of start and end points.
13. **Assuming each JVM has only one run**: tests, CLI tools, or context hierarchies can have multiple runs.
14. **Not testing against the actual Boot version being run**: API/registration changes across versions can invalidate old assumptions.

## 13. Design Checklist

Before using `ApplicationStartingEvent`, confirm:

- Do you truly need to do work **even before the Environment exists**, or can it wait for a later milestone?
- Does the work require beans, repositories, configuration binding, transactions, or a web server? If yes, change the event.
- Is the listener registered before `run(...)` via `addListeners`, builder, or `spring.factories`?
- Are you confusing the name with `ApplicationStartedEvent`/`ContextStartedEvent`?
- Are you logging raw CLI args containing sensitive information?
- Is the listener operation fast enough and safe if startup fails?
- If measuring duration, have you defined which two milestones represent "start" and "ready"?
- Have you distinguished `BootstrapContext` from `ApplicationContext`?
- Have you tested the listener receiving STARTING with a real `SpringApplication` and verified RUNNER/READY ordering?
- Are you using APIs from the exact Boot version being deployed?

**Takeaway:** `ApplicationStartingEvent` is the opening signal of the `SpringApplication.run(...)` cycle, published before Spring prepares the environment and creates the context. Register the listener early and keep handling lightweight and independent of IoC; move work requiring the context or readiness to more suitable milestones.

## References

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-events-and-listeners)
- [Spring Boot 3.3 — ApplicationStartingEvent Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartingEvent.html)
- [Spring Boot 3.3 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — ApplicationStartedEvent Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
