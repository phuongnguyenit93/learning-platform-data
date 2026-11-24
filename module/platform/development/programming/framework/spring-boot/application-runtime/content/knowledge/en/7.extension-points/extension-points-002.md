# ApplicationContextInitializer and Pre-Refresh Operations

## 1. When do you need to intervene before Spring refreshes the context?

A Spring Boot application does not create all beans immediately when the JVM starts. `SpringApplication` prepares the `Environment`, creates the `ApplicationContext`, loads configuration sources and bean definitions, and then calls `refresh()` to perform container setup steps and instantiate the required beans.

If you must **configure a context that has been created but not yet refreshed**, Spring Framework provides the `ApplicationContextInitializer` callback. Spring Boot knows how to invoke this callback during the bootstrap phase before loading primary sources and before calling `refresh()`.

Suitable use cases include:

- Adding a property source so that beans created afterward can read it.
- Setting an ID or configuring a property on the context before refresh.
- Registering bean definitions programmatically, in context types that support it.
- Attaching a `BeanFactoryPostProcessor` so Spring invokes it during the proper bean factory processing phase.
- Providing a bootstrap integration point for a library that needs to supply information before the application builds beans.

**Principle:** an initializer works in the **container configuration phase**. It is not the place to use repositories, HTTP clients, injected beans, or run post-startup business tasks.

This content applies to **Spring Boot 3.3.x**, **Spring Framework 6.1.x**, and **Java 17+**. Class names, event timing, and APIs should be checked when upgrading major versions.

## 2. API contract and the meaning of "before refresh"

Main interface:

```java
package org.springframework.context;

@FunctionalInterface
public interface ApplicationContextInitializer<C extends ConfigurableApplicationContext> {
    void initialize(C applicationContext);
}
```

This is a **condensed signature for study**, not a file to redefine in your project. Spring already provides this interface. The type parameter `C` is a subtype of `ConfigurableApplicationContext`; the `initialize(C)` callback receives a context that has been created and prepared, **not yet refreshed**.

`ConfigurableApplicationContext` allows access to `ConfigurableEnvironment`, setting the context ID, adding post-processors, and adjusting certain infrastructure components. With `GenericApplicationContext`, you can call `registerBean(...)` to register bean definitions early.

It **does not mean** any of the following:

- The context already has `isActive() == true`: no, in a typical initializer it is `false`.
- All bean definitions have been loaded: no; Boot's primary sources are loaded **after** initializers.
- Beans are created and `@PostConstruct` has run: no; most bean processing occurs during refresh.
- `ApplicationRunner` has run: no; runners come after refresh and `ApplicationStartedEvent`.
- The Web server is accepting requests: cannot be assumed at this point.

If an initializer calls `context.getBean(SomeService.class)`, the call may fail because the context has not refreshed and the bean does not exist yet. You should **register definitions** so Spring creates beans in a later step instead of building the dependency graph too early.

## 3. Exact position in the Spring Boot 3.3 startup sequence

```text
main() -> new SpringApplication(MyApp.class)
         -> addInitializers(...) / addListeners(...)
         -> run(args)
              |
              +--> ApplicationStartingEvent
              +--> prepare Environment, ConfigData, command-line options
              +--> ApplicationEnvironmentPreparedEvent
              +--> create appropriate ApplicationContext
              +--> attach Environment to context
              |
              +--> ApplicationContextInitializer.initialize(context)
              |      ^ context created, not refreshed yet
              |
              +--> ApplicationContextInitializedEvent
              |      ^ initializers have run, primary sources not loaded yet
              |
              +--> load primary bean definitions / sources
              +--> ApplicationPreparedEvent
              |      ^ sources loaded, context not refreshed yet
              |
              +--> refresh(context)
              |      +--> bean factory/registry post-processors
              |      +--> wiring, singleton creation, lifecycle callbacks
              |      +--> web server setup if present
              |
              +--> ApplicationStartedEvent
              +--> ApplicationRunner / CommandLineRunner
              +--> ApplicationReadyEvent
              +--> return ApplicationContext
```

From the diagram, distinguish **three states**: the context exists, definitions have been loaded, and the context has been refreshed. `ApplicationContextInitializer` runs in the first state. `ApplicationPreparedEvent` belongs to the second state. `ApplicationStartedEvent` belongs to the third state.

