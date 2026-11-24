# SpringApplication Event Map Across the Startup Process

## Objectives

Spring Boot emits multiple events (*application events*) while `SpringApplication.run(...)` prepares the environment, creates the `ApplicationContext`, refreshes the bean container, runs runners, transitions availability states, and signals readiness. Identifying the **right milestone** helps you place listeners, inspect startup, log, load configuration, and manage readiness without mistakenly accessing a container that is not ready yet.

This lesson belongs to **Spring Boot Application Runtime → Application Events**, using the API and lifecycle of **Spring Boot 3.3.13 / Spring Framework 6.1**. After completing it, you will be able to:

1. Read the exact order of `ApplicationStartingEvent`, `ApplicationEnvironmentPreparedEvent`, `ApplicationContextInitializedEvent`, `ApplicationPreparedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent`, and the `ApplicationFailedEvent` branch.
2. Place `ContextRefreshedEvent` and `WebServerInitializedEvent` in the right window of the startup process.
3. Distinguish `SpringApplication` events from `AvailabilityChangeEvent` carrying `LivenessState` or `ReadinessState`.
4. Know when `Environment` does not exist yet, when the context has been created but not refreshed, and when beans can be accessed safely.
5. Register listeners early enough using `SpringApplication.addListeners(...)` or `META-INF/spring.factories`; distinguish this from `@EventListener` on a bean.
6. Run a Java 17+ example to observe both the successful startup path and a failure inside a startup runner.

## 1. Why Do We Need an Event "Map"?

There is no single event that represents every meaning of "the application has started." During a startup:

- `Environment` appears before `ApplicationContext`.
- The context is created, `ApplicationContextInitializer` instances run, and bean definitions are loaded **before** `refresh()`.
- During `refresh()`, Spring creates many singletons, starts infrastructure, and emits `ContextRefreshedEvent`.
- `ApplicationStartedEvent` appears **after refresh** but **before** `ApplicationRunner`/`CommandLineRunner`.
- `ApplicationReadyEvent` appears **after** the runners complete successfully.
- Availability has its own notifications: **live** after refresh and **ready to accept traffic** after the ready event.
- If startup fails, `ApplicationFailedEvent` is a **failure branch**, not the final event of every startup.

Picking the wrong milestone causes bugs such as calling `getBean` when bean definitions are not loaded yet, running heavy migrations in an early listener, marking the app ready before data is prepared, or registering a `@Bean` listener too late to see initial events.

**Principle:** An event signals a *progress milestone* and permission to use the corresponding API. An event does not mean every component or external service is healthy.

## 2. Standard Timeline in Spring Boot 3.3

A typical successful run of `SpringApplication` follows this sequence. This is the order **documented by Spring Boot**, with the two Spring context/web events placed within the refresh window:

~~~text
main(String[] args)
    |
    v
SpringApplication.run(args)
    |
    +-- 01. ApplicationStartingEvent
    |       (listeners/initializers registered; no Environment yet)
    |
    +-- 02. ApplicationEnvironmentPreparedEvent
    |       (Environment is available; ApplicationContext not created yet)
    |
    +-- Create context, invoke ApplicationContextInitializer
    |
    +-- 03. ApplicationContextInitializedEvent
    |       (context prepared; bean definitions not loaded yet)
    |
    +-- Load bean definitions / prepare context
    |
    +-- 04. ApplicationPreparedEvent
    |       (bean definitions loaded; refresh not called yet)
    |
    +-- ApplicationContext.refresh()
    |       |-- BeanFactoryPostProcessors, BeanPostProcessors
    |       |-- Initialize non-lazy singletons / infrastructure
    |       |-- [web] WebServerInitializedEvent
    |       +-- ContextRefreshedEvent
    |           (these two web/context events belong to the refresh window;
    |            do not rely on an absolute order across all callbacks)
    |
    +-- 05. ApplicationStartedEvent
    |
    +-- 06. AvailabilityChangeEvent(LivenessState.CORRECT)
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- 07. ApplicationReadyEvent
    |
    +-- 08. AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
    |
    +-- run(...) returns ConfigurableApplicationContext
            |
            v
        Application running
~~~

When **startup throws an exception**, there is an additional branch:

~~~text
Some phase of SpringApplication.run(...)
    |
    +-- unrecoverable exception during startup
            |
            v
        ApplicationFailedEvent
            |
            +-- Log error / failure analysis / best-effort cleanup
            +-- run(...) exits with exception, does not reach ready
