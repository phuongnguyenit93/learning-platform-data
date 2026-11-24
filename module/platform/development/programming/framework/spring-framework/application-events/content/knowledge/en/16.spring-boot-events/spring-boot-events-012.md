# Declaring `ApplicationListener` via `META-INF/spring.factories` in Spring Boot

## 1. When Should You Declare a Listener Using `spring.factories`?

Spring Boot publishes several **SpringApplication events** throughout `SpringApplication.run(...)`. Some events appear **before `ApplicationContext` is created**, so listeners declared via `@Component`, `@Bean`, or `@EventListener` methods in beans cannot be present yet to receive them.

For example:

- `ApplicationStartingEvent` is published very early, before `Environment` and `ApplicationContext` are ready.
- `ApplicationEnvironmentPreparedEvent` is published once `Environment` is prepared, while the context has still not been created.
- `ApplicationContextInitializedEvent` is published after the context is created and `ApplicationContextInitializer`s have run, but before bean definitions are loaded.

To have Spring Boot **discover a listener right when preparing to run the application**, including for the early events above, you can register a class implementing `ApplicationListener` via the file:

```text
src/main/resources/META-INF/spring.factories
```

Minimal contents:

```properties
org.springframework.context.ApplicationListener=demo.BootstrapEventsListener
```

The part before `=` must be the **fully qualified name of the interface** `org.springframework.context.ApplicationListener`; the part after is the fully qualified name of the listener class to instantiate. Spring Boot loads these registrations from the classpath when setting up `SpringApplication`, **without waiting** for component scanning or dependency injection inside the context.

**Key takeaway:** `spring.factories` is used in this article to register an **`ApplicationListener`**. That differs from registering **auto-configuration**: starting in Spring Boot 3, declaring auto-configuration with key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` in `spring.factories` is no longer supported; auto-configuration uses `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. The two mechanisms serve different purposes and should not be confused.

## 2. Why Aren't `@EventListener` or `@Bean` Enough for Early Events?

Consider two registration styles:

```java
@Component
public class ReadyObserver {
    @EventListener
    public void ready(ApplicationReadyEvent event) {
        // Can receive once the context has beans.
    }
}
```

This is illustrative code; imports for `Component`, `EventListener`, and `ApplicationReadyEvent` are needed. The `@EventListener` method is discovered by Spring **when the bean is created/registered**. It can receive late events such as `ApplicationReadyEvent`, yet it cannot turn back time to receive `ApplicationStartingEvent` published before the context existed.

Conversely:

```java
public final class StartingObserver
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        // Can receive very early if registered via spring.factories
        // or SpringApplication.addListeners(...) before run().
    }
}
```

This is also illustrative code (requires importing `ApplicationListener` and `ApplicationStartingEvent`). **Implementing the interface alone is not enough**: the class must be registered with Spring Boot via `spring.factories` or an equivalent `addListeners`/builder API. Do not expect `@Component` on this class to make it receive `ApplicationStartingEvent`; the bean is still created too late.

### Selection Table

| Registration Method | When Available? | Receives `ApplicationStartingEvent`? | Best Fit |
| --- | --- | --- | --- |
| `META-INF/spring.factories` with key `ApplicationListener` | When Spring Boot builds `SpringApplication`/startup listeners | **Yes**, if class is valid and on the classpath | Libraries or bootstrap listeners needing automatic activation |
| `SpringApplication.addListeners(...)` before `run()` | When the developer registers before startup | **Yes** | Applications needing per-run registration control |
| `new SpringApplicationBuilder(...).listeners(...)` | When configuring builder before `run()` | **Yes** | Applications using the builder or context hierarchies |
| Spring bean implementing `ApplicationListener<T>` | After the context can instantiate/register beans | **No** for events already published earlier | Late events and application context events |
| `@EventListener` on a Spring bean | When Spring processes listener methods of the bean | **No** for early events | Business logic and events after context is ready |

Choose registration timing matching the event to observe. `ApplicationReadyEvent` or ordinary custom events usually **do not need** `spring.factories`, because Spring beans already exist to handle them.

## 3. Structure and Syntax of `spring.factories`

`spring.factories` is a file using **Java properties** syntax, placed precisely at `META-INF/spring.factories` inside the resources directory or JAR.

Example with one listener:

```properties
org.springframework.context.ApplicationListener=demo.BootstrapEventsListener
```

