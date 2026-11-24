# Registering Initializers and Listeners Before Startup — Spring Boot 3.3

## 1. Why Are Hooks Needed Before SpringApplication Runs?

In Spring Boot, calling `SpringApplication.run(...)` does not merely invoke `main`: it prepares `Environment`, creates `ApplicationContext`, loads configuration and bean definitions, refreshes the context, and only then runs `ApplicationRunner`/`CommandLineRunner`. Some needs must be handled **before** ordinary beans are created:

- Adding configuration or registering components into the context before refresh.
- Observing events when the application has just started or `Environment` has just been prepared.
- Recording errors if startup fails, even when the context has not finished starting.
- Packaging reusable hooks to apply automatically whenever a Spring Boot application starts.

Two extension points are directly involved:

| Hook | Interface | Purpose | Timing |
| --- | --- | --- | --- |
| **Initializer** | `ApplicationContextInitializer<ConfigurableApplicationContext>` | Customizes the context, registers info/configuration needed before refresh | After context creation, **before refresh** |
| **Listener** | `ApplicationListener<E extends ApplicationEvent>` | Receives matching events and reacts at lifecycle milestones | When the event is published; possibly **even before the context exists** if registered early |

Initializers and listeners are **not synonymous**. An initializer has an `initialize(context)` callback, applied when preparing a context. A listener has an `onApplicationEvent(event)` callback, which can run multiple times as matching events occur. Both must be **registered before calling `run(args)`** if you want to control the initial startup phase.

## 2. Understanding the Startup Order Before Writing Code

Key milestones of a successful startup in Spring Boot 3.3:

```text
main()
  │
  ├── new SpringApplication(App.class)
  ├── addInitializers(...) / addListeners(...)    ← register hooks beforehand
  │
  └── run(args)
       ├── ApplicationStartingEvent               ← context not created yet
       ├── prepare Environment
       ├── ApplicationEnvironmentPreparedEvent    ← context not created yet
       ├── create ApplicationContext
       ├── invoke ApplicationContextInitializers
       ├── ApplicationContextInitializedEvent     ← initializers have run
       ├── load bean definitions
       ├── ApplicationPreparedEvent               ← not refreshed yet
       ├── refresh context, create beans, start web server if any
       ├── ContextRefreshedEvent                  ← Spring Framework event
       ├── ApplicationStartedEvent                ← before runners
       ├── LivenessState.CORRECT
       ├── ApplicationRunner / CommandLineRunner
       ├── ApplicationReadyEvent                  ← after runners
       └── ReadinessState.ACCEPTING_TRAFFIC
```

This is a **conceptual diagram**, omitting internal steps and additional events such as `WebServerInitializedEvent`. If startup fails, Spring Boot publishes `ApplicationFailedEvent`; the earlier the failure occurs, the fewer components already exist.

Understand three boundaries:

1. **Before context creation:** `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent` can already occur; normal Spring beans cannot be retrieved.
2. **Context created but not yet refreshed:** `ApplicationContextInitializer` receives `ConfigurableApplicationContext` and can prepare information needed when the context refreshes; services/repositories are not guaranteed to be created yet.
3. **After refresh:** ordinary beans can now operate, runners are invoked after `ApplicationStartedEvent`, and `ApplicationReadyEvent` is published after runners.

A `@Component` or `@Bean` implementing `ApplicationListener` is only created when the container processes beans, so it **does not retroactively receive events published earlier**. For very early events, register the listener directly via `SpringApplication` or a bootstrap auto-registration mechanism.

## 3. How to Register Directly on SpringApplication

The usual static call:

```java
SpringApplication.run(App.class, args);
```

starts immediately, leaving no room to configure `SpringApplication` before running. Create an instance instead:

```java
SpringApplication app = new SpringApplication(App.class);
app.addInitializers(new MyContextInitializer());
app.addListeners(new MyEarlyListener());
app.run(args);
```

`MyContextInitializer` and `MyEarlyListener` in the short snippet above are **illustrative names** that need to be defined. Both `addInitializers(...)` and `addListeners(...)` accept one or more hook instances. You must call `run(args)` on **the exact configured instance**; accidentally calling `SpringApplication.run(App.class, args)` elsewhere means those hooks are not passed to the new run.

Do not wait until after `run(args)` to call `addListeners` or `addInitializers`: by then key bootstrap milestones have already passed, or `run` may have already thrown an exception.

## 4. Runnable Maven Project on Java 21 and Spring Boot 3.3