~~~

`ApplicationFailedEvent` can occur at multiple stages: before the context exists, during refresh, or when a runner throws an exception. Therefore, do not treat it as "step 9 guaranteed to appear after ready."

In the success map, order 01–08 represents the **primary operational milestones**. For a non-web application with no embedded HTTP server, there is **no** corresponding `WebServerInitializedEvent`. For applications with multiple parent/child contexts or multiple bootstrap runs, each run and each context must be evaluated separately.

## 3. Quick Reference Table: Event, Timing, and What Is Ready

| Event or milestone | Timing | What can you rely on? | What you should not assume yet |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | Very start of `run`, after registering listeners/initializers | `SpringApplication` info, raw args | No `Environment`/`ApplicationContext` yet |
| `ApplicationEnvironmentPreparedEvent` | `Environment` prepared for the first time | `ConfigurableEnvironment` to read/customize appropriate property sources | No Spring application context yet |
| `ApplicationContextInitializedEvent` | Context created, initializers have run | Prepared `ConfigurableApplicationContext` | Application bean definitions not loaded yet; not refreshed yet |
| `ApplicationPreparedEvent` | Bean definitions loaded, right before refresh | Prepared context and bean definitions | Do not assume application singletons are initialized |
| `ContextRefreshedEvent` | `ApplicationContext.refresh()` completes | BeanFactory/context refreshed successfully | Boot runners may not have run yet |
| `WebServerInitializedEvent` (web) | Server initialized during web startup | Server initialized, port information can be obtained | Does not automatically prove application readiness |
| `ApplicationStartedEvent` | After refresh, before runners | Context has been refreshed | Startup runners have not finished yet |
| `AvailabilityChangeEvent(LivenessState.CORRECT)` | Right after the started event | Spring Boot considers the context live | Not synonymous with ready to accept traffic |
| `ApplicationReadyEvent` | After runners | Main Boot startup phase has completed | The availability readiness event is emitted right **after** this milestone |
| `AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)` | After the ready event | Boot signals the instance is ready to accept traffic | Does not guarantee external dependencies are always healthy |
| `ApplicationFailedEvent` | When a startup error occurs | Exception that caused failure, context if it already exists | Context is not always present; not a request error |

All four initial `Application...Event` events are emitted **before** `refresh()`. The biggest differences among them lie in **whether Environment exists, whether the context exists, and whether bean definitions have been loaded**.

The events from `ApplicationStartingEvent` through `ApplicationReadyEvent` and `ApplicationFailedEvent` form the `SpringApplication`-specific event group in the `org.springframework.boot.context.event` package. `ContextRefreshedEvent` is a **Spring Framework** event in `org.springframework.context.event`; `AvailabilityChangeEvent` belongs to `org.springframework.boot.availability` and is not a subclass of `SpringApplicationEvent`. They can still be observed through the Spring `ApplicationListener` mechanism.

## 4. Stage-by-Stage Breakdown

### 4.1. ApplicationStartingEvent: No Environment Yet

`ApplicationStartingEvent` is emitted at a very early stage of `SpringApplication.run(...)`, right after the required listeners and initializers have been registered. You cannot use `Environment.getProperty(...)` or `ApplicationContext.getBean(...)` yet because those components have not been created for the run.

Appropriate work includes recording a minimal startup milestone, integrating very early bootstrap mechanisms, or preparing components that do not require application beans. Listeners should be lightweight and avoid depending on complex logging or bean initialization at this point.

This is why a listener created via `@Bean` **cannot be guaranteed to receive** `ApplicationStartingEvent`: bean definitions are only processed at a later stage.

### 4.2. ApplicationEnvironmentPreparedEvent: Environment Exists, No Context Yet

At this point `ConfigurableEnvironment` exists and will be used for the application context, but the context has not been created yet. Listeners can read existing property sources and add/adjust property sources within appropriate bounds.

**Partial illustrative** example:

~~~java
if (event instanceof ApplicationEnvironmentPreparedEvent prepared) {
    String appName = prepared.getEnvironment()
            .getProperty("spring.application.name", "unnamed");
    System.out.println("Application name: " + appName);
}
~~~

The snippet above assumes `event` has type `ApplicationEvent` and imports `ApplicationEnvironmentPreparedEvent`. Note that Config Data and property source precedence have their own mechanisms; you **should not arbitrarily add secrets or override properties** in a listener.

Do not call `getApplicationContext()` on this event: it provides an environment, not an application context yet.

