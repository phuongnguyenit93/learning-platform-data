# SpringApplicationBuilder.listeners in Spring Boot Application Events

## 1. The Problem That listeners(...) Solves

When a Spring Boot application starts running, some events are published **before `ApplicationContext` is created or refreshed**. For example, `ApplicationStartingEvent` is published very early, and `ApplicationEnvironmentPreparedEvent` is published when `Environment` has been prepared while the context does not exist yet. If you register listeners solely as `@Component`, `@Bean`, or `@EventListener` methods, those components have not been created/registered in time to receive the earliest events.

`SpringApplicationBuilder.listeners(ApplicationListener<?>... listeners)` solves this problem by **attaching listener objects directly to `SpringApplication` before calling `run(...)`**. The listeners are used by Spring Boot for application lifecycle events and continue to be registered with `ApplicationContext` so they can receive regular Spring events once the context is running.

Conceptual example:

~~~java
new SpringApplicationBuilder(AppConfig.class)
    .listeners(
        (ApplicationListener<ApplicationStartingEvent>) event ->
            System.out.println("The application is starting")
    )
    .run(args);
~~~

This is an **illustrative snippet**, requiring relevant Spring Boot imports. By registering before `run(...)`, the handler can receive `ApplicationStartingEvent`; registering the listener as a regular bean at a later stage would be too late.

Three key questions of this lesson:

1. Which objects does `listeners(...)` accept and which part of startup does it affect?
2. Which events occur before and after `ApplicationContext` is ready?
3. How do you write, test, and operate early startup listeners without creating dependencies on beans that do not exist yet?

## 2. Exact API and Related Components

The method resides in package `org.springframework.boot.builder`, with signature:

~~~java
public SpringApplicationBuilder listeners(
        ApplicationListener<?>... listeners)
~~~

- **Parameters:** one or more objects implementing `org.springframework.context.ApplicationListener<?>`. You can pass a custom listener class or a lambda typed as a specific `ApplicationListener<EventType>`.
- **Return value:** the builder itself to continue fluent API configuration.
- **Effect:** adds listeners to the application being configured by the builder. Javadoc specifies they listen to both **SpringApplication events** and **regular Spring events** when the context runs.
- **When to use:** before `run(args)` to receive the earliest events. Calling it after an application has already started cannot "replay" events that already occurred.
- **Additional detail from Spring Boot 3.5 Javadoc:** if a listener also implements `ApplicationContextInitializer`, the builder adds it to the initializer list as well. The two callbacks have different roles; avoid duplicate initialization if a single class serves both roles.

Relationship:

~~~text
main(String[] args)
    |
    v
new SpringApplicationBuilder(AppConfig.class)
    | .web(WebApplicationType.NONE)
    | .properties(...)
    | .listeners(earlyListener, readyListener)
    | .run(args)
    v
SpringApplication
    |
    +--> publishes very early-stage events
    |       +--> earlyListener receives them
    |
    +--> creates and refreshes ApplicationContext
    |       +--> registers listeners with context
    |
    +--> publishes post-refresh / post-runner events
            +--> readyListener receives them
~~~

`SpringApplicationBuilder` is a tool for building/configuring `SpringApplication`. `listeners(...)` itself **does not create a new event**, does not directly invoke listeners, and is not a business-event publishing API. Events are published when Spring Boot executes the startup sequence or when the context dispatches events.

## 3. Boot Event Milestones and Available Data

Key milestones in Spring Boot 3.x can be viewed as follows:

| Event | Relative Timing | What Is Available and What Should You Do? |
|---|---|---|
| `ApplicationStartingEvent` | When `run` begins, before most initialization processing | Can record a very early signal; **neither Environment nor ApplicationContext exists yet** to read like beans |
| `ApplicationEnvironmentPreparedEvent` | `Environment` created/prepared, before context | Read or adjust environment configuration appropriately; do not request beans from context yet |
| `ApplicationContextInitializedEvent` | Context created and initializers invoked, before loading bean definitions | Observe at the nascent context stage; cannot assume beans are initialized |
| `ApplicationPreparedEvent` | Bean definitions loaded, right before refresh | Context exists, yet many singleton beans are still uninitialized |
| `ContextRefreshedEvent` | `ApplicationContext` finishes refreshing | Context components are ready per the refresh contract; does not mean all runners have completed |
| `ApplicationStartedEvent` | After context refresh, **before** `ApplicationRunner` and `CommandLineRunner` | Observe the milestone that the context has started, about to run runners |
| `AvailabilityChangeEvent` with `LivenessState.CORRECT` | After the started milestone | Boot announces liveness state |
| `ApplicationReadyEvent` | After application/command-line runners | Boot milestone indicating the application is ready to serve after startup |
| `AvailabilityChangeEvent` with `ReadinessState.ACCEPTING_TRAFFIC` | After the ready milestone | Readiness state is announced |
| `ApplicationFailedEvent` | If startup fails | Record failure cause; context may not exist or may not be usable |