Example with multiple listeners:

```properties
org.springframework.context.ApplicationListener=\
demo.FirstBootstrapListener,\
demo.SecondBootstrapListener
```

The trailing `\` is line-continuation syntax in `.properties` format. Use commas to separate class names. Listed classes must be packaged on the runtime classpath, instantiable by the factory loading mechanism, and implement the appropriate `org.springframework.context.ApplicationListener`.

Important rules:

1. **Exact path:** `src/main/resources/META-INF/spring.factories`, not `src/main/java/META-INF/...`, and not a file named `spring-factories`.
2. **Exact key:** `org.springframework.context.ApplicationListener`, not the event name (`ApplicationStartingEvent`) and not `org.springframework.context.event.EventListener`.
3. **Exact fully qualified class name:** includes package and class, e.g. `demo.BootstrapEventsListener`.
4. **Class instantiable at bootstrap:** the simplest way is a `public class` or `public final class` with a public no-argument constructor. Do not require Spring to auto-inject beans before the context exists.
5. **Do not put `@Component` on the same listener class registered via factories without reason:** avoids creating an extra bean listener of the same type and risking duplicate event handling.
6. **Present on the runtime classpath:** when packaged as a library JAR, the file must live at `META-INF/spring.factories` inside that JAR. Spring Boot can discover factories files across multiple dependency JARs on the classpath.
7. **Watch out for resource merging:** a tool building a "fat/uber JAR" by naively merging files may overwrite `META-INF/spring.factories` from another dependency. If using a shaded JAR, ensure an appropriate resource-merging strategy; Boot executable JARs use a dedicated dependency packaging layout.

A listener loaded from `spring.factories` is **not a bean created via ApplicationContext constructor injection** at initial registration time. Therefore, avoid requiring `@Autowired` fields, repositories, services, or any context-dependent beans in constructors for early startup listeners. Once an event provides the environment or context, access only APIs genuinely available in that phase.

## 4. Runnable Java 17+ Example with Spring Boot 3.5

The example below demonstrates:

- A listener loaded via `spring.factories` receives **`ApplicationStartingEvent`** and **`ApplicationEnvironmentPreparedEvent`**, before Spring beans exist.
- That same listener can still receive the late event **`ApplicationReadyEvent`**.
- A `@Component` bean using `@EventListener` receives `ApplicationReadyEvent`, illustrating that factories are unnecessary for late events.
- Results are checked via four boolean flags, avoiding assumptions about console log ordering during Boot startup.

The project uses **Java 17**, **Spring Boot 3.5.16**, and Gradle 8.4+; no web server or database is required.

### 4.1. Structure

```text
boot-factories-listener-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── FactoriesDemoApplication.java
        │       ├── BootstrapEventsListener.java
        │       └── ReadyBeanObserver.java
        └── resources/
            └── META-INF/
                └── spring.factories