### 4.3. ApplicationContextInitializedEvent: Context Exists, Bean Definitions Not Loaded

`ApplicationContextInitializedEvent` is emitted after Spring Boot has created and prepared the context and invoked the `ApplicationContextInitializer` instances. At this point the context type (`SERVLET`, `REACTIVE`, or `NONE`, which led to the corresponding implementation) is known, but you cannot assume the application's `@Bean`/`@Component` definitions have been loaded.

Key distinction to remember:

- `ApplicationContextInitializer`: callback that **modifies the context** during preparation.
- `ApplicationContextInitializedEvent`: event that **signals the initializers have run**.

The two mechanisms are related but cannot be swapped arbitrarily.

### 4.4. ApplicationPreparedEvent: Bean Definitions Loaded, Refresh Not Started

After bean definitions are loaded, Spring Boot emits `ApplicationPreparedEvent` right before refresh. `Environment` is ready; bean definitions exist; many application singletons have still not been initialized. Calling `context.getBean(...)` in this early event may trigger premature bean creation or disrupt the normal lifecycle.

If you need to work with beans after the container is operational, use a later hook such as `ContextRefreshedEvent`, `ApplicationStartedEvent`, or a runner, depending on the task.

### 4.5. ContextRefreshedEvent and WebServerInitializedEvent

`ContextRefreshedEvent` signals that an `ApplicationContext` has been refreshed. During refresh, Spring prepares the BeanFactory, runs post-processors, creates eligible non-lazy singletons, and starts appropriate infrastructure.

For web applications, `WebServerInitializedEvent` appears when the embedded web server is ready during web startup, in the variant `ServletWebServerInitializedEvent` or `ReactiveWebServerInitializedEvent`. Spring Boot documentation places these events **after Prepared and before Started**; you should not rely on an absolute log order among all server and context callbacks without considering the web server implementation.

To determine the actual server port (especially with `server.port=0`), the web server initialized event is a more accurate signal than reading the configured port before the server binds. However, the web server having started **does not mean** startup runners have finished or readiness is accepting traffic.

### 4.6. ApplicationStartedEvent and Liveness

Once refresh completes, Spring Boot emits `ApplicationStartedEvent`, and then emits `AvailabilityChangeEvent` with `LivenessState.CORRECT`. This is how Boot indicates internal state after the context starts up successfully.

**Liveness ≠ readiness.** Liveness reflects whether the process can operate validly or needs to be restarted; readiness reflects whether traffic should be routed to the instance right now.

Important note: `ApplicationRunner` and `CommandLineRunner` **have not been called yet at the time of ApplicationStartedEvent**, so you should not use this event to declare that all application startup tasks are complete.

### 4.7. ApplicationReadyEvent and Readiness

After `ApplicationStartedEvent` and liveness correct, Spring Boot runs `ApplicationRunner`/`CommandLineRunner` beans in their configured order (`@Order`/`Ordered` if needed). Once the runners complete successfully, Boot emits `ApplicationReadyEvent`, followed by `AvailabilityChangeEvent` with `ReadinessState.ACCEPTING_TRAFFIC`.

You can use `ApplicationReadyEvent` to log the startup completion milestone, observe metrics, or perform very brief work. If a task **must complete before the application reaches ready**, place it in an appropriate runner with clear timeouts and error handling, rather than spawning an indefinite background loop inside a ready listener.

Boot marking the application as ready **does not guarantee** that an external DB, cache, or downstream API is always reachable. If routing depends on external systems, design an appropriate readiness/health policy instead of assuming every dependency stays permanently healthy.

### 4.8. ApplicationFailedEvent: Startup Failure Branch

`ApplicationFailedEvent` is emitted when `SpringApplication` fails to start up. Listeners can inspect `getException()` for diagnostics, and `getApplicationContext()` may not have a useful value if the error occurred before context creation.

A failure inside a runner is easy to visualize: the context has refreshed and may have already emitted `ApplicationStartedEvent` along with liveness correct, but the runner throws an exception, so **ApplicationReadyEvent** and **ReadinessState.ACCEPTING_TRAFFIC** will not appear on the normal success path.

`ApplicationFailedEvent` is **not** emitted for HTTP 4xx/5xx responses, controller exceptions, or client-aborted requests after the application has started. Those are separate runtime flows requiring dedicated exception handling and telemetry.

## 5. Why Early Listener Registration Matters

There are three common approaches.

### Approach A: SpringApplication.addListeners Before run

