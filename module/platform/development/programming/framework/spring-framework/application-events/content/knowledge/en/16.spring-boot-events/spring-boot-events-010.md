# SpringApplication.addListeners in Spring Boot Application Events

## 1. Purpose of SpringApplication.addListeners

`SpringApplication.addListeners(ApplicationListener<?>... listeners)` is Spring Boot's API to **register one or more additional listeners for the application startup process before calling `SpringApplication.run(...)`**. Listeners are added to `SpringApplication` and subsequently registered with the `ApplicationContext` once the context is ready.

The most important difference compared to `@EventListener` or `@Bean ApplicationListener` is **registration timing**:

- As Boot begins running, events such as `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent` occur **before `ApplicationContext` is created**.
- Listeners that depend on Spring beans do not exist yet at that stage, so you cannot rely on `@EventListener` or `@Bean` being scanned and instantiated in time to receive those early events.
- A listener passed to `app.addListeners(...)` **before `app.run(...)`** is already registered on `SpringApplication` itself, so it can receive early startup events.
- Once the context is created and configured, that listener is also registered with the context and can continue receiving appropriate events published by the context.

In short: **`SpringApplication.addListeners` is used when you need to observe or react to Spring Boot lifecycle events right from the start of bootstrap**, not only after the bean container finishes initializing.

Example registering a listener right in the `main` method:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners((ApplicationListener<ApplicationStartingEvent>) event ->
        System.out.println("Application starting up"));
app.run(args);
~~~

*This is an illustrative snippet, not a standalone program; it requires `MyApplication` along with Spring Boot and Spring Context imports. A complete, runnable example is in section 4.*

**Note:** `addListeners` only registers listeners; it **does not start the application, create events, or return event-handling results**. Startup is still triggered by `run(...)`.

## 2. API and Related Components

Primary signature on class `org.springframework.boot.SpringApplication`:

~~~java
public void addListeners(ApplicationListener<?>... listeners);
~~~

`ApplicationListener<E>` is a Spring Framework interface with a method accepting an event of type `E`:

~~~java
@FunctionalInterface
public interface ApplicationListener<E extends ApplicationEvent> {
    void onApplicationEvent(E event);
}
~~~

*The signature is shown in simplified form for learning the API; there is no need to redeclare Spring's interface.*

Concept table:

| Component | Role |
| --- | --- |
| `SpringApplication` | Object that configures, bootstraps, and runs Spring Boot. |
| `SpringApplication.addListeners(...)` | **Adds** listeners before `run(...)`; does not replace the entire existing listener set. |
| `ApplicationListener<E>` | Interface for receiving events of type `E extends ApplicationEvent`. |
| `SpringApplication.setListeners(...)` | **Sets/replaces** the listener collection configured on `SpringApplication`; use cautiously as it may affect internal listeners. |
| `SpringApplication.getListeners()` | Retrieves the listeners currently configured on the `SpringApplication` instance (read-only per API). |
| `SpringApplicationBuilder.listeners(...)` | Way to register listeners when configuring the application via the builder. |
| `ApplicationContext.addApplicationListener(...)` | Registers directly on an existing context; cannot reach back to receive events published before the context was created. |

One practical point: `addListeners` accepts **already-instantiated listener objects**. If you call `new MyListener()`, that object does not automatically get `@Autowired`, `@PostConstruct`, or bean lifecycle features like an ordinary Spring bean. Listeners used for bootstrap should be independent of DI or rely only on information immediately available at event time.

## 3. Which Events Occur During SpringApplication.run?

Spring Boot publishes the following typical lifecycle milestones:

| Event | Timing | Is `ApplicationContext` Available for Accessing Beans? |
| --- | --- | --- |
| `ApplicationStartingEvent` | Right at the start of `run`, after registering listeners/initializers and before preparing the environment. | **Not yet.** |
| `ApplicationEnvironmentPreparedEvent` | `Environment` is prepared, but context is not yet created. | **Not yet.** Can read/adjust `Environment` appropriately. |
| `ApplicationContextInitializedEvent` | Context created and `ApplicationContextInitializer`s have run, before loading bean definitions. | Context exists but **not yet refreshed**; should not be used as a complete bean container. |
| `ApplicationPreparedEvent` | Bean definitions loaded, right before `refresh`. | Context exists but **not yet refreshed**. |
| `ApplicationStartedEvent` | Context finished refreshing, **before** `ApplicationRunner` and `CommandLineRunner`. | Yes. |
| `ApplicationReadyEvent` | Runners completed; application is practically ready to serve. | Yes. |
| `ApplicationFailedEvent` | Published by Boot when startup fails. | Context may **not yet** exist or may be incomplete; must null-check before use. |

