# Registering Listeners via `SpringApplicationBuilder` or `spring.factories`

In Spring Boot, an **`ApplicationListener`** can react to startup lifecycle events: when the application just starts, when `Environment` is prepared, when `ApplicationContext` is created, after context refresh, after runners complete, or when startup fails.

The crucial detail is **when the listener is registered**. Some of the earliest events are published **before Spring creates the `ApplicationContext` and application beans**. Therefore, a listener discovered only through `@Component` or `@Bean` inside the context cannot reliably observe those very early events. When registration must happen before `run()` begins, Spring Boot provides two suitable mechanisms:

1. **`SpringApplicationBuilder.listeners(...)`:** registers listeners in Java code for the run being configured.
2. **`META-INF/spring.factories`:** declares the listener class name so Spring Boot loads it automatically from the classpath, even when the application entrypoint does not call `listeners(...)`.

This lesson uses Spring Boot **3.3.x**, Spring Framework 6.1, and **Java 17+**. The examples can be used in a Spring Boot Gradle project while clearly distinguishing very early listeners from bean-created listeners.

## 1. What Is a Listener in Spring Boot?

`ApplicationListener<E>` is a Spring Framework interface:

~~~java
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {
    void onApplicationEvent(E event);
}
~~~

This is an **abbreviated signature to explain the API**, not the full interface source. For a practical example, we implement a concrete event:

~~~java
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyNoticeListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Listener: SpringApplication has started");
    }
}
~~~

The snippet above is **a complete Java class when placed in a project with Spring Boot on the classpath**. It runs only when an appropriate `SpringApplication` or context actually registers the listener and publishes `ApplicationStartingEvent`. Having the class in source code does not mean the listener is active.

Spring Boot publishes `SpringApplication`-related events at these main milestones:

| Event | When does it occur? | What is available to use? |
| --- | --- | --- |
| `ApplicationStartingEvent` | Very early as soon as a `run` starts, after registering listeners/initializers | **No** `Environment` or `ApplicationContext` yet |
| `ApplicationEnvironmentPreparedEvent` | `Environment` is prepared, but context is not created yet | Can access `Environment` via the event |
| `ApplicationContextInitializedEvent` | Context is prepared and initializers have run; before loading bean definitions | Context exists, not yet refreshed |
| `ApplicationPreparedEvent` | Sources/bean definitions loaded; before refresh | Context is being prepared; do not assume all beans exist |
| `ApplicationStartedEvent` | After successful refresh, **before** `ApplicationRunner`/`CommandLineRunner` | Context has refreshed |
| `ApplicationReadyEvent` | After runners finish | Startup lifecycle has reached the ready milestone |
| `ApplicationFailedEvent` | If a startup run fails | Availability of environment/context depends on when failure occurred |

Beyond this table, there are `ContextRefreshedEvent`, `WebServerInitializedEvent`, and `AvailabilityChangeEvent`. They are not equivalent to every `SpringApplication` event in the table. An early-registered listener can continue receiving matching events once the context is active.

**Key takeaway:** `ApplicationStartingEvent` is not `ApplicationStartedEvent`. The first occurs at the very beginning; the second occurs after the context has refreshed.

## 2. Why Register Listeners Before Beans Are Created?

If you only write:

~~~java
@Component
public class StartupLogger
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Application starting");
    }
}
~~~

then that class only becomes a listener through the context's bean registration mechanism. Yet when `ApplicationStartingEvent` is published, the context and the `StartupLogger` bean **have not been created yet**. Thus, bean-style registration **misses the very first event during normal startup**.

Similarly, placing `@EventListener` on a bean method does not make it a listener registered before the context is formed.

To observe early events, Spring Boot needs to know about a listener instance **before or right when `run()` begins**. Specifically:

- **`SpringApplication.addListeners(...)`:** instantiate `SpringApplication`, register listeners before calling `run`.
- **`SpringApplicationBuilder.listeners(...)`:** use the fluent builder to add listeners before `run`.
- **`META-INF/spring.factories`:** list the implementation class name in a resource that Spring Boot's factories loader discovers on the classpath.

All three serve the same early-registration need, while differing in configuration scope and reusability.

## 3. Option A — Registering with `SpringApplicationBuilder.listeners(...)`

`SpringApplicationBuilder` provides a fluent API to configure `SpringApplication` and, if needed, build parent/child context hierarchies. The method:

