# ApplicationEnvironmentPreparedEvent in Spring Boot

## 1. Concept and Lifecycle Position

`ApplicationEnvironmentPreparedEvent` is a **Spring Boot application event** in package `org.springframework.boot.context.event`. Spring Boot publishes this event when the `Environment` used for the application has been created/prepared to the appropriate stage, **before the `ApplicationContext` is created**.

Its purpose is to provide a very early extension point to observe or, when clearly justified, customize the configuration environment before the container instantiates beans. For example: reading configuration flags for bootstrap, recording active profiles, or checking the presence of a mandatory configuration setting.

This event differs from Spring Framework's `ContextRefreshedEvent`. At the moment `ApplicationEnvironmentPreparedEvent` is published, the application **does not yet have an active context**, nor any initialized beans available for dependency injection as in a regular listener.

Key characteristics:

- **Publisher:** `SpringApplication` during the Spring Boot startup cycle, not a business event published by a controller or service.
- **Timing:** After `ApplicationStartingEvent` and before `ApplicationContextInitializedEvent`.
- **Main payload:** `event.getEnvironment()` returns a `ConfigurableEnvironment` containing the `PropertySource`s and profile information available when the event is handled.
- **Listener registration:** Must be registered **before `SpringApplication.run(...)`**, e.g., via `addListeners(...)` or `META-INF/spring.factories`.
- **Limitations:** Do not inject beans with `@Autowired` in this early listener, and do not treat the event as a signal that the application is ready to accept requests.

## 2. Sequence of Application Events

Typical Spring Boot startup flow:

```text
SpringApplication.run(...)
         |
         v
ApplicationStartingEvent
         |
         v
Prepare Environment / process configuration sources
         |
         v
ApplicationEnvironmentPreparedEvent  <-- this topic
         |                                ApplicationContext not yet created
         v
Create ApplicationContext and run initializers
         |
         v
ApplicationContextInitializedEvent
         |
         v
Load bean definitions
         |
         v
ApplicationPreparedEvent
         |
         v
Refresh ApplicationContext
    (including ContextRefreshedEvent)
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
Application has passed normal startup
```

For web applications, there are also web-server-related events during refresh. If startup fails, Spring Boot may publish `ApplicationFailedEvent`. `ApplicationReadyEvent` also does not guarantee that external dependent systems will remain healthy after startup; separate health/readiness checks are required.

**Details on configuration processing order:** Boot has internal listeners and `EnvironmentPostProcessor`s that participate directly while handling the environment-prepared event. A custom listener may see different property sources depending on execution order (`Ordered`/`@Order`). Do not assume all custom extensions have already run just because this event is published. In a standard Boot setup, a listener without special priority sees configurations already processed by Boot along the default startup chain.

## 3. What Is in the Environment at This Point?

`Environment` is Spring's configuration access interface. `ConfigurableEnvironment` also allows retrieving the list of property sources and adjusting certain settings before the context is initialized. Common read operations:

| API | Meaning | Note |
| --- | --- | --- |
| `getProperty("demo.feature")` | Gets the effective value according to source precedence | May return `null` |
| `getProperty("demo.feature", "off")` | Default value if the key is not found | The default here is not written back into the Environment |
| `getProperty("demo.enabled", Boolean.class, false)` | Reads as a Boolean | May fail type conversion if misconfigured |
| `getActiveProfiles()` | List of active profiles | An empty array means no active profile was specified |
| `getDefaultProfiles()` | Default profiles, typically `default` | Not synonymous with active profiles |
| `getPropertySources()` | Accesses existing `PropertySource`s | Exact order and sources depend on timing, version, and configuration |

Sources typically include command-line arguments (e.g., `--demo.topic=events`), system properties, environment variables, `application.properties`/`application.yml` files, and profile-specific files. Spring Boot applies precedence rules across sources; standard `--key=value` arguments can override values in config files, unless the application has changed its policy for accepting command-line properties.

