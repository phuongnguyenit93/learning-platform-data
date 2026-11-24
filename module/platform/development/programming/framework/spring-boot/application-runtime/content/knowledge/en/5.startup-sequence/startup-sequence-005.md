# Creating ApplicationContext and Applying Initializers in the Spring Boot Startup Sequence

## 1. The Big Picture: "Shell" First, Beans Later

When calling `SpringApplication.run(...)`, Spring Boot must prepare an **`ApplicationContext`**: the place that manages beans, configuration, events, and application resources. A very important question is: if we want to customize the context *before application beans are created*, where do we intervene?

Spring Boot provides `ApplicationContextInitializer` for this. It receives **a newly created and preliminarily prepared context that has not yet been `refresh()`ed**, allowing initialization configuration changes before loading and building beans completes.

Think of opening a workshop:

- **`SpringApplication`** is the coordinator opening the workshop.
- **`ApplicationContext`** is the workshop floor and resource management system.
- **`ApplicationContextInitializer`** is the step of preparing the floor before bringing in machinery and workers.
- **Bean definitions** are the blueprints describing what components are needed and how to create them.
- **`refresh()`** is the phase of constructing and activating components according to configuration.
- **`ApplicationRunner`** is work that runs after the context is ready to operate.

If you need to register a shared `PropertySource` before Spring processes beans, an initializer may fit. If you want to use an injected `UserService` to load data from a database, an initializer is usually **too early**.

This lesson uses Spring Boot **3.3.x**, Spring Framework 6.x, and Java **17+** APIs. The examples use an application without opening an HTTP server to make observing the order easier; the initializer mechanism still applies to Servlet and Reactive apps.

## 2. Where Is the Context Created in the Overall Startup Sequence?

A typical startup sequence:

```text
main(String[] args)
    |
    v
SpringApplication.run(args)
    |
    +-- Prepare listeners / bootstrap / Environment
    |       |
    |       +-- ApplicationStartingEvent
    |       +-- ApplicationEnvironmentPreparedEvent
    |
    +-- Determine context type and CREATE ApplicationContext object
    |       |
    |       +-- Attach Environment; prepare context configuration
    |       +-- applyInitializers(context)
    |       |       |
    |       |       +-- initializer.initialize(context)  [not yet refreshed]
    |       |
    |       +-- ApplicationContextInitializedEvent
    |
    +-- Load application configuration sources / bean definitions
    |       |
    |       +-- ApplicationPreparedEvent
    |
    +-- context.refresh()
    |       |
    |       +-- BeanFactoryPostProcessor / BeanPostProcessor
    |       +-- Instantiate non-lazy singletons, inject dependencies
    |       +-- Start web infrastructure if present
    |       +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
```

The diagram shows the **order of major milestones**, without describing every internal callback. Events like `WebServerInitializedEvent` only exist when using an appropriate web environment and can occur during the `refresh()` phase.

Four milestones to remember:

1. **`ApplicationEnvironmentPreparedEvent`**: `Environment` has been prepared, but no application context exists yet.
2. **Initializers run**: the context exists and has `Environment` attached; application bean definitions have not yet been loaded by the normal `SpringApplication` sequence.
3. **`ApplicationContextInitializedEvent`**: `ApplicationContextInitializer` instances have finished running, right before loading bean definitions.
4. **`ApplicationPreparedEvent`**: bean definitions have been loaded, but `refresh()` has not started yet.

By `ApplicationStartedEvent`, the context has finished refreshing; by `ApplicationReadyEvent`, runners have also executed. Therefore, **"context created", "context initialized by initializers", "context refreshed", and "application ready" are four distinct concepts**.

## 3. Which ApplicationContext Type Does Spring Boot Choose and Create?

`ApplicationContext` is an interface for lifecycle management and bean access. `ConfigurableApplicationContext` exposes additional operations for the configuration phase such as `setEnvironment(...)`, `addApplicationListener(...)`, `addBeanFactoryPostProcessor(...)`, `refresh()`, and `close()`.

Normally you do not manually write `new AnnotationConfigApplicationContext()` in a Boot application. `SpringApplication` uses `ApplicationContextFactory` to create the appropriate context type based on `WebApplicationType` and the classpath:

| `WebApplicationType` | Context typically created | Meaning |
| --- | --- | --- |
| `NONE` | `AnnotationConfigApplicationContext` | Holds beans and configuration; does not start a web server. |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` | Supports Servlet web servers and Spring MVC infrastructure. |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` | Supports reactive web servers and Spring WebFlux. |

Examples:

- A CLI tool using only `spring-boot-starter` typically creates a non-web context.
- A REST API with `spring-boot-starter-web` typically creates a Servlet context.
- A WebFlux server using only `spring-boot-starter-webflux` typically creates a Reactive context.

This is the default in Spring Boot 3.3; `setApplicationContextFactory(...)` can replace context creation when genuinely special requirements exist.

**Difference between creating the object and refreshing:** `ApplicationContextFactory` selects **the context class/instance**; initializers customize **that instance before refresh**; only `refresh()` triggers building beans and context infrastructure. An initializer cannot change a Servlet context into a Reactive context merely by adding a property after the instance has already been chosen.

## 4. What Is `ApplicationContextInitializer`?

The interface is conceptually defined as follows:

```java
@FunctionalInterface
public interface ApplicationContextInitializer<
        C extends ConfigurableApplicationContext> {
    void initialize(C applicationContext);
}
```

This is an abbreviated signature to explain the contract; use Spring Framework's real interface `org.springframework.context.ApplicationContextInitializer`.

`initialize(...)` is called **before `refresh()`**. You neither need nor are allowed to call `refresh()` yourself inside a Boot initializer. The `context` parameter is the exact instance that Boot will continue loading configuration into, refresh, and return after startup succeeds.

Initializers are typically suitable for:

- Intentionally adding a `PropertySource` to the context's `Environment`.
- Registering an `ApplicationListener` that must exist before context refresh.
- Registering a `BeanFactoryPostProcessor` so it runs at the proper stage of `refresh()`.
- Configuring certain context initialization behaviors or low-level framework/library integrations.

Safe methods with a clear contract include:

```java
context.getEnvironment().getPropertySources().addLast(propertySource);
context.addApplicationListener(listener);
context.addBeanFactoryPostProcessor(postProcessor);
```

These three lines **illustrate calls you can make inside `initialize(...)`**, not a standalone Java file. The variables `propertySource`, `listener`, and `postProcessor` must be created with their corresponding types before use.

**Things not to do inside an initializer:** calling `context.getBean(...)` to retrieve business beans, assuming `@Autowired` has already occurred, accessing beans that have gone through `@PostConstruct`, or serving HTTP requests. Here, the context has only been preliminarily configured; full bean registration and initialization have not completed.

An early-registered `ApplicationContextInitializer` is normally instantiated or received directly by Spring Boot as **a startup configuration object**. Do not assume simply annotating an initializer class with `@Component`/`@Bean` will make Boot automatically discover and call it in this phase: bean scanning happens too late to replace the initializer registration mechanism.

## 5. Why Is Environment Available Before Beans Are Created?

`Environment` represents configuration property sources and profiles. Spring Boot prepares it **before creating the context**: combining information from the OS, command-line arguments, application configuration, and other configuration mechanisms.

When `ApplicationContextInitializer.initialize(context)` runs, you can generally use:

```java
ConfigurableEnvironment env = context.getEnvironment();
String value = env.getProperty("demo.mode");
boolean active = env.acceptsProfiles(Profiles.of("dev"));
```

This is a snippet inside an initializer, requiring imports for `ConfigurableEnvironment` and `Profiles`. It reads properties and profile state from `Environment`. However, adding a property inside an initializer does not cause *all* earlier startup steps to re-run.

For example, if `WebApplicationType` has already been determined by Boot and the context has already been created, adding `spring.main.web-application-type=reactive` here **cannot turn back time** to swap the already-chosen context instance. Customizations that must occur **before the context exists** need to be configured on `SpringApplication`, startup config sources, or an earlier extension point.

### 5.1. Precedence Order of PropertySource

`MutablePropertySources` provides operations such as:

- `addFirst(...)`: adds a source with high precedence among the current sources.
- `addLast(...)`: adds a source with low precedence.
- `addBefore(name, source)` / `addAfter(name, source)`: positions relative to a named source.

Avoid accidentally using `addFirst` to override command-line arguments, environment variables, or external configuration that operators need the right to change. For **default values**, `addLast` is usually more appropriate; for **custom precedence policies**, state the order explicitly and test key-collision scenarios.