~~~java
SpringApplicationBuilder listeners(ApplicationListener<?>... listeners)
~~~

accepts one or more already-instantiated listener objects. The end of the fluent chain calls `run(args)` to launch the application.

Entrypoint example:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class BuilderExample {

    public static void main(String[] args) {
        new SpringApplicationBuilder(BuilderExample.class)
                .listeners(new MyEarlyListener())
                .run(args);
    }

    public static final class MyEarlyListener
            implements ApplicationListener<ApplicationStartingEvent> {

        @Override
        public void onApplicationEvent(ApplicationStartingEvent event) {
            System.out.println("BUILDER: starting");
        }
    }
}
~~~

This is an **illustration of the builder mechanism**; to serve as a complete Spring Boot application, it needs primary bean sources, dependencies, and an appropriate entrypoint like the hands-on example in Section 7. In real code, the builder must include the primary configuration class and listeners created **before `run`**.

### What Happens?

~~~text
main()
  |
  v
new SpringApplicationBuilder(MainConfig.class)
  |
  v
.listeners(new MyEarlyListener())
  |   Stores the listener for the SpringApplication being built
  v
.run(args)
  |   Spring Boot starts the startup cycle
  |   Publishes ApplicationStartingEvent
  +--> MyEarlyListener.onApplicationEvent(...)
  |
  v
Prepare Environment -> Create/refresh Context -> Started -> Runners -> Ready
~~~

Point to emphasize: the builder is not a separate event bus. It is a way to **configure `SpringApplication`**, after which Spring Boot uses the framework's event publishing mechanism.

### When Should You Use the Builder?

Choose the builder when:

- You **control the `main` entrypoint** and want clarity on which listeners are attached for this run.
- You already use the fluent API to set `profiles(...)`, `properties(...)`, `bannerMode(...)`, `web(...)`, or hierarchies.
- You need different listener setups per test environment or per entrypoint.
- You do not want a library to auto-register a listener into every application just by being on the classpath.

Builder example registering multiple listeners:

~~~java
new SpringApplicationBuilder(MyApplication.class)
        .listeners(
                new StartingListener(),
                new EnvironmentListener())
        .run(args);
~~~

The two classes `StartingListener` and `EnvironmentListener` above are **illustrative names** that must be defined with `ApplicationListener` and matching event types in your project. You do not have to switch to the builder solely to register listeners: `SpringApplication.addListeners(...)` does that as well.

### Comparison with `SpringApplication.addListeners(...)`

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.addListeners(new StartingListener());
application.run(args);
~~~

The option above has the same meaning when launching a single application. Both approaches require calling **before `run`**. Attempting to add a listener after `ApplicationStartingEvent` has been published **does not replay past events**.

**Note:** `SpringApplicationBuilder.listeners(...)` takes **listener instances**, not `String` class names. This lets you construct listeners yourself, pass custom configuration parameters, and control registration scope.

## 4. Option B — Auto-Registering via `META-INF/spring.factories`

In Spring Boot 3.3, a library or application can place the file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

with content:

~~~properties
org.springframework.context.ApplicationListener=com.example.runtime.EarlyStartupListener
~~~

Here:

- **Key** is the fully qualified name of the `org.springframework.context.ApplicationListener` interface.
- **Value** is the fully qualified name of the implementation class, including its package.
- Spring Boot scans `META-INF/spring.factories` files on the **classpath** and loads listeners declared under the appropriate key.
- The listener can be loaded even if `main` only calls `SpringApplication.run(MyApplication.class, args)` and **never calls `addListeners` or `builder.listeners`**.

A `spring.factories` file can declare multiple listeners separated by commas:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.runtime.FirstListener,\
com.example.runtime.SecondListener
~~~