**Do not use an early listener to print all configuration values:** `Environment` can contain tokens, passwords, URIs with credentials, and internal data. Read only the keys you need, log via an allowlist, or mask sensitive values.

### Environment Exists, Beans Do Not

At this stage you can read:

```java
String feature = event.getEnvironment()
        .getProperty("demo.feature", "off");
```

However, you cannot expect the following to be ready yet:

- `@Autowired SomeService` in a component-scanned bean meant to receive the event.
- `ApplicationContext.getBean(...)` from the event (this event does not provide a context).
- `@ConfigurationProperties` beans already created and bound.
- Repositories, `DataSource`, controllers, web server, or application beans.

If you need a Spring-managed service, wait until the context exists, using `ApplicationRunner`, `ApplicationReadyEvent`, or an appropriate lifecycle callback.

## 4. How to Register a Listener at the Right Time

Because the event is published **before the context exists**, merely writing a `@Component` with `@EventListener(ApplicationEnvironmentPreparedEvent.class)` or declaring an `@Bean ApplicationListener<...>` inside the context is **too late for that startup run's event**.

There are three common ways to register early:

1. `SpringApplication.addListeners(listener)` before `run(args)`. Suitable for applications that control the `main` method, straightforward and immediately visible where the listener is declared.
2. `SpringApplicationBuilder.listeners(listener)` when bootstrapping via the builder.
3. `META-INF/spring.factories` using key `org.springframework.context.ApplicationListener` when a library needs to self-register a listener across applications that use it.

The listener must implement `ApplicationListener<ApplicationEnvironmentPreparedEvent>` or an appropriate `ApplicationListener` registered directly on `SpringApplication`. A listener instance created with `new` at this stage is **not a Spring-managed bean**: it has no standard dependency injection, `@PostConstruct`, bean scope, or proxy-based transactions.

### Comparison with Other Hooks

| Hook | When to Use? |
| --- | --- |
| `ApplicationEnvironmentPreparedEvent` | Observe the startup environment and perform small operations needed before context creation |
| `EnvironmentPostProcessor` | Systematically extend or modify `PropertySource`s during environment preparation |
| `ApplicationContextInitializer` | Customize `ConfigurableApplicationContext` after context creation, before refresh |
| `@PostConstruct` or `InitializingBean` | Initialize state of a single bean after it is created and injected |
| `ApplicationRunner`/`CommandLineRunner` | Run tasks after the context has refreshed, before Boot reports ready |
| `ApplicationReadyEvent` | React when Spring Boot's startup process reaches the ready milestone |

If the main task is **adding a configuration source** or intervening in config data loading order, `EnvironmentPostProcessor` is usually the clearer hook. If you only need to log a loaded value, a listener on this event may suffice.

## 5. Runnable Java 17+ Example: Reading an Argument When Environment Is Prepared

Create a Spring Boot application without running a web server. The example uses `SpringApplication.addListeners(...)` to receive the event before context creation, then observes `CommandLineRunner` and code after `run(...)`.

### Structure

```text
environment-prepared-demo/
├── pom.xml
└── src/main/java/example/boot/EnvironmentPreparedDemo.java
```

### pom.xml

Maven 3.9+, Java 17, and Spring Boot 3.3.13 (choosing a specific release version so the example is reproducible):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>environment-prepared-demo</artifactId>
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
```

### EnvironmentPreparedDemo.java

```java
package example.boot;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;