Spring Boot also publishes `AvailabilityChangeEvent`s at appropriate points, such as `LivenessState.CORRECT` after `ApplicationStartedEvent` and `ReadinessState.ACCEPTING_TRAFFIC` after `ApplicationReadyEvent`. Web applications also have `WebServerInitializedEvent` when the web server is ready, and Spring Framework has `ContextRefreshedEvent` after refresh.

These events are **not direct substitutes for one another**:

- `ApplicationStartingEvent`: very early, with neither environment nor context.
- `ApplicationEnvironmentPreparedEvent`: has environment but no context yet, useful for observing/adjusting startup configuration.
- `ApplicationStartedEvent`: context refresh finished, **but runners have not executed yet**.
- `ApplicationReadyEvent`: runners have executed, suitable for tasks observing when the application is ready.
- `ApplicationFailedEvent`: diagnostic handling when startup fails; does not guarantee all beans or resources remain usable.

`SpringApplication.addListeners` is especially valuable at the **first two milestones**, because you normally cannot use a `@Bean` or `@EventListener` to receive events that occurred before the bean container existed.

## 4. Runnable Java 17+ Example: Observing the Entire Startup Sequence

This example uses **Spring Boot 3.5.16**, Java 17+, and Maven; this version is available on Maven Central. The program does not start a web server so output is easy to control. It registers listeners with `addListeners(...)` before `run(...)`, defines a `CommandLineRunner` to show the difference between `Started` and `Ready`, and then closes the context to observe `ContextClosedEvent`.

### 4.1. Structure

~~~text
spring-application-listeners-demo/
├── pom.xml
└── src/main/java/example/ListenerRegistrationDemo.java
~~~

File `pom.xml`:

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
    <groupId>example</groupId>
    <artifactId>spring-application-listeners-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
~~~