~~~java
SpringApplication application = new SpringApplication(DemoApplication.class);
application.addListeners(new MyStartupListener());
application.run(args);
~~~

This is a **partial illustration**; `DemoApplication` and `MyStartupListener` must be defined. This is the clearest option when you own `main`. The listener is registered before Boot emits the initial events, so it can observe `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`.

### Approach B: META-INF/spring.factories

A library or application that wants to auto-register a listener can declare:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Contents:

~~~properties
org.springframework.context.ApplicationListener=com.example.events.MyStartupListener
~~~

In Spring Boot 3.3, the key for listeners is **`org.springframework.context.ApplicationListener`**. The class must be instantiable by the Spring factories mechanism, typically with a no-argument constructor. When using this approach, do not register the same listener again via `addListeners` just to observe a startup unless duplicate handling is intentional.

`spring.factories` for listeners here is **not the same** as `AutoConfiguration.imports`, which is a separate mechanism for auto-configuration.

### Approach C: Spring-Managed @EventListener or ApplicationListener Bean

Once the application context has loaded and initialized beans, you can write:

~~~java
@Component
public class ReadyObserver {

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("READY observer: beans are available");
    }
}
~~~

This is **partial illustrative code**; it requires importing `Component`, `EventListener`, `ApplicationReadyEvent`, and a valid Spring Boot project. Bean listeners are suitable for **late** events once the context has been initialized. They cannot travel back in time to receive startup events emitted before their bean existed.

| Need | Suitable registration point |
| --- | --- |
| Receive `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent` | `addListeners` before `run` or `spring.factories` |
| Observe `ApplicationPreparedEvent` from very early on | Early-registered listener |
| Observe `ContextRefreshedEvent`, started/ready when beans are ready | `@EventListener` or Spring-managed `ApplicationListener` |
| Run work that must finish before ready | `ApplicationRunner` / `CommandLineRunner` |
| Modify beans/context before refresh | `ApplicationContextInitializer`, respecting the context contract |
| Observe application availability | `AvailabilityChangeEvent` or `ApplicationAvailability` |

If a listener needs to observe all milestones from the beginning, choose early registration and avoid depending on the bean container in the listener's constructor.

## 6. Runnable Example: Logging the Full Timeline and Simulating Startup Failure

The example below uses **Java 17**, **Spring Boot 3.3.13**, and **Gradle**. The application is **non-web** to avoid clutter from embedded server logs and events while still using the full `SpringApplication` and `ApplicationContext`. We register an `ApplicationListener<ApplicationEvent>` before `run` to capture early events, context events, and availability events.

### 6.1. Directory Structure

~~~text
spring-events-timeline/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/events/
    ├── EventsTimelineApplication.java
    └── TimelineListener.java
~~~

**File `settings.gradle`:**

~~~groovy
rootProject.name = 'spring-events-timeline'
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.events.EventsTimelineApplication'
}
~~~

The sample project uses `spring-boot-starter` without `spring-boot-starter-web`; the non-web mode is explicitly configured in code. The installed Gradle version must be compatible with Spring Boot 3.3. If the project includes a Gradle Wrapper, you can use the wrapper instead of the `gradle` command.

### 6.2. Main Class and Runner

**File `src/main/java/com/example/events/EventsTimelineApplication.java`:**

~~~java
package com.example.events;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EventsTimelineApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EventsTimelineApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Important: register before calling run().
        application.addListeners(new TimelineListener());

        // This callback runs before ApplicationContextInitializedEvent.
        application.addInitializers(context ->
                System.out.println("INIT: context initializer"));

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner demonstrateRunner() {
        return args -> {
            System.out.println("RUNNER: executed");

            // Used only to test the failure branch when the caller passes --fail-demo.
            if (args.containsOption("fail-demo")) {
                throw new IllegalStateException(
                        "Intentional startup failure");
            }
        };
    }
}
~~~

`ApplicationRunner` receives `ApplicationArguments`, allowing it to check for the `--fail-demo` option. Without the option, the runner finishes normally. `try-with-resources` actively closes the context once `run` returns and the `try` body completes; this structure is meant for a **CLI demo**. In a long-running web application, do not close the context immediately upon startup completion.

### 6.3. Listener Tracking Multiple Event Types

**File `src/main/java/com/example/events/TimelineListener.java`:**

~~~java
package com.example.events;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;