```

**`settings.gradle`**

```groovy
rootProject.name = 'boot-factories-listener-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'demo.FactoriesDemoApplication'
}
```

The Boot plugin and dependency-management plugin align compatible Spring dependency versions. If you do not have Gradle preinstalled, you can generate a Gradle Wrapper with Gradle and use `./gradlew` (Linux/macOS) or `gradlew.bat` (Windows); the example below uses the `gradle` command since the structure above does not include a wrapper.

### 4.2. Early-Loaded Listener: `BootstrapEventsListener.java`

```java
package demo;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class BootstrapEventsListener
        implements ApplicationListener<SpringApplicationEvent> {

    private static volatile boolean startingSeen;
    private static volatile boolean environmentSeen;
    private static volatile boolean readySeen;

    // No-arg constructor, independent of Spring beans.
    public BootstrapEventsListener() {
    }

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            startingSeen = true;
        } else if (event instanceof ApplicationEnvironmentPreparedEvent) {
            environmentSeen = true;
        } else if (event instanceof ApplicationReadyEvent) {
            readySeen = true;
        }
    }

    public static boolean startingSeen() {
        return startingSeen;
    }

    public static boolean environmentSeen() {
        return environmentSeen;
    }

    public static boolean readySeen() {
        return readySeen;
    }
}
```

Here `ApplicationListener<SpringApplicationEvent>` receives Spring Boot events extending `SpringApplicationEvent`, then uses `instanceof` to filter the three types under test. This is convenient for a demo. In real applications, if you only need one exact event, choose a more specific generic type such as `ApplicationListener<ApplicationEnvironmentPreparedEvent>`.

The `static` flags are solely a tool for the demo to verify after startup. Do not use static flags as production business storage, especially when a single JVM launches multiple `SpringApplication`s, runs repeated tests, or uses multiple class loaders.

### 4.3. Bean Listener Receiving Only Late Events: `ReadyBeanObserver.java`

```java
package demo;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyBeanObserver {

    private volatile boolean readySeen;

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        readySeen = true;
    }

    public boolean isReadySeen() {
        return readySeen;
    }
}
```

This bean is created by component scanning when the context is prepared; `@EventListener` registers the method. It does not try to receive `ApplicationStartingEvent` because that event fires **before** the component scanning phase. However, `ApplicationReadyEvent` occurs after refresh and after application runners, so the bean can receive it.

### 4.4. Main Program: `FactoriesDemoApplication.java`

```java
package demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class FactoriesDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(FactoriesDemoApplication.class);

        // Demo only needs startup events, without running a web server.
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ReadyBeanObserver bean =
                    context.getBean(ReadyBeanObserver.class);

            System.out.println("factories starting="
                    + BootstrapEventsListener.startingSeen());
            System.out.println("factories environment="
                    + BootstrapEventsListener.environmentSeen());
            System.out.println("factories ready="
                    + BootstrapEventsListener.readySeen());
            System.out.println("bean ready=" + bean.isReadySeen());
        }
    }
}
```

Spring Boot invokes `SpringApplication.run(...)` and publishes the corresponding Boot lifecycle events. The listener from factories was already created **before** early startup events were published; the bean observer is present only after the context has been processed.

Using `try-with-resources` closes `ConfigurableApplicationContext` after printing results. `WebApplicationType.NONE` does not automatically start an embedded web server; the lesson focuses solely on the event mechanism.

### 4.5. Registration File: `src/main/resources/META-INF/spring.factories`

```properties
org.springframework.context.ApplicationListener=demo.BootstrapEventsListener
```

This file alone registers the early listener. You do **not** need to define a `@Bean` for `BootstrapEventsListener`, and you do **not** need to import it in `FactoriesDemoApplication`. If the file is missing or placed in the wrong resources directory, Spring Boot can still run the application, yet the `factories ...` flags will show `false` because the listener never received the events.

### 4.6. Running and Output

Run with JDK 17 and Gradle 8.4+ available:

```bash
gradle bootRun
```

The `System.out.println` lines from `FactoriesDemoApplication`:

```text
factories starting=true
factories environment=true
factories ready=true
bean ready=true
```

Gradle and Spring Boot may print additional build/log lines depending on the environment; the four lines above are **the application's verification output**, not the entire terminal output.

**Why is this result valid?**

1. Spring Boot finds `META-INF/spring.factories` on the classpath and registers the class under key `org.springframework.context.ApplicationListener` before running startup steps.
2. `ApplicationStartingEvent` is dispatched at the very start of the run, before `Environment`/context exist; the factories listener already exists and sets `startingSeen=true`.
3. Once `Environment` is created and prepared, Boot publishes `ApplicationEnvironmentPreparedEvent`; the listener sets `environmentSeen=true`.
4. Boot creates/refreshes the context, runs application/command-line runners (if any), and then publishes `ApplicationReadyEvent`; both the factories listener and the `@EventListener` bean can receive this event.
5. `app.run(args)` returns after the ready phase upon successful startup, so the program reads all four flags below as `true`.

This is a successful startup example of a non-web application with no special runners and using the default synchronous event multicaster. When you add asynchronous listeners, your application's event handling may require dedicated test synchronization.

## 5. Spring Boot Events Related to Bootstrap Listeners

The `SpringApplication` lifecycle publishes events in the primary order:

| Event | Context at Publication Time | Receivable by a Listener from Factories? |
| --- | --- | --- |
| `ApplicationStartingEvent` | Run has just begun; neither `Environment` nor context exists | Yes |
| `ApplicationEnvironmentPreparedEvent` | `Environment` is available; context has not been created | Yes |
| `ApplicationContextInitializedEvent` | Context created and initializers run; bean definitions not yet loaded | Yes |
| `ApplicationPreparedEvent` | Bean definitions loaded; refresh has not begun | Yes |
| `ApplicationStartedEvent` | Context refreshed; before `ApplicationRunner`/`CommandLineRunner` | Yes |
| `ApplicationReadyEvent` | Runners finished; Boot is announcing application ready | Yes |
| `ApplicationFailedEvent` | Startup process failed | Yes, if listener was registered and failure event is published |

In addition, Boot publishes `AvailabilityChangeEvent` with **liveness/readiness** states at appropriate milestones. `AvailabilityChangeEvent` is not a subclass of `SpringApplicationEvent` as declared by the demo listener class; if you want to observe availability state, use a listener with a compatible event type.

Distinguish clearly:

- **Spring Boot's `ApplicationStartedEvent`**: after refresh, before runners.
- **Spring Framework's `ContextStartedEvent`**: reflects a call to `ConfigurableApplicationContext.start()`; does not automatically equate to Boot having started.
- **`ContextRefreshedEvent`**: context has refreshed.
- **Spring Boot's `ApplicationReadyEvent`**: ready milestone after runners.
- **Spring Framework's `ContextClosedEvent`**: context is preparing to close / closing.

With parent/child contexts, `ApplicationEvent`s from a child context can propagate to the parent context, causing a listener to receive multiple events of the same type. If you handle an event specific to a context, compare the event source/context rather than relying solely on class.

## 6. Programmatic Registration: `SpringApplication.addListeners` and `SpringApplicationBuilder.listeners`

If you only need a listener for **one application or one run**, factories are not strictly necessary:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new MyStartingListener());
app.run(args);
```