Spring Boot may add other events/processors between milestones, especially in web or multi-context applications. However, the relative order above is an important contract for Boot 3.3.x.

### 3.1. Why does ApplicationContextInitializedEvent not mean beans exist yet?

`ApplicationContextInitializedEvent` is fired by Boot **after invoking all initializers but before loading primary bean definitions**. The word "Initialized" here describes the context preparation phase, not that singletons have been instantiated.

`ApplicationPreparedEvent` is a different milestone: it occurs **after bean definitions have been loaded but before refresh**. If you need to act on existing definitions, typically use a post-processor or an appropriate event rather than assuming an initializer sees all definitions.

### 3.2. Environment is ready, though early steps have already run

By the time an initializer is called, `Environment` has already been prepared and attached to the context. Certain decisions such as loading config data, profile-specific configuration, and selecting the context type have happened earlier. Therefore, "before refresh" **does not** mean "every bootstrap configuration can be changed".

## 4. Suitable operations inside an initializer

| Operation | Should you do it? | Reason |
| --- | --- | --- |
| Read `context.getEnvironment().getProperty(...)` | Yes | Environment already exists |
| Add a `PropertySource` | Yes | Values can be read during subsequent bean creation |
| `context.setId("...")` | Yes when needed | Set context identifier before refresh |
| `context.addBeanFactoryPostProcessor(...)` | Yes | Register a processor to be invoked during refresh |
| `GenericApplicationContext.registerBean(...)` | Yes, when context is of this type | Register bean definition without using the bean prematurely |
| Call `getBean(OrderService.class)` | Should not | Bean factory and singletons are not in a normal usable state yet |
| Call `context.refresh()` manually | No | Boot manages refresh and lifecycle |
| Expect `@Autowired` to inject services into the initializer | Not by default | Initializers are usually created during bootstrap, not as Spring beans |
| Query database to preload data via repository bean | Not appropriate | Repositories require a fully initialized context; use a runner after refresh |
| Change web application type at this moment | Unreliable | The context type was already chosen and created before the initializer |
| Change active profiles expecting Boot to reload all ConfigData | Unreliable | Profile-based ConfigData processing may have already completed |

**Type constraint:** `ApplicationContextInitializer<ConfigurableApplicationContext>` works against a general abstraction. Only use `GenericApplicationContext` APIs after an `instanceof` check, because context types or custom context factories may vary.

## 5. Runnable example: an initializer modifying Environment and registering a bean

Experiment goal: print the event order, confirm `isActive()` is still false inside the initializer, register a bean without `@Component`, and then prove an `ApplicationRunner` after refresh receives both the bean and the property.

### 5.1. Java 17 / Spring Boot 3.3 project configuration