public final class TimelineListener
        implements ApplicationListener<ApplicationEvent> {

    @Override
    public void onApplicationEvent(ApplicationEvent event) {

        if (event instanceof ApplicationStartingEvent) {
            print("STARTING");

        } else if (event instanceof ApplicationEnvironmentPreparedEvent) {
            print("ENVIRONMENT_PREPARED");

        } else if (event instanceof ApplicationContextInitializedEvent) {
            print("CONTEXT_INITIALIZED");

        } else if (event instanceof ApplicationPreparedEvent) {
            print("PREPARED");

        } else if (event instanceof ContextRefreshedEvent) {
            print("CONTEXT_REFRESHED");

        } else if (event instanceof ApplicationStartedEvent) {
            print("STARTED");

        } else if (event instanceof AvailabilityChangeEvent<?> availability) {
            Object state = availability.getState();
            if (state == LivenessState.CORRECT) {
                print("LIVENESS_CORRECT");
            } else if (state == ReadinessState.ACCEPTING_TRAFFIC) {
                print("READINESS_ACCEPTING");
            }

        } else if (event instanceof ApplicationReadyEvent) {
            print("READY");

        } else if (event instanceof ApplicationFailedEvent) {
            print("FAILED");
        }
    }

    private static void print(String value) {
        System.out.println("EVENT: " + value);
    }
}
~~~

Details that make the example easy to verify:

- The listener implements `ApplicationListener<ApplicationEvent>`, so it can observe multiple subtypes of `ApplicationEvent`. In practice, register listeners with specific types if you only need one or two event types.
- `instanceof AvailabilityChangeEvent<?>` is supported in Java 17; `getState()` can hold `LivenessState` or `ReadinessState`. We only print two illustrative states to keep the startup log concise and avoid mixing in shutdown events.
- Because the code does not use the web starter, it does not emit `WebServerInitializedEvent`. When switching to a web application, you can add a branch to receive web server events if needed.
- The code deliberately does **not** read `ApplicationContext` during `STARTING` or `ENVIRONMENT_PREPARED`; a context is not guaranteed at those two milestones.
- The listener is not a Spring bean; it is added directly to `SpringApplication` before `run`, so it captures early events that a bean listener cannot receive from the start.

### 6.4. Running the Success Path

From the `spring-events-timeline` directory:

~~~bash
gradle bootRun
~~~

If the project has a Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows.

Ignoring framework/Gradle logs that may vary, **the lines printed by the Java code in this demo configuration** follow the expected order:

~~~text
EVENT: STARTING
EVENT: ENVIRONMENT_PREPARED
INIT: context initializer
EVENT: CONTEXT_INITIALIZED
EVENT: PREPARED
EVENT: CONTEXT_REFRESHED
EVENT: STARTED
EVENT: LIVENESS_CORRECT
RUNNER: executed
EVENT: READY
EVENT: READINESS_ACCEPTING
MAIN: run returned
MAIN: context closed
~~~

The line `INIT: context initializer` sits between prepared environment and initialized context, confirming that `ApplicationContextInitializedEvent` is emitted **after** the application context initializers run.

Looking at the two milestones `STARTED` and `READY`, you can see the runner sits **between them**, while the liveness correct state arrives before the runner and readiness accepting arrives after ready.

The CLI program closes the context on exit, so other shutdown events such as `ContextClosedEvent` may occur. `TimelineListener` does not print them. They are not included in the startup list above.

### 6.5. Running the Failure Branch Inside ApplicationRunner

Pass an option to make the runner deliberately throw an exception:

~~~bash
gradle bootRun --args="--fail-demo"
~~~

The lines printed by the application **before the framework logs the exception**:

~~~text
EVENT: STARTING
EVENT: ENVIRONMENT_PREPARED
INIT: context initializer
EVENT: CONTEXT_INITIALIZED
EVENT: PREPARED
EVENT: CONTEXT_REFRESHED
EVENT: STARTED
EVENT: LIVENESS_CORRECT
RUNNER: executed
EVENT: FAILED
~~~

Afterward, Gradle/Boot may display the startup failure and exit with a non-zero exit code. Because `application.run(args)` threw an exception before returning a context, execution never enters the `try` body, so **neither** `MAIN: run returned` nor `MAIN: context closed` is printed. This failure path also **does not** produce `EVENT: READY` or `EVENT: READINESS_ACCEPTING`.

Note: The `FAILED` line demonstrates that the listener was present early and therefore got notified. If a failure occurs very early, the context may not exist yet; listeners must avoid attempting to retrieve beans to report errors. In production code, log exceptions safely, limit sensitive information, and avoid throwing a second exception during diagnostics.

