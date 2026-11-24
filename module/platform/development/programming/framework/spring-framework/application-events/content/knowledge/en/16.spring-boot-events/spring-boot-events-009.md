# Events Before ApplicationContext Exists in Spring Boot

Spring Boot publishes several **application events right from the bootstrap phase**, even before creating the `ApplicationContext`. The two most important events to recognize are `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`. They enable an application or library to intervene very early in the startup lifecycle, such as recording bootstrap progress or adding environment configuration before the context is created.

Important point: **listeners declared with `@Component`, `@Bean`, or an `@EventListener` method are managed by Spring only after context creation takes place**. They are not the right mechanism for receiving events already published before the context exists. To receive early events, register the listener with `SpringApplication` before calling `run()`, or have Spring Boot load the listener via `META-INF/spring.factories`.

This article explains the order of startup milestones, which data is usable at each milestone, how to implement early listeners in Java 17+, how to test properly with JUnit 5, and common lifecycle mistakes.

## 1. What Does "Before ApplicationContext Exists" Exactly Mean?

`SpringApplication.run(...)` does not immediately return an initialized context. It performs multiple steps in sequence: preparing listeners and initializers, publishing the starting event, creating and preparing the `Environment`, creating the context, loading bean definitions, refreshing the context, and then running `ApplicationRunner`/`CommandLineRunner`.

During the initial steps, Spring Boot already has a **mechanism for publishing startup events**, yet it does not yet have a complete **container managing beans**:

~~~text
SpringApplication.run()
   |
   +-- Register listeners and initializers with SpringApplication
   |
   +-- ApplicationStartingEvent                 [no Environment yet; no Context yet]
   |
   +-- Prepare Environment
   +-- ApplicationEnvironmentPreparedEvent      [Environment available; no Context yet]
   |
   +-- Create ApplicationContext
   +-- Invoke ApplicationContextInitializers
   +-- ApplicationContextInitializedEvent       [Context available; bean definitions not yet loaded]
   |
   +-- Load bean definitions
   +-- ApplicationPreparedEvent                 [Context available; not yet refreshed]
   |
   +-- Refresh ApplicationContext
   +-- ApplicationStartedEvent                  [refresh complete; before runners]
   |
   +-- Run ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent                    [past runners; ready to serve]
   |
   +-- ApplicationFailedEvent if startup fails at an appropriate point
~~~

This is a conceptual diagram for the normal startup sequence. Other events such as `ContextRefreshedEvent`, `WebServerInitializedEvent`, and `AvailabilityChangeEvent` appear at their respective stages; they do not change the **before-context-exists** boundary examined here.

| Event | Publication Milestone | `Environment` Available? | `ApplicationContext` Available? | Appropriate Purpose |
| --- | --- | --- | --- | --- |
| `ApplicationStartingEvent` | Very early, after listeners/initializers are registered | **No** | **No** | Record start point, prepare very lightweight DI-independent work |
| `ApplicationEnvironmentPreparedEvent` | Once Environment is prepared, before creating context | **Yes** | **No** | Read or add property sources, validate bootstrap configuration |
| `ApplicationContextInitializedEvent` | Context created and initializers have run | Yes | **Yes, no bean definitions yet** | Observe context initialization without assuming beans are ready |
| `ApplicationPreparedEvent` | Bean definitions loaded, before refresh | Yes | **Yes, not yet refreshed** | Observe the preparation stage |
| `ApplicationStartedEvent` | After refresh, before runners | Yes | **Yes, refreshed** | Work after context starts but before runners |
| `ApplicationReadyEvent` | After runners | Yes | **Yes** | Tasks that should only run once startup has reached ready |

**Do not lump `ApplicationContextInitializedEvent` together with the first two events.** When `ApplicationContextInitializedEvent` is published, the context object **already exists**, though it has not yet been refreshed and bean definitions have not yet been loaded at that milestone. The phrase "events before context exists" is temporally accurate only for `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`.

## 2. Why Don't @Component, @Bean, and @EventListener Receive the Two Early Events?

A familiar Spring Framework listener:

~~~java
@Component
class StartingBeanListener {
    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        System.out.println("started");
    }
}
~~~

This is merely an **excerpt** illustrating what not to do when needing to receive `ApplicationStartingEvent`: this method is only discovered after bean construction and annotation processing occur, whereas the first startup event was already published earlier. That does not mean the method is syntactically invalid, but rather **it is registered too late for this specific event**.

Similarly, defining an `@Bean ApplicationListener<ApplicationEnvironmentPreparedEvent>` does not make Spring Boot "replay" the environment event that already occurred. Startup events are not a replay queue storing history for beans created later to catch up on.