This example is an **illustrative snippet**, where `MyApplication` is the configuration class and `MyStartingListener` implements `ApplicationListener<ApplicationStartingEvent>` with an appropriate constructor. The key is calling `addListeners(...)` **before** `run(...)`.

Similarly with the builder:

```java
new SpringApplicationBuilder(MyApplication.class)
        .listeners(new MyStartingListener())
        .run(args);
```

Requires importing `org.springframework.boot.builder.SpringApplicationBuilder`. Both approaches above are useful when you want local registration control, constructor arguments passed to the listener, or the listener enabled only in a certain launch mode.

`spring.factories` fits better when:

- The listener lives in a **library** and consuming applications should auto-register the listener at bootstrap.
- The listener always needs to be present regardless of where `SpringApplication.run` is called.
- You want to distribute the listener as a JAR without requiring every application to modify `main()`.

The downside of auto-registration is **classpath-wide scope**: if the library is in multiple applications, every application may load that listener. Avoid heavy side effects in constructors and provide a configuration mechanism to enable/disable behavior when needed.

## 7. `spring.factories` vs. `AutoConfiguration.imports` in Boot 3+

This is a very common source of confusion when reading older articles:

| Purpose | Spring Boot 3.5 | File/Key |
| --- | --- | --- |
| Register listeners to catch early Boot application events | Supported | `META-INF/spring.factories` with key `org.springframework.context.ApplicationListener` |
| Register `ApplicationContextInitializer` for early use | Supported via appropriate factories mechanism | `META-INF/spring.factories` with key `org.springframework.context.ApplicationContextInitializer` |
| Register auto-configuration classes | Uses new format | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Writing `EnableAutoConfiguration=...` in `spring.factories` | No longer the auto-configuration registration path in Boot 3 | Migrate to `AutoConfiguration.imports` |

`AutoConfiguration.imports` usually contains **one auto-configuration class name per line**, without the `ApplicationListener` key. Example:

```text
demo.autoconfigure.ExampleAutoConfiguration
demo.autoconfigure.AnotherAutoConfiguration
```

This is an **example of auto-configuration file structure**, not a replacement file for the listener factories in this lesson. Conversely, `spring.factories` is key–value properties; do not rename the file while keeping the same format.

Main takeaway when upgrading from Boot 2.x: Spring Boot 3 changed how **auto-configurations** are discovered, which **does not mean removing all of `spring.factories`**. The `ApplicationListener` key for bootstrap listeners still works.

## 8. When to Use `ApplicationListener` vs. `EnvironmentPostProcessor`?

A listener receiving `ApplicationEnvironmentPreparedEvent` can **read or modify** `ConfigurableEnvironment` while Boot is preparing startup, yet you should not default to using a listener for every kind of environment modification.

Example of an early listener that only reads properties:

```java
public class ProfileObserver
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        String[] profiles = event.getEnvironment().getActiveProfiles();
        // Can inspect profile/environment metadata in this phase.
        // Do not access @Autowired services because the context is not ready yet.
    }
}
```

This is an illustrative snippet requiring imports for `ApplicationListener` and `ApplicationEnvironmentPreparedEvent`. The class must be registered early. Keep in mind that when certain config data loads, listener ordering, and property sources affect which values are already configured in that phase.

If the goal is **systematically adding/modifying property sources**, Spring Boot has `EnvironmentPostProcessor`, which fits environment-processing intent better. It also has its own bootstrap registration path. Do not turn a factories listener into the home for all complex configuration merely because it runs early.

Selection rules:

- **Observe startup or early failures:** `ApplicationListener<...>` via `spring.factories`/`addListeners`.
- **Intervene in environment configuration before context:** consider `EnvironmentPostProcessor`.
- **Initialize beans or business logic after context:** `@Bean`, `@Component`, `@EventListener`, or `ApplicationRunner`.
- **Tasks when the application is genuinely ready:** `ApplicationReadyEvent` or a runner according to business semantics.
- **Stop/start background resources:** consider `SmartLifecycle` and shutdown callbacks; do not force every operation into a bootstrap event listener.

## 9. Listener Ordering, Startup Errors, and Limitations

### 9.1. Ordering

A class loader can find multiple `spring.factories` files across multiple JARs. Do not rely on the order classes are listed in files to coordinate dependent operations. Spring provides ordering mechanisms for listeners, such as `Ordered` or `@Order` where appropriate.

```java
public final class OrderedStartingListener
        implements ApplicationListener<ApplicationStartingEvent>, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        // Observe startup in the order appropriately sorted by Spring.
    }
}
```

This is illustrative code requiring imports for `ApplicationListener`, `ApplicationStartingEvent`, and `Ordered`. The order value only affects how Spring sorts listeners inside the corresponding dispatch mechanism; it **does not turn listeners into atomic transactions** or guarantee completion order if handled across multiple threads.

### 9.2. Pre-Context Events Cannot Rely on Dependency Injection

At `ApplicationStartingEvent`, Spring has not prepared `Environment` or the context yet. Avoid:

- Requiring constructor injection of an `@Service`/repository.
- Calling `ApplicationContext.getBean(...)` before the context exists.
- Assuming a `@ConfigurationProperties` bean is already bound.
- Querying a database or making slow network API calls on the startup thread.

At `ApplicationEnvironmentPreparedEvent`, you have a configuration environment to read, yet **no guarantee that business beans exist yet**. With `ApplicationContextInitializedEvent`, the context is created, yet **bean definitions have not been fully loaded**. With `ApplicationPreparedEvent`, the context has not refreshed, so most beans should not be accessed as though the application were ready.

### 9.3. `ApplicationFailedEvent`

If Boot fails to start, a listener receiving `ApplicationFailedEvent` can be useful for logging/telemetry. However, never assume `ApplicationContext` or all beans always exist:

```java
public final class FailureObserver
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        // Use available error info; the context may not have been created yet.
    }
}
```

This is an illustrative snippet requiring imports for `ApplicationListener` and `ApplicationFailedEvent`. The listener must be registered early like other listeners if you want to cover failures before the context exists.

Do not let errors inside the monitoring listener itself complicate fail-fast behavior. Log safely, avoid depending on uninitialized infrastructure, and keep handling brief.

## 10. Testing `spring.factories` Properly

### 10.1. Testing by Actually Launching `SpringApplication`

Because the focus is early application events **before the context has beans**, a test using only `ApplicationContextRunner` or manually instantiating `AnnotationConfigApplicationContext` does not fully replace testing the `SpringApplication.run(...)` path. Have an integration test launching a small Boot application with `META-INF/spring.factories` on the classpath.

Useful assertions:

1. After `run()` succeeds, the early listener received `ApplicationStartingEvent`.
2. `ApplicationEnvironmentPreparedEvent` was received before the bean creation stage.
3. Listeners declared only as Spring beans are not assumed to have received early events.
4. `ApplicationReadyEvent` was received after runners completed, when startup succeeds.
5. If intentionally triggering startup failure, the factories listener can observe `ApplicationFailedEvent`, even when the context failed to refresh.
6. If multiple JARs register listeners, verify no duplicate processing occurs and ordering relies solely on documented rules.