Create a Gradle Groovy project with Gradle Wrapper and `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

`settings.gradle`:

```groovy
rootProject.name = 'context-initializer-lab'
```

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Using a non-web context keeps the experiment independent of an HTTP server and makes log ordering easy to observe.

### 5.2. A complete single Java file

Create **`src/main/java/com/example/initializer/InitializerLabApplication.java`**:

```java
package com.example.initializer;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class InitializerLabApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(InitializerLabApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        // Register initializer from bootstrap, without @Component.
        app.addInitializers(new EarlySetup());

        // Early events: register listeners directly on SpringApplication.
        app.addListeners(
                (ApplicationListener<ApplicationContextInitializedEvent>) event ->
                        System.out.println("02 ContextInitializedEvent"));
        app.addListeners(
                (ApplicationListener<ApplicationPreparedEvent>) event ->
                        System.out.println("03 ApplicationPreparedEvent"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("07 main after run: " + context.isActive());
        }
    }

    static final class EarlySetup
            implements ApplicationContextInitializer<ConfigurableApplicationContext> {

        @Override
        public void initialize(ConfigurableApplicationContext context) {
            System.out.println("01 initializer active: " + context.isActive());

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "initializer-demo",
                            Map.<String, Object>of(
                                    "demo.message", "Hello from initializer")));

            if (!(context instanceof GenericApplicationContext generic)) {
                throw new IllegalStateException(
                        "This exercise requires GenericApplicationContext");
            }

            // Only register the bean definition, do not call getBean().
            generic.registerBean(StartupMarker.class, StartupMarker::new);
        }
    }

    // No @Component: registered solely by the initializer.
    static final class StartupMarker {
        String label() {
            return "early-registered bean";
        }
    }

    @Bean
    ApplicationRunner demoRunner(
            StartupMarker marker,
            @Value("${demo.message}") String message) {
        return args -> System.out.println(
                "05 runner: " + message + " | " + marker.label());
    }

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("04 ApplicationStartedEvent");
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("06 ApplicationReadyEvent");
    }
}
```

This is **a complete program in a single file** with nested classes; there is no need to create separate files for the initializer or marker. `@SpringBootApplication` serves as the primary source.

**Why does this program properly demonstrate the lifecycle?**

1. `EarlySetup` is passed directly to `SpringApplication` before `run(...)`, so it runs even **without `@Component`**.
2. When the initializer runs, the context is not active yet: `isActive()` prints `false`.
3. `MapPropertySource` adds the `demo.message` key to the Environment. The `Map.<String,Object>of(...)` syntax matches the exact generic type required by the `MapPropertySource` constructor.
4. `GenericApplicationContext.registerBean(...)` stores the definition for `StartupMarker`. This does not retrieve the bean via `getBean(...)`.
5. After refresh, Spring injects `StartupMarker` and the value of `demo.message` into the `ApplicationRunner` bean.
6. Listeners for `ApplicationContextInitializedEvent` and `ApplicationPreparedEvent` are registered **directly from bootstrap**. They arrive too early to rely on a bean listener using only `@EventListener`.
7. The two `@EventListener` methods on the application class listen for `ApplicationStartedEvent` and `ApplicationReadyEvent` after the context has refreshed.

### 5.3. Run command and output

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Lines **explicitly printed by the Java code** in order when no arguments are passed:

```text
01 initializer active: false
02 ContextInitializedEvent
03 ApplicationPreparedEvent
04 ApplicationStartedEvent
05 runner: Hello from initializer | early-registered bean
06 ApplicationReadyEvent
07 main after run: true
```

Gradle may emit additional build messages. The properties in the example disable the banner and INFO startup logs for easier reading; configuration errors or surrounding tools may produce extra output.

**Verification checkpoints:** Line 01 shows `false`; line 02 comes after the initializer; line 03 comes before refresh; lines 04 and 05 come after refresh; line 06 comes after the runner; line 07 appears after `SpringApplication.run(...)` returns.

### 5.4. Try changing things to understand the causes

- **Remove `app.addInitializers(new EarlySetup())`:** `StartupMarker` is no longer registered by the initializer and `demo.message` no longer has a source in the example; building the runner will fail due to a missing dependency or placeholder.
- **Remove only `registerBean(...)`:** the `@Bean demoRunner` method requires `StartupMarker` which the container does not have; startup fails.
- **Change the property in `MapPropertySource`:** line 05 changes its message without modifying the `demoRunner` code.
- **Move `context.getBean(StartupMarker.class)` into `initialize(...)`:** no longer guaranteed to work because the context has not refreshed yet; this is a counterexample of overly early access.
- **Only add `@Component` to `EarlySetup` and remove `addInitializers`:** component scanning happens too late for Boot to invoke the callback automatically; the mechanism has changed.
- **Switch to a Servlet/Reactive application:** requires the corresponding web dependency and checking the context type when using `registerBean(...)`. Initializer timing still remains before refresh.

## 6. How to register an initializer in Spring Boot?

### 6.1. addInitializers on SpringApplication

```java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addInitializers(new MyInitializer());
application.run(args);
```

This is an **illustrative snippet**, not a standalone Java file; real `MyApplication` and `MyInitializer` classes are required. `addInitializers(...)` appends callbacks. `setInitializers(collection)` replaces the callback set on the `SpringApplication` instance; do not use it carelessly if your goal is only to add one.

### 6.2. SpringApplicationBuilder

```java
new SpringApplicationBuilder(MyApplication.class)
        .initializers(new MyInitializer())
        .run(args);