Do not write passwords, tokens, sensitive data, or the entire `Environment` into diagnostic logs. Even though an initializer runs before beans, it can already see properties prepared for startup.

## 6. Runnable Example: Adding a Property and Observing Exactly Three Milestones

The following example consists of **a single complete Java file**. For simplicity and reproducible results, we use `WebApplicationType.NONE`, opening no HTTP server.

**Requirements:** a Gradle project created with Spring Boot 3.3.x, Java 17+, and the `spring-boot-starter` dependency. Place the file at `src/main/java/com/example/bootstrap/ContextInitializerDemoApplication.java`.

```java
package com.example.bootstrap;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class ContextInitializerDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ContextInitializerDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.addInitializers(new DefaultMessageInitializer());

        ApplicationListener<ApplicationContextInitializedEvent> listener =
                event -> System.out.println(
                        "2 EVENT context active="
                                + event.getApplicationContext().isActive());
        app.addListeners(listener);

        app.run(args);
    }

    public static class DefaultMessageInitializer
            implements ApplicationContextInitializer<ConfigurableApplicationContext> {

        @Override
        public void initialize(ConfigurableApplicationContext context) {
            MapPropertySource defaults = new MapPropertySource(
                    "demoInitializerDefaults",
                    Map.of("demo.message", "Hello from initializer")
            );

            context.getEnvironment()
                    .getPropertySources()
                    .addLast(defaults);

            System.out.println(
                    "1 INITIALIZER context active=" + context.isActive()
            );
        }
    }

    @Bean
    ApplicationRunner printMessage(Environment environment) {
        return args -> System.out.println(
                "3 RUNNER message=" + environment.getProperty("demo.message")
        );
    }
}
```

**Why is this code valid?**

1. `new SpringApplication(...)` allows registering initializers and listeners **before** `run`.
2. `app.setWebApplicationType(NONE)` keeps the example in a context without an HTTP server.
3. `DefaultMessageInitializer` implements the exact generic `ApplicationContextInitializer<ConfigurableApplicationContext>`; `MapPropertySource` provides a default property.
4. `ApplicationContextInitializedEvent` is received by the early-registered listener after initializers have run, yet before loading bean definitions.
5. The `@Bean printMessage` method is only processed by Spring during configuration/refresh; its `ApplicationRunner` is called **after refresh completes**.

### 6.1. Minimal Dependencies

In a project already set up with the Spring Boot Gradle plugin 3.3.x and matching dependency management, the sufficient dependency section for this example is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

`spring-boot-starter-web` is not needed. For a non-web example, do not use `curl` to test because no HTTP server is started.

### 6.2. Running and Reading the Output

```bash
./gradlew bootRun
```

On Windows CMD use `gradlew.bat bootRun`; in PowerShell you can use `.\gradlew.bat bootRun`.

Ignore the banner and interleaved Spring Boot log lines. The three lines from the example itself, in order, are:

```text
1 INITIALIZER context active=false
2 EVENT context active=false
3 RUNNER message=Hello from initializer
```

Explaining stdout:

- The first two lines print `false` because at the time of the initializer and `ApplicationContextInitializedEvent`, the context has **not yet refreshed** and is therefore not active.
- The third line prints after the context has refreshed and the `ApplicationRunner` bean has been created.
- This is **the order of logs printed by the program itself**, without guaranteeing that framework logs will not interleave between them.
- For a `NONE` application with no background thread keeping the JVM alive, the process may exit after startup/runners finish.

If run with a property from the command line:

```bash
./gradlew bootRun --args='--demo.message=From command line arg'
```

The runner line is expected to become `3 RUNNER message=From command line arg` because the `demoInitializerDefaults` source was added with `addLast`. On Windows CMD, argument quoting may differ; you can place the property in `application.properties` to test precedence simply.

**Takeaway:** an initializer can modify the configuration environment before beans exist; it is not the place to handle business work after the application is ready.

## 7. Ways to Register `ApplicationContextInitializer`

### 7.1. Explicit Registration in `main`