The demo in section 4 already asserts observations via booleans after `app.run(args)`. When writing JUnit tests, replace print lines with `assertTrue(...)` and **reset static state between tests** if keeping the demo's state-storage approach, or design an observer inspectable independently per run.

### 10.2. Verifying the Exact Location in the Build

If the listener is not loaded:

```bash
gradle clean processResources
```

Then verify the resource was copied into the corresponding build directory, for example:

```text
build/resources/main/META-INF/spring.factories
```

If building `bootJar`, inspect the JAR to verify it contains the resource and listener class at the right paths. If using multiple packaging/relocation plugins, ensure resources are not overwritten. Do not edit `spring.factories` inside a third-party dependency for testing; provide the file in your application module or a library module you control.

### 10.3. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Listener does not receive `ApplicationStartingEvent` | Only using `@Component`/`@Bean`; registered too late | Use `spring.factories` or `addListeners` before `run()` |
| Factories listener does not run | Wrong `META-INF/spring.factories` path, wrong key, or resource missing from classpath | Verify file name, full key, `processResources`, and JAR contents |
| `IllegalArgumentException`/error instantiating factory listener | Wrong class name, class does not implement `ApplicationListener`, unsuitable constructor | Ensure class is public, has a usable no-arg constructor, and implements the right interface |
| No `Environment` yet | Handling inside `ApplicationStartingEvent` | Wait for `ApplicationEnvironmentPreparedEvent` to read environment |
| `@Autowired` service is null/unready | Listener created before ApplicationContext | Avoid bean dependencies in bootstrap listeners |
| `ApplicationStartedEvent` confused with `ContextStartedEvent` | Wrong package import or mixing up Spring Boot and Spring Framework | Check class name and actual publication timing |
| Listener handles the same event twice | Registered via both factories and bean, multiple contexts, or multiple registrations | Use one registration path and inspect context/event source |
| After upgrading to Boot 3, auto-configuration fails to load | Still declaring `EnableAutoConfiguration` in `spring.factories` | Move auto-config to `AutoConfiguration.imports`; keep `ApplicationListener` key separate |
| Test creating only ApplicationContext misses early events | Not running `SpringApplication` lifecycle | Write an integration test invoking `SpringApplication.run` |
| Startup very slow or aborted by listener | Blocking I/O or exception during bootstrap | Keep listener short and safe; move long work to an appropriate stage |

## 11. Project Adoption Checklist

Before adding a listener from `spring.factories` to a project or library, confirm:

- **Which event do you want to receive?** If it occurs before the context, early registration is required; if only late events are needed, consider a simpler `@EventListener` bean.
- **Are the resource path and `ApplicationListener` key exact?** Verify inside the packaged artifact as well, not just source files.
- **Can the class be instantiated outside Spring context?** Avoid DI dependencies in the constructor and heavy initialization logic.
- **Did you avoid duplicate registration?** Do not accidentally both declare in factories and annotate the same listener with `@Component`.
- **Is the listener safe at that stage?** `ApplicationStartingEvent` has no environment yet; `ApplicationFailedEvent` may have no context.
- **Are ordering and errors clearly designed?** Do not slow startup with optional work; do not rely on implicit ordering.
- **Which Boot version?** Distinguish `ApplicationListener` in `spring.factories` from auto-configuration in `AutoConfiguration.imports` in Boot 3+.
- **Is there a real startup test?** A test running `SpringApplication.run` catches path, packaging, class loading, and listener registration errors.

**Summary:** To listen for Spring Boot events occurring before `ApplicationContext` is ready, declare a class implementing `ApplicationListener` in `META-INF/spring.factories` under key `org.springframework.context.ApplicationListener`. For late events, an `@EventListener` bean is usually sufficient. In Spring Boot 3+, do not confuse this listener mechanism with registering auto-configuration via `AutoConfiguration.imports`.

## Official Documentation

- [Spring Boot 3.5 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-events-and-listeners)
- [Spring Boot 3.5 — SpringApplication and listener bootstrap customization](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot — Customize Environment or ApplicationContext Before It Starts](https://docs.spring.io/spring-boot/how-to/application.html)
- [Spring Boot 3.5 — Spring Boot application event classes](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/package-summary.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html)
- [Spring Boot 3 Migration Guide — Auto-configuration files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