@SpringBootApplication
public class EnvironmentPreparedDemo {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EnvironmentPreparedDemo.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Must register before run(): context does not exist yet.
        application.addListeners(new EarlyEnvironmentListener());

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            System.out.println(
                    "MAIN contextActive=" + context.isActive());
        }
    }

    static class EarlyEnvironmentListener implements
            ApplicationListener<ApplicationEnvironmentPreparedEvent> {

        @Override
        public void onApplicationEvent(
                ApplicationEnvironmentPreparedEvent event) {

            ConfigurableEnvironment environment =
                    event.getEnvironment();

            String topic = environment.getProperty(
                    "demo.topic", "unset");

            System.out.println("EARLY demo.topic=" + topic);
        }
    }

    @Bean
    CommandLineRunner runner() {
        return args -> System.out.println("RUNNER executed");
    }
}
```

### Compile and Run

From the directory containing `pom.xml`:

```bash
mvn -q package
java -jar target/environment-prepared-demo-1.0.0.jar --demo.topic=events
```

Three lines printed **by the program itself** in order (any Maven/Spring logs are independent):

```text
EARLY demo.topic=events
RUNNER executed
MAIN contextActive=true
```

**Explanation:**

1. `addListeners(new EarlyEnvironmentListener())` is called on `SpringApplication` before calling `run(args)`. Thus the listener is present early enough to receive the event.
2. While Boot prepares the `Environment`, the command-line argument `--demo.topic=events` is added to the property sources. `event.getEnvironment().getProperty("demo.topic", "unset")` returns `events`.
3. Only after the environment is prepared does Boot create and refresh the context and instantiate application beans. The `@Bean CommandLineRunner` is invoked after refresh, printing `RUNNER executed`.
4. `application.run(args)` returns the context after completing standard startup; the `MAIN` block proves the context is active. Exiting `try-with-resources` closes the context.
5. If run again **without** `--demo.topic=events` and no other config source defines `demo.topic`, the first line becomes `EARLY demo.topic=unset`.

Printing with `System.out` in the example is solely to make the order obvious. In real applications, use a properly configured logging mechanism and do not log secrets. The listener does not require `@Component` or `@Bean` because it was registered on the `SpringApplication` instance.

## 6. Automatic Registration via META-INF/spring.factories

If you need to package a listener in a shared library, you can register it via a resource file:

```text
src/main/resources/META-INF/spring.factories
```

Contents:

```properties
org.springframework.context.ApplicationListener=\
example.boot.MyEarlyListener
```

Where `example.boot.MyEarlyListener` is **your custom listener class** and must have a suitable constructor for Boot to instantiate, for example:

```java
package example.boot;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public final class MyEarlyListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {
        String mode = event.getEnvironment()
                .getProperty("demo.mode", "normal");
        System.out.println("BOOTSTRAP mode=" + mode);
    }
}
```

Save the class file at `src/main/java/example/boot/MyEarlyListener.java`; this is a **standalone alternative** to calling `addListeners(...)`. Do not simultaneously register in `spring.factories` and call `addListeners(new MyEarlyListener())` for the same logic unless you intentionally want two instances and double execution.

The entry in `spring.factories` uses the **listener interface** name as the key, not the `ApplicationEnvironmentPreparedEvent` class name. Unlike Boot's auto-configuration mechanism, registering early `ApplicationListener`s can still use this approach.

Listeners can support ordering via `Ordered` or `@Order`; avoid assigning excessively high priority without understanding the order of Boot's internal listeners that handle config data and logging.

## 7. If You Need to Modify the Environment, How Should You Handle It?

You can call `event.getEnvironment().getPropertySources()` to inspect or modify `PropertySource`s. However, mutating configuration mid-startup comes with several constraints:

- Keys used to select **config file locations**, profiles, or bootstrap behavior may already have been consumed by some components before a custom listener runs. Do not assume modifying a property at this event will cause all config data to be re-read.
- `PropertySource`s have precedence order. `addFirst(...)` can override values from command-line arguments or environment variables, whereas `addLast(...)` usually acts only as a fallback. Choosing the order requires a clear business requirement.
- `@PropertySource` on `@Configuration` is generally added only during context refresh and may be too late for startup properties such as `logging.*` or `spring.main.*`.
- Do not attempt to touch beans/repositories here, as they have not been initialized yet.
- Early listeners should be brief, without long HTTP calls or holding unmanaged resources.

### Dedicated Hook: EnvironmentPostProcessor

When an application genuinely needs to load a custom property source before the context is created, Spring Boot supports the `EnvironmentPostProcessor` interface:

```java
package example.boot;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class DemoEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "demo-fallback",
                        Map.of("demo.feature", "off")));
    }
}
```

With Boot 3.3, register `src/main/resources/META-INF/spring.factories` as follows:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
example.boot.DemoEnvironmentPostProcessor
```