The following example launches a **non-web application** to make event observation easy. The initializer adds a low-priority default configuration value; the listener observes when `Environment` is prepared; the runner prints the value read by Spring after context refresh.

Structure:

```text
startup-hooks/
├── pom.xml
└── src/main/java/com/example/hooks/
    ├── HooksApplication.java
    ├── DefaultMessageInitializer.java
    └── EnvironmentReadyListener.java
```

### 4.1. Maven pom.xml

**File `pom.xml`**:

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

    <groupId>com.example</groupId>
    <artifactId>startup-hooks</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
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

`spring-boot-starter` suffices for a CLI example; `spring-boot-starter-web` is unnecessary since there are no HTTP endpoints. Boot's parent POM manages compatible library versions. The 3.3 line requires at least Java 17, though this article uses JDK 21 for a consistent practice environment.

### 4.2. ApplicationContextInitializer: Preparing the Context Before Refresh

**File `src/main/java/com/example/hooks/DefaultMessageInitializer.java`**:

```java
package com.example.hooks;

import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

public final class DefaultMessageInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        MapPropertySource defaults = new MapPropertySource(
                "hookDemoDefaults",
                Map.<String, Object>of("demo.message", "Hello from initializer"));

        // addLast: allows higher-precedence configuration sources to override this value.
        context.getEnvironment().getPropertySources().addLast(defaults);

        System.out.println("initializer: context created, before refresh");
    }
}
```

Explanation:

- `initialize(...)` is invoked by `SpringApplication` before refresh.
- `ConfigurableApplicationContext` provides access to the context's `Environment`.
- `MapPropertySource` represents a property source named `hookDemoDefaults`.
- `addLast` gives this source lower priority compared to existing property sources, making it convenient as a fallback.
- This moment is suitable for **preparing information for bean creation**, but **unsuitable for looking up a fully initialized service bean via `context.getBean(...)`**.

If the goal is solely to declare default properties, `SpringApplication.setDefaultProperties(Map)` is usually more concise. Here an initializer is intentionally used to study the lifecycle.

### 4.3. ApplicationListener: Catching an Event Before the Context Exists

**File `src/main/java/com/example/hooks/EnvironmentReadyListener.java`**:

```java
package com.example.hooks;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public final class EnvironmentReadyListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        System.out.println("listener: environment prepared");
    }
}
```

`ApplicationEnvironmentPreparedEvent` occurs once Spring Boot has prepared `Environment`, **before creating `ApplicationContext`**. You can access `event.getEnvironment()` to read configuration at that moment; you cannot expect a controller or service bean to exist yet. Using generics ensures receiving the exact event type of interest.

### 4.4. Main Class: Registering Before Calling run

**File `src/main/java/com/example/hooks/HooksApplication.java`**:

```java
package com.example.hooks;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class HooksApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(HooksApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        // Important: register hooks BEFORE run(args).
        app.addInitializers(new DefaultMessageInitializer());
        app.addListeners(new EnvironmentReadyListener());

        app.run(args);
    }

    @Bean
    ApplicationRunner showMessage(Environment environment) {
        return arguments -> System.out.println(
                "runner: " + environment.getProperty("demo.message"));
    }
}
```

`@SpringBootApplication` lets Spring Boot discover configurations/beans under package `com.example.hooks`. The `@Bean ApplicationRunner` is instantiated after context refresh and runs after `ApplicationStartedEvent`. Thus, the runner reads `demo.message` added earlier by the initializer.

### 4.5. Compiling, Running, and Verifying

In the `startup-hooks` directory, using JDK 21 and Maven:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Filtering only the three `System.out.println` lines printed by the example, the order is:

```text
listener: environment prepared
initializer: context created, before refresh
runner: Hello from initializer
```

The console may have interleaved Spring Boot logs; do not treat the block above as the entire stdout. The order of the three lines is what matters: **the listener runs on the pre-context event**, **the initializer runs once the context is created**, and **the runner runs after refresh**.

Packaging an executable JAR:

```bash
mvn package
java -jar target/startup-hooks-0.0.1-SNAPSHOT.jar
```

Testing a higher-precedence configuration source:

```bash
java -jar target/startup-hooks-0.0.1-SNAPSHOT.jar --demo.message=From-CLI
```

The runner line is now:

```text
runner: From-CLI
```

Because command-line arguments are placed into `Environment` by Spring Boot with higher precedence than the `hookDemoDefaults` source added via `addLast`. In a non-web example, the JVM normally exits after runners if no other non-daemon threads keep the process alive.

## 5. Registering with SpringApplicationBuilder