This is the **conceptual order** of the main Boot events; depending on the application, web server events, bean lifecycle events, hierarchical applications, and business events may be interleaved. `ContextRefreshedEvent` is a Spring Framework event, while the `Application...Event` types listed are Spring Boot lifecycle events.

Because the initial milestones happen before the context exists, never call:

~~~java
// Invalid premise at ApplicationStartingEvent:
ApplicationContext ctx = ...;      // No context yet to inject.
MyService service = ctx.getBean(MyService.class);
service.execute();
~~~

The code above is a **counterexample**. If you need to work with initialized beans or network/DB dependencies, choose a later milestone, such as `ApplicationReadyEvent` or using `ApplicationRunner` / `CommandLineRunner`.

### Distinguishing Started and Starting

The names are very similar, yet their timing differs significantly:

- `ApplicationStartingEvent`: published earliest; context has not been created yet.
- `ApplicationStartedEvent`: after refresh; context exists, but Boot has not yet run `ApplicationRunner` / `CommandLineRunner`.
- `ApplicationReadyEvent`: after runners; suitable for observing the milestone when the application is ready.

A common API-learning mistake is attaching a listener to `ApplicationStartedEvent` when the goal is logging right before `Environment` is formed.

## 4. Standalone Java 17 Example with Spring Boot 3.5

The following example uses **Java 17+**, Spring Boot **3.5.16**, and Maven, running **without a web server** to focus on events. The program registers three listeners via `SpringApplicationBuilder.listeners(...)`, reads a configuration property once the environment is prepared, and observes the active context after ready.

Project structure:

~~~text
builder-listeners-demo/
├── pom.xml
└── src/main/java/demo/BuilderListenersDemo.java
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>builder-listeners-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
            <version>3.5.16</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Contents of `src/main/java/demo/BuilderListenersDemo.java`:

~~~java
package demo;

import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Configuration;

public class BuilderListenersDemo {

    public static void main(String[] args) {

        ApplicationListener<ApplicationStartingEvent> starting = event ->
            System.out.println("01 STARTING: context not created");

        ApplicationListener<ApplicationEnvironmentPreparedEvent> environment = event ->
            System.out.println("02 ENV: demo.mode=" +
                event.getEnvironment().getProperty("demo.mode"));

        ApplicationListener<ApplicationReadyEvent> ready = event ->
            System.out.println("03 READY: active=" +
                event.getApplicationContext().isActive());

        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(Config.class)
                    .web(WebApplicationType.NONE)
                    .bannerMode(Banner.Mode.OFF)
                    .logStartupInfo(false)
                    .properties("demo.mode=demo")
                    .listeners(starting, environment, ready)
                    .run(args)) {

            System.out.println("04 MAIN: active=" + context.isActive());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        // Minimal configuration; no controller, service, or web server needed.
    }
}
~~~

Run from the project directory using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.BuilderListenersDemo
~~~

With the command above **and no additional configuration parameters**, the lines printed by the application code, in exact order:

~~~text
01 STARTING: context not created
02 ENV: demo.mode=demo
03 READY: active=true
04 MAIN: active=true
~~~

Maven and Spring Boot may emit extra technical messages depending on logging configuration, yet the four program lines still demonstrate the observed milestones. Within a single run with three different event types, Boot publishes `ApplicationStartingEvent` before `ApplicationEnvironmentPreparedEvent`, while `ApplicationReadyEvent` arrives after context refresh and runners complete. The fourth line executes after `run(args)` returns.

**Line-by-line explanation:**