This is the most readable approach when the initializer belongs to a specific application:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addInitializers(new MyInitializer());
app.run(args);
```

These three lines are a snippet inside the `main` method of `MyApplication`; `MyInitializer` must implement `ApplicationContextInitializer`. `addInitializers(...)` adds the initializer to the existing set of initializers, including those registered by Boot.

You can replace it with `app.setInitializers(...)` when you genuinely want to **replace the entire set of initializers**; replacing can drop initializers required by Boot or libraries, so do not use it as a normal "add" operation.

### 7.2. `SpringApplicationBuilder`

When you want a fluent API or have multiple startup configurations:

```java
new SpringApplicationBuilder(MyApplication.class)
        .initializers(new MyInitializer())
        .web(WebApplicationType.NONE)
        .run(args);
```

This is also a snippet in `main`, requiring imports for `SpringApplicationBuilder` and `WebApplicationType`; `MyApplication`/`MyInitializer` are application-defined classes. Fundamentally, the initializer still runs **after the context is created and before `refresh()`**.

### 7.3. Auto-Registration via `META-INF/spring.factories`

Suitable when developing a shared library and multiple Boot applications need the same early customization step. Inside the JAR artifact, add the file:

**`src/main/resources/META-INF/spring.factories`**

```properties
org.springframework.context.ApplicationContextInitializer=\
com.example.bootstrap.TraceInitializer
```

The specified class must implement `ApplicationContextInitializer` and be instantiable by the factory loading mechanism. Standalone class example:

**`src/main/java/com/example/bootstrap/TraceInitializer.java`**

```java
package com.example.bootstrap;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public class TraceInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    public TraceInitializer() {
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        System.out.println("TraceInitializer before refresh");
    }
}
```

Boot discovers initializers from `META-INF/spring.factories` on the classpath when instantiating `SpringApplication`. **This is an alternative** to manual registration; do not both declare the same class in `spring.factories` and add it manually unless you want the risk of running it twice.

Note: do not confuse `META-INF/spring.factories` used for initializers/listeners with the registration mechanism for **auto-configuration classes** that changed in Spring Boot 3.x. They serve different registration needs.

## 8. Ordering When There Are Multiple Initializers

An application can receive initializers from Spring Boot, supporting libraries, and the application code itself. When ordering matters, use `org.springframework.core.Ordered` or the `@Order` annotation.

For example, an initializer class in a project can declare:

```java
package com.example.bootstrap;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.Ordered;