### 6.6. Switching to a Web Application

To also observe web server initialization, **create a variant of the project** by changing the starter dependency to:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
~~~

and in `main`, remove the line:

~~~java
application.setWebApplicationType(WebApplicationType.NONE);
~~~

Those two snippets are **partial changes** to the Section 6 project, not a separate program. When running the web version, Tomcat is configured by Spring Boot according to the default dependency, and the listener can observe `ServletWebServerInitializedEvent` if you add a print branch:

~~~java
if (event instanceof ServletWebServerInitializedEvent serverEvent) {
    System.out.println(
            "EVENT: WEB_SERVER_PORT=" + serverEvent.getWebServer().getPort());
}
~~~

This is an **additional illustrative snippet**; it requires importing `org.springframework.boot.web.servlet.context.ServletWebServerInitializedEvent` and placing it at the appropriate spot in `onApplicationEvent`. Do not alter the non-web sample's logic just to force a web event to appear. With `spring-boot-starter-webflux`, the corresponding event is `ReactiveWebServerInitializedEvent` (if the application uses a reactive web server).

The web event may appear between `PREPARED` and `STARTED`, during the context refresh phase; do not treat it as a readiness signal. If you want to determine which context actually emitted an event in a hierarchical application, inspect the event's context information.

## 7. Three Easily Confused "Ready" Milestones

### Context Refreshed

`ContextRefreshedEvent` indicates that context refresh succeeded. Most non-lazy singletons and bean lifecycles have been processed according to the container contract. However, Spring Boot **has not necessarily** finished running startup runners yet.

### Application Started

`ApplicationStartedEvent` occurs after refresh but before runners. Right after that milestone, Boot emits `LivenessState.CORRECT`. Liveness is the state infrastructure uses to decide whether an instance is internally healthy; it **does not** represent permission to receive traffic.

### Application Ready

`ApplicationReadyEvent` occurs after runners complete, and then Boot emits `ReadinessState.ACCEPTING_TRAFFIC`. This is the sequence typically used to determine that an instance has completed full startup. Readiness can be changed at runtime when the application decides to stop accepting traffic, such as during maintenance or when a critical resource becomes temporarily unavailable.

| Signal | Question it answers |
| --- | --- |
| `ContextRefreshedEvent` | Has the Spring context finished refreshing? |
| `ApplicationStartedEvent` | Has Boot moved past refresh to enter runners? |
| `LivenessState.CORRECT` | Does Boot internally consider the instance live? |
| `ApplicationReadyEvent` | Have the startup runners for this run finished? |
| `ReadinessState.ACCEPTING_TRAFFIC` | Is Boot signaling that traffic can be routed to the instance? |

When running in Kubernetes, if Spring Boot Actuator and probes are enabled, liveness/readiness can be exposed through health groups. However, you still need to configure readiness to match your application's actual requirements. Do not treat liveness as a default "DB check"; coupling external dependencies into liveness carelessly can trigger cascading restarts.

## 8. Synchronous Listeners, Blocking, and Event Ordering

By default, Spring publishes application events through a synchronous listener mechanism; in most standard cases, listeners execute on the publishing thread. If a listener performs slow network I/O or a long `Thread.sleep`, it can **prolong startup**, or even delay when the application becomes ready.

Therefore:

- Listeners for `ApplicationStartingEvent`/`ApplicationEnvironmentPreparedEvent` should be very brief and should not depend on the bean container or external systems without timeouts.
- An event-handling listener is an observation callback or controlled adjustment, **not** a scheduler for an infinite loop.
- Tasks required before ready: consider `ApplicationRunner`/`CommandLineRunner` with timeouts and clear failure policies.
- Continuous post-startup tasks: use dedicated lifecycle hooks and executors/consumers; do not block the thread publishing `ApplicationReadyEvent`.
- If using asynchronous listeners via multicaster configuration or `@Async`, accept that completion ordering is no longer guaranteed like synchronous listeners, and exceptions may be routed through a different channel. Do not apply async just to make logging "faster" without analyzing the consequences.

**Event publication order** does not equal completion order of every task spawned by a listener. If a callback schedules a background task, that task might not be finished when Boot emits the next event.

### Do Not Confuse with @Order

`@Order`/`Ordered` can affect execution order among listeners for the same event or the order of runners, depending on the API. It **cannot** move `ApplicationReadyEvent` before `ApplicationStartedEvent`. For listeners with important dependencies, configure explicit ordering rather than relying on class names or incidental declaration order.