The proper mechanism is **registering before `SpringApplication.run()`** in one of three ways:

1. `SpringApplication.addListeners(...)` when explicitly constructing the application in `main`.
2. `SpringApplicationBuilder.listeners(...)` when initializing via the builder.
3. `META-INF/spring.factories` with key `org.springframework.context.ApplicationListener` so Boot loads the listener very early, even when a library does not control `main`.

An early listener should be an independent, self-instantiable Java class, usually **not relying on autowiring**. It can read the event and APIs genuinely available at that moment, but must not assume repositories, data sources, `@ConfigurationProperties` beans, schedulers, or the context already exist.

## 3. Java 17+ Example: Receiving ApplicationStartingEvent and ApplicationEnvironmentPreparedEvent

The example is a minimal Spring Boot application with two listeners **registered before `run()`**. The first listener records the starting milestone; the second adds a property to the `Environment` before the context is created. To simplify testing, both accept a `Consumer<String>` as the event sink.

### 3.1. Gradle Configuration

`settings.gradle`:

~~~groovy
rootProject.name = 'early-boot-events'
~~~

`build.gradle` (Java 17, Spring Boot 3.5.x):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

If you already have a Spring Boot project managed by an organization BOM/plugin, use the version aligned with that project instead of injecting an independent Spring Framework version. The example runs on the Spring Boot 3.5 branch supporting Java 17+.

### 3.2. File src/main/java/example/boot/EarlyEventsApplication.java

~~~java
package example.boot;

import java.util.Map;
import java.util.function.Consumer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class EarlyEventsApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
            EarlyEventsApplication.class
        );
        app.addListeners(
            new StartingListener(System.out::println),
            new EnvironmentListener(System.out::println)
        );
        app.run(args);
    }

    public static final class StartingListener
            implements ApplicationListener<ApplicationStartingEvent> {

        private final Consumer<String> sink;

        public StartingListener(Consumer<String> sink) {
            this.sink = sink;
        }

        @Override
        public void onApplicationEvent(ApplicationStartingEvent event) {
            sink.accept("starting");
        }
    }

    public static final class EnvironmentListener
            implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

        private final Consumer<String> sink;

        public EnvironmentListener(Consumer<String> sink) {
            this.sink = sink;
        }

        @Override
        public void onApplicationEvent(
                ApplicationEnvironmentPreparedEvent event) {
            event.getEnvironment()
                .getPropertySources()
                .addFirst(new MapPropertySource(
                    "early-demo",
                    Map.of("demo.phase", "bootstrap")
                ));

            sink.accept("environment-prepared");
        }
    }
}
~~~

**What to observe:**

- `StartingListener` uses `ApplicationStartingEvent`. At that milestone, `event.getEnvironment()` cannot be called because this event does not provide that API; even less can beans be fetched from an uncreated context.
- `EnvironmentListener` can call `event.getEnvironment()` because the environment event provides `ConfigurableEnvironment`, even though `ApplicationContext` does not exist yet.
- `MapPropertySource` is added via `addFirst`, so `demo.phase=bootstrap` has higher priority than many other sources. This illustrates bootstrap configuration; do not use `addFirst` arbitrarily to override security or user configuration.
- Both listeners are **objects instantiated in `main`**, without `@Component`. Spring Boot knows about them before the context exists.

In a project with a Gradle wrapper, run the application with:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell use `./gradlew.bat bootRun`. In stdout you can see the two lines printed by the listeners in order:

~~~text
starting
environment-prepared
~~~

Spring Boot may also print startup logs, a banner, and other framework messages. The two lines above are **the output produced by the two listeners**, not a guarantee that the entire stdout consists of only two lines.

## 4. Testing Early Events with a Real SpringApplication

For events prior to context creation, do not use a test that only calls listener methods manually to conclude Boot registered the listener early enough. Nor should you assume a `@SpringBootTest` bean automatically captures `ApplicationStartingEvent`: that bean only appears at a later stage.

Create a real `SpringApplication`, add the listeners to the application before `run()`, and assert that the events arrive in order and the property was attached to the context afterward.

File `src/test/java/example/boot/EarlyEventsApplicationTest.java`:

~~~java
package example.boot;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

class EarlyEventsApplicationTest {