public class FirstInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext>,
                   Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        System.out.println("Initializer first");
    }
}
```

The rest of the application must **register** `FirstInitializer` using one of the ways described above. Lower numbers returned by `getOrder()` have higher priority to run earlier per Boot's sorting mechanism. Avoid relying on arbitrary ordering among initializers with the same order value.

**Ordered dependency scenario:** initializer A needs to add a `PropertySource`, and initializer B reads that property. If A and B are not explicitly ordered, B may run before the property exists. Document the dependency between them and verify actual order via logs/tests.

Do not confuse initializer ordering with bean initialization ordering (`@DependsOn`, `@Order` on bean collections, `SmartLifecycle`): those are different lifecycle layers.

## 9. Distinguishing From Other Initialization Mechanisms

| Mechanism | When it runs | What is it for? | Can it retrieve normal business beans? |
| --- | --- | --- | --- |
| `BootstrapRegistryInitializer` | During bootstrap before a full context exists | Register temporary bootstrap objects/infrastructure | Should not depend on context beans. |
| `EnvironmentPostProcessor` | Early `Environment` preparation | Configuration sources, properties before context creation | Context beans do not exist yet. |
| `ApplicationContextInitializer` | Context created, **before loading bean definitions/refresh** | Customize context/environment, register post-processors/listeners | Not yet. |
| `BeanDefinitionRegistryPostProcessor` | While processing bean definitions in `refresh()` | Add/modify bean definitions before beans are instantiated | Should not depend on business singletons. |
| `BeanFactoryPostProcessor` | In `refresh()`, before normal singleton instantiation | Modify BeanFactory metadata/configuration | Should not instantiate business beans early. |
| `BeanPostProcessor` | Surrounds each bean's initialization | Customize bean instances, proxies, callbacks | Works on the bean currently being created. |
| `@PostConstruct` | When a specific bean is initialized | Finalize internal configuration of the bean | Dependencies already injected per bean lifecycle. |
| `ApplicationRunner`/`CommandLineRunner` | **After context refresh** | Startup tasks needing beans/infrastructure | Yes. |
| `ApplicationReadyEvent` | After runners | Observe milestone when Boot completes startup | Yes. |

Choose an extension point by **when you truly need it**. If you need to populate a cache from a repository, use a runner or a service with an explicit lifecycle; do not put heavy database queries into an initializer. If you need to add configuration for bean construction itself, an initializer may fit, whereas if you must influence **config-loading** or **context type selection** early, use an earlier mechanism.

### 9.1. An Initializer Is Not an Application-Wide `@PostConstruct`

`@PostConstruct` only runs after an individual bean has been created and its dependencies injected. An initializer can run when **no application beans exist yet**. Do not use `@PostConstruct` to simulate preparing the context before bean definitions.

### 9.2. An Initializer Is Not an `ApplicationListener`

- An initializer receives `ConfigurableApplicationContext` directly and is invoked by Boot to customize it before refresh.
- A listener reacts to a specific `ApplicationEvent`, such as `ApplicationContextInitializedEvent` or `ApplicationReadyEvent`.
- `ApplicationContextInitializedEvent` **is published after all initializers have been applied**; a listener for it does not replace the early initialization role of an initializer.

Specifically, a listener for very early events must be registered before `run` (via `addListeners(...)` or an appropriate early registration mechanism). An `@EventListener` in an application bean will be created too late to catch `ApplicationStartingEvent` or `ApplicationContextInitializedEvent` in that startup run.

## 10. Real-World Scenarios and Choosing the Right Spot

### Scenario A — Adding Defaults for an Internal Library

A library has a property `acme.feature.mode`; applications can override it via environment variables or custom configuration. The library's initializer adds a `MapPropertySource` with `addLast(...)`. Beans created afterward can read the default value, while operator configuration can still override it.

**Things to check:** the source name does not collide unintentionally, precedence order is right, no sensitive values are placed in the source, and it is not accidentally applied twice via both manual registration and `spring.factories`.

### Scenario B — Registering a Post-Processor Before Refresh

You need to affect the BeanFactory once bean definitions have been loaded, yet want to decide that at bootstrap time:

```java
@Override
public void initialize(ConfigurableApplicationContext context) {
    context.addBeanFactoryPostProcessor(beanFactory ->
            System.out.println("Bean definitions loaded: "
                    + beanFactory.getBeanDefinitionCount()));
}
```

This is an **illustrative method** inside a class implementing `ApplicationContextInitializer<ConfigurableApplicationContext>`. The callback registered in the initializer will be invoked during `refresh()`, after definitions have been loaded, rather than executing immediately inside `initialize(...)`. Do not use such a callback as an arbitrary way to instantiate business beans early.

### Scenario C — When `WebApplicationType` Must Be Decided

If the goal is to run a CLI without a web server, configure it before creating the context:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
```

Do not add a property changing the web type inside an initializer hoping Boot will destroy the already-created context and recreate a different type. `WebApplicationType` and `ApplicationContextFactory` govern the **context creation** step, which happens before initializers.

### Scenario D — Checking Liveness/Readiness of Dependencies or Loading Initial Data

Use an `ApplicationRunner` with injected services/repositories and explicit error handling. For a web service, runner tasks finish before `ApplicationReadyEvent`; if readiness to accept traffic depends on an initialization step, readiness should reflect that state. An initializer is not the right place to open long-lived connections, load millions of records, or wait indefinitely on external systems.

### Scenario E — Sharing One Initializer Across Multiple Applications

Package it as a library and register it via `spring.factories`. The design must not depend on a specific context type if intended for `NONE`, `SERVLET`, and `REACTIVE` alike. If the initializer needs Servlet/Reactive-specific APIs, apply it only when the instance is compatible and test for each mode.

## 11. Common Errors When Creating Context / Applying Initializers