```

Requires importing `org.springframework.boot.builder.SpringApplicationBuilder`. The builder is convenient when there are multiple bootstrap options or a context hierarchy; the initializer is attached to the bootstrap configuration rather than waiting for DI.

### 6.3. META-INF/spring.factories

With Spring Boot 3.x, a library can declare an `ApplicationContextInitializer` for Spring Boot to discover via `META-INF/spring.factories`.

File `src/main/resources/META-INF/spring.factories`:

```properties
org.springframework.context.ApplicationContextInitializer=\
com.example.initializer.ExtraInitializer
```

`ExtraInitializer` is an **illustrative class name** that you must implement yourself with an appropriate constructor for Boot to instantiate. Do not paste configuration if the class does not exist yet. This approach is useful for early-initializing integrations/libraries, though it can easily affect multiple applications sharing the dependency.

**You cannot simply put `@Component` on an initializer and expect Spring Boot to discover it before refresh.** Component scanning and bean creation belong to a later phase.

## 7. Ordering multiple initializers and repeated execution

Spring Boot applies ordering to initializers, supporting `Ordered` or `@Order`.

```java
public class ExampleInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext>,
                   Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.setId("example-context");
    }
}
```

This is an **illustrative class snippet**: import `Ordered`, `ApplicationContextInitializer`, and `ConfigurableApplicationContext` if used standalone.

- Smaller order values generally have higher priority.
- If two initializers modify the same `PropertySource` or register the same bean name, design conflict handling explicitly; do not assume they can be mixed in any order.
- An initializer may be applied to multiple contexts or multiple runs. Write logic that can repeat safely and avoid storing `ApplicationContext` in a `static` field.
- Only check the context type when a specific API is genuinely needed; do not assume every context is a Servlet web context.

## 8. PropertySource, precedence, and timing limits

`ConfigurableEnvironment` holds a collection of `PropertySource` entries in priority order. For example:

```java
context.getEnvironment().getPropertySources().addFirst(
        new MapPropertySource(
                "early-config",
                Map.<String, Object>of("feature.mode", "strict")));