This is a **separate configuration-extension example** and does not need to be added to the runnable demo in section 5. It only creates a fallback source; the `demo.feature` key from higher-precedence sources still wins. Do not use it to alter sensitive properties or override deployment configuration unintentionally.

## 8. Common Misconception When Using @EventListener

The following style **does not satisfy early reception** of the event during the same startup run:

```java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class TooLateListener {

    @EventListener
    public void observe(ApplicationEnvironmentPreparedEvent event) {
        System.out.println("Never called during this startup");
    }
}
```

This snippet is an **anti-pattern illustration**, not a file from the section 5 demo. A `@Component` is discovered and instantiated when the context builds beans, while the event was already published before that point. Using `@EventListener` does not automatically register the listener on `SpringApplication` upfront.

Contrast this with later events: `ApplicationStartedEvent` and `ApplicationReadyEvent` occur after context refresh, so listeners registered in the container can be invoked via the standard mechanism.

Do not conclude that the event can "never" reach a bean listener in any contrived scenario. An application could manually re-publish the event or create multiple contexts. However, **for the early event of `SpringApplication.run(...)` itself**, registering via a bean in the context created afterward misses the timing window.

## 9. Practical Usage and Safety Conditions

### Appropriate Scenarios

- Observing configuration values needed during bootstrap for controlled logging.
- Detecting a missing critical property before the context is created; if choosing to fail fast, ensure the error is clear and does not leak sensitive information.
- Setting or validating a small bootstrap-related option inside a startup library.
- Measuring when a startup milestone is reached or attaching a correlation ID for early logs, provided it does not depend on beans.

### Scenarios Where Another Hook Should Be Chosen

- **Need to inject services** to run business logic: wait until the context is created.
- **Need to query a DB or call an API** to seed baseline data: pick an appropriate lifecycle hook and design timeouts/retries; do not assume it belongs before context creation.
- **Need to add a property source with custom mechanics:** use `EnvironmentPostProcessor`.
- **Need to know the app is ready for requests:** use `ApplicationReadyEvent`/readiness.
- **Need to react to runtime configuration changes:** this event is not an automatic hot-reload event.

### Do Not Misrecord State or Errors

A listener throwing an exception in an early phase can fail startup before the context is created. Therefore, fail fast intentionally only for truly mandatory configuration. Do not catch and silently ignore all configuration errors, yet do not turn a routine logging task into a failure point that prevents startup.

In systems with multiple `SpringApplication`/contexts or tests starting up multiple times, the listener may execute multiple times. If a side effect must be globally unique across the system, persistent tracking and dedicated idempotency are needed; a `boolean` field inside the listener is not enough.

## 10. Testing ApplicationEnvironmentPreparedEvent

Tests should independently prove three things: **the listener is registered early enough**, **it reads the required property**, and **it does not accidentally depend on context/beans**.

| Scenario | Expected Result |
| --- | --- |
| `addListeners(...)` before `run(...)`, passing `--demo.topic=events` | Listener is invoked and reads `events` |
| No arg passed and no other source provides the key | Fallback value `unset` |
| Only `@Component @EventListener` declared in the subsequently created context | Does not receive the environment-prepared event for that bootstrap run |
| Overriding key via command-line arg compared to `application.properties` | Command-line arg normally takes higher precedence |
| Listener attempts to use a Spring bean via dependency injection | Invalid at this bootstrap stage |
| Listener throws an exception | Can cause startup to fail, depending on error handling path |
| Same program started twice | Each bootstrap cycle can publish its own event; avoid duplicate side effects |