    @Test
    void earlyListenersRunBeforeApplicationContextIsReady() {
        List<String> observed = new ArrayList<>();

        SpringApplication app = new SpringApplication(
            EarlyEventsApplication.class
        );
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.addListeners(
            new EarlyEventsApplication.StartingListener(observed::add),
            new EarlyEventsApplication.EnvironmentListener(observed::add)
        );

        try (ConfigurableApplicationContext context = app.run()) {
            assertEquals(
                List.of("starting", "environment-prepared"),
                observed
            );
            assertEquals(
                "bootstrap",
                context.getEnvironment().getProperty("demo.phase")
            );
        }
    }
}
~~~

Run the test:

~~~bash
./gradlew test --tests "example.boot.EarlyEventsApplicationTest"
~~~

From Windows PowerShell use `./gradlew.bat test --tests "example.boot.EarlyEventsApplicationTest"`.

**Why is this test reliable?**

1. `SpringApplication` receives the listeners **before** starting; the test does not manually invoke the two `onApplicationEvent` methods.
2. Spring Boot runs the real lifecycle. If a listener was not registered in time, the `observed` list misses elements and the assertion fails.
3. The `demo.phase` result is verified **after `run()` returns the context**, proving the environment listener modified the exact `Environment` object used in the context.
4. `WebApplicationType.NONE` avoids starting a web server, keeping the test focused on startup events. `try-with-resources` closes the context after assertions.

The test does not need repositories or services; testing the two early events requires only Boot's lifecycle and `Environment`. If you want to test startup failure or capture events in a library module, write separate tests for `ApplicationFailedEvent` or the corresponding automatic registration mechanism.

## 5. Automatic Listener Registration via META-INF/spring.factories

When building a starter or integration library without controlling `main`, the way to attach a listener at an early stage is the file:

`src/main/resources/META-INF/spring.factories`

~~~properties
org.springframework.context.ApplicationListener=example.boot.StartupTraceListener
~~~

The listener class must be instantiable by Spring Boot **before the context exists**. Standalone example (file `src/main/java/example/boot/StartupTraceListener.java`):

~~~java
package example.boot;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class StartupTraceListener
        implements ApplicationListener<ApplicationStartingEvent> {

    public StartupTraceListener() {
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("starter: beginning startup");
    }
}
~~~

When this class and `spring.factories` are on the runtime classpath, Boot can load the listener via factory discovery right at the beginning of startup. Modifying `main` is not required. If you have registered **the same listener** via both `addListeners` and `spring.factories`, check to avoid duplicate effects; each registration can instantiate a separate instance.

**Note:** the `spring.factories` syntax here is specifically for registering `ApplicationListener`. Do not confuse it with the auto-configuration registration mechanism in newer Spring Boot versions (`AutoConfiguration.imports`), as the two extension points serve different purposes.

### SpringApplicationBuilder

If the application already uses `SpringApplicationBuilder`, you can register early via the `listeners(...)` method before `run(...)`:

~~~java
new SpringApplicationBuilder(EarlyEventsApplication.class)
    .listeners(new EarlyEventsApplication.StartingListener(
        System.out::println
    ))
    .run(args);
~~~

This is an **excerpt**, requiring importing `org.springframework.boot.builder.SpringApplicationBuilder` and having `args` from `main`. Choose one registration approach matching the application's startup mechanism; avoid adding a listener twice just to be sure of receiving the event.

## 6. What Can and Cannot Be Done at the Two Early Milestones

| Action | `ApplicationStartingEvent` | `ApplicationEnvironmentPreparedEvent` |
| --- | --- | --- |
| Record startup milestone with standalone Java code | Yes | Yes |
| Use command-line `getArgs()` values from startup event, when appropriate | Yes | Yes |
| Read or adjust `ConfigurableEnvironment` | Not yet | Yes |
| Retrieve beans via `ApplicationContext.getBean(...)` | No | No |
| Call `@Autowired` injected services/repositories | No | No |
| Adjust property sources before creating context | No Environment yet | Yes |
| Wait until web server is ready | No | No |
| Run migrations depending on database beans | Unsuitable | Unsuitable |

If the goal is merely "do work once the application is running," use `ApplicationRunner`, `CommandLineRunner`, `ApplicationStartedEvent`, or `ApplicationReadyEvent` as needed. Do not attach long tasks, heavy I/O, or infinite retries to very early listeners: by default startup listeners run synchronously, causing the entire startup to block or fail if the listener throws an exception.

For example, for requirements that load external property sources into `Environment` very early, consider the **Config Data API** or `EnvironmentPostProcessor` provided by Boot if that is the proper extension point for configuration management. `ApplicationEnvironmentPreparedEvent` can add a property source, yet it is not always the right place to build a large configuration system.

### Do Not Confuse Pre-Context Events with Pre-Refresh Events