```

`addFirst` places the source at **very high priority**. If a key collides with a value passed by the operator from the command line, this property source can shadow that override. Choose `addFirst(...)`, `addLast(...)`, or a specific position based on precedence requirements and operability, rather than defaulting to `addFirst` every time.

For critical configuration already consumed early by Boot, initializers have limits:

- `Environment` and ConfigData were already prepared in an earlier step. Changing `spring.profiles.active` or `spring.config.import` now may be **too late** to reload the corresponding config files.
- `SpringApplication` already chose and created the `ApplicationContext` type before calling initializers; changing `spring.main.web-application-type` here is not guaranteed to change the context type.
- Several `spring.main.*` properties were already bound into `SpringApplication` before initializers. They must be configured from an appropriate bootstrap phase.

**Choose an earlier extension point** such as `EnvironmentPostProcessor` if you need to change how Boot constructs the Environment, loads config data, or makes bootstrap decisions. Initializers are better suited for configuration that will be used **during subsequent bean construction**.

## 9. Comparison with easily confused extension points

| Extension point | Timing | Appropriate purpose |
| --- | --- | --- |
| `BootstrapRegistryInitializer` | When preparing Boot's bootstrap registry | Supply helper objects during the bootstrap phase |
| `EnvironmentPostProcessor` | During Environment preparation, before context | Modify early configuration sources |
| **`ApplicationContextInitializer`** | Context created, before loading primary sources and refresh | Add property sources, configure context, register beans early |
| `ApplicationContextInitializedEvent` listener | After initializers, before loading primary sources | Observe/adjust at early milestone; listener must be registered from bootstrap |
| `ApplicationPreparedEvent` listener | Bean definitions loaded, before refresh | Observe a fully prepared context |
| `BeanDefinitionRegistryPostProcessor` | During refresh, when processing registry | Add/modify bean definitions once registry is available |
| `BeanFactoryPostProcessor` | During refresh, before creating most singletons | Modify bean factory/definition metadata |
| `@PostConstruct` | When a specific bean is created | Prepare internal state of a single bean |
| `ApplicationStartedEvent` | After refresh, before runners | Observe that startup reached the started milestone |
| `ApplicationRunner` / `CommandLineRunner` | After started, before ready | One-off tasks using injected beans |
| `ApplicationReadyEvent` | After runners | Observe that the application passed startup successfully |

**Practical scenario:** If you need to adjust a value used to build beans, an initializer or early config source is a candidate. If you need `JdbcTemplate`/repositories to preload data, choose a runner or a post-refresh startup mechanism. If you need to intervene in scanned bean definitions, choose a registry/factory post-processor.

## 10. Common errors

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `initialize(...)` never runs | Only used `@Component`, bootstrap callback not registered | Use `addInitializers`, builder, or `spring.factories` |
| `getBean(...)` fails inside initializer | Context not refreshed yet; beans not ready | Switch to registering definitions or wait until after refresh |
| `ClassCastException` when casting context | Assumed wrong context type (NONE/Servlet/Reactive/custom) | Check `instanceof`, use common APIs when possible |
| Command-line property is ignored | `MapPropertySource.addFirst` shadows other sources | Inspect the order of `Environment.getPropertySources()` |
| Changed web type in initializer but context did not change | Context type was already created before callback | Choose type before `run(...)` or via standard config |
| Changed profile but other profile configs did not load | ConfigData was already processed before initializer | Use bootstrap configuration or `EnvironmentPostProcessor` |
| `NoSuchBeanDefinitionException` during refresh | Missing/incorrect bean definition registration or invalid dependency | Inspect registry and root cause |
| Duplicate bean name registration | Multiple initializers or both scan and manual registration for the same bean | Design clear names/conditions, avoid duplication |
| `ApplicationContextInitializedEvent` does not reach `@EventListener` | Bean listener has not been created at that milestone | Use `SpringApplication.addListeners(...)` from bootstrap |
| Startup hangs when initializer calls external API | Heavy/blocking I/O too early | Minimize side effects, move tasks needing beans to runners |
| Initializer fails yet ReadyEvent is still expected | Startup failed before refresh | Read root exception; `ApplicationReadyEvent` will not be fired |

Some events are sent **before listener beans exist**, so when you want to observe or handle very early bootstrap errors, use a listener mechanism registered with `SpringApplication` before running.

To debug, you can log **the initializer name, event milestone, context ID, context type, and non-sensitive property keys**. Never print passwords, tokens, or the entire Environment verbatim.

## 11. Self-check questions

1. **Does an initializer run before or after context creation?** After the context is created, before refresh.
2. **Why can `isActive()` be false inside an initializer?** Because `refresh()` has not been executed yet.
3. **Can `Environment` be read at this time?** Yes, Environment has already been prepared and attached to the context.
4. **Should you retrieve a repository bean inside an initializer?** No; bean definitions/instances are not ready as they are after refresh.
5. **How does `ApplicationContextInitializedEvent` differ from `ApplicationPreparedEvent`?** The first event is after initializers but before loading primary sources; the second is after sources are loaded but before refresh.
6. **Is putting `@Component` on an initializer enough?** No; it must be registered from the bootstrap phase.
7. **What should you use to register a bean programmatically before refresh?** You can use `GenericApplicationContext.registerBean(...)` if the context is compatible, then let the container instantiate the bean according to its lifecycle.
8. **What should you use to change config data/profiles very early?** Consider `EnvironmentPostProcessor` or official bootstrap configuration, instead of relying on an initializer running too late.
9. **Can an initializer call `refresh()` manually?** It should not; Spring Boot manages refresh and event ordering.
10. **What should you use to run tasks using beans after refresh?** `ApplicationRunner` or `CommandLineRunner`, depending on the task.

## 12. Takeaways and references

- `ApplicationContextInitializer<C extends ConfigurableApplicationContext>` is a hook for configuring a **context that has been created but not yet refreshed**.
- Spring Boot 3.3.x invokes initializers **before loading primary bean definitions**, then fires `ApplicationContextInitializedEvent`; loads sources, fires `ApplicationPreparedEvent`, and then refreshes.
- Inside an initializer you can modify `Environment`, configure the context, and register definitions when the context supports it. **Do not retrieve business beans for use yet**.
- Register via `SpringApplication.addInitializers`, `SpringApplicationBuilder.initializers`, or `META-INF/spring.factories`; `@Component` alone is not enough.
- Bootstrap properties may have already been processed. Choose `EnvironmentPostProcessor` if you need to act earlier; use a runner if you need to work after refresh.

Official documentation:

- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), especially the event sequence.
- [Spring Boot 3.3.13 API — SpringApplication](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html), `addInitializers(...)`, `applyInitializers(...)`.
- [Spring Boot 3.3.13 API — ApplicationPreparedEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html).
- [Spring Framework — ApplicationContextInitializer API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextInitializer.html).

To properly diagnose a startup error, determine whether it occurred **before context creation, inside an initializer, while loading bean definitions, during refresh, or after refresh**. These milestones correspond to different extension points and troubleshooting approaches.