`SpringApplicationBuilder` offers a fluent API with the same semantics:

```java
package com.example.hooks;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;

public class BuilderLauncher {
    public static void main(String[] args) {
        new SpringApplicationBuilder(HooksApplication.class)
                .web(WebApplicationType.NONE)
                .initializers(new DefaultMessageInitializer())
                .listeners(new EnvironmentReadyListener())
                .run(args);
    }
}
```

This is an **alternative launcher** to `HooksApplication.main`; you do not need to run both. The configuration class is still `HooksApplication`, so the `showMessage` bean is still registered. When using the builder, attach `initializers(...)`/`listeners(...)` before `run(args)` just like when using an instance.

The builder is especially convenient when managing multiple `ApplicationContext`s in a parent–child relationship. In a hierarchy, events can propagate to the parent context; a listener may receive multiple events of the same type from different contexts, so do not assume each event type is published only once system-wide.

## 6. Auto-Registering via META-INF/spring.factories

For hooks packaged in a library or reused across multiple applications, Spring Boot can discover initializers/listeners from classpath metadata.

Create **file `src/main/resources/META-INF/spring.factories`**:

```properties
org.springframework.context.ApplicationContextInitializer=com.example.hooks.DefaultMessageInitializer
org.springframework.context.ApplicationListener=com.example.hooks.EnvironmentReadyListener
```

The two keys above are the fully qualified Spring Framework interface names. When `spring.factories` is on the classpath, Spring Boot 3.3 can load the implementations automatically during bootstrap, regardless of how `main` constructs `SpringApplication`.

**Practice one mechanism at a time:** to verify `spring.factories`, remove the two `app.addInitializers(...)` and `app.addListeners(...)` calls from `main`, then run again. If you both register manually and use metadata, hook instances can be added twice and cause unintended duplicate invocations or side effects.

These classes must be instantiated very early, so they should have an accessible no-arg constructor and must not require Spring bean constructor injection. Both classes in the example meet this requirement.

**Do not confuse with Boot 3's auto-configuration mechanism:** the list of auto-configuration classes is declared via `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; that is **separate** from registering listeners/initializers via the `spring.factories` keys above.

## 7. Key Events and Choosing the Right Hook

| Event / Hook | Timing | How to Use |
| --- | --- | --- |
| `ApplicationStartingEvent` | Right after `run` begins, before Environment is complete | Listener registered very early; do not access beans |
| `ApplicationEnvironmentPreparedEvent` | Environment ready, no context yet | Observe configuration and perform limited early adjustments |
| `ApplicationContextInitializer.initialize` | Context just created, not refreshed yet | Customize the context before bean instantiation |
| `ApplicationContextInitializedEvent` | After initializers, before loading bean definitions | Track when initializers finish |
| `ApplicationPreparedEvent` | Definitions loaded, about to refresh | Observe context preparation completion |
| `ApplicationStartedEvent` | Context refreshed, before runners | Track when startup is nearly complete |
| `ApplicationReadyEvent` | Runners have been invoked | Signal that the application is ready |
| `ApplicationFailedEvent` | Startup throws an error | Record the cause; context might not exist yet |

Distinguishing hooks from related mechanisms:

- **`@EventListener` or `ApplicationListener` bean:** suitable for events occurring after the bean-managing context is ready; does not replace listeners registered very early.
- **`ApplicationRunner`/`CommandLineRunner`:** suitable for tasks after refresh but before ready, such as checking initial data or performing a finite initialization step.
- **`EnvironmentPostProcessor`:** suitable for customizing `Environment` during early bootstrap, especially when config-loading timing matters. Registered using Boot's corresponding mechanism; distinct from a context initializer.
- **`SpringApplication.setDefaultProperties(...)`:** simple choice for default values; no need to build an initializer just to add one property.
- **`BootstrapRegistryInitializer`:** advanced bootstrap-registry-phase hook, not synonymous with `ApplicationContextInitializer`.

Because listeners are typically invoked synchronously on the event-publishing thread, avoid running heavy workloads, long network downloads, large data writes, or operations that may block indefinitely inside startup events. Move long-running logic into an explicitly designed lifecycle component or runner with timeouts and error handling.

## 8. Catching Startup Failures and Ordering Hooks

A listener can specifically listen for `ApplicationFailedEvent` to record errors **even when the context fails to start**.

**Additional file `src/main/java/com/example/hooks/StartupFailureListener.java`**:

```java
package com.example.hooks;

import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

public final class StartupFailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        System.err.println("startup failed: " + failure.getClass().getSimpleName());
    }
}
```