The trailing `\` denotes **line continuation** in Java `.properties` format. You can also write the entire list on one line to avoid syntax mistakes.

### Distinguishing from a Spring Bean

A listener class declared in `spring.factories` is instantiated by the bootstrap mechanism **independently of `ApplicationContext` beans**. Therefore, a safe example is a `public` class with a no-arg constructor that does not require Spring constructor injection:

~~~java
package com.example.runtime;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyStartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    public EarlyStartupListener() {
        // Constructor does not require a Spring bean.
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("FACTORIES listener invoked");
    }
}
~~~

When loading from `spring.factories`, Spring Boot does not wait for the container to create beans before instantiating the listener. Do not write:

~~~java
public EarlyStartupListener(MyRepository repository) {
    // There is no guarantee MyRepository exists as a bean here.
}
~~~

and expect the system to automatically `@Autowired` it like a regular `@Component`. For very early listeners, rely on data available from the event or configuration independent of application beans. An unsuitable constructor can cause listener loading to fail and prevent the application from starting.

### Shared Libraries

This is where `spring.factories` is especially useful. If a library JAR contains:

~~~text
META-INF/spring.factories
com/example/runtime/EarlyStartupListener.class
~~~

and that JAR is added to an application's runtime classpath, Spring Boot can auto-discover the listener. This feature is convenient for packaging infrastructure library listeners, but it also means they can run in **every Spring Boot application that has the library on its classpath**. Therefore, design such listeners with minimal side effects and avoid assuming a specific context type if the library targets multiple applications.

**Scope limit:** `spring.factories` does not make a listener run automatically in plain Java; a Spring Boot/Spring process that actually invokes the factories loader and publishes events is required. Do not confuse "classpath auto-discovery" with "global registration across every JVM."

## 5. Spring Boot 3.x: Is `spring.factories` Still Used to Register Listeners?

**Yes.** Spring Boot 3.3 still supports declaring `ApplicationListener` in `META-INF/spring.factories`. This rule is stated in the Spring Boot 3.3 SpringApplication reference documentation.

A common misconception is: "Spring Boot 3.x moved everything from `spring.factories` to `AutoConfiguration.imports`, so registering listeners with `spring.factories` no longer works." That statement is **false when applied to `ApplicationListener`**.

The two registration types differ:

| Purpose | Location/declaration in Spring Boot 3.3 |
| --- | --- |
| Registering `ApplicationListener` to load at bootstrap | `META-INF/spring.factories`, key `org.springframework.context.ApplicationListener` |
| Registering `ApplicationContextInitializer` via the same mechanism | `META-INF/spring.factories`, key for initializers |
| Listing auto-configuration classes for modern Spring Boot | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Registering beans in the context | `@Component`, `@Bean`, auto-configuration, and BeanDefinition mechanisms |

**Do not put listener names in `AutoConfiguration.imports` instead of the `ApplicationListener` key.** The auto-configuration imports file is for loading auto-configuration classes, not for catching an early `ApplicationStartingEvent`.

Likewise, `spring.main.*` properties are not a general replacement for listener registration; they primarily configure `SpringApplication` behavior.

## 6. Comparing the Two Registration Approaches

| Criterion | `SpringApplicationBuilder.listeners(...)` | `META-INF/spring.factories` |
| --- | --- | --- |
| Configuration location | Java code at the entrypoint | `.properties` resource on the classpath |
| Input | Instantiated `ApplicationListener` objects | Fully qualified listener class name |
| When discovered | Before `builder.run(args)` | During bootstrap, when Spring Boot loads listeners from classpath |
| Catches early events like `ApplicationStartingEvent` | Yes | Yes |
| Must be a Spring bean | No | No |
| Best suited when | Directly controlling one entrypoint, custom configuration | Shared libraries or listeners wanting classpath auto-registration |
| Can pass manual constructor arguments | Yes | Not via normal bean injection |
| Reusable across multiple apps | Each entrypoint must register or share a builder | Yes, if the library/file is on the classpath |
| Common pitfalls | Forgetting to call `listeners` before `run`; duplicate registration | Wrong path, key, package, constructor, or unpackaged resource |
| Per-run configurability | Explicit, flexible | Usually driven by classpath contents; per-run behavior requires internal config logic |

They are **not mutually exclusive**. An application can simultaneously have builder-registered listeners and listeners auto-loaded from `spring.factories`. However, avoid registering **the same logic multiple times** without controlling repeated effects.

## 7. Runnable Hands-On Example: Observing Both Mechanisms

We will create a Spring Boot application running **without a web server**. The demo intentionally includes two distinct listeners:

- **`BuilderStartingListener`** listens for `ApplicationStartingEvent`, registered via `SpringApplicationBuilder.listeners(...)`.
- **`FactoriesEnvironmentListener`** listens for `ApplicationEnvironmentPreparedEvent`, registered via `META-INF/spring.factories`.

Using two different event types makes the output easy to distinguish and avoids duplicate logs. An `ApplicationRunner` in the context prints one line after refresh, proving early listeners execute before bean runners.

### 7.1. Directory Structure

~~~text
early-listeners-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/earlyevents/
    │   ├── EarlyListenersDemoApplication.java
    │   ├── BuilderStartingListener.java
    │   └── FactoriesEnvironmentListener.java
    └── resources/META-INF/spring.factories
~~~

### 7.2. Gradle Configuration

File `settings.gradle`:

~~~groovy
rootProject.name = 'early-listeners-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // Spring Boot BOM supplies versions for dependencies in the Boot ecosystem.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Important QA point: because Gradle's native BOM support is used, the `spring-boot-starter` dependency resolves properly without an explicit version. If a project already uses the `io.spring.dependency-management` plugin or another aligned BOM, keep one consistent version-management mechanism rather than duplicating configuration.

Environment requirements: JDK 17 or later and a Gradle version compatible with Spring Boot 3.3. The example has no web dependency, so Tomcat does not start.

### 7.3. Entrypoint Using `SpringApplicationBuilder`

File `src/main/java/com/example/earlyevents/EarlyListenersDemoApplication.java`:

~~~java
package com.example.earlyevents;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EarlyListenersDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(
                        EarlyListenersDemoApplication.class)
                    .web(WebApplicationType.NONE)
                    .bannerMode(Banner.Mode.OFF)
                    .listeners(new BuilderStartingListener())
                    .run(args)) {
            System.out.println("MAIN contextActive=" + context.isActive());
        }
    }

    @Bean
    ApplicationRunner showRunner() {
        return args -> System.out.println("RUNNER");
    }
}
~~~

Explanation:

1. The builder accepts the main configuration class annotated with `@SpringBootApplication`.
2. `web(WebApplicationType.NONE)` selects a console application with no HTTP server.
3. `bannerMode(Banner.Mode.OFF)` hides the banner; it does not affect listeners.
4. `listeners(new BuilderStartingListener())` registers the instance before `run(args)` begins.
5. `run(args)` returns `ConfigurableApplicationContext` if startup succeeds.
6. `ApplicationRunner` is a context bean, so it runs only after the refresh phase finishes.
7. `try-with-resources` closes the context when exiting the block.

### 7.4. Listener Registered via Builder

File `src/main/java/com/example/earlyevents/BuilderStartingListener.java`:

~~~java
package com.example.earlyevents;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class BuilderStartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("BUILDER ApplicationStartingEvent");
    }
}
~~~

This class has no `@Component` and does not need to be created as a bean. The builder receives an instance created with `new` and puts it into the listener list before Spring Boot publishes the early event.

At the `ApplicationStartingEvent` milestone, **do not use `@Autowired` or try to retrieve `ApplicationContext`**: the context does not exist yet.

### 7.5. Listener Auto-Loaded from `spring.factories`

File `src/main/java/com/example/earlyevents/FactoriesEnvironmentListener.java`:

~~~java
package com.example.earlyevents;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public final class FactoriesEnvironmentListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    public FactoriesEnvironmentListener() {
        // No bean injection needed: the listener is created very early.
    }

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {
        String tag = event.getEnvironment()
                .getProperty("demo.tag", "unset");
        System.out.println(
                "FACTORIES ApplicationEnvironmentPreparedEvent demo.tag=" + tag);
    }
}
~~~

File `src/main/resources/META-INF/spring.factories`:

~~~properties
org.springframework.context.ApplicationListener=com.example.earlyevents.FactoriesEnvironmentListener
~~~

**Package and class names must match exactly.** The resource file must reside under `src/main/resources/META-INF/`, not in `src/main/java/`, and must not be confused with `application.properties`. Gradle packages this resource onto the application's runtime classpath according to standard Java build rules.

`demo.tag` is read from the event's `Environment`. We will pass it as an application argument so it is already present during environment preparation. `ApplicationEnvironmentPreparedEvent` is published before the context exists, so using `event.getEnvironment()` is more appropriate than trying to obtain an `Environment` bean injected by the container.

### 7.6. Running and Checking the Output

In a project directory with a compatible Gradle Wrapper:

~~~bash
./gradlew bootRun --args="--demo.tag=hello"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--demo.tag=hello"
~~~

If there is no wrapper yet and a compatible Gradle is installed:

~~~bash
gradle bootRun --args="--demo.tag=hello"
~~~

In a successful run, **the lines printed by the example's own code** appear in this order:

~~~text
BUILDER ApplicationStartingEvent
FACTORIES ApplicationEnvironmentPreparedEvent demo.tag=hello
RUNNER
MAIN contextActive=true
~~~

This is the subset of `System.out.println` lines from the demo, **not the entire stdout**. Spring Boot's logger and Gradle messages may print additional lines depending on configuration. What matters is the relative order of the four lines above:

- **BUILDER** appears first because `ApplicationStartingEvent` is a very early event.
- **FACTORIES** appears after `Environment` is prepared, proving the listener was loaded from the resource and could read the `--demo.tag=hello` argument.
- **RUNNER** appears after refresh because it is an `ApplicationRunner` bean.
- **MAIN** appears after `run(args)` returns an active context.

If run without `--demo.tag=hello`, the FACTORIES line may print `demo.tag=unset` when no other configuration source provides `demo.tag`. The rest of the sequence keeps the same meaning.

### 7.7. Three Experiments to Verify Independence

**Experiment A — Without registering the builder listener:** remove only `.listeners(new BuilderStartingListener())` in the entrypoint and run again. The **BUILDER** line disappears, while **FACTORIES** still appears because `spring.factories` remains on the classpath.

**Experiment B — Without registering via `spring.factories`:** restore the builder listener, then temporarily remove the `org.springframework.context.ApplicationListener=...` declaration from the resource. The **FACTORIES** line no longer appears, while **BUILDER** remains. You must rebuild/rerun with the updated resource to verify.

**Experiment C — Using regular `SpringApplication.run(...)`:** replace `main` with:

~~~java
public static void main(String[] args) {
    try (org.springframework.context.ConfigurableApplicationContext context =
            org.springframework.boot.SpringApplication.run(
                    EarlyListenersDemoApplication.class, args)) {
        System.out.println("MAIN contextActive=" + context.isActive());
    }
}
~~~

This is an **alternative replacing the entire `main`, not run alongside the builder**. While `spring.factories` remains, the FACTORIES listener continues to be auto-loaded; the BUILDER listener is not registered because the new entrypoint does not call `listeners(...)`. Default logs/banners will differ, but the registration principle stays the same.

After each experiment, restore the original version if you want to continue testing both mechanisms together.

## 8. How Does Classpath Listener Loading Work?

Conceptually, a Spring Boot bootstrap follows this flow:

~~~text
Runtime classpath:
    app classes + resources + dependent JARs
        |
        v
Spring Boot / SpringFactoriesLoader
    Finds META-INF/spring.factories across classpath entries
        |
        v
Reads key org.springframework.context.ApplicationListener
    Retrieves implementation class names
        |
        v
Instantiates and registers matching listeners during bootstrap
        |
        +----------------------+
        |                      |
        v                      v
ApplicationStartingEvent    ApplicationEnvironmentPreparedEvent
        |                      |
        v                      v
Invoke matching listeners   Invoke matching listeners
        |
        v
Continue creating and refreshing ApplicationContext
~~~

This diagram explains **why no bean needs to be created** for a listener listed in `spring.factories`. It is not a model claiming Spring tries to invoke **every** listener on **every** event: generic type/event filtering still applies.

An application can depend on multiple JARs, each with its own `META-INF/spring.factories`. The factories mechanism can read all matching resources on the classpath; there is not just one file in the entire process. When packaging a library, verify the resource is preserved after build/shading; a packaging step that overwrites or strips `spring.factories` will make the listener "disappear."

### Registering a Library Listener

In a library `runtime-observer.jar`, you can provide:

~~~text
runtime-observer.jar
    ├── META-INF/spring.factories
    └── com/example/observer/StartupObserver.class
~~~

Content:

~~~properties
org.springframework.context.ApplicationListener=com.example.observer.StartupObserver
~~~

Applications using the library only need to add the JAR to their runtime classpath. **Be careful about global classpath impact**: a module depending on the library across many projects can inadvertently activate the listener in unintended applications. Design such listeners so they can be safely disabled via configuration and do not hard-depend on business beans.

For a Spring Boot fat JAR, the resource path may be packaged under `BOOT-INF/classes/META-INF/spring.factories` (for the app itself) or inside a dependency JAR under `BOOT-INF/lib`. Those are **packaging** locations, while the logical classpath path that `SpringFactoriesLoader` searches remains `META-INF/spring.factories`.

## 9. Ordering Multiple Listeners and `@Order`

If multiple listeners listen to **the same event**, consider execution order. Spring Framework supports the `Ordered` interface and `@Order` annotation to express priority:

~~~java
import org.springframework.core.Ordered;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class PriorityStartingListener
        implements ApplicationListener<ApplicationStartingEvent>, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 100;
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Priority listener");
    }
}
~~~

This is a class that compiles in a Spring Boot project; it runs only if registered through one of the mechanisms learned. **Smaller** order values generally take precedence to run earlier when the event-publishing mechanism sorts listeners.

However, do not infer the following:

- Line order in `spring.factories` **is not** a contract for coordinating business logic between listeners.
- Two listeners with the same order value do not have a stable ordering relationship you should depend on.
- `@Order` for listeners **does not replace** ordering control for `ApplicationRunner` or `SmartLifecycle`; those are separate lifecycle contracts.
- Listeners receiving different events are ordered by **when each event is published**, not solely by class order.

If listener A must prepare data for B, sometimes the right solution is to put the logic into a clearer shared component rather than relying on implicit ordering between listeners.

## 10. Which Events Can Access Which Resources?

| Event | `Environment` | `ApplicationContext` | Application beans |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | Not ready yet | Does not exist yet | Do not exist yet |
| `ApplicationEnvironmentPreparedEvent` | Available, via event | Does not exist yet | Do not exist yet |
| `ApplicationContextInitializedEvent` | Available via context/event | Created, full app definitions not loaded yet | Must not be assumed available |
| `ApplicationPreparedEvent` | Available | Context prepared, not refreshed yet | Must not be assumed initialized |
| `ApplicationStartedEvent` | Available | Refreshed | Regular non-lazy singletons created, though lazy beans may still be uncreated |
| `ApplicationReadyEvent` | Available | Refreshed and past runners | Beans may still be lazy or scoped to be created later |

This determines what a listener should do:

- **Very early:** print a marker, record context-independent details, or set up bootstrap components where supported APIs exist.
- **Environment prepared:** read/adjust `PropertySource`s according to needs and corresponding APIs; avoid accessing beans.
- **Context initialized/prepared:** use appropriate context APIs while not yet refreshed; do not arbitrarily instantiate/read beans.
- **Started/ready:** better suited for observing beans and coordinating lifecycle actions, though you should not block indefinitely in a listener.

If an `ApplicationStartingEvent` listener tries to call `event.getApplicationContext()`, that is a conceptual mistake: **this event type does not provide a context**. Similarly, `ApplicationEnvironmentPreparedEvent` lets you read `getEnvironment()` but **does not** guarantee an `ApplicationContext` object exists yet.

## 11. Choosing Bean Listeners, `@EventListener`, or Early Registration?

Three practical scenarios:

### A. Only Need to React Once the Application Has a Context

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyReporter {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("READY");
    }
}
~~~

This is an ordinary Spring bean. It is appropriate because `ApplicationReadyEvent` is published after the context is created and refreshed. There is no need to use `spring.factories` just to listen to this event.

### B. Must Observe the Very First Event

Use the builder or `spring.factories` to register `ApplicationListener<ApplicationStartingEvent>` before `run`. Do not rely on `@Component` as the sole mechanism, and do not call application beans at this point.

### C. Want Automatic Registration for Applications Using a Library

Use `META-INF/spring.factories` when you need to attach a bootstrap listener without modifying each application's entrypoint. Be especially cautious with code that runs in every application with the library on the classpath, and apply conditions/configuration to prevent unintended effects.

**Selection rule:** need early events + control entrypoint → builder; need early events + auto-load from classpath → `spring.factories`; only listen to events after the context is active → a bean listener or `@EventListener` is usually simpler.

## 12. Distinguishing `ApplicationListener` and `SpringApplicationRunListener`

These two names are easy to confuse, yet they are **not the same interface**:

| Component | Role | Typically used when |
| --- | --- | --- |
| `ApplicationListener<E>` | Receives `ApplicationEvent` from Spring event publishing | Reacting to startup events or in-context events |
| `SpringApplicationRunListener` | Specialized callback for Spring Boot to coordinate each stage of a `SpringApplication.run` | Low-level infrastructure integration into Spring Boot bootstrap |

In this lesson, the exact key is:

~~~properties
org.springframework.context.ApplicationListener=com.example.runtime.EarlyStartupListener
~~~

**Do not** replace it with:

~~~properties
org.springframework.boot.SpringApplicationRunListener=com.example.runtime.EarlyStartupListener
~~~

because `EarlyStartupListener` in our example **does not implement `SpringApplicationRunListener`**, and `SpringApplicationRunListener` has a different instantiation contract. Registering under the wrong key can prevent the listener from being found as intended or cause loading errors.

Likewise, do not confuse `SpringApplicationBuilder.listeners(...)` with `ApplicationContextInitializer`: initializers customize the context during preparation; listeners react to published events. A class could fulfill multiple roles, but their contracts remain distinct.

## 13. Attention Needed with Parent/Child Contexts

`SpringApplicationBuilder` has `parent(...)` and `child(...)` for building context hierarchies. When an event is published from a **child context**, Spring's event mechanism can propagate the event to **parent contexts**, causing listeners registered in the parent context to also receive events from child contexts.

Therefore, if a listener operates on a specific context, do not assume "each event type is received exactly once across the entire application with a context hierarchy."

When an event provides a context, you can identify the emitting context and compare it with the context the listener manages. For listeners registered at very early bootstrap, no context exists yet, so filtering logic must rely on attributes actually supplied at that milestone.

Beyond context hierarchies, accidentally declaring the same class in `spring.factories` while also instantiating another via `builder.listeners(...)` can invoke the logic multiple times. Avoid using listeners for **non-idempotent** actions such as transferring money, deleting data, or committing transactions on the assumption that "the event runs only once."

## 14. Common Mistakes and How to Check Them

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `ApplicationStartingEvent` not seen when using `@Component` | Listener bean was created after the event | Switch to `builder.listeners` or `spring.factories` |
| Using builder yet not receiving events | Forgot to register before `run`, or created a different builder to run | Check the exact builder instance and placement of `listeners(...)` |
| `spring.factories` has no effect | Wrong path, key name, class name, or resource not on classpath | Check `src/main/resources/META-INF/spring.factories`, package, and packaged JAR |
| Loading listener fails with constructor error | Factory listener demands a dependency available only in the container | Use a bootstrap-compatible constructor; remove bean dependencies |
| Listener runs twice | Same logic registered from multiple sources, or context hierarchy | Check registration paths and event context |
| `event.getEnvironment()` returns unexpected property | Different config source/precedence, or listener ran before certain source-loading steps | Check property sources available at **that exact event milestone**; prefer testing with command-line arguments |
| `ApplicationStartedEvent` listener prints nothing despite initial startup logs | Context refresh failed before started event | Inspect root cause, `ApplicationFailedEvent`, and stack trace |
| `ApplicationReadyEvent` listener does not run | Runner failed or blocked, or listener not registered | Inspect runners and event registration point |
| Listener slows down startup | Callback performs heavy I/O or synchronous waiting | Move work to a runner/appropriate service; avoid blocking early stages |
| Moving listener to `AutoConfiguration.imports` | Confusing auto-config metadata with ApplicationListener metadata | Use key `org.springframework.context.ApplicationListener` in `spring.factories` |
| `@Autowired` is null inside factory listener | Object was not created as a context bean | Do not inject app beans into early listeners; use events, bootstrap APIs, or post-refresh hooks |
| Wrong order among multiple listeners | Relying on declaration order rather than priority | Use `Ordered`/`@Order` and design order-independently when possible |

### Quick Way to Inspect Resources Inside a JAR

After building the Spring Boot JAR with:

~~~bash
./gradlew bootJar
~~~

you can inspect the JAR contents with the JDK's `jar` tool (replace the JAR name with the actual artifact name produced by the build):

~~~bash
jar tf build/libs/early-listeners-demo-1.0.0.jar
~~~

Look for `BOOT-INF/classes/META-INF/spring.factories` in the executable JAR listing if it is the application's own resource. If a library contains `spring.factories`, it may reside inside a JAR under `BOOT-INF/lib`. Presence of the resource rules out packaging mistakes, though it **does not automatically guarantee the listener class instantiates cleanly**; still verify class names, constructors, and logs.

## 15. Operational and Testing Notes

A listener invoked early strongly affects whether an application can start. Therefore:

1. **Keep early listeners small and fast.** Spring Boot calls listeners on the startup thread by default for many milestones; blocking work can delay the entire `run`.
2. **Do not assume beans are ready.** Starting/environment phases precede the context; obtain information from the event when available.
3. **Do not log sensitive data from `Environment`.** It may contain passwords, tokens, and connection strings. In our example, `demo.tag` is a non-sensitive value.
4. **Avoid non-idempotent side effects.** There may be multiple contexts, multiple test runs, or duplicate registrations.
5. **Distinguish listener errors from bean errors.** An exception in a callback can fail `SpringApplication.run` before context refresh.
6. **Test both registration approaches.** Classpath tests with `spring.factories` must have the resource packaged/available as in runtime; builder tests must use the proper entrypoint.
7. **Separate responsibilities.** If the goal is to run one-time logic once the container has beans, `ApplicationRunner` is usually better suited than a super-early listener.

### An Extended Exercise

Implement a third listener for `ApplicationReadyEvent` using `@EventListener` on a bean inside the context. Run the demo again and observe:

~~~text
BUILDER ApplicationStartingEvent
FACTORIES ApplicationEnvironmentPreparedEvent demo.tag=hello
RUNNER
READY
MAIN contextActive=true
~~~

The `READY` line appears only after a real bean listener is defined and the runner completes successfully. This exercise illustrates **two early registration mechanisms** and **one late bean registration mechanism** coexisting in the same application.

## 16. Self-Check Questions

1. **Can `@Component` alone catch `ApplicationStartingEvent`?** Not during normal bootstrap, because the event occurs before the context creates beans.
2. **Must `SpringApplicationBuilder.listeners(...)` be called before or after `run`?** Before.
3. **Are the arguments to `listeners(...)` class names or listener objects?** Objects implementing `ApplicationListener`.
4. **Where is the application's factories file placed?** `src/main/resources/META-INF/spring.factories`.
5. **What key is used to auto-register `ApplicationListener`?** `org.springframework.context.ApplicationListener`.
6. **Does a listener in `spring.factories` need `@Component`?** No; it is loaded by the bootstrap mechanism.
7. **Can a factory listener require constructor injection of a context-created repository?** It should not; the context is not ready at the earliest events.
8. **Does Spring Boot 3.3 still use `spring.factories` for `ApplicationListener`?** Yes.
9. **Does `AutoConfiguration.imports` replace `spring.factories` for every purpose?** No; that is auto-configuration metadata.
10. **Are two listeners listening to the same event ordered by declaration position?** You should not rely on position; use appropriate ordering mechanisms.
11. **Can a library containing `spring.factories` affect applications using that library?** Yes, if the resource and listener class are on the classpath.
12. **Why does the example print `RUNNER` after `FACTORIES`?** The runner is a bean executing after refresh, whereas the factory listener catches the environment event before the context exists.
13. **If using regular `SpringApplication.run(...)` while keeping `spring.factories`, which listener is still auto-loaded?** The listener registered via `spring.factories`.
14. **If `ApplicationReadyEvent` is seen, can you conclude the starting listener will run again?** No. Past events are not replayed automatically; each event has its own timing.
15. **If the same listener is registered via both builder and factories, should you rely on it receiving the event only once?** No; avoid duplicate logic registration and design callbacks to tolerate repetition.

**Conclusion:** Both `SpringApplicationBuilder.listeners(...)` and `META-INF/spring.factories` inject an `ApplicationListener` into the startup process **before the context creates beans**. The builder fits when you want explicit control at the entrypoint; factories fit when you want classpath auto-discovery. In Spring Boot 3.3, `spring.factories` remains valid for listeners even though auto-configuration lists have moved to dedicated metadata. To choose the right registration mechanism, start from **the event you need to listen to** and **when that event occurs**, not merely from annotation syntax.

### References

- Spring Boot 3.3.13 — `SpringApplication`, **Fluent Builder API** and **Application Events and Listeners**: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — `SpringApplicationBuilder` API, `listeners(ApplicationListener<?>...)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html
- Spring Boot 3.3 — `SpringApplication` API, `addListeners(...)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework 6.1 — `ApplicationListener` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationListener.html
- Spring Framework 6.1 — `SpringFactoriesLoader`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/support/SpringFactoriesLoader.html
- Spring Boot 3.3 — Managing Dependencies with Gradle: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