1. `starting` receives the event right when startup begins. The handler **does not try to read `ApplicationContext`** because the context does not exist yet.
2. `environment` receives `ApplicationEnvironmentPreparedEvent`; the event allows reading `getEnvironment()`. Property `demo.mode` was set by the builder via `properties(...)`, so it has value `demo` when not overridden by a higher-precedence property source.
3. `ready` receives `ApplicationReadyEvent` and observes an active `ConfigurableApplicationContext`.
4. `try-with-resources` closes the context when the `main` block ends. Because the program has no web server, exiting `main` is expected.

The example uses `@Configuration` as the configuration source and chooses `WebApplicationType.NONE`, so no HTTP controller or database is needed. No `Thread.sleep(...)` is used to illustrate startup because Spring Boot's event ordering is sufficient to observe the key milestones.

### Replacing Lambdas with a Listener Class

In larger applications, a listener can be written as a separate class:

~~~java
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class StartingTraceListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("SpringApplication is starting");
    }
}
~~~

This is an **illustrative class**. If placed in package `demo` with full imports, register it in `main`:

~~~java
new SpringApplicationBuilder(Config.class)
    .listeners(new StartingTraceListener())
    .run(args);
~~~

Using a concrete Java object fits well when the listener has multiple logic branches, needs isolated unit testing, or needs initialization with simple arguments. **Do not place mandatory `@Autowired` dependencies in the constructor of an early startup listener**: those beans do not exist yet at registration time.

## 5. Why Can't @Bean and @EventListener Replace listeners(...) at Early Stages?

The two styles below differ in **registration lifecycle**, not merely syntax.

**Registering via builder before run:**

~~~java
new SpringApplicationBuilder(AppConfig.class)
    .listeners(new StartingTraceListener())
    .run(args);
~~~

**Registering a bean through the context:**

~~~java
@Configuration
class AppConfig {
    @Bean
    ApplicationListener<ApplicationReadyEvent> readyBeanListener() {
        return event -> System.out.println("ready via bean");
    }
}
~~~

The `readyBeanListener` bean can receive events published after the context is created and the listener bean is registered. However, it **cannot turn back time** to receive `ApplicationStartingEvent`, which was already published before the context was created.

With an `@EventListener` method:

~~~java
@Component
class ReadyObserver {

    @EventListener
    void afterReady(ApplicationReadyEvent event) {
        System.out.println("context ready");
    }
}
~~~

This is also integration code requiring bean `ReadyObserver` to be scanned/registered. The method is processed by Spring during bean preparation and event listener adapter registration, so it fits events **after** that stage.

In the illustrative code snippets above, add imports for `org.springframework.context.annotation.Bean`, `org.springframework.stereotype.Component`, and `org.springframework.context.event.EventListener` according to the chosen registration style. These snippets are independent of `BuilderListenersDemo.java` and should not be pasted sequentially into the same file without additional configuration.

| Registration Approach | Can Catch Events Before Context Exists? | Depends on Context Beans? | Purpose |
|---|---|---|---|
| `SpringApplicationBuilder.listeners(...)` | Yes | Should not, especially early listeners | Hook into Boot lifecycle before `run` |
| `SpringApplication.addListeners(...)` | Yes, if called before `run` | Should not | Equivalent API when not using builder |
| `META-INF/spring.factories` | Yes, when Boot auto-loads at startup | Instantiated by Boot infrastructure; design context-independent | Auto-register listener when library is added to classpath |
| `@Bean ApplicationListener<?>` | No for events published before bean creation | Yes | Register listener via the context |
| `@EventListener` on a bean | No for events published before listener adapter is active | Yes | Concise handling for regular events |

How to choose depends on **when you need to receive the event**. Use the builder when configuring a listener specifically for a given run, directly passable in `main`; use a bean when the listener needs services/DAOs and only handles events once the context is ready.

## 6. ApplicationEnvironmentPreparedEvent and Early Configuration Customization

`ApplicationEnvironmentPreparedEvent` lets you observe or customize a `ConfigurableEnvironment` before the context is fully constructed. Example listener adding a low-priority `PropertySource` when a key is not set:

~~~java
import java.util.Map;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.env.MapPropertySource;

public final class BootstrapDefaults
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        var sources = event.getEnvironment().getPropertySources();
        sources.addLast(new MapPropertySource(
            "custom-bootstrap-defaults",
            Map.of("demo.audit.enabled", "true")
        ));
    }
}
~~~

This is an **integration class**. Register it:

~~~java
new SpringApplicationBuilder(Config.class)
    .listeners(new BootstrapDefaults())
    .run(args);
~~~