Register **before** `app.run(args)` in `HooksApplication.main`:

```java
app.addListeners(new StartupFailureListener());
```

This listener prints nothing when startup succeeds. If an exception occurs, the callback prints the simple class name of the exception received; read the full stack trace and `Caused by` chain to determine the root cause. `ApplicationFailedEvent.getApplicationContext()` can return `null` if the context was not created yet; do not rely on beans when handling very early errors.

When a group of initializers/listeners have ordering dependencies, they can implement `Ordered` or use `@Order`. Example logic for an initializer that needs to run with priority:

```java
// Illustrative method inside a class implementing Ordered:
@Override
public int getOrder() {
    return Ordered.HIGHEST_PRECEDENCE;
}
```

The snippet above **is not a standalone Java file**. To use it, import `org.springframework.core.Ordered` and add `Ordered` to the class's `implements` clause. `@Order`/`Ordered` only defines processing order among matching hooks; it does not alter the order in which the framework publishes lifecycle events.

## 9. Common Issues

### 9.1. Listener Annotated with @Component Does Not Receive Early Events

**Cause:** Spring has not created beans yet when `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent` is published.

**Solution:** switch to registering via `SpringApplication.addListeners(...)`, the builder, or `spring.factories`. Ensure the generic type or listener signature matches the target event.

### 9.2. Initializer Is Not Invoked

Check whether `addInitializers` was called before `run`; whether the exact `SpringApplication` instance was used; whether the class properly implements `ApplicationContextInitializer`; and if using `spring.factories`, whether the file path and FQCN are accurate. Do not read configuration prematurely and conclude the initializer "is not working": a property may simply have been overridden by a higher-precedence source.

### 9.3. Calling getBean in an Initializer Causes an Error

**Cause:** the context has not refreshed yet; singletons/services may not exist yet.

**Solution:** only prepare configuration, bean definitions, or context settings in this hook; move work requiring beans to a post-refresh phase, such as a runner or an appropriate bean lifecycle callback.

### 9.4. Hook Runs Twice

**Cause:** the same class is registered in both `main` and `spring.factories`, or the application has multiple contexts. **Solution:** pick a single registration source; if using a context hierarchy, distinguish which context published the event.

### 9.5. Configuration Change Does Not Affect Logs or Bootstrap

**Cause:** initializers execute after the `Environment` preparation phase, while some settings have already been processed by Boot. **Solution:** choose `EnvironmentPostProcessor` or an EnvironmentPrepared listener if you genuinely need to intervene before context creation; use `setDefaultProperties` for simple defaults.

### 9.6. Startup Hangs or Fails Because of a Listener

**Cause:** a listener performs network calls without timeouts, runs heavy logic, or throws an exception. **Solution:** hooks should be short, with logging and error handling; move post-refresh work to a runner with clear resource limits.

### 9.7. Confusing Started and Ready

`ApplicationStartedEvent` arrives after refresh **before** runners; `ApplicationReadyEvent` arrives **after** runners. Do not report that runner tasks have completed simply upon receiving `ApplicationStartedEvent`.

## 10. Self-Check Exercises

1. Explain why the three lines in the section 4 example appear in the order listener → initializer → runner, even though both the initializer and listener are registered before `run`.
2. If you change `EnvironmentReadyListener` to `@Component` and remove `addListeners`, will the `ApplicationEnvironmentPreparedEvent` callback still be called? Why or why not?
3. Run the application with `--demo.message=From-CLI`. Identify the value the runner receives and the role of `addLast`.
4. Register an additional listener for `ApplicationContextInitializedEvent`; compare when it appears against the initializer.
5. Move the hooks to `META-INF/spring.factories`, remove the registration calls from `main`, and re-verify the startup sequence.
6. Write a `StartupFailureListener`, trigger a controlled startup failure to observe the error; do not assume the context exists inside the callback.
7. Choose the right hook for three scenarios: adding a default property, customizing the context before refresh, and executing a task that requires an initialized service bean.
8. Why does `@Order` not cause `ApplicationReadyEvent` to occur before `ApplicationStartedEvent`?

After this lesson, you should be able to **register initializers/listeners before startup**, distinguish between early, pre-refresh, and post-refresh events, and troubleshoot why a hook is not invoked.

## 11. Official Documentation

- Spring Boot 3.3.13 — SpringApplication and application event ordering: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — SpringApplication API (`addInitializers`, `addListeners`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework 6.1 — IoC container and lifecycle: https://docs.spring.io/spring-framework/reference/core/beans.html