## 9. Event Propagation Across Parent/Child Contexts and Duplicate Delivery

In systems with a context hierarchy, Spring Framework propagates application events from a child context to its parent context. Consequently, a listener in the parent context may see events emitted by both the child and parent contexts, creating the impression that an event was "sent twice" when it actually originated from **two different context sources**.

How to handle this:

1. Check whether the application runs multiple `SpringApplication` instances or `SpringApplicationBuilder.parent(...).child(...)`.
2. For events carrying an `ApplicationContext`, compare `event.getApplicationContext()` against the context the listener belongs to.
3. Do not simply count events by type and assume every event must appear exactly once in the entire JVM.
4. Watch out for listeners declared via both `spring.factories` and `addListeners`, or registered repeatedly across multiple contexts.

**Illustrative** example for a listener that holds a reference to its own context:

~~~java
if (event instanceof ContextRefreshedEvent refreshed
        && refreshed.getApplicationContext() == myContext) {
    System.out.println("Refreshed my own context");
}
~~~

This snippet is not standalone: it requires a `myContext` variable of the appropriate `ApplicationContext` type and importing `ContextRefreshedEvent`. When a listener is registered at a very early phase, do not expect to inject `myContext` in the constructor because the context does not exist yet.

## 10. Measuring Startup Time and Observing Failures

### Meaningful Milestone Measurement

Events can be used to measure intervals between milestones, such as after environment prepared, after refresh, and after runners. However:

- `System.currentTimeMillis()` is affected by system clock changes; use `System.nanoTime()` or proper startup/observation tooling to measure durations.
- Part of startup happens **before** bean listeners exist. To measure accurately from the beginning, register listeners before `run`.
- `ApplicationStartedEvent` marks the end of refresh; time until `ApplicationReadyEvent` can grow significantly due to heavy runners or listeners.
- Logging event timestamps only observes a single callback and **does not** fully replace tools like `ApplicationStartup`, Java Flight Recorder, or the Actuator startup endpoint when analyzing internal steps.

### Diagnosing the Right Scope

| Symptom | Check milestone and failure source |
| --- | --- |
| Did not receive `STARTING` | Was the listener actually registered before `run`? Did the right `main` execute? |
| Saw `STARTING` but no `ENVIRONMENT_PREPARED` | Very early error or interruption; check bootstrap logs and exceptions |
| Saw `ENVIRONMENT_PREPARED` but no `PREPARED` | Check context creation, initializers, config/bean definition loading |
| Saw `PREPARED` but no `CONTEXT_REFRESHED` | Check bean creation, auto-configuration, embedded server startup |
| Saw `STARTED` but no `READY` | Check startup runners and any errors/timeouts in between |
| Saw `READY` but no readiness accepting | Check listener/availability publishing and logs; do not infer everything from a single log line |
| Saw `FAILED` | Inspect the cause in the exception chain; do not assume a controller caused it |
| Saw web server event but traffic is rejected | Check readiness, network, service routing, security, and application state |

If your listener throws an exception, it can **fail startup** or mask the root cause. In diagnostic listeners, limit I/O, handle logging errors properly, and avoid letting instrumentation make the system less stable.

## 11. Common Misconceptions

**1. "ApplicationStartingEvent has an Environment."**

No. Spring Boot emits the starting event before the application environment is prepared; use the environment prepared event if you need access to `ConfigurableEnvironment`.

**2. "ApplicationContextInitializedEvent means beans have been initialized."**

Here "initialized" refers to **ApplicationContext having been prepared and initializers having run**, before application bean definitions are loaded. Do not assume all beans can be injected yet.

**3. "ApplicationPreparedEvent means context refresh is finished."**

Prepared happens before refresh. `ContextRefreshedEvent` is the post-refresh container milestone, while started and ready are subsequent Spring Boot milestones.

**4. "ApplicationStartedEvent and ApplicationReadyEvent are the same."**

Started comes before runners; ready comes after runners. This distinction is critical for migrations or initializations that must complete before serving traffic.

**5. "Liveness correct means readiness accepting."**

No. Liveness and readiness answer two different operational questions. An application can be live while temporarily not accepting traffic.

**6. "ApplicationFailedEvent runs after every HTTP 500."**

No. This event is tied to **`SpringApplication` startup failures**; request error handling belongs to the Servlet/WebFlux handler pipeline.

**7. "Registering @EventListener is enough to see every event from the start."**