When writing integration tests, create `SpringApplication` with `WebApplicationType.NONE` to avoid starting a web server, register a listener capturing output into an `AtomicReference`/counter, run with a test key, and close the context. Do not assert the exact order of **all internal Boot listeners**, as that order depends on registered extensions and versions.

Illustrative test body snippet (**illustrative, not a standalone program**):

```java
AtomicReference<String> seen = new AtomicReference<>();

SpringApplication app =
        new SpringApplication(EnvironmentPreparedDemo.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.addListeners(
        (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event ->
                seen.set(event.getEnvironment()
                        .getProperty("demo.topic")));

try (ConfigurableApplicationContext context =
             app.run("--demo.topic=verified")) {
    assertEquals("verified", seen.get());
}
```

This snippet assumes imports for `AtomicReference`, `ApplicationListener`, `ApplicationEnvironmentPreparedEvent`, `ConfigurableApplicationContext`, `SpringApplication`, `WebApplicationType`, and JUnit's `assertEquals`; appropriate Spring Boot/JUnit test dependencies are required. This test verifies **the property value received by the listener**, without assuming log-line ordering across all libraries.

## 11. Common Mistakes and Fixes

**Mistake 1 — Registering via @Component and waiting for the event.** The bean is created too late. Register the listener directly with `SpringApplication.addListeners(...)` before `run(...)` or via `spring.factories`.

**Mistake 2 — Accessing ApplicationContext or @Autowired services in the listener.** `ApplicationEnvironmentPreparedEvent` does not hold a context; the bean container is not ready yet. Use only independently instantiable dependencies or pick a later event.

**Mistake 3 — Assuming the Environment is immutable or already processed by all extensions.** The ordering of `ApplicationListener` and `EnvironmentPostProcessor` affects readable values at each moment. Only set special priority when you thoroughly understand Boot's lifecycle.

**Mistake 4 — Modifying profiles or config locations too late.** Some settings have already been consumed while loading config data. Set them via CLI/system env or use a dedicated extension in the proper order.

**Mistake 5 — Printing the entire Environment for debugging.** This can leak secrets. Log only non-sensitive keys and mask identifying details when needed.

**Mistake 6 — Doing long I/O or blocking in an early listener.** By default, listeners run on the startup thread, increasing startup time or hanging startup. Move heavy work to a hook after the app is ready.

**Mistake 7 — Calling this event ContextRefreshedEvent or ApplicationReadyEvent.** These three events mark different milestones. Early environment != beans created != ready to handle requests.

**Mistake 8 — Registering the same listener in both spring.factories and addListeners.** This can instantiate and invoke it twice, causing duplicate side effects. Choose one registration mechanism matching the desired scope.

## 12. Checklist When Applying in an Application

1. Do you genuinely need to act **before `ApplicationContext` creation**, or would a later hook be simpler to implement?
2. Has the listener been registered before `run(...)` via the proper mechanism?
3. Does all logic depend solely on `Environment`/startup arguments, without depending on uncreated beans?
4. If reading configuration, have the values and `PropertySource` precedence been verified at the exact timing?
5. Have you avoided logging secrets and avoided blocking operations during startup?
6. Is `EnvironmentPostProcessor` needed if you are modifying property sources?
7. On restarts or multiple contexts, is the logic safe when executed repeatedly?
8. Have you tested with/without the property and invalid-configuration cases?

**Takeaway:** `ApplicationEnvironmentPreparedEvent` enables handling the **Environment very early** in Spring Boot startup. Register the listener **before running SpringApplication**, use it for concise bootstrap responsibilities, and wait for later events when beans, context, or ready state are required.

## References

- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners): list of events and instructions for registering listeners before context creation.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, precedence, and command-line configuration.
- [Spring Boot — Customize the Environment or ApplicationContext](https://docs.spring.io/spring-boot/how-to/application.html): how to register `ApplicationListener`, `ApplicationContextInitializer`, and `EnvironmentPostProcessor`.
- [Spring Boot API — ApplicationEnvironmentPreparedEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html): event type and provided information.