`addLast` appends the property source at the end of current precedence order, so higher-precedence configurations can override `demo.audit.enabled`. Use this when there is a clear reason to affect `Environment` early; for simple default values, `builder.properties("key=value")` is usually clearer and has fewer side effects.

**Note:** the order of `EnvironmentPostProcessor`s, property sources loaded by Boot, and listeners is coordinated by startup infrastructure. If you must control configuration very early across all applications (e.g., logging config or special config sources), consider a dedicated extension point rather than relying on a listener running in an unguaranteed order. Do not log passwords, tokens, or the entire `Environment` to stdout.

## 7. Catching Startup Errors with ApplicationFailedEvent

To observe startup failures, you can register:

~~~java
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

public final class FailedStartupListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        System.err.println("Startup failed: " + failure.getClass().getName());

        // Can inspect exception; avoid dereferencing context when null.
    }
}
~~~

This snippet is separate from the success-path example. `ApplicationFailedEvent` only appears when startup fails, so a fixed output line from it cannot be included in the success-path example.

Register before `run`:

~~~java
new SpringApplicationBuilder(Config.class)
    .listeners(new FailedStartupListener())
    .run(args);
~~~

Points to watch:

- Startup can fail **before the context is created**, so never assume `event.getApplicationContext()` is always non-null.
- A failure listener itself can throw an error. Keep the logger/handler minimal, avoiding complex logic or accessing unready beans.
- Log only necessary technical details, avoiding exposing sensitive data from the exception chain or configuration.
- This event does not replace process monitoring, exit codes, or runtime health checks.

When needing to clean up resources after the application has run and then closes, that is the domain of `ContextClosedEvent` and lifecycle/shutdown, distinct from `ApplicationFailedEvent` on **startup failure**.

## 8. Comparing listeners(...) with Nearby APIs

### SpringApplication.addListeners(...)

If not using the builder, the equivalent way to register before startup is:

~~~java
SpringApplication app = new SpringApplication(Config.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.addListeners(new StartingTraceListener());
app.run(args);
~~~

Both APIs provide the ability to pass `ApplicationListener` into `SpringApplication` before running. `SpringApplicationBuilder` is convenient when needing fluent configuration, profiles, parent/child contexts, or combining many options in one expression.

### SpringApplicationBuilder.initializers(...)

`ApplicationContextInitializer<ConfigurableApplicationContext>` is a callback that **customizes the context before bean definitions are loaded**. It is not an event listener:

~~~java
ApplicationContextInitializer<ConfigurableApplicationContext> init =
    context -> context.getEnvironment()
        .setDefaultProfiles("demo");

new SpringApplicationBuilder(Config.class)
    .initializers(init)
    .run(args);
~~~

This is illustrative code requiring imports for `org.springframework.context.ApplicationContextInitializer` and `org.springframework.context.ConfigurableApplicationContext`. Use an initializer when you want to customize the context directly at the point where the context already exists. Use a listener when you need to observe one or more specific events, especially events before the context exists.

Subtle point: Javadoc for `SpringApplicationBuilder.listeners(...)` notes that an `ApplicationListener` object that is also an `ApplicationContextInitializer` is added to the initializers list as well. When building an extension combining both roles, do not treat them as a single callback; if an operation has side effects, ensure the logic is idempotent and timing-aware.

### META-INF/spring.factories

A library may want its listener auto-discovered in every application using the library, whether that application invokes `SpringApplication.run` or `SpringApplicationBuilder`. You can place a file at:

~~~text
src/main/resources/META-INF/spring.factories
~~~

with contents:

~~~properties
org.springframework.context.ApplicationListener=demo.StartingTraceListener
~~~

The listener is registered via Spring Boot's factory loading mechanism. The class must be in the right package, instantiable by the factory loader (typically via a no-arg constructor), and the JAR containing the resource must be on the classpath. This registration suits libraries/bootstrap integrations; for logic inside a single `main`, `listeners(...)` directly is clearer.

Note that `spring.factories` for registering `ApplicationListener` **differs** from `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` used for auto-configuration. Do not mechanically swap one mechanism for the other.

## 9. Hierarchical ApplicationContexts: Why Might a Listener Receive an Event Multiple Times?

`SpringApplicationBuilder` also supports `parent(...)`, `child(...)`, and `sibling(...)` to construct `ApplicationContext`s in a tree. In Spring Framework, events from a **child context** can be forwarded up to the **parent context**. Therefore, when placing a listener on the parent and an event originates in the child, the parent's listener may also receive events of the same type published in the child.

Example structure (illustrative code, requiring two configuration classes and proper imports):

~~~java
new SpringApplicationBuilder(ParentConfig.class)
    .web(WebApplicationType.NONE)
    .child(ChildConfig.class)
    .web(WebApplicationType.NONE)
    .run(args);
~~~

Exact context sequencing and event forwarding depend on the event type, how each `SpringApplication` starts, and listener configuration; **do not assert every event is published strictly once across the entire tree**.

If a listener needs to handle **only events from its own context**, for events with `getApplicationContext()`, compare context instances rather than comparing only event type:

~~~java
public void onApplicationEvent(ApplicationReadyEvent event) {
    if (event.getApplicationContext() == myContext) {
        // Handle event for the intended context.
    }
}
~~~

This is an **illustrative conditional snippet**; `myContext` must be properly initialized, e.g., the context to which the listener is bound, and determining it inside an early startup listener must account for context lifecycle. For `ApplicationStartingEvent`, there is no context yet to use this check: you may need to identify the source `SpringApplication` or use per-application listener registration policies.

Do not place non-idempotent tasks such as sending emails, writing audit logs, or creating jobs inside a listener that could be invoked from multiple hierarchy levels without source discrimination and deduplication.

## 10. Listener Ordering, @Order, and Error Behavior

### Handler Ordering

Multiple listeners registered for the same event type can be ordered via `Ordered` or `@Order`. Example:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;
import org.springframework.boot.context.event.ApplicationReadyEvent;

public final class PriorityReadyListener
        implements ApplicationListener<ApplicationReadyEvent>, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("high priority ready listener");
    }
}
~~~