| Symptom | Common cause | How to check and fix |
| --- | --- | --- |
| `initialize(...)` is never called | Only annotated with `@Component`, not registered with `SpringApplication`/`spring.factories` | Register early via `addInitializers(...)` or factory metadata. |
| `getBean(...)` fails to get a service in initializer | Context not yet refreshed; singletons not yet created | Move to a runner/bean lifecycle or register a post-processor for the right phase. |
| `ApplicationContextInitializedEvent` does not reach `@EventListener` | Listener bean was created after the event milestone | Register listener early via `addListeners(...)`. |
| Property added in initializer does not change web type | `WebApplicationType` already selected and context already created | Set web type before `run` via API or appropriate startup configuration. |
| Default property accidentally overrides operator values | Used `addFirst(...)` for a source that should have low precedence | Choose `addLast(...)`, inspect property source order and override results. |
| Code runs twice or initializer logs duplicate | Initializer registered in multiple places, or multiple contexts starting | Check `spring.factories`, `main`, context hierarchy/test configuration. |
| Order between two initializers is wrong | Neither `Ordered`/`@Order` used, or both share the same order | Set explicit ordering and verify dependencies. |
| Startup halts before `ApplicationPreparedEvent` | Initializer throws an exception or configuration error before refresh | Inspect root stack trace, early-registered `ApplicationFailedEvent` listener, property sources. |
| Application starts unusually slowly | Initializer performs network I/O, reads too much data, or waits indefinitely | Move heavy work to runners/services and use timeouts and selective logging. |
| Works in one JVM mode but fails in another | Cast initializer to an incompatible context subtype | Use `ConfigurableApplicationContext` when possible; check class before casting. |

### 11.1. Why Shouldn't You Call `refresh()` or `close()` From an Initializer?

`SpringApplication` owns the lifecycle sequence. Calling `context.refresh()` too early can instantiate beans before Boot loads all configuration sources and registers listeners/post-processors. Calling `context.close()` breaks the bootstrap process. Let Boot manage those two milestones; an initializer only performs customizations designed for the pre-refresh phase.

### 11.2. What If an Initializer Throws an Exception?

Startup failure can occur before ordinary beans are created. Boot handles the error within the startup sequence and may publish `ApplicationFailedEvent`; there is no `ApplicationReadyEvent` when startup fails. If very early errors must be recorded, the listener must also be registered early. Avoid swallowing exceptions and letting the application continue with broken configuration; when a safe fallback is genuinely viable, define the fallback conditions and observability clearly.

### 11.3. Can There Be Multiple ApplicationContexts?

Yes. A simple application usually has only one main context; systems with parent/child hierarchies, multiple `SpringApplication` instances, or certain tests can create multiple contexts. Identify **which `SpringApplication`** the initializer is attached to, and remember that events from a child context can propagate to ancestor listeners. Do not build policies assuming a process-wide initializer or listener is guaranteed to run only once.

## 12. QA Checklist When Modifying an Initializer

When modifying an initializer actually used in a project, verify by **behavior**:

1. Record the actual `ApplicationContext` created for `NONE`, `SERVLET`, or `REACTIVE`.
2. Confirm the initializer runs before `ApplicationContextInitializedEvent` and before `refresh()`; avoid fetching beans.
3. Verify property sources on key collisions: do values from config/CLI override as intended?
4. Verify `Ordered` if more than one initializer depends on another.
5. Verify the failure path: when the initializer fails, the application does not falsely report ready.
6. Re-verify the real runtime mode along with relevant integration/test profiles; do not extrapolate from logs of a single environment.
7. Do not put tokens or sensitive data into logs to prove execution.

A simple test for the example in section 6 is to change the value of `demo.message` from external configuration and confirm the runner log picks up the new value; the `INITIALIZER` and `EVENT` logs must still appear **before** the `RUNNER` log.

## 13. Key Takeaways

- **Creating the context** = instantiating a `ConfigurableApplicationContext` of the right type for Boot to continue configuring.
- **Applying initializers** = calling `initialize(context)` on registered `ApplicationContextInitializer` instances, **before `refresh()`**.
- **`ApplicationContextInitializedEvent`** confirms initializers have run and loading bean definitions along the main startup sequence still lies ahead.
- **`ApplicationPreparedEvent`** occurs after bean definitions have been loaded, right before refresh.
- **`refresh()`** executes the core work of building beans, post-processors, singleton lifecycle, and (if present) web infrastructure.
- **`ApplicationRunner`** runs after refresh; suitable for tasks needing business beans.
- **`SpringApplication`** manages the entire sequence. Choose the right extension point and do not force a lifecycle stage earlier than the framework supports.

## 14. Official Spring Documentation

- [Spring Boot 3.3 — `SpringApplication`: application events and startup order](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — `SpringApplication` API: createApplicationContext, setApplicationContextFactory, addInitializers, applyInitializers](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot — Customize the Environment or ApplicationContext Before It Starts](https://docs.spring.io/spring-boot/how-to/application.html)
- [Spring Framework 6.1 — `ApplicationContextInitializer` API](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
- [Spring Framework 6.1 — `ConfigurableApplicationContext` API](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