File `src/main/java/example/ListenerRegistrationDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;

@SpringBootApplication
public class ListenerRegistrationDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                ListenerRegistrationDemo.class);

        // Configurations to keep the illustrative output concise and deterministic.
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(Map.<String, Object>of(
                "demo.stage", "configured",
                "logging.level.root", "OFF"));

        // Register before run(): captures even very early events.
        app.addListeners(
            (ApplicationListener<ApplicationStartingEvent>) event ->
                System.out.println("01 STARTING"),

            (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event ->
                System.out.println("02 ENV: "
                    + event.getEnvironment().getProperty("demo.stage")),

            (ApplicationListener<ApplicationContextInitializedEvent>) event ->
                System.out.println("03 CONTEXT_INITIALIZED"),

            (ApplicationListener<ApplicationPreparedEvent>) event ->
                System.out.println("04 PREPARED"),

            (ApplicationListener<ApplicationStartedEvent>) event ->
                System.out.println("05 STARTED"),

            (ApplicationListener<ApplicationReadyEvent>) event ->
                System.out.println("07 READY"),

            (ApplicationListener<ApplicationFailedEvent>) event ->
                System.out.println("FAILED: " + event.getException()
                    .getClass().getSimpleName()),

            (ApplicationListener<ContextClosedEvent>) event ->
                System.out.println("09 CLOSED")
        );

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("08 RUN_RETURNED");
        }
    }

    @Bean
    public CommandLineRunner demoRunner() {
        return args -> System.out.println("06 RUNNER");
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

**Lines printed by the program on stdout upon successful startup** (excluding separate Maven/JVM log or build output):

~~~text
01 STARTING
02 ENV: configured
03 CONTEXT_INITIALIZED
04 PREPARED
05 STARTED
06 RUNNER
07 READY
08 RUN_RETURNED
09 CLOSED
~~~

### 4.2. Explaining the Order

1. Before `run`, the application creates `SpringApplication` and calls `app.addListeners(...)`. The lambdas are separate `ApplicationListener`s, each declaring a specific event type.
2. `ApplicationStartingEvent` occurs before environment/context exist. Because the listener was added to `SpringApplication` before running, it prints `01 STARTING`.
3. Once `Environment` is ready, `ApplicationEnvironmentPreparedEvent` is published. The default value `demo.stage=configured` was set on `SpringApplication` and is readable from the event, so it prints `02 ENV: configured`.
4. The context is initialized and then bean definitions are loaded; milestones `03 CONTEXT_INITIALIZED` and `04 PREPARED` appear before context refresh.
5. After context refresh succeeds, Boot publishes `ApplicationStartedEvent`; the listener prints `05 STARTED`.
6. Spring Boot invokes the `CommandLineRunner` bean; line `06 RUNNER` appears after `STARTED` and before `READY`.
7. Boot publishes `ApplicationReadyEvent`; the listener prints `07 READY`. When `app.run(args)` returns, the program prints `08 RUN_RETURNED`.
8. The `try-with-resources` block closes the context. The `ContextClosedEvent` listener was registered on the context, so it prints `09 CLOSED`. This is a Spring Framework event, not a milestone in the `SpringApplicationEvent` set.

The `FAILED` line does not appear because the example starts up successfully. Do not add `FAILED` manually to stdout in the normal flow.

*In practice, an application also has many other internal listeners and events; the lines in the example are only messages printed by the program's own listeners. Disabling the banner and log level keeps output readable without changing lifecycle event ordering.*

## 5. Why Not Use @Bean or @EventListener for Early Events?

A familiar listener declaration:

~~~java
@Component
class ReadyObserver {
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Ready to serve");
    }
}
~~~

*This is illustrative code: requires importing `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener`, and `ApplicationReadyEvent`.*

The method above is reasonable for `ApplicationReadyEvent` because by then the context has finished refreshing and the bean is managed by Spring. However, trying to receive `ApplicationStartingEvent` like this is unreliable:

~~~java
@Component
class TooLateObserver {
    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        // By the time the processor registers @EventListener, this event has already occurred.
    }
}
~~~

`@EventListener` relies on `ApplicationContext`'s event method registration infrastructure. When `ApplicationStartingEvent` is published, the context does not even exist yet, so the bean cannot receive the event that has already passed. `ApplicationEnvironmentPreparedEvent` also takes place before the context is created.

Even once `ApplicationContext` has been created (`ContextInitialized`/`Prepared`), it may still be **unrefreshed**: do not expect a bean listener to have completed its lifecycle or call all bean services at this stage.

How to choose properly:

- Need to catch **events before the context exists** → register early via `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)`, or the `spring.factories` mechanism.
- Need to handle once the context is complete → a Spring-managed `@EventListener` bean or `ApplicationListener` is the more natural approach.
- Need to execute business initialization work after startup → consider `ApplicationRunner` or `CommandLineRunner` instead of performing heavy tasks inside lifecycle listeners.

## 6. Registering a Listener with a Separate Class Instead of Lambdas

Lambdas suit short examples. For larger applications, separate classes are easier to test:

~~~java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;

public final class EarlyEnvironmentListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent>,
                   Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        String name = event.getEnvironment()
                .getProperty("spring.application.name", "unknown");
        System.out.println("Bootstrap environment for: " + name);
    }
}
~~~

*This snippet can be placed in a separate `EarlyEnvironmentListener.java` file and added to a Spring Boot application; it is not a standalone program.*

Registration:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(new EarlyEnvironmentListener());
application.run(args);
~~~

`Ordered` allows expressing a listener's priority relative to other listeners supporting ordering; smaller index values generally have higher priority. However, do not depend on accidental ordering between two listeners if business logic requires dependent execution steps. The order of **lifecycle event types** is determined by Boot; `Ordered` affects the order of **listeners within the same event dispatch**, without turning `ApplicationReadyEvent` into an event before `ApplicationStartingEvent`.

## 7. addListeners, setListeners, Builder, and spring.factories

### 7.1. addListeners vs. setListeners

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(first, second);
~~~

`addListeners` appends new listeners to the existing configured listener set. Conversely, `setListeners(Collection<? extends ApplicationListener<?>>)` replaces the list used by `SpringApplication`; it can accidentally overwrite listeners registered earlier by Boot or libraries. Therefore, when you only need to extend, **prefer `addListeners`**.

### 7.2. SpringApplicationBuilder

If constructing the application via the builder:

~~~java
new SpringApplicationBuilder(MyApplication.class)
        .listeners(new EarlyEnvironmentListener())
        .run(args);
~~~

*This is an illustrative snippet, requiring importing `org.springframework.boot.builder.SpringApplicationBuilder` and declaring the application class.*

This serves the same need to register listeners before startup, yet fits well when the application has custom bootstrapping steps.

### 7.3. META-INF/spring.factories

When writing a library that wants its listener auto-discovered **regardless of how external applications create `SpringApplication`**, Spring Boot supports registering `ApplicationListener` via `META-INF/spring.factories`:

~~~properties
org.springframework.context.ApplicationListener=example.EarlyEnvironmentListener
~~~

A listener from `spring.factories` is loaded by Boot during bootstrap, not a bean created later by component scanning. The class must have a constructor/instantiation capability compatible with Spring Boot's loading mechanism. This is not a general replacement for every bean; use it only for bootstrap integration or libraries that genuinely need a very early listener.

Other automatic registration mechanisms in Spring Boot (such as auto-configuration imports) serve different purposes. Do not place an early startup listener inside auto-configuration and expect it to retroactively receive events that already occurred before configurations were loaded.

## 8. Practical Scenario: Reading and Adjusting Environment Early

`ApplicationEnvironmentPreparedEvent` is when you can inspect `ConfigurableEnvironment` while the context has not been created yet. Example attaching a high-priority `PropertySource`:

~~~java
public final class ExtraPropertiesListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        Map<String, Object> values = Map.of(
                "feature.bootstrap-check", true);
        event.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("bootstrapOverrides", values));
    }
}
~~~

*This is an illustrative integration snippet. Import `java.util.Map`, `ApplicationListener`, `ApplicationEnvironmentPreparedEvent`, and `org.springframework.core.env.MapPropertySource`; place the class in the application and register with `app.addListeners(new ExtraPropertiesListener())` before `run`.*

Carefully consider before mutating `Environment` in this phase:

- The listener runs during bootstrap, typically on the synchronous startup path; heavy code slows startup.
- `addFirst(...)` places the property source at the front, potentially overriding values from config files, environment variables, or command-line arguments according to source precedence. Do this only when that is the explicit intent.
- If complex external configuration loading is required, consider dedicated configuration mechanisms like `EnvironmentPostProcessor` or Config Data instead of overloading a listener with too many responsibilities.
- Do not read secret data from the event and print it to the console. Avoid depending on bean repositories/services because the context has not been initialized yet.

## 9. Handling Startup Errors: ApplicationFailedEvent

A listener added early can receive `ApplicationFailedEvent` even when the context fails to refresh successfully:

~~~java
app.addListeners((ApplicationListener<ApplicationFailedEvent>) event -> {
    Throwable cause = event.getException();
    System.err.println("Startup failed: " + cause.getClass().getName());

    // event.getApplicationContext() may be null or incomplete:
    // do not assume all beans are ready.
});
~~~

*This is illustrative code inside the `main` method where variable `app` is a `SpringApplication`.*

Notes:

- This is a **startup failure notification**, not a general handler for every exception after the application is ready.
- `ApplicationFailedEvent` can happen when the context does not exist yet or has been partially destroyed. Perform diagnostics with information guaranteed to be available, without requiring uninitialized beans/services.
- Errors thrown **inside a startup listener itself** can cause startup to fail; do not use early listeners for unsafe operations or long delays.
- Do not use an `ApplicationFailedEvent` listener to swallow or turn a startup error into success; the cause must be properly reported/logged.

## 10. Important Pitfalls: Synchronicity, Ordering, Context Hierarchy

### 10.1. Default Listeners Run Synchronously

`ApplicationListener.onApplicationEvent(...)` is normally invoked synchronously by the default event publishing mechanism. A listener making slow HTTP calls, calling `Thread.sleep(...)`, or running heavy queries on `ApplicationEnvironmentPreparedEvent` blocks the startup path. For deferrable tasks, pick a runner, schedule, or lifecycle-managed executor after the context is ready.

### 10.2. Do Not Use Dependency Injection Too Early

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(new NeedsRepositoryListener());
application.run(args);
~~~

A listener passed via `new` is not a Spring-managed bean. Especially at very early events, **there is no container yet** to inject `@Autowired OrderRepository` or call bean-dependent services. Extract DI-independent bootstrap logic, or move work requiring DI to a late event or runner.

### 10.3. One Event May Reach Multiple Contexts

In applications building a parent/child `ApplicationContext` tree (e.g., certain `SpringApplicationBuilder` setups), events propagate up to ancestor contexts per Spring's event multicasting rules. Thus a listener may receive events from multiple contexts, or observe repeated events of the same type in complex topologies. When needing to handle only one context, compare `event.getApplicationContext()` against the expected context on events that carry a context, instead of assuming every application has only one context.

### 10.4. Do Not Add Listeners Too Late

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
ConfigurableApplicationContext context = application.run(args);
application.addListeners(new EarlyEnvironmentListener()); // Too late!
~~~

The newly added listener cannot retroactively receive `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent` published earlier. If you want to listen to events once the context is running, use the context's own mechanism, remembering that prior lifecycle events are not replayed automatically.

### 10.5. Do Not Equate Spring Boot Events with Spring Framework Events

`ApplicationStartedEvent`, `ApplicationReadyEvent`, and `ApplicationFailedEvent` are published by Boot for a `SpringApplication` run. `ContextRefreshedEvent` and `ContextClosedEvent` belong to Spring Framework's `ApplicationContext` lifecycle. Both can be handled by an appropriate `ApplicationListener`, yet their semantics and timing are not the same.

## 11. Choosing an API by Requirement

| Requirement | Recommended Choice | Reason |
| --- | --- | --- |
| Catch `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent` | `SpringApplication.addListeners(...)` before `run` | Does not depend on an uncreated context or beans. |
| Write a library whose listener auto-receives early events in all consuming apps | Register `ApplicationListener` in `spring.factories` | Bootstrap loads the listener automatically without forcing users to edit `main`. |
| Only react once the app has finished starting up | `@EventListener(ApplicationReadyEvent.class)` or an `ApplicationListener` bean | Spring beans are ready, making DI easy. |
| Run business initialization work before Boot reports Ready | `ApplicationRunner` / `CommandLineRunner` | Dedicated milestone for logic running after refresh. |
| Observe/handle `ApplicationContext` shutdown | `@EventListener(ContextClosedEvent.class)` or `ApplicationListener<ContextClosedEvent>` | This is a context event, not Boot's "ready" milestone. |
| Configure resources before context refresh | `ApplicationContextInitializer` or appropriate configuration integration | Better stage and responsibility fit than treating a listener as a general configuration callback. |

## 12. Self-Check Exercises

**Question 1.** Why does an `@EventListener` bean not receive `ApplicationStartingEvent`?

**Answer:** The event occurs before `ApplicationContext` is created. Beans and `@EventListener` registration infrastructure do not exist yet at that time.

**Question 2.** To observe `ApplicationEnvironmentPreparedEvent` in the `main` method, when must it be registered?

**Answer:** Create `SpringApplication`, call `app.addListeners(...)` with an `ApplicationListener<ApplicationEnvironmentPreparedEvent>`, and **then** call `app.run(args)`.

**Question 3.** What is the most important difference between `ApplicationStartedEvent` and `ApplicationReadyEvent`?

**Answer:** `Started` occurs after context refresh but **before** `ApplicationRunner`/`CommandLineRunner`; `Ready` occurs **after** runners finish executing.

**Question 4.** Should you use `setListeners(...)` when you only want to attach one additional listener?

**Answer:** Normally no. `setListeners` replaces the listener collection and can overwrite prior configuration. `addListeners` is designed for appending.

**Question 5.** When a listener receives `ApplicationFailedEvent`, can it call repository beans as when the application is running normally?

**Answer:** You cannot assume so. The context may not be initialized or may only be partially initialized; use only information genuinely still available for diagnosis.

**Question 6.** Why does the section 4 example print `05 STARTED`, then `06 RUNNER`, then `07 READY`?

**Answer:** That is Spring Boot's standard lifecycle order: context refresh → Started event → runner → Ready event.

## References

- [Spring Boot 3.5 Reference — Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): events in order and how to register listeners before the context exists.
- [Spring Boot 3.5.16 Javadoc — SpringApplication](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html): `addListeners`, `setListeners`, `getListeners`, `run`.
- [Spring Boot 3.5.16 API — Application Event Classes](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/package-summary.html): lifecycle events of `SpringApplication`.
- [Spring Framework Javadoc — ApplicationListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationListener.html): `onApplicationEvent` interface.
- [Spring Boot 3.5 Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): processing and precedence of `Environment` configuration sources.