This is an illustrative class that can be passed via `listeners(new PriorityReadyListener())`. Do not rely on default ordering of two listeners with equal priority to express mandatory business dependencies. If steps depend on one another, put them in an explicitly ordered workflow rather than splitting them into independent listeners.

### Exceptions in Listeners

Default event listeners are usually invoked synchronously on the event-publishing thread. A slow listener slows down startup; a listener throwing an exception early can fail startup or alter error-handling paths. Depending on stage and broadcaster, how exceptions are collected or propagated can vary.

Do not use early startup listeners for slow HTTP calls, DB queries, queue waits, or uncontrolled background tasks. When post-readiness work is needed, use `ApplicationRunner` or `CommandLineRunner`. When periodic work is needed, consider a scheduler or dedicated orchestration mechanism.

Placing `@Async` on a method of an object passed directly to `listeners(...)` does not guarantee Spring proxy/async infrastructure exists at very early events. Check who instantiates the listener, whether it passes through a proxy, and whether `@EnableAsync` is active yet. For early listeners, keep processing lightweight and synchronous so it is easy to control.

### Logging

For `ApplicationStartingEvent`, the logging system may not yet be completely prepared. Boot's internal components also process these events to configure logging and the environment. Therefore, if the primary goal is production telemetry or tracing, use appropriate observability integration/extension points and verify registration order; `System.out.println` in examples only illustrates event timing.

## 11. Verifying with Integration Tests Instead of Assuming Order

A practical way to confirm a listener was registered before `run(...)` is to create the context in a test, record events into a thread-safe collection, and assert the **event types** that occurred:

~~~java
List<String> observed = new CopyOnWriteArrayList<>();

ApplicationListener<ApplicationStartingEvent> starting =
    event -> observed.add("starting");

ApplicationListener<ApplicationReadyEvent> ready =
    event -> observed.add("ready");

try (ConfigurableApplicationContext context =
        new SpringApplicationBuilder(Config.class)
            .web(WebApplicationType.NONE)
            .bannerMode(Banner.Mode.OFF)
            .listeners(starting, ready)
            .run()) {

    if (!observed.equals(List.of("starting", "ready"))) {
        throw new AssertionError("Unexpected lifecycle: " + observed);
    }
}
~~~

The snippet above **illustrates a test**; it requires importing `java.util.List`, `java.util.concurrent.CopyOnWriteArrayList`, and Spring types as in the main example. It can be placed inside a test method or sample program with `Config` configured. Because only two specifically typed events are recorded, the expected `[starting, ready]` result does not depend on other events published in between.

Test additional meaningful cases:

1. **Early listener:** registered via builder must observe `ApplicationStartingEvent`.
2. **Environment configuration:** environment listener reads properties only after `Environment` is prepared.
3. **Late listener:** `ApplicationReadyEvent` handler accesses an active context with runners completed.
4. **Startup failure:** intentionally make a bean or runner throw an exception; confirm the `ApplicationFailedEvent` listener sees the error without assuming the context is always non-null.
5. **Hierarchical contexts:** if the application uses `child(...)`, verify events from child/parent are properly filtered, avoiding duplicate side effects.
6. **Execution duration:** bound work inside startup listeners so startup latency does not grow unexpectedly.

Do not try to test by taking an already-running context, calling `context.addApplicationListener(...)`, and expecting to observe `ApplicationStartingEvent`. Events already published are not replayed by that mechanism.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Registering `@Bean ApplicationListener<ApplicationStartingEvent>` | Bean does not exist yet when early event is published | Use `SpringApplicationBuilder.listeners(...)` before `run` |
| Confusing `ApplicationStartedEvent` with `ApplicationStartingEvent` | Handler runs after refresh instead of when startup starts | Pick the right event type and verify the milestone |
| Injecting services/DAOs with `@Autowired` into early listener | Context/beans not ready, flawed design | Use only data available at the event; move logic to a later milestone |
| Treating `listeners(...)` as an event publisher | Code does not publish events as expected | Use `ApplicationEventPublisher.publishEvent(...)` for business events |
| Reading beans in `ApplicationEnvironmentPreparedEvent` | Context not created yet | Use `event.getEnvironment()`; wait until after refresh for beans |
| Doing slow I/O in early listeners | Startup latency increases or fails | Keep listener lightweight; move work to runner/worker |
| Adding listener after `run(...)` | Misses early events | Register before calling run |
| Registering same listener in both builder and bean | Can cause duplicate side effects or confusing provenance | Pick one registration path or design idempotently |
| Relying on default listener order | Order is not a business contract | Use `Ordered` when needed, or a sequential workflow |
| Not filtering events in a context hierarchy | Duplicate processing when child events propagate to parent | Compare context/event source and deduplicate |
| Assuming failure event always has a context | `NullPointerException` in error handler | Null-check and log exceptions safely |
| Putting `@Async` on an object without a Spring proxy | Handler still runs synchronously | Understand lifecycle/proxies; use async after infrastructure is ready |

## 13. When Should You Choose SpringApplicationBuilder.listeners?

Choose `listeners(...)` when:

- You want to listen to `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent`, which occur before context beans are ready.
- You need to declare a listener **specifically for one startup run** in `main` or in a launch wrapper with fluent configuration.
- You need to combine setting profiles, properties, application type, and listeners in one clear builder chain.
- You want to observe startup/readiness milestones for logging, timing, or small bean-independent setup.

You do not need a separate builder solely for a regular listener in an already-running application. For business events and Spring-bean-dependent listeners, `@EventListener` or an `ApplicationListener` bean is usually simpler. For one-time post-startup actions needing services, `ApplicationRunner` / `CommandLineRunner` can express the flow more clearly. For libraries needing automatic listener loading in every application, consider `META-INF/spring.factories`.

### Official Documentation References

- [Spring Boot 3.5 Javadoc — SpringApplicationBuilder](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html) — `listeners(...)` signature and contract.
- [Spring Boot Reference — SpringApplication Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html) — event types, ordering, and early listener registration.
- [Spring Boot 3.5 Javadoc — SpringApplication](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html) — `addListeners(...)` and listener management.
- [Spring Boot How-to — Customize the Environment or ApplicationContext Before It Starts](https://docs.spring.io/spring-boot/how-to/application.html) — bootstrap customization and `spring.factories`.

## 14. Summary

`SpringApplicationBuilder.listeners(...)` adds `ApplicationListener`s **before `SpringApplication.run(...)` begins**, allowing listeners to observe very early startup events that `@Component`, `@Bean`, or `@EventListener` methods cannot receive in time. Listeners are registered on `SpringApplication` and continue receiving context events once the context is active. Choose events based on data genuinely available at each milestone, keep startup logic lightweight, and especially remember that `ApplicationStartingEvent` differs from `ApplicationStartedEvent`. When dealing with context trees, startup failures, or ordering requirements, verify behavior with integration tests rather than guessing.