`ApplicationContextInitializedEvent` is published when the context object already exists, after `ApplicationContextInitializer` runs, but before bean definitions are loaded. `ApplicationPreparedEvent` is even later: bean definitions have been loaded, yet refresh has not started. **Having a context does not mean all beans are ready**.

In particular, when `ApplicationFailedEvent` occurs, the failure stage determines whether the context already exists. When handling startup failures, never assume `getApplicationContext()` is always non-null; the listener must check for null while also avoiding accessing beans from the failed context.

## 7. Common Mistakes and Fixes

**Mistake 1 – Putting `@EventListener(ApplicationStartingEvent.class)` on a bean and waiting for it to receive the early event.** The bean is created too late. Register `ApplicationListener<ApplicationStartingEvent>` with `SpringApplication` before `run()`, or declare it in `spring.factories`.

**Mistake 2 – Assuming `ApplicationEnvironmentPreparedEvent` already has a context.** It only guarantees `Environment` is prepared; the context will be created in a later step. Do not call `getBean()` or use autowired services at this milestone.

**Mistake 3 – Waiting for `ApplicationReadyEvent` to change properties needed during bean creation.** By ready time, configuration has already been used to build many beans; changing property sources will not cause all beans to reconfigure themselves. Pick an extension point before context creation.

**Mistake 4 – Confusing `ApplicationStartedEvent` with `ApplicationStartingEvent`.** `ApplicationStartingEvent` happens very early; `ApplicationStartedEvent` happens **after refresh** but before runners. The two names look similar, yet their lifecycles and available data differ greatly.

**Mistake 5 – Failing to distinguish startup listener registration from bean listener registration.** A listener passed to `addListeners` is an object supplied to `SpringApplication`; Spring does not need to instantiate it as a bean. If it depends on DI, the early registration mechanism cannot satisfy that assumption.

**Mistake 6 – Running slow or failing logic in an early listener.** Listeners typically run on the startup thread; unhandled exceptions can halt the application. Perform only lightweight, fast work with clear bootstrap intent; log and handle errors proactively where appropriate.

**Mistake 7 – Writing tests that only call `onApplicationEvent`.** Such tests prove the handler method works, not that Boot's lifecycle dispatched the event. To verify early registration, run a real `SpringApplication` in the test.

**Mistake 8 – Relying on event counts in a multi-context hierarchy.** Applications with parent/child contexts can receive certain application events multiple times due to event propagation to ancestors. When using a hierarchy, filter by source context and design listeners to be idempotent; do not extrapolate from single-context examples to every topology.

## 8. Checklist and Self-Check Questions

- Identify precisely whether intervention is needed **before context creation**, or merely before refresh/runners.
- For `ApplicationStartingEvent`, do not expect `Environment` or `ApplicationContext`.
- For `ApplicationEnvironmentPreparedEvent`, use `event.getEnvironment()`, do not call beans.
- Register via `addListeners`/`SpringApplicationBuilder.listeners` or `spring.factories` before starting.
- Write the listener independent of DI and keep handling fast without blocking startup unnecessarily.
- Test properly with `SpringApplication.run()`, verifying order and an observable effect.
- If the goal is large-scale configuration modification, consider `EnvironmentPostProcessor`/Config Data instead of an ad-hoc listener.

**Question 1:** Why can't a `@Component` listener receive `ApplicationStartingEvent` from that startup run?

Because the container has not created beans when the event is published; Spring does not store and replay early events for beans created later.

**Question 2:** Which two events occur before `ApplicationContext` exists?

`ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`. `ApplicationContextInitializedEvent` occurs after the context has been created.

**Question 3:** When can you read or add a property source before the context is created?

Upon receiving `ApplicationEnvironmentPreparedEvent`, call `event.getEnvironment().getPropertySources()` and act as needed.

**Question 4:** Does a listener written in `spring.factories` need a no-arg constructor?

A listener instantiated by Boot during bootstrap must have a suitable way to be constructed without relying on bean injection; a public no-arg constructor is a transparent, simple choice for this example.

**Question 5:** When should you use `ApplicationRunner` instead of an early listener?

When a task needs beans, finalized configuration, or a refreshed context; if the task must run before ready is announced, a runner is an appropriate extension point.

**Takeaway:** `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent` are events of **SpringApplication bootstrap**, published before `ApplicationContext` exists. Register listeners **before calling `run()`** and use only components already available at each milestone. This boundary is what separates early startup events from application events handled by beans inside an already-built context.

## References

- [Spring Boot Reference – SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot API – org.springframework.boot.context.event](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/package-summary.html)
- [Spring Boot API – SpringApplication](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot API – ApplicationEnvironmentPreparedEvent](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html)