Bean listeners only exist after the container processes beans. To track early events, use `SpringApplication.addListeners` before `run` or `spring.factories`.

**8. "WebServerInitializedEvent means the server is ready for production traffic."**

This event indicates the server has been initialized; startup readiness still waits for runners and the `ACCEPTING_TRAFFIC` milestone.

**9. "A listener always runs asynchronously."**

By default, many listeners run synchronously. Long-running work in a listener can delay startup or impact the publishing thread. Async must be configured and designed intentionally.

**10. "An event type is always emitted only once across the entire JVM."**

Multiple contexts, multiple `run` calls, or event bubbling in a context hierarchy can cause a listener to see multiple events of the same type. Check the context source.

**11. "The ready event guarantees external dependencies will never fail."**

Ready marks a successful startup milestone. A DB, network, or cache can change state later; probes and retry/circuit-breaker policies must handle runtime failures.

**12. "You can start creating beans with getBean() in any listener."**

In early events, the context does not exist yet or has not been refreshed; accessing beans can fail or break lifecycle ordering. Only use the container at milestones where the API guarantees it is appropriate.

## 12. Practice Exercises

1. Run the project in Section 6. Write down the full order of `STARTING`, `ENVIRONMENT_PREPARED`, `CONTEXT_INITIALIZED`, `PREPARED`, `CONTEXT_REFRESHED`, `STARTED`, and `READY`. Place the two availability states in their exact positions.
2. Remove the line `application.addListeners(new TimelineListener())`. Explain why you no longer see the program's listener logs and why this **does not** mean Spring Boot stopped emitting events.
3. Register `TimelineListener` using `META-INF/spring.factories` instead of calling `addListeners`. Verify that early events are still recorded.
4. Create a `@EventListener(ApplicationReadyEvent.class)` bean. Why does this bean receive the ready event but cannot expect to receive the starting event?
5. Try `--fail-demo`. Identify the last milestone on the successful startup path that was reached, which events did not appear, and why `run` threw an exception.
6. Add a `CommandLineRunner` with logging and `@Order` to observe runner ordering. Explain why Boot's started and ready milestones sit on either side of the runners.
7. Switch the project to the Servlet web starter; add a listener for `ServletWebServerInitializedEvent` and print the actual port. Why does this event not replace readiness?
8. Predict what happens if a listener for `ApplicationEnvironmentPreparedEvent` tries to call a Spring bean: is the bean container ready at that moment?
9. With Spring Actuator, configure and inspect liveness/readiness probes. Explain why a run is already live while runners are still preparing business state.
10. Suppose an initializer throws an exception before the context is created. How should an `ApplicationFailedEvent` listener be written so it does not dereference a null context?
11. Suppose an application creates parent/child contexts. Design a way to count `ContextRefreshedEvent` without confusing child context events with parent context events.
12. A team wants to record metrics for time-to-refresh and time-to-ready. How would you choose an early listener, monotonic timestamps, or `ApplicationStartup` so the measurements are meaningful?

## Key Takeaways

- Main axis: **Starting → EnvironmentPrepared → ContextInitialized → Prepared → [refresh/context/web] → Started → Liveness CORRECT → runners → Ready → Readiness ACCEPTING_TRAFFIC**.
- `ApplicationFailedEvent` is the **startup failure branch** at some stage, not a step on the success path.
- `Environment` is available from environment-prepared; `ApplicationContext` is available from context-initialized, while bean definitions and refreshed state arrive later.
- `ContextRefreshedEvent`, `ApplicationStartedEvent`, and `ApplicationReadyEvent` are **three distinct milestones**.
- Listeners that need the earliest events must be registered before `run` or via `spring.factories`; bean listeners are only suitable for events emitted once the context is ready.
- `LivenessState.CORRECT` and `ReadinessState.ACCEPTING_TRAFFIC` convey two different meanings; a server binding a port does not prove an instance is ready.
- Listeners should be lightweight, mindful of synchronicity and lifecycle, and avoid disrupting startup just for a logging step.

### References

- Spring Boot 3.3.13 — SpringApplication, Application Events and Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — ApplicationStartingEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartingEvent.html
- Spring Boot 3.3.13 — ApplicationEnvironmentPreparedEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html
- Spring Boot 3.3.13 — ApplicationContextInitializedEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html
- Spring Boot 3.3.13 — ApplicationPreparedEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html
- Spring Boot 3.3.13 — AvailabilityChangeEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Boot 3.3.13 — Application Availability and Readiness: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability
